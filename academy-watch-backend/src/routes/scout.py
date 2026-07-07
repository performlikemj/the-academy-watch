"""Scout blueprint — cross-club talent discovery endpoints.

Gives scouts a way to browse, rank, and compare every tracked academy/loan
player across clubs and leagues, instead of navigating team-by-team.

Public endpoints:
- GET /scout/players       — filter/sort/paginate all tracked players with stats
- GET /scout/leaderboards  — top scorers / assists / minutes / per-90 boards
- GET /scout/compare       — side-by-side comparison of up to 4 players

Authenticated endpoints (Bearer token):
- GET/POST /scout/watchlist           — list / add saved players
- DELETE/PATCH /scout/watchlist/<id>  — remove / edit note
- GET /scout/watchlist/ids            — watched player ids only
- PATCH /scout/watchlist/settings     — digest opt-in toggle
- GET /scout/export.csv               — CSV export of scout rows
- POST /scout/admin/send-digests      — admin: send watchlist digest emails

Stats are aggregated in SQL: FixturePlayerStats (full coverage) with a
PlayerStatsCache fallback (limited coverage) merged via COALESCE, so no
per-player compute_stats() N+1 queries.
"""

import csv
import io
import logging
import os
from datetime import date

import bleach
from flask import Blueprint, Response, g, jsonify, request
from sqlalchemy import Integer, and_, case, cast, exists, func, or_, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import aliased, joinedload
from src.auth import _ensure_user_account, _safe_error_payload, require_api_key, require_user_auth
from src.extensions import limiter
from src.models.follow import Follow, FollowList, FollowPlayerSnapshot, PlayerShadow
from src.models.journey import PlayerJourney
from src.models.league import PlayerStatsCache, Team, UserAccount, db
from src.models.scout_watchlist import ScoutWatchlistEntry
from src.models.tracked_player import TrackedPlayer
from src.models.weekly import Fixture, FixturePlayerStats
from src.services.follow_resolver import derive_label, resolve_list, validate_selector
from src.services.player_shadow_service import (
    mint_shadow,
    refresh_shadows,
    search_players,
    user_shadow_follow_count,
)
from src.utils.sanitize import sanitize_plain_text

logger = logging.getLogger(__name__)

# Follow-graph caps (env-configurable; tests monkeypatch these module attrs).
MAX_FOLLOW_LISTS = int(os.getenv("MAX_FOLLOW_LISTS", "10"))
MAX_FOLLOWS_PER_LIST = int(os.getenv("MAX_FOLLOWS_PER_LIST", "50"))
SHADOW_FOLLOW_LIMIT = int(os.getenv("SHADOW_FOLLOW_LIMIT", "10"))
MAX_RESOLVE_PAGE = 50
MAX_LIST_NAME_LENGTH = 120
# Endpoint sanity cap for the pulse card-generation batch (env PULSE_CARD_LIMIT
# supplies the default; player_card_service enforces its own hard per-run cap).
MAX_PULSE_CARD_LIMIT = 500

scout_bp = Blueprint("scout", __name__)

VALID_POSITIONS = {"Goalkeeper", "Defender", "Midfielder", "Attacker"}
VALID_STATUSES = {"academy", "on_loan", "first_team", "released", "sold", "left"}
PER90_MIN_MINUTES = 270  # floor for per-90 rankings so 10-minute cameos don't top the boards
MAX_PER_PAGE = 100
MAX_COMPARE_PLAYERS = 4
FORM_MATCHES = 5
WATCHLIST_LIMIT = 200
MAX_NOTE_LENGTH = 2000
CSV_EXPORT_ROWS = 1000
CSV_HEADER = [
    "player_id",
    "name",
    "age",
    "position",
    "nationality",
    "status",
    "parent_club",
    "current_club",
    "appearances",
    "goals",
    "assists",
    "minutes",
    "avg_rating",
    "goal_contributions",
    "contributions_per90",
]


# Lazy import for api_client to avoid circular imports and early initialization
def _get_api_client():
    from src.routes.api import api_client

    return api_client


def _attach_recent_form(player_dicts):
    """Attach each player's last-N matches at their current club.

    One batched query for the whole page — (player, team) row-value IN works
    on both Postgres and SQLite.
    """
    pairs = {(p["player_id"], p["loan_team_api_id"]) for p in player_dicts if p.get("loan_team_api_id")}
    for p in player_dicts:
        p["recent_form"] = []
    if not pairs:
        return

    # Limit to the last N matches per pair in SQL — a watchlist can hold 200
    # players with full-season histories, so fetching everything and slicing
    # in Python transfers thousands of rows per request.
    ranked = (
        db.session.query(
            FixturePlayerStats.player_api_id.label("player_api_id"),
            FixturePlayerStats.team_api_id.label("team_api_id"),
            FixturePlayerStats.minutes.label("minutes"),
            FixturePlayerStats.goals.label("goals"),
            FixturePlayerStats.assists.label("assists"),
            FixturePlayerStats.rating.label("rating"),
            Fixture.date_utc.label("date_utc"),
            func.row_number()
            .over(
                partition_by=(FixturePlayerStats.player_api_id, FixturePlayerStats.team_api_id),
                order_by=Fixture.date_utc.desc().nullslast(),
            )
            .label("rn"),
        )
        .join(Fixture, Fixture.id == FixturePlayerStats.fixture_id)
        .filter(tuple_(FixturePlayerStats.player_api_id, FixturePlayerStats.team_api_id).in_(list(pairs)))
        .subquery()
    )
    rows = (
        db.session.query(ranked)
        .filter(ranked.c.rn <= FORM_MATCHES)
        .order_by(ranked.c.player_api_id, ranked.c.team_api_id, ranked.c.rn)
        .all()
    )

    form_by_pair = {}
    for row in rows:
        key = (row.player_api_id, row.team_api_id)
        form_by_pair.setdefault(key, []).append(
            {
                "date": row.date_utc.isoformat() if row.date_utc else None,
                "minutes": row.minutes or 0,
                "goals": row.goals or 0,
                "assists": row.assists or 0,
                "rating": round(float(row.rating), 1) if row.rating else None,
            }
        )

    for p in player_dicts:
        p["recent_form"] = form_by_pair.get((p["player_id"], p.get("loan_team_api_id")), [])


def _fixture_stats_subquery(season):
    """Aggregate FixturePlayerStats per player for one stats season.

    Grouped per player (NOT per (player, team)) and season-scoped: the Scout Desk
    shows a single season figure per player, summed across every club they played
    for. The old (player, team) grain forced the base query to join on
    ``current_club_api_id``, which hid a returned loanee's whole season once his
    tracked row pointed the current club back at the parent. ``avg_rating`` is now
    a cross-club season average, which is the intended cross-club view.
    """
    return (
        db.session.query(
            FixturePlayerStats.player_api_id.label("player_api_id"),
            func.count(FixturePlayerStats.id).label("appearances"),
            func.coalesce(func.sum(FixturePlayerStats.goals), 0).label("goals"),
            func.coalesce(func.sum(FixturePlayerStats.assists), 0).label("assists"),
            func.coalesce(func.sum(FixturePlayerStats.minutes), 0).label("minutes_played"),
            func.avg(FixturePlayerStats.rating).label("avg_rating"),
        )
        .join(Fixture, Fixture.id == FixturePlayerStats.fixture_id)
        .filter(Fixture.season == season)
        .group_by(FixturePlayerStats.player_api_id)
        .subquery()
    )


def _cache_stats_subquery():
    """Latest-cached-season PlayerStatsCache summed per player.

    Limited-coverage players have no fixture rows; their stats live in
    PlayerStatsCache. Per player, take their most recent cached season and sum
    across every club in it — dropping the old per-(player, team) grain and the
    base query's join on current_club_api_id, so one season figure lands per
    player regardless of which club the tracked row points at.
    """
    latest = (
        db.session.query(
            PlayerStatsCache.player_api_id.label("player_api_id"),
            func.max(PlayerStatsCache.season).label("season"),
        )
        .group_by(PlayerStatsCache.player_api_id)
        .subquery()
    )
    return (
        db.session.query(
            PlayerStatsCache.player_api_id.label("player_api_id"),
            func.coalesce(func.sum(PlayerStatsCache.appearances), 0).label("appearances"),
            func.coalesce(func.sum(PlayerStatsCache.goals), 0).label("goals"),
            func.coalesce(func.sum(PlayerStatsCache.assists), 0).label("assists"),
            func.coalesce(func.sum(PlayerStatsCache.minutes_played), 0).label("minutes_played"),
        )
        .join(
            latest,
            and_(
                PlayerStatsCache.player_api_id == latest.c.player_api_id,
                PlayerStatsCache.season == latest.c.season,
            ),
        )
        .group_by(PlayerStatsCache.player_api_id)
        .subquery()
    )


def _age_expression(today=None):
    """Player age as a SQL expression.

    Derived from birth_date ('YYYY-MM-DD' string) when present, because the
    stored age column is a point-in-time snapshot that is NULL or stale for
    most rows; falls back to the stored column. Dialect-safe (substr/cast
    work on both Postgres and SQLite).
    """
    today = today or date.today()
    birth_year_text = func.substr(TrackedPlayer.birth_date, 1, 4)
    birth_year = cast(birth_year_text, Integer)
    birth_month_day = func.substr(TrackedPlayer.birth_date, 6, 5)
    derived = case(
        (birth_month_day > today.strftime("%m-%d"), today.year - birth_year - 1),
        else_=today.year - birth_year,
    )
    # The year-range text comparison keeps a malformed value (e.g. a stray
    # "unknown" string) from reaching CAST, which raises on Postgres and
    # would 500 every age-filtered query.
    return case(
        (
            and_(
                TrackedPlayer.birth_date.isnot(None),
                func.length(TrackedPlayer.birth_date) >= 10,
                birth_year_text >= "1900",
                birth_year_text <= "2100",
            ),
            derived,
        ),
        else_=TrackedPlayer.age,
    )


def _preferred_row_filter():
    """Exclude duplicate TrackedPlayer rows for the same player, preferring
    academy-origin rows over owning-club rows (see CLAUDE.md guidance)."""
    other = aliased(TrackedPlayer)
    own_priority = case((TrackedPlayer.data_source == "owning-club", 1), else_=0)
    other_priority = case((other.data_source == "owning-club", 1), else_=0)
    better_row = (
        exists()
        .where(
            and_(
                other.player_api_id == TrackedPlayer.player_api_id,
                other.is_active.is_(True),
                or_(
                    other_priority < own_priority,
                    and_(other_priority == own_priority, other.id < TrackedPlayer.id),
                ),
            )
        )
        .correlate(TrackedPlayer)
    )
    return ~better_row


def _base_scout_query():
    """TrackedPlayer rows joined to aggregated stats, deduped per player."""
    from src.utils.academy_window import stats_season_with_data

    # Season-scope the fixture aggregate to the current stats season (latest with
    # data on rollover). One grouped join over the fixture rows, resolved once as
    # a subquery and outer-joined per player — no per-row N+1.
    season = stats_season_with_data(db.session)
    fps = _fixture_stats_subquery(season)
    cache = _cache_stats_subquery()

    goals = func.coalesce(fps.c.goals, cache.c.goals, 0).label("goals")
    assists = func.coalesce(fps.c.assists, cache.c.assists, 0).label("assists")
    minutes = func.coalesce(fps.c.minutes_played, cache.c.minutes_played, 0).label("minutes_played")
    appearances = func.coalesce(fps.c.appearances, cache.c.appearances, 0).label("appearances")
    avg_rating = fps.c.avg_rating.label("avg_rating")

    # Player-level CURRENT situation overrides the academy-relative
    # TrackedPlayer.status on player-facing surfaces. A Dortmund academy product
    # on loan from Ajax reads 'sold' relative to Dortmund but is really
    # 'on_loan · from Ajax'. journey.current_status (computed + stored during
    # sync) holds that truth; NULL defers to the academy-relative status.
    # player_journeys.player_api_id is unique, so this outerjoin yields ≤1 row
    # per player (no duplication) and never drops rows lacking a journey.
    journey_status = PlayerJourney.current_status.label("journey_status")
    journey_owner_id = PlayerJourney.current_owner_api_id.label("journey_owner_id")
    journey_owner_name = PlayerJourney.current_owner_name.label("journey_owner_name")
    effective_status = func.coalesce(PlayerJourney.current_status, TrackedPlayer.status).label("effective_status")

    query = (
        db.session.query(
            TrackedPlayer,
            goals,
            assists,
            minutes,
            appearances,
            avg_rating,
            journey_status,
            journey_owner_id,
            journey_owner_name,
        )
        .outerjoin(PlayerJourney, PlayerJourney.player_api_id == TrackedPlayer.player_api_id)
        # Stats join per player (not per current club): the aggregates are now
        # one season figure per player, so a returned loanee whose current club
        # points back at the parent still gets his loan-club season attributed.
        .outerjoin(fps, fps.c.player_api_id == TrackedPlayer.player_api_id)
        .outerjoin(cache, cache.c.player_api_id == TrackedPlayer.player_api_id)
        .filter(TrackedPlayer.is_active.is_(True))
        # owning-club rows are deprecated (senior signings, not academy
        # products) — never surface them even before a data repair runs.
        .filter(TrackedPlayer.data_source != "owning-club")
        .filter(_preferred_row_filter())
        # to_public_dict touches .team and .current_club — eager-load so a
        # page (or 1000-row CSV export) doesn't lazy-load per distinct club.
        .options(joinedload(TrackedPlayer.team), joinedload(TrackedPlayer.current_club))
    )
    columns = {
        "goals": goals,
        "assists": assists,
        "minutes_played": minutes,
        "appearances": appearances,
        "avg_rating": avg_rating,
        # status filter matches what the row displays (current situation,
        # falling back to academy-relative status).
        "effective_status": effective_status,
    }
    return query, columns


def _apply_filters(query, columns):
    """Apply shared request filters; returns (query, error_response_or_none)."""
    position = request.args.get("position", "").strip()
    if position:
        if position not in VALID_POSITIONS:
            return query, (jsonify({"error": f"Invalid position. One of: {sorted(VALID_POSITIONS)}"}), 400)
        query = query.filter(TrackedPlayer.position == position)

    statuses = [s.strip() for s in request.args.get("status", "").split(",") if s.strip()]
    if statuses:
        invalid = [s for s in statuses if s not in VALID_STATUSES]
        if invalid:
            return query, (jsonify({"error": f"Invalid status {invalid}. One of: {sorted(VALID_STATUSES)}"}), 400)
        query = query.filter(columns["effective_status"].in_(statuses))

    min_age = request.args.get("min_age", type=int)
    max_age = request.args.get("max_age", type=int)
    if min_age is not None or max_age is not None:
        age_expr = _age_expression()
        if min_age is not None:
            query = query.filter(age_expr >= min_age)
        if max_age is not None:
            query = query.filter(age_expr <= max_age)

    nationality = request.args.get("nationality", "").strip()
    if nationality:
        query = query.filter(TrackedPlayer.nationality.ilike(f"%{nationality}%"))

    search = request.args.get("search", "").strip()
    if search:
        query = query.filter(TrackedPlayer.player_name.ilike(f"%{search}%"))

    min_minutes = request.args.get("min_minutes", type=int)
    if min_minutes:
        query = query.filter(columns["minutes_played"] >= min_minutes)

    return query, None


def _row_to_dict(row):
    tracked_player = row[0]
    payload = tracked_player.to_public_dict()
    payload["appearances"] = int(row.appearances or 0)
    payload["goals"] = int(row.goals or 0)
    payload["assists"] = int(row.assists or 0)
    payload["minutes_played"] = int(row.minutes_played or 0)
    payload["avg_rating"] = round(float(row.avg_rating), 2) if row.avg_rating else None
    minutes = payload["minutes_played"]
    contributions = payload["goals"] + payload["assists"]
    payload["goal_contributions"] = contributions
    payload["contributions_per90"] = round(contributions * 90.0 / minutes, 2) if minutes else None
    # Surface the player's actual current situation (mirrors the player profile
    # endpoint): when stored, it overrides the academy-relative status and adds
    # the owning club so the CLUB column reads "from <owner>", not "from <academy>".
    if row.journey_status:
        payload["status"] = row.journey_status
        payload["owner_team_id"] = row.journey_owner_id
        payload["owner_team_name"] = row.journey_owner_name
    return payload


def _sort_expression(sort, columns):
    contributions = columns["goals"] + columns["assists"]
    per90 = (contributions * 90.0) / func.nullif(columns["minutes_played"], 0)
    sort_map = {
        "goals": columns["goals"],
        "assists": columns["assists"],
        "minutes": columns["minutes_played"],
        "appearances": columns["appearances"],
        "rating": columns["avg_rating"],
        "contributions": contributions,
        "per90": per90,
        "age": _age_expression(),
        "name": TrackedPlayer.player_name,
    }
    return sort_map.get(sort)


@scout_bp.route("/scout/players", methods=["GET"])
def scout_players():
    """Browse all tracked players across clubs with filters and stat sorting.

    Query params:
    - position: Goalkeeper | Defender | Midfielder | Attacker
    - status: comma-separated (academy,on_loan,first_team,released,sold)
    - min_age / max_age: integer bounds
    - nationality: substring match
    - search: player name substring
    - min_minutes: minimum minutes played
    - sort: goals | assists | minutes | appearances | rating | contributions |
            per90 | age | name (default: contributions)
    - order: asc | desc (default desc; name/age default asc)
    - page / per_page: pagination (per_page max 100)
    """
    try:
        query, columns = _base_scout_query()
        query, error = _apply_filters(query, columns)
        if error:
            return error

        sort = request.args.get("sort", "contributions").strip()
        sort_expr = _sort_expression(sort, columns)
        if sort_expr is None:
            return jsonify({"error": f"Invalid sort '{sort}'"}), 400
        if sort == "per90":
            # per-90 rankings need a minutes floor to be meaningful
            min_minutes = request.args.get("min_minutes", type=int) or 0
            query = query.filter(columns["minutes_played"] >= max(min_minutes, PER90_MIN_MINUTES))

        default_order = "asc" if sort in ("name", "age") else "desc"
        order = request.args.get("order", default_order).strip().lower()
        if order == "desc":
            query = query.order_by(sort_expr.desc().nullslast(), TrackedPlayer.id)
        else:
            query = query.order_by(sort_expr.asc().nullslast(), TrackedPlayer.id)

        page = max(request.args.get("page", 1, type=int), 1)
        per_page = min(max(request.args.get("per_page", 25, type=int), 1), MAX_PER_PAGE)

        total = query.count()
        rows = query.offset((page - 1) * per_page).limit(per_page).all()

        players = [_row_to_dict(row) for row in rows]
        _attach_recent_form(players)

        return jsonify(
            {
                "players": players,
                "total": total,
                "page": page,
                "per_page": per_page,
                "total_pages": (total + per_page - 1) // per_page if total else 0,
            }
        )
    except Exception as e:
        logger.error(f"Error in scout_players: {e}")
        return jsonify(_safe_error_payload(e, "An unexpected error occurred. Please try again later.")), 500


@scout_bp.route("/scout/leaderboards", methods=["GET"])
def scout_leaderboards():
    """Top performers across all tracked players.

    Query params:
    - limit: entries per board (default 10, max 25)
    - position / status / min_age / max_age / nationality: same as /scout/players
    """
    try:
        limit = min(max(request.args.get("limit", 10, type=int), 1), 25)

        def board(sort_key, extra_min_minutes=0):
            query, columns = _base_scout_query()
            query, error = _apply_filters(query, columns)
            if error:
                return None, error
            if extra_min_minutes:
                query = query.filter(columns["minutes_played"] >= extra_min_minutes)
            sort_expr = _sort_expression(sort_key, columns)
            query = query.filter(columns["appearances"] > 0)
            rows = query.order_by(sort_expr.desc().nullslast(), TrackedPlayer.id).limit(limit).all()
            return [_row_to_dict(row) for row in rows], None

        boards = {}
        for key, sort_key, min_minutes in (
            ("top_scorers", "goals", 0),
            ("top_assists", "assists", 0),
            ("most_minutes", "minutes", 0),
            ("best_per90", "per90", PER90_MIN_MINUTES),
        ):
            entries, error = board(sort_key, min_minutes)
            if error:
                return error
            boards[key] = entries

        return jsonify({"leaderboards": boards, "limit": limit})
    except Exception as e:
        logger.error(f"Error in scout_leaderboards: {e}")
        return jsonify(_safe_error_payload(e, "An unexpected error occurred. Please try again later.")), 500


def _per90(value, minutes):
    if not minutes or value is None:
        return None
    return round(float(value) * 90.0 / minutes, 2)


@scout_bp.route("/scout/compare", methods=["GET"])
def scout_compare():
    """Compare up to 4 players side by side.

    Query params:
    - ids: comma-separated player_api_ids (required, max 4)
    - include_availability: 'true' to add season injury/absence summaries
      (sourced live from API-Football's injuries endpoint, DB-cached)
    """
    try:
        include_availability = request.args.get("include_availability", "").lower() == "true"
        raw_ids = [p.strip() for p in request.args.get("ids", "").split(",") if p.strip()]
        if not raw_ids:
            return jsonify({"error": "ids parameter is required (comma-separated player ids)"}), 400
        if len(raw_ids) > MAX_COMPARE_PLAYERS:
            return jsonify({"error": f"At most {MAX_COMPARE_PLAYERS} players can be compared"}), 400
        try:
            player_ids = [int(p) for p in raw_ids]
        except ValueError:
            return jsonify({"error": "ids must be integers"}), 400

        from src.utils.academy_window import stats_season_with_data

        # One season figure per player, summed across EVERY club the player
        # appeared for — mirrors the season-scoped /scout/players list and
        # /players/<id>/season-stats. Keying this on current_club_api_id (as it
        # was) both hid a returned loanee's whole loan season and let a stray
        # parent-club cup cameo masquerade as his season, so the compare panel
        # contradicted the list on the same Scout Desk page.
        season = stats_season_with_data(db.session)

        players = []
        for player_id in player_ids:
            tracked_player = (
                TrackedPlayer.query.filter_by(player_api_id=player_id, is_active=True)
                .filter(TrackedPlayer.data_source != "owning-club")
                .order_by(TrackedPlayer.id)
                .first()
            )
            if not tracked_player:
                continue

            totals = None
            row = (
                db.session.query(
                    func.count(FixturePlayerStats.id).label("appearances"),
                    func.coalesce(func.sum(FixturePlayerStats.goals), 0).label("goals"),
                    func.coalesce(func.sum(FixturePlayerStats.assists), 0).label("assists"),
                    func.coalesce(func.sum(FixturePlayerStats.minutes), 0).label("minutes"),
                    func.avg(FixturePlayerStats.rating).label("avg_rating"),
                    func.coalesce(func.sum(FixturePlayerStats.shots_total), 0).label("shots_total"),
                    func.coalesce(func.sum(FixturePlayerStats.shots_on), 0).label("shots_on"),
                    func.coalesce(func.sum(FixturePlayerStats.passes_total), 0).label("passes_total"),
                    func.coalesce(func.sum(FixturePlayerStats.passes_key), 0).label("key_passes"),
                    func.coalesce(func.sum(FixturePlayerStats.dribbles_attempts), 0).label("dribbles_attempts"),
                    func.coalesce(func.sum(FixturePlayerStats.dribbles_success), 0).label("dribbles_success"),
                    func.coalesce(func.sum(FixturePlayerStats.tackles_total), 0).label("tackles"),
                    func.coalesce(func.sum(FixturePlayerStats.tackles_interceptions), 0).label("interceptions"),
                    func.coalesce(func.sum(FixturePlayerStats.duels_total), 0).label("duels_total"),
                    func.coalesce(func.sum(FixturePlayerStats.duels_won), 0).label("duels_won"),
                    func.coalesce(func.sum(FixturePlayerStats.fouls_drawn), 0).label("fouls_drawn"),
                    func.coalesce(func.sum(FixturePlayerStats.yellows), 0).label("yellows"),
                    func.coalesce(func.sum(FixturePlayerStats.reds), 0).label("reds"),
                    func.coalesce(func.sum(FixturePlayerStats.saves), 0).label("saves"),
                    func.coalesce(func.sum(FixturePlayerStats.goals_conceded), 0).label("goals_conceded"),
                )
                .join(Fixture, Fixture.id == FixturePlayerStats.fixture_id)
                .filter(
                    FixturePlayerStats.player_api_id == player_id,
                    Fixture.season == season,
                )
                .first()
            )
            if row and row.appearances:
                minutes = int(row.minutes or 0)
                totals = {
                    "appearances": int(row.appearances),
                    "goals": int(row.goals),
                    "assists": int(row.assists),
                    "minutes_played": minutes,
                    "avg_rating": round(float(row.avg_rating), 2) if row.avg_rating else None,
                    "shots_total": int(row.shots_total),
                    "shots_on": int(row.shots_on),
                    "passes_total": int(row.passes_total),
                    "key_passes": int(row.key_passes),
                    "dribbles_attempts": int(row.dribbles_attempts),
                    "dribbles_success": int(row.dribbles_success),
                    "tackles": int(row.tackles),
                    "interceptions": int(row.interceptions),
                    "duels_total": int(row.duels_total),
                    "duels_won": int(row.duels_won),
                    "fouls_drawn": int(row.fouls_drawn),
                    "yellows": int(row.yellows),
                    "reds": int(row.reds),
                    "saves": int(row.saves),
                    "goals_conceded": int(row.goals_conceded),
                    "stats_coverage": "full",
                }

            if totals is None:
                # No fixture rows this season (limited-coverage / no-data) — fall
                # back to basic totals. This keeps the detailed shot/duel/per-90
                # panel for full-coverage players while degrading gracefully.
                basic = tracked_player.compute_stats()
                totals = {**basic, "minutes_played": basic.get("minutes_played", 0)}

            minutes = totals.get("minutes_played", 0)
            per90 = {
                "goals": _per90(totals.get("goals"), minutes),
                "assists": _per90(totals.get("assists"), minutes),
                "goal_contributions": _per90((totals.get("goals") or 0) + (totals.get("assists") or 0), minutes),
                "key_passes": _per90(totals.get("key_passes"), minutes),
                "shots_total": _per90(totals.get("shots_total"), minutes),
                "dribbles_success": _per90(totals.get("dribbles_success"), minutes),
                "tackles": _per90(totals.get("tackles"), minutes),
                "interceptions": _per90(totals.get("interceptions"), minutes),
                "duels_won": _per90(totals.get("duels_won"), minutes),
            }

            career = None
            journey = tracked_player.journey
            if journey:
                career = {
                    "first_team_apps": journey.total_first_team_apps,
                    "youth_apps": journey.total_youth_apps,
                    "loan_apps": journey.total_loan_apps,
                    "goals": journey.total_goals,
                    "assists": journey.total_assists,
                    "first_team_debut_season": journey.first_team_debut_season,
                    "first_team_debut_club": journey.first_team_debut_club,
                }

            availability = None
            if include_availability:
                try:
                    api_client = _get_api_client()
                    records = api_client.get_player_injuries(player_id)
                    records = sorted(records, key=lambda r: (r.get("fixture") or {}).get("date") or "", reverse=True)
                    reasons = [(r.get("player") or {}).get("reason") or "Unknown" for r in records]
                    availability = {
                        "total_absences": len(records),
                        "last_reason": reasons[0] if reasons else None,
                    }
                except Exception as availability_error:
                    logger.warning(f"Availability lookup failed for player {player_id}: {availability_error}")

            profile = tracked_player.to_public_dict()
            # Same current-situation override as the list/profile surfaces.
            if journey and journey.current_status:
                profile["status"] = journey.current_status
                profile["owner_team_id"] = journey.current_owner_api_id
                profile["owner_team_name"] = journey.current_owner_name

            players.append(
                {
                    "profile": profile,
                    "totals": totals,
                    "per90": per90,
                    "career": career,
                    "availability": availability,
                }
            )

        missing = [pid for pid in player_ids if pid not in {p["profile"]["player_id"] for p in players}]
        return jsonify({"players": players, "missing_ids": missing})
    except Exception as e:
        logger.error(f"Error in scout_compare: {e}")
        return jsonify(_safe_error_payload(e, "An unexpected error occurred. Please try again later.")), 500


def _csv_safe(value):
    """Neutralise spreadsheet formula injection (CWE-1236).

    Names/clubs come from third-party feeds; a cell starting with = + - @
    (or tab/CR) executes as a formula when the export opens in Excel/Sheets.
    """
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return f"'{value}"
    return value


def _user_rate_limit_key() -> str:
    # remote_addr is the ingress proxy in production, so per-IP buckets would
    # collapse into one shared global bucket — key by authenticated email.
    return getattr(g, "user_email", None) or (request.remote_addr or "anon")


def _current_user_account():
    """UserAccount for the authenticated request, created on first use."""
    user = getattr(g, "user", None)
    if user is not None:
        return user
    email = getattr(g, "user_email", None)
    if not email:
        return None
    user = UserAccount.query.filter_by(email=email).first()
    if user is None:
        user = _ensure_user_account(email)
        db.session.commit()
    return user


def _watched_player_dicts(player_api_ids):
    """Enriched scout-row dicts keyed by player_api_id (missing when inactive)."""
    ids = [pid for pid in set(player_api_ids) if pid]
    if not ids:
        return {}
    query, _ = _base_scout_query()
    rows = query.filter(TrackedPlayer.player_api_id.in_(ids)).all()
    players = [_row_to_dict(row) for row in rows]
    _attach_recent_form(players)
    return {p["player_id"]: p for p in players}


def _entry_payload(entry, player=None):
    return {
        "player_api_id": entry.player_api_id,
        "note": entry.note,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
        "player": player,
    }


@scout_bp.route("/scout/watchlist", methods=["GET"])
@require_user_auth
@limiter.limit("60/minute", key_func=_user_rate_limit_key)
def scout_watchlist():
    """The authenticated user's watchlist, newest first, with enriched stats."""
    try:
        user = _current_user_account()
        if user is None:
            return jsonify({"error": "auth context missing email"}), 401
        entries = (
            ScoutWatchlistEntry.query.filter_by(user_account_id=user.id)
            .order_by(ScoutWatchlistEntry.created_at.desc(), ScoutWatchlistEntry.id.desc())
            .all()
        )
        players = _watched_player_dicts([entry.player_api_id for entry in entries])
        return jsonify(
            {
                "entries": [_entry_payload(entry, players.get(entry.player_api_id)) for entry in entries],
                "digest_opt_in": bool(user.scout_digest_opt_in),
                "scout_tier": user.scout_tier or "free",
            }
        )
    except Exception as e:
        logger.error(f"Error in scout_watchlist: {e}")
        return jsonify(_safe_error_payload(e, "An unexpected error occurred. Please try again later.")), 500


@scout_bp.route("/scout/watchlist", methods=["POST"])
@require_user_auth
@limiter.limit("30/minute", key_func=_user_rate_limit_key)
def scout_watchlist_add():
    """Add a player to the watchlist. Idempotent: re-adding returns 200.

    Watchlist entries stay TrackedPlayer-only (the 404 below is unchanged);
    worldwide/shadow players are followable only via follow lists. Every add is
    also mirrored into the user's default follow list.
    """
    try:
        user = _current_user_account()
        if user is None:
            return jsonify({"error": "auth context missing email"}), 401
        payload = request.get_json(silent=True) or {}
        player_api_id = payload.get("player_api_id")
        if not isinstance(player_api_id, int) or isinstance(player_api_id, bool) or player_api_id <= 0:
            return jsonify({"error": "player_api_id must be a positive integer"}), 400

        existing = ScoutWatchlistEntry.query.filter_by(user_account_id=user.id, player_api_id=player_api_id).first()
        if existing:
            _mirror_watchlist_add(user, player_api_id, note=existing.note)
            players = _watched_player_dicts([player_api_id])
            return jsonify({"entry": _entry_payload(existing, players.get(player_api_id))}), 200

        # Same row set the watchlist enrichment uses — owning-club rows are
        # excluded there, so allowing them here would create entries that
        # forever render empty.
        active = (
            TrackedPlayer.query.filter_by(player_api_id=player_api_id, is_active=True)
            .filter(TrackedPlayer.data_source != "owning-club")
            .first()
        )
        if not active:
            return jsonify({"error": "No active tracked player with that id"}), 404

        if ScoutWatchlistEntry.query.filter_by(user_account_id=user.id).count() >= WATCHLIST_LIMIT:
            return jsonify({"error": f"watchlist limit reached ({WATCHLIST_LIMIT})"}), 409

        entry = ScoutWatchlistEntry(user_account_id=user.id, player_api_id=player_api_id)
        db.session.add(entry)
        try:
            db.session.commit()
        except IntegrityError:
            # Concurrent add (double-click / second tab) lost the race to the
            # unique constraint — honour the idempotency contract with a 200.
            db.session.rollback()
            entry = ScoutWatchlistEntry.query.filter_by(user_account_id=user.id, player_api_id=player_api_id).first()
            if entry is None:
                raise
            _mirror_watchlist_add(user, player_api_id, note=entry.note)
            players = _watched_player_dicts([player_api_id])
            return jsonify({"entry": _entry_payload(entry, players.get(player_api_id))}), 200
        _mirror_watchlist_add(user, player_api_id, note=entry.note)
        players = _watched_player_dicts([player_api_id])
        return jsonify({"entry": _entry_payload(entry, players.get(player_api_id))}), 201
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in scout_watchlist_add: {e}")
        return jsonify(_safe_error_payload(e, "An unexpected error occurred. Please try again later.")), 500


@scout_bp.route("/scout/watchlist/<int:player_api_id>", methods=["DELETE"])
@require_user_auth
@limiter.limit("30/minute", key_func=_user_rate_limit_key)
def scout_watchlist_remove(player_api_id):
    """Remove a player from the watchlist. Idempotent."""
    try:
        user = _current_user_account()
        if user is None:
            return jsonify({"error": "auth context missing email"}), 401
        entry = ScoutWatchlistEntry.query.filter_by(user_account_id=user.id, player_api_id=player_api_id).first()
        if entry is None:
            return jsonify({"removed": False})
        db.session.delete(entry)
        db.session.commit()
        _mirror_watchlist_remove(user, player_api_id)
        return jsonify({"removed": True})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in scout_watchlist_remove: {e}")
        return jsonify(_safe_error_payload(e, "An unexpected error occurred. Please try again later.")), 500


@scout_bp.route("/scout/watchlist/<int:player_api_id>", methods=["PATCH"])
@require_user_auth
@limiter.limit("30/minute", key_func=_user_rate_limit_key)
def scout_watchlist_note(player_api_id):
    """Set, replace, or clear (empty/whitespace) the note on a watchlist entry."""
    try:
        user = _current_user_account()
        if user is None:
            return jsonify({"error": "auth context missing email"}), 401
        entry = ScoutWatchlistEntry.query.filter_by(user_account_id=user.id, player_api_id=player_api_id).first()
        if entry is None:
            return jsonify({"error": "Player is not on your watchlist"}), 404

        payload = request.get_json(silent=True) or {}
        note = payload.get("note", "")
        if note is None:
            note = ""
        if not isinstance(note, str):
            return jsonify({"error": "note must be a string"}), 400
        cleaned = bleach.clean(note, strip=True).strip()
        if len(cleaned) > MAX_NOTE_LENGTH:
            return jsonify({"error": f"note must be at most {MAX_NOTE_LENGTH} characters"}), 400

        entry.note = cleaned or None
        db.session.commit()
        players = _watched_player_dicts([player_api_id])
        return jsonify({"entry": _entry_payload(entry, players.get(player_api_id))})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in scout_watchlist_note: {e}")
        return jsonify(_safe_error_payload(e, "An unexpected error occurred. Please try again later.")), 500


@scout_bp.route("/scout/watchlist/ids", methods=["GET"])
@require_user_auth
@limiter.limit("120/minute", key_func=_user_rate_limit_key)
def scout_watchlist_ids():
    """Just the watched player_api_ids — cheap lookup for toggling UI state."""
    try:
        user = _current_user_account()
        if user is None:
            return jsonify({"error": "auth context missing email"}), 401
        rows = (
            db.session.query(ScoutWatchlistEntry.player_api_id)
            .filter(ScoutWatchlistEntry.user_account_id == user.id)
            .order_by(ScoutWatchlistEntry.created_at.desc(), ScoutWatchlistEntry.id.desc())
            .all()
        )
        return jsonify({"player_ids": [row[0] for row in rows]})
    except Exception as e:
        logger.error(f"Error in scout_watchlist_ids: {e}")
        return jsonify(_safe_error_payload(e, "An unexpected error occurred. Please try again later.")), 500


@scout_bp.route("/scout/watchlist/settings", methods=["PATCH"])
@require_user_auth
@limiter.limit("30/minute", key_func=_user_rate_limit_key)
def scout_watchlist_settings():
    """Toggle the weekly scout digest email for the authenticated user."""
    try:
        user = _current_user_account()
        if user is None:
            return jsonify({"error": "auth context missing email"}), 401
        payload = request.get_json(silent=True) or {}
        digest_opt_in = payload.get("digest_opt_in")
        if not isinstance(digest_opt_in, bool):
            return jsonify({"error": "digest_opt_in must be a boolean"}), 400
        user.scout_digest_opt_in = digest_opt_in
        db.session.commit()
        return jsonify({"digest_opt_in": digest_opt_in})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in scout_watchlist_settings: {e}")
        return jsonify(_safe_error_payload(e, "An unexpected error occurred. Please try again later.")), 500


@scout_bp.route("/scout/export.csv", methods=["GET"])
@require_user_auth
@limiter.limit("10/minute", key_func=_user_rate_limit_key)
def scout_export_csv():
    """CSV export of scout rows.

    Accepts the same query params as /scout/players, plus ids=comma-separated
    player_api_ids (max 200) which exports exactly those players and ignores
    other filters except sort/order. Capped at 1000 rows.
    """
    try:
        query, columns = _base_scout_query()

        raw_ids = [p.strip() for p in request.args.get("ids", "").split(",") if p.strip()]
        if raw_ids:
            if len(raw_ids) > WATCHLIST_LIMIT:
                return jsonify({"error": f"At most {WATCHLIST_LIMIT} ids can be exported"}), 400
            try:
                player_ids = [int(p) for p in raw_ids]
            except ValueError:
                return jsonify({"error": "ids must be integers"}), 400
            query = query.filter(TrackedPlayer.player_api_id.in_(player_ids))
        else:
            query, error = _apply_filters(query, columns)
            if error:
                return error

        sort = request.args.get("sort", "contributions").strip()
        sort_expr = _sort_expression(sort, columns)
        if sort_expr is None:
            return jsonify({"error": f"Invalid sort '{sort}'"}), 400
        if sort == "per90" and not raw_ids:
            min_minutes = request.args.get("min_minutes", type=int) or 0
            query = query.filter(columns["minutes_played"] >= max(min_minutes, PER90_MIN_MINUTES))

        default_order = "asc" if sort in ("name", "age") else "desc"
        order = request.args.get("order", default_order).strip().lower()
        if order == "desc":
            query = query.order_by(sort_expr.desc().nullslast(), TrackedPlayer.id)
        else:
            query = query.order_by(sort_expr.asc().nullslast(), TrackedPlayer.id)

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(CSV_HEADER)
        for row in query.limit(CSV_EXPORT_ROWS).all():
            p = _row_to_dict(row)
            writer.writerow(
                [
                    p["player_id"],
                    _csv_safe(p["player_name"]),
                    p["age"],
                    _csv_safe(p["position"]),
                    _csv_safe(p["nationality"]),
                    p["status"],
                    _csv_safe(p["primary_team_name"]),
                    _csv_safe(p["loan_team_name"]),
                    p["appearances"],
                    p["goals"],
                    p["assists"],
                    p["minutes_played"],
                    p["avg_rating"] if p["avg_rating"] is not None else "",
                    p["goal_contributions"],
                    p["contributions_per90"] if p["contributions_per90"] is not None else "",
                ]
            )

        return Response(
            buffer.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": 'attachment; filename="academy-watch-scout-export.csv"'},
        )
    except Exception as e:
        logger.error(f"Error in scout_export_csv: {e}")
        return jsonify(_safe_error_payload(e, "An unexpected error occurred. Please try again later.")), 500


@scout_bp.route("/scout/admin/send-digests", methods=["POST"])
@require_api_key
def scout_admin_send_digests():
    """Send (or dry-run preview) the scout digest email to watchlist users."""
    try:
        from src.services.scout_digest_service import MAX_DIGEST_USERS, send_scout_digests

        payload = request.get_json(silent=True) or {}
        dry_run = payload.get("dry_run", True)
        if not isinstance(dry_run, bool):
            return jsonify({"error": "dry_run must be a boolean"}), 400
        limit = payload.get("limit", 50)
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            return jsonify({"error": "limit must be a positive integer"}), 400
        limit = min(limit, MAX_DIGEST_USERS)
        cursor = payload.get("cursor", 0)
        if not isinstance(cursor, int) or isinstance(cursor, bool) or cursor < 0:
            return jsonify({"error": "cursor must be a non-negative integer"}), 400

        result = send_scout_digests(dry_run=dry_run, limit=limit, api_client=_get_api_client(), cursor=cursor)
        result["dry_run"] = dry_run
        result["applied"] = not dry_run
        return jsonify(result)
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in scout_admin_send_digests: {e}")
        return jsonify(_safe_error_payload(e, "An unexpected error occurred. Please try again later.")), 500


# =========================================================================== #
# Follow lists + shadow tracking
# =========================================================================== #


def _player_display_name(player_api_id):
    """Best-effort display name for a follow label (tracked, else shadow)."""
    tracked = (
        TrackedPlayer.query.filter_by(player_api_id=player_api_id, is_active=True)
        .filter(TrackedPlayer.data_source != "owning-club")
        .first()
    )
    if tracked:
        return tracked.player_name
    shadow = PlayerShadow.query.filter_by(player_api_id=player_api_id).first()
    return shadow.player_name if shadow else None


def _default_follow_list(user, create=True):
    """The user's migrated-watchlist default list, created on demand."""
    follow_list = FollowList.query.filter_by(user_account_id=user.id, is_default=True).first()
    if follow_list is None and create:
        follow_list = FollowList(user_account_id=user.id, name="My Watchlist", is_default=True)
        db.session.add(follow_list)
        db.session.flush()
    return follow_list


def _mirror_watchlist_add(user, player_api_id, note=None):
    """Mirror a watchlist add into the user's default follow list.

    Best-effort: a mirror failure never breaks the watchlist write. Watchlist
    entries are always tracked players (shadow players are followable only via
    lists), so this upserts a player-kind follow for an existing tracked player.
    """
    try:
        follow_list = _default_follow_list(user, create=True)
        for follow in follow_list.follows.filter(Follow.kind == "player").all():
            if (follow.selector or {}).get("player_api_id") == player_api_id:
                return
        db.session.add(
            Follow(
                list_id=follow_list.id,
                kind="player",
                selector={"player_api_id": player_api_id},
                label=derive_label("player", {"player_api_id": player_api_id}, _player_display_name(player_api_id)),
                note=note,
            )
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception("watchlist->list mirror (add) failed for player %s", player_api_id)


def _mirror_watchlist_remove(user, player_api_id):
    """Remove the matching player follow from the default list only."""
    try:
        follow_list = FollowList.query.filter_by(user_account_id=user.id, is_default=True).first()
        if follow_list is None:
            return
        removed = False
        for follow in follow_list.follows.filter(Follow.kind == "player").all():
            if (follow.selector or {}).get("player_api_id") == player_api_id:
                db.session.delete(follow)
                removed = True
        if removed:
            db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception("watchlist->list mirror (remove) failed for player %s", player_api_id)


def _user_already_follows_player(user_id, player_api_id):
    """True if the user follows this player id in any of their lists."""
    rows = (
        db.session.query(Follow.selector)
        .join(FollowList, FollowList.id == Follow.list_id)
        .filter(FollowList.user_account_id == user_id, Follow.kind == "player")
        .all()
    )
    return any((selector or {}).get("player_api_id") == player_api_id for (selector,) in rows)


def _follow_label_maps(follows):
    """Batched name lookups for read-time follow labels: player_api_id -> player
    name (TrackedPlayer, then PlayerShadow) and teams.id -> team name."""
    player_ids = set()
    team_ids = set()
    for follow in follows:
        selector = follow.selector or {}
        if follow.kind == "player" and selector.get("player_api_id"):
            player_ids.add(selector["player_api_id"])
        elif follow.kind == "academy_club" and selector.get("team_id"):
            team_ids.add(selector["team_id"])

    name_map = {}
    if player_ids:
        for tp in TrackedPlayer.query.filter(
            TrackedPlayer.player_api_id.in_(player_ids),
            TrackedPlayer.is_active.is_(True),
            TrackedPlayer.data_source != "owning-club",
        ).all():
            name_map.setdefault(tp.player_api_id, tp.player_name)
        remaining = player_ids - set(name_map)
        if remaining:
            for shadow in PlayerShadow.query.filter(PlayerShadow.player_api_id.in_(remaining)).all():
                name_map.setdefault(shadow.player_api_id, shadow.player_name)

    team_map = {}
    if team_ids:
        for team in Team.query.filter(Team.id.in_(team_ids)).all():
            team_map.setdefault(team.id, team.name)
    return name_map, team_map


def _follow_read_payload(follow, name_map, team_map):
    """A follow dict whose label is derived at read time from fresh names."""
    selector = follow.selector or {}
    if follow.kind == "player":
        name = name_map.get(selector.get("player_api_id"))
    elif follow.kind == "academy_club":
        name = team_map.get(selector.get("team_id"))
    else:
        name = None
    return {
        "id": follow.id,
        "kind": follow.kind,
        "selector": follow.selector,
        "label": derive_label(follow.kind, selector, name),
        "note": follow.note,
        "created_at": follow.created_at.isoformat() if follow.created_at else None,
    }


def _follow_list_payload(follow_list, follows=None, name_map=None, team_map=None):
    """List payload with embedded read-time-labelled follows.

    GET /scout/lists passes pre-batched ``follows`` + name/team maps (one query
    for all lists' follows) to stay N+1-free; single-list responses pass nothing
    and this loads that one list's follows.
    """
    if follows is None:
        follows = follow_list.follows.order_by(Follow.created_at.asc(), Follow.id.asc()).all()
        name_map, team_map = _follow_label_maps(follows)
    return {
        "id": follow_list.id,
        "name": follow_list.name,
        "cadence": follow_list.cadence,
        "is_active": follow_list.is_active,
        "is_default": follow_list.is_default,
        "player_cap": follow_list.player_cap,
        "follow_count": len(follows),
        "follows": [_follow_read_payload(f, name_map or {}, team_map or {}) for f in follows],
        "created_at": follow_list.created_at.isoformat() if follow_list.created_at else None,
        "updated_at": follow_list.updated_at.isoformat() if follow_list.updated_at else None,
    }


def _follow_payload(follow):
    return {
        "id": follow.id,
        "kind": follow.kind,
        "selector": follow.selector,
        "label": follow.label,
        "note": follow.note,
        "created_at": follow.created_at.isoformat() if follow.created_at else None,
    }


def _owned_list(user, list_id):
    return FollowList.query.filter_by(id=list_id, user_account_id=user.id).first()


def _clean_list_name(raw):
    """(name, error) — sanitized, non-empty, length-capped list name."""
    if not isinstance(raw, str):
        return None, "name must be a string"
    name = sanitize_plain_text(raw).strip()
    if not name:
        return None, "name is required"
    if len(name) > MAX_LIST_NAME_LENGTH:
        return None, f"name must be at most {MAX_LIST_NAME_LENGTH} characters"
    return name, None


@scout_bp.route("/scout/lists", methods=["GET"])
@require_user_auth
@limiter.limit("60/minute", key_func=_user_rate_limit_key)
def scout_lists():
    """The authenticated user's follow lists (default list first)."""
    try:
        user = _current_user_account()
        if user is None:
            return jsonify({"error": "auth context missing email"}), 401
        lists = (
            FollowList.query.filter_by(user_account_id=user.id)
            .order_by(FollowList.is_default.desc(), FollowList.created_at.asc(), FollowList.id.asc())
            .all()
        )
        # One query for every list's follows (the dynamic relationship rules out
        # selectinload), grouped by list, then one batched name/team lookup —
        # N+1-free regardless of list count.
        list_ids = [fl.id for fl in lists]
        follows_by_list = {}
        all_follows = []
        if list_ids:
            all_follows = (
                Follow.query.filter(Follow.list_id.in_(list_ids))
                .order_by(Follow.list_id, Follow.created_at.asc(), Follow.id.asc())
                .all()
            )
            for follow in all_follows:
                follows_by_list.setdefault(follow.list_id, []).append(follow)
        name_map, team_map = _follow_label_maps(all_follows)
        return jsonify(
            {
                "lists": [
                    _follow_list_payload(
                        fl, follows=follows_by_list.get(fl.id, []), name_map=name_map, team_map=team_map
                    )
                    for fl in lists
                ]
            }
        )
    except Exception as e:
        logger.error(f"Error in scout_lists: {e}")
        return jsonify(_safe_error_payload(e, "An unexpected error occurred. Please try again later.")), 500


@scout_bp.route("/scout/lists", methods=["POST"])
@require_user_auth
@limiter.limit("30/minute", key_func=_user_rate_limit_key)
def scout_lists_create():
    """Create a follow list (capped at MAX_FOLLOW_LISTS; unique name per user)."""
    try:
        user = _current_user_account()
        if user is None:
            return jsonify({"error": "auth context missing email"}), 401
        payload = request.get_json(silent=True) or {}
        name, error = _clean_list_name(payload.get("name", ""))
        if error:
            return jsonify({"error": error}), 400
        if FollowList.query.filter_by(user_account_id=user.id).count() >= MAX_FOLLOW_LISTS:
            return jsonify({"error": f"list limit reached ({MAX_FOLLOW_LISTS})"}), 409
        if FollowList.query.filter_by(user_account_id=user.id, name=name).first():
            return jsonify({"error": "a list with that name already exists"}), 409
        follow_list = FollowList(user_account_id=user.id, name=name, is_default=False)
        db.session.add(follow_list)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return jsonify({"error": "a list with that name already exists"}), 409
        return jsonify({"list": _follow_list_payload(follow_list, follows=[])}), 201
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in scout_lists_create: {e}")
        return jsonify(_safe_error_payload(e, "An unexpected error occurred. Please try again later.")), 500


@scout_bp.route("/scout/lists/<int:list_id>", methods=["PATCH"])
@require_user_auth
@limiter.limit("30/minute", key_func=_user_rate_limit_key)
def scout_list_update(list_id):
    """Rename a list or toggle is_active (owner-only)."""
    try:
        user = _current_user_account()
        if user is None:
            return jsonify({"error": "auth context missing email"}), 401
        follow_list = _owned_list(user, list_id)
        if follow_list is None:
            return jsonify({"error": "list not found"}), 404
        payload = request.get_json(silent=True) or {}
        if "name" in payload:
            name, error = _clean_list_name(payload.get("name"))
            if error:
                return jsonify({"error": error}), 400
            dup = FollowList.query.filter(
                FollowList.user_account_id == user.id,
                FollowList.name == name,
                FollowList.id != follow_list.id,
            ).first()
            if dup:
                return jsonify({"error": "a list with that name already exists"}), 409
            follow_list.name = name
        if "is_active" in payload:
            is_active = payload.get("is_active")
            if not isinstance(is_active, bool):
                return jsonify({"error": "is_active must be a boolean"}), 400
            follow_list.is_active = is_active
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return jsonify({"error": "a list with that name already exists"}), 409
        return jsonify({"list": _follow_list_payload(follow_list)})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in scout_list_update: {e}")
        return jsonify(_safe_error_payload(e, "An unexpected error occurred. Please try again later.")), 500


@scout_bp.route("/scout/lists/<int:list_id>", methods=["DELETE"])
@require_user_auth
@limiter.limit("30/minute", key_func=_user_rate_limit_key)
def scout_list_delete(list_id):
    """Delete a list (owner-only). The default list is not deletable."""
    try:
        user = _current_user_account()
        if user is None:
            return jsonify({"error": "auth context missing email"}), 401
        follow_list = _owned_list(user, list_id)
        if follow_list is None:
            return jsonify({"error": "list not found"}), 404
        if follow_list.is_default:
            return jsonify({"error": "the default list cannot be deleted"}), 400
        db.session.delete(follow_list)
        db.session.commit()
        return jsonify({"deleted": True})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in scout_list_delete: {e}")
        return jsonify(_safe_error_payload(e, "An unexpected error occurred. Please try again later.")), 500


@scout_bp.route("/scout/lists/<int:list_id>/follows", methods=["POST"])
@require_user_auth
@limiter.limit("30/minute", key_func=_user_rate_limit_key)
def scout_list_add_follow(list_id):
    """Add a follow (player | academy_club | geo | query) to a list.

    A player-kind follow whose target is outside the tracked universe mints a
    PlayerShadow, subject to SHADOW_FOLLOW_LIMIT distinct worldwide follows per
    user.
    """
    try:
        user = _current_user_account()
        if user is None:
            return jsonify({"error": "auth context missing email"}), 401
        follow_list = _owned_list(user, list_id)
        if follow_list is None:
            return jsonify({"error": "list not found"}), 404

        payload = request.get_json(silent=True) or {}
        kind = payload.get("kind")
        clean_selector, error = validate_selector(kind, payload.get("selector"))
        if error:
            return jsonify({"error": error}), 400

        if follow_list.follows.count() >= MAX_FOLLOWS_PER_LIST:
            return jsonify({"error": f"follow limit reached for this list ({MAX_FOLLOWS_PER_LIST})"}), 409

        for follow in follow_list.follows.filter(Follow.kind == kind).all():
            if follow.selector == clean_selector:
                return jsonify({"error": "this follow already exists in the list"}), 409

        note = payload.get("note")
        if note is not None:
            if not isinstance(note, str):
                return jsonify({"error": "note must be a string"}), 400
            note = sanitize_plain_text(note).strip()
            if len(note) > MAX_NOTE_LENGTH:
                return jsonify({"error": f"note must be at most {MAX_NOTE_LENGTH} characters"}), 400
            note = note or None

        shadow_created = False
        if kind == "player":
            player_api_id = clean_selector["player_api_id"]
            tracked = (
                TrackedPlayer.query.filter_by(player_api_id=player_api_id, is_active=True)
                .filter(TrackedPlayer.data_source != "owning-club")
                .first()
            )
            if tracked:
                label = derive_label("player", clean_selector, tracked.player_name)
            else:
                shadow = PlayerShadow.query.filter_by(player_api_id=player_api_id, is_active=True).first()
                # Cap distinct worldwide follows per user (a new shadow, or an
                # existing shadow this user does not already follow).
                if not _user_already_follows_player(user.id, player_api_id):
                    if user_shadow_follow_count(user.id) >= SHADOW_FOLLOW_LIMIT:
                        return jsonify({"error": f"worldwide follow limit reached ({SHADOW_FOLLOW_LIMIT})"}), 403
                if shadow is None:
                    seed = payload.get("seed") if isinstance(payload.get("seed"), dict) else None
                    shadow = mint_shadow(player_api_id, seed=seed, requested_by=user.id, api_client=_get_api_client())
                    shadow_created = True
                label = derive_label("player", clean_selector, shadow.player_name)
        elif kind == "academy_club":
            team = Team.query.filter_by(id=clean_selector["team_id"]).first()
            label = derive_label("academy_club", clean_selector, team.name if team else None)
        else:
            label = derive_label(kind, clean_selector)

        follow = Follow(list_id=follow_list.id, kind=kind, selector=clean_selector, label=label, note=note)
        db.session.add(follow)
        db.session.commit()
        return jsonify({"follow": _follow_payload(follow), "shadow_created": shadow_created}), 201
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in scout_list_add_follow: {e}")
        return jsonify(_safe_error_payload(e, "An unexpected error occurred. Please try again later.")), 500


@scout_bp.route("/scout/lists/<int:list_id>/follows/<int:follow_id>", methods=["DELETE"])
@require_user_auth
@limiter.limit("30/minute", key_func=_user_rate_limit_key)
def scout_list_remove_follow(list_id, follow_id):
    """Remove a follow from a list (owner-only). Idempotent."""
    try:
        user = _current_user_account()
        if user is None:
            return jsonify({"error": "auth context missing email"}), 401
        follow_list = _owned_list(user, list_id)
        if follow_list is None:
            return jsonify({"error": "list not found"}), 404
        follow = Follow.query.filter_by(id=follow_id, list_id=follow_list.id).first()
        if follow is None:
            return jsonify({"removed": False})
        db.session.delete(follow)
        db.session.commit()
        return jsonify({"removed": True})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in scout_list_remove_follow: {e}")
        return jsonify(_safe_error_payload(e, "An unexpected error occurred. Please try again later.")), 500


@scout_bp.route("/scout/lists/<int:list_id>/resolve", methods=["GET"])
@require_user_auth
@limiter.limit("60/minute", key_func=_user_rate_limit_key)
def scout_list_resolve(list_id):
    """Resolved player preview for a list (owner-only), paginated."""
    try:
        user = _current_user_account()
        if user is None:
            return jsonify({"error": "auth context missing email"}), 401
        follow_list = _owned_list(user, list_id)
        if follow_list is None:
            return jsonify({"error": "list not found"}), 404

        limit = min(max(request.args.get("limit", 25, type=int), 1), MAX_RESOLVE_PAGE)
        offset = max(request.args.get("offset", 0, type=int), 0)

        resolved = resolve_list(follow_list)
        total = len(resolved)
        page = resolved[offset : offset + limit]

        tracked_ids = [item["player_api_id"] for item in page if item["source"] == "tracked"]
        shadow_ids = [item["player_api_id"] for item in page if item["source"] == "shadow"]
        tracked_dicts = _watched_player_dicts(tracked_ids)
        shadows = {}
        if shadow_ids:
            for shadow in PlayerShadow.query.filter(PlayerShadow.player_api_id.in_(shadow_ids)).all():
                shadows[shadow.player_api_id] = shadow

        players = []
        for item in page:
            player_api_id = item["player_api_id"]
            if item["source"] == "tracked":
                enriched = tracked_dicts.get(player_api_id)
                players.append(
                    {
                        "player_api_id": player_api_id,
                        "player_name": enriched.get("player_name") if enriched else None,
                        "source": "tracked",
                        "team_name": (enriched.get("loan_team_name") or enriched.get("primary_team_name"))
                        if enriched
                        else None,
                        "status": enriched.get("status") if enriched else None,
                        "photo": enriched.get("player_photo") if enriched else None,
                    }
                )
            else:
                shadow = shadows.get(player_api_id)
                players.append(
                    {
                        "player_api_id": player_api_id,
                        "player_name": shadow.player_name if shadow else None,
                        "source": "shadow",
                        "team_name": shadow.current_club_name if shadow else None,
                        "status": None,
                        "photo": shadow.photo_url if shadow else None,
                    }
                )
        return jsonify({"players": players, "total": total})
    except Exception as e:
        logger.error(f"Error in scout_list_resolve: {e}")
        return jsonify(_safe_error_payload(e, "An unexpected error occurred. Please try again later.")), 500


@scout_bp.route("/scout/player-search", methods=["GET"])
@require_user_auth
@limiter.limit("10/minute", key_func=_user_rate_limit_key)
def scout_player_search():
    """Worldwide player search for adding follows. Stub-safe (returns [])."""
    try:
        user = _current_user_account()
        if user is None:
            return jsonify({"error": "auth context missing email"}), 401
        query = request.args.get("q", "").strip()
        results = search_players(query, api_client=_get_api_client())
        return jsonify({"players": results})
    except Exception as e:
        logger.error(f"Error in scout_player_search: {e}")
        return jsonify(_safe_error_payload(e, "An unexpected error occurred. Please try again later.")), 500


@scout_bp.route("/admin/scout/shadow-refresh", methods=["POST"])
@require_api_key
def scout_admin_shadow_refresh():
    """Refresh the N stalest active shadows (profile + season stats)."""
    try:
        payload = request.get_json(silent=True) or {}
        limit = payload.get("limit", 25)
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            return jsonify({"error": "limit must be a positive integer"}), 400
        cursor = payload.get("cursor")
        if cursor is not None and (not isinstance(cursor, int) or isinstance(cursor, bool) or cursor < 0):
            return jsonify({"error": "cursor must be a non-negative integer"}), 400
        result = refresh_shadows(limit=limit, cursor=cursor, api_client=_get_api_client())
        return jsonify(result)
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in scout_admin_shadow_refresh: {e}")
        return jsonify(_safe_error_payload(e, "An unexpected error occurred. Please try again later.")), 500


@scout_bp.route("/admin/scout/backfill-follow-lists", methods=["POST"])
@require_api_key
def scout_admin_backfill_follow_lists():
    """Backfill a default follow list from each user's watchlist (cursor-paged).

    Per user with watchlist entries and no default list: create a default
    FollowList + one player follow per entry (carrying its note) and copy the
    entry's last_snapshot into a FollowPlayerSnapshot. Idempotent — users who
    already have a default list are skipped.
    """
    try:
        payload = request.get_json(silent=True) or {}
        dry_run = payload.get("dry_run", True)
        if not isinstance(dry_run, bool):
            return jsonify({"error": "dry_run must be a boolean"}), 400
        limit = payload.get("limit", 50)
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            return jsonify({"error": "limit must be a positive integer"}), 400
        limit = min(limit, 200)
        cursor = payload.get("cursor", 0)
        if not isinstance(cursor, int) or isinstance(cursor, bool) or cursor < 0:
            return jsonify({"error": "cursor must be a non-negative integer"}), 400

        has_watchlist = exists().where(ScoutWatchlistEntry.user_account_id == UserAccount.id)
        has_default = exists().where(
            and_(FollowList.user_account_id == UserAccount.id, FollowList.is_default.is_(True))
        )
        users = (
            db.session.query(UserAccount)
            .filter(UserAccount.id > cursor, has_watchlist, ~has_default)
            .order_by(UserAccount.id)
            .limit(limit)
            .all()
        )
        next_cursor = users[-1].id if len(users) == limit else None

        lists_created = 0
        follows_created = 0
        snapshots_created = 0
        for user in users:
            follow_list = FollowList(user_account_id=user.id, name="My Watchlist", is_default=True)
            db.session.add(follow_list)
            db.session.flush()
            lists_created += 1

            entries = ScoutWatchlistEntry.query.filter_by(user_account_id=user.id).all()
            pids = [entry.player_api_id for entry in entries]
            name_map = {}
            if pids:
                name_map = {
                    tp.player_api_id: tp.player_name
                    for tp in TrackedPlayer.query.filter(
                        TrackedPlayer.player_api_id.in_(pids),
                        TrackedPlayer.is_active.is_(True),
                        TrackedPlayer.data_source != "owning-club",
                    ).all()
                }
            for entry in entries:
                db.session.add(
                    Follow(
                        list_id=follow_list.id,
                        kind="player",
                        selector={"player_api_id": entry.player_api_id},
                        label=derive_label(
                            "player",
                            {"player_api_id": entry.player_api_id},
                            name_map.get(entry.player_api_id),
                        ),
                        note=entry.note,
                    )
                )
                follows_created += 1
                existing_snap = FollowPlayerSnapshot.query.filter_by(
                    user_account_id=user.id, player_api_id=entry.player_api_id
                ).first()
                if existing_snap is None:
                    db.session.add(
                        FollowPlayerSnapshot(
                            user_account_id=user.id,
                            player_api_id=entry.player_api_id,
                            last_snapshot=entry.last_snapshot,
                            last_digest_at=entry.last_digest_at,
                            note=entry.note,
                        )
                    )
                    snapshots_created += 1

        result = {
            "users_processed": len(users),
            "lists_created": lists_created,
            "follows_created": follows_created,
            "snapshots_created": snapshots_created,
            "next_cursor": next_cursor,
            "dry_run": dry_run,
            "applied": not dry_run,
        }
        if dry_run:
            db.session.rollback()
        else:
            db.session.commit()
        return jsonify(result)
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in scout_admin_backfill_follow_lists: {e}")
        return jsonify(_safe_error_payload(e, "An unexpected error occurred. Please try again later.")), 500


# =========================================================================== #
# Player pulse + shared AI cards (admin ops until the Phase-3 scheduler exists)
# =========================================================================== #


def _parse_window_end(raw):
    """(date, error). Defaults to today when omitted/blank."""
    if raw is None or raw == "":
        return date.today(), None
    if not isinstance(raw, str):
        return None, "window_end must be a date string (YYYY-MM-DD)"
    try:
        return date.fromisoformat(raw), None
    except ValueError:
        return None, "window_end must be a valid date (YYYY-MM-DD)"


@scout_bp.route("/admin/pulse/compute", methods=["POST"])
@require_api_key
def scout_admin_pulse_compute():
    """Compute deterministic player_pulse scores for a window (admin; NO LLM).

    Body: {window_end?: "YYYY-MM-DD" (default today), dry_run?: bool (default
    True)}. compute_pulse dedups every followed player across all active lists +
    legacy watchlists and upserts one row per (player, window); it owns its own
    persistence and honours dry_run (score + preview, write nothing). Returns the
    service's counts + top scored preview.
    """
    try:
        payload = request.get_json(silent=True) or {}
        window_end, error = _parse_window_end(payload.get("window_end"))
        if error:
            return jsonify({"error": error}), 400
        dry_run = payload.get("dry_run", True)
        if not isinstance(dry_run, bool):
            return jsonify({"error": "dry_run must be a boolean"}), 400

        from src.services.player_pulse_service import compute_pulse

        result = compute_pulse(window_end, dry_run=dry_run)
        if not isinstance(result, dict):
            result = {"result": result}
        result.setdefault("window_end", window_end.isoformat())
        result["dry_run"] = dry_run
        result["applied"] = not dry_run
        return jsonify(result)
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in scout_admin_pulse_compute: {e}")
        return jsonify(_safe_error_payload(e, "An unexpected error occurred. Please try again later.")), 500


@scout_bp.route("/admin/pulse/generate-cards", methods=["POST"])
@require_api_key
def scout_admin_pulse_generate_cards():
    """Generate shared AI cards for high-pulse players (admin; THE LLM step).

    Body: {window_end?, threshold? (default env PULSE_CARD_THRESHOLD=3.0),
    limit? (default env PULSE_CARD_LIMIT=100), dry_run? (default True)}.
    generate_cards owns persistence + honours dry_run — a dry run lists the
    candidates (pulse >= threshold with no cached card) and makes ZERO LLM calls /
    writes nothing. Returns {generated, skipped_cached, candidates, ...}.
    """
    try:
        payload = request.get_json(silent=True) or {}
        window_end, error = _parse_window_end(payload.get("window_end"))
        if error:
            return jsonify({"error": error}), 400
        dry_run = payload.get("dry_run", True)
        if not isinstance(dry_run, bool):
            return jsonify({"error": "dry_run must be a boolean"}), 400

        threshold = payload.get("threshold")
        if threshold is not None and (isinstance(threshold, bool) or not isinstance(threshold, (int, float))):
            return jsonify({"error": "threshold must be a number"}), 400

        limit = payload.get("limit")
        if limit is not None:
            if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
                return jsonify({"error": "limit must be a positive integer"}), 400
            limit = min(limit, MAX_PULSE_CARD_LIMIT)

        # threshold/limit left as None fall back to the service's env defaults
        # (PULSE_CARD_THRESHOLD / PULSE_CARD_LIMIT).
        from src.services.player_card_service import generate_cards

        result = generate_cards(window_end, threshold, limit, dry_run=dry_run)
        if not isinstance(result, dict):
            result = {"result": result}
        result.setdefault("window_end", window_end.isoformat())
        result["dry_run"] = dry_run
        result["applied"] = not dry_run
        return jsonify(result)
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in scout_admin_pulse_generate_cards: {e}")
        return jsonify(_safe_error_payload(e, "An unexpected error occurred. Please try again later.")), 500
