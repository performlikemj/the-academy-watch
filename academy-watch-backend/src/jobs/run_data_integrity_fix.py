"""Scheduled job: Comprehensive data integrity fix.

Runs 5 idempotent phases to fix stale/missing data accumulated from
architectural changes. Each phase skips already-fixed rows, so the job
can be safely re-run if it times out.

Phases:
  1. Backfill team_profiles for teams in fixture_player_stats (fixes "Team 419")
  2. Backfill players table for players in fixture_player_stats (fixes numeric IDs as names)
  3. Recompute academy_club_ids on PlayerJourney records (DB-only, no API)
  4. Refresh statuses via transfer_heal_service (fixes stale on_loan)
  5. Backfill formation data for fixture_player_stats gaps

Usage:
    python -m src.jobs.run_data_integrity_fix [--dry-run] [--phase N]
"""

import logging
import sys
import time
from datetime import UTC, datetime

from sqlalchemy import func, text
from src.main import app
from src.models.league import db
from src.utils.job_utils import is_job_paused

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

PAUSE_KEY = "data_integrity_fix_paused"


def _verify_count(label, sql):
    """Run a verification count query and log the result."""
    result = db.session.execute(text(sql)).scalar()
    logger.info(f"  [VERIFY] {label}: {result}")
    return result


def phase_1_backfill_team_profiles(dry_run=False):
    """Backfill TeamProfile for all teams in fixture_player_stats that are missing.

    Uses raw SQL INSERT ON CONFLICT to bypass ORM session issues.
    """
    from src.api_football_client import APIFootballClient
    from src.utils.slug import generate_unique_team_slug

    logger.info("=== Phase 1: Backfill team_profiles ===")

    missing = db.session.execute(
        text("""
        SELECT DISTINCT fs.team_api_id
        FROM fixture_player_stats fs
        LEFT JOIN team_profiles tp ON fs.team_api_id = tp.team_id
        WHERE tp.team_id IS NULL
    """)
    ).fetchall()
    missing_ids = [row[0] for row in missing]
    logger.info(f"Teams missing profiles: {len(missing_ids)}")

    if not missing_ids or dry_run:
        return len(missing_ids)

    api_client = APIFootballClient()

    existing_slugs = set(
        row[0] for row in db.session.execute(text("SELECT slug FROM team_profiles WHERE slug IS NOT NULL")).fetchall()
    )

    filled = 0
    errors = 0
    for i, team_id in enumerate(missing_ids):
        if is_job_paused(PAUSE_KEY):
            logger.info("Paused by admin")
            break
        try:
            resp = api_client.get_team_by_id(team_id)
            team_data = resp.get("response", [])
            if not team_data:
                team_data = [resp] if resp.get("team") else []
            if not team_data:
                continue
            t = team_data[0].get("team", {}) if isinstance(team_data[0], dict) else {}
            venue = team_data[0].get("venue", {}) if isinstance(team_data[0], dict) else {}
            if not t.get("id"):
                continue

            from src.utils.team_resolver import resolve_team_name

            name = t.get("name") or resolve_team_name(t["id"])
            slug = generate_unique_team_slug(name, t.get("country"), t["id"], existing_slugs)
            existing_slugs.add(slug)

            db.session.execute(
                text("""
                INSERT INTO team_profiles (team_id, name, code, country, founded, is_national,
                    logo_url, venue_name, venue_city, venue_capacity, slug, created_at, updated_at)
                VALUES (:team_id, :name, :code, :country, :founded, :is_national,
                    :logo_url, :venue_name, :venue_city, :venue_capacity, :slug, NOW(), NOW())
                ON CONFLICT (team_id) DO NOTHING
            """),
                {
                    "team_id": t["id"],
                    "name": name,
                    "code": t.get("code"),
                    "country": t.get("country"),
                    "founded": t.get("founded"),
                    "is_national": t.get("national", False),
                    "logo_url": t.get("logo"),
                    "venue_name": venue.get("name"),
                    "venue_city": venue.get("city"),
                    "venue_capacity": venue.get("capacity"),
                    "slug": slug,
                },
            )
            db.session.commit()
            filled += 1
        except Exception as e:
            db.session.rollback()
            errors += 1
            logger.warning(f"Team {team_id} failed: {e}")

        if (i + 1) % 50 == 0:
            logger.info(f"  Progress: {i + 1}/{len(missing_ids)}, filled={filled}, errors={errors}")

    remaining = _verify_count(
        "teams still missing",
        "SELECT COUNT(DISTINCT fs.team_api_id) FROM fixture_player_stats fs "
        "LEFT JOIN team_profiles tp ON fs.team_api_id = tp.team_id WHERE tp.team_id IS NULL",
    )
    logger.info(f"Phase 1 complete: {filled} added, {errors} errors, {remaining} still missing")
    return filled


def phase_2_backfill_players(dry_run=False):
    """Backfill Player records for all players in fixture_player_stats that are missing.

    Uses raw SQL INSERT ON CONFLICT to bypass ORM session issues.
    """
    from src.api_football_client import APIFootballClient

    logger.info("=== Phase 2: Backfill players table ===")

    missing = db.session.execute(
        text("""
        SELECT DISTINCT fs.player_api_id
        FROM fixture_player_stats fs
        LEFT JOIN players p ON fs.player_api_id = p.player_id
        WHERE p.player_id IS NULL
    """)
    ).fetchall()
    missing_ids = [row[0] for row in missing]
    logger.info(f"Players missing records: {len(missing_ids)}")

    if not missing_ids or dry_run:
        return len(missing_ids)

    api_client = APIFootballClient()
    filled = 0
    errors = 0
    for i, player_id in enumerate(missing_ids):
        if is_job_paused(PAUSE_KEY):
            logger.info("Paused by admin")
            break
        try:
            resp = api_client.get_player_by_id(player_id, season=2025)
            if not resp:
                errors += 1
                continue
            pdata = resp.get("player", {})
            if not pdata.get("id"):
                errors += 1
                continue

            db.session.execute(
                text("""
                INSERT INTO players (player_id, name, firstname, lastname, nationality,
                    age, position, photo_url, created_at, updated_at)
                VALUES (:pid, :name, :firstname, :lastname, :nationality,
                    :age, :position, :photo_url, NOW(), NOW())
                ON CONFLICT (player_id) DO NOTHING
            """),
                {
                    "pid": pdata["id"],
                    "name": pdata.get("name", str(pdata["id"])),
                    "firstname": pdata.get("firstname"),
                    "lastname": pdata.get("lastname"),
                    "nationality": pdata.get("nationality"),
                    "age": pdata.get("age"),
                    "position": pdata.get("position"),
                    "photo_url": pdata.get("photo"),
                },
            )
            db.session.commit()
            filled += 1
        except Exception as e:
            db.session.rollback()
            errors += 1
            if "quota" in str(e).lower() or "ratelimit" in str(e).lower().replace(" ", ""):
                logger.warning(f"API rate limit at player {i + 1}. Filled: {filled}")
                break

        if (i + 1) % 200 == 0:
            logger.info(f"  Progress: {i + 1}/{len(missing_ids)}, filled={filled}, errors={errors}")

    remaining = _verify_count(
        "players still missing",
        "SELECT COUNT(DISTINCT fs.player_api_id) FROM fixture_player_stats fs "
        "LEFT JOIN players p ON fs.player_api_id = p.player_id WHERE p.player_id IS NULL",
    )
    logger.info(f"Phase 2 complete: {filled} added, {errors} errors, {remaining} still missing")
    return filled


def phase_3_recompute_academy_ids(dry_run=False):
    """Recompute academy_club_ids for all PlayerJourney records using current algorithm.

    Pure DB computation — no API calls.
    """
    from src.models.journey import PlayerJourney, PlayerJourneyEntry
    from src.services.journey_sync import JourneySyncService

    logger.info("=== Phase 3: Recompute academy_club_ids ===")

    journeys = PlayerJourney.query.filter(
        db.or_(
            PlayerJourney.academy_club_ids.is_(None),
            func.jsonb_array_length(PlayerJourney.academy_club_ids) == 0,
        )
    ).all()
    logger.info(f"Journeys with missing academy_club_ids: {len(journeys)}")

    if not journeys or dry_run:
        return len(journeys)

    sync_service = JourneySyncService()
    fixed = 0
    errors = 0
    for i, journey in enumerate(journeys):
        if is_job_paused(PAUSE_KEY):
            logger.info("Paused by admin")
            break
        try:
            entries = PlayerJourneyEntry.query.filter_by(journey_id=journey.id).all()
            if not entries:
                continue
            sync_service._compute_academy_club_ids(journey, entries=entries)
            db.session.commit()
            if journey.academy_club_ids:
                fixed += 1
        except Exception as e:
            db.session.rollback()
            errors += 1
            if (i + 1) % 500 == 0:
                logger.warning(f"Journey {journey.id} failed: {e}")

        if (i + 1) % 500 == 0:
            logger.info(f"  Progress: {i + 1}/{len(journeys)}, fixed={fixed}, errors={errors}")

    remaining = _verify_count(
        "journeys still missing IDs",
        "SELECT COUNT(*) FROM player_journeys "
        "WHERE academy_club_ids IS NULL OR jsonb_array_length(academy_club_ids) = 0",
    )
    logger.info(f"Phase 3 complete: {fixed} updated, {errors} errors, {remaining} still missing")
    return fixed


def phase_4_refresh_statuses(dry_run=False):
    """Refresh tracked player statuses using existing journey data + fresh transfers."""
    from src.services.transfer_heal_service import refresh_and_heal
    from src.utils.job_utils import teams_with_active_tracked_players

    logger.info("=== Phase 4: Refresh statuses ===")

    team_ids = teams_with_active_tracked_players()
    logger.info(f"Teams to process: {len(team_ids)}")

    if dry_run:
        return len(team_ids)

    total_changed = 0
    total_errors = 0
    for i, team_db_id in enumerate(team_ids):
        if is_job_paused(PAUSE_KEY):
            logger.info("Paused by admin")
            break
        try:
            try:
                db.session.rollback()
            except Exception:
                pass
            result = refresh_and_heal(
                team_id=team_db_id,
                resync_journeys=False,
                dry_run=False,
                cascade_fixtures=False,
            )
            changed = len(result.get("players_changed", []))
            total_changed += changed
            if changed:
                logger.info(f"  Team {team_db_id}: {changed} players changed")
        except Exception as e:
            try:
                db.session.rollback()
            except Exception:
                pass
            total_errors += 1
            if total_errors <= 5:
                logger.warning(f"Team {team_db_id} failed: {e}")

        if (i + 1) % 20 == 0:
            logger.info(f"  Progress: {i + 1}/{len(team_ids)} teams, {total_changed} changes, {total_errors} errors")

    logger.info(
        f"Phase 4 complete: {total_changed} players changed, {total_errors} errors across {len(team_ids)} teams"
    )
    return total_changed


def phase_5_backfill_formations(dry_run=False):
    """Backfill formation data for fixture_player_stats rows missing it."""
    from src.api_football_client import APIFootballClient
    from src.models.weekly import Fixture, FixturePlayerStats
    from src.utils.formation_roles import grid_to_role

    logger.info("=== Phase 5: Backfill formations ===")

    fixture_ids = (
        db.session.query(FixturePlayerStats.fixture_id).filter(FixturePlayerStats.formation.is_(None)).distinct().all()
    )
    fixture_ids = [row[0] for row in fixture_ids]
    logger.info(f"Fixtures missing formation: {len(fixture_ids)}")

    if not fixture_ids or dry_run:
        return len(fixture_ids)

    api_client = APIFootballClient()
    total_updated = 0
    for i, fix_id in enumerate(fixture_ids):
        if is_job_paused(PAUSE_KEY):
            logger.info("Paused by admin")
            break
        fixture = db.session.get(Fixture, fix_id)
        if not fixture:
            continue
        try:
            lineups = api_client.get_fixture_lineups(fixture.fixture_id_api).get("response", [])
        except Exception:
            continue

        team_lineup = {}
        for lu in lineups:
            tid = (lu.get("team") or {}).get("id")
            if not tid:
                continue
            formation = lu.get("formation")
            player_grids = {}
            for entry in lu.get("startXI") or []:
                pb = (entry or {}).get("player") or {}
                if pb.get("id"):
                    player_grids[pb["id"]] = pb.get("grid")
            for entry in lu.get("substitutes") or []:
                pb = (entry or {}).get("player") or {}
                if pb.get("id"):
                    player_grids[pb["id"]] = None
            team_lineup[tid] = {"formation": formation, "players": player_grids}

        for fps in FixturePlayerStats.query.filter_by(fixture_id=fix_id).all():
            tl = team_lineup.get(fps.team_api_id)
            if not tl:
                continue
            formation = tl["formation"]
            grid = tl["players"].get(fps.player_api_id)
            fps.formation = formation
            fps.grid = grid
            fps.formation_position = grid_to_role(formation, grid)
            total_updated += 1

        db.session.commit()

        if (i + 1) % 100 == 0:
            logger.info(f"  Progress: {i + 1}/{len(fixture_ids)}, updated={total_updated}")

    remaining = _verify_count(
        "fixture stats still missing formation", "SELECT COUNT(*) FROM fixture_player_stats WHERE formation IS NULL"
    )
    logger.info(f"Phase 5 complete: {total_updated} updated, {remaining} still missing")
    return total_updated


def run(dry_run=False, start_phase=1):
    try:
        db.session.rollback()
    except Exception:
        pass

    if is_job_paused(PAUSE_KEY):
        logger.info("Data integrity fix is paused by admin. Exiting.")
        return

    logger.info(f"Starting data integrity fix. dry_run={dry_run}, start_phase={start_phase}")
    start = datetime.now(UTC)

    results = {}
    phases = [
        (1, "team_profiles", phase_1_backfill_team_profiles),
        (2, "players", phase_2_backfill_players),
        (3, "academy_ids", phase_3_recompute_academy_ids),
        (4, "statuses", phase_4_refresh_statuses),
        (5, "formations", phase_5_backfill_formations),
    ]

    api_heavy_phases = {"players", "statuses", "formations"}
    for num, name, func in phases:
        if num < start_phase:
            logger.info(f"Skipping phase {num} ({name})")
            continue
        if is_job_paused(PAUSE_KEY):
            logger.info("Paused by admin, stopping.")
            break
        if name in api_heavy_phases and results:
            logger.info(f"Cooling down 60s before phase {num}...")
            time.sleep(60)
        try:
            results[name] = func(dry_run=dry_run)
        except Exception as e:
            logger.error(f"Phase {num} ({name}) failed: {e}")
            results[name] = f"ERROR: {e}"

    elapsed = (datetime.now(UTC) - start).total_seconds()
    logger.info(f"Data integrity fix complete in {elapsed / 60:.1f} minutes. Results: {results}")
    return results


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    start_phase = 1
    for arg in sys.argv:
        if arg.startswith("--phase"):
            try:
                start_phase = int(sys.argv[sys.argv.index(arg) + 1])
            except (IndexError, ValueError):
                pass
    with app.app_context():
        run(dry_run=dry_run, start_phase=start_phase)
