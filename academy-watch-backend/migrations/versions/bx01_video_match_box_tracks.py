"""Persist the box-track blob path on video matches.

Revision ID: bx01
Revises: jk01
Create Date: 2026-09-02

Both directions are guarded because production has drifted out-of-band.
"""

import sqlalchemy as sa
from alembic import op
from migrations._migration_helpers import add_column_safe, column_exists, table_exists

revision = "bx01"
down_revision = "jk01"
branch_labels = None
depends_on = None

TABLE = "video_matches"
COLUMN = "boxes_blob_path"


def upgrade():
    if table_exists(TABLE):
        add_column_safe(TABLE, sa.Column(COLUMN, sa.String(255), nullable=True))


def downgrade():
    if table_exists(TABLE) and column_exists(TABLE, COLUMN):
        op.drop_column(TABLE, COLUMN)
