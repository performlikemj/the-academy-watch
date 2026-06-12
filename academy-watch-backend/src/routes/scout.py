"""Scout blueprint — public cross-club talent discovery endpoints.

Gives scouts a way to browse, rank, and compare every tracked academy/loan
player across clubs and leagues, instead of navigating team-by-team.

Endpoints (all public):
- GET /scout/players       — filter/sort/paginate all tracked players with stats
- GET /scout/leaderboards  — top scorers / assists / minutes / per-90 boards
- GET /scout/compare       — side-by-side comparison of up to 4 players

Stats are aggregated in SQL: FixturePlayerStats (full coverage) with a
PlayerStatsCache fallback (limited coverage) merged via COALESCE, so no
per-player compute_stats() N+1 queries.
"""

import logging

from flask import Blueprint, jsonify, request
from sqlalchemy import and_, case, exists, func, or_, tuple_
from sqlalchemy.orm import aliased
from src.auth import _safe_error_payload
from src.models.league import PlayerStatsCache, db
from src.models.tracked_player import TrackedPlayer
from src.models.weekly import Fixture, FixturePlayerStats

logger = logging.getLogger(__name__)

scout_bp = Blueprint("scout", __name__)

VALID_POSITIONS = {"Goalkeeper", "Defender", "Midfielder", "Attacker"}
VALID_STATUSES = {"academy", "on_loan", "first_team", "released", "sold"}
PER90_MIN_MINUTES = 270  # floor for per-90 rankings so 10-minute cameos don't top the boards
MAX_PER_PAGE = 100
MAX_COMPARE_PLAYERS = 4
FORM_MATCHES = 5


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

    rows = (
        db.session.query(
            FixturePlayerStats.player_api_id,
            FixturePlayerStats.team_api_id,
            FixturePlayerStats.minutes,
            FixturePlayerStats.goals,
            FixturePlayerStats.assists,
            FixturePlayerStats.rating,
            Fixture.date_utc,
        )
        .join(Fixture, Fixture.id == FixturePlayerStats.fixture_id)
        .filter(tuple_(FixturePlayerStats.player_api_id, FixturePlayerStats.team_api_id).in_(list(pairs)))
        .order_by(Fixture.date_utc.desc().nullslast())
        .all()
    )

    form_by_pair = {}
    for row in rows:
        key = (row.player_api_id, row.team_api_id)
        matches = form_by_pair.setdefault(key, [])
        if len(matches) >= FORM_MATCHES:
            continue
        matches.append(
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


def _fixture_stats_subquery():
    """Aggregate FixturePlayerStats per (player, team)."""
    return (
        db.session.query(
            FixturePlayerStats.player_api_id.label("player_api_id"),
            FixturePlayerStats.team_api_id.label("team_api_id"),
            func.count(FixturePlayerStats.id).label("appearances"),
            func.coalesce(func.sum(FixturePlayerStats.goals), 0).label("goals"),
            func.coalesce(func.sum(FixturePlayerStats.assists), 0).label("assists"),
            func.coalesce(func.sum(FixturePlayerStats.minutes), 0).label("minutes_played"),
            func.avg(FixturePlayerStats.rating).label("avg_rating"),
        )
        .group_by(FixturePlayerStats.player_api_id, FixturePlayerStats.team_api_id)
        .subquery()
    )


def _cache_stats_subquery():
    """Latest-season PlayerStatsCache row per (player, team)."""
    latest = (
        db.session.query(
            PlayerStatsCache.player_api_id.label("player_api_id"),
            PlayerStatsCache.team_api_id.label("team_api_id"),
            func.max(PlayerStatsCache.season).label("season"),
        )
        .group_by(PlayerStatsCache.player_api_id, PlayerStatsCache.team_api_id)
        .subquery()
    )
    return (
        db.session.query(
            PlayerStatsCache.player_api_id.label("player_api_id"),
            PlayerStatsCache.team_api_id.label("team_api_id"),
            PlayerStatsCache.appearances.label("appearances"),
            PlayerStatsCache.goals.label("goals"),
            PlayerStatsCache.assists.label("assists"),
            PlayerStatsCache.minutes_played.label("minutes_played"),
        )
        .join(
            latest,
            and_(
                PlayerStatsCache.player_api_id == latest.c.player_api_id,
                PlayerStatsCache.team_api_id == latest.c.team_api_id,
                PlayerStatsCache.season == latest.c.season,
            ),
        )
        .subquery()
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
    fps = _fixture_stats_subquery()
    cache = _cache_stats_subquery()

    goals = func.coalesce(fps.c.goals, cache.c.goals, 0).label("goals")
    assists = func.coalesce(fps.c.assists, cache.c.assists, 0).label("assists")
    minutes = func.coalesce(fps.c.minutes_played, cache.c.minutes_played, 0).label("minutes_played")
    appearances = func.coalesce(fps.c.appearances, cache.c.appearances, 0).label("appearances")
    avg_rating = fps.c.avg_rating.label("avg_rating")

    query = (
        db.session.query(TrackedPlayer, goals, assists, minutes, appearances, avg_rating)
        .outerjoin(
            fps,
            and_(
                fps.c.player_api_id == TrackedPlayer.player_api_id,
                fps.c.team_api_id == TrackedPlayer.current_club_api_id,
            ),
        )
        .outerjoin(
            cache,
            and_(
                cache.c.player_api_id == TrackedPlayer.player_api_id,
                cache.c.team_api_id == TrackedPlayer.current_club_api_id,
            ),
        )
        .filter(TrackedPlayer.is_active.is_(True))
        .filter(_preferred_row_filter())
    )
    columns = {
        "goals": goals,
        "assists": assists,
        "minutes_played": minutes,
        "appearances": appearances,
        "avg_rating": avg_rating,
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
        query = query.filter(TrackedPlayer.status.in_(statuses))

    min_age = request.args.get("min_age", type=int)
    if min_age is not None:
        query = query.filter(TrackedPlayer.age >= min_age)
    max_age = request.args.get("max_age", type=int)
    if max_age is not None:
        query = query.filter(TrackedPlayer.age <= max_age)

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
        "age": TrackedPlayer.age,
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

        own_priority = case((TrackedPlayer.data_source == "owning-club", 1), else_=0)
        players = []
        for player_id in player_ids:
            tracked_player = (
                TrackedPlayer.query.filter_by(player_api_id=player_id, is_active=True)
                .order_by(own_priority, TrackedPlayer.id)
                .first()
            )
            if not tracked_player:
                continue

            totals = None
            if tracked_player.current_club_api_id:
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
                    .filter(
                        FixturePlayerStats.player_api_id == player_id,
                        FixturePlayerStats.team_api_id == tracked_player.current_club_api_id,
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
                # Fall back to basic limited-coverage stats
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

            players.append(
                {
                    "profile": tracked_player.to_public_dict(),
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
