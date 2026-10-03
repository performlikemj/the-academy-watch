#!/usr/bin/env python3
"""One-time repair: decode HTML entities in stored player names.

API-Football occasionally returns names with HTML entities (e.g.
``N. O&apos;Reilly``). Those were stored verbatim and then rendered literally
by the React frontend (which escapes, never decodes), leaking the raw entity
into the UI — visible on the Scout Desk leaderboards.

The ingestion paths now run names through ``clean_name`` (see
``src.utils.player_names``), so this script only repairs rows written before
that fix. It is idempotent — a clean name decodes to itself — and safe to
re-run.

Usage:
    cd academy-watch-backend
    python -m src.scripts.decode_name_entities            # dry-run (default)
    python -m src.scripts.decode_name_entities --apply    # commit changes

Postgres-only (uses the ``~`` regex operator). Safe to run against production.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

# (table, column) pairs holding feed-sourced player names.
NAME_COLUMNS = [
    ("tracked_players", "player_name"),
    ("player_journeys", "player_name"),
    ("academy_player_season_stats", "player_name"),
    ("cohort_members", "player_name"),
    ("academy_appearances", "player_name"),
    ("players", "name"),
]

# Matches named (&apos;), decimal (&#39;) and hex (&#x27;) HTML entities.
ENTITY_REGEX = r"&[a-zA-Z][a-zA-Z0-9]*;|&#[0-9]+;|&#x[0-9a-fA-F]+;"


def get_app():
    from src.main import app

    return app


def repair(apply: bool) -> int:
    """Decode entity-bearing names in place. Returns total rows updated."""
    import html

    from sqlalchemy import text
    from src.models.league import db

    total_rows = 0
    for table, column in NAME_COLUMNS:
        # Distinct encoded values → one UPDATE per value (no PK needed, and
        # the same encoded string always decodes to the same clean name).
        rows = db.session.execute(
            text(f"SELECT DISTINCT {column} AS val FROM {table} WHERE {column} ~ :rx"),  # noqa: S608
            {"rx": ENTITY_REGEX},
        ).all()

        table_rows = 0
        for (encoded,) in rows:
            decoded = html.unescape(encoded).strip()
            if decoded == encoded:
                continue  # entity-looking substring that is already correct
            log.info("  %s.%s: %r -> %r", table, column, encoded, decoded)
            if apply:
                result = db.session.execute(
                    text(f"UPDATE {table} SET {column} = :new WHERE {column} = :old"),  # noqa: S608
                    {"new": decoded, "old": encoded},
                )
                table_rows += result.rowcount or 0
            else:
                table_rows += 1

        if table_rows:
            log.info("[%s] %s rows %s", table, table_rows, "updated" if apply else "would update")
        total_rows += table_rows

    if apply:
        db.session.commit()
    return total_rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Decode HTML entities in stored player names")
    parser.add_argument("--apply", action="store_true", help="Commit changes (default: dry-run)")
    args = parser.parse_args()

    with get_app().app_context():
        mode = "APPLY" if args.apply else "DRY-RUN"
        log.info("Decoding HTML entities in player names (%s)", mode)
        total = repair(apply=args.apply)
        log.info("Done. %s rows %s.", total, "updated" if args.apply else "would be updated")
        if not args.apply and total:
            log.info("Re-run with --apply to commit.")


if __name__ == "__main__":
    main()
