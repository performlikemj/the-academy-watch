"""Scheduled job: Self-healing transfer window refresh.

Detects loan club changes for tracked players by re-syncing journey data
from API-Football, updates statuses, and cascades fixture syncs.

During transfer windows (Jan, Jun-Aug + 7-day buffer), performs a full
journey resync. Outside windows, does a lighter local-data-only status refresh.

Usage:
    python src/jobs/run_transfer_window_heal.py [--dry-run]
"""

import json
import logging
import sys
from datetime import UTC, datetime

from src.main import app
from src.models.league import db
from src.utils.background_jobs import has_running_job
from src.utils.job_utils import is_job_paused, teams_with_active_tracked_players

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def is_transfer_window() -> bool:
    """Check if today falls within a transfer window.

    Winter window: January 1 - February 7
    Summer window: June 1 - September 7

    Includes a ~7 day buffer past each window close because API-Football
    data can take a few days to update after deadline day.
    """
    today = datetime.now(UTC).date()
    month, day = today.month, today.day
    winter = month == 1 or (month == 2 and day <= 7)
    summer = 6 <= month <= 8 or (month == 9 and day <= 7)
    return winter or summer


def run(dry_run=False):
    from src.services.transfer_heal_service import refresh_and_heal

    # Clean transaction state
    try:
        db.session.rollback()
    except Exception:
        pass

    if is_job_paused("transfer_heal_paused"):
        logger.info("Transfer heal is paused by admin. Exiting.")
        return [{"error": "paused"}]

    if has_running_job("transfer_heal"):
        logger.info("Another transfer heal job is already running. Exiting.")
        return [{"error": "already_running"}]

    # Always resync journeys — transfer cross-reference needs fresh
    # transfer data to detect players who moved but haven't played yet.
    # The window check only controlled depth before, but skipping resync
    # entirely meant current_club never got updated outside windows.
    resync = True
    logger.info(
        "Transfer heal starting. transfer_window=%s, resync_journeys=%s, dry_run=%s",
        is_transfer_window(),
        resync,
        dry_run,
    )

    team_ids = teams_with_active_tracked_players()
    logger.info("Processing %d teams", len(team_ids))

    results = []
    for team_db_id in team_ids:
        if is_job_paused("transfer_heal_paused"):
            results.append({"team_id": team_db_id, "error": "stopped_by_admin"})
            break
        try:
            # Clean transaction before each team
            try:
                db.session.rollback()
            except Exception:
                pass

            result = refresh_and_heal(
                team_id=team_db_id,
                resync_journeys=resync,
                dry_run=dry_run,
                cascade_fixtures=True,
            )
            results.append({"team_id": team_db_id, **result})
            logger.info(
                "Team %d: %d/%d updated, %d changed, %d fixture syncs",
                team_db_id,
                result["updated"],
                result["total"],
                len(result["players_changed"]),
                result["fixture_syncs_triggered"],
            )
        except Exception as e:
            try:
                db.session.rollback()
            except Exception:
                pass
            logger.error("Team %d failed: %s", team_db_id, e)
            results.append({"team_id": team_db_id, "error": str(e)})

    logger.info("Transfer heal complete. Results: %s", json.dumps(results, default=str))
    return results


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    with app.app_context():
        run(dry_run=dry_run)
