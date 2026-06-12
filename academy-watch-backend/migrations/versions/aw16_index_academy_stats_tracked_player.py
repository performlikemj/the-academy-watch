"""Index academy_player_season_stats.tracked_player_id

Revision ID: aw16
Revises: aw15
Create Date: 2026-06-12

The newsletter academy-watch query joins TrackedPlayer to
AcademyPlayerSeasonStats via OR(tracked_player_id, player_api_id);
player_api_id is already indexed, but tracked_player_id was not —
indexing it measured a 14x speedup on the OR-join.
"""

from alembic import op
from migrations._migration_helpers import create_index_safe, index_exists

revision = "aw16"
down_revision = "aw15"
branch_labels = None
depends_on = None


def upgrade():
    create_index_safe("ix_apss_tracked_player", "academy_player_season_stats", ["tracked_player_id"])


def downgrade():
    if index_exists("ix_apss_tracked_player"):
        op.drop_index("ix_apss_tracked_player", table_name="academy_player_season_stats")
