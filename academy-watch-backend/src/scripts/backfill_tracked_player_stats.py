#!/usr/bin/env python3
"""Backfill script for Phase 0 of AcademyPlayer → TrackedPlayer migration.

Three tasks:
  1. Populate current_club_db_id on TrackedPlayer rows
  2. Copy limited-coverage stats from AcademyPlayer into PlayerStatsCache
  3. Report any active AcademyPlayer rows missing a corresponding TrackedPlayer

Usage:
    cd academy-watch-backend
    python src/scripts/backfill_tracked_player_stats.py
    python src/scripts/backfill_tracked_player_stats.py --dry-run
"""

import argparse
import logging
import os
import sys

# Add project root to path (two levels up from src/scripts/)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)


def get_app():
    from src.main import app

    return app


def backfill_current_club_db_id(dry_run=False):
    """For each TrackedPlayer with current_club_api_id, resolve the Team DB id."""
    from src.models.league import Team, db
    from src.models.tracked_player import TrackedPlayer

    players = TrackedPlayer.query.filter(
        TrackedPlayer.current_club_api_id.isnot(None),
        TrackedPlayer.current_club_db_id.is_(None),
    ).all()

    log.info(f"[club_db_id] Found {len(players)} TrackedPlayer rows to backfill")
    updated = 0
    missing_teams = set()

    for tp in players:
        team = Team.query.filter_by(team_id=tp.current_club_api_id).first()
        if team:
            tp.current_club_db_id = team.id
            updated += 1
        else:
            missing_teams.add(tp.current_club_api_id)

    if missing_teams:
        log.warning(
            f"[club_db_id] {len(missing_teams)} team API IDs not found in DB: "
            f"{sorted(missing_teams)[:20]}{'...' if len(missing_teams) > 20 else ''}"
        )

    if not dry_run:
        db.session.commit()
        log.info(f"[club_db_id] Updated {updated} rows")
    else:
        db.session.rollback()
        log.info(f"[club_db_id] DRY RUN — would update {updated} rows")


def backfill_player_stats_cache(dry_run=False):
    """Copy limited-coverage stats into PlayerStatsCache. (AcademyPlayer table dropped)"""
    log.info("[stats_cache] AcademyPlayer table dropped — skipping backfill")
    return


def check_coverage(dry_run=False):
    """Report TrackedPlayer coverage."""
    from src.models.tracked_player import TrackedPlayer

    log.info("[coverage] AcademyPlayer table dropped — checking TrackedPlayer only")
    active_aps = []  # No more AcademyPlayer rows
    log.info(f"[coverage] Checking {len(active_aps)} active AcademyPlayer rows")

    gaps = []
    for ap in active_aps:
        tp = TrackedPlayer.query.filter_by(
            player_api_id=ap.player_id,
            is_active=True,
        ).first()
        if not tp:
            gaps.append(
                {
                    "ap_id": ap.id,
                    "player_id": ap.player_id,
                    "player_name": ap.player_name,
                    "primary_team": ap.primary_team_name,
                    "loan_team": ap.loan_team_name,
                }
            )

    if gaps:
        log.warning(f"[coverage] {len(gaps)} active AcademyPlayer rows have NO matching TrackedPlayer:")
        for g in gaps[:30]:
            log.warning(f"  AP#{g['ap_id']} {g['player_name']} ({g['primary_team']} → {g['loan_team']})")
        if len(gaps) > 30:
            log.warning(f"  ... and {len(gaps) - 30} more")
    else:
        log.info("[coverage] All active AcademyPlayer rows have a matching TrackedPlayer")


def _season_from_window_key(window_key):
    """Extract season start year from window_key like '2024-25::SUMMER' → 2024."""
    if not window_key:
        return 2025  # default to current
    try:
        return int(window_key.split("-")[0])
    except (ValueError, IndexError):
        return 2025


def main():
    parser = argparse.ArgumentParser(description="Backfill TrackedPlayer stats foundation")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without committing")
    args = parser.parse_args()

    app = get_app()
    with app.app_context():
        log.info("=== Phase 0 Backfill: TrackedPlayer Stats Foundation ===")
        log.info("")

        log.info("--- Task 1: Backfill current_club_db_id ---")
        backfill_current_club_db_id(dry_run=args.dry_run)
        log.info("")

        log.info("--- Task 2: Backfill PlayerStatsCache ---")
        backfill_player_stats_cache(dry_run=args.dry_run)
        log.info("")

        log.info("--- Task 3: Coverage check ---")
        check_coverage(dry_run=args.dry_run)
        log.info("")

        log.info("=== Done ===")


if __name__ == "__main__":
    main()
