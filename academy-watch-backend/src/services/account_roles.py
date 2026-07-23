"""Derived account personas backed only by current authoritative grants."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from src.models.funding import ClubProgramManager
from src.models.league import db
from src.models.showcase import PlayerProfileClaim

if TYPE_CHECKING:
    from src.models.league import UserAccount

AccountRole = Literal["scout", "player", "club_manager"]
ACCOUNT_ROLE_PRECEDENCE: tuple[AccountRole, ...] = ("club_manager", "player", "scout")


def derive_account_role(user: UserAccount | None) -> AccountRole:
    """Project the highest-precedence persona; never persist the label itself."""
    roles: set[AccountRole] = {"scout"}
    if user is not None and user.id is not None:
        manager_grant = (
            db.session.query(ClubProgramManager.id)
            .filter(
                ClubProgramManager.user_account_id == user.id,
                ClubProgramManager.status == "active",
            )
            .first()
        )
        if manager_grant is not None:
            roles.add("club_manager")

        player_claim = (
            db.session.query(PlayerProfileClaim.id)
            .filter(
                PlayerProfileClaim.user_account_id == user.id,
                PlayerProfileClaim.relationship_type == "player",
                PlayerProfileClaim.status == "approved",
            )
            .first()
        )
        if player_claim is not None:
            roles.add("player")

    return next(role for role in ACCOUNT_ROLE_PRECEDENCE if role in roles)
