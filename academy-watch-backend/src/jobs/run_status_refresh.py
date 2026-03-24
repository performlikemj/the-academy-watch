"""Scheduled job: Refresh tracked player statuses.

Re-classifies all tracked players by checking their latest transfer data
against API-Football. Fixes stale loan statuses (e.g., players marked as
on_loan who were permanently sold) and updates owning-club relationships.

Usage:
    python -m src.jobs.run_status_refresh [--dry-run]
"""

import json
import sys
import logging
from datetime import datetime, timezone

from src.main import app
from src.models.league import db
from src.utils.job_utils import teams_with_active_tracked_players, is_job_paused
from src.utils.background_jobs import has_running_job

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')


def run(dry_run=False):
    from src.services.transfer_heal_service import refresh_and_heal

    try:
        db.session.rollback()
    except Exception:
        pass

    if is_job_paused('status_refresh_paused'):
        logger.info('Status refresh is paused by admin. Exiting.')
        return [{'error': 'paused'}]

    if has_running_job('status_refresh'):
        logger.info('Another status refresh job is already running. Exiting.')
        return [{'error': 'already_running'}]

    logger.info('Status refresh starting. resync_journeys=True, dry_run=%s', dry_run)

    team_ids = teams_with_active_tracked_players()
    logger.info('Processing %d teams', len(team_ids))

    results = []
    total_changed = 0
    for team_db_id in team_ids:
        if is_job_paused('status_refresh_paused'):
            results.append({'team_id': team_db_id, 'error': 'stopped_by_admin'})
            break
        try:
            try:
                db.session.rollback()
            except Exception:
                pass

            result = refresh_and_heal(
                team_id=team_db_id,
                resync_journeys=True,
                dry_run=dry_run,
                cascade_fixtures=True,
            )
            changed = len(result.get('players_changed', []))
            total_changed += changed
            results.append({'team_id': team_db_id, **result})
            logger.info(
                'Team %d: %d/%d updated, %d changed, %d fixture syncs',
                team_db_id,
                result['updated'],
                result['total'],
                changed,
                result['fixture_syncs_triggered'],
            )
        except Exception as e:
            try:
                db.session.rollback()
            except Exception:
                pass
            logger.error('Team %d failed: %s', team_db_id, e)
            results.append({'team_id': team_db_id, 'error': str(e)})

    logger.info('Status refresh complete. %d players changed across %d teams.', total_changed, len(team_ids))
    return results


if __name__ == '__main__':
    dry_run = '--dry-run' in sys.argv
    with app.app_context():
        run(dry_run=dry_run)
