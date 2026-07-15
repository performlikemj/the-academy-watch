"""Follow resolver — turn a FollowList's heterogeneous follows into a player set.

A list resolves to an ordered, deduped list of ``{player_api_id, source}`` where
source is ``tracked`` (an active academy/loan TrackedPlayer) or ``shadow`` (a
worldwide PlayerShadow). Per-kind resolution reuses the scout blueprint's base
query (``_base_scout_query``) so the owning-club exclusion, preferred-row
de-duplication, and is_active filters stay identical to the scout hub.

Selector validation is strict (unknown keys rejected) and lives here so both the
follows endpoint (create-time) and the resolver share one source of truth.
"""

import logging

from src.models.follow import Follow, PlayerShadow
from src.models.tracked_player import TrackedPlayer

logger = logging.getLogger(__name__)

FOLLOW_KINDS = ("player", "academy_club", "geo", "query")
GEO_MATCH_MODES = ("playing_in", "nationality")
MAX_GEO_COUNTRIES = 10
MAX_COUNTRY_LEN = 50
QUERY_ARG_KEYS = ("position", "status", "min_age", "max_age", "nationality", "min_minutes")

# A ``query`` follow is capped tighter than a whole list (a saved filter can match
# a very large slice); geo/academy contributions get a generous safety cap so a
# single country follow can't try to load the entire tracked universe into memory.
QUERY_FOLLOW_CAP = 100
MAX_RESOLVE_PER_FOLLOW = 500


# --------------------------------------------------------------------------- #
# Selector validation
# --------------------------------------------------------------------------- #


def _positive_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _non_negative_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def validate_selector(kind: str, selector) -> tuple[dict | None, str | None]:
    """Return (clean_selector, error). error is a user-facing 400 message."""
    if kind not in FOLLOW_KINDS:
        return None, f"Unknown follow kind '{kind}'. One of: {sorted(FOLLOW_KINDS)}"
    if not isinstance(selector, dict):
        return None, "selector must be an object"
    if kind == "player":
        return _validate_player(selector)
    if kind == "academy_club":
        return _validate_academy_club(selector)
    if kind == "geo":
        return _validate_geo(selector)
    return _validate_query(selector)


def _validate_player(selector: dict):
    extra = set(selector) - {"player_api_id"}
    if extra:
        return None, f"unexpected keys for player selector: {sorted(extra)}"
    pid = selector.get("player_api_id")
    if not _positive_int(pid):
        return None, "player_api_id must be a positive integer"
    return {"player_api_id": int(pid)}, None


def _validate_academy_club(selector: dict):
    extra = set(selector) - {"team_id", "program_id"}
    if extra:
        return None, f"unexpected keys for academy_club selector: {sorted(extra)}"
    if ("team_id" in selector) == ("program_id" in selector):
        return None, "academy_club selector must contain exactly one of team_id or program_id"
    if "program_id" in selector:
        program_id = selector.get("program_id")
        if not _positive_int(program_id):
            return None, "program_id must be a positive integer"
        return {"program_id": int(program_id)}, None
    team_id = selector.get("team_id")
    if not _positive_int(team_id):
        return None, "team_id must be a positive integer (internal teams.id)"
    return {"team_id": int(team_id)}, None


def _validate_geo(selector: dict):
    extra = set(selector) - {"countries", "match"}
    if extra:
        return None, f"unexpected keys for geo selector: {sorted(extra)}"
    countries = selector.get("countries")
    if not isinstance(countries, list) or not (1 <= len(countries) <= MAX_GEO_COUNTRIES):
        return None, f"countries must be a list of 1..{MAX_GEO_COUNTRIES} strings"
    clean = []
    for country in countries:
        if not isinstance(country, str):
            return None, "each country must be a string"
        trimmed = country.strip()
        if not trimmed or len(trimmed) > MAX_COUNTRY_LEN:
            return None, f"each country must be 1..{MAX_COUNTRY_LEN} characters"
        # Preserve the user's casing (str.title() corrupts "Bosnia and
        # Herzegovina" → "Bosnia And Herzegovina"); matching is case-insensitive.
        clean.append(trimmed)
    match = selector.get("match", "playing_in")
    if match not in GEO_MATCH_MODES:
        return None, f"match must be one of {list(GEO_MATCH_MODES)}"
    deduped = list(dict.fromkeys(clean))
    return {"countries": deduped, "match": match}, None


def _validate_query(selector: dict):
    from src.routes.scout import VALID_POSITIONS, VALID_STATUSES

    extra = set(selector) - {"scout_args"}
    if extra:
        return None, f"unexpected keys for query selector: {sorted(extra)}"
    scout_args = selector.get("scout_args")
    if not isinstance(scout_args, dict):
        return None, "scout_args must be an object"
    bad = set(scout_args) - set(QUERY_ARG_KEYS)
    if bad:
        return None, f"unexpected scout_args keys: {sorted(bad)}"

    clean: dict = {}
    if "position" in scout_args:
        position = scout_args["position"]
        if position not in VALID_POSITIONS:
            return None, f"Invalid position. One of: {sorted(VALID_POSITIONS)}"
        clean["position"] = position
    if "status" in scout_args:
        status = scout_args["status"]
        statuses = [status] if isinstance(status, str) else status
        if not isinstance(statuses, list) or not statuses:
            return None, "status must be a string or non-empty list"
        for value in statuses:
            if value not in VALID_STATUSES:
                return None, f"Invalid status {value}. One of: {sorted(VALID_STATUSES)}"
        clean["status"] = list(statuses)
    for key in ("min_age", "max_age", "min_minutes"):
        if key in scout_args:
            value = scout_args[key]
            if not _non_negative_int(value):
                return None, f"{key} must be a non-negative integer"
            clean[key] = int(value)
    if "nationality" in scout_args:
        nationality = scout_args["nationality"]
        if not isinstance(nationality, str) or not nationality.strip():
            return None, "nationality must be a non-empty string"
        clean["nationality"] = nationality.strip()
    if not clean:
        return None, "scout_args must include at least one filter"
    return {"scout_args": clean}, None


def derive_label(kind: str, selector: dict, name: str | None = None) -> str:
    """Server-derived display label for a follow.

    ``name`` is the resolved player/team name (passed by callers that resolve it
    at read time); when absent a stable id-based placeholder is used.
    """
    if kind == "player":
        return (name or f"Player {selector.get('player_api_id')}")[:160]
    if kind == "academy_club":
        if selector.get("program_id"):
            return (f"Club program: {name}" if name else f"Club program #{selector.get('program_id')}")[:160]
        return (f"Club academy: {name}" if name else f"Club academy #{selector.get('team_id')}")[:160]
    if kind == "geo":
        countries = ", ".join(selector.get("countries", []))
        prefix = "Nationality" if selector.get("match") == "nationality" else "Playing in"
        return f"{prefix}: {countries}"[:160]
    scout_args = selector.get("scout_args", {})
    parts = []
    if scout_args.get("position"):
        parts.append(scout_args["position"])
    if scout_args.get("status"):
        parts.append("/".join(scout_args["status"]))
    if scout_args.get("nationality"):
        parts.append(scout_args["nationality"])
    if scout_args.get("min_age") is not None or scout_args.get("max_age") is not None:
        parts.append(f"age {scout_args.get('min_age', '')}-{scout_args.get('max_age', '')}")
    if scout_args.get("min_minutes"):
        parts.append(f"{scout_args['min_minutes']}+ mins")
    return ("Filter: " + ", ".join(parts))[:160] if parts else "Filter"


# --------------------------------------------------------------------------- #
# Resolution
# --------------------------------------------------------------------------- #


def _resolve_player(selector: dict) -> list[tuple[int, str]]:
    pid = selector.get("player_api_id")
    if not pid:
        return []
    tracked = (
        TrackedPlayer.query.filter_by(player_api_id=pid, is_active=True)
        .filter(TrackedPlayer.data_source != "owning-club")
        .first()
    )
    if tracked:
        return [(pid, "tracked")]
    shadow = PlayerShadow.query.filter_by(player_api_id=pid, is_active=True).first()
    if shadow:
        return [(pid, "shadow")]
    return []


def _resolve_academy_club(selector: dict, limit: int | None) -> list[tuple[int, str]]:
    from src.routes.scout import _base_scout_query

    # A saved future-funding program is an expansion-demand/notification
    # signal only. It must never resolve players or affect digest/ranking.
    if selector.get("program_id"):
        return []
    team_id = selector.get("team_id")
    if not team_id:
        return []
    query, _ = _base_scout_query()
    query = query.filter(TrackedPlayer.team_id == team_id)
    cap = min(limit or MAX_RESOLVE_PER_FOLLOW, MAX_RESOLVE_PER_FOLLOW)
    rows = query.order_by(TrackedPlayer.id).limit(cap).all()
    return [(row[0].player_api_id, "tracked") for row in rows]


def _resolve_geo(selector: dict, limit: int | None) -> list[tuple[int, str]]:
    from sqlalchemy import func
    from sqlalchemy.orm import aliased
    from src.models.league import Team
    from src.routes.scout import _base_scout_query

    countries = selector.get("countries") or []
    if not countries:
        return []
    match = selector.get("match") or "playing_in"
    lowered = [c.lower() for c in countries]
    query, _ = _base_scout_query()
    if match == "nationality":
        query = query.filter(func.lower(TrackedPlayer.nationality).in_(lowered))
    else:
        # current_club_db_id is nullable; the inner join naturally drops players
        # with no resolved current club (correct for "players playing in X").
        current_club = aliased(Team)
        query = query.join(current_club, current_club.id == TrackedPlayer.current_club_db_id).filter(
            func.lower(current_club.country).in_(lowered)
        )
    cap = min(limit or MAX_RESOLVE_PER_FOLLOW, MAX_RESOLVE_PER_FOLLOW)
    rows = query.order_by(TrackedPlayer.id).limit(cap).all()
    return [(row[0].player_api_id, "tracked") for row in rows]


def _resolve_query(selector: dict, limit: int | None) -> list[tuple[int, str]]:
    from src.routes.scout import _age_expression, _base_scout_query

    scout_args = selector.get("scout_args") or {}
    query, columns = _base_scout_query()

    if scout_args.get("position"):
        query = query.filter(TrackedPlayer.position == scout_args["position"])
    if scout_args.get("status"):
        query = query.filter(columns["effective_status"].in_(scout_args["status"]))
    min_age = scout_args.get("min_age")
    max_age = scout_args.get("max_age")
    if min_age is not None or max_age is not None:
        age_expr = _age_expression()
        if min_age is not None:
            query = query.filter(age_expr >= min_age)
        if max_age is not None:
            query = query.filter(age_expr <= max_age)
    if scout_args.get("nationality"):
        query = query.filter(TrackedPlayer.nationality.ilike(f"%{scout_args['nationality']}%"))
    if scout_args.get("min_minutes"):
        query = query.filter(columns["minutes_played"] >= scout_args["min_minutes"])

    cap = min(limit or QUERY_FOLLOW_CAP, QUERY_FOLLOW_CAP)
    rows = query.order_by(TrackedPlayer.id).limit(cap).all()
    return [(row[0].player_api_id, "tracked") for row in rows]


def resolve_list(follow_list, limit: int | None = None) -> list[dict]:
    """Ordered, deduped [{player_api_id, source}] for a FollowList.

    Follows are resolved in creation order; the first follow to yield a player
    wins (later duplicates are dropped). ``limit`` caps the returned set (the
    digest passes ``list.player_cap``; the resolve endpoint paginates the full
    set by passing None).
    """
    follows = follow_list.follows.order_by(Follow.created_at.asc(), Follow.id.asc()).all()
    seen: set[int] = set()
    result: list[dict] = []
    for follow in follows:
        selector = follow.selector or {}
        try:
            if follow.kind == "player":
                pairs = _resolve_player(selector)
            elif follow.kind == "academy_club":
                pairs = _resolve_academy_club(selector, limit)
            elif follow.kind == "geo":
                pairs = _resolve_geo(selector, limit)
            elif follow.kind == "query":
                pairs = _resolve_query(selector, limit)
            else:
                pairs = []
        except Exception:
            logger.exception("Follow resolution failed for follow %s (kind=%s)", follow.id, follow.kind)
            pairs = []
        for pid, source in pairs:
            if pid in seen:
                continue
            seen.add(pid)
            result.append({"player_api_id": pid, "source": source})
            if limit is not None and len(result) >= limit:
                return result
    return result
