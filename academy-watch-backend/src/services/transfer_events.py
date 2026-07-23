"""Persistence choke point for durable API-Football transfer events."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from src.models.transfer_event import PlayerTransferEvent

_NATURAL_KEY_NAMES = (
    "player_api_id",
    "transfer_date",
    "out_club_api_id",
    "in_club_api_id",
    "transfer_type",
)


def _transfer_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def _club_id(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _nullable_match(column, value):
    return column.is_(None) if value is None else column == value


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _update_nullable_key_event(session, values: dict[str, Any]) -> None:
    """Portable fallback for dialects whose UNIQUE constraints distinguish NULL."""

    existing = session.execute(
        select(PlayerTransferEvent).where(
            and_(*(_nullable_match(getattr(PlayerTransferEvent, field), values[field]) for field in _NATURAL_KEY_NAMES))
        )
    ).scalar_one_or_none()
    if existing is None:
        session.add(PlayerTransferEvent(**values))
        return

    existing.last_seen_at = max(
        _as_utc(existing.last_seen_at),
        _as_utc(values["last_seen_at"]),
    )


def record_transfer_events(
    player_api_id: int,
    transfers: list[dict[str, Any]] | None,
    session,
    *,
    observed_at: datetime | None = None,
) -> int:
    """Upsert a flat list of raw transfer objects without committing.

    ``first_seen_at`` is insert-only. A repeated natural key advances
    ``last_seen_at`` while retaining the first-seen names, raw evidence, and
    row identity. Invalid/missing dates cannot satisfy the table's non-null
    key and are skipped.

    The caller owns the transaction. PostgreSQL and SQLite use their native
    ``ON CONFLICT`` forms; a small ORM fallback covers other test dialects and
    nullable natural-key components (SQL UNIQUE treats NULL values as distinct).
    """

    try:
        normalized_player_id = int(player_api_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("player_api_id must be an integer") from exc

    seen_at = _as_utc(observed_at or datetime.now(UTC))
    dialect_name = session.get_bind().dialect.name
    if dialect_name == "postgresql":
        insert_factory = postgresql_insert
    elif dialect_name == "sqlite":
        insert_factory = sqlite_insert
    else:
        insert_factory = None

    recorded = 0
    for transfer in transfers or []:
        if not isinstance(transfer, dict):
            continue

        effective_date = _transfer_date(transfer.get("date"))
        if effective_date is None:
            continue

        teams = transfer.get("teams")
        teams = teams if isinstance(teams, dict) else {}
        out_club = teams.get("out")
        out_club = out_club if isinstance(out_club, dict) else {}
        in_club = teams.get("in")
        in_club = in_club if isinstance(in_club, dict) else {}
        raw_type = transfer.get("type")
        transfer_type = raw_type if isinstance(raw_type, str) else None

        values = {
            "player_api_id": normalized_player_id,
            "transfer_date": effective_date,
            "transfer_type": transfer_type,
            "out_club_api_id": _club_id(out_club.get("id")),
            "out_club_name": out_club.get("name") if isinstance(out_club.get("name"), str) else None,
            "in_club_api_id": _club_id(in_club.get("id")),
            "in_club_name": in_club.get("name") if isinstance(in_club.get("name"), str) else None,
            "first_seen_at": seen_at,
            "last_seen_at": seen_at,
            "raw": deepcopy(transfer),
        }

        key_has_null = any(values[field] is None for field in _NATURAL_KEY_NAMES)
        if insert_factory is None or (key_has_null and dialect_name != "postgresql"):
            _update_nullable_key_event(session, values)
        else:
            statement = insert_factory(PlayerTransferEvent).values(**values)
            existing_last_seen = PlayerTransferEvent.__table__.c.last_seen_at
            latest_seen = (
                func.greatest(existing_last_seen, statement.excluded.last_seen_at)
                if dialect_name == "postgresql"
                else func.max(existing_last_seen, statement.excluded.last_seen_at)
            )
            statement = statement.on_conflict_do_update(
                index_elements=list(_NATURAL_KEY_NAMES),
                set_={"last_seen_at": latest_seen},
            )
            session.execute(statement)
        recorded += 1

    session.flush()
    return recorded
