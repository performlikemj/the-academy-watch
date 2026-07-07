"""Widen player_journey_entries with rich per-season stats + read-path index

Revision ID: sea01
Revises: aw23
Create Date: 2026-07-07

The journey sync already fetches the full API-Football `players?id&season`
statistics block per season but persists only 4 fields (appearances, goals,
assists, minutes). This widens player_journey_entries so that same free payload
can be banked as a durable per-season archive (api_cache TTL is only 7 days, so
the raw response is otherwise lost). All columns are nullable and guarded via
add_column_safe — prod schema has drifted out-of-band, and a re-applied or
partially-applied DDL must never crash `flask db upgrade` on deploy.

Also adds one index the seasons work needs on the denormalized read path:
  ix_pje_player_season     — player_journey_entries(player_api_id, season) for
                             the per-player-per-season reads.

fixture_player_stats(player_api_id) is deliberately NOT indexed separately here:
aw15's composite ix_fps_player_team already leads on player_api_id, so every
per-player FPS scan is index-served. A single-column duplicate would only add
write overhead on the hottest write table.

ADD COLUMN does not touch RLS, and player_journey_entries already has RLS
enabled, so no RLS statement is needed here.

DEPLOY ORDERING (migrations do NOT auto-run — deploy.yml only runs the RLS
security-check; the container CMD is gunicorn, nothing runs `flask db upgrade`).
The shipped ORM model declares these 28 columns, so the moment the new image takes
traffic every read of PlayerJourneyEntry SELECTs them; if the DDL is not yet applied
that is psycopg UndefinedColumn -> 500 on all journey / D1-provenance surfaces.
Chosen sequence: PRE-APPLY this migration out-of-band against prod BEFORE merging —
from a local checkout with the prod DB env (IPv4 pooler + `postgresql+psycopg://`,
invariants #1) run `FLASK_APP=src/main.py flask db upgrade`. ADD COLUMN is a
metadata-only instant op in Postgres; the single CREATE INDEX (ix_pje_player_season)
is the only real work.
Then merge: when CI deploys the image the columns already exist -> zero 500 window,
and the manual in-container `flask db upgrade` is a pure no-op stamp (all DDL guarded
via *_safe / index_exists). Fallback if pre-apply is skipped: run `flask db upgrade`
in the container immediately after the deploy goes green and accept the brief window.
"""

import sqlalchemy as sa
from alembic import op
from migrations._migration_helpers import (
    add_column_safe,
    column_exists,
    create_index_safe,
    index_exists,
)

revision = "sea01"
down_revision = "aw23"
branch_labels = None
depends_on = None


# (name, SQLAlchemy type) for every column added to player_journey_entries.
# All nullable; stats_source carries a server default so pre-existing rows read
# as 'legacy-basic' (they predate the wider extraction).
_COLUMNS = [
    ("player_api_id", sa.Integer()),
    ("rating", sa.Float()),
    ("position", sa.String(length=10)),
    ("lineups", sa.Integer()),
    ("shots_total", sa.Integer()),
    ("shots_on", sa.Integer()),
    ("passes_total", sa.Integer()),
    ("passes_key", sa.Integer()),
    ("passes_accuracy", sa.Integer()),
    ("tackles_total", sa.Integer()),
    ("tackles_blocks", sa.Integer()),
    ("tackles_interceptions", sa.Integer()),
    ("duels_total", sa.Integer()),
    ("duels_won", sa.Integer()),
    ("dribbles_attempts", sa.Integer()),
    ("dribbles_success", sa.Integer()),
    ("fouls_drawn", sa.Integer()),
    ("fouls_committed", sa.Integer()),
    ("cards_yellow", sa.Integer()),
    ("cards_red", sa.Integer()),
    ("penalty_scored", sa.Integer()),
    ("penalty_missed", sa.Integer()),
    ("penalty_saved", sa.Integer()),
    ("goals_conceded", sa.Integer()),
    ("saves", sa.Integer()),
    ("season_phase", sa.String(length=12)),
    ("stats_synced_at", sa.TIMESTAMP(timezone=True)),
]


def upgrade():
    for name, col_type in _COLUMNS:
        add_column_safe("player_journey_entries", sa.Column(name, col_type, nullable=True))

    # stats_source has a server default so existing rows backfill to 'legacy-basic'.
    add_column_safe(
        "player_journey_entries",
        sa.Column("stats_source", sa.String(length=24), nullable=True, server_default="legacy-basic"),
    )

    # fixture_player_stats(player_api_id) needs no index here — aw15's
    # ix_fps_player_team (player_api_id, team_api_id) already covers player-only scans.
    create_index_safe("ix_pje_player_season", "player_journey_entries", ["player_api_id", "season"])


def downgrade():
    if index_exists("ix_pje_player_season"):
        op.drop_index("ix_pje_player_season", table_name="player_journey_entries")

    for name, _ in [*_COLUMNS, ("stats_source", None)]:
        if column_exists("player_journey_entries", name):
            op.drop_column("player_journey_entries", name)
