"""Players blueprint for player-related endpoints.

This blueprint handles:
- Player stats retrieval
- Player profile information
- Season stats aggregation
- Player commentaries
"""

import logging
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from src.auth import _safe_error_payload
from src.models.league import (
    db,
    AcademyPlayer,
    Player,
    SupplementalLoan,
    Team,
    NewsletterCommentary,
)

logger = logging.getLogger(__name__)

players_bp = Blueprint('players', __name__)


# Lazy import for api_client to avoid circular imports and early initialization
def _get_api_client():
    from src.routes.api import api_client
    return api_client


def _get_resolve_team_name_and_logo():
    from src.routes.api import resolve_team_name_and_logo
    return resolve_team_name_and_logo


# ---------------------------------------------------------------------------
# Player stats endpoint
# ---------------------------------------------------------------------------

@players_bp.route('/players/<int:player_id>/stats', methods=['GET'])
def get_public_player_stats(player_id: int):
    """Get historical stats for a player (public endpoint).

    Fetches directly from API-Football if local data is incomplete.
    Only returns CLUB games (not international).

    Query params:
    - force_sync: If 'true', force sync from API-Football even if local count matches
    """
    try:
        from src.models.weekly import FixturePlayerStats, Fixture
        from src.api_football_client import APIFootballClient

        resolve_team_name_and_logo = _get_resolve_team_name_and_logo()
        force_sync = request.args.get('force_sync', '').lower() == 'true'

        # Get current season
        now_utc = datetime.now(timezone.utc)
        current_year = now_utc.year
        current_month = now_utc.month
        season = current_year if current_month >= 8 else current_year - 1
        season_prefix = f"{season}-{str(season + 1)[-2:]}"

        # Find ALL loan teams for this player this season
        all_loans = AcademyPlayer.query.filter(
            AcademyPlayer.player_id == player_id,
            AcademyPlayer.window_key.like(f"{season_prefix}%")
        ).order_by(AcademyPlayer.updated_at.desc()).all()

        if not all_loans:
            all_loans = [AcademyPlayer.query.filter_by(player_id=player_id).order_by(AcademyPlayer.updated_at.desc()).first()]
            all_loans = [l for l in all_loans if l]

        # Build a map of team_api_id -> team info
        loan_teams_info = {}
        for loan in all_loans:
            if loan and loan.loan_team_id:
                loan_team = Team.query.get(loan.loan_team_id)
                if loan_team:
                    window_type = 'Summer'
                    if loan.window_key and '::' in loan.window_key:
                        window_part = loan.window_key.split('::')[1]
                        if window_part.upper() == 'JANUARY':
                            window_type = 'January'
                    loan_teams_info[loan_team.team_id] = {
                        'name': loan_team.name,
                        'logo': loan_team.logo,
                        'window_type': window_type,
                        'is_active': loan.is_active,
                    }

        loan_team_api_ids = list(loan_teams_info.keys())

        # Query local stats for ALL loan teams
        stats_query = db.session.query(
            FixturePlayerStats, Fixture
        ).join(
            Fixture, FixturePlayerStats.fixture_id == Fixture.id
        ).filter(
            FixturePlayerStats.player_api_id == player_id
        )

        if loan_team_api_ids:
            stats_query = stats_query.filter(
                FixturePlayerStats.team_api_id.in_(loan_team_api_ids)
            )

        stats_query = stats_query.order_by(Fixture.date_utc.asc()).all()

        # Sync missing games from each loan team
        player_name_for_sync = all_loans[0].player_name if all_loans else None

        for loan_team_api_id in loan_team_api_ids:
            try:
                local_count = sum(1 for s, f in stats_query if s.team_api_id == loan_team_api_id)
                api_client = APIFootballClient()
                api_totals = api_client._fetch_player_team_season_totals_api(
                    player_id=player_id,
                    team_id=loan_team_api_id,
                    season=season,
                )
                api_appearances = api_totals.get('games_played', 0)
                api_totals_failed = not api_totals  # empty dict = API call failed

                if api_appearances > local_count or force_sync or (local_count == 0 and api_totals_failed):
                    logger.info(f"Player {player_id} at team {loan_team_api_id}: API={api_appearances}, local={local_count}, force={force_sync}. Syncing...")
                    from src.routes.api import _sync_player_club_fixtures
                    _sync_player_club_fixtures(player_id, loan_team_api_id, season, player_name=player_name_for_sync)
            except Exception as e:
                logger.warning(f"Failed to sync for player {player_id} at team {loan_team_api_id}: {e}")

        # Re-query after potential sync
        stats_query = db.session.query(
            FixturePlayerStats, Fixture
        ).join(
            Fixture, FixturePlayerStats.fixture_id == Fixture.id
        ).filter(
            FixturePlayerStats.player_api_id == player_id
        )
        if loan_team_api_ids:
            stats_query = stats_query.filter(
                FixturePlayerStats.team_api_id.in_(loan_team_api_ids)
            )
        stats_query = stats_query.order_by(Fixture.date_utc.asc()).all()

        result = []
        for stats, fixture in stats_query:
            is_home = (stats.team_api_id == fixture.home_team_api_id)
            opponent_api_id = fixture.away_team_api_id if is_home else fixture.home_team_api_id
            opponent_name, _ = resolve_team_name_and_logo(opponent_api_id, season)

            team_info = loan_teams_info.get(stats.team_api_id, {})
            if not team_info or not team_info.get('name'):
                loan_team_name, loan_team_logo = resolve_team_name_and_logo(stats.team_api_id, season)
                team_info = {
                    'name': loan_team_name,
                    'logo': loan_team_logo,
                    'window_type': 'Summer',
                }

            stats_dict = stats.to_dict()
            stats_dict['fixture_date'] = fixture.date_utc.isoformat() if fixture.date_utc else None
            stats_dict['opponent'] = opponent_name
            stats_dict['is_home'] = is_home
            stats_dict['competition'] = fixture.competition_name
            stats_dict['loan_team_name'] = team_info.get('name') or "Unknown"
            stats_dict['loan_team_logo'] = team_info.get('logo')
            stats_dict['loan_window'] = team_info.get('window_type', 'Summer')
            stats_dict['home_goals'] = fixture.home_goals
            stats_dict['away_goals'] = fixture.away_goals
            stats_dict['opponent_api_id'] = opponent_api_id

            result.append(stats_dict)

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error fetching player stats for player_id={player_id}: {e}")
        import traceback
        traceback.print_exc()
        return jsonify(_safe_error_payload(e, 'Failed to fetch player stats')), 500


# _sync_player_club_fixtures is imported from src.routes.api (canonical copy)
# to avoid maintaining two divergent implementations.


# ---------------------------------------------------------------------------
# Player profile endpoint
# ---------------------------------------------------------------------------

@players_bp.route('/players/<int:player_id>/profile', methods=['GET'])
def get_public_player_profile(player_id: int):
    """Get player profile info including name, team, position, photo."""
    try:
        from src.models.weekly import FixturePlayerStats

        result = {
            'player_id': player_id,
            'name': None,
            'photo': None,
            'position': None,
            'loan_team_name': None,
            'loan_team_id': None,
            'loan_team_logo': None,
            'parent_team_name': None,
            'parent_team_id': None,
            'parent_team_logo': None,
            'nationality': None,
            'age': None,
        }

        # Get player base info from Player table
        player = Player.query.filter_by(player_id=player_id).first()
        if player:
            result['name'] = player.name
            result['photo'] = player.photo_url
            result['position'] = player.position
            result['nationality'] = player.nationality
            result['age'] = player.age

        # Enrich position from TrackedPlayer or FixturePlayerStats if missing
        if not result['position']:
            from src.models.tracked_player import TrackedPlayer
            tp = TrackedPlayer.query.filter_by(player_api_id=player_id, is_active=True).first()
            if tp and tp.position:
                result['position'] = tp.position

        if not result['position']:
            POS_MAP = {'G': 'Goalkeeper', 'D': 'Defender', 'M': 'Midfielder', 'F': 'Attacker'}
            recent_stats = FixturePlayerStats.query.filter_by(
                player_api_id=player_id
            ).filter(
                FixturePlayerStats.position.isnot(None)
            ).order_by(FixturePlayerStats.id.desc()).first()
            if recent_stats:
                result['position'] = POS_MAP.get(recent_stats.position, recent_stats.position)

        # Get loan info from AcademyPlayer (most recent active loan)
        loaned = AcademyPlayer.query.filter_by(player_id=player_id, is_active=True).order_by(AcademyPlayer.updated_at.desc()).first()
        if not loaned:
            loaned = AcademyPlayer.query.filter_by(player_id=player_id).order_by(AcademyPlayer.updated_at.desc()).first()

        if loaned:
            if not result['name']:
                result['name'] = loaned.player_name
            result['loan_team_name'] = loaned.loan_team_name
            result['parent_team_name'] = loaned.primary_team_name

            if loaned.loan_team_id:
                loan_team = Team.query.get(loaned.loan_team_id)
                if loan_team:
                    result['loan_team_logo'] = loan_team.logo
                    result['loan_team_id'] = loan_team.team_id
                    result['loan_team_db_id'] = loaned.loan_team_id

            if loaned.primary_team_id:
                parent_team = Team.query.get(loaned.primary_team_id)
                if parent_team:
                    result['parent_team_logo'] = parent_team.logo
                    result['parent_team_id'] = parent_team.team_id
                    result['primary_team_db_id'] = loaned.primary_team_id

        # If still no name, try supplemental loans
        if not result['name']:
            supplemental = SupplementalLoan.query.filter_by(api_player_id=player_id).first()
            if supplemental:
                result['name'] = supplemental.player_name
                result['loan_team_name'] = supplemental.loan_team_name
                result['parent_team_name'] = supplemental.parent_team_name
                if supplemental.loan_team:
                    result['loan_team_logo'] = supplemental.loan_team.logo
                if supplemental.parent_team:
                    result['parent_team_logo'] = supplemental.parent_team.logo

        # If still no name, try to get from fixture stats
        if not result['name']:
            stats = FixturePlayerStats.query.filter_by(player_api_id=player_id).first()
            if stats:
                result['position'] = stats.position

        # Final fallback for name
        if not result['name']:
            result['name'] = f"Player #{player_id}"

        # Get ALL loans for this season (for mid-season transfers)
        now_utc = datetime.now(timezone.utc)
        current_year = now_utc.year
        current_month = now_utc.month
        season_year = current_year if current_month >= 8 else current_year - 1
        season_prefix = f"{season_year}-{str(season_year + 1)[-2:]}"

        all_season_loans = AcademyPlayer.query.filter(
            AcademyPlayer.player_id == player_id,
            AcademyPlayer.window_key.like(f"{season_prefix}%")
        ).order_by(AcademyPlayer.created_at.asc()).all()

        # Deduplicate by (loan_team_id, window_key)
        seen_loan_keys = set()
        loan_history = []
        for loan in all_season_loans:
            dedup_key = (loan.loan_team_id, loan.window_key)
            if dedup_key in seen_loan_keys:
                continue
            seen_loan_keys.add(dedup_key)

            loan_team = Team.query.get(loan.loan_team_id) if loan.loan_team_id else None
            parent_team = Team.query.get(loan.primary_team_id) if loan.primary_team_id else None

            window_type = 'Summer'
            if loan.window_key and '::' in loan.window_key:
                window_part = loan.window_key.split('::')[1]
                if window_part.upper() == 'JANUARY':
                    window_type = 'January'
                elif window_part.upper() == 'FULL':
                    window_type = 'Summer'
                else:
                    window_type = window_part.title()

            loan_history.append({
                'loan_team_name': loan.loan_team_name,
                'loan_team_id': loan_team.team_id if loan_team else None,
                'loan_team_db_id': loan.loan_team_id,
                'loan_team_logo': loan_team.logo if loan_team else None,
                'parent_team_name': loan.primary_team_name,
                'parent_team_id': parent_team.team_id if parent_team else None,
                'parent_team_logo': parent_team.logo if parent_team else None,
                'window_type': window_type,
                'window_key': loan.window_key,
                'is_active': loan.is_active,
            })

        result['loan_history'] = loan_history
        result['has_multiple_loans'] = len(loan_history) > 1

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error fetching player profile for player_id={player_id}: {e}")
        import traceback
        traceback.print_exc()
        return jsonify(_safe_error_payload(e, 'Failed to fetch player profile')), 500


# ---------------------------------------------------------------------------
# Player season stats endpoint
# ---------------------------------------------------------------------------

@players_bp.route('/players/<int:player_id>/season-stats', methods=['GET'])
def get_public_player_season_stats(player_id: int):
    """Get aggregated season stats for a player at their LOAN CLUB only."""
    try:
        from src.models.weekly import FixturePlayerStats, Fixture
        from src.api_football_client import APIFootballClient
        from sqlalchemy import func

        now_utc = datetime.now(timezone.utc)
        current_year = now_utc.year
        current_month = now_utc.month
        season_start_year = current_year if current_month >= 8 else current_year - 1
        season_start = datetime(season_start_year, 8, 1, tzinfo=timezone.utc)
        season_prefix = f"{season_start_year}-{str(season_start_year + 1)[-2:]}"

        result = {
            'player_id': player_id,
            'season': f"{season_start_year}/{season_start_year + 1}",
            'appearances': 0,
            'minutes': 0,
            'goals': 0,
            'assists': 0,
            'yellows': 0,
            'reds': 0,
            'avg_rating': None,
            'saves': 0,
            'goals_conceded': 0,
            'clean_sheets': 0,
            'source': 'none',
            'loan_clubs_only': True,
            'clubs': [],
        }

        # Find ALL loan teams for this player this season
        all_loans = AcademyPlayer.query.filter(
            AcademyPlayer.player_id == player_id,
            AcademyPlayer.window_key.like(f"{season_prefix}%")
        ).order_by(AcademyPlayer.updated_at.desc()).all()

        if not all_loans:
            loaned = AcademyPlayer.query.filter_by(player_id=player_id).order_by(AcademyPlayer.updated_at.desc()).first()
            all_loans = [loaned] if loaned else []

        if not all_loans:
            # Fallback: compute stats directly from FixturePlayerStats
            # This handles players seeded via squad fetch (no AcademyPlayer record)
            from src.models.tracked_player import TrackedPlayer
            tp = TrackedPlayer.query.filter_by(player_api_id=player_id, is_active=True).first()
            if tp:
                stats_agg = db.session.query(
                    func.count().label('appearances'),
                    func.coalesce(func.sum(FixturePlayerStats.minutes), 0).label('minutes'),
                    func.coalesce(func.sum(FixturePlayerStats.goals), 0).label('goals'),
                    func.coalesce(func.sum(FixturePlayerStats.assists), 0).label('assists'),
                    func.coalesce(func.sum(FixturePlayerStats.yellows), 0).label('yellows'),
                    func.coalesce(func.sum(FixturePlayerStats.reds), 0).label('reds'),
                    func.coalesce(func.sum(FixturePlayerStats.saves), 0).label('saves'),
                    func.coalesce(func.sum(FixturePlayerStats.goals_conceded), 0).label('goals_conceded'),
                ).filter(
                    FixturePlayerStats.player_api_id == player_id,
                ).join(Fixture, FixturePlayerStats.fixture_id == Fixture.id).filter(
                    Fixture.date_utc >= season_start,
                ).first()

                if stats_agg and stats_agg.appearances > 0:
                    # Compute avg rating
                    rated = db.session.query(
                        func.avg(func.cast(FixturePlayerStats.rating, db.Float))
                    ).filter(
                        FixturePlayerStats.player_api_id == player_id,
                        FixturePlayerStats.rating.isnot(None),
                    ).join(Fixture, FixturePlayerStats.fixture_id == Fixture.id).filter(
                        Fixture.date_utc >= season_start,
                    ).scalar()

                    result['appearances'] = stats_agg.appearances
                    result['minutes'] = int(stats_agg.minutes)
                    result['goals'] = int(stats_agg.goals)
                    result['assists'] = int(stats_agg.assists)
                    result['yellows'] = int(stats_agg.yellows)
                    result['reds'] = int(stats_agg.reds)
                    result['saves'] = int(stats_agg.saves)
                    result['goals_conceded'] = int(stats_agg.goals_conceded)
                    result['avg_rating'] = round(float(rated), 2) if rated else None
                    result['source'] = 'fixture-stats'

                    # Add parent team as club
                    parent_team = Team.query.get(tp.team_id)
                    if parent_team:
                        result['clubs'] = [{
                            'team_name': parent_team.name,
                            'team_logo': parent_team.logo,
                            'appearances': stats_agg.appearances,
                            'goals': int(stats_agg.goals),
                            'assists': int(stats_agg.assists),
                            'is_current': True,
                        }]

            return jsonify(result)

        # Check for limited coverage
        primary_loan = all_loans[0]
        if getattr(primary_loan, 'stats_coverage', 'full') == 'limited':
            logger.info(f"Using limited coverage stats for player {player_id}")
            result['appearances'] = primary_loan.appearances or 0
            result['minutes'] = 0
            result['goals'] = primary_loan.goals or 0
            result['assists'] = primary_loan.assists or 0
            result['yellows'] = primary_loan.yellows or 0
            result['reds'] = primary_loan.reds or 0
            result['source'] = 'limited-coverage'
            result['stats_coverage'] = 'limited'

            if primary_loan.loan_team_id:
                loan_team = Team.query.get(primary_loan.loan_team_id)
                if loan_team:
                    result['loan_team'] = loan_team.name
                    result['clubs'] = [{
                        'team_name': loan_team.name,
                        'team_logo': loan_team.logo,
                        'appearances': primary_loan.appearances or 0,
                        'goals': primary_loan.goals or 0,
                        'assists': primary_loan.assists or 0,
                        'is_current': primary_loan.is_active,
                    }]

            return jsonify(result)

        # Build list of loan teams with their API IDs
        loan_teams_info = []
        loan_team_api_ids = []
        for loan in all_loans:
            if loan and loan.loan_team_id:
                loan_team = Team.query.get(loan.loan_team_id)
                if loan_team and loan_team.team_id not in loan_team_api_ids:
                    window_type = 'Summer'
                    if loan.window_key and '::' in loan.window_key:
                        window_part = loan.window_key.split('::')[1]
                        if window_part.upper() == 'JANUARY':
                            window_type = 'January'
                    loan_teams_info.append({
                        'api_id': loan_team.team_id,
                        'name': loan_team.name,
                        'logo': loan_team.logo,
                        'window_type': window_type,
                        'is_active': loan.is_active,
                    })
                    loan_team_api_ids.append(loan_team.team_id)

        result['loan_team'] = loan_teams_info[0]['name'] if loan_teams_info else None
        result['has_multiple_clubs'] = len(loan_teams_info) > 1

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
                    team_id=team_info['api_id'],
                    season=season_start_year,
                )

                if api_totals and api_totals.get('games_played', 0) > 0:
                    club_stats = {
                        'team_name': team_info['name'],
                        'team_logo': team_info['logo'],
                        'window_type': team_info['window_type'],
                        'is_current': team_info['is_active'],
                        'appearances': api_totals.get('games_played', 0),
                        'minutes': api_totals.get('minutes', 0),
                        'goals': api_totals.get('goals', 0),
                        'assists': api_totals.get('assists', 0),
                        'saves': api_totals.get('saves', 0),
                        'goals_conceded': api_totals.get('goals_conceded', 0),
                    }
                    clubs_breakdown.append(club_stats)
                    total_appearances += club_stats['appearances']
                    total_minutes += club_stats['minutes']
                    total_goals += club_stats['goals']
                    total_assists += club_stats['assists']
                    result['source'] = 'api-football'
            except Exception as api_err:
                logger.warning(f"Failed to get API-Football stats for player {player_id} at {team_info['name']}: {api_err}")

        result['appearances'] = total_appearances
        result['minutes'] = total_minutes
        result['goals'] = total_goals
        result['assists'] = total_assists
        result['clubs'] = clubs_breakdown

        # Get detailed stats from local DB
        if loan_team_api_ids:
            stats_query = db.session.query(
                func.count(FixturePlayerStats.id).label('appearances'),
                func.sum(FixturePlayerStats.minutes).label('total_minutes'),
                func.sum(FixturePlayerStats.goals).label('total_goals'),
                func.sum(FixturePlayerStats.assists).label('total_assists'),
                func.sum(FixturePlayerStats.yellows).label('total_yellows'),
                func.sum(FixturePlayerStats.reds).label('total_reds'),
                func.avg(FixturePlayerStats.rating).label('avg_rating'),
                func.sum(FixturePlayerStats.saves).label('total_saves'),
                func.sum(FixturePlayerStats.goals_conceded).label('total_goals_conceded'),
            ).join(
                Fixture, FixturePlayerStats.fixture_id == Fixture.id
            ).filter(
                FixturePlayerStats.player_api_id == player_id,
                FixturePlayerStats.team_api_id.in_(loan_team_api_ids),
                Fixture.date_utc >= season_start
            ).first()

            if stats_query and stats_query.appearances:
                local_appearances = stats_query.appearances or 0
                local_minutes = int(stats_query.total_minutes or 0)
                local_goals = int(stats_query.total_goals or 0)
                local_assists = int(stats_query.total_assists or 0)

                result['yellows'] = int(stats_query.total_yellows or 0)
                result['reds'] = int(stats_query.total_reds or 0)
                result['avg_rating'] = round(float(stats_query.avg_rating or 0), 2) if stats_query.avg_rating else None
                result['saves'] = int(stats_query.total_saves or 0)
                result['goals_conceded'] = int(stats_query.total_goals_conceded or 0)
                result['local_appearances'] = local_appearances

                if local_appearances > result.get('appearances', 0):
                    result['appearances'] = local_appearances
                    result['minutes'] = local_minutes
                    result['goals'] = local_goals
                    result['assists'] = local_assists
                    result['source'] = 'local-db'
                elif result['source'] == 'none':
                    result['appearances'] = local_appearances
                    result['minutes'] = local_minutes
                    result['goals'] = local_goals
                    result['assists'] = local_assists
                    result['source'] = 'local-db'

            # Calculate clean sheets
            clean_sheets_query = db.session.query(
                func.count(FixturePlayerStats.id).label('clean_sheets')
            ).join(
                Fixture, FixturePlayerStats.fixture_id == Fixture.id
            ).filter(
                FixturePlayerStats.player_api_id == player_id,
                FixturePlayerStats.team_api_id.in_(loan_team_api_ids),
                Fixture.date_utc >= season_start,
                FixturePlayerStats.goals_conceded == 0,
                FixturePlayerStats.minutes >= 45
            ).first()

            result['clean_sheets'] = clean_sheets_query.clean_sheets if clean_sheets_query else 0

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error fetching season stats for player_id={player_id}: {e}")
        import traceback
        traceback.print_exc()
        return jsonify(_safe_error_payload(e, 'Failed to fetch season stats')), 500


# ---------------------------------------------------------------------------
# Player commentaries endpoint
# ---------------------------------------------------------------------------

@players_bp.route('/players/<int:player_id>/commentaries', methods=['GET'])
def get_player_commentaries(player_id: int):
    """Get all commentaries/writeups that mention this player."""
    try:
        commentaries = NewsletterCommentary.query.filter(
            NewsletterCommentary.player_id == player_id,
            NewsletterCommentary.is_active == True
        ).order_by(NewsletterCommentary.created_at.desc()).all()

        result = []
        for c in commentaries:
            author = c.author
            newsletter = c.newsletter

            commentary_data = {
                'id': c.id,
                'content': c.content,
                'title': c.title,
                'commentary_type': c.commentary_type,
                'is_premium': c.is_premium,
                'created_at': c.created_at.isoformat() if c.created_at else None,
                'updated_at': c.updated_at.isoformat() if c.updated_at else None,
                'author': {
                    'id': author.id if author else None,
                    'display_name': author.display_name if author else None,
                    'profile_image_url': author.profile_image_url if author else None,
                    'is_journalist': author.is_journalist if author else False,
                } if author else None,
                'newsletter': {
                    'id': newsletter.id if newsletter else None,
                    'title': newsletter.title if newsletter else None,
                    'week_start_date': newsletter.week_start_date.isoformat() if newsletter and newsletter.week_start_date else None,
                    'week_end_date': newsletter.week_end_date.isoformat() if newsletter and newsletter.week_end_date else None,
                    'team_name': newsletter.team.name if newsletter and newsletter.team else None,
                } if newsletter else None,
            }
            result.append(commentary_data)

        # Get unique authors
        unique_authors = {}
        for c in commentaries:
            if c.author and c.author.id not in unique_authors:
                unique_authors[c.author.id] = {
                    'id': c.author.id,
                    'display_name': c.author.display_name,
                    'profile_image_url': c.author.profile_image_url,
                    'is_journalist': c.author.is_journalist,
                    'commentary_count': 0,
                }
            if c.author:
                unique_authors[c.author.id]['commentary_count'] += 1

        return jsonify({
            'player_id': player_id,
            'commentaries': result,
            'total_count': len(result),
            'authors': list(unique_authors.values()),
        })

    except Exception as e:
        logger.error(f"Error fetching commentaries for player_id={player_id}: {e}")
        import traceback
        traceback.print_exc()
        return jsonify(_safe_error_payload(e, 'Failed to fetch player commentaries')), 500
