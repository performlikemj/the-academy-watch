#!/usr/bin/env python3
"""
Re-sync goalkeeper saves data from API-Football.

This script finds all goalkeeper fixture stats that are missing saves data
and re-fetches the data from API-Football to populate the saves field.

Usage:
    # Dry run (shows what would be updated)
    python scripts/resync_goalkeeper_saves.py --dry-run

    # Actually update the data
    python scripts/resync_goalkeeper_saves.py

    # Limit to specific player
    python scripts/resync_goalkeeper_saves.py --player-id 284361

Environment:
    Requires the following environment variables:
    - DATABASE_URL or DB_* variables for database connection
    - API_FOOTBALL_KEY for API-Football access
"""

import os
import sys
import argparse
import time
from datetime import datetime

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

def main():
    parser = argparse.ArgumentParser(description='Re-sync goalkeeper saves data from API-Football')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be updated without making changes')
    parser.add_argument('--player-id', type=int, help='Only process a specific player')
    parser.add_argument('--limit', type=int, default=100, help='Maximum number of fixtures to process (default: 100)')
    parser.add_argument('--delay', type=float, default=0.3, help='Delay between API calls in seconds (default: 0.3)')
    args = parser.parse_args()

    # Initialize Flask app context
    from src.main import app, db
    from src.models.weekly import FixturePlayerStats, Fixture
    from src.api_football_client import APIFootballClient

    with app.app_context():
        print("=" * 60)
        print("Goalkeeper Saves Re-sync Script")
        print("=" * 60)
        print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE UPDATE'}")
        print(f"Limit: {args.limit} fixtures")
        if args.player_id:
            print(f"Player filter: {args.player_id}")
        print()

        # Find goalkeeper stats with missing saves data
        query = db.session.query(
            FixturePlayerStats, Fixture
        ).join(
            Fixture, FixturePlayerStats.fixture_id == Fixture.id
        ).filter(
            FixturePlayerStats.position == 'G',
            FixturePlayerStats.saves.is_(None),
            FixturePlayerStats.minutes > 0  # Only players who actually played
        )

        if args.player_id:
            query = query.filter(FixturePlayerStats.player_api_id == args.player_id)

        query = query.order_by(Fixture.date_utc.desc()).limit(args.limit)
        
        results = query.all()
        
        print(f"Found {len(results)} goalkeeper fixtures with missing saves data")
        print()

        if not results:
            print("Nothing to update!")
            return

        # Initialize API client
        api_client = APIFootballClient()
        
        updated = 0
        skipped = 0
        errors = 0

        for stats, fixture in results:
            fixture_id_api = fixture.fixture_id_api
            player_id = stats.player_api_id
            season = fixture.season or datetime.now().year

            print(f"Processing: Player {player_id}, Fixture {fixture_id_api} ({fixture.date_utc.date() if fixture.date_utc else 'N/A'})")

            try:
                # Fetch player stats from API-Football
                player_stats = api_client.get_player_stats_for_fixture(player_id, season, fixture_id_api)
                
                if player_stats and player_stats.get('statistics'):
                    stat_list = player_stats['statistics']
                    if stat_list:
                        st = stat_list[0] if isinstance(stat_list, list) else stat_list
                        # Goalkeeper saves are in the 'goals' block in API-Football response
                        goals_block = st.get('goals', {}) or {}
                        saves = goals_block.get('saves')
                        goals_conceded = goals_block.get('conceded')
                        
                        if saves is not None:
                            print(f"  -> Found saves: {saves}, conceded: {goals_conceded}")
                            
                            if not args.dry_run:
                                stats.saves = saves
                                if goals_conceded is not None and stats.goals_conceded is None:
                                    stats.goals_conceded = goals_conceded
                                db.session.commit()
                            
                            updated += 1
                        else:
                            print(f"  -> No saves data in API response (goals block: {goals_block})")
                            skipped += 1
                    else:
                        print(f"  -> Empty statistics in response")
                        skipped += 1
                else:
                    print(f"  -> No player stats found in API response")
                    skipped += 1

                # Rate limiting
                time.sleep(args.delay)

            except Exception as e:
                print(f"  -> ERROR: {e}")
                errors += 1

        print()
        print("=" * 60)
        print("Summary")
        print("=" * 60)
        print(f"Updated: {updated}")
        print(f"Skipped: {skipped}")
        print(f"Errors: {errors}")
        
        if args.dry_run:
            print()
            print("This was a DRY RUN. No changes were made.")
            print("Run without --dry-run to apply changes.")


if __name__ == '__main__':
    main()

