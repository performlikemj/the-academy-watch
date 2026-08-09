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
USERS_TABLE = "user_accounts"


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


def active_program_manager_user_ids(program_id: int | None) -> list[int]:
    """Return the active user accounts participating for one club program."""
    if program_id is None or not registry_available():
        return []
    rows = db.session.execute(
        sa.text(
            f"SELECT DISTINCT user_account_id FROM {MANAGERS_TABLE} "
            "WHERE program_id = :program_id AND status = 'active' ORDER BY user_account_id"
        ),
        {"program_id": program_id},
    ).all()
    return [int(row[0]) for row in rows]


def active_program_manager_contacts(program_id: int | None) -> list[dict]:
    """Return stored account contacts for the program's active managers."""
    manager_columns = _table_columns(MANAGERS_TABLE)
    user_columns = _table_columns(USERS_TABLE)
    if (
        program_id is None
        or not {"program_id", "user_account_id", "status"}.issubset(manager_columns)
        or not {"id", "email"}.issubset(user_columns)
    ):
        return []
    display_name = "users.display_name" if "display_name" in user_columns else "NULL"
    rows = (
        db.session.execute(
            sa.text(
                f"SELECT users.id AS user_account_id, users.email, {display_name} AS display_name "
                f"FROM {MANAGERS_TABLE} AS managers "
                f"JOIN {USERS_TABLE} AS users ON users.id = managers.user_account_id "
                "WHERE managers.program_id = :program_id AND managers.status = 'active' "
                "ORDER BY users.id"
            ),
            {"program_id": program_id},
        )
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]


def _platform_club_identity(player_api_id: int | None) -> tuple[int | None, str | None]:
    """Return the persisted current-club identity without running classifiers."""
    if player_api_id is None:
        return None, None
    journey_columns = _table_columns("player_journeys")
    if {"player_api_id", "current_club_api_id", "current_club_name"}.issubset(journey_columns):
        row = (
            db.session.execute(
                sa.text(
                    "SELECT current_club_api_id, current_club_name FROM player_journeys "
                    "WHERE player_api_id = :player_api_id ORDER BY id LIMIT 1"
                ),
                {"player_api_id": player_api_id},
            )
            .mappings()
            .first()
        )
        if row is not None and (row["current_club_api_id"] is not None or row["current_club_name"]):
            return row["current_club_api_id"], row["current_club_name"]

    tracked_columns = _table_columns("tracked_players")
    required = {"player_api_id", "current_club_api_id", "current_club_name", "is_active", "data_source"}
    if required.issubset(tracked_columns):
        row = (
            db.session.execute(
                sa.text(
                    "SELECT current_club_api_id, current_club_name FROM tracked_players "
                    "WHERE player_api_id = :player_api_id AND is_active = true "
                    "AND data_source <> 'owning-club' ORDER BY id LIMIT 1"
                ),
                {"player_api_id": player_api_id},
            )
            .mappings()
            .first()
        )
        if row is not None:
            return row["current_club_api_id"], row["current_club_name"]
    return None, None


def find_club_notice_target(
    *,
    program_id: int | None,
    club_name: str | None,
    player_api_id: int | None = None,
) -> dict | None:
    """Resolve a courtesy-notice target without discovering external emails.

    Only ``club_programs.contact_email`` is eligible. With no linked program,
    the platform's current club id/name is tried before the claim's exact name.
    Name matches must resolve to exactly one row to avoid ambiguous delivery.
    """
    columns = _table_columns(PROGRAMS_TABLE)
    if not {"id", "name", "contact_email"}.issubset(columns):
        return None

    verification_filters = []
    if "platform_status" in columns:
        verification_filters.append("platform_status = 'approved'")
    if "emergency_hidden" in columns:
        verification_filters.append("emergency_hidden = false")
    verification_sql = "".join(f" AND {condition}" for condition in verification_filters)

    if program_id is not None:
        row = (
            db.session.execute(
                sa.text(
                    f"SELECT id, name, contact_email FROM {PROGRAMS_TABLE} "
                    "WHERE id = :program_id AND contact_email IS NOT NULL "
                    f"AND trim(contact_email) <> ''{verification_sql}"
                ),
                {"program_id": program_id},
            )
            .mappings()
            .first()
        )
        if row is not None:
            return dict(row)

    platform_club_api_id, platform_club_name = _platform_club_identity(player_api_id)
    if platform_club_api_id is not None and "team_api_id" in columns:
        rows = (
            db.session.execute(
                sa.text(
                    f"SELECT id, name, contact_email FROM {PROGRAMS_TABLE} "
                    "WHERE team_api_id = :team_api_id AND contact_email IS NOT NULL "
                    f"AND trim(contact_email) <> ''{verification_sql} ORDER BY id LIMIT 2"
                ),
                {"team_api_id": platform_club_api_id},
            )
            .mappings()
            .all()
        )
        if len(rows) == 1:
            return dict(rows[0])

    resolved_name = platform_club_name or club_name
    if not resolved_name:
        return None
    rows = (
        db.session.execute(
            sa.text(
                f"SELECT id, name, contact_email FROM {PROGRAMS_TABLE} "
                "WHERE lower(name) = lower(:club_name) AND contact_email IS NOT NULL "
                f"AND trim(contact_email) <> ''{verification_sql} ORDER BY id LIMIT 2"
            ),
            {"club_name": resolved_name},
        )
        .mappings()
        .all()
    )
    return dict(rows[0]) if len(rows) == 1 else None


__all__ = [
    "active_manager_program_ids",
    "active_program_manager_contacts",
    "active_program_manager_user_ids",
    "club_program_exists",
    "find_club_notice_target",
    "get_club_program",
    "is_active_program_manager",
    "program_has_active_manager",
    "registry_available",
]
