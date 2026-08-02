"""Scheduled job: quota-budgeted transfer-window ingestion.

The no-argument ACA cron path is deliberately cheap and resumable:

* in a transfer window, scan each tracked team once for transfer deltas and
  force-full sync only players with new durable transfer evidence;
* on Monday/Wednesday/Friday, spend any remaining budget on that weekday's
  weekly safety-net tranche;
* outside a transfer window, keep the pre-existing light status refresh.

Delta flags and sweep cursors live in ``AdminSetting`` JSON. Each team scan
commits new transfer evidence, exact-key flags, and its scan cursor together,
so an interrupted run either resumes that team or resumes its queued players.

Usage:
    python -m src.jobs.run_transfer_window_heal [--mode delta|sweep] [--dry-run]
"""

import argparse
import json
import logging
import os
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from threading import Lock
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session
from src.api_football_client import (
    APICallBudget,
    APICallBudgetExceeded,
    APIFootballClient,
)
from src.main import app
from src.models.league import AdminSetting, Team, db
from src.models.tracked_player import TrackedPlayer
from src.models.transfer_event import PlayerTransferEvent
from src.utils.affiliates import senior_base_name
from src.utils.background_jobs import has_running_job
from src.utils.job_utils import is_job_paused, teams_with_active_tracked_players
from src.utils.supported_leagues import DEFAULT_CRAWL_LEAGUE_IDS, get_supported_leagues

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

DEFAULT_DAILY_BUDGET = 400
DELTA_QUEUE_SETTING = "transfer_cadence_delta_queue_v1"
SWEEP_STATE_SETTING = "transfer_cadence_sweep_state_v1"
DAILY_BUDGET_SETTING = "transfer_cadence_daily_budget_v1"
TRANCHE_BY_WEEKDAY = {0: "mon", 2: "wed", 4: "fri"}
TRANCHES = ("mon", "wed", "fri")
TERMINAL_STATUSES = ("released", "sold", "left")
_POSTGRES_ADVISORY_LOCK_KEY = 0x5452414E53464552
_LOCAL_RUN_LOCK = Lock()


@dataclass(frozen=True)
class TransferWindowContext:
    """Calendar state for the configured winter/summer transfer windows."""

    in_window: bool
    deadline_week: bool
    close_date: date | None


@dataclass(frozen=True)
class TeamScanTarget:
    """One API team scan, possibly shared by multiple seasonal Team rows."""

    api_team_id: int
    db_team_ids: tuple[int, ...]
    player_api_ids: frozenset[int]


@dataclass
class RunSummary:
    """End-of-run operator counters."""

    modes: list[str] = field(default_factory=list)
    teams_scanned: int = 0
    new_transfers_found: int = 0
    new_transfer_keys: set[tuple[Any, ...]] = field(default_factory=set, repr=False)
    flagged_player_ids: set[int] = field(default_factory=set)
    resynced_player_ids: set[int] = field(default_factory=set)
    errors: list[str] = field(default_factory=list)

    def note_new_transfer_keys(self, keys: set[tuple[Any, ...]]) -> None:
        self.new_transfer_keys.update(keys)
        self.new_transfers_found = len(self.new_transfer_keys)

    def as_dict(
        self,
        *,
        budget: APICallBudget,
        budget_spent_at_start: int,
        remainder_queued: int,
    ) -> dict[str, Any]:
        return {
            "modes": self.modes,
            "teams_scanned": self.teams_scanned,
            "new_transfers_found": self.new_transfers_found,
            "players_flagged": len(self.flagged_player_ids),
            "players_resynced": len(self.resynced_player_ids),
            "api_calls_spent": budget.spent,
            "api_calls_spent_this_run": budget.spent - budget_spent_at_start,
            "api_call_budget": budget.limit,
            "remainder_queued": remainder_queued,
            "errors": self.errors,
        }


def _utcnow() -> datetime:
    return datetime.now(UTC)


def transfer_window_context(today: date | None = None) -> TransferWindowContext:
    """Return window/deadline state.

    Provider lag buffers remain February 1-7 and September 1-7. "Deadline
    week" means the final seven days before the actual January 31/August 31
    close, not the post-close provider buffer.
    """

    today = today or _utcnow().date()
    winter_close = date(today.year, 1, 31)
    summer_close = date(today.year, 8, 31)

    if date(today.year, 1, 1) <= today <= date(today.year, 2, 7):
        return TransferWindowContext(
            in_window=True,
            deadline_week=date(today.year, 1, 25) <= today <= winter_close,
            close_date=winter_close,
        )
    if date(today.year, 6, 1) <= today <= date(today.year, 9, 7):
        return TransferWindowContext(
            in_window=True,
            deadline_week=date(today.year, 8, 25) <= today <= summer_close,
            close_date=summer_close,
        )
    return TransferWindowContext(in_window=False, deadline_week=False, close_date=None)


def is_transfer_window(today: date | None = None) -> bool:
    """Backward-compatible transfer-window predicate."""

    return transfer_window_context(today).in_window


def _daily_budget() -> int:
    raw = os.getenv("TRANSFER_SYNC_DAILY_BUDGET", str(DEFAULT_DAILY_BUDGET)).strip()
    try:
        value = int(raw)
    except (TypeError, ValueError):
        logger.warning(
            "Invalid TRANSFER_SYNC_DAILY_BUDGET=%r; using %d",
            raw,
            DEFAULT_DAILY_BUDGET,
        )
        return DEFAULT_DAILY_BUDGET
    if value < 0:
        logger.warning("Negative TRANSFER_SYNC_DAILY_BUDGET=%r; using 0", raw)
        return 0
    return value


def _write_daily_budget_claim(engine, day: date, next_spent: int) -> None:
    """Durably reserve one daily call without committing the caller's work."""

    session = Session(bind=engine)
    try:
        row = session.query(AdminSetting).filter_by(key=DAILY_BUDGET_SETTING).one()
        try:
            state = json.loads(row.value_json or "{}")
        except (json.JSONDecodeError, TypeError) as exc:
            raise RuntimeError(f"Malformed {DAILY_BUDGET_SETTING} state") from exc
        if state.get("date") != day.isoformat():
            raise RuntimeError(f"{DAILY_BUDGET_SETTING} date changed while the cadence job was running")
        persisted_spent = _int_or_none(state.get("spent"))
        if persisted_spent is None or next_spent != persisted_spent + 1:
            raise RuntimeError(
                f"{DAILY_BUDGET_SETTING} claim sequence mismatch: persisted={persisted_spent!r}, next={next_spent}"
            )
        row.value_json = json.dumps(
            {"date": day.isoformat(), "spent": next_spent},
            sort_keys=True,
            separators=(",", ":"),
        )
        row.updated_at = _utcnow()
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _durable_daily_budget(day: date) -> APICallBudget:
    """Return the shared daily budget, resuming spend from an earlier run."""

    limit = _daily_budget()
    state = _load_setting(DAILY_BUDGET_SETTING, strict=True)
    if state is None or state.get("date") != day.isoformat():
        state = {"date": day.isoformat(), "spent": 0}
        _save_setting(DAILY_BUDGET_SETTING, state)
    spent = _int_or_none(state.get("spent"))
    if spent is None or spent < 0:
        raise RuntimeError(f"Malformed {DAILY_BUDGET_SETTING} spent value")
    engine = db.engine
    return APICallBudget(
        limit,
        initial_spent=spent,
        on_claim=lambda next_spent: _write_daily_budget_claim(engine, day, next_spent),
    )


@contextmanager
def _cadence_run_lock():
    """Hold one cross-process lock for every queue read/modify/write cycle."""

    if db.engine.dialect.name != "postgresql":
        acquired = _LOCAL_RUN_LOCK.acquire(blocking=False)
        try:
            yield acquired
        finally:
            if acquired:
                _LOCAL_RUN_LOCK.release()
        return

    connection = db.engine.connect()
    acquired = False
    try:
        acquired = bool(
            connection.execute(
                text("SELECT pg_try_advisory_lock(:lock_key)"),
                {"lock_key": _POSTGRES_ADVISORY_LOCK_KEY},
            ).scalar()
        )
        yield acquired
    finally:
        if acquired:
            try:
                connection.execute(
                    text("SELECT pg_advisory_unlock(:lock_key)"),
                    {"lock_key": _POSTGRES_ADVISORY_LOCK_KEY},
                )
            except Exception:
                logger.exception("Failed to release transfer cadence advisory lock")
        connection.close()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _parse_utc(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return _as_utc(parsed)


def _iso_utc(value: datetime) -> str:
    return _as_utc(value).isoformat()


def _load_setting(key: str, *, strict: bool = False) -> dict[str, Any] | None:
    row = AdminSetting.query.filter_by(key=key).populate_existing().first()
    if not row or not row.value_json:
        return None
    try:
        value = json.loads(row.value_json)
    except (json.JSONDecodeError, TypeError) as exc:
        if strict:
            raise RuntimeError(f"Malformed JSON in AdminSetting {key}") from exc
        logger.warning("Ignoring malformed JSON in AdminSetting %s", key)
        return None
    if not isinstance(value, dict):
        if strict:
            raise RuntimeError(f"Non-object JSON in AdminSetting {key}")
        logger.warning("Ignoring non-object JSON in AdminSetting %s", key)
        return None
    return value


def _save_setting(key: str, value: dict[str, Any]) -> None:
    row = AdminSetting.query.filter_by(key=key).first()
    if row is None:
        row = AdminSetting(key=key)
        db.session.add(row)
    row.value_json = json.dumps(value, sort_keys=True, separators=(",", ":"))
    row.updated_at = _utcnow()
    db.session.commit()


def _int_or_none(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _event_value(event: Any, mapping_name: str, attribute_name: str | None = None) -> Any:
    if isinstance(event, dict):
        return event.get(mapping_name)
    return getattr(event, attribute_name or mapping_name, None)


def _event_date(event: Any) -> date | None:
    raw = _event_value(event, "date", "transfer_date")
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    if not isinstance(raw, str):
        return None
    try:
        return date.fromisoformat(raw.strip())
    except ValueError:
        return None


def transfer_event_identity(player_api_id: Any, event: Any) -> tuple[Any, ...] | None:
    """Return the exact durable ``PlayerTransferEvent`` natural key."""

    normalized_player_id = _int_or_none(player_api_id)
    transfer_date = _event_date(event)
    if normalized_player_id is None or transfer_date is None:
        return None

    if isinstance(event, dict):
        teams = event.get("teams")
        teams = teams if isinstance(teams, dict) else {}
        outgoing = teams.get("out")
        outgoing = outgoing if isinstance(outgoing, dict) else {}
        incoming = teams.get("in")
        incoming = incoming if isinstance(incoming, dict) else {}
        out_club_api_id = _int_or_none(outgoing.get("id"))
        in_club_api_id = _int_or_none(incoming.get("id"))
        raw_type = event.get("type")
    else:
        out_club_api_id = _int_or_none(getattr(event, "out_club_api_id", None))
        in_club_api_id = _int_or_none(getattr(event, "in_club_api_id", None))
        raw_type = getattr(event, "transfer_type", None)

    transfer_type = raw_type if isinstance(raw_type, str) else None
    return (
        normalized_player_id,
        transfer_date,
        out_club_api_id,
        in_club_api_id,
        transfer_type,
    )


def _identity_payload(identity: tuple[Any, ...]) -> list[Any]:
    return [
        identity[0],
        identity[1].isoformat(),
        identity[2],
        identity[3],
        identity[4],
    ]


def _payload_identity(payload: Any) -> tuple[Any, ...] | None:
    if not isinstance(payload, list) or len(payload) != 5:
        return None
    player_api_id = _int_or_none(payload[0])
    try:
        transfer_date = date.fromisoformat(payload[1])
    except (TypeError, ValueError):
        return None
    if player_api_id is None:
        return None
    raw_type = payload[4]
    return (
        player_api_id,
        transfer_date,
        _int_or_none(payload[2]),
        _int_or_none(payload[3]),
        raw_type if isinstance(raw_type, str) else None,
    )


def _tracked_scan_targets() -> list[TeamScanTarget]:
    """Resolve helper-returned Team DB ids into de-duplicated API team scans."""

    team_db_ids = sorted(set(teams_with_active_tracked_players()))
    if not team_db_ids:
        return []

    teams = Team.query.filter(Team.id.in_(team_db_ids)).all()
    team_by_db_id = {team.id: team for team in teams}
    player_rows = (
        db.session.query(TrackedPlayer.team_id, TrackedPlayer.player_api_id)
        .filter(
            TrackedPlayer.team_id.in_(team_db_ids),
            TrackedPlayer.is_active.is_(True),
            TrackedPlayer.player_api_id.isnot(None),
            TrackedPlayer.status.notin_(TERMINAL_STATUSES),
        )
        .all()
    )

    players_by_team: dict[int, set[int]] = {}
    for team_db_id, player_api_id in player_rows:
        players_by_team.setdefault(team_db_id, set()).add(int(player_api_id))

    grouped: dict[int, dict[str, set[int]]] = {}
    for team_db_id in team_db_ids:
        team = team_by_db_id.get(team_db_id)
        api_team_id = _int_or_none(team.team_id if team else None)
        if api_team_id is None or api_team_id <= 0:
            logger.warning("Skipping tracked Team db_id=%s without a valid API team id", team_db_id)
            continue
        bucket = grouped.setdefault(api_team_id, {"db_team_ids": set(), "player_api_ids": set()})
        bucket["db_team_ids"].add(team_db_id)
        bucket["player_api_ids"].update(players_by_team.get(team_db_id, set()))

    return [
        TeamScanTarget(
            api_team_id=api_team_id,
            db_team_ids=tuple(sorted(values["db_team_ids"])),
            player_api_ids=frozenset(values["player_api_ids"]),
        )
        for api_team_id, values in sorted(grouped.items())
        if values["player_api_ids"]
    ]


def _stored_transfer_keys(player_api_ids: frozenset[int] | set[int]) -> set[tuple[Any, ...]]:
    if not player_api_ids:
        return set()
    rows = PlayerTransferEvent.query.filter(PlayerTransferEvent.player_api_id.in_(player_api_ids)).all()
    return {key for row in rows if (key := transfer_event_identity(row.player_api_id, row)) is not None}


def _default_delta_state() -> dict[str, Any]:
    return {
        "version": 1,
        "players": {},
        "scan_pending_api_team_ids": [],
        "scan_cycle_started_at": None,
    }


def _load_delta_state() -> dict[str, Any]:
    state = _load_setting(DELTA_QUEUE_SETTING, strict=True)
    if state is None:
        state = _default_delta_state()
        # Persist before the first provider call so the team-scan snapshot
        # below is always a durable resume point.
        _save_setting(DELTA_QUEUE_SETTING, state)
        return state
    if not isinstance(state.get("players"), dict):
        raise RuntimeError(f"Malformed players queue in {DELTA_QUEUE_SETTING}")

    state["version"] = 1
    return state


def _queue_delta_player(
    state: dict[str, Any],
    player_api_id: int,
    *,
    latest_transfer_date: date | None,
    flagged_at: datetime,
    reason: str,
    pending_identities: set[tuple[Any, ...]] | None = None,
) -> bool:
    players = state.setdefault("players", {})
    key = str(int(player_api_id))
    existing = players.get(key)
    created = not isinstance(existing, dict)
    if created:
        existing = {
            "player_api_id": int(player_api_id),
            "flagged_at": _iso_utc(flagged_at),
            "latest_transfer_date": None,
            "reasons": [],
            "pending_keys": [],
        }
        players[key] = existing

    current_latest = existing.get("latest_transfer_date")
    incoming_latest = latest_transfer_date.isoformat() if latest_transfer_date else None
    if incoming_latest and (not current_latest or incoming_latest > current_latest):
        existing["latest_transfer_date"] = incoming_latest
    reasons = set(existing.get("reasons") or [])
    reasons.add(reason)
    existing["reasons"] = sorted(reasons)
    pending_keys = {
        identity
        for payload in existing.get("pending_keys") or []
        if (identity := _payload_identity(payload)) is not None
    }
    pending_keys.update(pending_identities or set())
    existing["pending_keys"] = [
        _identity_payload(identity)
        for identity in sorted(
            pending_keys,
            key=lambda item: (
                item[1],
                item[0],
                item[2] if item[2] is not None else -1,
                item[3] if item[3] is not None else -1,
                item[4] or "",
            ),
        )
    ]
    return created


def _diff_team_response(
    target: TeamScanTarget,
    transfer_blocks: list[dict[str, Any]],
    known_keys: set[tuple[Any, ...]],
    state: dict[str, Any],
    *,
    observed_at: datetime,
    summary: RunSummary,
) -> dict[int, list[dict[str, Any]]]:
    """Diff a team response against the pre-fetch durable-key snapshot."""

    new_keys: set[tuple[Any, ...]] = set()
    new_events_by_player: dict[int, list[dict[str, Any]]] = {}
    new_identities_by_player: dict[int, set[tuple[Any, ...]]] = {}
    for block in transfer_blocks or []:
        if not isinstance(block, dict):
            continue
        player = block.get("player")
        player = player if isinstance(player, dict) else {}
        player_api_id = _int_or_none(player.get("id"))
        if player_api_id is None or player_api_id not in target.player_api_ids:
            continue

        latest_new_date = None
        for transfer in block.get("transfers") or []:
            identity = transfer_event_identity(player_api_id, transfer)
            if identity is None or identity in known_keys or identity in new_keys:
                continue
            new_keys.add(identity)
            new_events_by_player.setdefault(player_api_id, []).append(transfer)
            new_identities_by_player.setdefault(player_api_id, set()).add(identity)
            event_date = identity[1]
            if latest_new_date is None or event_date > latest_new_date:
                latest_new_date = event_date

        if latest_new_date is not None:
            _queue_delta_player(
                state,
                player_api_id,
                latest_transfer_date=latest_new_date,
                flagged_at=observed_at,
                reason="team-delta",
                pending_identities=new_identities_by_player[player_api_id],
            )
            summary.flagged_player_ids.add(player_api_id)

    known_keys.update(new_keys)
    summary.note_new_transfer_keys(new_keys)
    return new_events_by_player


def _active_tracked_player(player_api_id: int) -> bool:
    return (
        TrackedPlayer.query.filter(
            TrackedPlayer.player_api_id == player_api_id,
            TrackedPlayer.is_active.is_(True),
            TrackedPlayer.status.notin_(TERMINAL_STATUSES),
        ).first()
        is not None
    )


def _durable_transfers(player_api_id: int) -> list[PlayerTransferEvent]:
    return (
        PlayerTransferEvent.query.filter_by(player_api_id=player_api_id)
        .order_by(PlayerTransferEvent.transfer_date, PlayerTransferEvent.id)
        .all()
    )


def _delta_priority(entry: dict[str, Any], player_api_id: int, *, deadline_week: bool) -> tuple[Any, ...]:
    flagged_at = _parse_utc(entry.get("flagged_at")) or datetime.max.replace(tzinfo=UTC)
    if not deadline_week:
        return (flagged_at, player_api_id)
    try:
        latest_ordinal = date.fromisoformat(entry.get("latest_transfer_date") or "").toordinal()
    except (TypeError, ValueError):
        latest_ordinal = date.min.toordinal()
    return (-latest_ordinal, flagged_at, player_api_id)


def _ordered_delta_players(state: dict[str, Any], *, deadline_week: bool) -> list[int]:
    entries = []
    for raw_player_id, entry in (state.get("players") or {}).items():
        player_api_id = _int_or_none(raw_player_id)
        if player_api_id is None or not isinstance(entry, dict):
            continue
        entries.append((player_api_id, entry))
    entries.sort(key=lambda item: _delta_priority(item[1], item[0], deadline_week=deadline_week))
    return [player_api_id for player_api_id, _entry in entries]


def _process_delta_queue(
    state: dict[str, Any],
    *,
    client: APIFootballClient,
    budget: APICallBudget,
    deadline_week: bool,
    dry_run: bool,
    summary: RunSummary,
) -> None:
    if dry_run:
        logger.info("Delta dry-run: durable evidence/flags retained; targeted journey sync skipped")
        return

    from src.services.journey_sync import JourneySyncService

    service = JourneySyncService(api_client=client)
    for player_api_id in _ordered_delta_players(state, deadline_week=deadline_week):
        if is_job_paused("transfer_heal_paused") or budget.exhausted:
            break
        if not _active_tracked_player(player_api_id):
            state["players"].pop(str(player_api_id), None)
            _save_setting(DELTA_QUEUE_SETTING, state)
            continue

        transfers = _durable_transfers(player_api_id)
        if not transfers:
            logger.warning("Delta player %d has no durable transfer rows; leaving queued", player_api_id)
            continue
        entry = state["players"].get(str(player_api_id)) or {}
        raw_pending_keys = entry.get("pending_keys") or []
        pending_keys = {
            identity for payload in raw_pending_keys if (identity := _payload_identity(payload)) is not None
        }
        if len(pending_keys) != len(raw_pending_keys):
            logger.error(
                "Delta player %d has malformed pending transfer identities; leaving queued",
                player_api_id,
            )
            continue
        durable_keys = {
            identity
            for transfer in transfers
            if (identity := transfer_event_identity(player_api_id, transfer)) is not None
        }
        missing_keys = pending_keys - durable_keys
        if missing_keys:
            logger.error(
                "Delta player %d is missing %d expected durable transfer row(s); leaving queued",
                player_api_id,
                len(missing_keys),
            )
            continue

        try:
            journey = service.sync_player(
                player_api_id,
                force_full=True,
                prefetched_transfers=transfers,
            )
        except APICallBudgetExceeded:
            logger.info("API call budget exhausted while syncing delta player %d", player_api_id)
            break
        except Exception as exc:
            db.session.rollback()
            logger.exception("Delta journey sync failed for player %d", player_api_id)
            summary.errors.append(f"delta player {player_api_id}: {exc}")
            continue

        transfers_applied = bool(getattr(service, "last_sync_used_transfer_evidence", False))
        if journey is None or journey.sync_error or not transfers_applied:
            logger.warning(
                "Delta player %d did not complete a transfers-fed sync; leaving queued",
                player_api_id,
            )
            continue

        state["players"].pop(str(player_api_id), None)
        _save_setting(DELTA_QUEUE_SETTING, state)
        summary.resynced_player_ids.add(player_api_id)


def _run_delta(
    *,
    client: APIFootballClient,
    budget: APICallBudget,
    run_started_at: datetime,
    window: TransferWindowContext,
    dry_run: bool,
    summary: RunSummary,
) -> None:
    summary.modes.append("delta")
    state = _load_delta_state()
    summary.flagged_player_ids.update(
        player_api_id
        for raw_player_id in (state.get("players") or {})
        if (player_api_id := _int_or_none(raw_player_id)) is not None
    )
    _save_setting(DELTA_QUEUE_SETTING, state)

    targets = _tracked_scan_targets()
    targets_by_api_id = {target.api_team_id: target for target in targets}
    raw_pending_team_ids = state.get("scan_pending_api_team_ids") or []
    if not isinstance(raw_pending_team_ids, list):
        raise RuntimeError(f"Malformed scan cursor in {DELTA_QUEUE_SETTING}")
    pending_team_ids = list(
        dict.fromkeys(
            team_id
            for raw_team_id in raw_pending_team_ids
            if (team_id := _int_or_none(raw_team_id)) in targets_by_api_id
        )
    )
    if not pending_team_ids:
        pending_team_ids = sorted(targets_by_api_id)
        state["scan_cycle_started_at"] = _iso_utc(run_started_at)
    state["scan_pending_api_team_ids"] = pending_team_ids
    _save_setting(DELTA_QUEUE_SETTING, state)

    for api_team_id in list(pending_team_ids):
        if is_job_paused("transfer_heal_paused") or budget.exhausted:
            break
        target = targets_by_api_id[api_team_id]
        known_keys = _stored_transfer_keys(target.player_api_ids)
        try:
            transfer_blocks = client.get_team_transfers(
                target.api_team_id,
                force_refresh=True,
                raise_on_error=True,
                persist_events=False,
            )
        except APICallBudgetExceeded:
            logger.info("API call budget exhausted before team %d scan", target.api_team_id)
            break
        except Exception as exc:
            db.session.rollback()
            logger.error("Transfer delta scan failed for API team %d: %s", target.api_team_id, exc)
            summary.errors.append(f"team {target.api_team_id}: {exc}")
            continue

        observed_at = _utcnow()
        summary.teams_scanned += 1
        new_events_by_player = _diff_team_response(
            target,
            transfer_blocks,
            known_keys,
            state,
            observed_at=observed_at,
            summary=summary,
        )
        # The API client's write is intentionally best-effort for ordinary
        # callers. Cadence correctness is stricter: re-upsert each genuinely
        # new row in this transaction so evidence and its queue flag commit
        # together. A flag can only dequeue after every expected natural key
        # is verifiably durable.
        from src.services.transfer_events import record_transfer_events

        for player_api_id, transfers in new_events_by_player.items():
            record_transfer_events(
                player_api_id,
                transfers,
                db.session,
                observed_at=observed_at,
            )
        state["scan_pending_api_team_ids"].remove(target.api_team_id)
        # Persist after every team so ordinary interruptions resume with the
        # smallest possible replay. New evidence, exact-key flags, and this
        # cursor removal are one commit.
        _save_setting(DELTA_QUEUE_SETTING, state)

    _process_delta_queue(
        state,
        client=client,
        budget=budget,
        deadline_week=window.deadline_week,
        dry_run=dry_run,
        summary=summary,
    )


def team_sweep_tranche(team: Team) -> str:
    """Map a Team to the weekly safety-net tranche.

    Explicit youth/academy side names take Friday precedence. Senior teams in
    the original top-five crawl footprint are Monday; other env-configured
    leagues/regions are Wednesday. Residual/unmapped teams also go Friday so
    the safety net remains exhaustive as new academy/lower-league rows land.
    """

    name = (team.name or "").strip()
    if name and senior_base_name(name).casefold() != name.casefold():
        return "fri"
    league_api_id = team.league.league_id if team.league else None
    if league_api_id in DEFAULT_CRAWL_LEAGUE_IDS:
        return "mon"
    if league_api_id in get_supported_leagues():
        return "wed"
    return "fri"


def selected_sweep_tranches(today: date, override: str | None = None) -> list[str]:
    raw_override = override
    if raw_override is None:
        raw_override = os.getenv("SWEEP_TRANCHE_OVERRIDE", "")
    normalized = (raw_override or "").strip().lower()
    if normalized:
        if normalized == "all":
            return list(TRANCHES)
        if normalized in TRANCHES:
            return [normalized]
        raise ValueError("SWEEP_TRANCHE_OVERRIDE must be one of mon|wed|fri|all")
    tranche = TRANCHE_BY_WEEKDAY.get(today.weekday())
    return [tranche] if tranche else []


def planned_modes(
    *,
    requested_mode: str | None,
    today: date,
    sweep_override: str | None = None,
) -> list[str]:
    """Pure dispatch plan used by the no-args cron and date-frozen tests."""

    if requested_mode == "delta":
        return ["delta"]
    if requested_mode == "sweep":
        tranches = selected_sweep_tranches(today, sweep_override)
        if not tranches:
            raise ValueError("--mode sweep has no tranche today; set SWEEP_TRANCHE_OVERRIDE=mon|wed|fri|all")
        return [f"sweep:{tranche}" for tranche in tranches]

    if not transfer_window_context(today).in_window:
        return ["local"]
    return ["delta", *(f"sweep:{tranche}" for tranche in selected_sweep_tranches(today, sweep_override))]


def _week_key(today: date) -> str:
    iso_year, iso_week, _weekday = today.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def _load_sweep_state() -> dict[str, Any]:
    state = _load_setting(SWEEP_STATE_SETTING, strict=True)
    if state is None:
        return {"version": 1, "tranches": {}}
    if not isinstance(state.get("tranches"), dict):
        raise RuntimeError(f"Malformed tranches queue in {SWEEP_STATE_SETTING}")
    state["version"] = 1
    return state


def _sweep_candidates(tranche: str) -> list[int]:
    team_db_ids = sorted(set(teams_with_active_tracked_players()))
    if not team_db_ids:
        return []
    teams = Team.query.filter(Team.id.in_(team_db_ids)).all()
    teams_by_id = {team.id: team for team in teams}
    eligible_rows = (
        db.session.query(TrackedPlayer.player_api_id, TrackedPlayer.team_id)
        .filter(
            TrackedPlayer.team_id.in_(team_db_ids),
            TrackedPlayer.is_active.is_(True),
            TrackedPlayer.player_api_id.isnot(None),
            TrackedPlayer.status.notin_(TERMINAL_STATUSES),
        )
        .all()
    )
    if not eligible_rows:
        return []

    teams_by_api_id: dict[int, list[Team]] = {}
    for _player_api_id, team_db_id in eligible_rows:
        team = teams_by_id.get(team_db_id)
        api_team_id = _int_or_none(team.team_id if team else None)
        if team is not None and api_team_id is not None:
            bucket = teams_by_api_id.setdefault(api_team_id, [])
            if team not in bucket:
                bucket.append(team)

    canonical_team_tranche: dict[int, str] = {}
    for api_team_id, seasonal_rows in teams_by_api_id.items():
        row_tranches = {team_sweep_tranche(team) for team in seasonal_rows}
        if "fri" in row_tranches and any(
            senior_base_name((team.name or "").strip()).casefold() != (team.name or "").strip().casefold()
            for team in seasonal_rows
            if (team.name or "").strip()
        ):
            canonical_team_tranche[api_team_id] = "fri"
        elif "mon" in row_tranches:
            canonical_team_tranche[api_team_id] = "mon"
        elif "wed" in row_tranches:
            canonical_team_tranche[api_team_id] = "wed"
        else:
            canonical_team_tranche[api_team_id] = "fri"

    tranche_order = {name: index for index, name in enumerate(TRANCHES)}
    player_tranches: dict[int, set[str]] = {}
    for player_api_id, team_db_id in eligible_rows:
        team = teams_by_id.get(team_db_id)
        api_team_id = _int_or_none(team.team_id if team else None)
        selected = canonical_team_tranche.get(api_team_id)
        if selected:
            player_tranches.setdefault(int(player_api_id), set()).add(selected)

    return sorted(
        player_api_id
        for player_api_id, memberships in player_tranches.items()
        if min(memberships, key=tranche_order.__getitem__) == tranche
    )


def _ensure_sweep_queue(
    state: dict[str, Any],
    tranche: str,
    *,
    today: date,
    already_resynced: set[int],
) -> dict[str, Any]:
    week = _week_key(today)
    tranches = state.setdefault("tranches", {})
    queue = tranches.get(tranche)
    if not isinstance(queue, dict):
        queue = {}
        tranches[tranche] = queue

    raw_remaining = queue.get("remaining") or []
    remaining = [
        int(player_api_id)
        for player_api_id in raw_remaining
        if _int_or_none(player_api_id) is not None and int(player_api_id) not in already_resynced
    ]
    if remaining:
        queue["remaining"] = remaining
        return queue
    if isinstance(queue.get("started_week"), str) and queue.get("completed_week") is None and "remaining" in queue:
        # The final old item may have been handled by delta earlier in this
        # invocation, or a process may have died after saving its removal but
        # before writing completed_week. Let _run_sweep close that exact
        # started_week before it snapshots a newer one.
        queue["remaining"] = []
        return queue
    if queue.get("completed_week") == week:
        queue["remaining"] = []
        return queue

    queue.update(
        {
            "started_week": week,
            "completed_week": None,
            "remaining": [
                player_api_id for player_api_id in _sweep_candidates(tranche) if player_api_id not in already_resynced
            ],
        }
    )
    # Snapshot the whole tranche before the first expensive call.
    _save_setting(SWEEP_STATE_SETTING, state)
    return queue


def _run_sweep(
    tranches: list[str],
    *,
    client: APIFootballClient,
    budget: APICallBudget,
    today: date,
    dry_run: bool,
    summary: RunSummary,
) -> None:
    if not tranches:
        logger.info("Sweep mode selected, but today has no tranche and no override was set")
        return

    from src.services.journey_sync import JourneySyncService

    state = _load_sweep_state()
    service = JourneySyncService(api_client=client)
    for tranche in tranches:
        summary.modes.append(f"sweep:{tranche}")
        while True:
            queue = _ensure_sweep_queue(
                state,
                tranche,
                today=today,
                already_resynced=summary.resynced_player_ids,
            )
            if dry_run:
                logger.info(
                    "Sweep dry-run: tranche=%s queued=%d; journey sync skipped",
                    tranche,
                    len(queue.get("remaining") or []),
                )
                break

            for player_api_id in list(queue.get("remaining") or []):
                if is_job_paused("transfer_heal_paused") or budget.exhausted:
                    break
                if player_api_id in summary.resynced_player_ids or not _active_tracked_player(player_api_id):
                    queue["remaining"].remove(player_api_id)
                    _save_setting(SWEEP_STATE_SETTING, state)
                    continue
                try:
                    journey = service.sync_player(
                        player_api_id,
                        force_full=True,
                        force_transfer_refresh=True,
                    )
                except APICallBudgetExceeded:
                    logger.info(
                        "API call budget exhausted while syncing %s sweep player %d",
                        tranche,
                        player_api_id,
                    )
                    break
                except Exception as exc:
                    db.session.rollback()
                    logger.exception("%s sweep sync failed for player %d", tranche, player_api_id)
                    summary.errors.append(f"{tranche} sweep player {player_api_id}: {exc}")
                    continue

                transfers_applied = bool(getattr(service, "last_sync_used_transfer_evidence", False))
                if journey is None or journey.sync_error or not transfers_applied:
                    logger.warning(
                        "%s sweep player %d did not complete a transfers-fed sync; leaving queued",
                        tranche,
                        player_api_id,
                    )
                    continue

                queue["remaining"].remove(player_api_id)
                _save_setting(SWEEP_STATE_SETTING, state)
                summary.resynced_player_ids.add(player_api_id)

            if queue.get("remaining"):
                break
            started_week = queue.get("started_week")
            if not isinstance(started_week, str):
                raise RuntimeError(f"Malformed started_week in {SWEEP_STATE_SETTING} {tranche} queue")
            queue["completed_week"] = started_week
            _save_setting(SWEEP_STATE_SETTING, state)
            if started_week == _week_key(today):
                break
            # A prior week's backlog just drained. Snapshot and process the
            # current week now; never mark it complete using an old cursor.
        if budget.exhausted or is_job_paused("transfer_heal_paused"):
            break


def _run_local_refresh(
    *,
    client: APIFootballClient,
    budget: APICallBudget,
    dry_run: bool,
    summary: RunSummary,
) -> None:
    """Keep the historical outside-window refresh, without full journey sync."""

    from src.services.transfer_heal_service import refresh_and_heal

    summary.modes.append("local")
    for team_db_id in teams_with_active_tracked_players():
        if is_job_paused("transfer_heal_paused") or budget.exhausted:
            break
        try:
            db.session.rollback()
            refresh_and_heal(
                team_id=team_db_id,
                resync_journeys=False,
                dry_run=dry_run,
                cascade_fixtures=True,
                orphan_budget=0,
                api_client=client,
            )
            summary.teams_scanned += 1
        except APICallBudgetExceeded:
            break
        except Exception as exc:
            db.session.rollback()
            logger.error("Local transfer refresh failed for Team db_id=%d: %s", team_db_id, exc)
            summary.errors.append(f"local team {team_db_id}: {exc}")


def _queued_player_count() -> int:
    queued: set[int] = set()
    delta = _load_setting(DELTA_QUEUE_SETTING, strict=True) or {}
    for raw_player_id in (delta.get("players") or {}).keys():
        player_api_id = _int_or_none(raw_player_id)
        if player_api_id is not None:
            queued.add(player_api_id)
    sweep = _load_setting(SWEEP_STATE_SETTING, strict=True) or {}
    for queue in (sweep.get("tranches") or {}).values():
        if not isinstance(queue, dict):
            continue
        for raw_player_id in queue.get("remaining") or []:
            player_api_id = _int_or_none(raw_player_id)
            if player_api_id is not None:
                queued.add(player_api_id)
    return len(queued)


def _run_locked(
    dry_run: bool = False,
    *,
    mode: str | None = None,
    now: datetime | None = None,
    api_client: APIFootballClient | None = None,
    call_budget: APICallBudget | None = None,
) -> dict[str, Any]:
    """Execute after the caller has acquired the cadence-wide lock."""
    run_started_at = _as_utc(now or _utcnow())
    window = transfer_window_context(run_started_at.date())
    plan = planned_modes(
        requested_mode=mode,
        today=run_started_at.date(),
    )
    budget = call_budget or _durable_daily_budget(run_started_at.date())
    budget_spent_at_start = budget.spent
    client = api_client or APIFootballClient(
        call_budget=budget,
        skip_handshake=True,
    )
    try:
        client.call_budget = budget
    except (AttributeError, TypeError) as exc:
        raise TypeError("api_client must allow the cadence call budget to be attached") from exc
    summary = RunSummary()

    logger.info(
        "Transfer cadence starting. requested_mode=%s plan=%s in_window=%s deadline_week=%s dry_run=%s budget=%d",
        mode or "auto",
        plan,
        window.in_window,
        window.deadline_week,
        dry_run,
        budget.limit,
    )

    if plan == ["local"]:
        _run_local_refresh(
            client=client,
            budget=budget,
            dry_run=dry_run,
            summary=summary,
        )
    else:
        if "delta" in plan:
            _run_delta(
                client=client,
                budget=budget,
                run_started_at=run_started_at,
                window=window,
                dry_run=dry_run,
                summary=summary,
            )
        sweep_tranches = [item.split(":", 1)[1] for item in plan if item.startswith("sweep:")]
        if sweep_tranches:
            _run_sweep(
                sweep_tranches,
                client=client,
                budget=budget,
                today=run_started_at.date(),
                dry_run=dry_run,
                summary=summary,
            )

    result = summary.as_dict(
        budget=budget,
        budget_spent_at_start=budget_spent_at_start,
        remainder_queued=_queued_player_count(),
    )
    logger.info(
        "Transfer cadence summary: teams_scanned=%d new_transfers_found=%d "
        "players_flagged=%d players_resynced=%d api_calls_this_run=%d "
        "daily_api_calls=%d/%d remainder_queued=%d modes=%s",
        result["teams_scanned"],
        result["new_transfers_found"],
        result["players_flagged"],
        result["players_resynced"],
        result["api_calls_spent_this_run"],
        result["api_calls_spent"],
        result["api_call_budget"],
        result["remainder_queued"],
        ",".join(result["modes"]) or "none",
    )
    if result["errors"]:
        logger.warning("Transfer cadence completed with errors: %s", json.dumps(result["errors"]))
    return result


def run(
    dry_run: bool = False,
    *,
    mode: str | None = None,
    now: datetime | None = None,
    api_client: APIFootballClient | None = None,
    call_budget: APICallBudget | None = None,
) -> dict[str, Any]:
    """Run explicit delta/sweep mode or the no-args calendar dispatch."""

    try:
        db.session.rollback()
    except Exception:
        pass

    if is_job_paused("transfer_heal_paused"):
        logger.info("Transfer heal is paused by admin. Exiting.")
        return {"error": "paused"}

    with _cadence_run_lock() as acquired:
        if not acquired or has_running_job("transfer_heal"):
            logger.info("Another transfer heal job is already running. Exiting.")
            return {"error": "already_running"}
        return _run_locked(
            dry_run=dry_run,
            mode=mode,
            now=now,
            api_client=api_client,
            call_budget=call_budget,
        )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("delta", "sweep"))
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    with app.app_context():
        run(dry_run=args.dry_run, mode=args.mode)
