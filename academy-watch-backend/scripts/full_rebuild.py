#!/usr/bin/env python3
"""Full Academy Rebuild Script

Nukes academy-related data and rebuilds from scratch:
  Stage 0: Pre-flight checks (DB, API quota)
  Stage 1: Clean slate (delete TrackedPlayer, journey, cohort, loan data)
  Stage 2: Seed academy leagues (if missing)
  Stage 3: Cohort discovery + journey sync via Big6SeedingService
  Stage 4: Create TrackedPlayer records for each Big 6 team
  Stage 5: Link orphaned journeys
  Stage 6: Refresh statuses
  Stage 7: Seed club locations
  Stage 8: Summary

Usage:
    cd loan-army-backend
    ../.loan/bin/python scripts/full_rebuild.py
    ../.loan/bin/python scripts/full_rebuild.py --dry-run
    ../.loan/bin/python scripts/full_rebuild.py --yes --teams 33,42
    ../.loan/bin/python scripts/full_rebuild.py --skip-clean --skip-cohorts
"""

import argparse
import logging
import os
import sys
import time
from datetime import datetime, timezone

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from src.main import app
from src.models.league import db, Team, LoanedPlayer, AcademyLeague

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('full_rebuild')

# ── Constants ──────────────────────────────────────────────────────────

BIG_6 = {
    33: 'Manchester United',
    42: 'Arsenal',
    49: 'Chelsea',
    50: 'Manchester City',
    40: 'Liverpool',
    47: 'Tottenham',
}

DEFAULT_SEASONS = [2020, 2021, 2022, 2023, 2024]

YOUTH_LEAGUES_DATA = [
    {'api_league_id': 706, 'name': 'Premier League 2 - Division One', 'country': 'England', 'level': 'U23', 'season': 2024},
    {'api_league_id': 707, 'name': 'Premier League 2 - Division Two', 'country': 'England', 'level': 'U23', 'season': 2024},
    {'api_league_id': 703, 'name': 'U18 Premier League', 'country': 'England', 'level': 'U18', 'season': 2024},
    {'api_league_id': 708, 'name': 'Professional Development League', 'country': 'England', 'level': 'U21', 'season': 2024},
    {'api_league_id': 775, 'name': 'UEFA Youth League', 'country': 'Europe', 'level': 'U21', 'season': 2024},
    {'api_league_id': 718, 'name': 'FA Youth Cup', 'country': 'England', 'level': 'U18', 'season': 2024},
]


# ── Helpers ────────────────────────────────────────────────────────────

def banner(stage_num, title):
    print(f"\n{'='*60}")
    print(f"  Stage {stage_num}: {title}")
    print(f"{'='*60}\n")


def confirm(message, auto_yes=False):
    if auto_yes:
        return True
    response = input(f"{message} [y/N] ").strip().lower()
    return response in ('y', 'yes')


# ── Stage 0: Pre-flight ───────────────────────────────────────────────

def stage_0_preflight(team_ids, seasons, dry_run):
    banner(0, 'Pre-flight checks')

    # Check DB connection
    try:
        db.session.execute(db.text('SELECT 1'))
        print('  [OK] Database connection')
    except Exception as e:
        print(f'  [FAIL] Database connection: {e}')
        return False

    # Check API quota
    try:
        from src.models.api_cache import APIUsageDaily
        today_total = APIUsageDaily.today_total()
        pct = (today_total / 7000) * 100
        status = 'WARN' if pct > 50 else 'OK'
        print(f'  [{status}] API calls today: {today_total}/7000 ({pct:.0f}%)')
        if pct > 80:
            print('  WARNING: API quota is >80% used. Consider running tomorrow.')
    except Exception:
        print('  [SKIP] Could not check API usage (table may not exist)')

    # Print plan
    team_names = []
    for t in team_ids:
        name = BIG_6.get(t)
        if not name:
            team_row = Team.query.filter_by(team_id=t).order_by(Team.season.desc()).first()
            name = team_row.name if team_row else str(t)
        team_names.append(name)
    combos = len(team_ids) * 6 * len(seasons)  # 6 youth leagues
    print(f'\n  Teams: {", ".join(team_names)}')
    print(f'  Seasons: {seasons}')
    print(f'  Cohort combos: {combos}')
    print(f'  Mode: {"DRY RUN" if dry_run else "LIVE"}')

    return True


# ── Stage 1: Clean slate ──────────────────────────────────────────────

def stage_1_clean(dry_run):
    banner(1, 'Clean slate')

    from src.models.tracked_player import TrackedPlayer
    from src.models.journey import PlayerJourneyEntry, PlayerJourney, ClubLocation
    from src.models.cohort import CohortMember, AcademyCohort

    tables = [
        ('TrackedPlayer', TrackedPlayer),
        ('PlayerJourneyEntry', PlayerJourneyEntry),
        ('PlayerJourney', PlayerJourney),
        ('CohortMember', CohortMember),
        ('AcademyCohort', AcademyCohort),
        ('LoanedPlayer', LoanedPlayer),
        ('ClubLocation', ClubLocation),
    ]

    for name, model in tables:
        count = model.query.count()
        if dry_run:
            print(f'  [DRY] Would delete {count} {name} records')
        else:
            if count > 0:
                model.query.delete()
                db.session.commit()
            print(f'  Deleted {count} {name} records')

    if not dry_run:
        print('\n  Clean slate complete.')


# ── Stage 2: Seed academy leagues ─────────────────────────────────────

def stage_2_seed_leagues(dry_run):
    banner(2, 'Seed academy leagues')

    created = 0
    skipped = 0

    for league_data in YOUTH_LEAGUES_DATA:
        existing = AcademyLeague.query.filter_by(
            api_league_id=league_data['api_league_id']
        ).first()

        if existing:
            skipped += 1
            print(f'  [SKIP] {league_data["name"]} (already exists)')
            continue

        if dry_run:
            print(f'  [DRY] Would create {league_data["name"]}')
            created += 1
            continue

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
        created += 1

    if not dry_run and created:
        db.session.commit()

    print(f'\n  Created: {created}, Skipped: {skipped}')


# ── Stage 3: Cohort discovery + journey sync ──────────────────────────

def stage_3_cohorts(team_ids, seasons, dry_run):
    banner(3, 'Cohort discovery + journey sync (Big 6 seeding)')

    if dry_run:
        combos = len(team_ids) * 6 * len(seasons)
        print(f'  [DRY] Would discover {combos} cohort combos')
        print(f'  [DRY] Would sync journeys for all unique players found')
        return {'cohorts_created': 0, 'players_synced': 0}

    from src.services.big6_seeding_service import run_big6_seed

    # Create a dummy job_id for progress tracking
    try:
        from src.utils.background_jobs import create_job
        job_id = create_job('full_rebuild', 'Full academy rebuild - cohort discovery')
    except Exception:
        job_id = 'full-rebuild-cli'

    start = time.time()
    result = run_big6_seed(
        job_id=job_id,
        seasons=seasons,
        team_ids=team_ids,
    )
    elapsed = time.time() - start

    print(f'\n  Cohorts created: {result.get("cohorts_created", 0)}')
    print(f'  Players synced: {result.get("players_synced", 0)}')
    print(f'  Elapsed: {elapsed/60:.1f} minutes')

    return result


# ── Stage 4: Create TrackedPlayers ────────────────────────────────────

def stage_4_tracked_players(team_ids, seasons, dry_run):
    banner(4, 'Create TrackedPlayer records')

    from src.models.tracked_player import TrackedPlayer
    from src.models.journey import PlayerJourney
    from src.models.cohort import AcademyCohort, CohortMember
    from src.utils.academy_classifier import derive_player_status
    from src.api_football_client import APIFootballClient
    from src.services.journey_sync import JourneySyncService
    from sqlalchemy import cast
    from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB

    total_created = 0
    total_skipped = 0
    total_errors = []

    api_client = APIFootballClient()
    journey_svc = JourneySyncService(api_client)
    current_season = max(seasons)

    for api_team_id in team_ids:
        team_name = BIG_6.get(api_team_id)
        if not team_name:
            _team_row = Team.query.filter_by(team_id=api_team_id).order_by(Team.season.desc()).first()
            team_name = _team_row.name if _team_row else str(api_team_id)
        print(f'\n  Processing {team_name} (api_id={api_team_id})...')

        # Find the Team row (most recent season)
        team = Team.query.filter_by(team_id=api_team_id).order_by(Team.season.desc()).first()
        if not team:
            print(f'    [WARN] No Team row found for api_id={api_team_id}, skipping')
            total_errors.append(f'{team_name}: no Team row')
            continue

        parent_api_id = team.team_id

        # ── Source 1: Players already identified as academy products ──
        known_journeys = PlayerJourney.query.filter(
            PlayerJourney.academy_club_ids.contains(cast([parent_api_id], PG_JSONB))
        ).all()
        candidate_ids = {j.player_api_id: j for j in known_journeys}
        print(f'    Source 1 (academy_club_ids): {len(candidate_ids)} players')

        # ── Source 2: API squad (multiple seasons) ──
        squad_data = []
        all_squad_player_ids = set()
        seasons_to_fetch = range(current_season - 3, current_season + 1)

        if not dry_run:
            for fetch_season in seasons_to_fetch:
                try:
                    season_squad = api_client.get_team_players(parent_api_id, season=fetch_season)
                    for entry in season_squad:
                        player_info = (entry or {}).get('player') or {}
                        pid = player_info.get('id')
                        if pid:
                            all_squad_player_ids.add(int(pid))
                    squad_data.extend(season_squad)
                except Exception as e:
                    logger.warning('Squad fetch failed for %s season %d: %s', team_name, fetch_season, e)

            print(f'    Source 2 (squad): {len(all_squad_player_ids)} unique across {len(list(seasons_to_fetch))} seasons')

            # Sync journeys for squad players not yet known
            synced = 0
            for entry in squad_data:
                player_info = (entry or {}).get('player') or {}
                pid = player_info.get('id')
                if not pid:
                    continue
                pid = int(pid)
                if pid in candidate_ids:
                    continue
                age = player_info.get('age')
                if age and int(age) > 23:
                    continue

                existing_journey = PlayerJourney.query.filter_by(player_api_id=pid).first()
                if existing_journey:
                    if parent_api_id in (existing_journey.academy_club_ids or []):
                        candidate_ids[pid] = existing_journey
                    continue

                try:
                    journey = journey_svc.sync_player(pid)
                    synced += 1
                    if journey and parent_api_id in (journey.academy_club_ids or []):
                        candidate_ids[pid] = journey
                except Exception as sync_err:
                    logger.warning('Journey sync failed for %d: %s', pid, sync_err)

            print(f'    Squad journey syncs: {synced}')
        else:
            print(f'    [DRY] Would fetch squads for seasons {list(seasons_to_fetch)}')

        # ── Source 3: CohortMember records ──
        cohort_ids = [c.id for c in AcademyCohort.query.filter_by(team_api_id=parent_api_id).all()]
        if cohort_ids:
            cohort_members = CohortMember.query.filter(
                CohortMember.cohort_id.in_(cohort_ids)
            ).all()
            for cm in cohort_members:
                if cm.player_api_id and cm.player_api_id not in candidate_ids:
                    journey = PlayerJourney.query.filter_by(
                        player_api_id=cm.player_api_id
                    ).first()
                    candidate_ids[cm.player_api_id] = journey  # may be None
            print(f'    Source 3 (cohorts): {len(cohort_members)} members across {len(cohort_ids)} cohorts')
        else:
            print(f'    Source 3 (cohorts): no cohorts found')

        print(f'    Total candidates: {len(candidate_ids)}')

        if dry_run:
            print(f'    [DRY] Would create up to {len(candidate_ids)} TrackedPlayer records')
            continue

        # Build squad lookup for enrichment
        squad_by_id = {}
        for entry in squad_data:
            pi = (entry or {}).get('player') or {}
            if pi.get('id'):
                squad_by_id[int(pi['id'])] = entry

        # Create TrackedPlayer rows
        created = 0
        skipped = 0
        errors = []

        for pid, journey in candidate_ids.items():
            try:
                existing = TrackedPlayer.query.filter_by(
                    player_api_id=pid, team_id=team.id,
                ).first()
                if existing:
                    skipped += 1
                    continue

                squad_entry = squad_by_id.get(pid) or {}
                pi = squad_entry.get('player') or {}

                player_name = (
                    (journey.player_name if journey else None)
                    or pi.get('name')
                    or f'Player {pid}'
                )
                photo_url = (journey.player_photo if journey else None) or pi.get('photo')
                nationality = (journey.nationality if journey else None) or pi.get('nationality')
                birth_date = (journey.birth_date if journey else None) or (pi.get('birth') or {}).get('date')
                position = pi.get('position') or ''
                age = pi.get('age')

                status, current_club_api_id, current_club_name = derive_player_status(
                    current_club_api_id=journey.current_club_api_id if journey else None,
                    current_club_name=journey.current_club_name if journey else None,
                    current_level=journey.current_level if journey else None,
                    parent_api_id=parent_api_id,
                    parent_club_name=team.name,
                )

                current_level = None
                if journey and journey.current_level:
                    current_level = journey.current_level

                tp = TrackedPlayer(
                    player_api_id=pid,
                    player_name=player_name,
                    photo_url=photo_url,
                    position=position,
                    nationality=nationality,
                    birth_date=birth_date,
                    age=int(age) if age else None,
                    team_id=team.id,
                    status=status,
                    current_level=current_level,
                    current_club_api_id=current_club_api_id,
                    current_club_name=current_club_name,
                    data_source='api-football',
                    data_depth='full_stats',
                    journey_id=journey.id if journey else None,
                )
                db.session.add(tp)
                created += 1
            except Exception as entry_err:
                errors.append(f'Player {pid}: {entry_err}')
                logger.warning('TrackedPlayer error for %d: %s', pid, entry_err)

        db.session.commit()
        print(f'    Created: {created}, Skipped: {skipped}, Errors: {len(errors)}')
        total_created += created
        total_skipped += skipped
        total_errors.extend(errors)

    print(f'\n  Total TrackedPlayers created: {total_created}')
    print(f'  Total skipped: {total_skipped}')
    if total_errors:
        print(f'  Errors: {len(total_errors)}')
        for err in total_errors[:10]:
            print(f'    - {err}')

    return {'created': total_created, 'skipped': total_skipped, 'errors': len(total_errors)}


# ── Stage 5: Link orphaned journeys ───────────────────────────────────

def stage_5_link_journeys(dry_run):
    banner(5, 'Link orphaned journeys')

    from src.models.tracked_player import TrackedPlayer
    from src.models.journey import PlayerJourney

    unlinked = TrackedPlayer.query.filter(
        TrackedPlayer.is_active == True,
        TrackedPlayer.journey_id.is_(None),
    ).all()

    print(f'  Found {len(unlinked)} TrackedPlayers with no journey_id')

    linked = 0
    for tp in unlinked:
        journey = PlayerJourney.query.filter_by(player_api_id=tp.player_api_id).first()
        if journey:
            if dry_run:
                linked += 1
            else:
                tp.journey_id = journey.id
                linked += 1

    if not dry_run and linked:
        db.session.commit()

    action = 'Would link' if dry_run else 'Linked'
    print(f'  {action} {linked} players to existing journeys')


# ── Stage 6: Refresh statuses ─────────────────────────────────────────

def stage_6_refresh_statuses(team_ids, dry_run):
    banner(6, 'Refresh statuses')

    from src.models.tracked_player import TrackedPlayer
    from src.utils.academy_classifier import derive_player_status

    tracked = TrackedPlayer.query.filter(
        TrackedPlayer.is_active == True,
    ).all()

    print(f'  Checking {len(tracked)} active TrackedPlayers...')

    updated = 0
    status_counts = {}

    for tp in tracked:
        if not tp.team:
            continue

        journey = tp.journey
        status, current_club_api_id, current_club_name = derive_player_status(
            current_club_api_id=journey.current_club_api_id if journey else None,
            current_club_name=journey.current_club_name if journey else None,
            current_level=journey.current_level if journey else None,
            parent_api_id=tp.team.team_id,
            parent_club_name=tp.team.name,
        )

        changed = (
            tp.status != status or
            tp.current_club_api_id != current_club_api_id or
            tp.current_club_name != current_club_name
        )

        if changed and not dry_run:
            tp.status = status
            tp.current_club_api_id = current_club_api_id
            tp.current_club_name = current_club_name
            updated += 1
        elif changed:
            updated += 1

        status_counts[status] = status_counts.get(status, 0) + 1

    if not dry_run and updated:
        db.session.commit()

    action = 'Would update' if dry_run else 'Updated'
    print(f'  {action} {updated} players')
    print(f'\n  Status breakdown:')
    for status, count in sorted(status_counts.items()):
        print(f'    {status}: {count}')


# ── Stage 7: Seed club locations ──────────────────────────────────────

def stage_7_locations(dry_run):
    banner(7, 'Seed club locations')

    from src.models.journey import ClubLocation

    existing = ClubLocation.query.count()
    print(f'  Existing locations: {existing}')

    if dry_run:
        print(f'  [DRY] Would seed club locations for major clubs')
        return

    from src.services.journey_sync import seed_club_locations
    added = seed_club_locations()
    print(f'  Added {added} new club locations')


# ── Stage 8: Summary ──────────────────────────────────────────────────

def stage_8_summary(team_ids):
    banner(8, 'Summary')

    from src.models.tracked_player import TrackedPlayer
    from src.models.journey import PlayerJourney, PlayerJourneyEntry, ClubLocation
    from src.models.cohort import AcademyCohort, CohortMember

    print(f'  {"Table":<25} {"Count":>8}')
    print(f'  {"-"*25} {"-"*8}')

    tables = [
        ('AcademyCohort', AcademyCohort),
        ('CohortMember', CohortMember),
        ('PlayerJourney', PlayerJourney),
        ('PlayerJourneyEntry', PlayerJourneyEntry),
        ('TrackedPlayer', TrackedPlayer),
        ('ClubLocation', ClubLocation),
    ]

    for name, model in tables:
        count = model.query.count()
        print(f'  {name:<25} {count:>8}')

    # Per-team breakdown
    print(f'\n  {"Team":<25} {"Tracked":>8} {"Academy":>8} {"On Loan":>8} {"1st Team":>8}')
    print(f'  {"-"*25} {"-"*8} {"-"*8} {"-"*8} {"-"*8}')

    for api_id in team_ids:
        team = Team.query.filter_by(team_id=api_id).order_by(Team.season.desc()).first()
        if not team:
            continue

        total = TrackedPlayer.query.filter_by(team_id=team.id, is_active=True).count()
        academy = TrackedPlayer.query.filter_by(team_id=team.id, is_active=True, status='academy').count()
        on_loan = TrackedPlayer.query.filter_by(team_id=team.id, is_active=True, status='on_loan').count()
        first_team = TrackedPlayer.query.filter_by(team_id=team.id, is_active=True, status='first_team').count()

        print(f'  {team.name:<25} {total:>8} {academy:>8} {on_loan:>8} {first_team:>8}')

    print()


# ── Main ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Full academy data rebuild')
    parser.add_argument('--teams', type=str, default=None,
                        help='Comma-separated API team IDs (default: all Big 6)')
    parser.add_argument('--seasons', type=str, default=None,
                        help='Comma-separated seasons (default: 2020,2021,2022,2023,2024)')
    parser.add_argument('--league', type=int, default=None,
                        help='API league ID to auto-discover teams (e.g. 39 for Premier League)')
    parser.add_argument('--exclude-teams', type=str, default=None,
                        help='Comma-separated API team IDs to exclude (use with --league)')
    parser.add_argument('--skip-clean', action='store_true',
                        help='Skip stage 1 (keep existing data)')
    parser.add_argument('--skip-cohorts', action='store_true',
                        help='Skip stage 3 (cohort discovery)')
    parser.add_argument('--yes', '-y', action='store_true',
                        help='Skip confirmation prompt')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would happen without making changes')

    args = parser.parse_args()

    # Parse seasons (needed before --league resolution)
    if args.seasons:
        seasons = [int(s.strip()) for s in args.seasons.split(',')]
    else:
        seasons = DEFAULT_SEASONS

    # Parse exclude set
    exclude_ids = set()
    if args.exclude_teams:
        exclude_ids = {int(t.strip()) for t in args.exclude_teams.split(',')}

    # Parse team IDs
    if args.teams:
        team_ids = [int(t.strip()) for t in args.teams.split(',')]
    else:
        team_ids = list(BIG_6.keys())

    with app.app_context():
        # --league: auto-discover teams from DB for the given league
        if args.league:
            from src.models.league import League
            season_for_lookup = max(seasons)
            league_row = League.query.filter_by(league_id=args.league).first()
            if not league_row:
                print(f'\n  [FAIL] League {args.league} not found in DB. Run sync-teams first.')
                sys.exit(1)
            league_teams = Team.query.filter_by(
                league_id=league_row.id, season=season_for_lookup
            ).all()
            if not league_teams:
                print(f'\n  [FAIL] No teams found for league {args.league} season {season_for_lookup}.')
                print(f'  Run: POST /api/sync-teams/{season_for_lookup}')
                sys.exit(1)
            team_ids = [t.team_id for t in league_teams if t.team_id not in exclude_ids]
            print(f'\n  Discovered {len(team_ids)} teams from league {league_row.name} '
                  f'(season {season_for_lookup}, excluded {len(exclude_ids)})')
        print('\n' + '='*60)
        print('  FULL ACADEMY REBUILD')
        print('='*60)

        start_time = time.time()

        # Stage 0
        if not stage_0_preflight(team_ids, seasons, args.dry_run):
            print('\nPre-flight checks failed. Aborting.')
            sys.exit(1)

        if not args.dry_run and not args.yes:
            print()
            if not confirm('Proceed with rebuild?'):
                print('Aborted.')
                sys.exit(0)

        # Stage 1
        if not args.skip_clean:
            stage_1_clean(args.dry_run)
        else:
            print('\n  [SKIP] Stage 1: Clean slate (--skip-clean)')

        # Stage 2
        stage_2_seed_leagues(args.dry_run)

        # Stage 3
        if not args.skip_cohorts:
            stage_3_cohorts(team_ids, seasons, args.dry_run)
        else:
            print('\n  [SKIP] Stage 3: Cohort discovery (--skip-cohorts)')

        # Stage 4
        stage_4_tracked_players(team_ids, seasons, args.dry_run)

        # Stage 5
        stage_5_link_journeys(args.dry_run)

        # Stage 6
        stage_6_refresh_statuses(team_ids, args.dry_run)

        # Stage 7
        stage_7_locations(args.dry_run)

        # Stage 8
        stage_8_summary(team_ids)

        elapsed = time.time() - start_time
        print(f'  Total time: {elapsed/60:.1f} minutes')
        print(f'  Done!\n')


if __name__ == '__main__':
    main()
