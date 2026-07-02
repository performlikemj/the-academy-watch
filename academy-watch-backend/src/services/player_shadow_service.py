"""Shadow player service — worldwide tracking without league crawling.

Following a player outside the tracked universe mints a lightweight
``PlayerShadow`` (profile) plus per-season ``PlayerShadowStats``, giving that
player a working profile/season-stats page. Discovery is a single worldwide
``players/profiles`` name search; refresh is an operator-paced, quota-capped
batch.

Client injection everywhere (test-safety): every function takes
``api_client=None`` and resolves the shared singleton lazily. Never construct
APIFootballClient directly. In stub mode the profiles endpoint returns
``{"response": []}`` so mint falls back to its seed, search returns [], and
refresh no-ops — none of these paths raise.
"""

import logging
from datetime import UTC, date, datetime, timedelta

from src.models.follow import PlayerShadow, PlayerShadowStats
from src.models.league import db
from src.models.tracked_player import TrackedPlayer
from src.utils.sanitize import is_safe_https_url, sanitize_plain_text

logger = logging.getLogger(__name__)

SHADOW_PROFILE_STALE_DAYS = 7
MAX_SEARCH_RESULTS = 10


def _get_api_client():
    from src.routes.api import api_client

    return api_client


def _resolve_client(api_client):
    return api_client if api_client is not None else _get_api_client()


def _parse_birth_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


def _as_naive(value):
    """Normalize a datetime to naive UTC so aware/naive comparisons never raise
    (SQLite reads stored datetimes back as naive)."""
    if value is not None and value.tzinfo is not None:
        return value.replace(tzinfo=None)
    return value


def _current_season_start_year(client=None) -> int:
    year = getattr(client, "current_season_start_year", None)
    if isinstance(year, int):
        return year
    now = datetime.now(UTC)
    return now.year if now.month >= 8 else now.year - 1


# --------------------------------------------------------------------------- #
# Mint
# --------------------------------------------------------------------------- #


def _clean_seed(seed):
    """Sanitize the attacker-controlled seed dict from the follow payload."""
    if not isinstance(seed, dict):
        return {}
    cleaned = {}
    for key in ("name", "position", "nationality", "club_name"):
        value = seed.get(key)
        if isinstance(value, str) and value.strip():
            text = sanitize_plain_text(value).strip()
            if text:
                cleaned[key] = text
    photo = seed.get("photo")
    if isinstance(photo, str) and is_safe_https_url(photo):
        cleaned["photo"] = photo
    club_api_id = seed.get("club_api_id")
    if isinstance(club_api_id, int) and club_api_id > 0:
        cleaned["club_api_id"] = club_api_id
    return cleaned


def mint_shadow(player_api_id, seed=None, requested_by=None, api_client=None):
    """Get-or-create the PlayerShadow for ``player_api_id``.

    The profile comes from ``players/profiles``; on any error (or stub mode) it
    falls back to the ``seed`` fields carried by the search result so the mint
    always succeeds offline.
    """
    existing = PlayerShadow.query.filter_by(player_api_id=player_api_id).first()
    if existing:
        if not existing.is_active:
            existing.is_active = True
        # Re-follow churn guard: refresh the profile only when it is stale
        # (>7d), so unfollow/refollow spam costs zero upstream calls (on top of
        # the DB api_cache) for a shadow that was just synced.
        last_profile = _as_naive(existing.last_profile_sync_at)
        stale_before = _as_naive(datetime.now(UTC)) - timedelta(days=SHADOW_PROFILE_STALE_DAYS)
        if last_profile is None or last_profile < stale_before:
            if _refresh_profile(_resolve_client(api_client), existing):
                existing.last_profile_sync_at = datetime.now(UTC)
        return existing

    client = _resolve_client(api_client)
    profile = {}
    try:
        profile = client.get_player_profile(player_api_id) or {}
    except Exception:
        logger.warning("Shadow profile fetch failed for %s; falling back to seed", player_api_id)
        profile = {}

    info = (profile.get("player") if isinstance(profile, dict) else None) or {}
    # Seed values are ATTACKER-CONTROLLED request payload (the search result the
    # frontend echoes back) — bleach-clean every text field and https-validate
    # the photo URL before they land on a globally-shared row. API-sourced
    # values win over seed values wherever both exist.
    seed = _clean_seed(seed)
    name = (info.get("name") or seed.get("name") or f"Player {player_api_id}").strip() or f"Player {player_api_id}"

    def _clip(value, length):
        return str(value)[:length] if value else None

    shadow = PlayerShadow(
        player_api_id=player_api_id,
        player_name=name[:200],
        photo_url=_clip(info.get("photo") or seed.get("photo"), 500),
        position=_clip(info.get("position") or seed.get("position"), 50),
        nationality=_clip(info.get("nationality") or seed.get("nationality"), 100),
        birth_date=_parse_birth_date((info.get("birth") or {}).get("date")),
        current_club_name=_clip(seed.get("club_name"), 200),
        current_club_api_id=seed.get("club_api_id"),
        requested_by_user_id=requested_by,
        last_profile_sync_at=datetime.now(UTC) if info else None,
        is_active=True,
    )
    db.session.add(shadow)
    db.session.flush()
    return shadow


# --------------------------------------------------------------------------- #
# Search
# --------------------------------------------------------------------------- #


def search_players(q, api_client=None):
    """Worldwide player search for the shadow-follow UI.

    Returns up to 10 [{player_api_id, name, age?, nationality?, photo?,
    club_name?, tracked, shadow}]. Stub-safe: returns [] on empty query, no
    key, or any client error.
    """
    query = str(q or "").strip()
    if len(query) < 3:
        return []

    client = _resolve_client(api_client)
    rows = []
    try:
        rows = client.search_player_profiles_global(query) or []
    except Exception:
        logger.warning("Global profile search failed for %r", query)
        rows = []
    if not rows:
        try:
            rows = client.search_player_profiles(query) or []
        except Exception:
            logger.warning("Fallback player search failed for %r", query)
            rows = []

    results = []
    seen = set()
    for row in rows:
        player = (row or {}).get("player") or {}
        pid = player.get("id")
        if not isinstance(pid, int) or pid in seen:
            continue
        seen.add(pid)
        stats = row.get("statistics") if isinstance(row, dict) else None
        club_name = None
        if stats:
            club_name = ((stats[0] or {}).get("team") or {}).get("name")
        results.append(
            {
                "player_api_id": pid,
                "name": player.get("name") or f"Player {pid}",
                "age": player.get("age"),
                "nationality": player.get("nationality"),
                "photo": player.get("photo"),
                "club_name": club_name,
            }
        )
        if len(results) >= MAX_SEARCH_RESULTS:
            break

    pids = [r["player_api_id"] for r in results]
    tracked_ids: set[int] = set()
    shadow_ids: set[int] = set()
    if pids:
        tracked_ids = {
            row[0]
            for row in db.session.query(TrackedPlayer.player_api_id)
            .filter(
                TrackedPlayer.player_api_id.in_(pids),
                TrackedPlayer.is_active.is_(True),
                TrackedPlayer.data_source != "owning-club",
            )
            .all()
        }
        shadow_ids = {
            row[0]
            for row in db.session.query(PlayerShadow.player_api_id)
            .filter(PlayerShadow.player_api_id.in_(pids), PlayerShadow.is_active.is_(True))
            .all()
        }
    for result in results:
        result["tracked"] = result["player_api_id"] in tracked_ids
        result["shadow"] = result["player_api_id"] in shadow_ids
    return results


def user_shadow_follow_count(user_id: int) -> int:
    """Distinct shadow players the user follows across all their lists — the
    quantity capped by SHADOW_FOLLOW_LIMIT."""
    from src.models.follow import Follow, FollowList

    rows = (
        db.session.query(Follow.selector)
        .join(FollowList, FollowList.id == Follow.list_id)
        .filter(FollowList.user_account_id == user_id, Follow.kind == "player")
        .all()
    )
    pids = {(selector or {}).get("player_api_id") for (selector,) in rows}
    pids.discard(None)
    if not pids:
        return 0
    shadow_ids = {
        row[0]
        for row in db.session.query(PlayerShadow.player_api_id)
        .filter(PlayerShadow.player_api_id.in_(pids), PlayerShadow.is_active.is_(True))
        .all()
    }
    return len(shadow_ids)


# --------------------------------------------------------------------------- #
# Refresh (operator-paced batch)
# --------------------------------------------------------------------------- #


def _fetch_season_data(client, player_api_id, season):
    resp = client._make_request("players", {"id": player_api_id, "season": season})
    data = resp.get("response", []) if isinstance(resp, dict) else []
    return data[0] if data else None


def _aggregate_season_stats(data) -> dict:
    """Sum statistics[] blocks per team into one row per team."""
    if not data:
        return {}
    per_team: dict = {}
    for stat in data.get("statistics", []) or []:
        team = stat.get("team") or {}
        team_api_id = team.get("id")
        games = stat.get("games") or {}
        goals = stat.get("goals") or {}
        apps = games.get("appearences") or games.get("appearances") or 0
        agg = per_team.setdefault(
            team_api_id,
            {
                "team_api_id": team_api_id,
                "team_name": team.get("name"),
                "appearances": 0,
                "goals": 0,
                "assists": 0,
                "minutes": 0,
            },
        )
        agg["appearances"] += int(apps or 0)
        agg["goals"] += int(goals.get("total") or 0)
        agg["assists"] += int(goals.get("assists") or 0)
        agg["minutes"] += int(games.get("minutes") or 0)
    return per_team


def _upsert_shadow_stats(player_api_id, team_api_id, season, agg):
    row = PlayerShadowStats.query.filter_by(player_api_id=player_api_id, team_api_id=team_api_id, season=season).first()
    if row is None:
        row = PlayerShadowStats(player_api_id=player_api_id, team_api_id=team_api_id, season=season)
        db.session.add(row)
    row.team_name = agg.get("team_name")
    row.appearances = agg["appearances"]
    row.goals = agg["goals"]
    row.assists = agg["assists"]
    row.minutes = agg["minutes"]


def _refresh_profile(client, shadow) -> bool:
    try:
        profile = client.get_player_profile(shadow.player_api_id) or {}
    except Exception:
        return False
    info = (profile.get("player") if isinstance(profile, dict) else None) or {}
    if not info:
        return False
    if info.get("name"):
        shadow.player_name = str(info["name"])[:200]
    if info.get("photo"):
        shadow.photo_url = str(info["photo"])[:500]
    if info.get("position"):
        shadow.position = str(info["position"])[:50]
    if info.get("nationality"):
        shadow.nationality = str(info["nationality"])[:100]
    birth = _parse_birth_date((info.get("birth") or {}).get("date"))
    if birth:
        shadow.birth_date = birth
    return True


def refresh_shadows(limit=25, cursor=None, api_client=None) -> dict:
    """Refresh the N stalest active shadows (default) or an id-paged sweep.

    Default (no cursor): stalest-first by ``last_stats_sync_at`` — successful
    refreshes update that column, so repeated operator-paced calls naturally
    walk the whole population. Passing ``cursor`` switches to a deterministic
    id-paged sweep with backfill-names next_cursor semantics.

    Per shadow: fetch current-season data, sum per-team stat blocks into
    PlayerShadowStats, and refresh the profile when stale (>7d). Failures are
    isolated per row. Quota safety = the DB api_cache TTL + the client quota
    gate; no extra rate-limiter for operator-paced batches.
    """
    client = _resolve_client(api_client)
    limit = max(1, min(int(limit or 25), 200))

    query = PlayerShadow.query.filter(PlayerShadow.is_active.is_(True))
    if cursor:
        query = query.filter(PlayerShadow.id > cursor).order_by(PlayerShadow.id.asc())
    else:
        query = query.order_by(PlayerShadow.last_stats_sync_at.asc().nullsfirst(), PlayerShadow.id.asc())
    shadows = query.limit(limit).all()
    next_cursor = shadows[-1].id if (cursor and len(shadows) == limit) else None

    season = _current_season_start_year(client)
    now = datetime.now(UTC)
    stale_before = _as_naive(now) - timedelta(days=SHADOW_PROFILE_STALE_DAYS)

    considered = 0
    stats_upserted = 0
    profiles_refreshed = 0
    failed = 0

    for shadow in shadows:
        considered += 1
        try:
            data = _fetch_season_data(client, shadow.player_api_id, season)
            per_team = _aggregate_season_stats(data)
            for team_api_id, agg in per_team.items():
                _upsert_shadow_stats(shadow.player_api_id, team_api_id, season, agg)
                stats_upserted += 1
            if per_team:
                top = max(per_team.values(), key=lambda a: a["appearances"])
                shadow.current_club_api_id = top["team_api_id"]
                shadow.current_club_name = top["team_name"] or shadow.current_club_name
            shadow.last_stats_sync_at = now

            last_profile = _as_naive(shadow.last_profile_sync_at)
            if last_profile is None or last_profile < stale_before:
                if _refresh_profile(client, shadow):
                    profiles_refreshed += 1
                shadow.last_profile_sync_at = now
        except Exception:
            logger.exception("Shadow refresh failed for player %s", shadow.player_api_id)
            failed += 1
            continue

    db.session.commit()
    return {
        "considered": considered,
        "stats_upserted": stats_upserted,
        "profiles_refreshed": profiles_refreshed,
        "failed": failed,
        "next_cursor": next_cursor,
    }
