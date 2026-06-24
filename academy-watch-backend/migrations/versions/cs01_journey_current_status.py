"""Player-level current_status on player_journeys.

The player's ACTUAL current situation (on loan / etc.), independent of any
tracked academy. TrackedPlayer.status is RELATIVE to a parent academy, so a
departed academy product reads 'left'/'sold' there even while he is really on
loan from a club the platform doesn't track as his academy (e.g. Rijkhoff:
Dortmund academy product, on loan from Ajax). current_status overrides the
academy-relative status for player-facing surfaces; NULL defers to it.

- player_journeys.current_status: e.g. 'on_loan' (NULL = defer to academy row).
- player_journeys.current_owner_api_id / current_owner_name: the club the player
  is on loan FROM (for "on loan from <owner>").

Idempotent (add_column_safe) — prod columns are also added out-of-band, so a
re-run is a no-op.

Revision ID: cs01
Revises: aw18
"""

import sqlalchemy as sa
from migrations._migration_helpers import add_column_safe, column_exists
from alembic import op

revision = "cs01"
down_revision = "aw18"
branch_labels = None
depends_on = None


def upgrade():
    add_column_safe("player_journeys", sa.Column("current_status", sa.String(length=20), nullable=True))
    add_column_safe("player_journeys", sa.Column("current_owner_api_id", sa.Integer(), nullable=True))
    add_column_safe("player_journeys", sa.Column("current_owner_name", sa.String(length=200), nullable=True))


def downgrade():
    for col in ("current_status", "current_owner_api_id", "current_owner_name"):
        if column_exists("player_journeys", col):
            op.drop_column("player_journeys", col)
