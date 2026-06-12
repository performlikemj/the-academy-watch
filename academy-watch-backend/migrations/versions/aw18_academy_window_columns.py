"""Academy tracking window columns.

- tracked_players.last_academy_season: the player's most recent youth season
  (season-start year) at the parent club — evidence for the current+4-season
  tracking window.
- player_journeys.academy_last_seasons: JSONB map of academy club api id →
  last youth season there, so seed/rebuild paths can window-gate candidates
  without re-resolving youth entries.

Revision ID: aw18
Revises: aw17
"""

import sqlalchemy as sa
from alembic import op
from migrations._migration_helpers import add_column_safe, column_exists
from sqlalchemy.dialects import postgresql

revision = "aw18"
down_revision = "aw17"
branch_labels = None
depends_on = None


def upgrade():
    add_column_safe("tracked_players", sa.Column("last_academy_season", sa.Integer(), nullable=True))
    add_column_safe(
        "player_journeys",
        sa.Column("academy_last_seasons", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade():
    if column_exists("tracked_players", "last_academy_season"):
        op.drop_column("tracked_players", "last_academy_season")
    if column_exists("player_journeys", "academy_last_seasons"):
        op.drop_column("player_journeys", "academy_last_seasons")
