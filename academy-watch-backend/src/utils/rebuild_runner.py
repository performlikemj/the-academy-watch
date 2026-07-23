"""Subprocess entry point for rebuild jobs.

Runs rebuild operations in a separate multiprocessing.Process, completely
isolated from gunicorn workers.  This prevents gunicorn's worker timeout
from killing long-running rebuilds, and avoids zombie threads exhausting
the DB connection pool.
"""

import logging
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


def _classification_season_start(league_api_id, season_configs) -> tuple[int, int]:
    """Return the configured statistics-season boundary for a league."""
    season_config = season_configs.get(league_api_id)
    if season_config is None:
        return (7, 1)

    season_type = (getattr(season_config, "season_type", None) or "").strip().lower()
    rollover_month = getattr(season_config, "rollover_month", None)
    try:
        rollover_month = int(rollover_month)
    except (TypeError, ValueError):
        rollover_month = None
    if rollover_month is not None and 1 <= rollover_month <= 12:
        return (rollover_month, 1)
    if season_type == "calendar":
        return (1, 1)
    return (7, 1)


def _classification_season_context(journey, season_configs) -> tuple[int | None, int, int]:
    """Use one domestic entry for both latest-season and calendar evidence."""
    if journey is None:
        return (None, 7, 1)
    from src.models.journey import PlayerJourneyEntry

    latest_entry = journey.entries.filter(PlayerJourneyEntry.is_international.is_not(True)).first()
    if latest_entry is None:
        latest_entry = journey.entries.first()
    if latest_entry is None:
        return (None, 7, 1)
    start_month, start_day = _classification_season_start(
        getattr(latest_entry, "league_api_id", None),
        season_configs,
    )
    return (latest_entry.season, start_month, start_day)


def _rebuild_transfer_evidence(
    api_client,
    player_api_id: int,
    transfer_cache: dict[int, list | None],
    *,
    parent_api_id: int,
    parent_club_name: str | None,
    as_of,
    season_start_month: int,
    season_start_day: int,
):
    """Fetch once, then resolve the cached history for one academy parent.

    ``None`` in the cache means the provider request failed; an empty list is a
    successful, authoritative empty history.  Keeping those states distinct
    prevents Stage 4 and Stage 6 from retrying independently or treating an
    outage as evidence that a previous fee should be cleared.
    """
    from src.services.transfer_resolver import resolve_transfer_state
    from src.utils.academy_classifier import flatten_transfers

    if player_api_id not in transfer_cache:
        try:
            transfer_cache[player_api_id] = flatten_transfers(api_client.get_player_transfers(player_api_id))
        except Exception as exc:
            logger.warning(
                "Transfer fetch failed during rebuild for player %s: %s",
                player_api_id,
                exc,
            )
            transfer_cache[player_api_id] = None

    transfers = transfer_cache[player_api_id]
    if transfers is None:
        return None, None

    resolution = resolve_transfer_state(
        transfers,
        as_of=as_of,
        initial_owner={"id": parent_api_id, "name": parent_club_name},
        season_start_month=season_start_month,
        season_start_day=season_start_day,
    )
    return transfers, resolution


def _rebuild_sale_fee(
    current_fee: str | None,
    *,
    status: str,
    resolution,
    parent_api_id: int,
    parent_club_name: str | None,
) -> str | None:
    """Return the academy-parent sale fee, preserving it on fetch failure."""
    from src.utils.academy_classifier import latest_parent_permanent_departure

    if resolution is None:
        return current_fee
    if status != "sold":
        return None
    departure = latest_parent_permanent_departure(
        resolution,
        parent_api_id,
        parent_club_name,
    )
    return departure.fee if departure is not None else None


def run_rebuild_process(job_id, rebuild_type, kwargs):
    """Entry point for the rebuild subprocess.

    Creates its own Flask app context and DB connections, completely
    independent of any gunicorn worker.
    """
    import signal
    import sys

    # Ensure subprocess logging goes to stdout/stderr so container logs
    # capture it.  multiprocessing.Process inherits the parent's FDs but
    # the logging configuration may not propagate.
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        force=True,
    )

    from src.main import app

    # Handle SIGTERM gracefully so container restarts / worker recycling
    # mark the job as failed instead of leaving it stuck in 'running'.
    def _sigterm_handler(signum, frame):
        logger.warning("Rebuild subprocess %s received SIGTERM, marking job failed", job_id)
        try:
            with app.app_context():
                from src.utils.background_jobs import update_job as _update

                _update(
                    job_id,
                    status="failed",
                    error="Process terminated (SIGTERM — container restart or shutdown)",
                    completed_at=datetime.now(UTC).isoformat(),
                )
        except Exception:
            pass
        sys.exit(1)

    signal.signal(signal.SIGTERM, _sigterm_handler)

    with app.app_context():
        from src.models.league import db
        from src.utils.background_jobs import update_job

        try:
            if rebuild_type == "seed_big6":
                from src.services.big6_seeding_service import run_big6_seed

                result = run_big6_seed(job_id, **kwargs)
                update_job(job_id, status="completed", results=result, completed_at=datetime.now(UTC).isoformat())
            elif rebuild_type == "full_rebuild":
                _run_full_rebuild(job_id, kwargs)
        except InterruptedError as e:
            db.session.rollback()
            update_job(job_id, status="cancelled", error=str(e), completed_at=datetime.now(UTC).isoformat())
        except Exception as e:
            logger.exception("Rebuild job %s failed", job_id)
            db.session.rollback()
            update_job(job_id, status="failed", error=str(e), completed_at=datetime.now(UTC).isoformat())


def _run_full_rebuild(job_id, config):
    """Execute the full academy rebuild pipeline.

    Stages:
      1. Clean slate (delete tracked players, journeys, cohorts, loans, locations)
      2. Seed academy leagues
      3. Cohort discovery + journey sync (Big 6 seeding)
      4. Create TrackedPlayer records for each team
      5. Link orphaned journeys
      6. Refresh statuses
      7. Seed club locations
    """
    from sqlalchemy import cast
    from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB
    from src.api_football_client import APIFootballClient
    from src.models.cohort import AcademyCohort, CohortMember
    from src.models.journey import ClubLocation, PlayerJourney, PlayerJourneyEntry
    from src.models.league import AcademyAppearance, AcademyLeague, Team, db
    from src.models.season_rollup import LeagueSeasonConfig
    from src.models.tracked_player import TrackedPlayer
    from src.models.weekly import WeeklyLoanAppearance
    from src.services.big6_seeding_service import BIG_6, SEASONS, run_big6_seed
    from src.services.journey_sync import JourneySyncService, seed_club_locations
    from src.services.youth_competition_resolver import build_academy_league_seed_rows
    from src.utils.academy_classifier import classify_tracked_player
    from src.utils.academy_window import is_within_academy_window, last_academy_season_for
    from src.utils.background_jobs import is_job_cancelled, update_job

    if config.get("team_ids"):
        team_ids = config["team_ids"]
    else:
        # Process ALL tracked teams, not just Big 6
        tracked_teams = Team.query.filter_by(is_tracked=True).with_entities(Team.team_id).all()
        team_ids = [t[0] for t in tracked_teams] if tracked_teams else list(BIG_6.keys())
    seasons = config.get("seasons") or SEASONS
    skip_clean = config.get("skip_clean", False)
    skip_cohorts = config.get("skip_cohorts", False)
    season_configs = {row.league_api_id: row for row in LeagueSeasonConfig.query.all()}

    stage = "starting"
    try:
        total_stages = 7
        results = {
            "stages_completed": [],
            "teams": {},
            "errors": [],
        }

        def _check_cancelled():
            if is_job_cancelled(job_id):
                raise InterruptedError(f"Job cancelled at stage: {stage}")

        # ── Pre-check: ensure league teams exist ──
        league_ids = config.get("league_ids", [])
        if league_ids:
            from src.models.league import League

            for lid in league_ids:
                league = League.query.filter_by(league_id=lid).first()
                if not league or Team.query.filter_by(league_id=league.id, is_active=True).count() == 0:
                    update_job(job_id, current_player="Syncing European league teams...")
                    from src.routes.teams import _lazy_sync_european_teams

                    _lazy_sync_european_teams(seasons[0] if seasons else None)
                    break

        # ── Stage 1: Clean slate ──
        if not skip_clean:
            stage = "clean"
            update_job(job_id, progress=0, total=total_stages, current_player="Stage 1: Cleaning data...")
            deleted = {}
            # Delete tables with models in FK-safe order
            for name, model in [
                ("tracked_players", TrackedPlayer),
                ("journey_entries", PlayerJourneyEntry),
                ("cohort_members", CohortMember),
                ("journeys", PlayerJourney),
                ("cohorts", AcademyCohort),
                ("weekly_loan_appearances", WeeklyLoanAppearance),
                ("academy_appearances", AcademyAppearance),
                ("tracked_players", TrackedPlayer),
                ("club_locations", ClubLocation),
            ]:
                count = model.query.count()
                if count > 0:
                    model.query.delete()
                    db.session.commit()
                deleted[name] = count
            # Also clear cached API responses so discovery gets fresh data
            from src.models.api_cache import APICache

            deleted["players_cache"] = APICache.invalidate_cached("players")
            results["deleted"] = deleted
            results["stages_completed"].append("clean")
        else:
            results["stages_completed"].append("clean (skipped)")

        # ── Stage 2: Seed academy leagues ──
        _check_cancelled()
        stage = "seed_leagues"
        update_job(job_id, progress=1, total=total_stages, current_player="Stage 2: Seeding academy leagues...")
        api_client_for_leagues = APIFootballClient()
        youth_league_rows = build_academy_league_seed_rows(
            api_client=api_client_for_leagues,
            season=max(seasons),
        )
        leagues_created = 0
        leagues_updated = 0
        for ld in youth_league_rows:
            existing = AcademyLeague.query.filter_by(api_league_id=ld["api_league_id"]).first()
            if not existing:
                league = AcademyLeague(
                    api_league_id=ld["api_league_id"],
                    name=ld["name"],
                    country=ld["country"],
                    level=ld["level"],
                    season=ld.get("season"),
                    is_active=True,
                    sync_enabled=True,
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
                db.session.add(league)
                leagues_created += 1
            else:
                changed = False
                if existing.name != ld["name"]:
                    existing.name = ld["name"]
                    changed = True
                if existing.country != ld["country"]:
                    existing.country = ld["country"]
                    changed = True
                if existing.level != ld["level"]:
                    existing.level = ld["level"]
                    changed = True
                if ld.get("season") and existing.season != ld.get("season"):
                    existing.season = ld.get("season")
                    changed = True
                if not existing.is_active:
                    existing.is_active = True
                    changed = True
                if not existing.sync_enabled:
                    existing.sync_enabled = True
                    changed = True
                if changed:
                    existing.updated_at = datetime.now(UTC)
                    leagues_updated += 1
        if leagues_created or leagues_updated:
            db.session.commit()
        results["leagues_created"] = leagues_created
        results["leagues_updated"] = leagues_updated
        results["stages_completed"].append("seed_leagues")

        # ── Stage 3: Cohort discovery + journey sync ──
        _check_cancelled()
        if not skip_cohorts:
            stage = "cohorts"
            update_job(
                job_id,
                progress=2,
                total=total_stages,
                current_player="Stage 3: Discovering cohorts + syncing journeys...",
            )
            try:
                seed_result = run_big6_seed(
                    job_id,
                    seasons=seasons,
                    team_ids=team_ids,
                    cohort_discover_timeout=config.get("cohort_discover_timeout"),
                    player_sync_timeout=config.get("player_sync_timeout"),
                    rate_limit_per_minute=config.get("rate_limit_per_minute"),
                    rate_limit_per_day=config.get("rate_limit_per_day"),
                )
                results["cohorts_created"] = seed_result.get("cohorts_created", 0)
                results["players_synced"] = seed_result.get("players_synced", 0)
            except Exception as stage3_err:
                logger.warning("Stage 3 (cohort seed) failed, continuing to remaining stages: %s", stage3_err)
                results["errors"].append(f"Stage 3 partial failure: {stage3_err}")

            # Report how many cohorts still need journey sync
            seeded_only = AcademyCohort.query.filter_by(sync_status="seeded").count()
            if seeded_only:
                logger.warning('%d cohorts still at "seeded" status (journey sync incomplete)', seeded_only)
                results["cohorts_pending_sync"] = seeded_only

            results["stages_completed"].append("cohorts")
        else:
            results["stages_completed"].append("cohorts (skipped)")

        # ── Stage 4: Create TrackedPlayers ──
        _check_cancelled()
        stage = "tracked_players"
        update_job(job_id, progress=4, total=total_stages, current_player="Stage 4: Creating TrackedPlayer records...")
        api_client = APIFootballClient()
        journey_svc = JourneySyncService(api_client)
        current_season = max(seasons)
        rebuild_as_of = datetime.now(UTC).date()
        transfer_cache: dict[int, list | None] = {}
        total_created = 0
        total_skipped = 0

        for api_team_id in team_ids:
            team_rec = Team.query.filter_by(team_id=api_team_id).order_by(Team.season.desc()).first()
            team_name = team_rec.name if team_rec else str(api_team_id)
            update_job(job_id, current_player=f"Stage 4: Seeding {team_name}...")

            team = team_rec
            if not team:
                results["errors"].append(f"{team_name}: no Team row found")
                continue

            parent_api_id = team.team_id
            # Source 1: academy_club_ids
            known_journeys = PlayerJourney.query.filter(
                PlayerJourney.academy_club_ids.contains(cast([parent_api_id], PG_JSONB))
            ).all()
            candidate_ids = {j.player_api_id: j for j in known_journeys}

            # Source 2: API squad (multiple seasons)
            squad_data = []
            seasons_to_fetch = range(current_season - 3, current_season + 1)
            for fetch_season in seasons_to_fetch:
                try:
                    season_squad = api_client.get_team_players(parent_api_id, season=fetch_season)
                    for entry in season_squad:
                        player_info = (entry or {}).get("player") or {}
                        pid = player_info.get("id")
                        if pid:
                            pass  # just collecting data
                    squad_data.extend(season_squad)
                except Exception as e:
                    logger.warning("Squad fetch failed for %s season %d: %s", team_name, fetch_season, e)

            # Sync journeys for squad players
            for entry in squad_data:
                player_info = (entry or {}).get("player") or {}
                pid = player_info.get("id")
                if not pid:
                    continue
                pid = int(pid)
                if pid in candidate_ids:
                    continue
                age = player_info.get("age")
                if age and int(age) > 23:
                    continue
                existing_journey = PlayerJourney.query.filter_by(player_api_id=pid).first()
                if existing_journey:
                    if parent_api_id in (existing_journey.academy_club_ids or []):
                        candidate_ids[pid] = existing_journey
                    continue
                try:
                    journey = journey_svc.sync_player(pid)
                    if journey and parent_api_id in (journey.academy_club_ids or []):
                        candidate_ids[pid] = journey
                except Exception:
                    pass

            # Source 3: CohortMember records (skip duplicate cohorts)
            cohort_ids = [
                c.id
                for c in AcademyCohort.query.filter_by(team_api_id=parent_api_id)
                .filter(AcademyCohort.sync_status != "duplicate")
                .all()
            ]
            if cohort_ids:
                cohort_members = CohortMember.query.filter(CohortMember.cohort_id.in_(cohort_ids)).all()
                for cm in cohort_members:
                    if cm.player_api_id and cm.player_api_id not in candidate_ids:
                        journey = PlayerJourney.query.filter_by(player_api_id=cm.player_api_id).first()
                        if journey and parent_api_id in (journey.academy_club_ids or []):
                            candidate_ids[cm.player_api_id] = journey

            # Build squad lookup
            squad_by_id = {}
            for entry in squad_data:
                pi = (entry or {}).get("player") or {}
                if pi.get("id"):
                    squad_by_id[int(pi["id"])] = entry

            # Create TrackedPlayer rows
            created = 0
            skipped = 0
            for pid, journey in candidate_ids.items():
                try:
                    existing = TrackedPlayer.query.filter_by(player_api_id=pid, team_id=team.id).first()
                    if existing:
                        skipped += 1
                        continue

                    squad_entry = squad_by_id.get(pid) or {}
                    pi = squad_entry.get("player") or {}

                    from src.utils.player_names import resolve_player_name

                    player_name = resolve_player_name(pid, journey.player_name if journey else None, pi.get("name"))
                    photo_url = (journey.player_photo if journey else None) or pi.get("photo")
                    nationality = (journey.nationality if journey else None) or pi.get("nationality")
                    birth_date = (journey.birth_date if journey else None) or (pi.get("birth") or {}).get("date")
                    position = pi.get("position") or ""
                    age = pi.get("age")
                    latest_season, season_start_month, season_start_day = _classification_season_context(
                        journey,
                        season_configs,
                    )
                    transfers, transfer_resolution = _rebuild_transfer_evidence(
                        api_client,
                        pid,
                        transfer_cache,
                        parent_api_id=parent_api_id,
                        parent_club_name=team.name,
                        as_of=rebuild_as_of,
                        season_start_month=season_start_month,
                        season_start_day=season_start_day,
                    )
                    if transfer_resolution is None:
                        skipped += 1
                        logger.warning(
                            "Skipping rebuild creation for player %s at %s because transfer evidence was not fetched",
                            pid,
                            team.name,
                        )
                        continue

                    status, current_club_api_id, current_club_name = classify_tracked_player(
                        current_club_api_id=journey.current_club_api_id if journey else None,
                        current_club_name=journey.current_club_name if journey else None,
                        current_level=journey.current_level if journey else None,
                        parent_api_id=parent_api_id,
                        parent_club_name=team.name,
                        transfers=transfers,
                        player_api_id=pid,
                        latest_season=latest_season,
                        transfer_resolution=transfer_resolution,
                        as_of=rebuild_as_of,
                        season_start_month=season_start_month,
                        season_start_day=season_start_day,
                    )
                    sale_fee = _rebuild_sale_fee(
                        None,
                        status=status,
                        resolution=transfer_resolution,
                        parent_api_id=parent_api_id,
                        parent_club_name=team.name,
                    )

                    current_level = journey.current_level if journey and journey.current_level else None

                    last_academy_season = last_academy_season_for(journey, parent_api_id)
                    if not is_within_academy_window(last_academy_season, status=status, birth_date=birth_date):
                        skipped += 1
                        continue

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
                        sale_fee=sale_fee,
                        data_source="api-football",
                        data_depth="full_stats",
                        journey_id=journey.id if journey else None,
                        last_academy_season=last_academy_season,
                    )
                    db.session.add(tp)
                    created += 1
                except Exception as entry_err:
                    results["errors"].append(f"{team_name} player {pid}: {entry_err}")

            db.session.commit()
            results["teams"][team_name] = {"created": created, "skipped": skipped, "candidates": len(candidate_ids)}
            total_created += created
            total_skipped += skipped

        results["total_created"] = total_created
        results["total_skipped"] = total_skipped
        results["stages_completed"].append("tracked_players")

        # ── Stage 5: Link orphaned journeys ──
        _check_cancelled()
        stage = "link_journeys"
        update_job(job_id, progress=5, total=total_stages, current_player="Stage 5: Linking orphaned journeys...")
        unlinked = TrackedPlayer.query.filter(
            TrackedPlayer.is_active,
            TrackedPlayer.journey_id.is_(None),
        ).all()
        linked = 0
        for tp in unlinked:
            journey = PlayerJourney.query.filter_by(player_api_id=tp.player_api_id).first()
            if journey:
                tp.journey_id = journey.id
                linked += 1
        if linked:
            db.session.commit()
        results["journeys_linked"] = linked
        results["stages_completed"].append("link_journeys")

        # ── Stage 6: Refresh statuses ──
        _check_cancelled()
        stage = "refresh_statuses"
        update_job(job_id, progress=6, total=total_stages, current_player="Stage 6: Refreshing statuses...")
        tracked = TrackedPlayer.query.filter(TrackedPlayer.is_active).all()

        # Build squad membership map for squad cross-reference
        squad_members_by_club = {}
        _loan_ids = {tp.current_club_api_id for tp in tracked if tp.current_club_api_id}
        _parent_ids = {tp.team.team_id for tp in tracked if tp.team}
        for _cid in _loan_ids | _parent_ids:
            try:
                _sq = api_client.get_team_players(_cid)
                squad_members_by_club[_cid] = {
                    int(e["player"]["id"]) for e in _sq if e and e.get("player", {}).get("id")
                }
            except Exception:
                pass

        updated = 0
        status_counts = {}
        for tp in tracked:
            if not tp.team:
                continue
            journey = tp.journey
            latest_season, season_start_month, season_start_day = _classification_season_context(
                journey,
                season_configs,
            )
            transfers, transfer_resolution = _rebuild_transfer_evidence(
                api_client,
                tp.player_api_id,
                transfer_cache,
                parent_api_id=tp.team.team_id,
                parent_club_name=tp.team.name,
                as_of=rebuild_as_of,
                season_start_month=season_start_month,
                season_start_day=season_start_day,
            )
            if transfer_resolution is None:
                # A failed fetch is not evidence that any stored transfer state
                # changed. Preserve status, current club, and fee together.
                status_counts[tp.status] = status_counts.get(tp.status, 0) + 1
                logger.warning(
                    "Skipping rebuild transfer refresh for player %s because transfer evidence was not fetched",
                    tp.player_api_id,
                )
                continue
            status, loan_api_id, loan_name = classify_tracked_player(
                current_club_api_id=journey.current_club_api_id if journey else None,
                current_club_name=journey.current_club_name if journey else None,
                current_level=journey.current_level if journey else None,
                parent_api_id=tp.team.team_id,
                parent_club_name=tp.team.name,
                transfers=transfers,
                player_api_id=tp.player_api_id,
                latest_season=latest_season,
                squad_members_by_club=squad_members_by_club,
                transfer_resolution=transfer_resolution,
                as_of=rebuild_as_of,
                season_start_month=season_start_month,
                season_start_day=season_start_day,
            )
            sale_fee = _rebuild_sale_fee(
                tp.sale_fee,
                status=status,
                resolution=transfer_resolution,
                parent_api_id=tp.team.team_id,
                parent_club_name=tp.team.name,
            )
            if (
                tp.status != status
                or tp.current_club_api_id != loan_api_id
                or tp.current_club_name != loan_name
                or tp.sale_fee != sale_fee
            ):
                tp.status = status
                tp.current_club_api_id = loan_api_id
                tp.current_club_name = loan_name
                tp.sale_fee = sale_fee
                updated += 1
            status_counts[status] = status_counts.get(status, 0) + 1
        if updated:
            db.session.commit()
        results["statuses_updated"] = updated
        results["status_breakdown"] = status_counts
        results["stages_completed"].append("refresh_statuses")

        # ── Stage 7: Seed club locations ──
        _check_cancelled()
        stage = "locations"
        update_job(job_id, progress=7, total=total_stages, current_player="Stage 7: Seeding club locations...")
        locations_added = seed_club_locations()
        results["locations_added"] = locations_added
        results["stages_completed"].append("locations")

        update_job(job_id, status="completed", results=results, completed_at=datetime.now(UTC).isoformat())

    except InterruptedError as e:
        logger.info("Full rebuild job %s cancelled at stage: %s", job_id, stage)
        results["stages_completed"].append(f"{stage} (cancelled)")
        update_job(
            job_id, status="cancelled", results=results, error=str(e), completed_at=datetime.now(UTC).isoformat()
        )
    except Exception as e:
        logger.exception("Full rebuild job %s failed at stage: %s", job_id, stage)
        db.session.rollback()
        update_job(job_id, status="failed", error=f"Failed at {stage}: {e}", completed_at=datetime.now(UTC).isoformat())
