"""Index fixtures.season

Revision ID: aw23
Revises: aw22
Create Date: 2026-07-07

stats_season_with_data() runs `SELECT id FROM fixtures WHERE season = :s LIMIT 1`
(plus a MAX(season) fallback in the rollover gap), and every season-scoped stats,
chart, and radar query filters `Fixture.season == season`. fixtures.season was
unindexed, so each of those was a near-full seq scan of ~20k rows — worse for the
current season whose rows sit at the heap tail. On the 0.5 CPU prod container this
cost tens of ms per request and seconds per newsletter render (many players x
multiple chart calls). Guarded so it is a no-op if the index was added out-of-band.
"""

from alembic import op
from migrations._migration_helpers import create_index_safe, index_exists

revision = "aw23"
down_revision = "aw22"
branch_labels = None
depends_on = None


def upgrade():
    create_index_safe("ix_fixtures_season", "fixtures", ["season"])


def downgrade():
    if index_exists("ix_fixtures_season"):
        op.drop_index("ix_fixtures_season", table_name="fixtures")
