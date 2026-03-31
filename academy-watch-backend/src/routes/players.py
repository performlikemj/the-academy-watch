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
    Player,
    Team,
    NewsletterCommentary,
)
from src.models.tracked_player import TrackedPlayer

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

        # Find ALL tracked players for this player
        tracked = TrackedPlayer.query.filter_by(
            player_api_id=player_id, is_active=True,
        ).all()

        if not tracked:
            tracked = TrackedPlayer.query.filter_by(
                player_api_id=player_id,
            ).order_by(TrackedPlayer.updated_at.desc()).limit(1).all()

        # Build a map of team_api_id -> team info
        # For on_loan: use current_club (loan destination)
        # For first_team/academy: use parent club (team)
        loan_teams_info = {}
        for tp in tracked:
            if tp.status == 'on_loan' and tp.current_club_api_id:
                loan_teams_info[tp.current_club_api_id] = {
                    'name': tp.current_club_name or (tp.current_club.name if tp.current_club else 'Unknown'),
                    'logo': tp.current_club.logo if tp.current_club else None,
                    'window_type': 'Summer',
                    'is_active': tp.is_active,
                }
            elif tp.team:
                loan_teams_info[tp.team.team_id] = {
                    'name': tp.team.name,
                    'logo': tp.team.logo,
                    'window_type': 'Summer',
                    'is_active': tp.is_active,
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
        player_name_for_sync = tracked[0].player_name if tracked else None

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

        # Enrich from TrackedPlayer (position, status, sale_fee, loan/parent team)
        tp = TrackedPlayer.query.filter_by(player_api_id=player_id, is_active=True).first()
        if not tp:
            tp = TrackedPlayer.query.filter_by(player_api_id=player_id).order_by(TrackedPlayer.updated_at.desc()).first()

        if tp:
            if not result['position'] and tp.position:
                result['position'] = tp.position
            if not result['name']:
                result['name'] = tp.player_name
            result['status'] = tp.status
            result['sale_fee'] = tp.sale_fee

            # Loan team info
            result['loan_team_name'] = tp.current_club_name
            if tp.current_club:
                result['loan_team_logo'] = tp.current_club.logo
                result['loan_team_id'] = tp.current_club.team_id
                result['loan_team_db_id'] = tp.current_club_db_id
            elif tp.current_club_api_id:
                result['loan_team_id'] = tp.current_club_api_id

            # Parent team info
            if tp.team:
                result['parent_team_name'] = tp.team.name
                result['parent_team_logo'] = tp.team.logo
                result['parent_team_id'] = tp.team.team_id
                result['primary_team_db_id'] = tp.team_id

        if not result['position']:
            POS_MAP = {'G': 'Goalkeeper', 'D': 'Defender', 'M': 'Midfielder', 'F': 'Attacker'}
            recent_stats = FixturePlayerStats.query.filter_by(
                player_api_id=player_id
            ).filter(
                FixturePlayerStats.position.isnot(None)
            ).order_by(FixturePlayerStats.id.desc()).first()
            if recent_stats:
                result['position'] = POS_MAP.get(recent_stats.position, recent_stats.position)

        # If still no name, try to get from fixture stats
        if not result['name']:
            stats = FixturePlayerStats.query.filter_by(player_api_id=player_id).first()
            if stats:
                result['position'] = stats.position

        # Final fallback for name
        if not result['name']:
            result['name'] = f"Player #{player_id}"

        # Build loan history from all TrackedPlayer records for this player
        all_tracked = TrackedPlayer.query.filter_by(
            player_api_id=player_id,
        ).order_by(TrackedPlayer.created_at.asc()).all()

        seen_clubs = set()
        loan_history = []
        for t in all_tracked:
            if not t.current_club_api_id:
                continue
            if t.current_club_api_id in seen_clubs:
                continue
            seen_clubs.add(t.current_club_api_id)

            loan_history.append({
                'loan_team_name': t.current_club_name,
                'loan_team_id': t.current_club_api_id,
                'loan_team_db_id': t.current_club_db_id,
                'loan_team_logo': t.current_club.logo if t.current_club else None,
                'parent_team_name': t.team.name if t.team else None,
                'parent_team_id': t.team.team_id if t.team else None,
                'parent_team_logo': t.team.logo if t.team else None,
                'window_type': 'Summer',
                'window_key': None,
                'is_active': t.is_active,
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

        # Find tracked players for this player
        all_tracked = TrackedPlayer.query.filter_by(
            player_api_id=player_id, is_active=True,
        ).all()

        if not all_tracked:
            tp_single = TrackedPlayer.query.filter_by(player_api_id=player_id).order_by(TrackedPlayer.updated_at.desc()).first()
            all_tracked = [tp_single] if tp_single else []

        # Check for limited coverage
        if all_tracked and all_tracked[0].data_depth in ('events_only', 'profile_only'):
            tp = all_tracked[0]
            computed = tp.compute_stats()
            result['appearances'] = computed['appearances']
            result['minutes'] = computed['minutes_played']
            result['goals'] = computed['goals']
            result['assists'] = computed['assists']
            result['yellows'] = computed['yellows']
            result['reds'] = computed['reds']
            result['source'] = 'limited-coverage'
            result['stats_coverage'] = 'limited'

            if tp.current_club:
                result['loan_team'] = tp.current_club.name
                result['clubs'] = [{
                    'team_name': tp.current_club.name,
                    'team_logo': tp.current_club.logo,
                    'appearances': computed['appearances'],
                    'goals': computed['goals'],
                    'assists': computed['assists'],
                    'is_current': tp.is_active,
                }]

            return jsonify(result)

        if not all_tracked:
            return jsonify(result)

        # Build list of clubs with their API IDs from TrackedPlayer
        # For on_loan: use current_club (loan destination)
        # For first_team/academy: use parent club (team)
        loan_teams_info = []
        loan_team_api_ids = []
        for tp in all_tracked:
            if not tp:
                continue
            if tp.status == 'on_loan' and tp.current_club_api_id:
                club_api_id = tp.current_club_api_id
                club_name = tp.current_club_name or (tp.current_club.name if tp.current_club else 'Unknown')
                club_logo = tp.current_club.logo if tp.current_club else None
            elif tp.team:
                club_api_id = tp.team.team_id
                club_name = tp.team.name
                club_logo = tp.team.logo
            else:
                continue

            if club_api_id not in loan_team_api_ids:
                loan_teams_info.append({
                    'api_id': club_api_id,
                    'name': club_name,
                    'logo': club_logo,
                    'window_type': 'Summer',
                    'is_active': tp.is_active,
                })
                loan_team_api_ids.append(club_api_id)

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
