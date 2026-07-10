"""Players blueprint for player-related endpoints.

This blueprint handles:
- Player stats retrieval
- Player profile information
- Season stats aggregation
- Player commentaries
"""

import logging
import os

from flask import Blueprint, Response, jsonify, make_response, request
from markupsafe import escape
from src.auth import _safe_error_payload
from src.models.league import (
    NewsletterCommentary,
    Player,
    db,
)
from src.models.tracked_player import TrackedPlayer

logger = logging.getLogger(__name__)

players_bp = Blueprint("players", __name__)


# Lazy import for api_client to avoid circular imports and early initialization
def _get_api_client():
    from src.routes.api import api_client

    return api_client


def _get_resolve_team_name_and_logo():
    from src.routes.api import resolve_team_name_and_logo

    return resolve_team_name_and_logo


def _prefer_academy_origin():
    """Order expression that sorts owning-club rows last.
    Use with .order_by() to prefer academy-origin TrackedPlayer rows."""
    return db.case(
        (TrackedPlayer.data_source == "owning-club", 1),
        else_=0,
    ).asc()


def _season_provenance(player_id: int, season: int) -> dict:
    """On-read provenance for a (player, season) SENIOR minutes figure.

    Reconciles the two independent minute sources without ever silently mixing
    them: per-match ``FixturePlayerStats`` (match-proven) vs the
    ``PlayerJourneyEntry`` season totals (API season summary, cup-inclusive).

    - ``fixtures_minutes``: SUM of the player's FixturePlayerStats minutes in
      fixtures of this season.
    - ``journey_minutes``: SUM of the player's SENIOR journey-entry minutes this
      season — youth and international entries excluded.
    - ``source``: which source wins the headline — the larger-minutes source
      taken whole (journey wins ties / ``>=`` as the cup-inclusive convention).
    - ``reconcile_flag``: ``cup-gap`` (journey > fixtures > 0) |
      ``fixtures-invisible`` (fixtures == 0 < journey) | ``journey-under-sync``
      (fixtures > journey) | ``None`` (agree, or both zero).
    - ``delta_pct``: signed % gap ``(journey - fixtures) / max(both)``, 1 dp.

    Two bounded aggregate queries (one FPS, one PJE) — cheap for a single
    player, and pre-index acceptable per the D1 design.
    """
    from sqlalchemy import func
    from src.models.journey import PlayerJourney, PlayerJourneyEntry
    from src.models.weekly import Fixture, FixturePlayerStats

    fixtures_minutes = int(
        db.session.query(func.coalesce(func.sum(FixturePlayerStats.minutes), 0))
        .join(Fixture, FixturePlayerStats.fixture_id == Fixture.id)
        .filter(
            FixturePlayerStats.player_api_id == player_id,
            Fixture.season == season,
        )
        .scalar()
    )

    journey_minutes = int(
        db.session.query(func.coalesce(func.sum(PlayerJourneyEntry.minutes), 0))
        .join(PlayerJourney, PlayerJourneyEntry.journey_id == PlayerJourney.id)
        .filter(
            PlayerJourney.player_api_id == player_id,
            PlayerJourneyEntry.season == season,
            PlayerJourneyEntry.is_youth.is_(False),
            PlayerJourneyEntry.is_international.is_(False),
        )
        .scalar()
    )

    if fixtures_minutes == 0 and journey_minutes == 0:
        source = "none"
    elif journey_minutes >= fixtures_minutes:
        source = "journey"
    else:
        source = "fixtures"

    if fixtures_minutes == 0 and journey_minutes > 0:
        reconcile_flag = "fixtures-invisible"
    elif journey_minutes > fixtures_minutes > 0:
        reconcile_flag = "cup-gap"
    elif fixtures_minutes > journey_minutes:
        reconcile_flag = "journey-under-sync"
    else:
        reconcile_flag = None

    larger = max(fixtures_minutes, journey_minutes)
    delta_pct = round((journey_minutes - fixtures_minutes) / larger * 100, 1) if larger else 0.0

    return {
        "source": source,
        "fixtures_minutes": fixtures_minutes,
        "journey_minutes": journey_minutes,
        "delta_pct": delta_pct,
        "reconcile_flag": reconcile_flag,
    }


# ---------------------------------------------------------------------------
# Player stats endpoint
# ---------------------------------------------------------------------------


@players_bp.route("/players/<int:player_id>/stats", methods=["GET"])
def get_public_player_stats(player_id: int):
    """Get historical stats for a player (public endpoint).

    Fetches directly from API-Football if local data is incomplete.
    Only returns CLUB games (not international).

    Query params:
    - force_sync: If 'true', force sync from API-Football even if local count matches
    """
    try:
        from src.api_football_client import APIFootballClient
        from src.models.weekly import Fixture, FixturePlayerStats

        resolve_team_name_and_logo = _get_resolve_team_name_and_logo()
        force_sync = request.args.get("force_sync", "").lower() == "true"

        # Stats DISPLAY season. With no ?season this keeps today's behavior via
        # the with-data fallback resolver (never blanks a not-yet-started season);
        # an explicit ?season — validated to the fixture-data range — scopes every
        # read below (club-set union, match log, freshness fetch) to it.
        from src.utils.academy_window import current_stats_season, resolve_stats_season

        requested_season = request.args.get("season") or None
        try:
            season = resolve_stats_season(db.session, requested=requested_season, surface="discovery")
        except ValueError as ve:
            return jsonify({"error": str(ve)}), 400
        season_prefix = f"{season}-{str(season + 1)[-2:]}"
        # SYNC/FETCH season. With no ?season it stays the pure calendar season
        # (current_stats_season), NOT the with-data fallback: during the Aug
        # rollover `season` pins to the OLD season, and fetching that could never
        # ingest the first new-season match, leaving the page permanently blank at
        # the new club. current_stats_season() lets the view-driven sync land the
        # new season and self-heal the fallback for all readers. With an explicit
        # ?season the freshness fetch targets exactly that requested season.
        sync_season = season if requested_season is not None else current_stats_season()

        # Find ALL tracked players for this player (prefer academy-origin rows)
        tracked = (
            TrackedPlayer.query.filter_by(
                player_api_id=player_id,
                is_active=True,
            )
            .order_by(_prefer_academy_origin(), TrackedPlayer.updated_at.desc())
            .all()
        )

        if not tracked:
            tracked = (
                TrackedPlayer.query.filter_by(
                    player_api_id=player_id,
                )
                .order_by(_prefer_academy_origin(), TrackedPlayer.updated_at.desc())
                .limit(1)
                .all()
            )

        # Build a map of team_api_id -> team info for every club the player is
        # tracked at. We include BOTH the club where they currently play
        # (current_club_api_id — loan destination OR the club that bought them)
        # AND their parent/academy club. Previously the current club was added
        # only for status == "on_loan"; once moved players were reclassified
        # "sold"/"released" they fell through to the parent-only branch, so this
        # query filtered out every fixture at their real club and the page showed
        # "No match data available" even though the rows exist in
        # FixturePlayerStats (season-stats builds its club list straight from
        # FixturePlayerStats and was therefore unaffected).
        loan_teams_info = {}
        for tp in tracked:
            # The club where the player actually plays now (loan dest or buyer).
            if tp.current_club_api_id:
                loan_teams_info.setdefault(
                    tp.current_club_api_id,
                    {
                        "name": tp.current_club_name or (tp.current_club.name if tp.current_club else "Unknown"),
                        "logo": tp.current_club.logo if tp.current_club else None,
                        "window_type": "Summer",
                        "is_active": tp.is_active,
                    },
                )
            # The parent/academy club (academy + first-team-at-origin appearances).
            if tp.team:
                loan_teams_info.setdefault(
                    tp.team.team_id,
                    {
                        "name": tp.team.name,
                        "logo": tp.team.logo,
                        "window_type": "Summer",
                        "is_active": tp.is_active,
                    },
                )

        # UNION in every club the player actually appeared for THIS stats season,
        # taken straight from FixturePlayerStats (the source of truth for where a
        # player played). A returned loanee's tracked row points current_club back
        # at the parent club, so his loan club is absent from the sets above and
        # the match log renders empty even though the fixture rows exist — this is
        # exactly how /season-stats stays correct (it derives its club list from
        # FixturePlayerStats). Season-scoped via the fixtures.season index so a
        # prior-season-only club doesn't leak into the current club set.
        fixture_team_rows = (
            db.session.query(FixturePlayerStats.team_api_id)
            .join(Fixture, FixturePlayerStats.fixture_id == Fixture.id)
            .filter(
                FixturePlayerStats.player_api_id == player_id,
                Fixture.season == season,
            )
            .distinct()
            .all()
        )
        for (fixture_team_api_id,) in fixture_team_rows:
            if not fixture_team_api_id or fixture_team_api_id in loan_teams_info:
                continue
            fixture_team_name, fixture_team_logo = resolve_team_name_and_logo(fixture_team_api_id, season)
            loan_teams_info[fixture_team_api_id] = {
                "name": fixture_team_name or "Unknown",
                "logo": fixture_team_logo,
                "window_type": "Summer",
                "is_active": True,
            }

        loan_team_api_ids = list(loan_teams_info.keys())

        # Query local stats for ALL loan teams
        stats_query = (
            db.session.query(FixturePlayerStats, Fixture)
            .join(Fixture, FixturePlayerStats.fixture_id == Fixture.id)
            .filter(
                FixturePlayerStats.player_api_id == player_id,
                Fixture.season == season,
            )
        )

        if loan_team_api_ids:
            stats_query = stats_query.filter(FixturePlayerStats.team_api_id.in_(loan_team_api_ids))

        stats_query = stats_query.order_by(Fixture.date_utc.asc()).all()

        # Sync missing games from each loan team
        player_name_for_sync = tracked[0].player_name if tracked else None

        for loan_team_api_id in loan_team_api_ids:
            try:
                local_count = sum(1 for s, f in stats_query if s.team_api_id == loan_team_api_id)
                api_client = APIFootballClient()
                api_totals = api_client._fetch_player_team_season_totals_api(
                    player_id=player_id,
                    team_id=loan_team_api_id,
                    season=sync_season,
                )
                api_appearances = api_totals.get("games_played", 0)
                api_totals_failed = not api_totals  # empty dict = API call failed

                if api_appearances > local_count or force_sync or (local_count == 0 and api_totals_failed):
                    logger.info(
                        f"Player {player_id} at team {loan_team_api_id}: API={api_appearances}, local={local_count}, force={force_sync}. Syncing..."
                    )
                    from src.routes.api import _sync_player_club_fixtures

                    _sync_player_club_fixtures(
                        player_id, loan_team_api_id, sync_season, player_name=player_name_for_sync
                    )
            except Exception as e:
                logger.warning(f"Failed to sync for player {player_id} at team {loan_team_api_id}: {e}")

        # Re-query after potential sync
        stats_query = (
            db.session.query(FixturePlayerStats, Fixture)
            .join(Fixture, FixturePlayerStats.fixture_id == Fixture.id)
            .filter(
                FixturePlayerStats.player_api_id == player_id,
                Fixture.season == season,
            )
        )
        if loan_team_api_ids:
            stats_query = stats_query.filter(FixturePlayerStats.team_api_id.in_(loan_team_api_ids))
        stats_query = stats_query.order_by(Fixture.date_utc.asc()).all()

        result = []
        for stats, fixture in stats_query:
            is_home = stats.team_api_id == fixture.home_team_api_id
            opponent_api_id = fixture.away_team_api_id if is_home else fixture.home_team_api_id
            opponent_name, _ = resolve_team_name_and_logo(opponent_api_id, season)

            team_info = loan_teams_info.get(stats.team_api_id, {})
            if not team_info or not team_info.get("name"):
                loan_team_name, loan_team_logo = resolve_team_name_and_logo(stats.team_api_id, season)
                team_info = {
                    "name": loan_team_name,
                    "logo": loan_team_logo,
                    "window_type": "Summer",
                }

            stats_dict = stats.to_dict()
            stats_dict["fixture_date"] = fixture.date_utc.isoformat() if fixture.date_utc else None
            stats_dict["opponent"] = opponent_name
            stats_dict["is_home"] = is_home
            stats_dict["competition"] = fixture.competition_name
            stats_dict["loan_team_name"] = team_info.get("name") or "Unknown"
            stats_dict["loan_team_logo"] = team_info.get("logo")
            stats_dict["loan_window"] = team_info.get("window_type", "Summer")
            stats_dict["home_goals"] = fixture.home_goals
            stats_dict["away_goals"] = fixture.away_goals
            stats_dict["opponent_api_id"] = opponent_api_id

            result.append(stats_dict)

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error fetching player stats for player_id={player_id}: {e}")
        import traceback

        traceback.print_exc()
        return jsonify(_safe_error_payload(e, "Failed to fetch player stats")), 500


# _sync_player_club_fixtures is imported from src.routes.api (canonical copy)
# to avoid maintaining two divergent implementations.


# ---------------------------------------------------------------------------
# Player profile endpoint
# ---------------------------------------------------------------------------


@players_bp.route("/players/<int:player_id>/profile", methods=["GET"])
def get_public_player_profile(player_id: int):
    """Get player profile info including name, team, position, photo."""
    try:
        from src.models.weekly import FixturePlayerStats

        result = {
            "player_id": player_id,
            "name": None,
            "photo": None,
            "position": None,
            "loan_team_name": None,
            "loan_team_id": None,
            "loan_team_logo": None,
            "parent_team_name": None,
            "parent_team_id": None,
            "parent_team_logo": None,
            "nationality": None,
            "age": None,
        }

        # Get player base info from Player table
        player = Player.query.filter_by(player_id=player_id).first()
        if player:
            result["name"] = player.name
            result["photo"] = player.photo_url
            result["position"] = player.position
            result["nationality"] = player.nationality
            result["age"] = player.age

        # Enrich from TrackedPlayer (prefer academy-origin row over owning-club)
        tp = (
            TrackedPlayer.query.filter_by(
                player_api_id=player_id,
                is_active=True,
            )
            .order_by(_prefer_academy_origin(), TrackedPlayer.updated_at.desc())
            .first()
        )
        if not tp:
            tp = (
                TrackedPlayer.query.filter_by(
                    player_api_id=player_id,
                )
                .order_by(_prefer_academy_origin(), TrackedPlayer.updated_at.desc())
                .first()
            )

        if tp:
            if not result["position"] and tp.position:
                result["position"] = tp.position
            if not result["name"]:
                result["name"] = tp.player_name
            result["status"] = tp.status
            result["sale_fee"] = tp.sale_fee

            # Loan team info
            result["loan_team_name"] = tp.current_club_name
            if tp.current_club:
                result["loan_team_logo"] = tp.current_club.logo
                result["loan_team_id"] = tp.current_club.team_id
                result["loan_team_db_id"] = tp.current_club_db_id
            elif tp.current_club_api_id:
                result["loan_team_id"] = tp.current_club_api_id

            # Parent team info
            if tp.team:
                result["parent_team_name"] = tp.team.name
                result["parent_team_logo"] = tp.team.logo
                result["parent_team_id"] = tp.team.team_id
                result["primary_team_db_id"] = tp.team_id

        # ── Actual current status (overrides the academy-relative status) ──
        # tp.status is the player's status RELATIVE TO his tracked academy: a
        # player who left his academy reads 'left'/'sold' there even though his
        # real, current situation is an active loan from a DIFFERENT club the
        # platform doesn't track as his academy (e.g. Julian Rijkhoff — a
        # Borussia Dortmund academy product, on loan at Almere City FROM AJAX).
        # journey.current_status holds that player-level truth (computed + stored
        # during sync); NULL means defer to the academy-relative tp.status. This
        # reads the stored field so every surface stays consistent.
        from src.models.journey import PlayerJourney

        journey = PlayerJourney.query.filter_by(player_api_id=player_id).first()
        if journey and journey.current_status:
            result["status"] = journey.current_status
            if journey.current_owner_api_id:
                from src.models.league import Team

                owner_team = (
                    Team.query.filter_by(team_id=journey.current_owner_api_id, is_active=True)
                    .order_by(Team.season.desc())
                    .first()
                )
                result["owner_team_id"] = journey.current_owner_api_id
                result["owner_team_name"] = journey.current_owner_name
                result["owner_team_logo"] = owner_team.logo if owner_team else None

        # Shadow player fallback — a worldwide-followed player minted outside the
        # tracked universe has no Player/TrackedPlayer row. Fill still-empty
        # fields from its PlayerShadow so the profile page renders. Tracked-player
        # payloads are untouched (this only runs when no tracked row was found).
        if not tp:
            from src.models.follow import PlayerShadow

            shadow = PlayerShadow.query.filter_by(player_api_id=player_id, is_active=True).first()
            if shadow:
                result["shadow"] = True
                if not result["name"]:
                    result["name"] = shadow.player_name
                if not result["photo"]:
                    result["photo"] = shadow.photo_url
                if not result["position"]:
                    result["position"] = shadow.position
                if not result["nationality"]:
                    result["nationality"] = shadow.nationality
                if not result["age"] and shadow.birth_date:
                    from datetime import date as _date

                    today = _date.today()
                    bd = shadow.birth_date
                    result["age"] = today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))
                if not result["loan_team_name"]:
                    result["loan_team_name"] = shadow.current_club_name

        if not result["position"]:
            POS_MAP = {"G": "Goalkeeper", "D": "Defender", "M": "Midfielder", "F": "Attacker"}
            recent_stats = (
                FixturePlayerStats.query.filter_by(player_api_id=player_id)
                .filter(FixturePlayerStats.position.isnot(None))
                .order_by(FixturePlayerStats.id.desc())
                .first()
            )
            if recent_stats:
                result["position"] = POS_MAP.get(recent_stats.position, recent_stats.position)

        # If still no name, try to get from fixture stats
        if not result["name"]:
            stats = FixturePlayerStats.query.filter_by(player_api_id=player_id).first()
            if stats:
                result["position"] = stats.position

        # Final fallback for name
        if not result["name"]:
            result["name"] = f"Player #{player_id}"

        # Build loan history from all TrackedPlayer records for this player
        all_tracked = (
            TrackedPlayer.query.filter_by(
                player_api_id=player_id,
            )
            .order_by(TrackedPlayer.created_at.asc())
            .all()
        )

        seen_clubs = set()
        loan_history = []
        for t in all_tracked:
            if not t.current_club_api_id:
                continue
            if t.current_club_api_id in seen_clubs:
                continue
            seen_clubs.add(t.current_club_api_id)

            loan_history.append(
                {
                    "loan_team_name": t.current_club_name,
                    "loan_team_id": t.current_club_api_id,
                    "loan_team_db_id": t.current_club_db_id,
                    "loan_team_logo": t.current_club.logo if t.current_club else None,
                    "parent_team_name": t.team.name if t.team else None,
                    "parent_team_id": t.team.team_id if t.team else None,
                    "parent_team_logo": t.team.logo if t.team else None,
                    "window_type": "Summer",
                    "window_key": None,
                    "is_active": t.is_active,
                }
            )

        result["loan_history"] = loan_history
        result["has_multiple_loans"] = len(loan_history) > 1

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error fetching player profile for player_id={player_id}: {e}")
        import traceback

        traceback.print_exc()
        return jsonify(_safe_error_payload(e, "Failed to fetch player profile")), 500


# ---------------------------------------------------------------------------
# Player season stats endpoint
# ---------------------------------------------------------------------------


@players_bp.route("/players/<int:player_id>/season-stats", methods=["GET"])
def get_public_player_season_stats(player_id: int):
    """Get aggregated season stats for a player at their LOAN CLUB only."""
    try:
        from sqlalchemy import func
        from src.api_football_client import APIFootballClient
        from src.models.weekly import Fixture, FixturePlayerStats

        # Stats DISPLAY season. Default (no ?season) is the with-data fallback so
        # a not-yet-started season never blanks the page; an explicit ?season —
        # validated to the fixture-data range — scopes every read below to it.
        from src.utils.academy_window import resolve_stats_season

        requested_season = request.args.get("season") or None
        try:
            season_start_year = resolve_stats_season(db.session, requested=requested_season, surface="discovery")
        except ValueError as ve:
            return jsonify({"error": str(ve)}), 400
        season_prefix = f"{season_start_year}-{str(season_start_year + 1)[-2:]}"

        result = {
            "player_id": player_id,
            "season": f"{season_start_year}/{season_start_year + 1}",
            "appearances": 0,
            "minutes": 0,
            "goals": 0,
            "assists": 0,
            "yellows": 0,
            "reds": 0,
            "avg_rating": None,
            "saves": 0,
            "goals_conceded": 0,
            "clean_sheets": 0,
            "source": "none",
            "loan_clubs_only": True,
            "clubs": [],
        }

        # On-read provenance for the resolved season — computed once here so every
        # return path below (limited-coverage, shadow, main) carries it. Additive:
        # the existing top-level `source` field is left exactly as-is.
        result["provenance"] = _season_provenance(player_id, season_start_year)

        # Find tracked players (prefer academy-origin rows)
        all_tracked = (
            TrackedPlayer.query.filter_by(
                player_api_id=player_id,
                is_active=True,
            )
            .order_by(_prefer_academy_origin(), TrackedPlayer.updated_at.desc())
            .all()
        )

        if not all_tracked:
            tp_single = (
                TrackedPlayer.query.filter_by(
                    player_api_id=player_id,
                )
                .order_by(_prefer_academy_origin(), TrackedPlayer.updated_at.desc())
                .first()
            )
            all_tracked = [tp_single] if tp_single else []

        # Check for limited coverage
        if all_tracked and all_tracked[0].data_depth in ("events_only", "profile_only"):
            from src.models.league import PlayerStatsCache

            tp = all_tracked[0]
            # PlayerStatsCache is season-keyed. compute_stats() can't yet take a
            # season — it is pinned to stats_season_with_data() with its own
            # latest-cached-season fallback, so it always reports whichever season
            # that fallback lands on, which need NOT be the one the caller asked
            # for. Gating it on stats_season_with_data() is doubly wrong: for a
            # request that matches the display season but has no cache rows there,
            # the fallback still serves an OLDER season's totals under the display
            # label (mislabel); and for a request that matches the season the
            # cache rows actually live in but differs from the display season, it
            # zeroes real data. So: the default (no ?season) keeps calling
            # compute_stats() verbatim (byte-compat, preserves the lower-league
            # lag fallback), while an explicit ?season reads the cache DIRECTLY,
            # scoped to that season — zeros only when no rows genuinely exist for
            # it. (compute_stats(season=) lands in D4.)
            if requested_season is None:
                computed = tp.compute_stats()
                result["appearances"] = computed["appearances"]
                result["minutes"] = computed["minutes_played"]
                result["goals"] = computed["goals"]
                result["assists"] = computed["assists"]
                result["yellows"] = computed["yellows"]
                result["reds"] = computed["reds"]
            else:
                cache = (
                    db.session.query(
                        func.coalesce(func.sum(PlayerStatsCache.appearances), 0),
                        func.coalesce(func.sum(PlayerStatsCache.minutes_played), 0),
                        func.coalesce(func.sum(PlayerStatsCache.goals), 0),
                        func.coalesce(func.sum(PlayerStatsCache.assists), 0),
                        func.coalesce(func.sum(PlayerStatsCache.yellows), 0),
                        func.coalesce(func.sum(PlayerStatsCache.reds), 0),
                    )
                    .filter(
                        PlayerStatsCache.player_api_id == player_id,
                        PlayerStatsCache.season == season_start_year,
                    )
                    .first()
                )
                apps, minutes, goals, assists, yellows, reds = (int(v or 0) for v in (cache or (0, 0, 0, 0, 0, 0)))
                result["appearances"] = apps
                result["minutes"] = minutes
                result["goals"] = goals
                result["assists"] = assists
                result["yellows"] = yellows
                result["reds"] = reds
            result["source"] = "limited-coverage"
            result["stats_coverage"] = "limited"

            if tp.current_club:
                result["loan_team"] = tp.current_club.name
                result["clubs"] = [
                    {
                        "team_name": tp.current_club.name,
                        "team_logo": tp.current_club.logo,
                        "appearances": result["appearances"],
                        "goals": result["goals"],
                        "assists": result["assists"],
                        "is_current": tp.is_active,
                    }
                ]

            return jsonify(result)

        if not all_tracked:
            # Shadow player fallback — no tracked rows, but a worldwide-followed
            # PlayerShadow exists: serve PlayerShadowStats as limited coverage so
            # the profile's stats view renders. Default (no ?season) serves the
            # LATEST season with shadow rows (not wall-clock) so it is immune to
            # API-Football client season drift; an explicit ?season scopes to
            # exactly that season (PlayerShadowStats is season-keyed) so the
            # totals match the response's season label and the provenance object.
            from src.models.follow import PlayerShadow, PlayerShadowStats

            shadow = PlayerShadow.query.filter_by(player_api_id=player_id, is_active=True).first()
            if shadow:
                if requested_season is not None:
                    target_season = season_start_year
                else:
                    target_season = (
                        db.session.query(func.max(PlayerShadowStats.season))
                        .filter(PlayerShadowStats.player_api_id == player_id)
                        .scalar()
                    )
                totals = (
                    db.session.query(
                        func.coalesce(func.sum(PlayerShadowStats.appearances), 0),
                        func.coalesce(func.sum(PlayerShadowStats.goals), 0),
                        func.coalesce(func.sum(PlayerShadowStats.assists), 0),
                        func.coalesce(func.sum(PlayerShadowStats.minutes), 0),
                    )
                    .filter(
                        PlayerShadowStats.player_api_id == player_id,
                        PlayerShadowStats.season == target_season,
                    )
                    .first()
                    if target_season is not None
                    else None
                )
                apps, goals, assists, minutes = (int(v or 0) for v in (totals or (0, 0, 0, 0)))
                result["appearances"] = apps
                result["goals"] = goals
                result["assists"] = assists
                result["minutes"] = minutes
                result["source"] = "shadow"
                result["stats_coverage"] = "limited"
                if shadow.current_club_name:
                    result["loan_team"] = shadow.current_club_name
                    result["clubs"] = [
                        {
                            "team_name": shadow.current_club_name,
                            "team_logo": None,
                            "appearances": apps,
                            "goals": goals,
                            "assists": assists,
                            "is_current": True,
                        }
                    ]
            return jsonify(result)

        # Build list of clubs from FixturePlayerStats (source of truth for which
        # clubs the player actually played for this season) rather than deriving
        # from TrackedPlayer rows which may include owning-club rows.
        resolve_team_name_and_logo = _get_resolve_team_name_and_logo()
        distinct_teams = (
            db.session.query(
                FixturePlayerStats.team_api_id,
            )
            .join(
                Fixture,
                FixturePlayerStats.fixture_id == Fixture.id,
            )
            .filter(
                FixturePlayerStats.player_api_id == player_id,
                Fixture.season == season_start_year,
            )
            .distinct()
            .all()
        )

        loan_teams_info = []
        loan_team_api_ids = []
        for (team_api_id,) in distinct_teams:
            if team_api_id in loan_team_api_ids:
                continue
            team_name, team_logo = resolve_team_name_and_logo(team_api_id, season_start_year)
            loan_teams_info.append(
                {
                    "api_id": team_api_id,
                    "name": team_name or "Unknown",
                    "logo": team_logo,
                    "window_type": "Summer",
                    "is_active": True,
                }
            )
            loan_team_api_ids.append(team_api_id)

        # Fallback: if no fixture stats yet, use TrackedPlayer
        if not loan_teams_info:
            for tp in all_tracked:
                if not tp:
                    continue
                if tp.status == "on_loan" and tp.current_club_api_id:
                    club_api_id = tp.current_club_api_id
                    club_name = tp.current_club_name or "Unknown"
                    club_logo = tp.current_club.logo if tp.current_club else None
                elif tp.team:
                    club_api_id = tp.team.team_id
                    club_name = tp.team.name
                    club_logo = tp.team.logo
                else:
                    continue
                if club_api_id not in loan_team_api_ids:
                    loan_teams_info.append(
                        {
                            "api_id": club_api_id,
                            "name": club_name,
                            "logo": club_logo,
                            "window_type": "Summer",
                            "is_active": tp.is_active,
                        }
                    )
                    loan_team_api_ids.append(club_api_id)

        result["loan_team"] = loan_teams_info[0]["name"] if loan_teams_info else None
        result["has_multiple_clubs"] = len(loan_teams_info) > 1

        # Aggregate stats from API-Football for ALL loan clubs
        api_client = APIFootballClient()
        total_appearances = 0
        total_minutes = 0
        total_goals = 0
        total_assists = 0
        clubs_breakdown = []

        for team_info in loan_teams_info:
            try:
                api_totals = api_client._fetch_player_team_season_totals_api(
                    player_id=player_id,
                    team_id=team_info["api_id"],
                    season=season_start_year,
                )

                if api_totals and api_totals.get("games_played", 0) > 0:
                    club_stats = {
                        "team_name": team_info["name"],
                        "team_logo": team_info["logo"],
                        "window_type": team_info["window_type"],
                        "is_current": team_info["is_active"],
                        "appearances": api_totals.get("games_played", 0),
                        "minutes": api_totals.get("minutes", 0),
                        "goals": api_totals.get("goals", 0),
                        "assists": api_totals.get("assists", 0),
                        "saves": api_totals.get("saves", 0),
                        "goals_conceded": api_totals.get("goals_conceded", 0),
                    }
                    clubs_breakdown.append(club_stats)
                    total_appearances += club_stats["appearances"]
                    total_minutes += club_stats["minutes"]
                    total_goals += club_stats["goals"]
                    total_assists += club_stats["assists"]
                    result["source"] = "api-football"
            except Exception as api_err:
                logger.warning(
                    f"Failed to get API-Football stats for player {player_id} at {team_info['name']}: {api_err}"
                )

        result["appearances"] = total_appearances
        result["minutes"] = total_minutes
        result["goals"] = total_goals
        result["assists"] = total_assists
        result["clubs"] = clubs_breakdown

        # Get detailed stats from local DB
        if loan_team_api_ids:
            stats_query = (
                db.session.query(
                    func.count(FixturePlayerStats.id).label("appearances"),
                    func.sum(FixturePlayerStats.minutes).label("total_minutes"),
                    func.sum(FixturePlayerStats.goals).label("total_goals"),
                    func.sum(FixturePlayerStats.assists).label("total_assists"),
                    func.sum(FixturePlayerStats.yellows).label("total_yellows"),
                    func.sum(FixturePlayerStats.reds).label("total_reds"),
                    func.avg(FixturePlayerStats.rating).label("avg_rating"),
                    func.sum(FixturePlayerStats.saves).label("total_saves"),
                    func.sum(FixturePlayerStats.goals_conceded).label("total_goals_conceded"),
                )
                .join(Fixture, FixturePlayerStats.fixture_id == Fixture.id)
                .filter(
                    FixturePlayerStats.player_api_id == player_id,
                    FixturePlayerStats.team_api_id.in_(loan_team_api_ids),
                    Fixture.season == season_start_year,
                )
                .first()
            )

            if stats_query and stats_query.appearances:
                local_appearances = stats_query.appearances or 0
                local_minutes = int(stats_query.total_minutes or 0)
                local_goals = int(stats_query.total_goals or 0)
                local_assists = int(stats_query.total_assists or 0)

                result["yellows"] = int(stats_query.total_yellows or 0)
                result["reds"] = int(stats_query.total_reds or 0)
                result["avg_rating"] = round(float(stats_query.avg_rating or 0), 2) if stats_query.avg_rating else None
                result["saves"] = int(stats_query.total_saves or 0)
                result["goals_conceded"] = int(stats_query.total_goals_conceded or 0)
                result["local_appearances"] = local_appearances

                if local_appearances > result.get("appearances", 0) or result["source"] == "none":
                    result["appearances"] = local_appearances
                    result["minutes"] = local_minutes
                    result["goals"] = local_goals
                    result["assists"] = local_assists
                    result["source"] = "local-db"

            # Calculate clean sheets
            clean_sheets_query = (
                db.session.query(func.count(FixturePlayerStats.id).label("clean_sheets"))
                .join(Fixture, FixturePlayerStats.fixture_id == Fixture.id)
                .filter(
                    FixturePlayerStats.player_api_id == player_id,
                    FixturePlayerStats.team_api_id.in_(loan_team_api_ids),
                    Fixture.season == season_start_year,
                    FixturePlayerStats.goals_conceded == 0,
                    FixturePlayerStats.minutes >= 45,
                )
                .first()
            )

            result["clean_sheets"] = clean_sheets_query.clean_sheets if clean_sheets_query else 0

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error fetching season stats for player_id={player_id}: {e}")
        import traceback

        traceback.print_exc()
        return jsonify(_safe_error_payload(e, "Failed to fetch season stats")), 500


# ---------------------------------------------------------------------------
# Player availability endpoint
# ---------------------------------------------------------------------------


@players_bp.route("/players/<int:player_id>/availability", methods=["GET"])
def get_player_availability(player_id: int):
    """Get injury/absence history for a player this season.

    Sourced from API-Football's `injuries` endpoint (DB-cached). Each record
    is a fixture the player missed or was doubtful for, with the reason.

    Query params:
    - season: season start year (default: current season)
    """
    try:
        api_client = _get_api_client()
        season = request.args.get("season", type=int) or api_client.current_season_start_year
        raw = api_client.get_player_injuries(player_id, season)

        absences = []
        for record in raw:
            player_info = record.get("player") or {}
            fixture_info = record.get("fixture") or {}
            team_info = record.get("team") or {}
            league_info = record.get("league") or {}
            absences.append(
                {
                    "date": fixture_info.get("date"),
                    "fixture_id": fixture_info.get("id"),
                    "type": player_info.get("type"),
                    "reason": player_info.get("reason"),
                    "team_id": team_info.get("id"),
                    "team_name": team_info.get("name"),
                    "team_logo": team_info.get("logo"),
                    "league_name": league_info.get("name"),
                }
            )
        absences.sort(key=lambda a: a.get("date") or "", reverse=True)

        by_reason = {}
        for absence in absences:
            reason = absence.get("reason") or "Unknown"
            by_reason[reason] = by_reason.get(reason, 0) + 1

        return jsonify(
            {
                "player_id": player_id,
                "season": season,
                "absences": absences,
                "summary": {
                    "total_absences": len(absences),
                    "by_reason": by_reason,
                    "last_absence": absences[0] if absences else None,
                },
            }
        )
    except Exception as e:
        logger.error(f"Error fetching availability for player_id={player_id}: {e}")
        return jsonify(_safe_error_payload(e, "Failed to fetch availability")), 500


# ---------------------------------------------------------------------------
# Player commentaries endpoint
# ---------------------------------------------------------------------------


@players_bp.route("/players/<int:player_id>/commentaries", methods=["GET"])
def get_player_commentaries(player_id: int):
    """Get all commentaries/writeups that mention this player."""
    try:
        commentaries = (
            NewsletterCommentary.query.filter(
                NewsletterCommentary.player_id == player_id, NewsletterCommentary.is_active
            )
            .order_by(NewsletterCommentary.created_at.desc())
            .all()
        )

        result = []
        for c in commentaries:
            author = c.author
            newsletter = c.newsletter

            commentary_data = {
                "id": c.id,
                "content": c.content,
                "title": c.title,
                "commentary_type": c.commentary_type,
                "is_premium": c.is_premium,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
                "author": {
                    "id": author.id if author else None,
                    "display_name": author.display_name if author else None,
                    "profile_image_url": author.profile_image_url if author else None,
                    "is_journalist": author.is_journalist if author else False,
                }
                if author
                else None,
                "newsletter": {
                    "id": newsletter.id if newsletter else None,
                    "title": newsletter.title if newsletter else None,
                    "week_start_date": newsletter.week_start_date.isoformat()
                    if newsletter and newsletter.week_start_date
                    else None,
                    "week_end_date": newsletter.week_end_date.isoformat()
                    if newsletter and newsletter.week_end_date
                    else None,
                    "team_name": newsletter.team.name if newsletter and newsletter.team else None,
                }
                if newsletter
                else None,
            }
            result.append(commentary_data)

        # Get unique authors
        unique_authors = {}
        for c in commentaries:
            if c.author and c.author.id not in unique_authors:
                unique_authors[c.author.id] = {
                    "id": c.author.id,
                    "display_name": c.author.display_name,
                    "profile_image_url": c.author.profile_image_url,
                    "is_journalist": c.author.is_journalist,
                    "commentary_count": 0,
                }
            if c.author:
                unique_authors[c.author.id]["commentary_count"] += 1

        return jsonify(
            {
                "player_id": player_id,
                "commentaries": result,
                "total_count": len(result),
                "authors": list(unique_authors.values()),
            }
        )

    except Exception as e:
        logger.error(f"Error fetching commentaries for player_id={player_id}: {e}")
        import traceback

        traceback.print_exc()
        return jsonify(_safe_error_payload(e, "Failed to fetch player commentaries")), 500


# ---------------------------------------------------------------------------
# Player share / OG-unfurl endpoint
# ---------------------------------------------------------------------------


def _player_exists(player_api_id: int) -> bool:
    """Cheap existence check so /share can 404 unknown players.

    get_public_player_profile() never 404s — it always returns a payload,
    falling back to a "Player #<id>" placeholder name — so this endpoint
    needs its own check across the same three sources that view checks
    (Player, TrackedPlayer, PlayerShadow) before it will build unfurl meta.
    """
    from src.models.follow import PlayerShadow

    if Player.query.filter_by(player_id=player_api_id).first() is not None:
        return True
    if TrackedPlayer.query.filter_by(player_api_id=player_api_id).first() is not None:
        return True
    return PlayerShadow.query.filter_by(player_api_id=player_api_id, is_active=True).first() is not None


def _player_season_snapshot(player_api_id: int) -> tuple[int, int]:
    """Cheap local-only (appearances, goals) for the current stats season.

    Deliberately does NOT call the API-Football sync used by /stats and
    /season-stats — this endpoint is hit by link-preview crawlers on every
    share, so it stays a single indexed local read. Flavor text only; the
    real page (loaded after the redirect) shows the authoritative numbers.
    """
    from sqlalchemy import func
    from src.models.weekly import Fixture, FixturePlayerStats
    from src.utils.academy_window import current_stats_season

    season = current_stats_season()
    row = (
        db.session.query(
            func.count(FixturePlayerStats.id),
            func.coalesce(func.sum(FixturePlayerStats.goals), 0),
        )
        .join(Fixture, FixturePlayerStats.fixture_id == Fixture.id)
        .filter(
            FixturePlayerStats.player_api_id == player_api_id,
            Fixture.season == season,
        )
        .first()
    )
    apps, goals = row if row else (0, 0)
    return int(apps or 0), int(goals or 0)


def _frontend_base_url() -> str:
    """SPA origin for canonical/redirect links.

    Reuses the exact same FRONTEND_URL env var (+ default) that
    journalist.py already uses for claim-account emails, so this endpoint
    doesn't introduce a second, possibly-drifting notion of "the frontend".
    """
    return os.getenv("FRONTEND_URL", "https://theacademywatch.com").rstrip("/")


@players_bp.route("/players/<int:player_api_id>/share", methods=["GET"])
def get_player_share_page(player_api_id: int):
    """Public OG-unfurl + human-redirect page for a player's SPA profile.

    Social crawlers (X/Twitter, Facebook, WhatsApp, Slack, iMessage, ...)
    request this URL directly for link-preview metadata — it is what makes
    a shared player link "unfurl beautifully" instead of showing a bare
    URL. Humans who click through get bounced straight to the real SPA
    page. No auth, no JSON — a small HTML document is the entire contract.
    """
    if not _player_exists(player_api_id):
        return Response("Player not found", status=404, mimetype="text/plain")

    # get_public_player_profile() is a Flask view function — it can return
    # either a bare Response or a (body, status) tuple; make_response()
    # normalizes both so .get_json() always works here.
    profile_resp = make_response(get_public_player_profile(player_api_id))
    profile = profile_resp.get_json() or {}

    name = profile.get("name") or f"Player #{player_api_id}"
    photo = profile.get("photo")
    position = profile.get("position")
    nationality = profile.get("nationality")
    current_club = profile.get("loan_team_name") or profile.get("parent_team_name")

    apps, goals = _player_season_snapshot(player_api_id)

    description_parts = []
    if position:
        description_parts.append(position)
    if nationality:
        description_parts.append(nationality)
    if current_club:
        description_parts.append(f"currently at {current_club}")
    if apps:
        stat_bit = f"{apps} appearance{'s' if apps != 1 else ''}"
        if goals:
            stat_bit += f", {goals} goal{'s' if goals != 1 else ''}"
        description_parts.append(f"{stat_bit} this season")
    description = " · ".join(description_parts) or "Follow their journey on The Academy Watch."

    title = f"{name} — Player Profile | The Academy Watch"
    frontend_base = _frontend_base_url()
    canonical_url = f"{frontend_base}/players/{player_api_id}"
    twitter_card = "summary_large_image" if photo else "summary"

    safe_title = escape(title)
    safe_description = escape(description)
    safe_name = escape(name)
    safe_canonical = escape(canonical_url)
    photo_meta = f'<meta property="og:image" content="{escape(photo)}">\n    ' if photo else ""

    html = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>{safe_title}</title>
    <meta name="description" content="{safe_description}">
    <link rel="canonical" href="{safe_canonical}">

    <meta property="og:type" content="profile">
    <meta property="og:title" content="{safe_title}">
    <meta property="og:description" content="{safe_description}">
    <meta property="og:url" content="{safe_canonical}">
    <meta property="og:site_name" content="The Academy Watch">
    {photo_meta}<meta name="twitter:card" content="{twitter_card}">
    <meta name="twitter:title" content="{safe_title}">
    <meta name="twitter:description" content="{safe_description}">

    <meta http-equiv="refresh" content="0;url={safe_canonical}">
    <script>window.location.replace({canonical_url!r});</script>
  </head>
  <body>
    <p>Redirecting to {safe_name}&#8217;s profile on The Academy Watch&hellip;</p>
    <p><a href="{safe_canonical}">Continue to {safe_name}&#8217;s profile</a></p>
  </body>
</html>
"""
    return Response(html, mimetype="text/html")
