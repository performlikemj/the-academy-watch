"""Teams blueprint for team and league endpoints.

This blueprint handles:
- League listings
- Gameweek information
- Team listings and details
- Team loan information
- Academy network visualization
"""

import logging
from datetime import UTC, datetime

from flask import Blueprint, jsonify, request
from sqlalchemy import cast
from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB
from src.auth import _safe_error_payload
from src.models.journey import ClubLocation, PlayerJourney, PlayerJourneyEntry
from src.models.league import (
    League,
    Player,
    Team,
    TeamProfile,
    db,
)
from src.models.tracked_player import TrackedPlayer
from src.utils.academy_classifier import _get_latest_season, classify_tracked_player, is_same_club
from src.utils.geocoding import get_team_coordinates
from src.utils.slug import resolve_team_by_identifier
from werkzeug.exceptions import NotFound

logger = logging.getLogger(__name__)

teams_bp = Blueprint("teams", __name__)


# Lazy import for api_client to avoid circular imports and early initialization
def _get_api_client():
    from src.routes.api import api_client

    return api_client


def _inject_slugs(team_dicts: list[dict], teams: list) -> None:
    """Batch-fetch slugs from TeamProfile and inject into team dicts."""
    api_ids = list({t.team_id for t in teams})
    if not api_ids:
        return
    profiles = TeamProfile.query.filter(TeamProfile.team_id.in_(api_ids)).all()
    slug_map = {p.team_id: p.slug for p in profiles}
    for td in team_dicts:
        td["slug"] = slug_map.get(td["team_id"])


def _get_team_slug(team) -> str | None:
    """Get slug for a single team from its TeamProfile."""
    profile = TeamProfile.query.filter_by(team_id=team.team_id).first()
    return profile.slug if profile else None


# Expose api_client as a module-level attribute for patching in tests
class _LazyApiClient:
    def __getattr__(self, name):
        return getattr(_get_api_client(), name)


api_client = _LazyApiClient()


# ---------------------------------------------------------------------------
# League endpoints
# ---------------------------------------------------------------------------


@teams_bp.route("/leagues", methods=["GET"])
def get_leagues():
    """Get all European leagues."""
    try:
        leagues = League.query.filter_by(is_european_top_league=True).all()
        return jsonify([league.to_dict() for league in leagues])
    except Exception as e:
        return jsonify(_safe_error_payload(e, "An unexpected error occurred. Please try again later.")), 500


# ---------------------------------------------------------------------------
# Gameweek endpoints
# ---------------------------------------------------------------------------


@teams_bp.route("/gameweeks", methods=["GET"])
def get_gameweeks():
    """Get available gameweeks for the season."""
    try:
        season = request.args.get("season", type=int)
        from src.utils.gameweeks import get_season_gameweeks

        weeks = get_season_gameweeks(season_start_year=season)
        return jsonify(weeks)
    except Exception as e:
        logger.error(f"Error getting gameweeks: {e}")
        return jsonify(_safe_error_payload(e, "An unexpected error occurred. Please try again later.")), 500


# ---------------------------------------------------------------------------
# Team endpoints
# ---------------------------------------------------------------------------


@teams_bp.route("/teams", methods=["GET"])
def get_teams():
    """Get all teams with optional filtering.

    Query params:
    - season: Filter by season year
    - european_only: Filter to European top leagues only
    - has_loans: Filter to teams with active loans
    - search: Filter by name search
    """
    try:
        logger.info("GET /teams endpoint called")
        logger.info(f"Request args: {dict(request.args)}")

        # Check database connection and teams table
        total_teams = Team.query.count()
        logger.info(f"Total teams in database: {total_teams}")

        # Start with base query for active teams
        query = Team.query.filter_by(is_active=True)

        # Handle season filter
        season = request.args.get("season", type=int)
        if season:
            logger.info(f"Filtering for season: {season}")
            query = query.filter_by(season=season)

        # Handle european_only filter
        european_only = request.args.get("european_only", "").lower() == "true"
        if european_only:
            logger.info("Filtering for European teams only")
            european_leagues = ["Premier League", "La Liga", "Serie A", "Bundesliga", "Ligue 1"]
            query = query.join(League).filter(League.name.in_(european_leagues))

        # Handle has_loans filter
        has_loans = request.args.get("has_loans", "").lower() == "true"
        if has_loans:
            logger.info("Filtering for teams with active tracked players")
            query = (
                query.join(TrackedPlayer, Team.id == TrackedPlayer.team_id)
                .filter(TrackedPlayer.is_active.is_(True))
                .distinct()
            )

        # Handle search filter (for global search)
        search = request.args.get("search", "").strip()
        if search:
            logger.info(f"Searching teams for: {search}")
            query = query.filter(Team.name.ilike(f"%{search}%"))

        teams = query.all()
        active_teams_count = len(teams)
        logger.info(f"Filtered teams found: {active_teams_count}")

        # Deduplicate teams by team_id, keeping the latest season
        deduped_teams = {}
        for team in teams:
            existing = deduped_teams.get(team.team_id)
            if not existing or team.season > existing.season:
                deduped_teams[team.team_id] = team

        teams = list(deduped_teams.values())
        # Sort by name for consistent display
        teams.sort(key=lambda x: x.name)

        if active_teams_count == 0 and european_only:
            # Lazy sync logic for European teams when none found
            try:
                _lazy_sync_european_teams(season)
                # Re-run the filtered query
                query = Team.query.filter_by(is_active=True)
                if season:
                    query = query.filter_by(season=season)
                if european_only:
                    european_leagues = ["Premier League", "La Liga", "Serie A", "Bundesliga", "Ligue 1"]
                    query = query.join(League).filter(League.name.in_(european_leagues))
                teams = query.all()
            except Exception as sync_ex:
                logger.error(f"Lazy sync failed: {sync_ex}")

        team_dicts = [team.to_dict() for team in teams]

        # Override loan counts with tracked-player counts
        team_db_ids = [t.id for t in teams]
        if team_db_ids:
            from sqlalchemy import func as sa_func

            tp_counts = dict(
                db.session.query(
                    TrackedPlayer.team_id,
                    sa_func.count(TrackedPlayer.id),
                )
                .filter(
                    TrackedPlayer.team_id.in_(team_db_ids),
                    TrackedPlayer.is_active.is_(True),
                )
                .group_by(TrackedPlayer.team_id)
                .all()
            )
            for td in team_dicts:
                td["tracked_player_count"] = tp_counts.get(td["id"], 0)

        _inject_slugs(team_dicts, teams)
        logger.info(f"Returning {len(team_dicts)} team records")

        return jsonify(team_dicts)
    except Exception as e:
        logger.error(f"Error in get_teams: {str(e)}")
        import traceback

        logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify(_safe_error_payload(e, "An unexpected error occurred. Please try again later.")), 500


def _lazy_sync_european_teams(season: int | None):
    """Lazily sync European teams if none exist in database."""
    real_client = _get_api_client()
    season = season or real_client.current_season_start_year
    logger.info(f"Attempting lazy sync for European top leagues for season {season}")

    # Sync leagues (top-5)
    leagues_data = real_client.get_european_leagues(season)
    for league_data in leagues_data:
        league_info = league_data.get("league", {})
        country_info = league_data.get("country", {})
        seasons = league_data.get("seasons", [])
        current_season = next((s for s in seasons if s.get("current")), seasons[0] if seasons else {})
        existing = League.query.filter_by(league_id=league_info.get("id")).first()
        if existing:
            existing.name = league_info.get("name")
            existing.country = country_info.get("name")
            existing.season = current_season.get("year", real_client.current_season_start_year)
            existing.logo = league_info.get("logo")
            existing.is_european_top_league = True
        else:
            db.session.add(
                League(
                    league_id=league_info.get("id"),
                    name=league_info.get("name"),
                    country=country_info.get("name"),
                    season=current_season.get("year", real_client.current_season_start_year),
                    is_european_top_league=True,
                    logo=league_info.get("logo"),
                )
            )

    # Sync teams for those leagues
    all_teams = real_client.get_all_european_teams(season)
    for team_data in all_teams:
        team_info = team_data.get("team", {})
        league_info = team_data.get("league_info", {})
        league = League.query.filter_by(league_id=league_info.get("id")).first()
        if not league:
            continue
        existing_team = Team.query.filter_by(team_id=team_info.get("id"), season=season).first()
        if existing_team:
            existing_team.name = team_info.get("name")
            existing_team.country = team_info.get("country")
            existing_team.founded = team_info.get("founded")
            existing_team.logo = team_info.get("logo")
            existing_team.league_id = league.id
            existing_team.is_active = True
        else:
            db.session.add(
                Team(
                    team_id=team_info.get("id"),
                    name=team_info.get("name"),
                    country=team_info.get("country"),
                    founded=team_info.get("founded"),
                    logo=team_info.get("logo"),
                    league_id=league.id,
                    season=season,
                    is_active=True,
                )
            )
    db.session.commit()
    logger.info("Lazy sync complete")


@teams_bp.route("/teams/<team_identifier>", methods=["GET"])
def get_team(team_identifier):
    """Get specific team with tracked player summary."""
    try:
        team = resolve_team_by_identifier(team_identifier)
        team_dict = team.to_dict()
        team_dict["slug"] = _get_team_slug(team)

        # Include tracked player count + status breakdown
        tracked = TrackedPlayer.query.filter_by(team_id=team.id, is_active=True).all()
        team_dict["tracked_player_count"] = len(tracked)
        team_dict["tracked_status_breakdown"] = {}
        for tp in tracked:
            status = tp.status or "unknown"
            team_dict["tracked_status_breakdown"][status] = team_dict["tracked_status_breakdown"].get(status, 0) + 1

        # Keep active_loans for backward compat (e.g. old newsletter code)
        active_players = team.unique_active_players()
        team_dict["active_loans"] = [p.to_dict() for p in active_players]

        return jsonify(team_dict)
    except NotFound:
        raise
    except Exception as e:
        return jsonify(_safe_error_payload(e, "An unexpected error occurred. Please try again later.")), 500


@teams_bp.route("/teams/<team_identifier>/loans", methods=["GET"])
def get_team_loans(team_identifier):
    """Get loans for a specific team.

    Query params:
    - direction: 'loaned_from' (default) to show players loaned OUT from this team,
                 'loaned_to' to show players loaned TO this team
    - active_only: filter to only active loans (default: true)
    - dedupe: deduplicate loans by player_id (default: true)
    - season: filter by season year
    - include_supplemental: include supplemental loans (default: false)
    - include_season_context: enrich with season stats (default: false)
    - pathway_status: filter by pathway status (e.g. 'academy', 'on_loan')
    - academy_only: filter to players with this team in their academy_club_ids (default: false)
    - aggregate_stats: when deduping, sum stats across all loan spells per player (default: false)
    """
    try:
        team = resolve_team_by_identifier(team_identifier)
        active_only = request.args.get("active_only", "true").lower() in ("1", "true", "yes", "on", "y")
        dedupe = request.args.get("dedupe", "true").lower() in ("1", "true", "yes", "on", "y")
        season_val = request.args.get("season", type=int)
        direction = request.args.get("direction", "loaned_from").lower()
        pathway_status = request.args.get("pathway_status", "").strip().lower()
        academy_only = request.args.get("academy_only", "false").lower() in ("1", "true", "yes", "on", "y")

        # Query TrackedPlayer by direction
        if direction == "loaned_to":
            tp_query = TrackedPlayer.query.filter_by(current_club_db_id=team.id)
        else:
            tp_query = TrackedPlayer.query.filter_by(team_id=team.id)

        if active_only:
            tp_query = tp_query.filter(TrackedPlayer.is_active.is_(True))

        if pathway_status:
            tp_query = tp_query.filter(TrackedPlayer.status == pathway_status)

        # Filter to academy products using JSONB @> containment
        if academy_only:
            from sqlalchemy import or_

            tp_query = tp_query.outerjoin(
                PlayerJourney, TrackedPlayer.player_api_id == PlayerJourney.player_api_id
            ).filter(
                or_(
                    PlayerJourney.id.is_(None),
                    PlayerJourney.academy_club_ids.contains(cast([team.team_id], PG_JSONB)),
                )
            )

        tracked = tp_query.order_by(TrackedPlayer.updated_at.desc()).all()

        # Batch-fetch stats for all TrackedPlayers
        from sqlalchemy import func as sa_func
        from src.models.weekly import FixturePlayerStats

        tp_api_ids = [tp.player_api_id for tp in tracked]
        stats_by_player = {}
        if tp_api_ids:
            stats_rows = (
                db.session.query(
                    FixturePlayerStats.player_api_id,
                    sa_func.count().label("appearances"),
                    sa_func.coalesce(sa_func.sum(FixturePlayerStats.goals), 0).label("goals"),
                    sa_func.coalesce(sa_func.sum(FixturePlayerStats.assists), 0).label("assists"),
                    sa_func.coalesce(sa_func.sum(FixturePlayerStats.minutes), 0).label("minutes_played"),
                )
                .filter(FixturePlayerStats.player_api_id.in_(tp_api_ids))
                .group_by(FixturePlayerStats.player_api_id)
                .all()
            )
            for row in stats_rows:
                stats_by_player[row.player_api_id] = {
                    "appearances": row.appearances,
                    "goals": int(row.goals),
                    "assists": int(row.assists),
                    "minutes_played": int(row.minutes_played),
                }

        result = []
        for tp in tracked:
            tp_dict = tp.to_public_dict()
            if tp.player_api_id in stats_by_player:
                tp_dict.update(stats_by_player[tp.player_api_id])
            result.append(tp_dict)

        # Supplemental loans removed (deprecated SupplementalLoan table)

        return jsonify(result)
    except NotFound:
        raise
    except Exception as e:
        return jsonify(_safe_error_payload(e, "An unexpected error occurred. Please try again later.")), 500


def _get_player_photo(player_id: int) -> str | None:
    """Get player photo URL."""
    try:
        from src.agents.weekly_agent import _player_photo_for

        return _player_photo_for(player_id)
    except Exception:
        return None


def _get_player_position(player_id: int) -> str | None:
    """Get player position from Player table."""
    try:
        player = Player.query.filter_by(player_id=player_id).first()
        return player.position if player else None
    except Exception:
        return None


def _get_team_logo(team_api_id: int) -> str | None:
    """Get team logo URL."""
    try:
        from src.agents.weekly_agent import _team_logo_for_team

        return _team_logo_for_team(team_api_id)
    except Exception:
        return None


@teams_bp.route("/teams/<team_identifier>/loans/season/<int:season>", methods=["GET"])
def get_team_loans_by_season(team_identifier: str, season: int):
    """Get loans for a specific team in a specific season (by window_key prefix)."""
    try:
        team = resolve_team_by_identifier(team_identifier)
        slug = f"{season}-{str(season + 1)[-2:]}"
        active_only = request.args.get("active_only", "false").lower() in ("true", "1", "yes", "y")

        q = TrackedPlayer.query.filter(TrackedPlayer.team_id == team.id)
        if active_only:
            q = q.filter(TrackedPlayer.is_active.is_(True))

        players = q.order_by(TrackedPlayer.updated_at.desc()).all()
        return jsonify([tp.to_public_dict() for tp in players])
    except NotFound:
        raise
    except Exception as e:
        return jsonify(_safe_error_payload(e, "An unexpected error occurred. Please try again later.")), 500


@teams_bp.route("/teams/season/<int:season>", methods=["GET"])
def get_teams_for_season(season):
    """Get all teams for a specific season with their names."""
    try:
        real_client = _get_api_client()
        team_mapping = real_client.get_teams_for_season(season)
        return jsonify({"season": season, "teams": team_mapping, "count": len(team_mapping)})
    except Exception as e:
        logger.error(f"Error fetching teams for season {season}: {e}")
        return jsonify(_safe_error_payload(e, "An unexpected error occurred. Please try again later.")), 500


@teams_bp.route("/teams/<team_identifier>/academy-network", methods=["GET"])
def get_academy_network(team_identifier):
    """Get academy network data for constellation visualization.

    Returns nodes (clubs) and links (player pathways) for a force-directed graph
    showing where a club's academy players end up.

    Query params:
    - years: number of seasons to look back (default 4)
    """
    try:
        resolved_team = resolve_team_by_identifier(team_identifier)
        team_api_id = resolved_team.team_id

        years = request.args.get("years", 4, type=int)
        limit = request.args.get("limit", 200, type=int)
        now = datetime.now(UTC)
        current_season = now.year if now.month >= 8 else now.year - 1
        min_season = current_season - years + 1

        # Find the parent team for name/logo
        parent_team = Team.query.filter_by(team_id=team_api_id, is_active=True).order_by(Team.season.desc()).first()
        if parent_team and parent_team.name:
            parent_name, parent_logo = parent_team.name, parent_team.logo
        else:
            from src.utils.team_resolver import resolve_team_name_and_logo

            parent_name, parent_logo = resolve_team_name_and_logo(team_api_id)

        # Query 1: Academy products — prefer TrackedPlayer, fallback to JSONB
        tp_lookup = {}
        journey_ids = []
        journeys = []

        if parent_team:
            tracked = TrackedPlayer.query.filter_by(team_id=parent_team.id, is_active=True).all()
            for tp in tracked:
                tp_lookup[tp.player_api_id] = tp

        if tp_lookup:
            # TrackedPlayer is source of truth
            tp_journey_ids = [tp.journey_id for tp in tp_lookup.values() if tp.journey_id]
            if tp_journey_ids:
                journeys = PlayerJourney.query.filter(PlayerJourney.id.in_(tp_journey_ids)).all()
            # Also include TrackedPlayers without journeys (they won't have entries
            # but will appear in all_players with zero appearances)
        else:
            # Fallback: legacy JSONB query (before backfill migration runs)
            journeys = PlayerJourney.query.filter(
                PlayerJourney.academy_club_ids.contains(cast([team_api_id], PG_JSONB))
            ).all()

        if not journeys and not tp_lookup:
            return jsonify(
                {
                    "team_api_id": team_api_id,
                    "team_name": parent_name,
                    "team_logo": parent_logo,
                    "season_range": [min_season, current_season],
                    "total_academy_players": 0,
                    "summary": {},
                    "nodes": [],
                    "links": [],
                    "all_players": [],
                }
            )

        journey_ids = [j.id for j in journeys]
        journey_map = {j.id: j for j in journeys}

        # Query 2: All entries in the season window (exclude internationals)
        entries = []
        if journey_ids:
            entries = PlayerJourneyEntry.query.filter(
                PlayerJourneyEntry.journey_id.in_(journey_ids),
                PlayerJourneyEntry.season >= min_season,
                PlayerJourneyEntry.is_international.is_(False),
            ).all()

        # Capture league_country hints for geocoding fallback
        club_country_hint = {}  # club_api_id → league_country
        for entry in entries:
            if entry.club_api_id not in club_country_hint and entry.league_country:
                club_country_hint[entry.club_api_id] = entry.league_country

        # Aggregate: group entries by player and destination club
        # player_clubs[player_api_id][club_api_id] = {stats}
        player_clubs = {}
        for entry in entries:
            journey = journey_map[entry.journey_id]
            pid = journey.player_api_id

            # Fold same-club youth entries into parent node
            dest_id = entry.club_api_id
            dest_name = entry.club_name
            dest_logo = entry.club_logo
            if is_same_club(entry.club_name or "", parent_name):
                dest_id = team_api_id
                dest_name = parent_name
                dest_logo = parent_logo

            if pid not in player_clubs:
                player_clubs[pid] = {}

            if dest_id not in player_clubs[pid]:
                player_clubs[pid][dest_id] = {
                    "club_name": dest_name,
                    "club_logo": dest_logo,
                    "appearances": 0,
                    "goals": 0,
                    "assists": 0,
                    "entry_types": set(),
                }

            bucket = player_clubs[pid][dest_id]
            bucket["appearances"] += entry.appearances or 0
            bucket["goals"] += entry.goals or 0
            bucket["assists"] += entry.assists or 0
            bucket["entry_types"].add(entry.entry_type or "unknown")

        # Build per-player ordered club path from entries sorted chronologically
        # (moved before all_players loop so journey_path can be included)
        player_paths = {}  # pid -> [(club_api_id, entry_type), ...]
        for entry in sorted(entries, key=lambda e: (e.season, e.transfer_date or "")):
            journey = journey_map[entry.journey_id]
            pid = journey.player_api_id

            # Fold same-club youth entries into parent node
            dest_id = entry.club_api_id
            if is_same_club(entry.club_name or "", parent_name):
                dest_id = team_api_id

            if pid not in player_paths:
                player_paths[pid] = []

            path = player_paths[pid]
            # Dedupe consecutive same-club stops
            if not path or path[-1][0] != dest_id:
                path.append((dest_id, entry.entry_type or "unknown"))

        # Anchor disconnected players back to parent hub.
        # When a player's academy entries fall outside the season window,
        # their path contains only destination clubs. Prepending the parent
        # ensures a link from the hub to their first visible destination.
        for pid in player_paths:
            club_ids_in_path = {cid for cid, _ in player_paths[pid]}
            if team_api_id not in club_ids_in_path and player_paths[pid]:
                player_paths[pid].insert(0, (team_api_id, "academy"))

        # Build club_info lookup for resolving journey paths to names/logos
        club_info = {team_api_id: {"club_name": parent_name, "club_logo": parent_logo}}
        for pid, clubs in player_clubs.items():
            for cid, cdata in clubs.items():
                if cid not in club_info:
                    club_info[cid] = {
                        "club_name": cdata["club_name"],
                        "club_logo": cdata["club_logo"],
                    }

        # Build pid→journey lookup for O(1) access in link building
        pid_to_journey = {j.player_api_id: j for j in journeys}

        # Derive player statuses and build per-player summary
        all_players = []
        status_counts = {}
        seen_pids = set()

        for journey in journeys:
            pid = journey.player_api_id
            seen_pids.add(pid)

            # Derive status: prefer TrackedPlayer, fallback to classify_tracked_player
            tp = tp_lookup.get(pid)
            if tp:
                status = tp.status
            else:
                status, _, _ = classify_tracked_player(
                    journey.current_club_api_id,
                    journey.current_club_name,
                    journey.current_level,
                    team_api_id,
                    parent_name,
                    transfers=[],  # read-only view, skip API calls
                    latest_season=_get_latest_season(
                        journey.id, parent_api_id=team_api_id, parent_club_name=parent_name
                    ),
                )

            status_counts[status] = status_counts.get(status, 0) + 1

            # Compute destinations list for this player
            destinations = []
            total_apps = 0
            clubs = player_clubs.get(pid, {})
            for cid, cdata in clubs.items():
                if cid == team_api_id:
                    total_apps += cdata["appearances"]
                    continue
                destinations.append(
                    {
                        "club_api_id": cid,
                        "club_name": cdata["club_name"],
                        "appearances": cdata["appearances"],
                    }
                )
                total_apps += cdata["appearances"]

            # Resolve journey path to club names/logos
            journey_path = []
            for cid, _ in player_paths.get(pid, []):
                info = club_info.get(cid, {})
                journey_path.append(
                    {
                        "club_api_id": cid,
                        "club_name": info.get("club_name", f"Club {cid}"),
                        "club_logo": info.get("club_logo"),
                    }
                )

            parent_apps = clubs.get(team_api_id, {}).get("appearances", 0)

            all_players.append(
                {
                    "player_api_id": pid,
                    "player_name": journey.player_name,
                    "player_photo": journey.player_photo,
                    "status": status,
                    "current_club_name": journey.current_club_name,
                    "total_appearances": total_apps,
                    "parent_club_appearances": parent_apps,
                    "destinations": destinations,
                    "journey_path": journey_path,
                }
            )

        # Include TrackedPlayers that don't have journeys yet
        for tp in tp_lookup.values():
            if tp.player_api_id in seen_pids:
                continue
            status_counts[tp.status] = status_counts.get(tp.status, 0) + 1
            all_players.append(
                {
                    "player_api_id": tp.player_api_id,
                    "player_name": tp.player_name,
                    "player_photo": tp.photo_url,
                    "status": tp.status,
                    "current_club_name": tp.current_club_name,
                    "total_appearances": 0,
                    "parent_club_appearances": 0,
                    "destinations": [],
                    "journey_path": [],
                }
            )

        # Build nodes and links
        club_nodes = {}  # club_api_id -> node data
        # Parent node always present
        parent_players_at_home = set()
        for pid, clubs in player_clubs.items():
            if team_api_id in clubs:
                parent_players_at_home.add(pid)

        club_nodes[team_api_id] = {
            "id": f"club-{team_api_id}",
            "club_api_id": team_api_id,
            "club_name": parent_name,
            "club_logo": parent_logo,
            "is_parent": True,
            "player_count": len(parent_players_at_home),
            "total_appearances": sum(
                player_clubs.get(pid, {}).get(team_api_id, {}).get("appearances", 0) for pid in parent_players_at_home
            ),
            "players": [],
        }

        # Destination nodes
        for pid, clubs in player_clubs.items():
            for cid, cdata in clubs.items():
                if cid == team_api_id:
                    continue

                if cid not in club_nodes:
                    club_nodes[cid] = {
                        "id": f"club-{cid}",
                        "club_api_id": cid,
                        "club_name": cdata["club_name"],
                        "club_logo": cdata["club_logo"],
                        "is_parent": False,
                        "player_count": 0,
                        "total_appearances": 0,
                        "link_types": set(),
                        "players": [],
                    }

                node = club_nodes[cid]
                node["player_count"] += 1
                node["total_appearances"] += cdata["appearances"]
                node["link_types"].update(cdata["entry_types"])

                journey = pid_to_journey.get(pid)
                if journey:
                    node["players"].append(
                        {
                            "player_api_id": pid,
                            "player_name": journey.player_name,
                            "appearances": cdata["appearances"],
                            "goals": cdata["goals"],
                            "assists": cdata["assists"],
                        }
                    )

        # Build lattice links by tracing each player's consecutive club path
        link_map = {}  # (source_id, target_id) -> link data
        for pid, path in player_paths.items():
            for i in range(len(path) - 1):
                src_cid, _ = path[i]
                dst_cid, dst_entry_type = path[i + 1]

                # Determine link type from destination entry
                if dst_entry_type == "loan":
                    link_type = "loan"
                elif dst_cid == team_api_id:
                    link_type = "return"
                else:
                    link_type = "permanent"

                # Canonical key: always smaller id first to avoid duplicate
                # directional links between the same pair of clubs
                a, b = f"club-{src_cid}", f"club-{dst_cid}"
                link_key = (min(a, b), max(a, b))

                if link_key not in link_map:
                    link_map[link_key] = {
                        "source": link_key[0],
                        "target": link_key[1],
                        "player_count": 0,
                        "link_types": set(),
                        "players": {},
                    }
                link_map[link_key]["player_count"] += 1
                link_map[link_key]["link_types"].add(link_type)
                # Track player identity on this link (deduped by pid)
                if pid not in link_map[link_key]["players"]:
                    j = pid_to_journey.get(pid)
                    link_map[link_key]["players"][pid] = j.player_name if j else f"Player {pid}"

        # Enrich nodes with geographic coordinates from ClubLocation
        all_club_ids = [n["club_api_id"] for n in club_nodes.values()]
        locations = ClubLocation.query.filter(ClubLocation.club_api_id.in_(all_club_ids)).all()
        loc_map = {loc.club_api_id: loc for loc in locations}

        # Auto-geocode missing clubs using TeamProfile → Team → league_country fallback
        missing_ids = set(all_club_ids) - set(loc_map.keys())
        if missing_ids:
            geocoded = 0
            for cid in missing_ids:
                city = None
                country = None

                # 1. Try TeamProfile
                profile = TeamProfile.query.filter_by(team_id=cid).first()
                if profile and profile.venue_city:
                    city = profile.venue_city
                    country = profile.country

                # 2. Fallback: Team model (has venue data from fixtures sync)
                if not city:
                    team_rec = Team.query.filter_by(team_id=cid).order_by(Team.season.desc()).first()
                    if team_rec and team_rec.venue_city:
                        city = team_rec.venue_city
                        country = team_rec.country

                # 3. Fallback: use league_country from entries as country hint
                if not country:
                    country = club_country_hint.get(cid)

                if not city:
                    continue

                coords = get_team_coordinates(city, country)
                if not coords:
                    continue
                club_node = club_nodes.get(cid, {})
                loc = ClubLocation(
                    club_api_id=cid,
                    club_name=club_node.get("club_name", ""),
                    city=city,
                    country=country,
                    latitude=coords[0],
                    longitude=coords[1],
                    geocode_source="auto",
                    geocode_confidence=0.7,
                )
                db.session.add(loc)
                loc_map[cid] = loc
                geocoded += 1
            if geocoded:
                db.session.commit()
                logger.info(f"Auto-geocoded {geocoded} club locations for academy network")

        # Serialize nodes — convert sets to lists, add lat/lng
        nodes = []
        for node in club_nodes.values():
            n = {**node}
            if "link_types" in n:
                n["link_types"] = sorted(n["link_types"])
            loc = loc_map.get(n["club_api_id"])
            if loc:
                n["lat"] = loc.latitude
                n["lng"] = loc.longitude
                n["city"] = loc.city
                n["country"] = loc.country
            else:
                # Add country hint for unmapped nodes so frontend can group by country
                n["country"] = club_country_hint.get(n["club_api_id"])
            nodes.append(n)

        links = []
        for link in link_map.values():
            # Pick dominant link type: loan > return > permanent
            types = link["link_types"]
            if "loan" in types:
                link_type = "loan"
            elif "return" in types:
                link_type = "return"
            else:
                link_type = "permanent"
            links.append(
                {
                    "source": link["source"],
                    "target": link["target"],
                    "player_count": link["player_count"],
                    "link_type": link_type,
                    "players": [{"player_api_id": pid, "player_name": name} for pid, name in link["players"].items()],
                }
            )

        # Sort by appearances and apply limit
        all_players_sorted = sorted(all_players, key=lambda p: p["total_appearances"], reverse=True)
        total_academy_players = len(all_players_sorted)
        if len(all_players_sorted) > limit:
            # Keep top N players by appearances; drop entries/nodes for the rest
            kept_pids = {p["player_api_id"] for p in all_players_sorted[:limit]}
            all_players_sorted = all_players_sorted[:limit]
        else:
            kept_pids = None  # no filtering needed

        return jsonify(
            {
                "team_api_id": team_api_id,
                "team_name": parent_name,
                "team_logo": parent_logo,
                "season_range": [min_season, current_season],
                "total_academy_players": total_academy_players,
                "summary": status_counts,
                "nodes": nodes,
                "links": links,
                "all_players": all_players_sorted,
            }
        )
    except Exception as e:
        logger.error(f"Error getting academy network for team {team_api_id}: {e}")
        import traceback

        logger.error(traceback.format_exc())
        return jsonify(_safe_error_payload(e, "Failed to load academy network data.")), 500


@teams_bp.route("/teams/<team_identifier>/api-info", methods=["GET"])
def get_team_api_info(team_identifier):
    """Get team information from API-Football by ID."""
    try:
        team = resolve_team_by_identifier(team_identifier)
        real_client = _get_api_client()
        season = request.args.get("season", real_client.current_season_start_year)
        team_data = real_client.get_team_by_id(team.team_id)

        if not team_data:
            return jsonify({"error": f"Team {team_identifier} not found"}), 404

        return jsonify({"team_id": team.team_id, "season": season, "data": team_data})
    except NotFound:
        raise
    except Exception as e:
        logger.error(f"Error fetching team {team_identifier} from API: {e}")
        return jsonify(_safe_error_payload(e, "An unexpected error occurred. Please try again later.")), 500
