"""Private development actions and revision-scoped progress.

Revision ID: s4d1
Revises: s4c1
"""

import sqlalchemy as sa
from alembic import op
from migrations._migration_helpers import column_exists, table_exists

revision = "s4d1"
down_revision = "s4c1"
branch_labels = None
depends_on = None


def upgrade():
    if not table_exists("player_feedback"):
        raise RuntimeError("player_feedback must exist before s4d1")
    for name in ("development_action", "development_progress"):
        if not column_exists("player_feedback", name):
            op.add_column("player_feedback", sa.Column(name, sa.JSON(), nullable=True))


def downgrade():
    if table_exists("player_feedback"):
        for name in ("development_progress", "development_action"):
            if column_exists("player_feedback", name):
                op.drop_column("player_feedback", name)
