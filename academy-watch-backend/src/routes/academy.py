"""Academy Tracking API endpoints.

Handles:
- Academy league configuration (CRUD)
- Sync triggers for academy fixtures
- Academy appearance data retrieval
"""
from flask import Blueprint, request, jsonify
from src.models.league import db, AcademyLeague, AcademyAppearance
from src.routes.api import require_api_key
from src.services.academy_sync_service import academy_sync_service
from datetime import datetime, date, timedelta, timezone
import logging

academy_bp = Blueprint('academy', __name__)
logger = logging.getLogger(__name__)


# =============================================================================
# Academy League Management (Admin)
# =============================================================================

@academy_bp.route('/admin/academy-leagues', methods=['GET'])
@require_api_key
def list_academy_leagues():
    """List all configured academy leagues."""
    leagues = AcademyLeague.query.order_by(AcademyLeague.name).all()
    return jsonify({
        'leagues': [l.to_dict() for l in leagues],
        'total': len(leagues),
    })


@academy_bp.route('/admin/academy-leagues', methods=['POST'])
@require_api_key
def create_academy_league():
    """Create a new academy league configuration.

    Body:
    - api_league_id: Required. API-Football league ID
    - name: Required. League name
    - country: Optional. Country name
    - level: Required. 'U18' | 'U21' | 'U23' | 'Reserve'
    - season: Optional. Season year
    - parent_team_id: Optional. Parent club team ID
    """
    data = request.get_json() or {}

    api_league_id = data.get('api_league_id')
    name = (data.get('name') or '').strip()
    level = (data.get('level') or '').strip()

    if not api_league_id:
        return jsonify({'error': 'api_league_id is required'}), 400
    if not name:
        return jsonify({'error': 'name is required'}), 400
    if level not in ('U18', 'U21', 'U23', 'Reserve'):
        return jsonify({'error': 'level must be U18, U21, U23, or Reserve'}), 400

    # Check for duplicate
    existing = AcademyLeague.query.filter_by(api_league_id=api_league_id).first()
    if existing:
        return jsonify({'error': f'League {api_league_id} already exists'}), 409

    league = AcademyLeague(
        api_league_id=api_league_id,
        name=name,
        country=(data.get('country') or '').strip() or None,
        level=level,
        season=data.get('season'),
        parent_team_id=data.get('parent_team_id'),
        is_active=True,
        sync_enabled=True,
    )

    db.session.add(league)
    db.session.commit()

    logger.info(f'Created academy league: {name} ({api_league_id})')

    return jsonify({
        'message': 'League created',
        'league': league.to_dict(),
    }), 201


@academy_bp.route('/admin/academy-leagues/<int:league_id>', methods=['PUT'])
@require_api_key
def update_academy_league(league_id):
    """Update an academy league configuration."""
    league = db.session.get(AcademyLeague, league_id)
    if not league:
        return jsonify({'error': 'League not found'}), 404

    data = request.get_json() or {}

    if 'name' in data:
        league.name = (data['name'] or '').strip()
    if 'country' in data:
        league.country = (data['country'] or '').strip() or None
    if 'level' in data:
        level = (data['level'] or '').strip()
        if level not in ('U18', 'U21', 'U23', 'Reserve'):
            return jsonify({'error': 'level must be U18, U21, U23, or Reserve'}), 400
        league.level = level
    if 'season' in data:
        league.season = data['season']
    if 'parent_team_id' in data:
        league.parent_team_id = data['parent_team_id']
    if 'is_active' in data:
        league.is_active = bool(data['is_active'])
    if 'sync_enabled' in data:
        league.sync_enabled = bool(data['sync_enabled'])

    db.session.commit()

    return jsonify({
        'message': 'League updated',
        'league': league.to_dict(),
    })


@academy_bp.route('/admin/academy-leagues/<int:league_id>', methods=['DELETE'])
@require_api_key
def delete_academy_league(league_id):
    """Delete an academy league and its appearances."""
    league = db.session.get(AcademyLeague, league_id)
    if not league:
        return jsonify({'error': 'League not found'}), 404

    # Delete associated appearances
    AcademyAppearance.query.filter_by(academy_league_id=league_id).delete()

    db.session.delete(league)
    db.session.commit()

    logger.info(f'Deleted academy league: {league.name} ({league.api_league_id})')

    return jsonify({'message': 'League deleted'})


# =============================================================================
# Sync Operations (Admin)
# =============================================================================

@academy_bp.route('/admin/academy-leagues/<int:league_id>/sync', methods=['POST'])
@require_api_key
def sync_academy_league(league_id):
    """Trigger a sync for a specific academy league.

    Optional body:
    - date_from: Start date (YYYY-MM-DD), default: 7 days ago
    - date_to: End date (YYYY-MM-DD), default: today
    """
    league = db.session.get(AcademyLeague, league_id)
    if not league:
        return jsonify({'error': 'League not found'}), 404

    data = request.get_json() or {}

    date_from = None
    date_to = None

    if data.get('date_from'):
        try:
            date_from = date.fromisoformat(data['date_from'])
        except ValueError:
            return jsonify({'error': 'Invalid date_from format (use YYYY-MM-DD)'}), 400

    if data.get('date_to'):
        try:
            date_to = date.fromisoformat(data['date_to'])
        except ValueError:
            return jsonify({'error': 'Invalid date_to format (use YYYY-MM-DD)'}), 400

    result = academy_sync_service.sync_league(
        league=league,
        date_from=date_from,
        date_to=date_to,
    )

    return jsonify({
        'message': 'Sync completed',
        'result': result,
    })


@academy_bp.route('/admin/academy-leagues/sync-all', methods=['POST'])
@require_api_key
def sync_all_academy_leagues():
    """Trigger a sync for all active academy leagues."""
    data = request.get_json() or {}

    date_from = None
    date_to = None

    if data.get('date_from'):
        try:
            date_from = date.fromisoformat(data['date_from'])
        except ValueError:
            return jsonify({'error': 'Invalid date_from format (use YYYY-MM-DD)'}), 400

    if data.get('date_to'):
        try:
            date_to = date.fromisoformat(data['date_to'])
        except ValueError:
            return jsonify({'error': 'Invalid date_to format (use YYYY-MM-DD)'}), 400

    results = academy_sync_service.sync_all_active_leagues(
        date_from=date_from,
        date_to=date_to,
    )

    total_fixtures = sum(r.get('fixtures_processed', 0) for r in results)
    total_appearances = sum(r.get('appearances_created', 0) for r in results)

    return jsonify({
        'message': 'Sync completed',
        'summary': {
            'leagues_synced': len(results),
            'fixtures_processed': total_fixtures,
            'appearances_created': total_appearances,
        },
        'results': results,
    })


# =============================================================================
# Player-level Academy Stats Sync
# =============================================================================

@academy_bp.route('/admin/academy-stats/sync-players', methods=['POST'])
@require_api_key
def sync_academy_player_stats():
    """Sync season-level stats for all tracked academy players.

    Uses /players endpoint which returns richer data than fixture lineups.
    Optional JSON body: {"season": 2025}
    """
    data = request.get_json() or {}
    season = data.get('season')

    results = academy_sync_service.sync_academy_stats_for_players(season=season)

    return jsonify({
        'message': 'Player stats sync completed',
        'results': results,
    })


# =============================================================================
# Academy Appearances (Admin & Public)
# =============================================================================

@academy_bp.route('/admin/academy-appearances', methods=['GET'])
@require_api_key
def list_academy_appearances():
    """List academy appearances with optional filters.

    Query params:
    - player_id: Filter by API player ID
    - loaned_player_id: Filter by AcademyPlayer ID
    - league_id: Filter by academy league ID
    - date_from: Filter from date (YYYY-MM-DD)
    - date_to: Filter to date (YYYY-MM-DD)
    - limit: Max results (default 50, max 200)
    - offset: Pagination offset
    """
    player_id = request.args.get('player_id', type=int)
    loaned_player_id = request.args.get('loaned_player_id', type=int)
    league_id = request.args.get('league_id', type=int)
    date_from_str = request.args.get('date_from')
    date_to_str = request.args.get('date_to')
    limit = min(request.args.get('limit', 50, type=int), 200)
    offset = request.args.get('offset', 0, type=int)

    query = AcademyAppearance.query

    if player_id:
        query = query.filter_by(player_id=player_id)
    if loaned_player_id:
        query = query.filter_by(loaned_player_id=loaned_player_id)
    if league_id:
        query = query.filter_by(academy_league_id=league_id)
    if date_from_str:
        try:
            date_from = date.fromisoformat(date_from_str)
            query = query.filter(AcademyAppearance.fixture_date >= date_from)
        except ValueError:
            pass
    if date_to_str:
        try:
            date_to = date.fromisoformat(date_to_str)
            query = query.filter(AcademyAppearance.fixture_date <= date_to)
        except ValueError:
            pass

    query = query.order_by(AcademyAppearance.fixture_date.desc())
    total = query.count()
    appearances = query.offset(offset).limit(limit).all()

    return jsonify({
        'appearances': [a.to_dict() for a in appearances],
        'total': total,
        'limit': limit,
        'offset': offset,
    })


@academy_bp.route('/players/<int:player_id>/academy-stats', methods=['GET'])
def get_player_academy_stats(player_id):
    """Get academy stats for a player (public endpoint).

    Query params:
    - date_from: Optional start date (YYYY-MM-DD)
    - date_to: Optional end date (YYYY-MM-DD)
    """
    date_from = None
    date_to = None

    if request.args.get('date_from'):
        try:
            date_from = date.fromisoformat(request.args['date_from'])
        except ValueError:
            pass

    if request.args.get('date_to'):
        try:
            date_to = date.fromisoformat(request.args['date_to'])
        except ValueError:
            pass

    stats = academy_sync_service.get_player_academy_stats(
        player_id=player_id,
        date_from=date_from,
        date_to=date_to,
    )

    return jsonify(stats)


@academy_bp.route('/admin/academy-stats/summary', methods=['GET'])
@require_api_key
def get_academy_stats_summary():
    """Get summary statistics for academy tracking."""
    total_leagues = AcademyLeague.query.count()
    active_leagues = AcademyLeague.query.filter_by(is_active=True).count()
    total_appearances = AcademyAppearance.query.count()

    # Recent activity (last 7 days)
    week_ago = date.today() - timedelta(days=7)
    recent_appearances = AcademyAppearance.query.filter(
        AcademyAppearance.fixture_date >= week_ago
    ).count()

    # Tracked players with academy appearances
    tracked_with_appearances = db.session.query(
        AcademyAppearance.loaned_player_id
    ).filter(
        AcademyAppearance.loaned_player_id.isnot(None)
    ).distinct().count()

    return jsonify({
        'leagues': {
            'total': total_leagues,
            'active': active_leagues,
        },
        'appearances': {
            'total': total_appearances,
            'last_7_days': recent_appearances,
        },
        'tracked_players_with_appearances': tracked_with_appearances,
    })
