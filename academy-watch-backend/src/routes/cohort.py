"""Cohort API endpoints.

Handles:
- Admin cohort seeding and management
- Public cohort browsing and analytics
- Rebuild configuration management (presets + audit trail)
"""
from flask import Blueprint, request, jsonify
from src.models.league import db, RebuildConfig, RebuildConfigLog
from src.models.cohort import AcademyCohort, CohortMember
from src.models.journey import PlayerJourney
from src.routes.api import require_api_key
from src.services.cohort_service import CohortService
from src.utils.background_jobs import create_background_job, update_job, get_job
from datetime import datetime, timezone
import multiprocessing
import json
import logging

cohort_bp = Blueprint('cohort', __name__)
logger = logging.getLogger(__name__)


# =============================================================================
# Admin Endpoints
# =============================================================================

@cohort_bp.route('/admin/cohorts/seed', methods=['POST'])
@require_api_key
def admin_seed_cohort():
    """Seed a single cohort.

    Body: {team_api_id, league_api_id, season}
    """
    data = request.get_json() or {}

    team_api_id = data.get('team_api_id')
    league_api_id = data.get('league_api_id')
    season = data.get('season')

    if not all([team_api_id, league_api_id, season]):
        return jsonify({'error': 'team_api_id, league_api_id, and season are required'}), 400

    try:
        # Clear stale cache that may contain empty API responses
        from src.models.api_cache import APICache
        for page in range(1, 11):
            APICache.invalidate_cached('players', {
                'team': int(team_api_id), 'league': int(league_api_id),
                'season': int(season), 'page': page,
            })

        service = CohortService()
        cohort = service.discover_cohort(int(team_api_id), int(league_api_id), int(season))
        return jsonify(cohort.to_dict(include_members=True)), 201
    except Exception as e:
        logger.exception('admin_seed_cohort failed')
        return jsonify({'error': str(e)}), 500


@cohort_bp.route('/admin/cohorts/seed-big6', methods=['POST'])
@require_api_key
def admin_seed_big6():
    """Start Big 6 bulk seeding as a background job.

    Body (all optional): {seasons: [], team_ids: [], league_ids: []}
    """
    from src.utils.rebuild_runner import run_rebuild_process

    data = request.get_json() or {}
    seasons = data.get('seasons')
    team_ids = data.get('team_ids')
    league_ids = data.get('league_ids')

    job_id = create_background_job('seed_big6')

    p = multiprocessing.Process(
        target=run_rebuild_process,
        args=(job_id, 'seed_big6', {'seasons': seasons, 'team_ids': team_ids, 'league_ids': league_ids}),
        daemon=False,
    )
    p.start()
    # Detach: prevent parent's atexit handler from blocking on join()
    multiprocessing.process._children.discard(p)

    return jsonify({
        'message': 'Big 6 seeding started in background',
        'job_id': job_id,
        'status': 'running',
        'check_status_url': f'/api/admin/jobs/{job_id}'
    }), 202


@cohort_bp.route('/admin/cohorts/<int:cohort_id>/sync-journeys', methods=['POST'])
@require_api_key
def admin_sync_cohort_journeys(cohort_id):
    """Trigger journey sync for all members in a cohort."""
    try:
        service = CohortService()
        cohort = service.sync_cohort_journeys(cohort_id)
        return jsonify(cohort.to_dict(include_members=True))
    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        logger.exception('admin_sync_cohort_journeys failed')
        return jsonify({'error': str(e)}), 500


@cohort_bp.route('/admin/cohorts/<int:cohort_id>/refresh-stats', methods=['POST'])
@require_api_key
def admin_refresh_cohort_stats(cohort_id):
    """Recalculate denormalized analytics for a cohort."""
    cohort = db.session.get(AcademyCohort, cohort_id)
    if not cohort:
        return jsonify({'error': 'Cohort not found'}), 404

    try:
        service = CohortService()
        service.refresh_cohort_stats(cohort_id)
        return jsonify(cohort.to_dict())
    except Exception as e:
        logger.exception('admin_refresh_cohort_stats failed')
        return jsonify({'error': str(e)}), 500


@cohort_bp.route('/admin/cohorts/seed-status', methods=['GET'])
@require_api_key
def admin_cohort_seed_status():
    """List all cohorts with sync status."""
    cohorts = AcademyCohort.query.order_by(
        AcademyCohort.season.desc(),
        AcademyCohort.team_name
    ).all()
    return jsonify({
        'cohorts': [c.to_dict() for c in cohorts],
        'total': len(cohorts),
    })


@cohort_bp.route('/admin/cohorts/<int:cohort_id>', methods=['DELETE'])
@require_api_key
def admin_delete_cohort(cohort_id):
    """Delete a cohort and all its members."""
    cohort = db.session.get(AcademyCohort, cohort_id)
    if not cohort:
        return jsonify({'error': 'Cohort not found'}), 404

    db.session.delete(cohort)
    db.session.commit()
    return '', 204


@cohort_bp.route('/admin/cohorts/re-derive-statuses', methods=['POST'])
@require_api_key
def admin_re_derive_statuses():
    """Re-derive current_status for all synced cohort members.

    Fixes data produced by the bug where _derive_status was called
    without parent club context. Iterates all members with
    journey_synced=True, re-runs status derivation with the correct
    parent club from their cohort, then refreshes aggregate stats.

    Body (optional): {cohort_ids: [1, 2, 3]}
    """
    data = request.get_json() or {}
    target_cohort_ids = data.get('cohort_ids')

    service = CohortService()
    current_year = datetime.now().year

    query = CohortMember.query.filter(CohortMember.journey_synced == True)
    if target_cohort_ids:
        query = query.filter(CohortMember.cohort_id.in_(target_cohort_ids))

    members = query.all()
    updated = 0
    errors = []

    for member in members:
        try:
            if not member.journey_id:
                continue

            journey = db.session.get(PlayerJourney, member.journey_id)
            if not journey:
                continue

            cohort = db.session.get(AcademyCohort, member.cohort_id)
            if not cohort:
                continue

            new_status = CohortService._derive_status(
                journey, current_year,
                parent_api_id=cohort.team_api_id,
                parent_club_name=cohort.team_name or '',
            )

            if member.current_status != new_status:
                member.current_status = new_status
                updated += 1

        except Exception as e:
            errors.append(f"Player {member.player_api_id}: {e}")

    db.session.commit()

    # Refresh stats for affected cohorts
    affected_cohort_ids = target_cohort_ids or list(set(m.cohort_id for m in members))
    for cid in affected_cohort_ids:
        service.refresh_cohort_stats(cid)

    return jsonify({
        'members_checked': len(members),
        'statuses_updated': updated,
        'cohorts_refreshed': len(affected_cohort_ids),
        'errors': errors[:20],
    })


# =============================================================================
# Public Endpoints
# =============================================================================

@cohort_bp.route('/cohorts', methods=['GET'])
def list_cohorts():
    """List cohorts with optional filters.

    Query params: team_api_id, season, league_api_id
    """
    query = AcademyCohort.query

    team_api_id = request.args.get('team_api_id', type=int)
    if team_api_id:
        query = query.filter_by(team_api_id=team_api_id)

    season = request.args.get('season', type=int)
    if season:
        query = query.filter_by(season=season)

    league_api_id = request.args.get('league_api_id', type=int)
    if league_api_id:
        query = query.filter_by(league_api_id=league_api_id)

    cohorts = query.order_by(AcademyCohort.season.desc(), AcademyCohort.team_name).all()

    return jsonify({
        'cohorts': [c.to_dict() for c in cohorts],
        'total': len(cohorts),
    })


@cohort_bp.route('/cohorts/<int:cohort_id>', methods=['GET'])
def get_cohort(cohort_id):
    """Get a single cohort, optionally with members."""
    cohort = db.session.get(AcademyCohort, cohort_id)
    if not cohort:
        return jsonify({'error': 'Cohort not found'}), 404

    include_members = request.args.get('include_members', 'false').lower() == 'true'
    return jsonify(cohort.to_dict(include_members=include_members))


@cohort_bp.route('/cohorts/teams', methods=['GET'])
def cohort_teams():
    """Get distinct teams that have cohort data."""
    from src.models.league import TeamProfile

    results = db.session.query(
        AcademyCohort.team_api_id,
        db.func.max(AcademyCohort.team_name).label('team_name'),
    ).filter(
        AcademyCohort.total_players > 0,
    ).group_by(AcademyCohort.team_api_id).order_by(
        db.func.max(AcademyCohort.team_name)
    ).all()

    # Resolve correct parent club logos from TeamProfile
    team_ids = [r.team_api_id for r in results]
    profiles = {p.team_id: p.logo_url for p in
                TeamProfile.query.filter(TeamProfile.team_id.in_(team_ids)).all()}

    teams = [{
        'team_api_id': r.team_api_id,
        'team_name': r.team_name,
        'team_logo': profiles.get(r.team_api_id),
    } for r in results]

    return jsonify({'teams': teams})


@cohort_bp.route('/cohorts/analytics', methods=['GET'])
def cohort_analytics():
    """Cross-club comparison analytics."""
    from src.models.league import TeamProfile

    cohorts = AcademyCohort.query.filter(
        AcademyCohort.sync_status.in_(('complete', 'partial', 'seeded')),
        AcademyCohort.total_players > 0,
    ).all()

    # Build logo lookup from TeamProfile
    team_ids = list(set(c.team_api_id for c in cohorts))
    profiles = {p.team_id: p.logo_url for p in
                TeamProfile.query.filter(TeamProfile.team_id.in_(team_ids)).all()}

    # Group by team
    team_data = {}
    for c in cohorts:
        tid = c.team_api_id
        if tid not in team_data:
            team_data[tid] = {
                'team_api_id': tid,
                'team_name': c.team_name,
                'team_logo': profiles.get(tid),
                'total_players': 0,
                'players_first_team': 0,
                'players_on_loan': 0,
                'players_still_academy': 0,
                'players_released': 0,
                'cohort_count': 0,
                'seasons': [],
            }

        td = team_data[tid]
        td['total_players'] += c.total_players
        td['players_first_team'] += c.players_first_team
        td['players_on_loan'] += c.players_on_loan
        td['players_still_academy'] += c.players_still_academy
        td['players_released'] += c.players_released
        td['cohort_count'] += 1
        if c.season not in td['seasons']:
            td['seasons'].append(c.season)

    # Calculate conversion rates
    analytics = []
    for td in team_data.values():
        total = td['total_players']
        td['conversion_rate'] = round(td['players_first_team'] / total * 100, 1) if total > 0 else 0
        td['seasons'] = sorted(td['seasons'])
        analytics.append(td)

    analytics.sort(key=lambda x: x['conversion_rate'], reverse=True)

    return jsonify({'analytics': analytics})


# =============================================================================
# Full Academy Rebuild
# =============================================================================

@cohort_bp.route('/admin/academy/full-rebuild', methods=['POST'])
@require_api_key
def admin_full_rebuild():
    """Run the full academy rebuild pipeline as a background job.

    Stages:
      1. Clean slate (delete tracked players, journeys, cohorts, loans, locations)
      2. Seed academy leagues
      3. Cohort discovery + journey sync (Big 6 seeding)
      4. Create TrackedPlayer records for each team
      5. Link orphaned journeys
      6. Refresh statuses
      7. Seed club locations

    Body (all optional):
      config_id: int (load specific RebuildConfig; otherwise uses active config)
      team_ids: list of API team IDs (override)
      seasons: list of season years (override)
      skip_clean: bool (default: false)
      skip_cohorts: bool (default: false)
    """
    from src.services.big6_seeding_service import BIG_6, SEASONS
    from src.utils.rebuild_runner import run_rebuild_process

    data = request.get_json() or {}

    # Load rebuild config: explicit config_id > active config > hardcoded defaults
    config_id_used = None
    if data.get('config_id'):
        rc = RebuildConfig.query.get(data['config_id'])
        if not rc:
            return jsonify({'error': f'RebuildConfig {data["config_id"]} not found'}), 404
        try:
            rebuild_cfg = json.loads(rc.config_json)
        except (json.JSONDecodeError, TypeError):
            rebuild_cfg = {}
        config_id_used = rc.id
    else:
        rebuild_cfg, config_id_used = get_active_rebuild_config()

    # Request body overrides take precedence over stored config
    team_ids_cfg = rebuild_cfg.get('team_ids', {})
    team_ids = data.get('team_ids') or [int(k) for k in team_ids_cfg.keys()] or list(BIG_6.keys())
    seasons = data.get('seasons') or rebuild_cfg.get('seasons') or SEASONS
    skip_clean = data.get('skip_clean', False)
    skip_cohorts = data.get('skip_cohorts', False)

    # Resolve league_ids to team IDs and merge with explicit team_ids
    league_ids_cfg = rebuild_cfg.get('league_ids', [])
    if league_ids_cfg:
        from src.models.league import Team, League
        seen = set(team_ids)
        for lid in league_ids_cfg:
            league = League.query.filter_by(league_id=lid).first()
            if league:
                for t in Team.query.filter_by(league_id=league.id, is_active=True).all():
                    if t.team_id not in seen:
                        team_ids.append(t.team_id)
                        seen.add(t.team_id)

    job_id = create_background_job('full_rebuild')

    # Merge rebuild config params into the job kwargs
    job_config = {
        'team_ids': team_ids,
        'league_ids': league_ids_cfg,
        'seasons': seasons,
        'skip_clean': skip_clean,
        'skip_cohorts': skip_cohorts,
        'use_transfers_for_status': rebuild_cfg.get('use_transfers_for_status', True),
        'inactivity_threshold_years': rebuild_cfg.get('inactivity_threshold_years', 2),
        'cohort_discover_timeout': rebuild_cfg.get('cohort_discover_timeout', 120),
        'player_sync_timeout': rebuild_cfg.get('player_sync_timeout', 90),
        'rate_limit_per_minute': rebuild_cfg.get('rate_limit_per_minute', 280),
        'rate_limit_per_day': rebuild_cfg.get('rate_limit_per_day', 7000),
        'config_id': config_id_used,
    }

    p = multiprocessing.Process(
        target=run_rebuild_process,
        args=(job_id, 'full_rebuild', job_config),
        daemon=False,
    )
    p.start()
    # Detach: prevent parent's atexit handler from blocking on join()
    multiprocessing.process._children.discard(p)

    return jsonify({
        'message': 'Full academy rebuild started in background',
        'job_id': job_id,
        'status': 'running',
        'check_status_url': f'/api/admin/jobs/{job_id}',
        'config': job_config,
    }), 202


# =============================================================================
# Rebuild Configuration Endpoints
# =============================================================================

def _get_default_config():
    """Return the hardcoded default configuration as a dict."""
    from src.services.big6_seeding_service import BIG_6, SEASONS, COHORT_DISCOVER_TIMEOUT, PLAYER_SYNC_TIMEOUT
    from src.services.youth_competition_resolver import DEFAULT_YOUTH_LEAGUES
    return {
        'team_ids': {str(k): v for k, v in BIG_6.items()},
        'league_ids': [],
        'seasons': list(SEASONS),
        'youth_leagues': [
            {'key': yl['key'], 'name': yl['name'], 'fallback_id': yl['fallback_id'], 'level': yl['level']}
            for yl in DEFAULT_YOUTH_LEAGUES
        ],
        'use_transfers_for_status': True,
        'inactivity_release_years': 2,
        'assume_full_minutes': False,
        'cohort_discover_timeout': COHORT_DISCOVER_TIMEOUT,
        'player_sync_timeout': PLAYER_SYNC_TIMEOUT,
        'rate_limit_per_minute': 280,
        'rate_limit_per_day': 7000,
    }


def _compute_diff(old_config, new_config):
    """Compute a diff between two config dicts: {key: {old, new}} for changed fields."""
    diff = {}
    all_keys = set(list(old_config.keys()) + list(new_config.keys()))
    for key in all_keys:
        old_val = old_config.get(key)
        new_val = new_config.get(key)
        if old_val != new_val:
            diff[key] = {'old': old_val, 'new': new_val}
    return diff


def _log_config_change(config, action, diff=None):
    """Write an audit log entry for a config change."""
    log = RebuildConfigLog(
        config_id=config.id,
        action=action,
        diff_json=json.dumps(diff) if diff else None,
        snapshot_json=config.config_json,
    )
    db.session.add(log)


def get_active_rebuild_config():
    """Load the active RebuildConfig as a dict, falling back to hardcoded defaults."""
    active = RebuildConfig.query.filter_by(is_active=True).first()
    if active:
        try:
            return json.loads(active.config_json), active.id
        except (json.JSONDecodeError, TypeError):
            pass
    return _get_default_config(), None


@cohort_bp.route('/admin/rebuild-configs/defaults', methods=['GET'])
@require_api_key
def admin_rebuild_config_defaults():
    """Return the current hardcoded defaults as JSON."""
    return jsonify(_get_default_config())


@cohort_bp.route('/admin/rebuild-configs', methods=['GET'])
@require_api_key
def admin_list_rebuild_configs():
    """List all saved rebuild configurations."""
    configs = RebuildConfig.query.order_by(RebuildConfig.updated_at.desc()).all()
    return jsonify([c.to_dict(include_config=False) for c in configs])


@cohort_bp.route('/admin/rebuild-configs/<int:config_id>', methods=['GET'])
@require_api_key
def admin_get_rebuild_config(config_id):
    """Get a single rebuild config with full details and recent history."""
    config = RebuildConfig.query.get_or_404(config_id)
    result = config.to_dict()
    recent_logs = (config.logs
                   .order_by(RebuildConfigLog.created_at.desc())
                   .limit(20)
                   .all())
    result['history'] = [l.to_dict() for l in recent_logs]
    return jsonify(result)


@cohort_bp.route('/admin/rebuild-configs', methods=['POST'])
@require_api_key
def admin_create_rebuild_config():
    """Create a new rebuild configuration.

    Body:
        name: str (required)
        config: dict (optional, defaults to hardcoded defaults)
        notes: str (optional)
        clone_from: int (optional, config ID to clone from)
    """
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'Name is required'}), 400

    if RebuildConfig.query.filter_by(name=name).first():
        return jsonify({'error': f'Config "{name}" already exists'}), 409

    # Determine initial config
    clone_id = data.get('clone_from')
    if clone_id:
        source = RebuildConfig.query.get(clone_id)
        if not source:
            return jsonify({'error': f'Clone source {clone_id} not found'}), 404
        config_dict = json.loads(source.config_json)
    elif data.get('config'):
        config_dict = data['config']
    else:
        config_dict = _get_default_config()

    config = RebuildConfig(
        name=name,
        is_active=False,
        config_json=json.dumps(config_dict),
        notes=data.get('notes', ''),
    )
    db.session.add(config)
    db.session.flush()
    _log_config_change(config, 'created')
    db.session.commit()

    return jsonify(config.to_dict()), 201


@cohort_bp.route('/admin/rebuild-configs/<int:config_id>', methods=['PUT'])
@require_api_key
def admin_update_rebuild_config(config_id):
    """Update a rebuild configuration. Logs the diff.

    Body:
        name: str (optional)
        config: dict (optional, partial or full replacement)
        notes: str (optional)
    """
    config = RebuildConfig.query.get_or_404(config_id)
    data = request.get_json() or {}

    if 'name' in data:
        new_name = (data['name'] or '').strip()
        if not new_name:
            return jsonify({'error': 'Name cannot be empty'}), 400
        existing = RebuildConfig.query.filter_by(name=new_name).first()
        if existing and existing.id != config_id:
            return jsonify({'error': f'Config "{new_name}" already exists'}), 409
        config.name = new_name

    if 'notes' in data:
        config.notes = data['notes']

    if 'config' in data:
        try:
            old_config = json.loads(config.config_json)
        except (json.JSONDecodeError, TypeError):
            old_config = {}
        new_config = data['config']
        diff = _compute_diff(old_config, new_config)
        config.config_json = json.dumps(new_config)
        _log_config_change(config, 'updated', diff=diff)
    else:
        _log_config_change(config, 'updated')

    db.session.commit()
    return jsonify(config.to_dict())


@cohort_bp.route('/admin/rebuild-configs/<int:config_id>/activate', methods=['POST'])
@require_api_key
def admin_activate_rebuild_config(config_id):
    """Set a config as the active one. Deactivates the previous active config."""
    config = RebuildConfig.query.get_or_404(config_id)

    if config.is_active:
        return jsonify({'message': 'Already active', **config.to_dict()})

    # Deactivate current active
    prev = RebuildConfig.query.filter_by(is_active=True).first()
    if prev:
        prev.is_active = False
        _log_config_change(prev, 'deactivated')

    config.is_active = True
    _log_config_change(config, 'activated')
    db.session.commit()

    return jsonify(config.to_dict())


@cohort_bp.route('/admin/rebuild-configs/<int:config_id>', methods=['DELETE'])
@require_api_key
def admin_delete_rebuild_config(config_id):
    """Delete a rebuild configuration (cannot delete active config)."""
    config = RebuildConfig.query.get_or_404(config_id)

    if config.is_active:
        return jsonify({'error': 'Cannot delete the active configuration'}), 400

    db.session.delete(config)
    db.session.commit()
    return jsonify({'message': f'Config "{config.name}" deleted'})


@cohort_bp.route('/admin/rebuild-configs/<int:config_id>/history', methods=['GET'])
@require_api_key
def admin_rebuild_config_history(config_id):
    """Get the full change history for a config."""
    config = RebuildConfig.query.get_or_404(config_id)
    logs = (config.logs
            .order_by(RebuildConfigLog.created_at.desc())
            .all())
    return jsonify([l.to_dict() for l in logs])
