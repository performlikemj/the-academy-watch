"""Derived existing emergency state for NEW public reads; no suppression writes.

Existing holds continue to apply when rollout flags are switched off. Only the
new admin mutation endpoints are rollout gated; legacy callers are unchanged.
"""

import sqlalchemy as sa
from sqlalchemy.orm import aliased
from src.models.funding import ClubProgram, ClubRosterMember
from src.models.league import Team, db
from src.models.showcase import LocalClub, LocalPlayer, PlayerClubAffiliation, PlayerProfileClaim
from src.models.tracked_player import TrackedPlayer


def club_publication_hold_filter(program_id):
    """Correlated SQL predicate: a program is under an emergency hold."""
    return sa.exists(
        sa.select(ClubProgram.id).where(ClubProgram.id == program_id, ClubProgram.emergency_hidden.is_(True))
    )


def club_publication_held(program_id) -> bool:
    return bool(db.session.query(club_publication_hold_filter(program_id)).scalar())


def subject_publication_hold_filter(signed_id):
    """Whole-page hold if ANY linked program is hidden, including API aliases.

    Links: origin, roster, approved claim routing, approved team affiliation and
    tracked parent/current club. This only derives state; it never lifts a
    player's independent suppression. Private staff access is not granted here.
    """
    local_keys = aliased(LocalPlayer)
    origin = aliased(LocalPlayer)
    local_ids = (
        sa.select(local_keys.id)
        .where(sa.or_(local_keys.api_player_id == signed_id, local_keys.id == -signed_id))
        .correlate_except(local_keys)
    )
    linked = sa.or_(
        sa.exists(
            sa.select(origin.id)
            .where(origin.id.in_(local_ids), origin.origin_program_id == ClubProgram.id)
            .correlate_except(origin)
        ),
        sa.exists(
            sa.select(ClubRosterMember.id)
            .where(
                ClubRosterMember.program_id == ClubProgram.id,
                sa.or_(ClubRosterMember.player_api_id == signed_id, ClubRosterMember.local_player_id.in_(local_ids)),
            )
            .correlate_except(ClubRosterMember)
        ),
        sa.exists(
            sa.select(PlayerProfileClaim.id)
            .where(
                PlayerProfileClaim.club_program_id == ClubProgram.id,
                PlayerProfileClaim.status == "approved",
                sa.or_(
                    PlayerProfileClaim.player_api_id == signed_id, PlayerProfileClaim.local_player_id.in_(local_ids)
                ),
            )
            .correlate_except(PlayerProfileClaim)
        ),
        sa.exists(
            sa.select(PlayerClubAffiliation.id)
            .where(
                PlayerClubAffiliation.status == "approved",
                sa.or_(
                    PlayerClubAffiliation.team_api_id == ClubProgram.team_api_id,
                    PlayerClubAffiliation.local_club_id.in_(
                        sa.select(LocalClub.id)
                        .where(LocalClub.api_team_id == ClubProgram.team_api_id)
                        .correlate_except(LocalClub)
                    ),
                ),
                sa.or_(
                    PlayerClubAffiliation.player_api_id == signed_id,
                    PlayerClubAffiliation.local_player_id.in_(local_ids),
                ),
            )
            .correlate_except(PlayerClubAffiliation)
        ),
        sa.exists(
            sa.select(TrackedPlayer.id)
            .outerjoin(Team, Team.id == TrackedPlayer.team_id)
            .where(
                TrackedPlayer.player_api_id == signed_id,
                sa.or_(
                    Team.team_id == ClubProgram.team_api_id,
                    TrackedPlayer.current_club_api_id == ClubProgram.team_api_id,
                ),
            )
            .correlate_except(TrackedPlayer, Team)
        ),
    )
    return sa.exists(
        sa.select(ClubProgram.id).where(ClubProgram.emergency_hidden.is_(True), linked).correlate_except(ClubProgram)
    )


def subject_publication_held(subject) -> bool:
    signed_id = getattr(subject, "signed_id", subject)
    if isinstance(signed_id, bool) or not isinstance(signed_id, int) or not signed_id:
        return True
    return bool(db.session.query(subject_publication_hold_filter(signed_id)).scalar())
