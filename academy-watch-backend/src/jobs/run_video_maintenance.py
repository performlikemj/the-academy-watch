"""Scheduled job: video maintenance.

Reaps heartbeat-dead video analysis jobs (``video_queue.reap_stale_jobs``) so retries can happen
without an admin calling the reap endpoint by hand. Raw-footage retention expiry joins this job in a
later task.

Usage:
    python -m src.jobs.run_video_maintenance [--dry-run]
"""

import logging
import sys

from src.main import app
from src.services import video_queue

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def run(dry_run=False) -> dict:
    """Run every maintenance step once. Returns counts so a caller (or a test) can see what happened."""
    if dry_run:
        logger.info("video maintenance dry run: nothing changed")
        return {"stale_failed": 0, "dry_run": True}
    stale = video_queue.reap_stale_jobs()
    logger.info("video maintenance: stale-failed %d job(s)", stale)
    return {"stale_failed": stale, "dry_run": False}


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    with app.app_context():
        run(dry_run=dry_run)
