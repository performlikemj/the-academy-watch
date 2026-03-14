"""
Big 6 Seeding Service

Orchestrates bulk cohort discovery and journey sync for the
Premier League Big 6 clubs across multiple youth leagues and seasons.
"""

import logging
import time
from datetime import datetime, timezone
from collections import deque

from src.models.league import db
from src.models.cohort import AcademyCohort, CohortMember
from src.models.journey import PlayerJourney
from src.services.cohort_service import CohortService
from src.services.journey_sync import JourneySyncService
from src.services.youth_competition_resolver import (
    get_default_youth_league_map,
    resolve_team_name,
    resolve_youth_leagues,
    resolve_youth_team_for_parent,
)
from src.utils.background_jobs import update_job, is_job_cancelled

logger = logging.getLogger(__name__)

BIG_6 = {
    33: 'Manchester United',
    42: 'Arsenal',
    49: 'Chelsea',
    50: 'Manchester City',
    40: 'Liverpool',
    47: 'Tottenham',
}

YOUTH_LEAGUES = get_default_youth_league_map()

SEASONS = [2020, 2021, 2022, 2023, 2024]

# Max time (seconds) for a single discover_cohort call before skipping
COHORT_DISCOVER_TIMEOUT = 120
# Max time (seconds) for a single sync_player call before skipping
PLAYER_SYNC_TIMEOUT = 90


class RateLimiter:
    """Simple rate limiter tracking per-minute and per-day API usage."""

    def __init__(self, per_minute_cap=280, per_day_cap=7000, heartbeat_fn=None):
        self.per_minute_cap = per_minute_cap
        self.per_day_cap = per_day_cap
        self.minute_calls = deque()
        self.day_calls = 0
        self.heartbeat_fn = heartbeat_fn

    def wait_if_needed(self):
        """Block if rate limits would be exceeded."""
        now = time.time()

        # Clean old minute entries
        while self.minute_calls and self.minute_calls[0] < now - 60:
            self.minute_calls.popleft()

        # Check per-minute cap
        if len(self.minute_calls) >= self.per_minute_cap:
            sleep_until = self.minute_calls[0] + 60
            sleep_time = sleep_until - now
            if sleep_time > 0:
                if self.heartbeat_fn:
                    self.heartbeat_fn()
                logger.info(f"Rate limit: sleeping {sleep_time:.1f}s (minute cap)")
                time.sleep(sleep_time)

        # Check per-day cap
        if self.day_calls >= self.per_day_cap:
            logger.warning("Daily API call limit reached, stopping")
            raise RuntimeError("Daily API call limit reached")

        self.minute_calls.append(time.time())
        self.day_calls += 1


def run_big6_seed(job_id, seasons=None, team_ids=None, league_ids=None,
                   cohort_discover_timeout=None, player_sync_timeout=None,
                   rate_limit_per_minute=None, rate_limit_per_day=None):
    """
    Run the full Big 6 cohort seeding pipeline.

    Phase 1: Discover cohorts for each (team, league, season) combo
    Phase 2: Sync journeys for all unique players
    Phase 3: Refresh cohort aggregates

    Args:
        job_id: Background job ID for progress tracking
        seasons: List of season years (default: SEASONS)
        team_ids: List of team API IDs (default: BIG_6 keys)
        league_ids: List of league API IDs (default: YOUTH_LEAGUES keys)
        cohort_discover_timeout: Seconds before skipping a cohort discovery (default: COHORT_DISCOVER_TIMEOUT)
        player_sync_timeout: Seconds before skipping a player sync (default: PLAYER_SYNC_TIMEOUT)
    """
    seasons = seasons or SEASONS
    team_ids = team_ids or list(BIG_6.keys())
    provided_league_ids = league_ids
    league_ids = league_ids or list(YOUTH_LEAGUES.keys())
    cohort_timeout = cohort_discover_timeout or COHORT_DISCOVER_TIMEOUT
    player_timeout = player_sync_timeout or PLAYER_SYNC_TIMEOUT

    cohort_service = CohortService()
    journey_service = JourneySyncService()
    api_client = cohort_service.api

    # Group teams by country for per-country youth league resolution.
    from src.models.league import Team as TeamModel
    team_country_map: dict[str, list[int]] = {}
    for team_id in team_ids:
        team_row = TeamModel.query.filter_by(team_id=team_id).order_by(TeamModel.season.desc()).first()
        country = (team_row.league.country if team_row and team_row.league else 'England')
        team_country_map.setdefault(country, []).append(team_id)

    # Resolve youth competitions per country (with static fallback).
    combos = []
    if provided_league_ids:
        # Explicit league IDs override country-based resolution.
        resolved_leagues = resolve_youth_leagues(
            api_client=api_client,
            explicit_league_ids=provided_league_ids,
        )
        combos = [(t, lg, s) for t in team_ids for lg in resolved_leagues for s in seasons]
    else:
        for country, country_team_ids in team_country_map.items():
            resolved_leagues = resolve_youth_leagues(
                api_client=api_client,
                country=country,
            )
            if not resolved_leagues:
                resolved_leagues = [
                    {'league_id': lid, 'name': YOUTH_LEAGUES.get(lid, str(lid))}
                    for lid in league_ids
                ]
            combos.extend(
                (t, lg, s) for t in country_team_ids for lg in resolved_leagues for s in seasons
            )
    total_combos = len(combos)

    update_job(job_id, total=total_combos, progress=0)
    logger.info(
        "Seed: %d combos across %d teams in %d countries",
        total_combos,
        len(team_ids),
        len(team_country_map),
    )

    parent_names = {
        team_id: resolve_team_name(api_client, team_id, fallback_name=BIG_6.get(team_id))
        for team_id in team_ids
    }
    teams_cache = {}
    skipped_no_youth_team = 0
    skipped_empty_cohorts = 0

    def phase1_heartbeat():
        update_job(job_id, current_player="Phase 1: discovering cohorts...")

    # ── Phase 1: Discovery ──
    cohort_ids = []
    for idx, (team_id, league_meta, season) in enumerate(combos):
        if is_job_cancelled(job_id):
            logger.info("Big 6 seed cancelled during Phase 1 at combo %d/%d", idx, total_combos)
            return {'cancelled': True, 'phase': 'discovery', 'cohorts_created': len(cohort_ids)}

        league_id = int(league_meta.get('league_id'))
        league_name = league_meta.get('name') or YOUTH_LEAGUES.get(league_id, str(league_id))
        team_name = parent_names.get(team_id, str(team_id))

        try:
            update_job(
                job_id,
                progress=idx,
                current_player=f"Discovering {team_name} {league_name} {season}",
            )

            # Resolve the youth-team API ID for this parent team in this league/season.
            query_team_id, query_team_name = resolve_youth_team_for_parent(
                api_client=api_client,
                league_id=league_id,
                season=season,
                parent_team_name=team_name,
                teams_cache=teams_cache,
            )
            if not query_team_id:
                skipped_no_youth_team += 1
                logger.info(
                    "Skipping combo: no youth team found for parent='%s' league=%s season=%s",
                    team_name,
                    league_name,
                    season,
                )
                continue

            # Skip if already complete
            existing = AcademyCohort.query.filter_by(
                team_api_id=team_id,
                league_api_id=league_id,
                season=season
            ).first()

            if existing and existing.sync_status != 'failed':
                member_count = CohortMember.query.filter_by(cohort_id=existing.id).count()
                if member_count > 0:
                    cohort_ids.append(existing.id)
                    continue
                # Empty cohort — fall through to re-discover

            # Clear stale cache entries that may contain empty API responses.
            try:
                from src.models.api_cache import APICache
                for page in range(1, 11):
                    APICache.invalidate_cached('players', {
                        'team': int(query_team_id),
                        'league': int(league_id),
                        'season': int(season),
                        'page': page,
                    })
            except Exception as cache_err:
                logger.warning("Cache clearing failed for combo %s/%s/%s: %s", team_name, league_name, season, cache_err)

            # Call discover_cohort directly in the main thread.
            # Previous approach used ThreadPoolExecutor for timeout, but
            # timed-out threads leaked DB connections from the pool,
            # eventually exhausting it and hanging the subprocess.
            # The API client has per-request HTTP timeouts (15s), so
            # individual calls are bounded.
            cohort = cohort_service.discover_cohort(
                team_api_id=team_id, league_api_id=league_id, season=season,
                fallback_team_name=team_name, fallback_league_name=league_name,
                query_team_api_id=int(query_team_id), heartbeat_fn=phase1_heartbeat,
            )
            if not cohort:
                skipped_empty_cohorts += 1
                continue

            if cohort.total_players > 0:
                # Check for near-duplicate cohorts (different league IDs, same players)
                existing_cohorts = AcademyCohort.query.filter(
                    AcademyCohort.team_api_id == team_id,
                    AcademyCohort.season == season,
                    AcademyCohort.id != cohort.id,
                    AcademyCohort.sync_status.in_(['complete', 'seeding', 'seeded', 'partial']),
                ).all()
                is_dup = False
                new_pids = {m.player_api_id for m in CohortMember.query.filter_by(cohort_id=cohort.id).all()}
                for ec in existing_cohorts:
                    ec_pids = {m.player_api_id for m in CohortMember.query.filter_by(cohort_id=ec.id).all()}
                    if ec_pids and new_pids:
                        overlap = len(new_pids & ec_pids) / min(len(new_pids), len(ec_pids))
                        if overlap > 0.8:
                            is_dup = True
                            break
                if is_dup:
                    cohort.sync_status = 'duplicate'
                    db.session.commit()
                    logger.info("Skipping duplicate cohort id=%s (>80%% overlap)", cohort.id)
                    continue
                cohort_ids.append(cohort.id)
            else:
                skipped_empty_cohorts += 1
                logger.info(
                    "Skipping empty cohort id=%s (%s/%s/%s, query_team=%s %s)",
                    cohort.id,
                    team_name,
                    league_name,
                    season,
                    query_team_id,
                    query_team_name,
                )

        except Exception as e:
            logger.error(f"Failed to discover cohort {team_name}/{league_name}/{season}: {e}")
            continue

    if not cohort_ids:
        logger.warning("Big 6 seed produced no populated cohorts")
        return {
            'cohorts_created': 0,
            'players_synced': 0,
            'combos_attempted': total_combos,
            'combos_skipped_no_youth_team': skipped_no_youth_team,
            'combos_skipped_empty_cohort': skipped_empty_cohorts,
            'resolved_leagues': [l.get('league_id') for l in resolved_leagues],
        }

    # ── Phase 2: Journey sync ──
    # Pre-load cohort parent context for status derivation
    cohort_context = {}
    for cid in cohort_ids:
        c = db.session.get(AcademyCohort, cid)
        if c:
            cohort_context[cid] = (c.team_api_id, c.team_name or '')

    # Collect all unique player IDs across cohorts
    all_members = CohortMember.query.filter(
        CohortMember.cohort_id.in_(cohort_ids),
        CohortMember.journey_synced == False
    ).all()

    # Dedupe by player_api_id
    seen_players = set()
    unique_members = []
    for m in all_members:
        if m.player_api_id not in seen_players:
            seen_players.add(m.player_api_id)
            unique_members.append(m)

    total_players = len(unique_members)
    logger.info(f"Big 6 seed: {total_players} unique players to sync journeys")

    update_job(job_id, total=total_combos + total_players,
               progress=total_combos,
               current_player="Starting journey sync")

    current_year = datetime.now().year

    def heartbeat():
        update_job(job_id, current_player=f"Heartbeat ({synced_count} synced)")

    def _mark_player_sync_failure(player_api_id: int, sync_error: str, journey_id: int | None = None):
        """Persist journey sync failure for all cohort members of a player."""
        members = CohortMember.query.filter_by(player_api_id=player_api_id).all()
        for pm in members:
            if journey_id is not None:
                pm.journey_id = journey_id
            pm.journey_synced = False
            pm.journey_sync_error = sync_error
        db.session.commit()

    rate_limiter = RateLimiter(
        per_minute_cap=rate_limit_per_minute or 280,
        per_day_cap=rate_limit_per_day or 7000,
        heartbeat_fn=heartbeat,
    )
    quota_exhausted = False
    synced_count = 0

    for idx, member in enumerate(unique_members):
        if quota_exhausted:
            break
        if idx % 10 == 0 and is_job_cancelled(job_id):
            logger.info("Big 6 seed cancelled during Phase 2 at player %d/%d (%d synced)", idx, total_players, synced_count)
            return {'cancelled': True, 'phase': 'journey_sync', 'players_synced': synced_count, 'cohorts_created': len(cohort_ids)}

        try:
            rate_limiter.wait_if_needed()

            update_job(job_id, progress=total_combos + idx,
                       current_player=f"Journey: {member.player_name}")

            # Call sync_player directly in the subprocess thread.
            # Previous approach used ThreadPoolExecutor for timeout, but
            # timed-out threads leaked DB connections from the pool, eventually
            # exhausting it and hanging the entire subprocess.  The API client
            # already has per-request HTTP timeouts (15s), so individual calls
            # are bounded.
            t0 = time.time()
            journey = None
            sync_error = None
            try:
                journey = journey_service.sync_player(
                    player_api_id=member.player_api_id,
                    heartbeat_fn=heartbeat,
                )
                if journey:
                    sync_error = journey.sync_error
            except Exception as sync_exc:
                elapsed = time.time() - t0
                logger.warning(
                    "Journey sync failed for player %s after %.1fs: %s",
                    member.player_api_id, elapsed, sync_exc,
                )
                db.session.rollback()
                _mark_player_sync_failure(member.player_api_id, str(sync_exc))
                continue

            elapsed = time.time() - t0
            if elapsed > player_timeout:
                logger.warning(
                    "Journey sync slow for player %s: %.1fs (limit %ds)",
                    member.player_api_id, elapsed, player_timeout,
                )

            if journey and not sync_error:
                # Update ALL members with this player_api_id
                all_player_members = CohortMember.query.filter_by(
                    player_api_id=member.player_api_id
                ).all()

                for pm in all_player_members:
                    pm.journey_id = journey.id
                    pm.current_club_api_id = journey.current_club_api_id
                    pm.current_club_name = journey.current_club_name
                    pm.current_level = journey.current_level
                    pm.first_team_debut_season = journey.first_team_debut_season
                    pm.total_first_team_apps = journey.total_first_team_apps
                    pm.total_clubs = journey.total_clubs
                    parent_api_id, parent_club_name = cohort_context.get(pm.cohort_id, (0, ''))
                    pm.current_status = CohortService._derive_status(
                        journey, current_year,
                        parent_api_id=parent_api_id,
                        parent_club_name=parent_club_name,
                    )
                    pm.journey_synced = True
                    pm.journey_sync_error = None

                db.session.commit()
                synced_count += 1
            elif journey and sync_error:
                _mark_player_sync_failure(
                    member.player_api_id,
                    sync_error or "Journey sync returned error",
                    journey_id=journey.id,
                )
            else:
                _mark_player_sync_failure(
                    member.player_api_id,
                    "Journey sync returned no data",
                )

        except RuntimeError as e:
            err_msg = str(e).lower()
            if 'daily api call limit' in err_msg or 'daily quota' in err_msg:
                logger.warning(
                    "Daily API limit reached at player %d/%d (%d synced so far), saving progress",
                    idx + 1, total_players, synced_count,
                )
                quota_exhausted = True
                break
            logger.warning(f"Failed journey sync for player {member.player_api_id}: {e}")
            _mark_player_sync_failure(member.player_api_id, str(e))
        except Exception as e:
            logger.warning(f"Failed journey sync for player {member.player_api_id}: {e}")
            _mark_player_sync_failure(member.player_api_id, str(e))

        if (idx + 1) % 50 == 0:
            logger.info(
                "Journey sync progress: %d/%d (%.0f%%), %d synced",
                idx + 1, total_players, (idx + 1) / total_players * 100, synced_count,
            )

    if quota_exhausted:
        remaining = total_players - (idx + 1)
        logger.warning(
            "Journey sync stopped early: %d/%d completed, %d remaining (re-run to continue)",
            synced_count, total_players, remaining,
        )
    else:
        logger.info("Journey sync complete: %d/%d synced", synced_count, total_players)

    # ── Phase 3: Refresh stats ──
    update_job(job_id, current_player="Refreshing cohort stats")
    for cohort_id in cohort_ids:
        try:
            cohort_service.refresh_cohort_stats(cohort_id)
        except Exception as e:
            logger.warning(f"Failed to refresh stats for cohort {cohort_id}: {e}")

    # Mark cohorts by actual sync coverage.
    now = datetime.now(timezone.utc)
    for cohort_id in cohort_ids:
        try:
            c = db.session.get(AcademyCohort, cohort_id)
            if not c:
                continue
            total_members = CohortMember.query.filter_by(cohort_id=cohort_id).count()
            synced_members = CohortMember.query.filter_by(
                cohort_id=cohort_id,
                journey_synced=True,
            ).count()

            if total_members == 0:
                c.sync_status = 'no_data'
            elif synced_members == total_members:
                c.sync_status = 'complete'
                c.journeys_synced_at = now
            elif synced_members == 0:
                c.sync_status = 'failed'
            else:
                c.sync_status = 'partial'
                c.journeys_synced_at = now
        except Exception as e:
            logger.warning(f"Failed to mark cohort {cohort_id} complete: {e}")
    db.session.commit()

    logger.info(
        "Big 6 seed complete: %d cohorts, %d/%d players synced%s",
        len(cohort_ids), synced_count, total_players,
        " (quota exhausted)" if quota_exhausted else "",
    )
    return {
        'cohorts_created': len(cohort_ids),
        'players_synced': synced_count,
        'players_total': total_players,
        'quota_exhausted': quota_exhausted,
        'combos_attempted': total_combos,
        'combos_skipped_no_youth_team': skipped_no_youth_team,
        'combos_skipped_empty_cohort': skipped_empty_cohorts,
        'resolved_leagues': [l.get('league_id') for l in resolved_leagues],
    }
