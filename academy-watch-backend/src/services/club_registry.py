"""Read-only bridge to the independently ordered funding registry.

PR #636's ``gf01`` migration may land before or after the Full Circle stack,
so FC-B3 cannot import funding-registry ORM models or declare hard foreign
keys.  These helpers deliberately use narrow SQLAlchemy Core reads and degrade
to "registry unavailable" while the two migration stacks are being ordered.
"""

from __future__ import annotations

import sqlalchemy as sa
from src.models.league import db

PROGRAMS_TABLE = "club_programs"
MANAGERS_TABLE = "club_program_managers"


def _table_columns(table_name: str) -> set[str]:
    bind = db.session.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(table_name):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def registry_available() -> bool:
    """Return whether both authoritative registry tables are present."""
    return bool(_table_columns(PROGRAMS_TABLE) and _table_columns(MANAGERS_TABLE))


def get_club_program(program_id: int | None) -> dict | None:
    """Return the narrow program projection FC-B3 is allowed to consume."""
    if program_id is None:
        return None
    columns = _table_columns(PROGRAMS_TABLE)
    if not {"id", "name"}.issubset(columns):
        return None
    selected = ["id", "name"]
    if "contact_email" in columns:
        selected.append("contact_email")
    row = (
        db.session.execute(
            sa.text(f"SELECT {', '.join(selected)} FROM {PROGRAMS_TABLE} WHERE id = :program_id"),
            {"program_id": program_id},
        )
        .mappings()
        .first()
    )
    return dict(row) if row is not None else None


def club_program_exists(program_id: int | None) -> bool:
    return get_club_program(program_id) is not None


def program_has_active_manager(program_id: int | None) -> bool:
    if program_id is None or not registry_available():
        return False
    return (
        db.session.execute(
            sa.text(
                f"SELECT 1 FROM {MANAGERS_TABLE} AS managers "
                f"JOIN {PROGRAMS_TABLE} AS programs ON programs.id = managers.program_id "
                "WHERE managers.program_id = :program_id AND managers.status = 'active' LIMIT 1"
            ),
            {"program_id": program_id},
        ).scalar()
        is not None
    )


def is_active_program_manager(user_id: int | None, program_id: int | None) -> bool:
    if user_id is None or program_id is None or not registry_available():
        return False
    return (
        db.session.execute(
            sa.text(
                f"SELECT 1 FROM {MANAGERS_TABLE} "
                "WHERE user_account_id = :user_id AND program_id = :program_id "
                "AND status = 'active' LIMIT 1"
            ),
            {"user_id": user_id, "program_id": program_id},
        ).scalar()
        is not None
    )


def active_manager_program_ids(user_id: int | None) -> list[int]:
    if user_id is None or not registry_available():
        return []
    rows = db.session.execute(
        sa.text(
            f"SELECT DISTINCT program_id FROM {MANAGERS_TABLE} "
            "WHERE user_account_id = :user_id AND status = 'active' ORDER BY program_id"
        ),
        {"user_id": user_id},
    ).all()
    return [int(row[0]) for row in rows]


def find_club_notice_target(*, program_id: int | None, club_name: str | None) -> dict | None:
    """Resolve a courtesy-notice target without discovering external emails.

    Only ``club_programs.contact_email`` is eligible.  When there is no linked
    program, an exact case-insensitive name match is allowed only if it resolves
    to exactly one row, avoiding delivery to an ambiguous club identity.
    """
    columns = _table_columns(PROGRAMS_TABLE)
    if not {"id", "name", "contact_email"}.issubset(columns):
        return None

    if program_id is not None:
        row = (
            db.session.execute(
                sa.text(
                    f"SELECT id, name, contact_email FROM {PROGRAMS_TABLE} "
                    "WHERE id = :program_id AND contact_email IS NOT NULL "
                    "AND trim(contact_email) <> ''"
                ),
                {"program_id": program_id},
            )
            .mappings()
            .first()
        )
        return dict(row) if row is not None else None

    if not club_name:
        return None
    rows = (
        db.session.execute(
            sa.text(
                f"SELECT id, name, contact_email FROM {PROGRAMS_TABLE} "
                "WHERE lower(name) = lower(:club_name) AND contact_email IS NOT NULL "
                "AND trim(contact_email) <> '' ORDER BY id LIMIT 2"
            ),
            {"club_name": club_name},
        )
        .mappings()
        .all()
    )
    return dict(rows[0]) if len(rows) == 1 else None


__all__ = [
    "active_manager_program_ids",
    "club_program_exists",
    "find_club_notice_target",
    "get_club_program",
    "is_active_program_manager",
    "program_has_active_manager",
    "registry_available",
]
