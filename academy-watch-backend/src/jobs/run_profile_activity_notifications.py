"""Scheduled job: send opted-in weekly profile-activity notifications.

Usage:
    python /app/src/jobs/run_profile_activity_notifications.py [--dry-run]
    python -m src.jobs.run_profile_activity_notifications [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from contextlib import redirect_stdout
from datetime import UTC, datetime

# The application currently has a legacy import-time diagnostic on stdout.
# Keep this job's stdout machine-readable: its only stdout line is the summary.
with redirect_stdout(sys.stderr):
    from src.main import app

from src.services.profile_activity_notification_service import (
    DEFAULT_MAX_SENDS,
    MAX_PROFILE_ACTIVITY_USERS,
    send_profile_activity_notifications,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

_TRUE_VALUES = frozenset(("1", "true", "yes", "on"))


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _max_sends_from_env() -> int:
    raw = os.getenv("PROFILE_ACTIVITY_MAX_SENDS", str(DEFAULT_MAX_SENDS)).strip()
    try:
        value = int(raw)
    except (TypeError, ValueError):
        logger.warning(
            "Invalid PROFILE_ACTIVITY_MAX_SENDS=%r; using %d",
            raw,
            DEFAULT_MAX_SENDS,
        )
        return DEFAULT_MAX_SENDS
    if value < 0:
        logger.warning("Negative PROFILE_ACTIVITY_MAX_SENDS=%r; using 0", raw)
        return 0
    return value


def run(*, dry_run: bool = False, max_sends: int = DEFAULT_MAX_SENDS, now=None) -> dict:
    """Page through eligible accounts within one whole-run send budget."""

    try:
        remaining = max(int(max_sends), 0)
    except (TypeError, ValueError):
        remaining = DEFAULT_MAX_SENDS
    summary = {
        "dry_run": bool(dry_run),
        "users_considered": 0,
        "sent": 0,
        "skipped_no_activity": 0,
        "skipped_no_subjects": 0,
        "errors": 0,
        "pages": 0,
        "budget_exhausted": remaining == 0,
    }
    if remaining == 0:
        return summary

    cursor = None
    run_now = now if now is not None else _utcnow()
    while True:
        try:
            page = send_profile_activity_notifications(
                dry_run=dry_run,
                cursor=cursor,
                limit=MAX_PROFILE_ACTIVITY_USERS,
                max_sends=remaining,
                now=run_now,
            )
        except Exception:
            logger.exception("Profile activity notification job failed at cursor=%r", cursor)
            summary["errors"] += 1
            break

        summary["pages"] += 1
        for key in ("users_considered", "sent", "skipped_no_activity", "skipped_no_subjects", "errors"):
            summary[key] += int(page.get(key, 0))

        attempts = len(page.get("previews", ())) if dry_run else int(page.get("sent", 0)) + int(page.get("errors", 0))
        if attempts < 0 or attempts > remaining:
            logger.error(
                "Profile activity page exceeded its remaining budget: remaining=%r attempts=%r",
                remaining,
                attempts,
            )
            summary["errors"] += 1
            break
        remaining -= attempts

        if page.get("budget_exhausted") or remaining == 0:
            summary["budget_exhausted"] = True
            break

        next_cursor = page.get("next_cursor")
        if next_cursor is None:
            break
        current_cursor = cursor or 0
        if isinstance(next_cursor, bool) or not isinstance(next_cursor, int) or next_cursor <= current_cursor:
            logger.error(
                "Profile activity paging returned a non-advancing cursor: cursor=%r next_cursor=%r users_considered=%r",
                cursor,
                next_cursor,
                page.get("users_considered"),
            )
            summary["errors"] += 1
            break
        cursor = next_cursor

    return summary


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    dry_run = args.dry_run or os.getenv("PROFILE_ACTIVITY_DRY_RUN", "").strip().lower() in _TRUE_VALUES
    with app.app_context():
        summary = run(dry_run=dry_run, max_sends=_max_sends_from_env())
    print(json.dumps(summary, sort_keys=True, separators=(",", ":")), flush=True)
    return 1 if summary["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
