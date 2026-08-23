"""Scheduled job: video maintenance.

Reaps heartbeat-dead video analysis jobs (``video_queue.reap_stale_jobs``) so retries can happen
without an admin calling the reap endpoint by hand, then expires raw footage past its 90-day retention
(``video_retention.expire_raw_footage``).

Usage:
    python -m src.jobs.run_video_maintenance [--dry-run]
"""

import logging
import sys

from src.main import app
from src.services import video_queue, video_retention

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def run(dry_run=False) -> dict:
    """Run every maintenance step once. Returns counts so a caller (or a test) can see what happened."""
    if dry_run:
        retention = video_retention.expire_raw_footage(dry_run=True)
        logger.info("video maintenance dry run: nothing changed (%d match(es) due for expiry)", retention["due"])
        return {"stale_failed": 0, "retention": retention, "dry_run": True}
    stale = video_queue.reap_stale_jobs()
    retention = video_retention.expire_raw_footage()
    logger.info(
        "video maintenance: stale-failed %d job(s); footage expired %d of %d due (%d failed)",
        stale,
        retention["expired"],
        retention["due"],
        retention["failed"],
    )
    return {"stale_failed": stale, "retention": retention, "dry_run": False}


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    with app.app_context():
        run(dry_run=dry_run)
