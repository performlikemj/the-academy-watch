"""Derived trust state backed by current moderation records."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.models.league import db
from src.models.trust import ScoutVerification

if TYPE_CHECKING:
    from src.models.league import UserAccount


def is_verified_scout(user: UserAccount | None) -> bool:
    """Return whether ``user`` currently has an approved verification.

    The value is intentionally queried from the authoritative review row and
    is never persisted as a role flag on ``user_accounts``.
    """
    if user is None or user.id is None:
        return False
    return (
        db.session.query(ScoutVerification.id)
        .filter(
            ScoutVerification.user_account_id == user.id,
            ScoutVerification.status == "approved",
        )
        .first()
        is not None
    )


__all__ = ["is_verified_scout"]
