"""Add private coach and system briefs to their owning club rows.

Revision ID: cb01
Revises: pm01
Create Date: 2026-09-02

All DDL is guarded because production has drifted out-of-band. Both owning
tables already have RLS enabled, so RLS is inherited and this migration does
not create or expose a new public table.

DEPLOY ORDERING (migrations do NOT auto-run): pre-apply ``cb01`` via the
PostgreSQL pooler and stamp it before merging application code that writes
these columns.
"""

import sqlalchemy as sa
from alembic import op
from migrations._migration_helpers import add_column_safe, column_exists, table_exists

revision = "cb01"
down_revision = "pm01"
branch_labels = None
depends_on = None

MEMBER_TABLE = "club_roster_members"
PROGRAM_TABLE = "club_programs"

MEMBER_COLUMNS = (
    sa.Column("coach_brief_body", sa.Text(), nullable=True),
    sa.Column("brief_updated_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column(
        "brief_updated_by_user_id",
        sa.Integer(),
        nullable=True,
    ),
)
PROGRAM_COLUMNS = (
    sa.Column("system_brief_body", sa.Text(), nullable=True),
    sa.Column("system_brief_updated_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column(
        "system_brief_updated_by_user_id",
        sa.Integer(),
        nullable=True,
    ),
)
AUDIT_FOREIGN_KEYS = (
    (
        MEMBER_TABLE,
        "brief_updated_by_user_id",
        "fk_club_roster_members_brief_updated_by_user_id",
    ),
    (
        PROGRAM_TABLE,
        "system_brief_updated_by_user_id",
        "fk_club_programs_system_brief_updated_by_user_id",
    ),
)


def _constraint_exists(table_name: str, column_name: str, constraint_name: str | None = None) -> bool:
    name_filter = ""
    params = {
        "column_name": column_name,
        "qualified_table": f"public.{table_name}",
    }
    if constraint_name is not None:
        name_filter = " AND constraint_record.conname = :constraint_name"
        params["constraint_name"] = constraint_name
    return (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT 1 FROM pg_constraint AS constraint_record "
                "JOIN pg_attribute AS attribute "
                "ON attribute.attrelid = constraint_record.conrelid "
                "AND attribute.attname = :column_name "
                "WHERE constraint_record.contype = 'f' "
                "AND constraint_record.conrelid = to_regclass(:qualified_table) "
                "AND constraint_record.conkey = ARRAY[attribute.attnum]" + name_filter
            ),
            params,
        )
        .scalar()
        is not None
    )


def upgrade():
    for table, columns in ((MEMBER_TABLE, MEMBER_COLUMNS), (PROGRAM_TABLE, PROGRAM_COLUMNS)):
        if table_exists(table):
            for column in columns:
                add_column_safe(table, column)
    if table_exists("user_accounts"):
        for table, column, constraint in AUDIT_FOREIGN_KEYS:
            if table_exists(table) and column_exists(table, column) and not _constraint_exists(table, column):
                op.create_foreign_key(
                    constraint,
                    table,
                    "user_accounts",
                    [column],
                    ["id"],
                    ondelete="SET NULL",
                )


def downgrade():
    for table, column, constraint in AUDIT_FOREIGN_KEYS:
        if table_exists(table) and _constraint_exists(table, column, constraint):
            op.drop_constraint(constraint, table, type_="foreignkey")
    for table, columns in ((MEMBER_TABLE, MEMBER_COLUMNS), (PROGRAM_TABLE, PROGRAM_COLUMNS)):
        if not table_exists(table):
            continue
        for column in reversed(columns):
            if column_exists(table, column.name):
                op.drop_column(table, column.name)
