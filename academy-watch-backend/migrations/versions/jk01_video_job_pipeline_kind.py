"""Persist the pipeline kind on video analysis jobs.

Revision ID: jk01
Revises: sw01
Create Date: 2026-08-31

DDL is guarded because production has drifted out-of-band; re-running either
direction is a clean no-op.
"""

import sqlalchemy as sa
from alembic import op
from migrations._migration_helpers import add_column_safe, column_exists, table_exists

revision = "jk01"
down_revision = "sw01"
branch_labels = None
depends_on = None

TABLE = "video_analysis_jobs"
COLUMN = "pipeline_kind"


def upgrade():
    if table_exists(TABLE):
        add_column_safe(
            TABLE,
            sa.Column(COLUMN, sa.String(30), nullable=False, server_default="cv"),
        )


def downgrade():
    if table_exists(TABLE) and column_exists(TABLE, COLUMN):
        op.drop_column(TABLE, COLUMN)
