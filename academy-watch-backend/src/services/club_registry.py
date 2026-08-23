"""Read-only bridge to the independently ordered funding registry.

PR #636's ``gf01`` migration may land before or after the Full Circle stack,
so FC-B3 cannot import funding-registry ORM models or declare hard foreign
keys.  These helpers deliberately use narrow SQLAlchemy Core reads and degrade
to "registry unavailable" while the two migration stacks are being ordered.
"""

from __future__ import annotations

from functools import wraps

import sqlalchemy as sa
from flask import g, has_request_context, jsonify, request
from src.auth import require_user_auth
from src.models.league import db

PROGRAMS_TABLE = "club_programs"
MANAGERS_TABLE = "club_program_managers"
CLAIMS_TABLE = "club_program_claims"
USERS_TABLE = "user_accounts"


def _introspect_table_columns(table_name: str) -> set[str]:
    # Stay on the session's transaction. An inspector-owned wrapper can roll
    # back SQLite's shared in-memory connection when it closes mid-request.
    bind = db.session.connection()
    inspector = sa.inspect(bind)
    if not inspector.has_table(table_name):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def _table_columns(table_name: str) -> set[str]:
    """Introspect once per HTTP request; the schema cannot change mid-request and the
    registry is consulted up to a dozen times per contact-rail call. No cache outside a request."""
    if not has_request_context():
        return _introspect_table_columns(table_name)
    cache = getattr(request, "_club_registry_columns", None)
    if cache is None:
        cache = {}
        request._club_registry_columns = cache
    if table_name not in cache:
        cache[table_name] = _introspect_table_columns(table_name)
    return cache[table_name]


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


def program_is_operational(program_id: int | None, *, for_update: bool = False) -> bool:
    """Return whether a program may participate in operational contact flows."""
    if program_id is None:
        return False
    columns = _table_columns(PROGRAMS_TABLE)
    if not {"id", "platform_status", "emergency_hidden"}.issubset(columns):
        return False
    programs = sa.table(
        PROGRAMS_TABLE,
        sa.column("id"),
        sa.column("platform_status"),
        sa.column("emergency_hidden"),
    )
    statement = (
        sa.select(sa.literal(1))
        .select_from(programs)
        .where(
            programs.c.id == program_id,
            programs.c.platform_status == "approved",
            programs.c.emergency_hidden.is_(False),
        )
        .limit(1)
    )
    if for_update:
        statement = statement.with_for_update()
    return db.session.execute(statement).scalar() is not None


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


def _is_manager_of_approved_program(user_id: int | None, program_id: int | None) -> bool:
    """Strict console authorization: active grant, claim, and program standing."""

    program_columns = _table_columns(PROGRAMS_TABLE)
    manager_columns = _table_columns(MANAGERS_TABLE)
    claim_columns = _table_columns(CLAIMS_TABLE)
    if (
        user_id is None
        or program_id is None
        or not {"id", "platform_status", "emergency_hidden"}.issubset(program_columns)
        or not {"program_id", "user_account_id", "source_claim_id", "status"}.issubset(manager_columns)
        or not {"id", "program_id", "user_account_id", "status"}.issubset(claim_columns)
    ):
        return False
    return (
        db.session.execute(
            sa.text(
                f"SELECT 1 FROM {MANAGERS_TABLE} AS managers "
                f"JOIN {PROGRAMS_TABLE} AS programs ON programs.id = managers.program_id "
                f"JOIN {CLAIMS_TABLE} AS claims ON claims.id = managers.source_claim_id "
                "AND claims.program_id = managers.program_id "
                "AND claims.user_account_id = managers.user_account_id "
                "WHERE managers.user_account_id = :user_id AND managers.program_id = :program_id "
                "AND managers.status = 'active' AND programs.platform_status = 'approved' "
                "AND programs.emergency_hidden = false "
                "AND claims.status = 'approved' LIMIT 1"
            ),
            {"user_id": user_id, "program_id": program_id},
        ).scalar()
        is not None
    )


def require_club_manager(program_id_arg: str = "program_id"):
    """Require one authenticated, active manager for the route's program.

    The denial is deliberately neutral: an unknown program, a pending claim,
    and a revoked/removed manager all receive the same 403.  Resource-owning
    routes must still query their child row through ``program_id``; this
    decorator establishes authority, not ownership of an arbitrary resource id.
    """

    def decorator(view):
        @wraps(view)
        def manager_checked(*args, **kwargs):
            program_id = kwargs.get(program_id_arg)
            if not _is_manager_of_approved_program(getattr(g, "user_id", None), program_id):
                return jsonify({"error": "Club manager access denied"}), 403
            return view(*args, **kwargs)

        return require_user_auth(manager_checked)

    return decorator


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


def manager_program_ids(user_id: int | None) -> list[int]:
    """Return every program ever managed by the user, including revoked grants."""
    if user_id is None or not registry_available():
        return []
    rows = db.session.execute(
        sa.text(
            f"SELECT DISTINCT program_id FROM {MANAGERS_TABLE} WHERE user_account_id = :user_id ORDER BY program_id"
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


def program_manager_user_ids(program_ids: list[int]) -> set[int]:
    """Return current or historical manager accounts for the given programs."""
    columns = _table_columns(MANAGERS_TABLE)
    if not program_ids or not {"program_id", "user_account_id"}.issubset(columns):
        return set()
    managers = sa.table(
        MANAGERS_TABLE,
        sa.column("program_id"),
        sa.column("user_account_id"),
    )
    rows = db.session.execute(
        sa.select(managers.c.user_account_id).distinct().where(managers.c.program_id.in_(program_ids))
    ).scalars()
    return {int(user_id) for user_id in rows if user_id is not None}


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
    for_update: bool = False,
) -> dict | None:
    """Resolve a courtesy-notice target without discovering external emails.

    Only ``club_programs.contact_email`` is eligible. A linked program resolves
    only to that exact row. Without a link, only the platform's persisted team
    API id is strong enough; name-only discovery is deliberately suppressed.
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
        if not program_is_operational(program_id, for_update=for_update):
            return None
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
        return dict(row) if row is not None else None

    platform_club_api_id, _platform_club_name = _platform_club_identity(player_api_id)
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
    return None


__all__ = [
    "active_manager_program_ids",
    "active_program_manager_contacts",
    "active_program_manager_user_ids",
    "club_program_exists",
    "find_club_notice_target",
    "get_club_program",
    "is_active_program_manager",
    "manager_program_ids",
    "program_has_active_manager",
    "program_manager_user_ids",
    "program_is_operational",
    "require_club_manager",
    "registry_available",
]
