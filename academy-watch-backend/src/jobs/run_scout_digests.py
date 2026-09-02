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
import os
from datetime import UTC, datetime, timedelta

from src.api_football_client import APICallBudget
from src.main import app
from src.routes.scout import _get_api_client
from src.services.scout_digest_service import MAX_DIGEST_USERS, send_scout_digests

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

DEFAULT_MIN_INTERVAL_HOURS = 144
DEFAULT_API_BUDGET = 200


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _api_budget_limit() -> int:
    raw = os.getenv("SCOUT_DIGEST_API_BUDGET", str(DEFAULT_API_BUDGET)).strip()
    try:
        value = int(raw)
    except (TypeError, ValueError):
        logger.warning(
            "Invalid SCOUT_DIGEST_API_BUDGET=%r; using %d",
            raw,
            DEFAULT_API_BUDGET,
        )
        return DEFAULT_API_BUDGET
    if value < 0:
        logger.warning("Negative SCOUT_DIGEST_API_BUDGET=%r; using 0", raw)
        return 0
    return value


def _attach_api_budget(api_client, budget: APICallBudget):
    """Resolve the route's lazy client and attach this run's hard call cap."""
    missing = object()
    resolve = getattr(api_client, "_resolve", None)
    factory = getattr(api_client, "_factory", None)
    instance = getattr(api_client, "_instance", missing)
    if instance is None and callable(factory) and callable(resolve):

        def budgeted_factory():
            return factory(call_budget=budget)

        api_client._factory = budgeted_factory
        try:
            client = resolve()
        finally:
            api_client._factory = factory
    else:
        client = resolve() if callable(resolve) else api_client
    try:
        client.call_budget = budget
    except (AttributeError, TypeError) as exc:
        raise TypeError("api_client must allow the scout digest call budget to be attached") from exc
    if callable(resolve) and getattr(resolve(), "call_budget", None) is not budget:
        raise TypeError("resolved api_client did not retain the scout digest call budget")
    return client


def run(dry_run: bool = False, min_interval_hours: int = DEFAULT_MIN_INTERVAL_HOURS) -> dict:
    """Send all due digest pages and return operator-facing totals."""
    if min_interval_hours < 0:
        raise ValueError("min_interval_hours must be non-negative")

    api_budget = APICallBudget(_api_budget_limit())
    summary = {
        "users_considered": 0,
        "sent": 0,
        "skipped": 0,
        "errors": 0,
        "dry_run": dry_run,
        "would_send": 0,
        "api_calls_used": 0,
        "api_budget_exhausted": False,
    }
    cursor = 0
    skip_sent_since = _utcnow() - timedelta(hours=min_interval_hours) if min_interval_hours else None
    enrichment_cache: dict = {}

    try:
        api_client = _attach_api_budget(_get_api_client(), api_budget)
        while True:
            page = send_scout_digests(
                dry_run=dry_run,
                limit=MAX_DIGEST_USERS,
                api_client=api_client,
                cursor=cursor,
                skip_sent_since=skip_sent_since,
                report_job_metrics=True,
                enrichment_cache=enrichment_cache,
            )
            summary["users_considered"] += int(page["users_processed"])
            for key in ("sent", "skipped", "errors"):
                summary[key] += int(page.get(key, 0))

            next_cursor = page.get("next_cursor")
            if next_cursor is None:
                break
            if isinstance(next_cursor, bool) or not isinstance(next_cursor, int) or next_cursor <= cursor:
                logger.error(
                    "Scout digest paging returned a non-advancing cursor: cursor=%r next_cursor=%r users_considered=%r",
                    cursor,
                    next_cursor,
                    page.get("users_considered"),
                )
                summary["errors"] += 1
                break
            cursor = next_cursor
    except Exception:
        logger.exception("Scout digest job failed at cursor=%r", cursor)
        summary["errors"] += 1

    summary["would_send"] = summary["users_considered"] - summary["skipped"]
    summary["api_calls_used"] = api_budget.spent
    summary["api_budget_exhausted"] = api_budget.exhausted
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
    dry_run = args.dry_run or os.getenv("SCOUT_DIGEST_DRY_RUN", "").strip().lower() in ("1", "true", "yes", "on")
    with app.app_context():
        summary = run(dry_run=dry_run, min_interval_hours=args.min_interval_hours)
    print(json.dumps(summary, sort_keys=True, separators=(",", ":")), flush=True)
    return 1 if summary["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
