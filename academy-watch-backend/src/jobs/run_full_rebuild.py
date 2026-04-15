"""Scheduled job: Full data rebuild from scratch.

Wipes all tracked player, journey, and cohort data, then rebuilds
everything from API-Football using the current classification logic.

7 stages:
  1. Clean slate (delete all academy/journey/tracked data)
  2. Seed academy leagues
  3. Cohort discovery + journey sync
  4. Create TrackedPlayer records
  5. Link orphaned journeys
  6. Refresh statuses
  7. Seed club locations

Usage:
    python -m src.jobs.run_full_rebuild [--skip-clean]
"""

import logging
import sys

from src.main import app
from src.models.league import db
from src.utils.background_jobs import create_background_job, update_job

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def run(skip_clean=False):
    from src.utils.rebuild_runner import run_rebuild_process

    try:
        db.session.rollback()
    except Exception:
        pass

    logger.info("Full rebuild starting. skip_clean=%s", skip_clean)

    # Create a background job record for tracking
    job_id = create_background_job("full_rebuild")
    logger.info("Job ID: %s", job_id)

    try:
        run_rebuild_process(
            job_id,
            "full_rebuild",
            {
                "skip_clean": skip_clean,
            },
        )
        logger.info("Full rebuild completed successfully.")
    except Exception as e:
        logger.error("Full rebuild failed: %s", e)
        update_job(job_id, status="failed", error=str(e))
        raise


if __name__ == "__main__":
    skip_clean = "--skip-clean" in sys.argv
    with app.app_context():
        run(skip_clean=skip_clean)
