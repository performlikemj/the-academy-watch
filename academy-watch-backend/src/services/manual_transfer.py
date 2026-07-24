"""Single-player manual transfer entry through the durable resolver path."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func
from src.models.funding import ClubProgram
from src.models.journey import PlayerJourney, PlayerJourneyEntry
from src.models.league import Team, TeamProfile, db
from src.models.tracked_player import TrackedPlayer
from src.models.transfer_event import PlayerTransferEvent, TransferAdminEvent
from src.services.journey_sync import JourneySyncService
from src.services.player_suppression import is_player_suppressed
from src.services.season_rollup_service import refresh_player as refresh_season_rollup
from src.services.transfer_events import record_transfer_events
from src.utils.sanitize import sanitize_plain_text

ALLOWED_TRANSFER_TYPES = frozenset({"signed", "loan", "loan_return", "released", "sold"})
_PROVIDER_TYPES = {
    "loan": "Loan",
    "loan_return": "Loan Return",
    "released": "Free agent",
}
_RESOLVER_MOVEMENT_LABELS = frozenset(
    {
        "loan",
        "back from loan",
        "return from loan",
        "end of loan",
        "loan end",
        "loan return",
        "n/a",
        "na",
    }
)


class ManualTransferValidationError(ValueError):
    """The operator request cannot be represented safely."""


class ManualTransferPlayerNotFound(LookupError):
    """The player is unknown or deliberately hidden by suppression."""


@dataclass(frozen=True, slots=True)
class ClubResolution:
    api_id: int | None
    name: str | None
    resolution: str
    program_id: int | None = None


@dataclass(frozen=True, slots=True)
class ManualTransferInput:
    player_api_id: int
    from_team_api_id: int | None
    to_team_api_id: int | None
    to_team_name: str | None
    transfer_type: str
    effective_date: date
    fee_text: str | None
    source_note: str
    dry_run: bool


def _positive_integer(value: Any, field: str, *, required: bool = False) -> int | None:
    if value is None or value == "":
        if required:
            raise ManualTransferValidationError(f"{field} is required")
        return None
    if isinstance(value, bool):
        raise ManualTransferValidationError(f"{field} must be a positive integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ManualTransferValidationError(f"{field} must be a positive integer") from exc
    if parsed <= 0 or isinstance(value, float) and not value.is_integer():
        raise ManualTransferValidationError(f"{field} must be a positive integer")
    if isinstance(value, str) and str(parsed) != value.strip():
        raise ManualTransferValidationError(f"{field} must be a positive integer")
    return parsed


def _clean_text(value: Any, field: str, *, required: bool = False, max_length: int) -> str | None:
    if value is None:
        if required:
            raise ManualTransferValidationError(f"{field} is required")
        return None
    if not isinstance(value, str):
        raise ManualTransferValidationError(f"{field} must be a string")
    cleaned = sanitize_plain_text(value).strip()
    if not cleaned:
        if required:
            raise ManualTransferValidationError(f"{field} is required")
        return None
    if len(cleaned) > max_length:
        raise ManualTransferValidationError(f"{field} must be at most {max_length} characters")
    return cleaned


def _parse_request(payload: Any) -> ManualTransferInput:
    if not isinstance(payload, dict):
        raise ManualTransferValidationError("JSON body must be an object")

    player_api_id = _positive_integer(payload.get("player_api_id"), "player_api_id", required=True)
    from_team_api_id = _positive_integer(payload.get("from_team_api_id"), "from_team_api_id")
    to_team_api_id = _positive_integer(payload.get("to_team_api_id"), "to_team_api_id")
    to_team_name = _clean_text(payload.get("to_team_name"), "to_team_name", max_length=200)
    source_note = _clean_text(payload.get("source_note"), "source_note", required=True, max_length=2000)
    fee_text = _clean_text(payload.get("fee_text"), "fee_text", max_length=100)

    raw_type = payload.get("transfer_type")
    if not isinstance(raw_type, str) or raw_type.strip().lower() not in ALLOWED_TRANSFER_TYPES:
        choices = ", ".join(sorted(ALLOWED_TRANSFER_TYPES))
        raise ManualTransferValidationError(f"transfer_type must be one of: {choices}")
    transfer_type = raw_type.strip().lower()
    if (
        transfer_type in {"signed", "sold"}
        and fee_text is not None
        and " ".join(fee_text.casefold().split()) in _RESOLVER_MOVEMENT_LABELS
    ):
        raise ManualTransferValidationError("fee_text cannot be a loan/return movement label for a permanent transfer")

    raw_date = payload.get("effective_date")
    if not isinstance(raw_date, str):
        raise ManualTransferValidationError("effective_date must be an ISO date (YYYY-MM-DD)")
    try:
        effective_date = date.fromisoformat(raw_date.strip())
    except ValueError as exc:
        raise ManualTransferValidationError("effective_date must be an ISO date (YYYY-MM-DD)") from exc

    dry_run = payload.get("dry_run", False)
    if not isinstance(dry_run, bool):
        raise ManualTransferValidationError("dry_run must be a boolean")

    if transfer_type == "released":
        if to_team_api_id is not None or to_team_name is not None:
            raise ManualTransferValidationError("released transfers must not include a destination")
    elif to_team_api_id is None and to_team_name is None:
        raise ManualTransferValidationError("to_team_api_id or to_team_name is required for this transfer type")

    return ManualTransferInput(
        player_api_id=player_api_id,
        from_team_api_id=from_team_api_id,
        to_team_api_id=to_team_api_id,
        to_team_name=to_team_name,
        transfer_type=transfer_type,
        effective_date=effective_date,
        fee_text=fee_text,
        source_note=source_note,
        dry_run=dry_run,
    )


def _latest_team_for_api_id(team_api_id: int) -> Team | None:
    return (
        Team.query.filter_by(team_id=team_api_id)
        .order_by(Team.is_active.desc(), Team.season.desc(), Team.id.desc())
        .first()
    )


def _linked_program(team_api_id: int) -> ClubProgram | None:
    return ClubProgram.query.filter_by(team_api_id=team_api_id).order_by(ClubProgram.id).first()


def _linked_program_id(team_api_id: int) -> int | None:
    program = _linked_program(team_api_id)
    return program.id if program is not None else None


def _resolve_destination_by_id(team_api_id: int) -> ClubResolution:
    program = _linked_program(team_api_id)
    team = _latest_team_for_api_id(team_api_id)
    if team is not None:
        return ClubResolution(
            team_api_id,
            team.name,
            "teams.api_id",
            program_id=program.id if program is not None else None,
        )

    profile = db.session.get(TeamProfile, team_api_id)
    if profile is not None:
        return ClubResolution(
            team_api_id,
            profile.name,
            "team_profiles.api_id",
            program_id=program.id if program is not None else None,
        )

    if program is not None:
        return ClubResolution(
            team_api_id,
            program.name,
            "club_programs.api_id",
            program_id=program.id,
        )

    raise ManualTransferValidationError(
        f"to_team_api_id {team_api_id} is not present in teams, team_profiles, or club_programs"
    )


def _one_name_identity(
    rows: list,
    *,
    identity,
    to_resolution,
    rung: str,
) -> ClubResolution | None:
    if not rows:
        return None
    by_identity = {}
    for row in rows:
        by_identity.setdefault(identity(row), row)
    if len(by_identity) != 1:
        raise ManualTransferValidationError(f"to_team_name is ambiguous in {rung}; provide to_team_api_id")
    return to_resolution(next(iter(by_identity.values())))


def _resolve_destination_by_name(team_name: str) -> ClubResolution:
    normalized = team_name.casefold()
    teams = (
        Team.query.filter(func.lower(func.trim(Team.name)) == normalized)
        .order_by(Team.is_active.desc(), Team.season.desc(), Team.id.desc())
        .all()
    )
    resolved = _one_name_identity(
        teams,
        identity=lambda row: row.team_id,
        to_resolution=lambda row: ClubResolution(
            row.team_id,
            row.name,
            "teams.name",
            program_id=_linked_program_id(row.team_id),
        ),
        rung="teams",
    )
    if resolved is not None:
        return resolved

    profiles = (
        TeamProfile.query.filter(func.lower(func.trim(TeamProfile.name)) == normalized)
        .order_by(TeamProfile.team_id)
        .all()
    )
    resolved = _one_name_identity(
        profiles,
        identity=lambda row: row.team_id,
        to_resolution=lambda row: ClubResolution(
            row.team_id,
            row.name,
            "team_profiles.name",
            program_id=_linked_program_id(row.team_id),
        ),
        rung="team_profiles",
    )
    if resolved is not None:
        return resolved

    programs = (
        ClubProgram.query.filter(func.lower(func.trim(ClubProgram.name)) == normalized).order_by(ClubProgram.id).all()
    )
    resolved = _one_name_identity(
        programs,
        identity=lambda row: ("team", row.team_api_id) if row.team_api_id is not None else ("program", row.id),
        to_resolution=lambda row: ClubResolution(
            row.team_api_id,
            row.name,
            "club_programs.name",
            program_id=row.id,
        ),
        rung="club_programs",
    )
    if resolved is not None:
        return resolved

    raise ManualTransferValidationError(
        f'to_team_name "{team_name}" was not found in teams, team_profiles, or club_programs'
    )


def _resolve_destination(values: ManualTransferInput) -> ClubResolution | None:
    if values.transfer_type == "released":
        return None
    if values.to_team_api_id is not None:
        return _resolve_destination_by_id(values.to_team_api_id)
    return _resolve_destination_by_name(values.to_team_name or "")


def _known_club_name(team_api_id: int) -> str | None:
    team = _latest_team_for_api_id(team_api_id)
    if team is not None:
        return team.name
    profile = db.session.get(TeamProfile, team_api_id)
    if profile is not None:
        return profile.name
    program = ClubProgram.query.filter_by(team_api_id=team_api_id).order_by(ClubProgram.id).first()
    return program.name if program is not None else None


def _club_from_ref(ref, resolution: str) -> ClubResolution | None:
    if ref is None:
        return None
    return ClubResolution(
        ref.organization_api_id or ref.api_id,
        ref.name,
        resolution,
    )


def _resolve_source(
    values: ManualTransferInput,
    journey: PlayerJourney,
    entries: list[PlayerJourneyEntry],
    service: JourneySyncService,
) -> ClubResolution:
    if values.from_team_api_id is not None:
        return ClubResolution(
            values.from_team_api_id,
            _known_club_name(values.from_team_api_id),
            "request.from_team_api_id",
        )

    prior_as_of = (
        values.effective_date - timedelta(days=1) if values.effective_date > date.min else values.effective_date
    )
    resolution = service._resolve_durable_transfer_state(journey, entries, as_of=prior_as_of)
    if values.transfer_type == "loan_return" and resolution is not None:
        source = _club_from_ref(
            resolution.active_loan.loan_club if resolution.active_loan is not None else None,
            "durable_transfer.active_loan",
        )
        if source is not None:
            return source

    if resolution is not None:
        source = _club_from_ref(resolution.legal_owner, "durable_transfer.legal_owner")
        if source is not None:
            return source

    if journey.current_owner_api_id is not None:
        return ClubResolution(
            journey.current_owner_api_id,
            journey.current_owner_name or _known_club_name(journey.current_owner_api_id),
            "journey.current_owner",
        )
    if journey.current_club_api_id is not None or journey.current_club_name:
        return ClubResolution(
            journey.current_club_api_id,
            journey.current_club_name,
            "journey.current_club",
        )

    tracked_rows = (
        TrackedPlayer.query.filter_by(player_api_id=values.player_api_id, is_active=True)
        .order_by(TrackedPlayer.id)
        .all()
    )
    parents: dict[int, Team] = {}
    for row in tracked_rows:
        if row.team is not None:
            parents.setdefault(row.team.team_id, row.team)
    if len(parents) == 1:
        parent = next(iter(parents.values()))
        return ClubResolution(parent.team_id, parent.name, "tracked_players.parent")
    if len(parents) > 1:
        raise ManualTransferValidationError(
            "from_team_api_id is required because the player has multiple active academy parents"
        )
    raise ManualTransferValidationError(
        "from_team_api_id is required because no source club can be inferred from stored journey evidence"
    )


def _provider_type(values: ManualTransferInput) -> str:
    if values.transfer_type in _PROVIDER_TYPES:
        return _PROVIDER_TYPES[values.transfer_type]
    return values.fee_text or "Undisclosed"


def _destination_key(destination: ClubResolution | None) -> str:
    if destination is None:
        return "none"
    if destination.program_id is not None:
        return f"program:{destination.program_id}"
    if destination.api_id is not None:
        return f"id:{destination.api_id}"
    return f"name:{(destination.name or '').strip().casefold()}"


def _candidate_event(
    values: ManualTransferInput,
    source: ClubResolution,
    destination: ClubResolution | None,
) -> dict:
    return {
        "date": values.effective_date.isoformat(),
        "type": _provider_type(values),
        "teams": {
            "out": {"id": source.api_id, "name": source.name},
            "in": {
                "id": destination.api_id if destination is not None else None,
                "name": destination.name if destination is not None else None,
            },
        },
        "source": "manual",
        "source_note": values.source_note,
        "manual_transfer_type": values.transfer_type,
        "fee_text": values.fee_text,
        "destination_program_id": destination.program_id if destination is not None else None,
        "destination_resolution": destination.resolution if destination is not None else "released.no_destination",
    }


def _same_destination(row: PlayerTransferEvent, destination: ClubResolution | None) -> bool:
    if destination is None:
        return row.in_club_api_id is None and not row.in_club_name
    raw = row.raw if isinstance(row.raw, dict) else {}
    recorded_program_id = raw.get("destination_program_id")
    if destination.program_id is not None and recorded_program_id == destination.program_id:
        return True
    if recorded_program_id is not None and recorded_program_id != destination.program_id:
        return False
    if destination.api_id is not None:
        return row.in_club_api_id == destination.api_id
    return (
        row.in_club_api_id is None
        and (row.in_club_name or "").strip().casefold() == (destination.name or "").strip().casefold()
    )


def _semantic_existing_event(
    values: ManualTransferInput,
    destination: ClubResolution | None,
) -> PlayerTransferEvent | None:
    rows = (
        PlayerTransferEvent.query.filter_by(
            player_api_id=values.player_api_id,
            transfer_date=values.effective_date,
        )
        .order_by(PlayerTransferEvent.id)
        .all()
    )
    for row in rows:
        raw = row.raw if isinstance(row.raw, dict) else {}
        if (
            raw.get("source") == "manual"
            and raw.get("manual_transfer_type") == values.transfer_type
            and _same_destination(row, destination)
        ):
            return row

    key = _destination_key(destination)
    audits = (
        TransferAdminEvent.query.filter_by(player_api_id=values.player_api_id)
        .order_by(TransferAdminEvent.id.desc())
        .all()
    )
    for audit in audits:
        metadata = audit.event_metadata if isinstance(audit.event_metadata, dict) else {}
        if (
            metadata.get("effective_date") == values.effective_date.isoformat()
            and metadata.get("transfer_type") == values.transfer_type
            and metadata.get("destination_key") == key
        ):
            event = db.session.get(PlayerTransferEvent, audit.transfer_event_id)
            if event is not None:
                return event
    return None


def _natural_existing_event(values: ManualTransferInput, candidate: dict) -> PlayerTransferEvent | None:
    teams = candidate["teams"]
    source = teams["out"]
    destination = teams["in"]
    rows = (
        PlayerTransferEvent.query.filter_by(
            player_api_id=values.player_api_id,
            transfer_date=values.effective_date,
            transfer_type=candidate["type"],
        )
        .order_by(PlayerTransferEvent.id)
        .all()
    )
    for row in rows:
        if row.out_club_api_id != source["id"] or row.in_club_api_id != destination["id"]:
            continue

        logical_types = set()
        raw = row.raw if isinstance(row.raw, dict) else {}
        if raw.get("source") == "manual" and raw.get("manual_transfer_type"):
            logical_types.add(raw["manual_transfer_type"])
        for audit in TransferAdminEvent.query.filter_by(transfer_event_id=row.id).all():
            metadata = audit.event_metadata if isinstance(audit.event_metadata, dict) else {}
            if metadata.get("transfer_type"):
                logical_types.add(metadata["transfer_type"])

        if logical_types and values.transfer_type not in logical_types:
            raise ManualTransferValidationError(
                "An existing transfer has the same storage key but a different manual transfer_type"
            )
        if not _same_destination(
            row,
            ClubResolution(
                destination["id"],
                destination["name"],
                "candidate",
                program_id=candidate.get("destination_program_id"),
            )
            if destination["id"] is not None or destination["name"]
            else None,
        ):
            raise ManualTransferValidationError(
                "An existing transfer has the same storage key but a different destination"
            )
        return row
    return None


def _persisted_candidate(values: ManualTransferInput, candidate: dict) -> PlayerTransferEvent:
    record_transfer_events(values.player_api_id, [candidate], db.session)
    event = _natural_existing_event(values, candidate)
    if event is None:
        raise RuntimeError("manual transfer event was not persisted")
    return event


def _tracked_snapshot(player_api_id: int) -> dict[int, dict]:
    rows = TrackedPlayer.query.filter_by(player_api_id=player_api_id).order_by(TrackedPlayer.id).all()
    return {
        row.id: {
            "tracked_player_id": row.id,
            "player_name": row.player_name,
            "parent_team_name": row.team.name if row.team is not None else None,
            "status": row.status,
            "is_active": bool(row.is_active),
            "current_club_api_id": row.current_club_api_id,
            "current_club_name": row.current_club_name,
            "sale_fee": row.sale_fee,
        }
        for row in rows
    }


def _affected_rows(
    before: dict[int, dict],
    after: dict[int, dict],
    *,
    old_journey_status: str | None,
    new_journey_status: str | None,
) -> list[dict]:
    affected = []
    for tracked_id in sorted(before.keys() | after.keys()):
        old = before.get(tracked_id)
        new = after.get(tracked_id)
        if old is None and new is None:
            continue
        affected.append(
            {
                "tracked_player_id": tracked_id,
                "player_name": (new or old)["player_name"],
                "parent_team_name": (new or old)["parent_team_name"],
                "old_status": old["status"] if old is not None else None,
                "would_be_status": new["status"] if new is not None else None,
                "old_is_active": old["is_active"] if old is not None else False,
                "would_be_is_active": new["is_active"] if new is not None else False,
                "old_current_club": {
                    "api_id": old["current_club_api_id"],
                    "name": old["current_club_name"],
                }
                if old is not None
                else None,
                "would_be_current_club": {
                    "api_id": new["current_club_api_id"],
                    "name": new["current_club_name"],
                }
                if new is not None
                else None,
                "old_sale_fee": old["sale_fee"] if old is not None else None,
                "would_be_sale_fee": new["sale_fee"] if new is not None else None,
                "journey_current_status": {
                    "old": old_journey_status,
                    "new": new_journey_status,
                },
            }
        )
    return affected


def _transfer_response(
    values: ManualTransferInput,
    source: ClubResolution,
    destination: ClubResolution | None,
    *,
    fee_text: str | None,
) -> dict:
    return {
        "player_api_id": values.player_api_id,
        "effective_date": values.effective_date.isoformat(),
        "transfer_type": values.transfer_type,
        "source": "manual",
        "fee_text": fee_text,
        "from_team": {
            "api_id": source.api_id,
            "name": source.name,
            "resolution": source.resolution,
        },
        "to_team": {
            "api_id": destination.api_id,
            "name": destination.name,
        }
        if destination is not None
        else None,
        "destination_resolution": (destination.resolution if destination is not None else "released.no_destination"),
    }


def apply_manual_transfer(payload: Any, *, actor_email: str | None) -> tuple[dict, bool]:
    """Preview or apply one event; the caller owns commit/rollback."""

    values = _parse_request(payload)
    if is_player_suppressed(values.player_api_id):
        raise ManualTransferPlayerNotFound

    journey = PlayerJourney.query.filter_by(player_api_id=values.player_api_id).with_for_update().first()
    if journey is None:
        if TrackedPlayer.query.filter_by(player_api_id=values.player_api_id).first() is None:
            raise ManualTransferPlayerNotFound
        raise ManualTransferValidationError(
            "Player has no stored journey; sync journey history before recording a manual transfer"
        )

    entries = PlayerJourneyEntry.query.filter_by(journey_id=journey.id).all()
    if not entries:
        raise ManualTransferValidationError(
            "Player has no stored journey entries; sync journey history before recording a manual transfer"
        )

    service = JourneySyncService(database_only=True)
    destination = _resolve_destination(values)
    source = _resolve_source(values, journey, entries, service)
    candidate = _candidate_event(values, source, destination)

    existing = _semantic_existing_event(values, destination)
    if existing is None:
        existing = _natural_existing_event(values, candidate)
    idempotent = existing is not None
    recorded_source = source
    recorded_fee_text = values.fee_text
    if existing is not None:
        recorded_source = ClubResolution(
            existing.out_club_api_id,
            existing.out_club_name,
            "existing_transfer_event",
        )
        raw = existing.raw if isinstance(existing.raw, dict) else {}
        if values.transfer_type in {"signed", "sold"}:
            recorded_fee_text = raw.get("fee_text", existing.transfer_type)

    before = _tracked_snapshot(values.player_api_id)
    old_journey_status = journey.current_status

    if values.dry_run:
        durable_rows = (
            PlayerTransferEvent.query.filter_by(player_api_id=values.player_api_id)
            .order_by(PlayerTransferEvent.transfer_date, PlayerTransferEvent.id)
            .all()
        )
        transfers = durable_rows if idempotent else [*durable_rows, candidate]
        result = service.reclassify_from_transfer_events(journey, transfers)
    else:
        event = existing or _persisted_candidate(values, candidate)
        result = service.reclassify_from_durable_transfer_events(journey)

    if result is None:
        raise RuntimeError("manual transfer did not produce non-empty transfer evidence")
    if not values.dry_run:
        for season in sorted(result["entry_seasons"]):
            refresh_season_rollup(values.player_api_id, season=season, session=db.session)
    db.session.flush()

    after = _tracked_snapshot(values.player_api_id)
    response = {
        "dry_run": values.dry_run,
        "idempotent": idempotent,
        "transfer": _transfer_response(
            values,
            recorded_source,
            destination,
            fee_text=recorded_fee_text,
        ),
        "affected_rows": _affected_rows(
            before,
            after,
            old_journey_status=old_journey_status,
            new_journey_status=journey.current_status,
        ),
    }

    if not values.dry_run:
        audit = TransferAdminEvent(
            transfer_event_id=event.id,
            player_api_id=values.player_api_id,
            actor_email=(actor_email or "system")[:254],
            action="manual.reused" if idempotent else "manual.created",
            source_note=values.source_note,
            event_metadata={
                "effective_date": values.effective_date.isoformat(),
                "transfer_type": values.transfer_type,
                "destination_key": _destination_key(destination),
                "destination_resolution": response["transfer"]["destination_resolution"],
                "from_team_api_id": recorded_source.api_id,
                "submitted_from_team_api_id": source.api_id,
                "submitted_fee_text": values.fee_text,
                "to_team_api_id": destination.api_id if destination is not None else None,
                "to_team_name": destination.name if destination is not None else None,
                "destination_program_id": destination.program_id if destination is not None else None,
            },
        )
        db.session.add(audit)
        db.session.flush()
        response["record_ids"] = {
            "transfer_event_id": event.id,
            "audit_event_id": audit.id,
        }

    return response, values.dry_run


__all__ = [
    "ManualTransferPlayerNotFound",
    "ManualTransferValidationError",
    "apply_manual_transfer",
]
