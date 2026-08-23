"""Index scout_watchlist_entries.player_api_id for per-player lookups.

Revision ID: sw01
Revises: c201
Create Date: 2026-08-23

``c201`` was the sole Alembic head when this was written (verified 2026-08-23). If another migration
lands first, re-point ``down_revision`` before merge. Never allow a migration fork.

DDL is guarded because production has drifted out-of-band; re-running the upgrade is a clean no-op.
"""

from alembic import op
from migrations._migration_helpers import create_index_safe, index_exists, table_exists

revision = "sw01"
down_revision = "c201"
branch_labels = None
depends_on = None

TABLE = "scout_watchlist_entries"
INDEX = "ix_scout_watchlist_player"


def upgrade():
    if table_exists(TABLE):
        create_index_safe(INDEX, TABLE, ["player_api_id"])


def downgrade():
    if table_exists(TABLE) and index_exists(INDEX):
        op.drop_index(INDEX, table_name=TABLE)
