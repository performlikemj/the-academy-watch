"""Shared user-block predicates with pre-migration tolerance."""

import logging
from collections.abc import Callable, Iterable
from threading import Lock

from sqlalchemy import or_
from sqlalchemy.exc import ProgrammingError
from src.models.league import db
from src.models.user_block import UserBlock

logger = logging.getLogger(__name__)

UNDEFINED_TABLE_SQLSTATE = "42P01"

_missing_table_logged = False
_missing_table_log_lock = Lock()


def is_user_blocks_undefined_table_error(exc: BaseException) -> bool:
    """Match only PostgreSQL's undefined-table programming error."""
    if not isinstance(exc, ProgrammingError):
        return False
    original = getattr(exc, "orig", None)
    return (
        getattr(original, "sqlstate", None) == UNDEFINED_TABLE_SQLSTATE
        or getattr(original, "pgcode", None) == UNDEFINED_TABLE_SQLSTATE
    )


def log_user_blocks_table_unavailable_once() -> None:
    """Emit one process-level operator signal while the DDL is pending."""
    global _missing_table_logged
    if _missing_table_logged:
        return
    with _missing_table_log_lock:
        if _missing_table_logged:
            return
        logger.warning("user_blocks table is unavailable; pre-apply ug01 via the PostgreSQL pooler")
        _missing_table_logged = True


def _optional_user_blocks_query(operation: Callable[[], object], *, default):
    """Run a user-block operation behind a savepoint and tolerate only 42P01.

    PostgreSQL marks a transaction failed after an undefined-table error. The
    savepoint is therefore required: catching the exception without rolling
    back to it would still make the caller's later work fail.
    """
    try:
        with db.session.begin_nested():
            return operation()
    except ProgrammingError as exc:
        if not is_user_blocks_undefined_table_error(exc):
            raise
        log_user_blocks_table_unavailable_once()
        return default


def user_block_exists(*, blocker_user_id: int, blocked_user_id: int) -> bool:
    """Return whether ``blocker_user_id`` currently blocks ``blocked_user_id``."""

    def _query() -> bool:
        return (
            db.session.query(UserBlock.id)
            .filter_by(
                blocker_user_id=blocker_user_id,
                blocked_user_id=blocked_user_id,
            )
            .first()
            is not None
        )

    return _optional_user_blocks_query(_query, default=False)


def users_have_block_relationship(*, first_user_id: int, second_user_id: int) -> bool:
    """Return whether either account blocks the other."""
    if first_user_id == second_user_id:
        return False

    def _query() -> bool:
        return (
            db.session.query(UserBlock.id)
            .filter(
                or_(
                    (UserBlock.blocker_user_id == first_user_id) & (UserBlock.blocked_user_id == second_user_id),
                    (UserBlock.blocker_user_id == second_user_id) & (UserBlock.blocked_user_id == first_user_id),
                )
            )
            .first()
            is not None
        )

    return _optional_user_blocks_query(_query, default=False)


def user_has_block_relationship_with_any(*, user_id: int, counterpart_user_ids: Iterable[int | None]) -> bool:
    """Return whether the caller has a block in either direction with any counterpart."""
    counterpart_ids = {
        counterpart_id
        for counterpart_id in counterpart_user_ids
        if counterpart_id is not None and counterpart_id != user_id
    }
    if not counterpart_ids:
        return False

    def _query() -> bool:
        return (
            db.session.query(UserBlock.id)
            .filter(
                or_(
                    (UserBlock.blocker_user_id == user_id) & UserBlock.blocked_user_id.in_(counterpart_ids),
                    (UserBlock.blocked_user_id == user_id) & UserBlock.blocker_user_id.in_(counterpart_ids),
                )
            )
            .first()
            is not None
        )

    return _optional_user_blocks_query(_query, default=False)


def block_related_user_ids(*, user_id: int) -> set[int]:
    """Return accounts connected to ``user_id`` by a block in either direction."""

    def _query() -> set[int]:
        rows = (
            db.session.query(UserBlock.blocker_user_id, UserBlock.blocked_user_id)
            .filter(or_(UserBlock.blocker_user_id == user_id, UserBlock.blocked_user_id == user_id))
            .all()
        )
        return {
            blocked_user_id if blocker_user_id == user_id else blocker_user_id
            for blocker_user_id, blocked_user_id in rows
        }

    return _optional_user_blocks_query(_query, default=set())


def blocked_user_ids(*, blocker_user_id: int) -> set[int]:
    """Return only accounts blocked by ``blocker_user_id`` (management semantics)."""

    def _query() -> set[int]:
        return {
            blocked_user_id
            for (blocked_user_id,) in db.session.query(UserBlock.blocked_user_id)
            .filter(UserBlock.blocker_user_id == blocker_user_id)
            .all()
        }

    return _optional_user_blocks_query(_query, default=set())


def delete_user_block_rows_for_account(*, user_id: int) -> int:
    """Delete both directions during erasure, or no-op before ug01 exists."""

    def _delete() -> int:
        return UserBlock.query.filter(
            or_(
                UserBlock.blocker_user_id == user_id,
                UserBlock.blocked_user_id == user_id,
            )
        ).delete(synchronize_session=False)

    return _optional_user_blocks_query(_delete, default=0)


__all__ = [
    "block_related_user_ids",
    "blocked_user_ids",
    "delete_user_block_rows_for_account",
    "is_user_blocks_undefined_table_error",
    "log_user_blocks_table_unavailable_once",
    "user_block_exists",
    "user_has_block_relationship_with_any",
    "users_have_block_relationship",
]
