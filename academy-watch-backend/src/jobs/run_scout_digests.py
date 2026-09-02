"""Scheduled job: send scout watchlist and follow-list digests.

Pages through every eligible user while preserving the digest service's per-call
cap. Live sending is the default; ``--dry-run`` renders without sending or
updating digest snapshots.

Usage:
    python -m src.jobs.run_scout_digests [--dry-run] [--min-interval-hours HOURS]
"""

import argparse
import json
import logging
from datetime import UTC, datetime, timedelta

from src.main import app
from src.routes.scout import _get_api_client
from src.services.scout_digest_service import MAX_DIGEST_USERS, send_scout_digests

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

DEFAULT_MIN_INTERVAL_HOURS = 144


def _utcnow() -> datetime:
    return datetime.now(UTC)


def run(dry_run: bool = False, min_interval_hours: int = DEFAULT_MIN_INTERVAL_HOURS) -> dict:
    """Send all due digest pages and return operator-facing totals."""
    if min_interval_hours < 0:
        raise ValueError("min_interval_hours must be non-negative")

    summary = {"users_considered": 0, "sent": 0, "skipped": 0, "errors": 0}
    cursor = 0
    skip_sent_since = _utcnow() - timedelta(hours=min_interval_hours) if min_interval_hours else None

    try:
        api_client = _get_api_client()
        while True:
            page = send_scout_digests(
                dry_run=dry_run,
                limit=MAX_DIGEST_USERS,
                api_client=api_client,
                cursor=cursor,
                skip_sent_since=skip_sent_since,
                report_job_metrics=True,
            )
            summary["users_considered"] += int(page["users_processed"])
            for key in ("sent", "skipped", "errors"):
                summary[key] += int(page.get(key, 0))

            next_cursor = page.get("next_cursor")
            if next_cursor is None:
                break
            if isinstance(next_cursor, bool) or not isinstance(next_cursor, int) or next_cursor <= cursor:
                logger.error("Scout digest paging returned a non-advancing cursor")
                summary["errors"] += 1
                break
            cursor = next_cursor
    except Exception:
        logger.exception("Scout digest job failed")
        summary["errors"] += 1

    return summary


def _non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return parsed


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--min-interval-hours",
        type=_non_negative_int,
        default=DEFAULT_MIN_INTERVAL_HOURS,
        help="skip users sent a digest within this window; 0 disables the guard (default: 144)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    with app.app_context():
        summary = run(dry_run=args.dry_run, min_interval_hours=args.min_interval_hours)
    print(json.dumps(summary, sort_keys=True, separators=(",", ":")), flush=True)
    return 1 if summary["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
