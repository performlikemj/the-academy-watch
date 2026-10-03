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


def _first_per_player(rows):
    """Rows arrive in the contact route's target order; the first per player is the target."""
    targets = {}
    for player_id, claim_id, owner_id in rows:
        targets.setdefault(player_id, (claim_id, owner_id))
    return targets


def _operational_program_ids(program_ids) -> set[int]:
    """Batched ``program_is_operational``: approved and not emergency-hidden."""
    import sqlalchemy as sa
    from src.services.club_registry import PROGRAMS_TABLE, _table_columns

    ids = {program_id for program_id in program_ids if program_id is not None}
    if not ids or not {"id", "platform_status", "emergency_hidden"}.issubset(_table_columns(PROGRAMS_TABLE)):
        return set()
    programs = sa.table(PROGRAMS_TABLE, sa.column("id"), sa.column("platform_status"), sa.column("emergency_hidden"))
    statement = sa.select(programs.c.id).where(
        programs.c.id.in_(ids),
        programs.c.platform_status == "approved",
        programs.c.emergency_hidden.is_(False),
    )
    return set(db.session.execute(statement).scalars())


def target_claims(player_ids) -> dict[int, tuple[int, int]]:
    """``{player_id: (claim_id, owner_user_id)}`` — the claim a NEW request would be sent to.

    The batched form of ``routes.contact._target_claim`` plus the conditions
    ``create_contact_request`` then puts on it: the newest approved player
    self-claim (``reviewed_at`` desc, ``id`` desc) of an unsuppressed subject;
    for a club-created player, the claim pinned by the live publication, and
    only while that claim's club program is operational. A player missing from
    the result cannot be asked.
    """
    from src.models.showcase import LocalPlayer
    from src.services.player_suppression import active_local_suppression_exists, without_active_suppression

    ids = _signed_ids(player_ids)
    targets: dict[int, tuple[int, int]] = {}
    approved_player = and_(PlayerProfileClaim.relationship_type == "player", PlayerProfileClaim.status == "approved")
    newest_first = (PlayerProfileClaim.reviewed_at.desc(), PlayerProfileClaim.id.desc())

    api_ids = {player_id for player_id in ids if player_id > 0}
    if api_ids:
        targets.update(
            _first_per_player(
                db.session.query(
                    PlayerProfileClaim.player_api_id, PlayerProfileClaim.id, PlayerProfileClaim.user_account_id
                )
                .filter(
                    PlayerProfileClaim.player_api_id.in_(api_ids),
                    approved_player,
                    without_active_suppression(PlayerProfileClaim.player_api_id),
                )
                .order_by(*newest_first)
                .all()
            )
        )

    local_ids = {-player_id for player_id in ids if player_id < 0}
    if not local_ids:
        return targets
    club_created = {
        row[0]
        for row in db.session.query(LocalPlayer.id).filter(
            LocalPlayer.id.in_(local_ids), LocalPlayer.provenance == "club"
        )
    }
    self_created = local_ids - club_created
    if self_created:
        rows = (
            db.session.query(
                PlayerProfileClaim.local_player_id, PlayerProfileClaim.id, PlayerProfileClaim.user_account_id
            )
            .filter(
                PlayerProfileClaim.local_player_id.in_(self_created),
                approved_player,
                ~active_local_suppression_exists(PlayerProfileClaim.local_player_id),
            )
            .order_by(*newest_first)
            .all()
        )
        targets.update(_first_per_player((-local_id, claim_id, owner_id) for local_id, claim_id, owner_id in rows))
    if club_created:
        from src.models.club_player_publication import ClubPlayerPublication
        from src.services.club_player_publication import enabled, publication_local_ids

        if enabled():
            rows = (
                db.session.query(
                    ClubPlayerPublication.local_player_id,
                    PlayerProfileClaim.id,
                    PlayerProfileClaim.user_account_id,
                    PlayerProfileClaim.club_program_id,
                )
                .join(PlayerProfileClaim, PlayerProfileClaim.id == ClubPlayerPublication.claim_id)
                .filter(
                    ClubPlayerPublication.local_player_id.in_(club_created),
                    ClubPlayerPublication.local_player_id.in_(publication_local_ids()),
                    approved_player,
                )
                .all()
            )
            operational = _operational_program_ids(row[3] for row in rows)
            for local_id, claim_id, owner_id, program_id in rows:
                if program_id in operational:
                    targets[-local_id] = (claim_id, owner_id)
    return targets


def introductions_for(user, player_ids) -> dict[int, dict]:
    """The caller's introduction state per signed player id.

    ``{}`` when the contact rail is off or nobody is signed in; otherwise one
    entry per id. It mirrors what the contact routes enforce, so the UI offers
    exactly what ``POST /contact/requests`` would accept:

    * ``can_ask`` — there is a target claim (``target_claims``), the caller and
      THAT claim's owner have not blocked one another, no request of the caller
      for this player is still active, and no decline is inside its cool-off.
    * the request shown is the caller's newest one that the sent box would
      list: a request is hidden only when ITS OWN claim belongs to a blocked
      account. Another claimant's block, or a rejected / guardian claim by a
      blocked account, hides nothing.
    * a blocked pair reads like any player who cannot be asked — never as a
      missing entry.

    One ``contact_requests`` query for all ids; the other lookups run once per
    response and only when a listed row needs them.
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
    from src.services.user_blocks import block_related_user_ids

    ids = _signed_ids(player_ids)
    if user is None or not ids or not contact_rail_enabled():
        return {}

    rows = (
        ContactRequest.query.filter(ContactRequest.scout_user_id == user.id, ContactRequest.player_api_id.in_(ids))
        .order_by(ContactRequest.created_at.desc(), ContactRequest.id.desc())
        .all()
    )
    targets = target_claims(ids)
    related = block_related_user_ids(user_id=user.id)
    blocked_claim_ids = set()
    if related:
        request_claim_ids = {row.claim_id for row in rows if row.claim_id is not None}
        if request_claim_ids:
            blocked_claim_ids = {
                row[0]
                for row in db.session.query(PlayerProfileClaim.id).filter(
                    PlayerProfileClaim.id.in_(request_claim_ids), PlayerProfileClaim.user_account_id.in_(related)
                )
            }

    now = utcnow()
    cooldown = timedelta(days=decline_cooldown_days())

    def state_of(row):
        expired = request_can_expire(row) and row.expires_at is not None and row.expires_at <= now
        return "expired" if expired else row.status

    latest: dict[int, ContactRequest] = {}
    has_active: set[int] = set()
    ask_again_from: dict[int, object] = {}
    for row in rows:
        # Creation looks at every request of this scout for the player…
        if state_of(row) in ACTIVE_STATES:
            has_active.add(row.player_api_id)
        if row.status == "declined":
            reopens = (row.responded_at or row.created_at) + cooldown
            if reopens >= now and reopens > ask_again_from.get(row.player_api_id, now - cooldown):
                ask_again_from[row.player_api_id] = reopens
        # …while the sent box lists only requests whose own claim is not behind a block.
        if row.claim_id not in blocked_claim_ids:
            latest.setdefault(row.player_api_id, row)

    shown = list(latest.values())
    programs = get_club_programs(
        {row.club_program_id for row in shown if row.routing_mode == ROUTING_CLUB_INCLUDED and row.club_program_id}
    )
    live_club_first = available_club_requests(shown)

    result = {}
    for player_id in ids:
        target = targets.get(player_id)
        can_ask = (
            target is not None
            and target[1] not in related
            and player_id not in has_active
            and player_id not in ask_again_from
        )
        row = latest.get(player_id)
        if row is None:
            result[player_id] = {"state": "none", "can_ask": can_ask}
            continue
        state = state_of(row)
        active = state in ACTIVE_STATES
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
    introductions = introductions_for(viewer, ids)
    for player in players:
        player_id = player.get("player_id")
        player["availability"] = availability.get(player_id)
        if player_id in introductions:
            player["introduction"] = introductions[player_id]
