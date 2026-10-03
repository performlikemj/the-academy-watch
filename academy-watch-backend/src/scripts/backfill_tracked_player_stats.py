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
from src.utils.log_privacy import log_metadata

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

    log.info("[club_db_id] Found %s TrackedPlayer rows to backfill", len(players))
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
            "[club_db_id] %s team API IDs not found in DB: %s%s",
            len(missing_teams),
            log_metadata(sorted(missing_teams)[:20]),
            log_metadata("..." if len(missing_teams) > 20 else ""),
        )

    if not dry_run:
        db.session.commit()
        log.info("[club_db_id] Updated %s rows", log_metadata(updated))
    else:
        db.session.rollback()
        log.info("[club_db_id] DRY RUN — would update %s rows", log_metadata(updated))


def backfill_player_stats_cache(dry_run=False):
    """Copy limited-coverage stats into PlayerStatsCache. (AcademyPlayer table dropped)"""
    log.info("[stats_cache] AcademyPlayer table dropped — skipping backfill")
    return


def check_coverage(dry_run=False):
    """Report TrackedPlayer coverage."""
    from src.models.tracked_player import TrackedPlayer

    log.info("[coverage] AcademyPlayer table dropped — checking TrackedPlayer only")
    active_aps = []  # No more AcademyPlayer rows
    log.info("[coverage] Checking %s active AcademyPlayer rows", len(active_aps))

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
        log.warning("[coverage] %s active AcademyPlayer rows have NO matching TrackedPlayer:", len(gaps))
        for g in gaps[:30]:
            log.warning(
                "  AP#%s %s (%s → %s)",
                log_metadata(g["ap_id"]),
                log_metadata(g["player_name"]),
                log_metadata(g["primary_team"]),
                log_metadata(g["loan_team"]),
            )
        if len(gaps) > 30:
            log.warning("  ... and %s more", log_metadata(len(gaps) - 30))
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
