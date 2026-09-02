"""Store exact birth dates for local-player adulthood decisions.

Revision ID: lp01
Revises: bx01
Create Date: 2026-09-02

Both directions are guarded because production has drifted out-of-band.

Production pre-apply DDL::

    ALTER TABLE public.local_players ADD COLUMN IF NOT EXISTS birth_date DATE;
"""

import sqlalchemy as sa
from alembic import op
from migrations._migration_helpers import column_exists, table_exists

revision = "lp01"
down_revision = "bx01"
branch_labels = None
depends_on = None

TABLE = "local_players"
COLUMN = "birth_date"


def upgrade():
    if table_exists(TABLE) and not column_exists(TABLE, COLUMN):
        op.add_column(TABLE, sa.Column(COLUMN, sa.Date(), nullable=True))


def downgrade():
    if table_exists(TABLE) and column_exists(TABLE, COLUMN):
        op.drop_column(TABLE, COLUMN)
