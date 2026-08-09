"""Add a self-reported club name to local players.

Revision ID: ob01
Revises: ug01
Create Date: 2026-08-09

``ug01`` was the sole Alembic head when this migration was authored. If another
migration lands first, re-point ``down_revision`` before merge. Never allow a
migration fork.

All DDL is guarded because production has drifted out-of-band. ``local_players``
is an existing RLS-enabled table, so this migration does not create or expose a
new public table.

DEPLOY ORDERING (migrations do NOT auto-run): pre-apply ``ob01`` via the
PostgreSQL pooler before deploying application code that writes ``club_name``.
Re-running the guarded upgrade is a clean no-op.
"""

import sqlalchemy as sa
from alembic import op
from migrations._migration_helpers import add_column_safe, column_exists, table_exists

revision = "ob01"
down_revision = "ug01"
branch_labels = None
depends_on = None

TABLE = "local_players"
COLUMN = "club_name"


def upgrade():
    if table_exists(TABLE):
        add_column_safe(TABLE, sa.Column(COLUMN, sa.String(length=200), nullable=True))


def downgrade():
    if table_exists(TABLE) and column_exists(TABLE, COLUMN):
        op.drop_column(TABLE, COLUMN)
