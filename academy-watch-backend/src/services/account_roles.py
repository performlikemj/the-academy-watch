"""Derived account personas for signed-in users.

The persona is a projection of authoritative approvals, not stored account
state. Keeping that distinction here prevents the auth payload from drifting
away from claim/grant revocations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from src.models.league import db
from src.models.showcase import PlayerProfileClaim

if TYPE_CHECKING:
    from src.models.league import UserAccount

AccountRole = Literal["scout", "player", "club_manager"]

# Highest-authority persona wins. F2 will add ``club_manager`` to the derived
# role set below when its approved club-grant model exists; F1 deliberately
# does not query or invent that source.
ACCOUNT_ROLE_PRECEDENCE: tuple[AccountRole, ...] = ("club_manager", "player", "scout")


def derive_account_role(user: UserAccount | None) -> AccountRole:
    """Return the user's highest-precedence persona from approved records."""
    derived_roles: set[AccountRole] = {"scout"}
    if user is not None and user.id is not None:
        approved_player_claim = (
            db.session.query(PlayerProfileClaim.id)
            .filter(
                PlayerProfileClaim.user_account_id == user.id,
                PlayerProfileClaim.relationship_type == "player",
                PlayerProfileClaim.status == "approved",
            )
            .first()
        )
        if approved_player_claim is not None:
            derived_roles.add("player")

    return next(role for role in ACCOUNT_ROLE_PRECEDENCE if role in derived_roles)
