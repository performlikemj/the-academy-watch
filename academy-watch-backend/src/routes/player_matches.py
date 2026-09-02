"""Public match-entry reads and claimant-owned self-report CRUD."""

import logging
from datetime import UTC, date, datetime, timedelta

from flask import Blueprint, g, jsonify, request
from itsdangerous import BadSignature, SignatureExpired
from sqlalchemy.exc import IntegrityError
from src.auth import _user_serializer, require_user_auth
from src.extensions import limiter
from src.models.follow import PlayerShadow
from src.models.funding import ClubRosterMember
from src.models.league import UserAccount, db
from src.models.player_match_entry import PlayerMatchEntry
from src.models.showcase import LocalPlayer, PlayerProfileClaim, local_player_is_minor
from src.models.tracked_player import TrackedPlayer
from src.services import season_rollup_service
from src.services.club_registry import _is_manager_of_approved_program
from src.services.player_suppression import (
    is_local_player_suppressed,
    is_player_suppressed,
    neutral_player_not_found,
)
from src.utils.academy_window import current_stats_season
from src.utils.sanitize import sanitize_plain_text

player_matches_bp = Blueprint("player_matches", __name__)
logger = logging.getLogger(__name__)

# Every approved representative who may manage private entries may also read
# them. Public visibility remains independently blocked for every minor.
CLAIM_RELATIONSHIPS = frozenset({"player", "guardian", "agent"})
HOME_AWAY_VALUES = frozenset({"home", "away", "neutral"})
COUNT_FIELDS = ("goals", "assists", "yellows", "reds")
OPTIONAL_COUNT_FIELDS = ("result_for", "result_against", "saves", "goals_conceded")
EDITABLE_FIELDS = frozenset(
    {
        "match_date",
        "competition",
        "opponent",
        "home_away",
        "result_for",
        "result_against",
        "minutes",
        "goals",
        "assists",
        "yellows",
        "reds",
        "saves",
        "goals_conceded",
        "note",
    }
)


def _user_rate_limit_key() -> str:
    return getattr(g, "user_email", None) or (request.remote_addr or "anon")


def _optional_authenticated_user() -> UserAccount | None:
    """Read-only optional auth; invalid credentials degrade to anonymous."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth.split(" ", 1)[1].strip()
    if not token:
        return None
    try:
        data = _user_serializer().loads(token, max_age=60 * 60 * 24 * 30)
        if not isinstance(data, dict):
            return None
        email = (data.get("email") or "").strip()
        if not email:
            return None
        token_user_id = data.get("user_id")
        if token_user_id is None:
            user = UserAccount.query.filter_by(email=email).first()
            token_iat = data.get("iat")
            if user is not None and user.created_at is not None and isinstance(token_iat, int):
                created_at = user.created_at
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=UTC)
                if int(created_at.timestamp()) > token_iat:
                    user = None
        else:
            if isinstance(token_user_id, bool):
                return None
            try:
                token_user_id = int(token_user_id)
            except (TypeError, ValueError):
                return None
            user = db.session.get(UserAccount, token_user_id)
            if user is not None and (user.email or "").strip().lower() != email.lower():
                return None
            account_created_at = data.get("account_created_at")
            if account_created_at is not None and (
                user is None or user.created_at is None or user.created_at.isoformat() != account_created_at
            ):
                return None
        if user is None or getattr(user, "is_tombstone", False):
            return None
        return user
    except (BadSignature, SignatureExpired, TypeError, ValueError):
        return None


def _positive_subject_is_minor(
    player_api_id: int, tracked_rows: list[TrackedPlayer], shadow: PlayerShadow | None
) -> bool:
    """Conservative persisted-age rule for tracked/shadow identities."""
    return season_rollup_service.positive_subject_is_minor(
        player_api_id,
        tracked_rows,
        shadow,
        session=db.session,
        today=datetime.now(UTC).date(),
    )


def _resolve_subject(player_api_id: int) -> dict | None:
    """Resolve one signed player identity without any upstream API call."""
    if player_api_id == 0:
        return None
    if player_api_id < 0:
        local_player_id = -player_api_id
        local = db.session.get(LocalPlayer, local_player_id)
        if (
            local is None
            or local.status != "approved"
            or (local.api_player_id is not None and local.api_player_id != player_api_id)
            or local.merged_into_local_player_id is not None
            or is_local_player_suppressed(local_player_id)
            or is_player_suppressed(player_api_id)
        ):
            return None
        return {
            "player_api_id": player_api_id,
            "local_player_id": local_player_id,
            "is_minor": local_player_is_minor(local),
        }

    if is_player_suppressed(player_api_id):
        return None
    bridged_local_ids = [
        row[0] for row in db.session.query(LocalPlayer.id).filter(LocalPlayer.api_player_id == player_api_id).all()
    ]
    if any(is_local_player_suppressed(local_id) for local_id in bridged_local_ids):
        return None
    tracked_rows = TrackedPlayer.query.filter_by(player_api_id=player_api_id).order_by(TrackedPlayer.id.asc()).all()
    shadow = PlayerShadow.query.filter_by(player_api_id=player_api_id, is_active=True).first()
    if not tracked_rows and shadow is None:
        return None
    return {
        "player_api_id": player_api_id,
        "local_player_id": None,
        "is_minor": _positive_subject_is_minor(player_api_id, tracked_rows, shadow),
    }


def _claim_for_user(subject: dict, user_id: int, relationships: frozenset[str]) -> PlayerProfileClaim | None:
    query = PlayerProfileClaim.query.filter(
        PlayerProfileClaim.user_account_id == user_id,
        PlayerProfileClaim.status == "approved",
        PlayerProfileClaim.relationship_type.in_(relationships),
    )
    if subject["local_player_id"] is not None:
        query = query.filter(
            PlayerProfileClaim.local_player_id == subject["local_player_id"],
            PlayerProfileClaim.player_api_id.is_(None),
        )
    else:
        query = query.filter(
            PlayerProfileClaim.player_api_id == subject["player_api_id"],
            PlayerProfileClaim.local_player_id.is_(None),
        )
    return query.order_by(PlayerProfileClaim.id.asc()).first()


def _manager_can_read_subject(subject: dict, user_id: int) -> bool:
    subject_filter = (
        ClubRosterMember.local_player_id == subject["local_player_id"]
        if subject["local_player_id"] is not None
        else ClubRosterMember.player_api_id == subject["player_api_id"]
    )
    program_ids = [
        row[0] for row in db.session.query(ClubRosterMember.program_id).filter(subject_filter).distinct().all()
    ]
    return any(_is_manager_of_approved_program(user_id, program_id) for program_id in program_ids)


def _json_object() -> dict:
    payload = request.get_json(silent=True)
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValueError("JSON body must be an object")
    return payload


def _parse_match_date(value) -> date:
    if not isinstance(value, str):
        raise ValueError("match_date must be an ISO date in YYYY-MM-DD format")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise ValueError("match_date must be an ISO date in YYYY-MM-DD format") from None
    if value != parsed.isoformat():
        raise ValueError("match_date must be an ISO date in YYYY-MM-DD format")
    if parsed < date(1970, 1, 1):
        raise ValueError("match_date cannot be before 1970-01-01")
    if parsed > datetime.now(UTC).date() + timedelta(days=1):
        raise ValueError("match_date cannot be more than one day in the future")
    return parsed


def _clean_text(value, field: str, limit: int, *, required: bool) -> str | None:
    if value is None:
        if required:
            raise ValueError(f"{field} is required")
        return None
    if not isinstance(value, str):
        suffix = "" if required else " or null"
        raise ValueError(f"{field} must be a string{suffix}")
    cleaned = sanitize_plain_text(value).strip()
    if required and not cleaned:
        raise ValueError(f"{field} is required")
    if len(cleaned) > limit:
        raise ValueError(f"{field} must be at most {limit} characters")
    return cleaned or None


def _bounded_int(value, field: str, maximum: int, *, nullable: bool = False) -> int | None:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        suffix = " or null" if nullable else ""
        raise ValueError(f"{field} must be an integer{suffix}")
    if not 0 <= value <= maximum:
        raise ValueError(f"{field} must be between 0 and {maximum}")
    return value


def _entry_values(payload: dict, existing: PlayerMatchEntry | None = None) -> dict:
    if existing is None:
        if "match_date" not in payload:
            raise ValueError("match_date is required")
        if "opponent" not in payload:
            raise ValueError("opponent is required")
        if "home_away" not in payload:
            raise ValueError("home_away is required")
        values = {
            "match_date": _parse_match_date(payload.get("match_date")),
            "competition": _clean_text(payload.get("competition"), "competition", 120, required=False),
            "opponent": _clean_text(payload.get("opponent"), "opponent", 120, required=True),
            "home_away": payload.get("home_away"),
            "minutes": _bounded_int(payload.get("minutes", 0), "minutes", 130),
            "note": _clean_text(payload.get("note"), "note", 500, required=False),
        }
        values.update({field: _bounded_int(payload.get(field, 0), field, 20) for field in COUNT_FIELDS})
        values.update(
            {field: _bounded_int(payload.get(field), field, 20, nullable=True) for field in OPTIONAL_COUNT_FIELDS}
        )
    else:
        if not EDITABLE_FIELDS.intersection(payload):
            raise ValueError("at least one editable match field is required")
        values = {field: getattr(existing, field) for field in EDITABLE_FIELDS}
        if "match_date" in payload:
            values["match_date"] = _parse_match_date(payload.get("match_date"))
        if "competition" in payload:
            values["competition"] = _clean_text(payload.get("competition"), "competition", 120, required=False)
        if "opponent" in payload:
            values["opponent"] = _clean_text(payload.get("opponent"), "opponent", 120, required=True)
        if "home_away" in payload:
            values["home_away"] = payload.get("home_away")
        if "minutes" in payload:
            values["minutes"] = _bounded_int(payload.get("minutes"), "minutes", 130)
        for field in COUNT_FIELDS:
            if field in payload:
                values[field] = _bounded_int(payload.get(field), field, 20)
        for field in OPTIONAL_COUNT_FIELDS:
            if field in payload:
                values[field] = _bounded_int(payload.get(field), field, 20, nullable=True)
        if "note" in payload:
            values["note"] = _clean_text(payload.get("note"), "note", 500, required=False)

    home_away = values["home_away"]
    if not isinstance(home_away, str) or home_away not in HOME_AWAY_VALUES:
        raise ValueError(f"home_away must be one of {sorted(HOME_AWAY_VALUES)}")
    return values


def _query_integer(name: str, default: int, *, minimum: int = 1, maximum: int | None = None) -> int:
    raw = request.args.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be an integer") from None
    if value < minimum or (maximum is not None and value > maximum):
        if maximum is None:
            raise ValueError(f"{name} must be at least {minimum}")
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _write_claim_or_error(player_api_id: int):
    subject = _resolve_subject(player_api_id)
    if subject is None:
        return None, None, neutral_player_not_found()
    claim = _claim_for_user(subject, g.user_id, CLAIM_RELATIONSHIPS)
    if claim is None:
        if subject["is_minor"]:
            return subject, None, neutral_player_not_found()
        return subject, None, (jsonify({"error": "You do not have an approved claim for this player"}), 403)
    return subject, claim, None


def _find_self_entry(
    player_api_id: int,
    match_date: date,
    opponent: str,
    user_id: int,
) -> PlayerMatchEntry | None:
    return PlayerMatchEntry.query.filter_by(
        player_api_id=player_api_id,
        match_date=match_date,
        opponent=opponent,
        source="self",
        reported_by_user_id=user_id,
    ).first()


def _apply_self_entry(
    entry: PlayerMatchEntry,
    values: dict,
    *,
    player_api_id: int,
    user_id: int,
    season: int,
) -> None:
    for field, value in values.items():
        setattr(entry, field, value)
    entry.player_api_id = player_api_id
    entry.season = season
    entry.source = "self"
    entry.status = "self_reported"
    entry.reported_by_user_id = user_id
    entry.club_program_id = None


@player_matches_bp.route("/players/<int(signed=True):player_api_id>/matches", methods=["GET"])
def list_player_matches(player_api_id: int):
    try:
        subject = _resolve_subject(player_api_id)
        if subject is None:
            return neutral_player_not_found()
        user = _optional_authenticated_user()
        if subject["is_minor"]:
            can_read = bool(
                user
                and (
                    _claim_for_user(subject, user.id, CLAIM_RELATIONSHIPS)
                    or _manager_can_read_subject(subject, user.id)
                )
            )
            if not can_read:
                return neutral_player_not_found()

        season = request.args.get("season")
        if season is not None:
            try:
                season = int(season)
            except (TypeError, ValueError):
                raise ValueError("season must be an integer") from None
        source = request.args.get("source")
        if source is not None and source not in {"self", "club"}:
            raise ValueError("source must be self or club")
        page = _query_integer("page", 1)
        per_page = _query_integer("per_page", 25, maximum=100)

        query = PlayerMatchEntry.query.filter_by(player_api_id=player_api_id)
        if season is not None:
            query = query.filter(PlayerMatchEntry.season == season)
        if source is not None:
            query = query.filter(PlayerMatchEntry.source == source)
        total = query.count()
        rows = (
            query.order_by(PlayerMatchEntry.match_date.desc(), PlayerMatchEntry.id.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )
        write_claim = _claim_for_user(subject, user.id, CLAIM_RELATIONSHIPS) if user else None
        return jsonify(
            {
                "matches": [
                    row.to_dict(
                        editable=bool(write_claim and row.source == "self" and row.reported_by_user_id == user.id)
                    )
                    for row in rows
                ],
                "total": total,
                "page": page,
                "per_page": per_page,
            }
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception:
        logger.exception("Failed to list match entries for player %s", player_api_id)
        return jsonify({"error": "Failed to load player matches"}), 500


@player_matches_bp.route("/players/<int(signed=True):player_api_id>/matches", methods=["POST"])
@require_user_auth
@limiter.limit("30/minute", key_func=_user_rate_limit_key)
def create_player_match(player_api_id: int):
    try:
        _subject, _claim, error = _write_claim_or_error(player_api_id)
        if error:
            return error
        values = _entry_values(_json_object())
        season = current_stats_season(values["match_date"])
        entry = _find_self_entry(
            player_api_id,
            values["match_date"],
            values["opponent"],
            g.user_id,
        )
        created = entry is None
        if entry is None:
            entry = PlayerMatchEntry()
            db.session.add(entry)
        _apply_self_entry(
            entry,
            values,
            player_api_id=player_api_id,
            user_id=g.user_id,
            season=season,
        )
        try:
            db.session.flush()
        except IntegrityError:
            # Another identical POST may have committed after our preflight.
            # Join that winner and apply this request as the idempotent update.
            db.session.rollback()
            entry = _find_self_entry(
                player_api_id,
                values["match_date"],
                values["opponent"],
                g.user_id,
            )
            if entry is None:
                raise
            created = False
            _apply_self_entry(
                entry,
                values,
                player_api_id=player_api_id,
                user_id=g.user_id,
                season=season,
            )
            db.session.flush()
        season_stats = season_rollup_service.refresh_player(player_api_id, season, session=db.session)
        db.session.commit()
        return jsonify({"match": entry.to_dict(editable=True), "season_stats": season_stats}), 201 if created else 200
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400
    except Exception:
        db.session.rollback()
        logger.exception("Failed to create match entry for player %s", player_api_id)
        return jsonify({"error": "Failed to save player match"}), 500


@player_matches_bp.route(
    "/players/<int(signed=True):player_api_id>/matches/<int:entry_id>",
    methods=["PATCH"],
)
@require_user_auth
@limiter.limit("30/minute", key_func=_user_rate_limit_key)
def update_player_match(player_api_id: int, entry_id: int):
    try:
        _subject, _claim, error = _write_claim_or_error(player_api_id)
        if error:
            return error
        entry = PlayerMatchEntry.query.filter_by(
            id=entry_id,
            player_api_id=player_api_id,
            reported_by_user_id=g.user_id,
            source="self",
        ).first()
        if entry is None:
            return jsonify({"error": "Match entry not found"}), 404
        old_season = entry.season
        values = _entry_values(_json_object(), existing=entry)
        for field, value in values.items():
            setattr(entry, field, value)
        entry.season = current_stats_season(entry.match_date)
        entry.source = "self"
        entry.status = "self_reported"
        entry.reported_by_user_id = g.user_id
        entry.club_program_id = None
        try:
            db.session.flush()
        except IntegrityError:
            db.session.rollback()
            return jsonify({"error": "A match entry already exists for that date and opponent"}), 409
        refreshes = {}
        for season in sorted({old_season, entry.season}):
            refreshes[season] = season_rollup_service.refresh_player(
                player_api_id,
                season,
                session=db.session,
            )
        db.session.commit()
        return jsonify(
            {
                "match": entry.to_dict(editable=True),
                "season_stats": refreshes[entry.season],
            }
        )
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400
    except Exception:
        db.session.rollback()
        logger.exception("Failed to update match entry %s for player %s", entry_id, player_api_id)
        return jsonify({"error": "Failed to update player match"}), 500


@player_matches_bp.route(
    "/players/<int(signed=True):player_api_id>/matches/<int:entry_id>",
    methods=["DELETE"],
)
@require_user_auth
@limiter.limit("30/minute", key_func=_user_rate_limit_key)
def delete_player_match(player_api_id: int, entry_id: int):
    try:
        _subject, _claim, error = _write_claim_or_error(player_api_id)
        if error:
            return error
        entry = PlayerMatchEntry.query.filter_by(
            id=entry_id,
            player_api_id=player_api_id,
            reported_by_user_id=g.user_id,
            source="self",
        ).first()
        if entry is None:
            return jsonify({"error": "Match entry not found"}), 404
        season = entry.season
        db.session.delete(entry)
        db.session.flush()
        season_rollup_service.refresh_player(player_api_id, season, session=db.session)
        db.session.commit()
        return jsonify({"deleted": True, "season": season, "rollup_refreshed": True})
    except Exception:
        db.session.rollback()
        logger.exception("Failed to delete match entry %s for player %s", entry_id, player_api_id)
        return jsonify({"error": "Failed to delete player match"}), 500


__all__ = ["player_matches_bp"]
