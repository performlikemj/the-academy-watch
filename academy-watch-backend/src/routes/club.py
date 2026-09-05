"""Verified club-manager roster and match-video console.

Roster membership is a private authorization boundary for video and reports;
it is deliberately not a player claim, public affiliation, or contact-consent
signal. GPU processing, tracklet review, tag review, and finalization remain on
the existing admin-only concierge routes.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import unicodedata
import uuid
from datetime import UTC, date, datetime, timedelta
from functools import wraps
from html import unescape
from urllib.parse import urlsplit

from flask import Blueprint, g, jsonify, request
from sqlalchemy import func, or_, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from src.auth import mint_media_token
from src.extensions import limiter
from src.models.club_invitation import (
    ClubInvitation,
    InvitationError,
    create_invitation,
    governed_member_available,
    invitation_dict,
    list_invitations,
    relationships_enabled,
    resolve_invitation,
)
from src.models.funding import (
    ClubProgram,
    ClubProgramProfileRevision,
    ClubProgramUpdate,
    ClubRosterMember,
    approved_revision_for,
    revision_dict,
    update_dict,
)
from src.models.league import Team, db
from src.models.player_match_entry import PlayerMatchEntry
from src.models.season_rollup import PlayerSeasonTotal
from src.models.showcase import LocalPlayer, local_player_is_minor
from src.models.tracked_player import TrackedPlayer
from src.models.video import VideoMatch, VideoPlayerReport, VideoRosterEntry, VideoTracklet
from src.services import season_rollup_service, video_retention, video_storage
from src.services.capture_meta import merge_preflight
from src.services.club_player_authority import club_authorized_player_ids, club_has_authority_over_player
from src.services.club_registry import require_club_manager
from src.services.coach_brief import MAX_BRIEF_CHARS, MAX_BRIEF_LINE_CHARS, MAX_BRIEF_LINES, brief_payload
from src.services.player_identity import retained_shadow_identity_exists
from src.services.player_subject import resolve_player_subject
from src.services.player_suppression import is_local_player_suppressed, is_player_suppressed
from src.utils.academy_window import current_stats_season
from src.utils.sanitize import is_safe_https_url, sanitize_plain_text

club_bp = Blueprint("club", __name__)
logger = logging.getLogger(__name__)

RAW_RETENTION_DAYS = 90
DEFAULT_MATCH_QUOTA = 3
MAX_MATCH_QUOTA = 100
QUOTA_LOCK_NAMESPACE = 4_343_202
RESULT_PLAYER_LOCK_NAMESPACE = 4_343_203
MAX_CAPTURE_META_BYTES = 8 * 1024
MAX_CAPTURE_META_DEPTH = 4
MAX_CAPTURE_META_KEYS = 50
MAX_TIMELINE_SECONDS = 6 * 60 * 60
BRIEF_NAME_TOKEN_RE = re.compile(r"[^\W\d_]{2,}")
CLUB_EDITABLE_MATCH_STATUSES = {"created", "uploaded"}
RESULT_COUNT_FIELDS = ("goals", "assists", "yellows", "reds")
RESULT_OPTIONAL_COUNT_FIELDS = ("saves", "goals_conceded")
RESULT_STAT_FIELDS = ("appearances", "minutes", *RESULT_COUNT_FIELDS, *RESULT_OPTIONAL_COUNT_FIELDS)
TEXT_LIMITS = {
    "opponent_name": 200,
    "competition": 200,
    "our_kit_color": 50,
    "opponent_kit_color": 50,
}
PROGRAM_PROFILE_LIMITS = {
    "summary_max": 2000,
    "funding_purpose_max": 1000,
    "list_items_max": 12,
    "list_item_max": 40,
    "media_urls_max": 6,
    "updates_pending_max": 5,
}
EXTERNAL_SUPPORT_HOSTS = {
    "patreon": {"patreon.com", "www.patreon.com"},
    "buy_me_a_coffee": {"buymeacoffee.com", "www.buymeacoffee.com"},
}


def _bad_request(message: str):
    return jsonify({"error": message}), 400


def _payload() -> dict:
    data = request.get_json(silent=True)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError("JSON body must be an object")
    return data


def _clean_optional(value, field: str, limit: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string or null")
    cleaned = sanitize_plain_text(value).strip()
    if len(cleaned) > limit:
        raise ValueError(f"{field} must be at most {limit} characters")
    return cleaned or None


def _user_rate_limit_key():
    return getattr(g, "user_email", None) or request.remote_addr or "anon"


def _field_text(value, field: str, limit: int, *, required: bool = False) -> str | None:
    if value is None:
        if required:
            raise ValueError(f"{field} is required")
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    decoded = value
    while (next_decoded := unescape(decoded)) != decoded:
        decoded = next_decoded
    cleaned = unescape(sanitize_plain_text(decoded)).strip()
    if required and not cleaned:
        raise ValueError(f"{field} is required")
    if len(cleaned) > limit:
        raise ValueError(f"{field} must be at most {limit} characters")
    return cleaned or None


def _field_list(value, field: str, *, max_items: int, item_limit: int) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    if len(value) > max_items:
        raise ValueError(f"{field} must contain at most {max_items} items")
    cleaned_items = []
    for item in value:
        cleaned = _field_text(item, field, item_limit, required=True)
        if cleaned not in cleaned_items:
            cleaned_items.append(cleaned)
    return cleaned_items


def _field_url_text(value, field: str, limit: int, *, required: bool = False) -> str | None:
    if value is None:
        if required:
            raise ValueError(f"{field} is required")
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    cleaned = value.strip()
    if required and not cleaned:
        raise ValueError(f"{field} is required")
    if len(cleaned) > limit:
        raise ValueError(f"{field} must be at most {limit} characters")
    if cleaned and ("<" in cleaned or ">" in cleaned or any(character.isspace() for character in cleaned)):
        raise ValueError(f"{field} must not contain angle brackets or whitespace")
    return cleaned or None


def _field_https(value, field: str, *, required: bool = False) -> str | None:
    cleaned = _field_url_text(value, field, 500, required=required)
    if cleaned and not is_safe_https_url(cleaned):
        raise ValueError(f"{field} must be an absolute https URL")
    return cleaned


def _field_https_list(value, field: str, *, max_items: int) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    if len(value) > max_items:
        raise ValueError(f"{field} must contain at most {max_items} items")
    cleaned_items = []
    for item in value:
        cleaned = _field_https(item, field, required=True)
        if cleaned not in cleaned_items:
            cleaned_items.append(cleaned)
    return cleaned_items


def _external_support(value) -> tuple[str | None, str | None]:
    if value is None:
        return None, None
    if not isinstance(value, dict):
        raise ValueError("external_support must be an object or null")
    provider = _field_text(value.get("provider"), "external_support.provider", 30, required=True)
    if provider not in EXTERNAL_SUPPORT_HOSTS:
        raise ValueError("external_support.provider must be patreon or buy_me_a_coffee")
    url = _field_url_text(value.get("url"), "external_support.url", 200, required=True)
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("external_support.url must be a valid provider URL") from exc
    host = (parsed.hostname or "").lower()
    if (
        parsed.scheme.lower() != "https"
        or host not in EXTERNAL_SUPPORT_HOSTS[provider]
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.query
        or parsed.fragment
        or not parsed.path.strip("/")
    ):
        raise ValueError("external_support.url must be an allowed provider profile URL")
    normalized_path = parsed.path.rstrip("/")
    return provider, f"https://{host}{normalized_path}"


def _profile_values(data) -> tuple[dict, dict[str, str]]:
    if not isinstance(data, dict):
        return {}, {"body": "JSON body must be an object"}
    values = {}
    errors = {}
    specs = (
        ("summary", lambda value: _field_text(value, "summary", PROGRAM_PROFILE_LIMITS["summary_max"])),
        (
            "funding_purpose",
            lambda value: _field_text(value, "funding_purpose", PROGRAM_PROFILE_LIMITS["funding_purpose_max"]),
        ),
        ("official_url", lambda value: _field_https(value, "official_url")),
        ("safeguarding_url", lambda value: _field_https(value, "safeguarding_url")),
        (
            "age_groups",
            lambda value: _field_list(
                value,
                "age_groups",
                max_items=PROGRAM_PROFILE_LIMITS["list_items_max"],
                item_limit=PROGRAM_PROFILE_LIMITS["list_item_max"],
            ),
        ),
        (
            "activities",
            lambda value: _field_list(
                value,
                "activities",
                max_items=PROGRAM_PROFILE_LIMITS["list_items_max"],
                item_limit=PROGRAM_PROFILE_LIMITS["list_item_max"],
            ),
        ),
        (
            "media_urls",
            lambda value: _field_https_list(
                value,
                "media_urls",
                max_items=PROGRAM_PROFILE_LIMITS["media_urls_max"],
            ),
        ),
    )
    for field, parser in specs:
        try:
            values[field] = parser(data.get(field))
        except ValueError as exc:
            errors[field] = str(exc)
    try:
        provider, url = _external_support(data.get("external_support"))
        values["external_support_provider"] = provider
        values["external_support_url"] = url
    except ValueError as exc:
        errors["external_support"] = str(exc)
    return values, errors


def _update_values(data) -> tuple[dict, dict[str, str]]:
    if not isinstance(data, dict):
        return {}, {"body": "JSON body must be an object"}
    values = {}
    errors = {}
    for field, limit, minimum, required in (
        ("title", 140, 3, True),
        ("body", 4000, 20, True),
        ("impact", 500, 0, False),
    ):
        try:
            cleaned = _field_text(data.get(field), field, limit, required=required)
            if cleaned is not None and len(cleaned) < minimum:
                raise ValueError(f"{field} must be at least {minimum} characters")
            values[field] = cleaned
        except ValueError as exc:
            errors[field] = str(exc)
    return values, errors


def _validation_failed(fields):
    return jsonify({"error": "validation_failed", "fields": fields}), 400


def _positive_int(value, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _timeline_value(value, field: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a number or null")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a number or null") from exc
    if not math.isfinite(parsed) or parsed < 0:
        raise ValueError(f"{field} must be a finite non-negative number")
    if parsed > MAX_TIMELINE_SECONDS:
        raise ValueError(f"{field} must be at most {MAX_TIMELINE_SECONDS} seconds")
    return parsed


def _match_date(value):
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ValueError("match_date must be YYYY-MM-DD or null")
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("match_date must be YYYY-MM-DD or null") from exc


class _ClubResultConflict(Exception):
    pass


def _result_match_date(value) -> date:
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


def _bounded_result_int(value, field: str, maximum: int, *, nullable: bool = False) -> int | None:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        suffix = " or null" if nullable else ""
        raise ValueError(f"{field} must be an integer{suffix}")
    if not 0 <= value <= maximum:
        raise ValueError(f"{field} must be between 0 and {maximum}")
    return value


def _result_header_values(data: dict) -> dict:
    for field in ("match_date", "opponent", "home_away", "result_for", "result_against"):
        if field not in data:
            raise ValueError(f"{field} is required")
    opponent = _clean_optional(data.get("opponent"), "opponent", 120)
    if opponent is None:
        raise ValueError("opponent is required")
    home_away = data.get("home_away")
    if not isinstance(home_away, str) or home_away not in {"home", "away", "neutral"}:
        raise ValueError("home_away must be one of ['away', 'home', 'neutral']")
    return {
        "match_date": _result_match_date(data.get("match_date")),
        "opponent": opponent,
        "competition": _clean_optional(data.get("competition"), "competition", 120),
        "home_away": home_away,
        "result_for": _bounded_result_int(data.get("result_for"), "result_for", 20),
        "result_against": _bounded_result_int(data.get("result_against"), "result_against", 20),
    }


def _result_entry_values(data: dict) -> dict:
    values = {
        "minutes": _bounded_result_int(data.get("minutes", 0), "minutes", 130),
        "note": _clean_optional(data.get("note"), "note", 500),
    }
    values.update({field: _bounded_result_int(data.get(field, 0), field, 20) for field in RESULT_COUNT_FIELDS})
    values.update(
        {
            field: _bounded_result_int(data.get(field), field, 20, nullable=True)
            for field in RESULT_OPTIONAL_COUNT_FIELDS
        }
    )
    return values


def _normalized_result(header: dict, video_match_id: int | None) -> dict:
    return {
        "video_match_id": video_match_id,
        "match_date": header["match_date"].isoformat(),
        "opponent": header["opponent"],
        "competition": header["competition"],
        "home_away": header["home_away"],
        "result_for": header["result_for"],
        "result_against": header["result_against"],
    }


def _capture_meta(value):
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("capture_meta must be an object or null")

    key_count = 0

    def inspect_shape(node, depth: int) -> None:
        nonlocal key_count
        if isinstance(node, dict):
            if depth > MAX_CAPTURE_META_DEPTH:
                raise ValueError(f"capture_meta nesting depth must be at most {MAX_CAPTURE_META_DEPTH}")
            key_count += len(node)
            if key_count > MAX_CAPTURE_META_KEYS:
                raise ValueError(f"capture_meta must contain at most {MAX_CAPTURE_META_KEYS} keys")
            for child in node.values():
                inspect_shape(child, depth + 1)
        elif isinstance(node, list):
            if depth > MAX_CAPTURE_META_DEPTH:
                raise ValueError(f"capture_meta nesting depth must be at most {MAX_CAPTURE_META_DEPTH}")
            for child in node:
                inspect_shape(child, depth + 1)

    inspect_shape(value, 1)
    try:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()
    except (TypeError, ValueError) as exc:
        raise ValueError("capture_meta must contain valid JSON values") from exc
    if len(encoded) > MAX_CAPTURE_META_BYTES:
        raise ValueError(f"capture_meta must be at most {MAX_CAPTURE_META_BYTES} serialized bytes")
    return value


def _club_match(program_id: int, match_id: int) -> VideoMatch | None:
    return VideoMatch.query.filter_by(id=match_id, club_program_id=program_id).first()


def _tracked_player(player_api_id: int) -> TrackedPlayer | None:
    return (
        TrackedPlayer.query.filter_by(player_api_id=player_api_id)
        .order_by(TrackedPlayer.is_active.desc(), TrackedPlayer.id.asc())
        .first()
    )


def _local_player_available(player: LocalPlayer | None) -> bool:
    return bool(
        player
        and player.status not in {"rejected", "merged"}
        and player.merged_into_local_player_id is None
        and not is_local_player_suppressed(player.id)
        and not (player.api_player_id and is_player_suppressed(player.api_player_id))
    )


def _member_subject(member: ClubRosterMember) -> tuple[dict | None, object | None]:
    if not governed_member_available(db.session, member):
        return None, None
    if member.player_api_id is not None:
        subject = resolve_player_subject(member.player_api_id)
        if subject is None or subject.is_suppressed:
            return None, None
        tracked_rows = TrackedPlayer.query.filter_by(player_api_id=member.player_api_id).all()
        is_minor = season_rollup_service.positive_subject_is_minor(
            member.player_api_id,
            tracked_rows,
            subject.shadow,
            session=db.session,
        )
        return (
            {
                "subject_type": "tracked",
                "player_api_id": subject.player_api_id,
                "local_player_id": None,
                "display_name": subject.display_name,
                "position": subject.position,
                "is_minor": is_minor,
            },
            subject.tracked_player or subject.shadow,
        )
    local = db.session.get(LocalPlayer, member.local_player_id)
    if not _local_player_available(local):
        return None, None
    return (
        {
            "subject_type": "local",
            "player_api_id": None,
            "local_player_id": local.id,
            "display_name": local.display_name,
            "position": local.position,
            "is_minor": local_player_is_minor(local),
        },
        local,
    )


def _member_dict(member: ClubRosterMember, *, authorized_player_ids: set[int] | None = None) -> dict:
    subject, player = _member_subject(member)
    public_stats_allowed = False
    if subject is not None and not subject["is_minor"]:
        if member.player_api_id is not None:
            public_stats_allowed = (
                member.player_api_id in authorized_player_ids
                if authorized_player_ids is not None
                else club_has_authority_over_player(
                    db.session.get(ClubProgram, member.program_id),
                    member.player_api_id,
                    season=current_stats_season(),
                    session=db.session,
                )
            )
        else:
            public_stats_allowed = player.status == "approved" and player.api_player_id == -player.id
    out = {
        "id": member.id,
        "program_id": member.program_id,
        "role": member.role,
        "note": member.note,
        "brief": _brief_dict(member.coach_brief_body, member.brief_updated_at),
        "created_at": member.created_at.isoformat() if member.created_at else None,
        "available": subject is not None,
        "public_stats_allowed": public_stats_allowed,
    }
    if subject is not None:
        out.update(subject)
    return out


def _brief_dict(body: str | None, updated_at: datetime | None) -> dict:
    payload = brief_payload(body)
    return {
        "body": body,
        "updated_at": updated_at.isoformat() if updated_at else None,
        "hash": payload["hash"] if payload else None,
        "lines": payload["lines"] if payload else None,
    }


def _brief_name_tokens(program: ClubProgram) -> dict[str, str]:
    names = []
    for member in program.roster_members:
        display_name = _member_dict(member).get("display_name")
        if display_name:
            names.append(display_name)
    names.extend(
        player_name
        for (player_name,) in db.session.query(VideoRosterEntry.player_name)
        .join(VideoMatch, VideoRosterEntry.video_match_id == VideoMatch.id)
        .filter(VideoMatch.club_program_id == program.id)
        .all()
        if player_name
    )
    tokens = {}
    for name in names:
        for token in BRIEF_NAME_TOKEN_RE.findall(name):
            tokens.setdefault(token.casefold(), token)
    return tokens


def _fold_brief_name(value: str) -> str:
    return "".join(
        character for character in unicodedata.normalize("NFKD", value) if not unicodedata.combining(character)
    ).casefold()


def _is_latin_word_character(character: str) -> bool:
    return character == "_" or character.isdigit() or unicodedata.name(character, "").startswith("LATIN ")


def _brief_name_token_matches(token: str, line: str) -> bool:
    folded_token = _fold_brief_name(token)
    folded_line = _fold_brief_name(line)
    contains_non_latin_letter = any(
        character.isalpha() and not unicodedata.name(character, "").startswith("LATIN ") for character in token
    )
    if contains_non_latin_letter:
        return folded_token in folded_line

    start = 0
    while (match_start := folded_line.find(folded_token, start)) != -1:
        match_end = match_start + len(folded_token)
        left_is_word = match_start > 0 and _is_latin_word_character(folded_line[match_start - 1])
        right_is_word = match_end < len(folded_line) and _is_latin_word_character(folded_line[match_end])
        if not left_is_word and not right_is_word:
            return True
        start = match_start + 1
    return False


def _clean_brief(body, program: ClubProgram) -> str | None:
    if not isinstance(body, str):
        raise ValueError("body must be a string")
    cleaned = body.strip()
    if not cleaned:
        return None
    if len(cleaned) > MAX_BRIEF_CHARS:
        raise ValueError(f"Brief must be at most {MAX_BRIEF_CHARS} characters")
    lines = [(line_number, line.strip()) for line_number, line in enumerate(body.splitlines(), start=1) if line.strip()]
    if len(lines) > MAX_BRIEF_LINES:
        raise ValueError(f"Brief must contain at most {MAX_BRIEF_LINES} non-empty lines")

    name_tokens = _brief_name_tokens(program)
    for line_number, line in lines:
        if len(line) > MAX_BRIEF_LINE_CHARS:
            raise ValueError(f"Brief lines must be at most {MAX_BRIEF_LINE_CHARS} characters")
        for token in name_tokens.values():
            if _brief_name_token_matches(token, line):
                raise ValueError(
                    f'Briefs describe behaviours, not people — remove the name "{token}" from line {line_number}.'
                )
    return "\n".join(line for _line_number, line in lines)


def _result_player(member: ClubRosterMember) -> tuple[int, str | None, bool]:
    if not governed_member_available(db.session, member):
        raise _ClubResultConflict("Every result player must be an available club roster member")
    if member.player_api_id is not None:
        subject, _ = _member_subject(member)
        if member.player_api_id <= 0 or subject is None:
            raise _ClubResultConflict("Every result player must be an available club roster member")
        return member.player_api_id, subject["display_name"], subject["is_minor"]

    local = db.session.get(LocalPlayer, member.local_player_id)
    if (
        local is None
        or local.status != "approved"
        or local.api_player_id != -local.id
        or local.merged_into_local_player_id is not None
    ):
        raise _ClubResultConflict(
            "Local roster members need an approved local player identity before stats can be recorded"
        )
    if not _local_player_available(local):
        raise _ClubResultConflict("Every result player must be an available club roster member")
    return -local.id, local.display_name, bool(local_player_is_minor(local))


def _result_entry_dict(entry: PlayerMatchEntry, member_id: int | None) -> dict:
    out = entry.to_dict()
    out["club_roster_member_id"] = member_id
    return out


def _club_season_stats(
    player_api_id: int,
    season: int,
    level_group: str,
    member_id: int,
    player_name: str | None,
    is_minor: bool,
) -> dict | None:
    metadata = {
        "club_roster_member_id": member_id,
        "player_name": player_name,
        "season": season,
        "level_group": level_group,
        "source": "club",
    }
    if is_minor:
        return {**metadata, "withheld": "minor"}
    total = PlayerSeasonTotal.query.filter_by(
        player_api_id=player_api_id,
        season=season,
        level_group=level_group,
    ).one_or_none()
    breakdown = total.source_breakdown if total is not None else None
    club_stats = breakdown.get("club") if isinstance(breakdown, dict) else None
    if not isinstance(club_stats, dict):
        return None
    return {
        **metadata,
        **{field: club_stats.get(field) for field in RESULT_STAT_FIELDS},
    }


def _quota() -> int:
    try:
        configured = int(os.getenv("CLUB_MATCH_QUOTA_DEFAULT", str(DEFAULT_MATCH_QUOTA)))
    except ValueError:
        configured = DEFAULT_MATCH_QUOTA
    return min(MAX_MATCH_QUOTA, max(1, configured))


def _lock_program_quota(program_id: int) -> None:
    """Serialize count+insert on Postgres; SQLite tests are single-process."""
    if db.session.get_bind().dialect.name == "postgresql":
        db.session.execute(
            text("SELECT pg_advisory_xact_lock(:namespace, :program_id)"),
            {"namespace": QUOTA_LOCK_NAMESPACE, "program_id": program_id},
        )


def _lock_result_players(player_api_ids: set[int]) -> None:
    """Serialize cross-program club-result identity checks on Postgres."""
    if db.session.get_bind().dialect.name == "postgresql":
        for player_api_id in sorted(player_api_ids):
            db.session.execute(
                text("SELECT pg_advisory_xact_lock(:namespace, :player_api_id)"),
                {
                    "namespace": RESULT_PLAYER_LOCK_NAMESPACE,
                    "player_api_id": player_api_id,
                },
            )


def _resolve_team_id(program: ClubProgram) -> int | None:
    if program.team_api_id is None:
        return None
    row = Team.query.filter_by(team_id=program.team_api_id).order_by(Team.season.desc(), Team.id.desc()).first()
    return row.id if row else None


@club_bp.route("/club/<int:program_id>/profile", methods=["GET"])
@require_club_manager()
def get_club_program_profile(program_id: int):
    program = db.session.get(ClubProgram, program_id)
    pending = (
        ClubProgramProfileRevision.query.filter_by(program_id=program_id, status="pending")
        .order_by(ClubProgramProfileRevision.created_at.desc(), ClubProgramProfileRevision.id.desc())
        .first()
    )
    approved = approved_revision_for(program)
    return jsonify(
        {
            "program": {"id": program.id, "slug": program.slug, "name": program.name},
            "approved": revision_dict(approved) if approved else None,
            "pending": revision_dict(pending) if pending else None,
            "limits": PROGRAM_PROFILE_LIMITS,
        }
    )


@club_bp.route("/club/<int:program_id>/profile", methods=["PUT"])
@require_club_manager()
@limiter.limit("20 per hour", key_func=_user_rate_limit_key)
def put_club_program_profile(program_id: int):
    values, errors = _profile_values(request.get_json(silent=True))
    if errors:
        return _validation_failed(errors)
    db.session.get(ClubProgram, program_id, with_for_update=True)
    pending_rows = (
        ClubProgramProfileRevision.query.filter_by(program_id=program_id, status="pending")
        .order_by(ClubProgramProfileRevision.created_at.desc(), ClubProgramProfileRevision.id.desc())
        .with_for_update()
        .all()
    )
    pending = pending_rows[0] if pending_rows else None
    for duplicate in pending_rows[1:]:
        db.session.delete(duplicate)
    if pending is None:
        pending = ClubProgramProfileRevision(
            program_id=program_id,
            submitted_by_user_id=g.user_id,
            status="pending",
            created_at=datetime.now(UTC).replace(tzinfo=None),
        )
        db.session.add(pending)
    else:
        pending.submitted_by_user_id = g.user_id
    for field, value in values.items():
        setattr(pending, field, value)
    db.session.commit()
    return jsonify({"pending": revision_dict(pending)})


@club_bp.route("/club/<int:program_id>/updates", methods=["GET"])
@require_club_manager()
def get_club_program_updates(program_id: int):
    updates = (
        ClubProgramUpdate.query.filter_by(program_id=program_id)
        .order_by(ClubProgramUpdate.created_at.desc(), ClubProgramUpdate.id.desc())
        .all()
    )
    return jsonify({"updates": [update_dict(update) for update in updates]})


@club_bp.route("/club/<int:program_id>/updates", methods=["POST"])
@require_club_manager()
@limiter.limit("10 per hour", key_func=_user_rate_limit_key)
def create_club_program_update(program_id: int):
    values, errors = _update_values(request.get_json(silent=True))
    if errors:
        return _validation_failed(errors)
    db.session.get(ClubProgram, program_id, with_for_update=True)
    pending_count = ClubProgramUpdate.query.filter_by(program_id=program_id, status="pending").count()
    if pending_count >= PROGRAM_PROFILE_LIMITS["updates_pending_max"]:
        return jsonify({"error": "pending_limit_reached"}), 409
    update = ClubProgramUpdate(
        program_id=program_id,
        author_user_id=g.user_id,
        status="pending",
        **values,
    )
    db.session.add(update)
    db.session.commit()
    return jsonify({"update": update_dict(update)}), 201


@club_bp.route("/club/<int:program_id>/updates/<int:update_id>", methods=["DELETE"])
@require_club_manager()
def delete_club_program_update(program_id: int, update_id: int):
    update = ClubProgramUpdate.query.filter_by(id=update_id, program_id=program_id).with_for_update().first()
    if update is None:
        return jsonify({"error": "update not found"}), 404
    if update.status in {"approved", "withdrawn"}:
        if update.status == "approved":
            update.status = "withdrawn"
            db.session.commit()
        return jsonify({"deleted": False, "status": "withdrawn"})
    db.session.delete(update)
    db.session.commit()
    return jsonify({"deleted": True, "status": None})


@club_bp.route("/club/<int:program_id>/roster", methods=["GET"])
@require_club_manager()
def list_club_roster(program_id: int):
    program = db.session.get(ClubProgram, program_id)
    rows = (
        ClubRosterMember.query.filter_by(program_id=program_id)
        .order_by(ClubRosterMember.created_at.asc(), ClubRosterMember.id.asc())
        .all()
    )
    authorized_player_ids = club_authorized_player_ids(
        program, {row.player_api_id for row in rows}, season=current_stats_season(), session=db.session
    )
    return jsonify(
        {
            "members": [_member_dict(row, authorized_player_ids=authorized_player_ids) for row in rows],
            "count": len(rows),
            "system_brief": _brief_dict(program.system_brief_body, program.system_brief_updated_at),
        }
    )


@club_bp.route("/club/<int:program_id>/roster", methods=["POST"])
@require_club_manager()
def add_club_roster_member(program_id: int):
    try:
        data = _payload()
        has_api = data.get("player_api_id") is not None
        has_local = data.get("local_player_id") is not None
        if has_api == has_local:
            raise ValueError("exactly one of player_api_id or local_player_id is required")

        player_api_id = None
        local_player_id = None
        if has_api:
            # This roster link grants private video/report scope only. It does
            # not confer a public affiliation or public footage attribution.
            player_api_id = _positive_int(data.get("player_api_id"), "player_api_id")
            if is_player_suppressed(player_api_id) or _tracked_player(player_api_id) is None:
                return jsonify({"error": "Player not found"}), 404
        else:
            local_player_id = _positive_int(data.get("local_player_id"), "local_player_id")
            local = db.session.get(LocalPlayer, local_player_id)
            # A manager can attach only a local identity they personally created.
            # The response is neutral for foreign, merged, rejected, or suppressed rows.
            if (
                local is None
                or local.created_by_user_id != g.user_id
                or local.status in {"rejected", "merged"}
                or local.merged_into_local_player_id is not None
            ):
                return jsonify({"error": "Player not found"}), 404
            if retained_shadow_identity_exists(
                display_name=local.display_name,
                birth_year=local.birth_year,
                api_player_id=local.api_player_id,
            ):
                return jsonify({"error": "An existing player identity needs review"}), 409
            if not _local_player_available(local):
                return jsonify({"error": "Player not found"}), 404

        signed_id = player_api_id if player_api_id is not None else -local_player_id
        if (
            ClubInvitation.query.filter_by(program_id=program_id, player_api_id=signed_id)
            .filter(ClubInvitation.responded_at.isnot(None), ClubInvitation.status.in_(["accepted", "revoked"]))
            .first()
        ):
            return jsonify({"error": "club_relationship_required"}), 409

        member = ClubRosterMember(
            program_id=program_id,
            player_api_id=player_api_id,
            local_player_id=local_player_id,
            added_by_user_id=g.user_id,
            role=_clean_optional(data.get("role"), "role", 80),
            note=_clean_optional(data.get("note"), "note", 500),
        )
        db.session.add(member)
        db.session.commit()
        return jsonify({"member": _member_dict(member)}), 201
    except ValueError as exc:
        db.session.rollback()
        return _bad_request(str(exc))
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "Player is already on this club roster"}), 409


@club_bp.route("/club/<int:program_id>/roster/<int:member_id>/brief", methods=["PUT"])
@require_club_manager()
def set_club_roster_member_brief(program_id: int, member_id: int):
    member = ClubRosterMember.query.filter_by(id=member_id, program_id=program_id).first()
    if member is None:
        return jsonify({"error": "Member not found"}), 404
    program = db.session.get(ClubProgram, program_id)
    try:
        body = _clean_brief(_payload().get("body"), program)
    except ValueError as exc:
        return _bad_request(str(exc))

    member.coach_brief_body = body
    member.brief_updated_at = datetime.now(UTC) if body is not None else None
    member.brief_updated_by_user_id = g.user_id if body is not None else None
    db.session.commit()
    return jsonify({"member": _member_dict(member)})


@club_bp.route("/club/<int:program_id>/system-brief", methods=["PUT"])
@require_club_manager()
def set_club_system_brief(program_id: int):
    program = db.session.get(ClubProgram, program_id)
    try:
        body = _clean_brief(_payload().get("body"), program)
    except ValueError as exc:
        return _bad_request(str(exc))

    program.system_brief_body = body
    program.system_brief_updated_at = datetime.now(UTC) if body is not None else None
    program.system_brief_updated_by_user_id = g.user_id if body is not None else None
    db.session.commit()
    return jsonify(
        {
            "system_brief": _brief_dict(
                program.system_brief_body,
                program.system_brief_updated_at,
            )
        }
    )


@club_bp.route("/club/<int:program_id>/roster/<int:member_id>", methods=["DELETE"])
@require_club_manager()
def delete_club_roster_member(program_id: int, member_id: int):
    member = ClubRosterMember.query.filter_by(id=member_id, program_id=program_id).first()
    if member is None:
        return jsonify({"error": "Roster member not found"}), 404
    if member.requires_player_acceptance:
        if not relationships_enabled():
            return jsonify({"error": "not_found"}), 404
        invitation = (
            db.session.get(ClubInvitation, member.accepted_invitation_id) if member.accepted_invitation_id else None
        )
        if invitation is not None:
            return _invitation_operation(
                lambda: (resolve_invitation(db.session, invitation, g.user_id, "revoke", manager=True), 200)
            )
    # A player who leaves before finalization must not acquire report access.
    VideoRosterEntry.query.filter_by(club_roster_member_id=member.id).update(
        {VideoRosterEntry.club_roster_member_id: None}, synchronize_session=False
    )
    db.session.delete(member)
    db.session.commit()
    return "", 204


@club_bp.route("/club/<int:program_id>/results", methods=["POST"])
@require_club_manager()
def record_club_result(program_id: int):
    """Upsert one fixture's club-confirmed lines.

    ``video_match_id`` is validated and echoed for this POST only. Persistence
    awaits a later ``player_match_entries.video_match_id`` column, so result
    history returns it as null.
    """
    try:
        data = _payload()
        header = _result_header_values(data)
        video_match_id = data.get("video_match_id")
        if video_match_id is not None:
            video_match_id = _positive_int(video_match_id, "video_match_id")

        requested_entries = data.get("entries")
        if not isinstance(requested_entries, list) or not requested_entries:
            raise ValueError("entries must be a non-empty list")
        parsed_entries = []
        member_ids = []
        for requested_entry in requested_entries:
            if not isinstance(requested_entry, dict):
                raise ValueError("each entry must be an object")
            member_id = _positive_int(
                requested_entry.get("club_roster_member_id"),
                "club_roster_member_id",
            )
            if member_id in member_ids:
                raise ValueError(f"duplicate club_roster_member_id {member_id}")
            member_ids.append(member_id)
            parsed_entries.append((member_id, _result_entry_values(requested_entry)))

        program = db.session.get(ClubProgram, program_id)
        if program is None:
            raise _ClubResultConflict("Club manager access denied")
        _lock_program_quota(program_id)

        if video_match_id is not None:
            video_match = (
                VideoMatch.query.filter_by(id=video_match_id, club_program_id=program_id).with_for_update().first()
            )
            if video_match is None or video_match.status not in CLUB_EDITABLE_MATCH_STATUSES:
                raise _ClubResultConflict("Video match must belong to this club program and remain editable")

        members = {
            row.id: row
            for row in ClubRosterMember.query.filter(
                ClubRosterMember.program_id == program_id,
                ClubRosterMember.id.in_(member_ids),
            )
            .with_for_update()
            .all()
        }
        if len(members) != len(member_ids):
            raise _ClubResultConflict("Every result player must belong to this club program")

        resolved_entries = []
        seen_player_ids = set()
        for member_id, values in parsed_entries:
            player_api_id, player_name, is_minor = _result_player(members[member_id])
            if player_api_id in seen_player_ids:
                raise _ClubResultConflict("Each result player may appear only once")
            seen_player_ids.add(player_api_id)
            resolved_entries.append((member_id, player_api_id, player_name, is_minor, values))

        season = current_stats_season(header["match_date"])
        _lock_result_players(seen_player_ids)
        identity_query = PlayerMatchEntry.query.filter(
            PlayerMatchEntry.match_date == header["match_date"],
            func.lower(PlayerMatchEntry.opponent) == func.lower(header["opponent"]),
            PlayerMatchEntry.source == "club",
        )
        fixture_rows = (
            identity_query.filter(PlayerMatchEntry.club_program_id == program_id)
            .order_by(PlayerMatchEntry.id)
            .with_for_update()
            .all()
        )
        foreign_rows = (
            identity_query.filter(
                PlayerMatchEntry.player_api_id.in_(seen_player_ids),
                or_(
                    PlayerMatchEntry.club_program_id.is_(None),
                    PlayerMatchEntry.club_program_id != program_id,
                ),
            )
            .order_by(PlayerMatchEntry.id)
            .all()
        )
        if foreign_rows:
            raise _ClubResultConflict("A matching result entry already belongs to another club program")

        fixture_by_player = {}
        for row in fixture_rows:
            if row.player_api_id in fixture_by_player:
                raise _ClubResultConflict(
                    "Multiple matching result entries already exist for this club program "
                    f"(player_api_id={row.player_api_id})"
                )
            fixture_by_player[row.player_api_id] = row
        existing = {
            player_api_id: row for player_api_id, row in fixture_by_player.items() if player_api_id in seen_player_ids
        }

        # This program's confirmed fixture rows retain their entry-time authority
        # after transfers, including omitted players touched by header corrections.
        established_player_ids = {row.player_api_id for row in fixture_rows if row.status == "club_confirmed"}
        players_requiring_authority = {
            player_id
            for player_id in (seen_player_ids | set(fixture_by_player)) - established_player_ids
            if player_id > 0
        }
        authorized_player_ids = club_authorized_player_ids(
            program, players_requiring_authority, season=season, session=db.session
        )
        unauthorized_player_ids = sorted(players_requiring_authority - authorized_player_ids)
        if unauthorized_player_ids:
            db.session.rollback()
            return jsonify({"error": "player_not_affiliated", "player_api_ids": unauthorized_player_ids}), 422

        for entry in fixture_rows:
            for field, value in header.items():
                setattr(entry, field, value)
            entry.season = season

        created = False
        response_rows = []
        touched_player_ids = {entry.player_api_id for entry in fixture_rows}
        for member_id, player_api_id, _player_name, _is_minor, values in resolved_entries:
            entry = existing.get(player_api_id)
            if entry is None:
                entry = PlayerMatchEntry()
                db.session.add(entry)
                created = True
                for field, value in header.items():
                    setattr(entry, field, value)
                entry.reported_by_user_id = g.user_id
            for field, value in values.items():
                setattr(entry, field, value)
            entry.player_api_id = player_api_id
            entry.season = season
            entry.source = "club"
            entry.status = "club_confirmed"
            entry.club_program_id = program_id
            response_rows.append((entry, member_id))
            touched_player_ids.add(player_api_id)

        try:
            db.session.flush()
        except IntegrityError:
            raise _ClubResultConflict("Club result conflicts with an existing entry") from None

        for player_api_id in sorted(touched_player_ids):
            season_rollup_service.refresh_player(
                player_api_id,
                season,
                session=db.session,
            )

        level_group = "youth" if season_rollup_service._is_youth_competition(header["competition"]) else "senior"
        season_stats_by_player = {}
        for member_id, player_api_id, player_name, is_minor, _values in resolved_entries:
            stats = _club_season_stats(
                player_api_id,
                season,
                level_group,
                member_id,
                player_name,
                is_minor,
            )
            if stats is not None:
                season_stats_by_player[str(player_api_id)] = stats
        matches = [_result_entry_dict(entry, member_id) for entry, member_id in response_rows]
        db.session.commit()
        return (
            jsonify(
                {
                    "result": _normalized_result(header, video_match_id),
                    "matches": matches,
                    "season_stats_by_player": season_stats_by_player,
                }
            ),
            201 if created else 200,
        )
    except ValueError as exc:
        db.session.rollback()
        return _bad_request(str(exc))
    except _ClubResultConflict as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 409
    except Exception:
        db.session.rollback()
        logger.exception("Failed to record club result for program %s", program_id)
        return jsonify({"error": "Failed to record club result"}), 500


@club_bp.route("/club/<int:program_id>/results", methods=["GET"])
@require_club_manager()
def list_club_results(program_id: int):
    try:
        season = request.args.get("season")
        if season is not None:
            try:
                season = int(season)
            except (TypeError, ValueError):
                raise ValueError("season must be an integer") from None

        query = PlayerMatchEntry.query.filter_by(
            club_program_id=program_id,
            source="club",
            status="club_confirmed",
        )
        if season is not None:
            query = query.filter(PlayerMatchEntry.season == season)
        rows = query.order_by(PlayerMatchEntry.match_date.desc(), PlayerMatchEntry.id.desc()).all()

        member_id_by_player = {}
        for member in ClubRosterMember.query.filter_by(program_id=program_id).all():
            player_api_id = member.player_api_id if member.player_api_id is not None else -member.local_player_id
            member_id_by_player[player_api_id] = member.id

        grouped = {}
        for entry in rows:
            key = (
                entry.season,
                entry.match_date,
                entry.opponent.lower(),
            )
            group = grouped.get(key)
            if group is None:
                header = {
                    "match_date": entry.match_date,
                    "opponent": entry.opponent,
                    "competition": entry.competition,
                    "home_away": entry.home_away,
                    "result_for": entry.result_for,
                    "result_against": entry.result_against,
                }
                group = {
                    "result": _normalized_result(header, None),
                    "matches": [],
                }
                grouped[key] = group
            group["matches"].append(_result_entry_dict(entry, member_id_by_player.get(entry.player_api_id)))
        results = list(grouped.values())
        return jsonify({"results": results, "total": len(results)})
    except ValueError as exc:
        return _bad_request(str(exc))
    except Exception:
        logger.exception("Failed to list club results for program %s", program_id)
        return jsonify({"error": "Failed to load club results"}), 500


@club_bp.route("/club/<int:program_id>/matches", methods=["POST"])
@require_club_manager()
def create_club_match(program_id: int):
    try:
        data = _payload()
        capture_meta = _capture_meta(data.get("capture_meta"))
        capture_meta = merge_preflight(capture_meta, capture_meta or {})
        capture_meta = merge_preflight(capture_meta, data)
        program = db.session.get(ClubProgram, program_id)
        if program is None:
            return jsonify({"error": "Club manager access denied"}), 403

        _lock_program_quota(program_id)
        used = db.session.query(func.count(VideoMatch.id)).filter(VideoMatch.club_program_id == program_id).scalar()
        quota = _quota()
        if used >= quota:
            db.session.rollback()
            return (
                jsonify({"error": f"Club match quota reached ({quota})", "quota": quota}),
                429,
            )

        values = {field: _clean_optional(data.get(field), field, limit) for field, limit in TEXT_LIMITS.items()}
        match = VideoMatch(
            team_id=_resolve_team_id(program),
            club_program_id=program_id,
            match_date=_match_date(data.get("match_date")),
            capture_meta=capture_meta,
            status="created",
            **values,
        )
        db.session.add(match)
        db.session.flush()
        match.blob_path = f"matches/{match.id}/{uuid.uuid4().hex}.mp4"
        db.session.commit()
        out = match.to_dict()
        if video_storage.is_configured():
            out["upload"] = video_storage.mint_upload_sas(match.blob_path)
        else:
            out["upload"] = None
            out["upload_unavailable"] = "blob storage not configured"
        return jsonify(out), 201
    except ValueError as exc:
        db.session.rollback()
        return _bad_request(str(exc))


@club_bp.route("/club/<int:program_id>/matches", methods=["GET"])
@require_club_manager()
def list_club_matches(program_id: int):
    """List one program's matches, newest first. Quota caps a program at MAX_MATCH_QUOTA rows, so no paging."""
    rows = (
        VideoMatch.query.filter_by(club_program_id=program_id)
        .order_by(VideoMatch.created_at.desc(), VideoMatch.id.desc())
        .all()
    )
    matches = []
    for match in rows:
        out = match.to_dict(include_job=True)
        out["processing_request_status"] = "requested" if match.processing_requested_at else None
        matches.append(out)
    return jsonify({"matches": matches, "total": len(matches)})


@club_bp.route("/club/<int:program_id>/matches/<int:match_id>/sas", methods=["POST"])
@require_club_manager()
def club_match_sas(program_id: int, match_id: int):
    match = _club_match(program_id, match_id)
    if match is None:
        return jsonify({"error": "Match not found"}), 404
    if match.status not in {"created", "uploaded"}:
        return _bad_request(f"cannot re-mint SAS in status '{match.status}'")
    if not video_retention.can_issue_upload_grant(match):
        return jsonify({"error": "retention deadline too close to issue an upload grant; create a new match"}), 409
    if not video_storage.is_configured():
        return jsonify({"error": "blob storage not configured"}), 503
    return jsonify(video_storage.mint_upload_sas(match.blob_path))


@club_bp.route("/club/<int:program_id>/matches/<int:match_id>/upload-complete", methods=["POST"])
@require_club_manager()
def club_match_upload_complete(program_id: int, match_id: int):
    match = _club_match(program_id, match_id)
    if match is None:
        return jsonify({"error": "Match not found"}), 404
    # Serialize with the retention sweeper: it re-checks this row under the same lock before deleting footage.
    db.session.refresh(match, with_for_update=True)
    if match.status not in {"created", "uploaded"}:
        return _bad_request(f"cannot complete upload in status '{match.status}'")
    if video_retention.retention_window_closed(match):
        return jsonify({"error": "retention window closed; the footage is due for deletion"}), 409
    if not video_storage.is_configured():
        return jsonify({"error": "blob storage not configured"}), 503
    is_reattestation = match.status == "uploaded"
    check = video_storage.verify_uploaded_blob(match.blob_path)
    if not check["ok"]:
        return jsonify({"error": check["error"]}), 422
    # TODO(C2 follow-up): validate media signatures/container with ffprobe during admin processing.
    try:
        data = _payload()
        for field in ("kickoff_s", "halftime_s", "second_half_kickoff_s", "duration_s"):
            if field in data:
                setattr(match, field, _timeline_value(data[field], field))
    except ValueError as exc:
        return _bad_request(str(exc))
    now = datetime.now(UTC)
    match.blob_etag = check["etag"]
    match.status = "uploaded"
    match.uploaded_at = now
    if match.expires_at is None:  # first completion stamps the deadline; a reattestation keeps the original one
        match.expires_at = now + timedelta(days=RAW_RETENTION_DAYS)
    if is_reattestation:
        match.processing_requested_at = None
        match.processing_requested_by_user_id = None
    db.session.commit()
    return jsonify(match.to_dict() | {"size_bytes": check["size_bytes"]})


@club_bp.route("/club/<int:program_id>/matches/<int:match_id>", methods=["PATCH"])
@require_club_manager()
def update_club_match(program_id: int, match_id: int):
    match = _club_match(program_id, match_id)
    if match is None:
        return jsonify({"error": "Match not found"}), 404
    if match.status not in CLUB_EDITABLE_MATCH_STATUSES:
        return _bad_request(f"cannot edit match in status '{match.status}'")
    try:
        data = _payload()
        for field, limit in TEXT_LIMITS.items():
            if field in data:
                setattr(match, field, _clean_optional(data[field], field, limit))
        if "match_date" in data:
            match.match_date = _match_date(data["match_date"])
        for field in ("kickoff_s", "halftime_s", "second_half_kickoff_s", "duration_s"):
            if field in data:
                setattr(match, field, _timeline_value(data[field], field))
        if "capture_meta" in data:
            incoming_meta = _capture_meta(data["capture_meta"])
            match.capture_meta = merge_preflight(match.capture_meta, incoming_meta or {})
        match.capture_meta = merge_preflight(match.capture_meta, data)
    except ValueError as exc:
        return _bad_request(str(exc))
    db.session.commit()
    return jsonify(match.to_dict())


@club_bp.route("/club/<int:program_id>/matches/<int:match_id>", methods=["GET"])
@require_club_manager()
def get_club_match(program_id: int, match_id: int):
    match = _club_match(program_id, match_id)
    if match is None:
        return jsonify({"error": "Match not found"}), 404
    out = match.to_dict(include_job=True)
    out["roster"] = [
        entry.to_dict()
        for entry in match.roster_entries
        if entry.club_roster_member_id is not None
        and (member := db.session.get(ClubRosterMember, entry.club_roster_member_id)) is not None
        and member.program_id == program_id
        and _member_subject(member)[0] is not None
    ]
    out["processing_request_status"] = "requested" if match.processing_requested_at else None
    return jsonify(out)


@club_bp.route("/club/<int:program_id>/matches/<int:match_id>/media-token", methods=["GET"])
@require_club_manager()
def get_club_match_media_token(program_id: int, match_id: int):
    match = _club_match(program_id, match_id)
    if match is None:
        return jsonify({"error": "Match not found"}), 404
    return jsonify(
        mint_media_token(
            match.id,
            email=getattr(g, "user_email", None),
            club_program_id=program_id,
        )
    )


@club_bp.route("/club/<int:program_id>/matches/<int:match_id>/reel", methods=["GET"])
@require_club_manager()
def get_club_match_reel(program_id: int, match_id: int):
    match = _club_match(program_id, match_id)
    if match is None:
        return jsonify({"error": "Match not found"}), 404

    # A club sees only identities still available through its own roster
    # boundary. This mirrors the report's suppression/detachment posture while
    # retaining private minor rows for their own verified manager.
    visible_roster_entries = []
    for entry in match.roster_entries:
        member = (
            ClubRosterMember.query.filter_by(
                id=entry.club_roster_member_id,
                program_id=program_id,
            ).first()
            if entry.club_roster_member_id is not None
            else None
        )
        if member is not None and _member_subject(member)[0] is not None:
            visible_roster_entries.append(entry)

    # Imported lazily to keep the club blueprint independent of registration
    # order while sharing the exact admin reel loader and aggregation service.
    from src.routes.video import _reel_payload

    return jsonify(_reel_payload(match, visible_roster_entries))


@club_bp.route("/club/<int:program_id>/matches/<int:match_id>/roster", methods=["PUT"])
@require_club_manager()
def set_club_match_roster(program_id: int, match_id: int):
    match = _club_match(program_id, match_id)
    if match is None:
        return jsonify({"error": "Match not found"}), 404
    if match.status not in CLUB_EDITABLE_MATCH_STATUSES:
        return _bad_request(f"cannot edit roster in status '{match.status}'")
    try:
        entries = _payload().get("entries")
        if not isinstance(entries, list) or not entries:
            raise ValueError("entries must be a non-empty list")
        member_ids: list[int] = []
        seen_numbers: set[int] = set()
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("each entry must be an object")
            member_id = _positive_int(entry.get("club_roster_member_id"), "club_roster_member_id")
            number = entry.get("jersey_number")
            if isinstance(number, bool) or not isinstance(number, int) or not 1 <= number <= 99:
                raise ValueError("each entry needs jersey_number 1-99")
            if member_id in member_ids:
                raise ValueError(f"duplicate club_roster_member_id {member_id}")
            if number in seen_numbers:
                raise ValueError(f"duplicate jersey_number {number}")
            member_ids.append(member_id)
            seen_numbers.add(number)

        members = {
            row.id: row
            for row in ClubRosterMember.query.filter(
                ClubRosterMember.program_id == program_id,
                ClubRosterMember.id.in_(member_ids),
            )
        }
        if len(members) != len(member_ids):
            return _bad_request("every match player must be on this club roster")

        resolved = {}
        for member_id, member in members.items():
            subject, model = _member_subject(member)
            if subject is None:
                return _bad_request("every match player must be an available club roster member")
            resolved[member_id] = (subject, model)

        existing = {row.jersey_number: row for row in match.roster_entries}
        kept_numbers: set[int] = set()
        for payload_entry in entries:
            number = payload_entry["jersey_number"]
            member_id = payload_entry["club_roster_member_id"]
            subject, model = resolved[member_id]
            row = existing.get(number)
            if row is None:
                row = VideoRosterEntry(video_match_id=match.id, jersey_number=number)
                db.session.add(row)
            row.player_name = subject["display_name"]
            row.position = subject["position"]
            row.club_roster_member_id = member_id
            row.tracked_player_id = model.id if isinstance(model, TrackedPlayer) else None
            kept_numbers.add(number)

        removed = 0
        for number, row in existing.items():
            if number not in kept_numbers:
                VideoTracklet.query.filter_by(roster_entry_id=row.id).update(
                    {VideoTracklet.roster_entry_id: None, VideoTracklet.tag_source: None},
                    synchronize_session=False,
                )
                VideoPlayerReport.query.filter_by(roster_entry_id=row.id).delete(synchronize_session=False)
                db.session.delete(row)
                removed += 1
        db.session.commit()
        return jsonify({"roster": [row.to_dict() for row in match.roster_entries], "removed": removed})
    except ValueError as exc:
        db.session.rollback()
        return _bad_request(str(exc))


@club_bp.route("/club/<int:program_id>/matches/<int:match_id>/process", methods=["POST"])
@require_club_manager()
def request_club_match_processing(program_id: int, match_id: int):
    """Record a request only; no GPU job, tag access, or state transition."""
    match = _club_match(program_id, match_id)
    if match is None:
        return jsonify({"error": "Match not found"}), 404
    if match.status != "uploaded":
        return _bad_request(f"cannot request processing in status '{match.status}' (upload first)")
    if match.kickoff_s is None:
        return _bad_request("kickoff_s must be marked before requesting processing")
    integrity = video_storage.verify_expected_blob(match.blob_path, match.blob_etag)
    if not integrity["ok"]:
        return jsonify({"error": integrity["error"]}), 422
    if match.processing_requested_at is None:
        match.processing_requested_at = datetime.now(UTC)
        match.processing_requested_by_user_id = g.user_id
        db.session.commit()
    return jsonify({"processing_request_status": "requested", "match": match.to_dict()}), 202


@club_bp.route("/club/<int:program_id>/matches/<int:match_id>/report", methods=["GET"])
@require_club_manager()
def get_club_match_report(program_id: int, match_id: int):
    match = _club_match(program_id, match_id)
    if match is None:
        return jsonify({"error": "Match not found"}), 404
    if match.status != "finalized":
        return jsonify({"error": "Report is not finalized"}), 409

    reports = VideoPlayerReport.query.filter_by(
        video_match_id=match.id,
        club_program_id_at_finalize=program_id,
    ).all()
    roster_by_id = {row.id: row for row in match.roster_entries}
    visible = []
    for report in reports:
        # Governed snapshots require a current member; historical result rows stay intact.
        signed_id = report.club_player_api_id_at_finalize or (
            -report.club_local_player_id_at_finalize if report.club_local_player_id_at_finalize else None
        )
        governed_history = (
            ClubInvitation.query.filter_by(program_id=program_id, player_api_id=signed_id)
            .filter(ClubInvitation.responded_at.isnot(None), ClubInvitation.status.in_(["accepted", "revoked"]))
            .first()
            if signed_id
            else None
        )
        entry = roster_by_id.get(report.roster_entry_id)
        member = (
            db.session.get(ClubRosterMember, entry.club_roster_member_id)
            if entry and entry.club_roster_member_id
            else None
        )
        if governed_history and (
            member is None
            or member.program_id != program_id
            or not member.requires_player_acceptance
            or not governed_member_available(db.session, member)
        ):
            continue
        if member and not governed_member_available(db.session, member):
            continue
        subject = None
        if report.club_player_api_id_at_finalize is not None:
            if is_player_suppressed(report.club_player_api_id_at_finalize):
                continue
            subject = {
                "subject_type": "tracked",
                "player_api_id": report.club_player_api_id_at_finalize,
                "local_player_id": None,
                "is_minor": False,
            }
        elif report.club_local_player_id_at_finalize is not None:
            local = db.session.get(LocalPlayer, report.club_local_player_id_at_finalize)
            if not _local_player_available(local):
                continue
            subject = {
                "subject_type": "local",
                "player_api_id": None,
                "local_player_id": local.id,
                "is_minor": local_player_is_minor(local),
            }
        if subject is None:
            continue
        row = report.to_dict()
        entry = roster_by_id.get(report.roster_entry_id)
        row["player_name"] = entry.player_name if entry else None
        row["jersey_number"] = entry.jersey_number if entry else None
        row["subject"] = subject
        visible.append(row)
    visible.sort(key=lambda row: -(row["minutes_visible"] or 0))
    return jsonify({"match": match.to_dict(), "reports": visible})


@club_bp.after_request
def _private_invitation_response(response):
    if "/invitations" in request.path:
        response.headers["Cache-Control"] = "private, no-store"
    return response


def _require_relationships(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not relationships_enabled():
            return jsonify({"error": "not_found"}), 404
        return view(*args, **kwargs)

    return wrapped


def _invitation_limit_key():
    return f"{getattr(g, 'user_id', 'anon')}:{(request.view_args or {}).get('program_id', '')}"


def _invitation_rate_rejected(limit):
    import time

    response = jsonify({"error": "rate_limit_exceeded"})
    response.status_code = 429
    response.headers["Retry-After"] = str(max(1, math.ceil(limit.reset_at - time.time())))
    response.headers["Cache-Control"] = "private, no-store"
    return response


def _invitation_operation(operation, *, share=False):
    try:
        invitation, status = operation()
        db.session.flush()
        payload = {"invitation": invitation_dict(db.session, invitation)}
        if share:
            payload["share_path"] = f"/players/{invitation.player_api_id}#club-invitation={invitation.id}"
        expired = invitation.status == "expired" and not share
        db.session.commit()
        if expired:
            return jsonify({"error": "invitation_expired"}), 409
        return jsonify(payload), status
    except InvitationError as error:
        db.session.rollback()
        return jsonify({"error": error.code}), error.status
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "retry_conflict"}), 409
    except SQLAlchemyError as error:
        return _invitation_database_error(error)
    except Exception as error:
        db.session.rollback()
        logger.error("Invitation operation failed (%s)", type(error).__name__)
        return jsonify({"error": "invitation_operation_failed"}), 500


def _invitation_database_error(error):
    db.session.rollback()
    code = getattr(getattr(error, "orig", None), "sqlstate", None)
    if code in {"40001", "40P01"}:
        return jsonify({"error": "retry_conflict"}), 409
    logger.error("Invitation transaction failed (%s)", type(error).__name__)
    return jsonify({"error": "invitation_operation_failed"}), 500


def _invitation_list_response(**scope):
    try:
        if set(request.args) - {"limit", "before", "player_api_id"} or any(
            len(request.args.getlist(key)) != 1 for key in request.args
        ):
            raise InvitationError("invalid_request", 400)
        limit = int(request.args.get("limit", "20"))
        signed_id = int(request.args["player_api_id"]) if "player_api_id" in request.args else None
        result = list_invitations(
            db.session, **scope, player_api_id=signed_id, limit=limit, before=request.args.get("before")
        )
        return jsonify(result)
    except (ValueError, InvitationError) as error:
        return jsonify(
            {"error": error.code if isinstance(error, InvitationError) else "invalid_request"}
        ), error.status if isinstance(error, InvitationError) else 400

    except SQLAlchemyError as error:
        return _invitation_database_error(error)


@club_bp.route("/club/<int:program_id>/invitations", methods=["POST"])
@require_club_manager()
@_require_relationships
@limiter.limit("20 per hour", key_func=_invitation_limit_key, on_breach=_invitation_rate_rejected)
def create_club_invitation(program_id):
    return _invitation_operation(
        lambda: create_invitation(db.session, program_id, g.user_id, request.get_json(silent=True)), share=True
    )


@club_bp.route("/club/<int:program_id>/invitations", methods=["GET"])
@require_club_manager()
@_require_relationships
@limiter.limit("60 per minute", key_func=_invitation_limit_key, on_breach=_invitation_rate_rejected)
def list_club_invitations(program_id):
    return _invitation_list_response(program_id=program_id)


@club_bp.route("/club/<int:program_id>/invitations/<uuid:invitation_id>/revoke", methods=["POST"])
@require_club_manager()
@_require_relationships
@limiter.limit("30 per hour", key_func=_invitation_limit_key, on_breach=_invitation_rate_rejected)
def revoke_club_invitation(program_id, invitation_id):
    if request.get_json(silent=True) != {}:
        return jsonify({"error": "invalid_request"}), 400
    invitation = ClubInvitation.query.filter_by(id=str(invitation_id), program_id=program_id).first()
    if invitation is None:
        return jsonify({"error": "invitation_not_found"}), 404
    return _invitation_operation(
        lambda: (resolve_invitation(db.session, invitation, g.user_id, "revoke", manager=True), 200)
    )
