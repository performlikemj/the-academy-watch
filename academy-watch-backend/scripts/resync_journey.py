#!/usr/bin/env python3
"""
Re-sync player journey data from API-Football.

Usage:
    # Sync a single player (force full re-sync)
    python scripts/resync_journey.py 403064

    # Sync multiple players
    python scripts/resync_journey.py 403064 284324 389456

    # Incremental sync (only new/current seasons)
    python scripts/resync_journey.py --incremental 403064

    # Sync all existing journeys (force full)
    python scripts/resync_journey.py --all

Environment:
    Requires DB_* variables for database and API_FOOTBALL_KEY for API access.
"""

import os
import sys
import argparse

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def main():
    parser = argparse.ArgumentParser(description='Re-sync player journey data')
    parser.add_argument('player_ids', nargs='*', type=int, help='API-Football player IDs to sync')
    parser.add_argument('--all', action='store_true', help='Re-sync all existing journeys')
    parser.add_argument('--incremental', action='store_true', help='Only sync new/current seasons (skip force_full)')
    args = parser.parse_args()

    if not args.player_ids and not args.all:
        parser.error('Provide player IDs or use --all')

    from src.main import app, db
    from src.models.journey import PlayerJourney
    from src.services.journey_sync import JourneySyncService

    force_full = not args.incremental

    with app.app_context():
        service = JourneySyncService()

        if args.all:
            journeys = PlayerJourney.query.all()
            player_ids = [j.player_api_id for j in journeys]
            print(f"Found {len(player_ids)} existing journeys to re-sync")
        else:
            player_ids = args.player_ids

        success = 0
        failed = 0

        for pid in player_ids:
            print(f"\nSyncing player {pid} (force_full={force_full})...")
            journey = service.sync_player(pid, force_full=force_full)

            if journey and not journey.sync_error:
                print(f"  OK: {journey.player_name}")
                print(f"  Current club: {journey.current_club_name} ({journey.current_level})")
                print(f"  Entries: {journey.entries.count()}")
                print(f"  First team apps: {journey.total_first_team_apps}, Loan apps: {journey.total_loan_apps}")
                success += 1
            else:
                error = journey.sync_error if journey else 'sync returned None'
                print(f"  FAILED: {error}")
                failed += 1

        print(f"\nDone: {success} synced, {failed} failed")


if __name__ == '__main__':
    main()
