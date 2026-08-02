"""Shared user-block predicates used by contact enforcement."""

from collections.abc import Iterable

from src.models.league import db
from src.models.user_block import UserBlock


def user_block_exists(*, blocker_user_id: int, blocked_user_id: int) -> bool:
    """Return whether ``blocker_user_id`` currently blocks ``blocked_user_id``."""
    return (
        db.session.query(UserBlock.id)
        .filter_by(
            blocker_user_id=blocker_user_id,
            blocked_user_id=blocked_user_id,
        )
        .first()
        is not None
    )


def user_is_blocked_by_any(*, user_id: int, counterpart_user_ids: Iterable[int | None]) -> bool:
    """Return whether any direct counterpart blocks the acting user."""
    counterpart_ids = {
        counterpart_id
        for counterpart_id in counterpart_user_ids
        if counterpart_id is not None and counterpart_id != user_id
    }
    if not counterpart_ids:
        return False
    return (
        db.session.query(UserBlock.id)
        .filter(
            UserBlock.blocker_user_id.in_(counterpart_ids),
            UserBlock.blocked_user_id == user_id,
        )
        .first()
        is not None
    )


__all__ = ["user_block_exists", "user_is_blocked_by_any"]
