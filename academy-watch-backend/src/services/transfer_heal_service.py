"""Self-healing transfer window service.

Detects loan club changes for tracked players by re-querying API-Football,
updates statuses, and optionally cascades fixture syncs for affected players.

Uses TrackedPlayer as the primary model — fixture syncs are cascaded
per-player via _sync_player_club_fixtures using TrackedPlayer.loan_club_api_id
directly, without depending on AcademyPlayer rows.
"""

import logging
from datetime import datetime, timezone

from src.models.league import db, Team
from src.models.tracked_player import TrackedPlayer
from src.models.journey import PlayerJourney
from src.api_football_client import APIFootballClient
from src.services.journey_sync import JourneySyncService
from src.utils.academy_classifier import (
    classify_tracked_player,
    flatten_transfers,
    _get_latest_season,
)

logger = logging.getLogger(__name__)


def refresh_and_heal(team_id=None, resync_journeys=True, dry_run=False,
                     cascade_fixtures=True):
    """Re-derive statuses for tracked players, detecting loan club changes.

    Args:
        team_id: Optional team DB ID to limit refresh to a single team.
        resync_journeys: If True, re-sync journey data from API-Football first.
        dry_run: If True, do not commit changes or cascade fixture syncs.
        cascade_fixtures: If True, sync fixtures for players whose loan club
            changed. Set False for admin endpoint (preserves old behavior).

    Returns:
        dict with keys: total, updated, journeys_resynced, players_changed,
        fixture_syncs_triggered.

    Note: Fixture syncs are independent — status changes persist even if
    a fixture sync fails for an individual player.
    """
    query = TrackedPlayer.query.filter_by(is_active=True)
    if team_id:
        query = query.filter_by(team_id=team_id)

    players = query.all()

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
    transfers_map = {
        pid: flatten_transfers(raw)
        for pid, raw in raw_transfers_map.items()
    }

    # Batch pre-fetch squads for loan + parent clubs
    squad_members_by_club = {}
    loan_club_ids = {tp.loan_club_api_id for tp in players if tp.loan_club_api_id}
    parent_club_ids = set()
    _team_cache = {}
    for tp in players:
        if tp.team_id not in _team_cache:
            _team_cache[tp.team_id] = Team.query.get(tp.team_id)
        pt = _team_cache[tp.team_id]
        if pt:
            parent_club_ids.add(pt.team_id)
    for club_id in (loan_club_ids | parent_club_ids):
        try:
            squad = api_client.get_team_players(club_id)
            squad_members_by_club[club_id] = {
                int(e['player']['id']) for e in squad
                if e and e.get('player', {}).get('id')
            }
        except Exception as exc:
            logger.warning('Squad fetch failed for club %d: %s', club_id, exc)

    # Process each player
    for tp in players:
        journey = None

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
                    'transfer-heal: journey resync failed for player %d: %s',
                    tp.player_api_id, sync_err,
                )

        if not journey:
            if tp.journey_id:
                journey = db.session.get(PlayerJourney, tp.journey_id)
            if not journey:
                journey = PlayerJourney.query.filter_by(
                    player_api_id=tp.player_api_id
                ).first()

        if not journey:
            continue

        parent_team = _team_cache.get(tp.team_id) or Team.query.get(tp.team_id)
        if not parent_team:
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
                'transfer-heal: skipping status update for pinned player %d (%s)',
                tp.player_api_id, tp.player_name,
            )
            continue

        changed = False
        old_loan_id = tp.loan_club_api_id

        if tp.status != new_status:
            tp.status = new_status
            changed = True
        if tp.loan_club_api_id != new_loan_id:
            tp.loan_club_api_id = new_loan_id
            changed = True
        if tp.loan_club_name != new_loan_name:
            tp.loan_club_name = new_loan_name
            changed = True
        if journey.current_level and tp.current_level != journey.current_level:
            tp.current_level = journey.current_level
            changed = True

        if changed:
            updated += 1
            # Track loan club changes for fixture sync cascade
            if new_loan_id and new_loan_id != old_loan_id:
                players_changed.append({
                    'player_api_id': tp.player_api_id,
                    'player_name': tp.player_name,
                    'team_id': tp.team_id,
                    'old_loan_club_api_id': old_loan_id,
                    'new_loan_club_api_id': new_loan_id,
                    'new_loan_club': new_loan_name,
                })

    if not dry_run:
        db.session.commit()
    else:
        db.session.rollback()

    # Cascade fixture syncs per changed player using TrackedPlayer data directly
    fixture_syncs_triggered = 0
    if not dry_run and cascade_fixtures and players_changed:
        from src.routes.api import _sync_player_club_fixtures
        now = datetime.now(timezone.utc)
        season = now.year if now.month >= 8 else now.year - 1

        for pc in players_changed:
            try:
                synced = _sync_player_club_fixtures(
                    player_id=pc['player_api_id'],
                    loan_team_api_id=pc['new_loan_club_api_id'],
                    season=season,
                    player_name=pc.get('player_name'),
                )
                fixture_syncs_triggered += 1
                logger.info(
                    'transfer-heal: synced %d fixtures for player %d (%s) '
                    'at new club %s (api_id=%d)',
                    synced, pc['player_api_id'], pc.get('player_name'),
                    pc['new_loan_club'], pc['new_loan_club_api_id'],
                )
            except Exception as exc:
                logger.error(
                    'transfer-heal: fixture sync failed for player %d at club %d: %s',
                    pc['player_api_id'], pc['new_loan_club_api_id'], exc,
                )

    return {
        'total': len(players),
        'updated': updated,
        'journeys_resynced': journeys_resynced,
        'players_changed': players_changed,
        'fixture_syncs_triggered': fixture_syncs_triggered,
    }
