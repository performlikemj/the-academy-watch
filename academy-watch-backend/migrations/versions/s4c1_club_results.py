"""Stable club results and deterministic legacy adoption.

Revision ID: s4c1
Revises: s4b1

Pre-apply uses upgrade's DDL and backfill_legacy_results(bind) online without
stamping. Pause result writes and rerun adoption immediately around deployment.
"""

import hashlib
import json
from collections import defaultdict
from datetime import UTC
from uuid import UUID, uuid5

import bleach
import sqlalchemy as sa
from alembic import op
from migrations._migration_helpers import column_exists, create_index_safe, table_exists

revision = "s4c1"
down_revision = "s4b1"
branch_labels = None
depends_on = None
LEGACY_NAMESPACE = UUID("3e5c3325-24a8-58e2-8d15-63450e06b9c0")
TABLE = "club_results"
CHILD = "player_match_entries"


def _columns():
    return [
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("program_id", sa.Integer(), nullable=False),
        sa.Column("client_request_id", sa.String(36), nullable=False),
        sa.Column("create_request_hash", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("match_date", sa.Date(), nullable=False),
        sa.Column("season", sa.Integer(), nullable=False),
        sa.Column("opponent", sa.String(120), nullable=False),
        sa.Column("opponent_key", sa.String(120), nullable=False),
        sa.Column("competition", sa.String(120)),
        sa.Column("home_away", sa.String(8), nullable=False),
        sa.Column("result_for", sa.Integer(), nullable=False),
        sa.Column("result_against", sa.Integer(), nullable=False),
        sa.Column("video_match_id", sa.Integer()),
        sa.Column("created_by_user_id", sa.Integer()),
        sa.Column("updated_by_user_id", sa.Integer()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime()),
    ]


def _inspect():
    return sa.inspect(op.get_bind())


def _unique(table, name, columns):
    if not any(c["column_names"] == columns for c in _inspect().get_unique_constraints(table)):
        op.create_unique_constraint(name, table, columns)


def _check(table, name, expression):
    if name not in {c["name"] for c in _inspect().get_check_constraints(table)}:
        op.create_check_constraint(name, table, expression)


def _foreign(table, name, columns, target, remote, ondelete=None):
    if not any(
        c["constrained_columns"] == columns and c["referred_table"] == target and c["referred_columns"] == remote
        for c in _inspect().get_foreign_keys(table)
    ):
        op.create_foreign_key(name, table, target, columns, remote, ondelete=ondelete)


def upgrade():
    if not table_exists(TABLE):
        op.create_table(TABLE, *_columns())
    for column in _columns():
        if not column_exists(TABLE, column.name):
            op.add_column(TABLE, column)
    if not _inspect().get_pk_constraint(TABLE)["constrained_columns"]:
        op.create_primary_key("pk_club_results", TABLE, ["id"])
    _unique(TABLE, "uq_club_results_request", ["program_id", "client_request_id"])
    _unique(TABLE, "uq_club_results_program", ["id", "program_id"])
    _check(TABLE, "ck_club_results_version", "version > 0")
    _check(TABLE, "ck_club_results_home_away", "home_away IN ('home','away','neutral')")
    _check(TABLE, "ck_club_results_counts", "result_for BETWEEN 0 AND 20 AND result_against BETWEEN 0 AND 20")
    for column, target, ondelete in (
        ("program_id", "club_programs", None),
        ("video_match_id", "video_matches", "SET NULL"),
        ("created_by_user_id", "user_accounts", "SET NULL"),
        ("updated_by_user_id", "user_accounts", "SET NULL"),
    ):
        _foreign(TABLE, f"fk_club_results_{column}", [column], target, ["id"], ondelete)
    create_index_safe(
        "uq_club_results_active",
        TABLE,
        ["program_id", "match_date", "opponent_key"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    create_index_safe("ix_club_results_history", TABLE, ["program_id", "season", "match_date", "id"])
    create_index_safe("ix_club_results_video_match_id", TABLE, ["video_match_id"])
    if not column_exists(CHILD, "club_result_id"):
        op.add_column(CHILD, sa.Column("club_result_id", sa.String(36)))
    create_index_safe("ix_player_match_entries_club_result_id", CHILD, ["club_result_id"])
    _foreign(
        CHILD,
        "fk_player_match_entries_result_program",
        ["club_result_id", "club_program_id"],
        TABLE,
        ["id", "program_id"],
    )
    _unique(CHILD, "uq_player_match_entries_result_player", ["club_result_id", "player_api_id"])
    _check(
        CHILD,
        "ck_player_match_entries_result_source",
        "club_result_id IS NULL OR (source = 'club' AND club_program_id IS NOT NULL)",
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text("ALTER TABLE club_results ENABLE ROW LEVEL SECURITY"))
    backfill_legacy_results(op.get_bind())


def _normalize(value):
    # Same plain-text sanitizer as the writer, frozen here with no app imports.
    return bleach.clean(value, tags=[], attributes={}, strip=True).strip()


def backfill_legacy_results(bind):
    """Validate ALL groups before adopting any. Caller owns the transaction.

    Diagnostics contain bounded reason counts and entry IDs, never private text.
    Existing linked groups are validated when old binaries append orphan lines;
    no row is silently folded into a corrected or tombstoned result.
    """
    meta = sa.MetaData()
    entries = sa.Table(CHILD, meta, autoload_with=bind)
    results = sa.Table(TABLE, meta, autoload_with=bind)
    rows = bind.execute(sa.select(entries).where(entries.c.source == "club").order_by(entries.c.id)).mappings().all()
    groups = defaultdict(list)
    errors = []
    for row in rows:
        if row["club_program_id"] is None:
            errors.append(("null_program", row["id"]))
        else:
            key = (row["club_program_id"], row["match_date"].isoformat(), _normalize(row["opponent"]).lower())
            groups[key].append(row)
    plans = []
    header_fields = ("season", "competition", "home_away", "result_for", "result_against")
    for key, lines in groups.items():
        orphans = [row for row in lines if row["club_result_id"] is None]
        if not orphans:
            continue
        first = lines[0]
        if len({row["player_api_id"] for row in lines}) != len(lines):
            errors.append(("duplicate_player", first["id"]))
        if any(any(row[field] != first[field] for field in header_fields) for row in lines):
            errors.append(("inconsistent_header", first["id"]))
        if first["result_for"] is None or first["result_against"] is None:
            errors.append(("missing_score", first["id"]))
        identity = json.dumps(key, ensure_ascii=False, separators=(",", ":"))
        result_id = str(uuid5(LEGACY_NAMESPACE, identity))
        existing = (
            bind.execute(
                sa.select(results).where(
                    sa.or_(
                        results.c.id == result_id,
                        sa.and_(
                            results.c.program_id == key[0],
                            results.c.match_date == first["match_date"],
                            results.c.opponent_key == key[2],
                            results.c.deleted_at.is_(None),
                        ),
                    )
                )
            )
            .mappings()
            .all()
        )
        if existing or any(row["club_result_id"] for row in lines):
            errors.append(("already_adopted_slot", first["id"]))
        plans.append((key, lines, result_id, identity))
    if errors:
        counts = {reason: sum(r == reason for r, _ in errors) for reason in sorted({r for r, _ in errors})}
        raise RuntimeError(f"legacy_result_adoption_failed counts={counts} entry_ids={[i for _, i in errors[:10]]}")
    for key, lines, result_id, identity in plans:
        first = lines[0]

        def naive(value):
            return value.astimezone(UTC).replace(tzinfo=None) if value.tzinfo else value

        created_at = min(naive(row["created_at"]) for row in lines)
        updated_at = max(naive(row["updated_at"]) for row in lines)
        bind.execute(
            results.insert().values(
                id=result_id,
                program_id=key[0],
                client_request_id=result_id,
                create_request_hash=hashlib.sha256(("legacy:" + identity).encode()).hexdigest(),
                version=1,
                match_date=first["match_date"],
                opponent=_normalize(first["opponent"]),
                opponent_key=key[2],
                **{field: first[field] for field in header_fields},
                video_match_id=None,
                created_by_user_id=None,
                updated_by_user_id=None,
                created_at=created_at,
                updated_at=updated_at,
            )
        )
        bind.execute(
            entries.update().where(entries.c.id.in_([row["id"] for row in lines])).values(club_result_id=result_id)
        )
    return {"adopted_results": len(plans), "adopted_entries": sum(len(lines) for _, lines, _, _ in plans)}


def downgrade():
    # A data-bearing rollback keeps this additive schema and the result-write pause.
    raise RuntimeError("Keep s4c1 additive schema; pause result writes before rolling back the application")
