"""Card fields for the scout desk and the watchlist.

Read-only projections, each batched over the rows of one response (never one
query per row), on top of rules that already exist elsewhere:

* ``contactable_filter`` — the SQL form of the desk's ``contactable`` flag, so
  "Open to an introduction" filters before counting and paging.
* ``availability_by_player`` — the availability word of an APPROVED showcase
  profile (the same field the player's public page prints).
* ``introductions_for`` — where the caller's OWN introduction to each player
  stands, and whether the contact rules would let them ask (again).

Nothing here writes: a request that is past its expiry is reported as expired,
the row itself is still expired by the contact routes.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import and_, exists, or_
from src.models.contact import ContactRequest
from src.models.league import db
from src.models.showcase import PlayerProfileClaim, PlayerShowcaseProfile

AVAILABILITY_VALUES = frozenset({"open_to_moves", "not_looking", "trial_available"})
ACTIVE_STATES = frozenset({"pending", "accepted"})


def contactable_filter(player_id_column):
    """Rows whose player holds an approved self-claim (same set as the ``contactable`` flag)."""
    return exists().where(
        and_(
            PlayerProfileClaim.relationship_type == "player",
            PlayerProfileClaim.status == "approved",
            or_(
                PlayerProfileClaim.player_api_id == player_id_column,
                and_(player_id_column < 0, PlayerProfileClaim.local_player_id == -player_id_column),
            ),
        )
    )


def _signed_ids(player_ids) -> set[int]:
    return {int(player_id) for player_id in player_ids if player_id}


def availability_by_player(player_ids) -> dict[int, str]:
    """Published availability per signed player id — approved profiles only (one query)."""
    ids = _signed_ids(player_ids)
    if not ids:
        return {}
    api_ids = {player_id for player_id in ids if player_id > 0}
    local_ids = {-player_id for player_id in ids if player_id < 0}
    subjects = []
    if api_ids:
        subjects.append(
            and_(PlayerShowcaseProfile.player_api_id.in_(api_ids), PlayerShowcaseProfile.local_player_id.is_(None))
        )
    if local_ids:
        subjects.append(
            and_(PlayerShowcaseProfile.local_player_id.in_(local_ids), PlayerShowcaseProfile.player_api_id.is_(None))
        )
    rows = (
        db.session.query(
            PlayerShowcaseProfile.player_api_id,
            PlayerShowcaseProfile.local_player_id,
            PlayerShowcaseProfile.availability,
        )
        .filter(
            PlayerShowcaseProfile.status == "approved",
            PlayerShowcaseProfile.availability.isnot(None),
            or_(*subjects),
        )
        .all()
    )
    return {
        (-local_player_id if local_player_id is not None else player_api_id): availability
        for player_api_id, local_player_id, availability in rows
        if availability in AVAILABILITY_VALUES
    }


def _iso(value):
    return value.isoformat() if value is not None else None


def _players_behind_a_block(user_id: int, ids: set[int]) -> set[int]:
    """Players whose claimant and the caller have blocked one another (either direction)."""
    from src.services.user_blocks import block_related_user_ids

    related = block_related_user_ids(user_id=user_id)
    if not related:
        return set()
    local_ids = {-player_id for player_id in ids if player_id < 0}
    rows = (
        db.session.query(PlayerProfileClaim.player_api_id, PlayerProfileClaim.local_player_id)
        .filter(
            PlayerProfileClaim.user_account_id.in_(related),
            or_(PlayerProfileClaim.player_api_id.in_(ids), PlayerProfileClaim.local_player_id.in_(local_ids)),
        )
        .all()
    )
    hidden = set()
    for player_api_id, local_player_id in rows:
        if player_api_id is not None:
            hidden.add(player_api_id)
        if local_player_id is not None:
            hidden.add(-local_player_id)
    return hidden


def introductions_for(user, player_ids, *, contactable_ids=frozenset()) -> dict[int, dict]:
    """The caller's introduction state per signed player id.

    ``{}`` when the contact rail is off or nobody is signed in. A player behind a
    block is left out entirely (the contact routes hide those requests too).
    One ``contact_requests`` query for all ids; the club-name and club-first
    lookups run once per response, and only when a listed request needs them.
    """
    from src.services.club_player_publication import available_club_requests
    from src.services.club_registry import get_club_programs
    from src.services.contact import (
        ROUTING_CLUB_INCLUDED,
        contact_rail_enabled,
        decline_cooldown_days,
        request_can_expire,
        utcnow,
    )

    ids = _signed_ids(player_ids)
    if user is None or not ids or not contact_rail_enabled():
        return {}

    hidden = _players_behind_a_block(user.id, ids)
    rows = (
        ContactRequest.query.filter(ContactRequest.scout_user_id == user.id, ContactRequest.player_api_id.in_(ids))
        .order_by(ContactRequest.created_at.desc(), ContactRequest.id.desc())
        .all()
    )
    now = utcnow()
    cooldown = timedelta(days=decline_cooldown_days())
    latest: dict[int, ContactRequest] = {}
    ask_again_from: dict[int, object] = {}
    for row in rows:
        latest.setdefault(row.player_api_id, row)
        if row.status == "declined":
            reopens = (row.responded_at or row.created_at) + cooldown
            if reopens >= now and reopens > ask_again_from.get(row.player_api_id, now - cooldown):
                ask_again_from[row.player_api_id] = reopens

    shown = [row for player_id, row in latest.items() if player_id not in hidden]
    programs = get_club_programs(
        {row.club_program_id for row in shown if row.routing_mode == ROUTING_CLUB_INCLUDED and row.club_program_id}
    )
    live_club_first = available_club_requests(shown)

    result = {}
    for player_id in ids - hidden:
        row = latest.get(player_id)
        state = "none"
        if row is not None:
            expired = request_can_expire(row) and row.expires_at is not None and row.expires_at <= now
            state = "expired" if expired else row.status
        active = state in ACTIVE_STATES
        can_ask = player_id in contactable_ids and not active and player_id not in ask_again_from
        if row is None:
            result[player_id] = {"state": "none", "can_ask": can_ask}
            continue
        club_included = row.routing_mode == ROUTING_CLUB_INCLUDED
        # A club-first thread is only reachable while its publication is live.
        closed = active and bool(row.club_first) and row.id not in live_club_first
        club_pending = club_included and row.club_consent_status == "pending"
        waiting_on = None
        if state == "pending":
            waiting_on = "club" if club_pending and row.club_first else "club_and_player" if club_pending else "player"
        elif state == "accepted" and club_included and row.club_consent_status != "granted":
            waiting_on = "club"
        program = programs.get(row.club_program_id) if club_included else None
        result[player_id] = {
            "state": state,
            "request_id": row.id,
            "created_at": _iso(row.created_at),
            "responded_at": _iso(row.responded_at),
            "expires_at": _iso(row.expires_at),
            "via_club": program.get("name") if program else None,
            "waiting_on": None if closed else waiting_on,
            "conversation_open": state == "accepted" and waiting_on is None and not closed,
            "declined_by": (
                ("club" if row.club_consent_status == "declined" else "player") if state == "declined" else None
            ),
            "closed": closed,
            "can_ask": can_ask,
            "ask_again_from": _iso(ask_again_from.get(player_id)),
        }
    return result


def attach_desk_card_fields(players: list[dict], *, viewer=None) -> None:
    """Add ``availability`` and, for a signed-in caller, ``introduction`` to desk rows."""
    ids = [player.get("player_id") for player in players]
    availability = availability_by_player(ids)
    contactable = {player["player_id"] for player in players if player.get("contactable")}
    introductions = introductions_for(viewer, ids, contactable_ids=contactable)
    for player in players:
        player_id = player.get("player_id")
        player["availability"] = availability.get(player_id)
        if player_id in introductions:
            player["introduction"] = introductions[player_id]
