"""Manual transfer-entry audit trail.

Revision ID: td01
Revises: shp05
Create Date: 2026-07-23

``shp05`` was the sole Alembic head on refreshed ``origin/main`` when this
migration was authored. If another head lands first, re-point ``down_revision``
before merge. Never allow a migration fork.

Manual transfer provenance remains in ``player_transfer_events.raw`` so the
stored fact keeps the exact API-Football-compatible shape consumed by the
chronological resolver. This migration adds only the append-only admin audit
surface. All DDL is guarded because production has drifted out-of-band, and the
new public table enables Row Level Security in this same migration. Downgrade
refuses to discard audit history.

DEPLOY ORDERING (migrations do NOT auto-run): pre-apply ``td01`` before
deploying the writer route. The route and audit row commit atomically, so code
must not accept a manual transfer while its audit table is unavailable.
Re-running the guarded upgrade is a clean no-op.
"""

import sqlalchemy as sa
from alembic import op
from migrations._migration_helpers import create_index_safe, index_exists, table_exists

revision = "td01"
down_revision = "shp05"
branch_labels = None
depends_on = None

TABLE = "transfer_admin_events"
TRANSFER_INDEX = "ix_transfer_admin_events_transfer_event"
PLAYER_CREATED_INDEX = "ix_transfer_admin_events_player_created"


def _table_has_rows() -> bool:
    return bool(op.get_bind().execute(sa.text(f'SELECT EXISTS (SELECT 1 FROM "{TABLE}")')).scalar())


def upgrade():
    if not table_exists(TABLE):
        op.create_table(
            TABLE,
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column(
                "transfer_event_id",
                sa.BigInteger(),
                sa.ForeignKey("player_transfer_events.id"),
                nullable=False,
            ),
            sa.Column("player_api_id", sa.Integer(), nullable=False),
            sa.Column("actor_email", sa.String(length=254), nullable=False),
            sa.Column("action", sa.String(length=80), nullable=False),
            sa.Column("source_note", sa.Text(), nullable=False),
            sa.Column("event_metadata", sa.JSON(), nullable=False),
            sa.Column(
                "created_at",
                sa.TIMESTAMP(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )

    if table_exists(TABLE):
        create_index_safe(
            TRANSFER_INDEX,
            TABLE,
            ["transfer_event_id"],
        )
        create_index_safe(
            PLAYER_CREATED_INDEX,
            TABLE,
            ["player_api_id", "created_at"],
        )
        op.execute(sa.text(f'ALTER TABLE "{TABLE}" ENABLE ROW LEVEL SECURITY'))


def downgrade():
    if table_exists(TABLE) and _table_has_rows():
        raise RuntimeError("td01 downgrade refused: manual transfer audit history exists")
    if table_exists(TABLE):
        if index_exists(PLAYER_CREATED_INDEX):
            op.drop_index(PLAYER_CREATED_INDEX, table_name=TABLE)
        if index_exists(TRANSFER_INDEX):
            op.drop_index(TRANSFER_INDEX, table_name=TABLE)
        op.drop_table(TABLE)
