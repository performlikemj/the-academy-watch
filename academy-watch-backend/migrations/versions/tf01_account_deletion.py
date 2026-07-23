"""Account-deletion tombstones and append-only completion events.

Revision ID: tf01
Revises: fc03

This stacked migration intentionally chains from FC-B3's ``fc03``. PR #636
(``gf01``, funding registry) remains independently ordered: if ``gf01`` lands
first, re-point ``fc01`` onto ``gf01`` and retain
``tf01 -> fc03 -> fc02 -> fc01``; upgrade ``gf01`` before this stack and
downgrade this stack before ``gf01``. If this trust-floor stack lands first,
re-point ``gf01`` onto ``tf01`` and downgrade ``gf01`` before ``tf01``. Never
merge an arrangement with two Alembic heads.

All DDL is guarded because production has drifted out-of-band. The new public
table enables Row Level Security in this same migration, with no permissive
direct-client policies. Downgrade refuses to discard completed deletion events,
live tombstones, or contact threads whose claim was erased.
"""

import sqlalchemy as sa
from alembic import op
from migrations._migration_helpers import (
    add_column_safe,
    column_exists,
    create_index_safe,
    index_exists,
    table_exists,
)

revision = "tf01"
down_revision = "fc03"
branch_labels = None
depends_on = None


EVENT_TABLE = "account_deletion_events"
TOMBSTONE_INDEX = "uq_account_deletion_events_tombstone_user"
REQUESTED_AT_INDEX = "ix_account_deletion_events_requested_at"


def _column_is_nullable(table_name: str, column_name: str) -> bool:
    """Return the current PostgreSQL nullability for a guarded column."""
    result = op.get_bind().execute(
        sa.text(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = :table_name "
            "AND column_name = :column_name"
        ),
        {"table_name": table_name, "column_name": column_name},
    )
    return result.scalar() == "YES"


def _table_has_rows(table_name: str) -> bool:
    return bool(op.get_bind().execute(sa.text(f'SELECT EXISTS (SELECT 1 FROM "{table_name}")')).scalar())


def _column_has_nulls(table_name: str, column_name: str) -> bool:
    return bool(
        op.get_bind()
        .execute(sa.text(f'SELECT EXISTS (SELECT 1 FROM "{table_name}" WHERE "{column_name}" IS NULL)'))
        .scalar()
    )


def _column_has_true(table_name: str, column_name: str) -> bool:
    return bool(
        op.get_bind()
        .execute(sa.text(f'SELECT EXISTS (SELECT 1 FROM "{table_name}" WHERE "{column_name}" IS TRUE)'))
        .scalar()
    )


def upgrade():
    if table_exists("user_accounts"):
        add_column_safe(
            "user_accounts",
            sa.Column("is_tombstone", sa.Boolean(), nullable=False, server_default=sa.false()),
        )

    if (
        table_exists("contact_requests")
        and column_exists("contact_requests", "claim_id")
        and not _column_is_nullable("contact_requests", "claim_id")
    ):
        op.alter_column(
            "contact_requests",
            "claim_id",
            existing_type=sa.Integer(),
            nullable=True,
        )

    if not table_exists(EVENT_TABLE) and table_exists("user_accounts"):
        op.create_table(
            EVENT_TABLE,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "tombstone_user_id",
                sa.Integer(),
                sa.ForeignKey("user_accounts.id"),
                nullable=False,
            ),
            sa.Column("requested_at", sa.DateTime(), nullable=False),
            sa.Column("completed_at", sa.DateTime(), nullable=False),
            sa.Column("counts", sa.JSON(), nullable=False),
        )

    if table_exists(EVENT_TABLE):
        create_index_safe(
            TOMBSTONE_INDEX,
            EVENT_TABLE,
            ["tombstone_user_id"],
            unique=True,
        )
        create_index_safe(
            REQUESTED_AT_INDEX,
            EVENT_TABLE,
            ["requested_at"],
        )
        # Idempotent and intentionally policy-free: only the Flask service writes
        # this append-only audit surface.
        op.execute(sa.text(f'ALTER TABLE "{EVENT_TABLE}" ENABLE ROW LEVEL SECURITY'))


def downgrade():
    if table_exists(EVENT_TABLE) and _table_has_rows(EVENT_TABLE):
        raise RuntimeError("tf01 downgrade refused: account deletion events are append-only")

    if (
        table_exists("user_accounts")
        and column_exists("user_accounts", "is_tombstone")
        and _column_has_true("user_accounts", "is_tombstone")
    ):
        raise RuntimeError("tf01 downgrade refused: tombstone accounts still exist")

    if (
        table_exists("contact_requests")
        and column_exists("contact_requests", "claim_id")
        and _column_has_nulls("contact_requests", "claim_id")
    ):
        raise RuntimeError("tf01 downgrade refused: anonymized contact requests still exist")

    if (
        table_exists("contact_requests")
        and column_exists("contact_requests", "claim_id")
        and _column_is_nullable("contact_requests", "claim_id")
    ):
        op.alter_column(
            "contact_requests",
            "claim_id",
            existing_type=sa.Integer(),
            nullable=False,
        )

    if table_exists(EVENT_TABLE):
        if index_exists(REQUESTED_AT_INDEX):
            op.drop_index(REQUESTED_AT_INDEX, table_name=EVENT_TABLE)
        if index_exists(TOMBSTONE_INDEX):
            op.drop_index(TOMBSTONE_INDEX, table_name=EVENT_TABLE)
        op.drop_table(EVENT_TABLE)

    if table_exists("user_accounts") and column_exists("user_accounts", "is_tombstone"):
        op.drop_column("user_accounts", "is_tombstone")
