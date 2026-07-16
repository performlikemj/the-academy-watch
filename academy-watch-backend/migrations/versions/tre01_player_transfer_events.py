"""Durable player transfer events

Revision ID: tre01
Revises: sea03
Create Date: 2026-07-16

Creates ``player_transfer_events``, the durable evidence surface for the raw
API-Football transfer objects already fetched by sync paths. One row represents
one provider event at the natural grain
``(player, date, out club, in club, raw type)``; repeated observations preserve
``first_seen_at`` and monotonically advance ``last_seen_at``. PostgreSQL's
``NULLS NOT DISTINCT`` semantics keep that natural key unique even when the
provider omits a club id or transfer type.

All DDL is guarded (invariants section 8): table creation uses ``table_exists``,
the player lookup index uses ``create_index_safe``, and RLS enablement is
idempotent. The new public table enables ROW LEVEL SECURITY in this same
migration, as required by the deploy gate (invariants section 2).

DEPLOY ORDERING (migrations do NOT auto-run): prefer PRE-APPLYING ``tre01``
out-of-band before deploying the writer code. R1 only writes this table from
transfer-sync paths and no read path SELECTs it, so an unapplied migration has
no UndefinedTable read-path 500 window. Applying it after the code deploy is
therefore read-safe; the additive writer also treats a missing table as a
best-effort persistence miss without changing the transfer payload returned to
existing consumers. Transfer syncs should still be held until the migration
lands to avoid an evidence gap. Once applied, re-running the guarded upgrade is
a clean no-op.
"""

import sqlalchemy as sa
from alembic import op
from migrations._migration_helpers import (
    create_index_safe,
    index_exists,
    table_exists,
)
from sqlalchemy.dialects.postgresql import JSONB

revision = "tre01"
down_revision = "sea03"
branch_labels = None
depends_on = None


def upgrade():
    if not table_exists("player_transfer_events"):
        op.create_table(
            "player_transfer_events",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("player_api_id", sa.Integer(), nullable=False),
            sa.Column("transfer_date", sa.Date(), nullable=False),
            sa.Column("transfer_type", sa.String(), nullable=True),
            sa.Column("out_club_api_id", sa.Integer(), nullable=True),
            sa.Column("out_club_name", sa.String(), nullable=True),
            sa.Column("in_club_api_id", sa.Integer(), nullable=True),
            sa.Column("in_club_name", sa.String(), nullable=True),
            sa.Column("first_seen_at", sa.TIMESTAMP(timezone=True), nullable=False),
            sa.Column("last_seen_at", sa.TIMESTAMP(timezone=True), nullable=False),
            sa.Column("raw", JSONB(), nullable=True),
            sa.UniqueConstraint(
                "player_api_id",
                "transfer_date",
                "out_club_api_id",
                "in_club_api_id",
                "transfer_type",
                name="uq_player_transfer_events_natural_key",
                postgresql_nulls_not_distinct=True,
            ),
        )

    create_index_safe(
        "ix_player_transfer_events_player_api_id",
        "player_transfer_events",
        ["player_api_id"],
    )

    # Idempotent and intentionally unconditional after the table is guaranteed
    # to exist: the deploy security gate rejects any public table without RLS.
    op.execute("ALTER TABLE player_transfer_events ENABLE ROW LEVEL SECURITY")


def downgrade():
    if index_exists("ix_player_transfer_events_player_api_id"):
        op.drop_index("ix_player_transfer_events_player_api_id", table_name="player_transfer_events")
    if table_exists("player_transfer_events"):
        op.drop_table("player_transfer_events")
