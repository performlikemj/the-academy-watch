"""Self-healing transfer window service.

Detects loan club changes for tracked players by re-querying API-Football,
updates statuses, and optionally cascades fixture syncs for affected players.

Uses TrackedPlayer as the primary model — fixture syncs are cascaded
per-player via _sync_player_club_fixtures using TrackedPlayer.current_club_api_id
directly, without depending on AcademyPlayer rows.
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import text
from src.api_football_client import APIFootballClient
from src.models.journey import PlayerJourney
from src.models.league import Team, db
from src.models.tracked_player import TrackedPlayer
from src.services.journey_sync import JourneySyncService
from src.utils.academy_classifier import (
    _get_latest_season,
    classify_tracked_player,
    flatten_transfers,
)

logger = logging.getLogger(__name__)

# Budget on how many orphaned rows may be requeued for a force_full journey
# re-sync. Each requeued row costs ~7s + several API-Football calls, so an
# unbounded requeue (e.g. after a mass-orphaning incident) would blow the
# nightly job's runtime and API quota.
#
# This is the DEFAULT per-call cap. The nightly job runners iterate ~137 teams
# and call refresh_and_heal once per team, so a per-call cap would multiply into
# 50×137 re-syncs a night — the exact quota/runtime blow-up the cap is meant to
# prevent. Those runners therefore pass an ``orphan_budget`` that they DECREMENT
# across teams, making the ceiling job-global (this constant) rather than
# per-team. Callers that fire a single refresh (admin endpoint, team-verify,
# newsletter pre-refresh) omit ``orphan_budget`` and get this cap for that call.
#
# Genuinely-healable orphans reactivate and leave the pool; non-healable rows
# have their updated_at touched on the skipped requeue so the oldest-touched
# ordering ROUND-ROBINS through the backlog instead of pinning the same stuck
# tail every night — so the budget rotates fairly and the backlog drains.
MAX_ORPHAN_REQUEUE = 50


def refresh_and_heal(team_id=None, resync_journeys=True, dry_run=False, cascade_fixtures=True, orphan_budget=None):
    """Re-derive statuses for tracked players, detecting loan club changes.

    Args:
        team_id: Optional team DB ID to limit refresh to a single team.
        resync_journeys: If True, re-sync journey data from API-Football first.
        dry_run: If True, do not commit changes or cascade fixture syncs.
        cascade_fixtures: If True, sync fixtures for players whose loan club
            changed. Set False for admin endpoint (preserves old behavior).
        orphan_budget: Max orphan rows this call may requeue for a force_full
            journey re-sync. None → the per-call default MAX_ORPHAN_REQUEUE.
            The nightly per-team job loops pass a shrinking budget so the
            ceiling stays job-global (see MAX_ORPHAN_REQUEUE) rather than
            multiplying by the team count.

    Returns:
        dict with keys: total, updated, journeys_resynced, players_changed,
        fixture_syncs_triggered, orphans_requeued.

    Note: Fixture syncs are independent — status changes persist even if
    a fixture sync fails for an individual player.
    """
    orphan_cap = MAX_ORPHAN_REQUEUE if orphan_budget is None else max(int(orphan_budget), 0)
    query = TrackedPlayer.query.filter_by(is_active=True)
    if team_id:
        query = query.filter_by(team_id=team_id)

    players = query.all()

    # ── Orphan self-heal ──
    # Requeue is_active=false rows that were orphaned by an earlier transient
    # empty computation so a transfers-fed journey re-sync can reactivate them
    # via the upsert's reactivation branch (invariant #10 — status only changes
    # through the transfers-fed sync). The journey upsert's reactivation branch
    # only fires during a full journey re-sync, and the heal historically looked
    # at ACTIVE rows only, so orphans were never revisited.
    #
    # Bounded and TERMINAL by construction, so the nightly job doesn't force_full
    # re-sync a never-healable tail forever (API-Football quota + runtime):
    #   1. Journey-attribution gate — only requeue a row whose LINKED journey
    #      STILL attributes the row's academy club IN-WINDOW. Those are the only
    #      rows the upsert can actually reactivate; graveyard rows (no journey /
    #      journey no longer attributes the club / aged-out season) are excluded,
    #      and once an evidenced re-sync overwrites the attribution or the season
    #      ages out, a row drops out of the set (terminal). This also catches the
    #      legacy owning-club orphans (the canonical Gore row) that carry NO row-
    #      local season, which the old row-local filter silently missed.
    #   2. MAX_ORPHAN_REQUEUE cap, oldest-touched first, so a mass orphaning
    #      can't blow up a single run.
    # Reactivation requires a journey re-sync, so this is gated on resync_journeys;
    # scoped by team_id like the active set.
    orphans = []
    if resync_journeys and orphan_cap > 0:
        from src.utils.academy_window import academy_window_start, is_within_academy_window

        window_start = academy_window_start()
        candidate_q = TrackedPlayer.query.filter(
            TrackedPlayer.is_active.is_(False),
            TrackedPlayer.pinned_parent.isnot(True),
            TrackedPlayer.data_source != "manual",
            TrackedPlayer.player_api_id.isnot(None),
            db.or_(
                TrackedPlayer.last_academy_season >= window_start,
                TrackedPlayer.status == "academy",
                # Legacy owning-club orphans were created without row-local season
                # evidence; keep them in the candidate net and let the journey
                # gate below decide.
                TrackedPlayer.data_source == "owning-club",
            ),
        ).order_by(TrackedPlayer.updated_at.asc())
        if team_id:
            candidate_q = candidate_q.filter(TrackedPlayer.team_id == team_id)
        candidates = candidate_q.all()

        if candidates:
            cand_team_ids = {tp.team_id for tp in candidates}
            teams_by_id = {t.id: t for t in Team.query.filter(Team.id.in_(cand_team_ids)).all()}
            cand_api_ids = {tp.player_api_id for tp in candidates}
            journeys_by_api = {
                j.player_api_id: j
                for j in PlayerJourney.query.filter(PlayerJourney.player_api_id.in_(cand_api_ids)).all()
            }
            for tp in candidates:
                if len(orphans) >= orphan_cap:
                    break
                parent = teams_by_id.get(tp.team_id)
                journey = journeys_by_api.get(tp.player_api_id)
                if not parent or not journey:
                    continue
                if parent.team_id not in set(journey.academy_club_ids or []):
                    continue
                season = (journey.academy_last_seasons or {}).get(str(parent.team_id))
                window_status = "academy" if tp.status == "academy" else None
                if is_within_academy_window(season, status=window_status, birth_date=journey.birth_date):
                    orphans.append(tp)

        if orphans:
            logger.info(
                "transfer-heal: requeuing %d journey-attributed in-window orphan row(s) for reactivation (budget %d)",
                len(orphans),
                orphan_cap,
            )
            players = players + orphans

    updated = 0
    journeys_resynced = 0
    players_changed = []

    # Optionally set up journey sync service
    journey_svc = None
    if resync_journeys:
        journey_svc = JourneySyncService()

    # Batch pre-fetch transfers
    api_client = APIFootballClient()
    player_api_ids = [tp.player_api_id for tp in players if tp.player_api_id]
    raw_transfers_map = api_client.batch_get_player_transfers(player_api_ids)
    transfers_map = {pid: flatten_transfers(raw) for pid, raw in raw_transfers_map.items()}

    # Batch pre-fetch squads for loan + parent clubs.
    # Squads that fail to fetch are tracked in `failed_squad_clubs` so we can
    # SKIP status classification for any player whose classification would
    # otherwise depend on a silently-missing squad. Previously a single
    # failed club would just be a warning and the squad cross-reference
    # rule inside classify_tracked_player would silently not fire for any
    # player at that club — an exactly-the-kind-of-silent-miss that let the
    # O. Hammond class of bug persist. Now those players are left untouched.
    squad_members_by_club = {}
    failed_squad_clubs: set[int] = set()
    loan_club_ids = {tp.current_club_api_id for tp in players if tp.current_club_api_id}
    parent_club_ids = set()
    _team_cache = {}
    for tp in players:
        if tp.team_id not in _team_cache:
            _team_cache[tp.team_id] = Team.query.get(tp.team_id)
        pt = _team_cache[tp.team_id]
        if pt:
            parent_club_ids.add(pt.team_id)
    for club_id in loan_club_ids | parent_club_ids:
        try:
            squad = api_client.get_team_players(club_id)
            squad_members_by_club[club_id] = {
                int(e["player"]["id"]) for e in squad if e and e.get("player", {}).get("id")
            }
        except Exception as exc:
            failed_squad_clubs.add(club_id)
            logger.warning(
                "transfer-heal: squad fetch failed for club %d: %s — "
                "classification will be SKIPPED for players at this club",
                club_id,
                exc,
            )

    if failed_squad_clubs:
        logger.warning(
            "transfer-heal: %d squad fetch(es) failed (clubs=%s); affected "
            "players will have their status left untouched.",
            len(failed_squad_clubs),
            sorted(failed_squad_clubs),
        )

    # Also track players whose transfer batch came back empty in a way that
    # suggests a fetch failure rather than a genuinely empty history. We
    # cannot distinguish a real empty list from a failed fetch for a
    # batch-call, so we only flag players we received NO key for at all.
    transfer_fetch_missing = {
        tp.player_api_id for tp in players if tp.player_api_id and tp.player_api_id not in raw_transfers_map
    }
    if transfer_fetch_missing:
        logger.warning(
            "transfer-heal: %d player(s) missing from transfer batch response — "
            "their classification will be SKIPPED to avoid basing it on partial data. "
            "player_api_ids=%s",
            len(transfer_fetch_missing),
            sorted(transfer_fetch_missing),
        )

    # Process each player
    skipped_by_failed_prefetch = 0
    for tp in players:
        journey = None
        was_inactive = not tp.is_active

        # Re-sync journey from API-Football if requested
        if resync_journeys and journey_svc and tp.player_api_id:
            try:
                journey = journey_svc.sync_player(tp.player_api_id, force_full=True)
                if journey:
                    journeys_resynced += 1
                    if not tp.journey_id:
                        tp.journey_id = journey.id
            except Exception as sync_err:
                logger.warning(
                    "transfer-heal: journey resync failed for player %d: %s",
                    tp.player_api_id,
                    sync_err,
                )

        # Orphan requeue that the re-sync could NOT reactivate (still inactive
        # after the journey upsert ran — e.g. the API coverage gap persists) must
        # not have its status rewritten or its fixtures cascaded: it is not
        # displayed anywhere. Writing to it and appending it to players_changed
        # would fire a fixture sync for a hidden player. Leave it for a future
        # run where the re-sync actually has evidence to revive it.
        if was_inactive and not tp.is_active:
            # Rotate the queue: this row keeps its old updated_at otherwise, so
            # the oldest-touched candidate ordering (ORDER BY updated_at ASC)
            # would re-select the SAME never-healable rows first every night —
            # perpetual force_full churn that starves healable orphans behind
            # them once a team accumulates a budget's worth of stuck rows. Touch
            # updated_at so the backlog round-robins and drains instead.
            tp.updated_at = datetime.now(UTC)
            continue

        if not journey:
            if tp.journey_id:
                journey = db.session.get(PlayerJourney, tp.journey_id)
            if not journey:
                journey = PlayerJourney.query.filter_by(player_api_id=tp.player_api_id).first()

        if not journey:
            continue

        parent_team = _team_cache.get(tp.team_id) or Team.query.get(tp.team_id)
        if not parent_team:
            continue

        # Skip classification if any of the data the classifier needs for
        # this specific player failed to pre-fetch. Running the classifier
        # against a known-partial squad dict or missing transfer list is
        # exactly how wrong statuses silently persist — we prefer leaving
        # the row untouched over writing a guess.
        player_parent_id = parent_team.team_id
        player_loan_id = tp.current_club_api_id
        if (
            player_parent_id in failed_squad_clubs
            or (player_loan_id and player_loan_id in failed_squad_clubs)
            or tp.player_api_id in transfer_fetch_missing
        ):
            skipped_by_failed_prefetch += 1
            logger.info(
                "transfer-heal: skipping player %d (%s) — prefetch incomplete "
                "(parent_squad_failed=%s loan_squad_failed=%s transfers_missing=%s)",
                tp.player_api_id,
                tp.player_name,
                player_parent_id in failed_squad_clubs,
                bool(player_loan_id and player_loan_id in failed_squad_clubs),
                tp.player_api_id in transfer_fetch_missing,
            )
            continue

        new_status, new_loan_id, new_loan_name = classify_tracked_player(
            current_club_api_id=journey.current_club_api_id,
            current_club_name=journey.current_club_name,
            current_level=journey.current_level,
            parent_api_id=parent_team.team_id,
            parent_club_name=parent_team.name,
            transfers=transfers_map.get(tp.player_api_id),
            player_api_id=tp.player_api_id,
            api_client=api_client,
            latest_season=_get_latest_season(
                journey.id,
                parent_api_id=parent_team.team_id,
                parent_club_name=parent_team.name,
            ),
            squad_members_by_club=squad_members_by_club,
        )

        # Pinned players: skip all automated field changes.
        # Journey data was already resynced above, but status/loan/level
        # fields are frozen until explicitly unpinned.
        if tp.pinned_parent:
            logger.info(
                "transfer-heal: skipping status update for pinned player %d (%s)",
                tp.player_api_id,
                tp.player_name,
            )
            continue

        changed = False
        old_loan_id = tp.current_club_api_id

        if tp.status != new_status:
            tp.status = new_status
            changed = True
        if tp.current_club_api_id != new_loan_id:
            tp.current_club_api_id = new_loan_id
            changed = True
        if tp.current_club_name != new_loan_name:
            tp.current_club_name = new_loan_name
            changed = True
        if journey.current_level and tp.current_level != journey.current_level:
            tp.current_level = journey.current_level
            changed = True

        # Resolve and write the local Team FK alongside the API id, so
        # downstream consumers that prefer current_club_db_id (e.g. radar
        # comparison resolution, team-loans-out filters, journey badges)
        # don't have to do their own join. None is allowed when the API
        # id points at a club we haven't ingested locally yet.
        new_db_id = None
        if new_loan_id:
            target_team = Team.query.filter_by(team_id=new_loan_id).first()
            new_db_id = target_team.id if target_team else None
        if tp.current_club_db_id != new_db_id:
            tp.current_club_db_id = new_db_id
            changed = True

        if changed:
            updated += 1
            # Track loan club changes for fixture sync cascade
            if new_loan_id and new_loan_id != old_loan_id:
                players_changed.append(
                    {
                        "player_api_id": tp.player_api_id,
                        "player_name": tp.player_name,
                        "team_id": tp.team_id,
                        "old_current_club_api_id": old_loan_id,
                        "new_current_club_api_id": new_loan_id,
                        "new_loan_club": new_loan_name,
                    }
                )

    if not dry_run:
        db.session.commit()
    else:
        db.session.rollback()

    # Cascade fixture syncs per changed player using TrackedPlayer data directly
    fixture_syncs_triggered = 0
    if not dry_run and cascade_fixtures and players_changed:
        from src.routes.api import _sync_player_club_fixtures
        from src.utils.academy_window import current_stats_season

        # Transfer heal fetches fixtures for the UPCOMING season — use the pure
        # calendar season (NO latest-with-data fallback) so a newly-started
        # season actually gets synced instead of being pinned to old data.
        season = current_stats_season()

        for pc in players_changed:
            try:
                synced = _sync_player_club_fixtures(
                    player_id=pc["player_api_id"],
                    loan_team_api_id=pc["new_current_club_api_id"],
                    season=season,
                    player_name=pc.get("player_name"),
                )
                fixture_syncs_triggered += 1
                logger.info(
                    "transfer-heal: synced %d fixtures for player %d (%s) at new club %s (api_id=%d)",
                    synced,
                    pc["player_api_id"],
                    pc.get("player_name"),
                    pc["new_loan_club"],
                    pc["new_current_club_api_id"],
                )
            except Exception as exc:
                logger.error(
                    "transfer-heal: fixture sync failed for player %d at club %d: %s",
                    pc["player_api_id"],
                    pc["new_current_club_api_id"],
                    exc,
                )

    # Clean up deprecated owning-club duplicates. The academy-origin row is
    # the canonical one (clubs track their OWN academy products); an
    # owning-club duplicate must never supersede it — scout/teams surfaces
    # exclude owning-club rows entirely, so retiring the academy row here
    # would make the player invisible everywhere.
    if not dry_run:
        try:
            stale = db.session.execute(
                text("""
                UPDATE tracked_players SET is_active = false
                WHERE id IN (
                    SELECT b.id FROM tracked_players a
                    JOIN tracked_players b ON a.player_api_id = b.player_api_id
                    WHERE a.is_active = true AND b.is_active = true
                      AND a.id != b.id
                      AND a.data_source != 'owning-club'
                      AND b.data_source = 'owning-club'
                )
            """)
            )
            stale_count = stale.rowcount
            if stale_count:
                db.session.commit()
                logger.info("transfer-heal: deactivated %d owning-club duplicate rows", stale_count)
        except Exception as exc:
            logger.warning("transfer-heal: stale row cleanup failed: %s", exc)

    return {
        "total": len(players),
        "updated": updated,
        "journeys_resynced": journeys_resynced,
        "players_changed": players_changed,
        "fixture_syncs_triggered": fixture_syncs_triggered,
        "skipped_by_failed_prefetch": skipped_by_failed_prefetch,
        "failed_squad_clubs": sorted(failed_squad_clubs),
        "orphans_requeued": len(orphans),
    }
