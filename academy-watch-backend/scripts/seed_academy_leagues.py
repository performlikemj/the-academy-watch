#!/usr/bin/env python3
"""Seed script for academy/youth leagues.

Seeds the AcademyLeague table with relevant youth leagues for tracking.

API-Football Youth League IDs (England):
- 703: U18 Premier League (North & South combined)
- 706: Premier League 2 Division One
- 707: Premier League 2 Division Two
- 708: U21 Professional Development League
- 775: UEFA Youth League
- 46: EFL Trophy (includes U21 teams)
- 718: FA Youth Cup

Usage:
    cd loan-army-backend
    python scripts/seed_academy_leagues.py
"""

import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

# Import the Flask app instance
from src.main import app
from src.models.league import db, AcademyLeague, Team
from datetime import datetime, timezone


# Youth leagues to seed
YOUTH_LEAGUES = [
    {
        'api_league_id': 706,
        'name': 'Premier League 2 - Division One',
        'country': 'England',
        'level': 'U23',
        'season': 2024,
    },
    {
        'api_league_id': 707,
        'name': 'Premier League 2 - Division Two',
        'country': 'England',
        'level': 'U23',
        'season': 2024,
    },
    {
        'api_league_id': 703,
        'name': 'U18 Premier League',
        'country': 'England',
        'level': 'U18',
        'season': 2024,
    },
    {
        'api_league_id': 708,
        'name': 'Professional Development League',
        'country': 'England',
        'level': 'U21',
        'season': 2024,
    },
    {
        'api_league_id': 775,
        'name': 'UEFA Youth League',
        'country': 'Europe',
        'level': 'U21',
        'season': 2024,
    },
    {
        'api_league_id': 718,
        'name': 'FA Youth Cup',
        'country': 'England',
        'level': 'U18',
        'season': 2024,
    },
]


def seed_leagues(dry_run: bool = False):
    """Seed youth leagues into the database.

    Args:
        dry_run: If True, print what would be done without making changes
    """
    with app.app_context():
        created = []
        skipped = []

        for league_data in YOUTH_LEAGUES:
            # Check if already exists
            existing = AcademyLeague.query.filter_by(
                api_league_id=league_data['api_league_id']
            ).first()

            if existing:
                skipped.append(f"{league_data['name']} (ID: {league_data['api_league_id']}) - already exists")
                continue

            if dry_run:
                created.append(f"{league_data['name']} (ID: {league_data['api_league_id']}) - would create")
                continue

            # Create new league
            league = AcademyLeague(
                api_league_id=league_data['api_league_id'],
                name=league_data['name'],
                country=league_data['country'],
                level=league_data['level'],
                season=league_data.get('season'),
                is_active=True,
                sync_enabled=True,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )

            db.session.add(league)
            created.append(f"{league_data['name']} (ID: {league_data['api_league_id']})")

        if not dry_run and created:
            db.session.commit()

        # Print results
        print("\n=== Academy League Seeding ===\n")

        if dry_run:
            print("DRY RUN - No changes made\n")

        if created:
            print(f"Created {len(created)} league(s):")
            for item in created:
                print(f"  + {item}")

        if skipped:
            print(f"\nSkipped {len(skipped)} league(s):")
            for item in skipped:
                print(f"  - {item}")

        # Show summary
        total = AcademyLeague.query.count()
        active = AcademyLeague.query.filter_by(is_active=True).count()
        print(f"\nTotal leagues in database: {total} ({active} active)")

        # List all leagues
        print("\nAll configured leagues:")
        for league in AcademyLeague.query.order_by(AcademyLeague.level, AcademyLeague.name).all():
            sync_status = "sync on" if league.sync_enabled else "sync off"
            active_status = "active" if league.is_active else "inactive"
            print(f"  [{league.level}] {league.name} (ID: {league.api_league_id}) - {active_status}, {sync_status}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Seed academy/youth leagues')
    parser.add_argument('--dry-run', action='store_true',
                        help='Print what would be done without making changes')

    args = parser.parse_args()
    seed_leagues(dry_run=args.dry_run)


if __name__ == '__main__':
    main()
