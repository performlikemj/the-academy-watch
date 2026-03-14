"""Add academy_club_ids column to player_journeys

Revision ID: aw08
Revises: aw07
Create Date: 2026-02-07

Stores a JSON array of API-Football team IDs for clubs where the player
went through the academy (derived from is_youth journey entries).
Enables filtering Browse Teams to show only genuine academy products.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision = 'aw08'
down_revision = 'ac01'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'player_journeys',
        sa.Column('academy_club_ids', JSONB(), nullable=True),
    )
    op.execute(
        "CREATE INDEX ix_player_journeys_academy_club_ids "
        "ON player_journeys USING GIN (academy_club_ids jsonb_path_ops)"
    )


def downgrade():
    op.drop_index('ix_player_journeys_academy_club_ids', table_name='player_journeys')
    op.drop_column('player_journeys', 'academy_club_ids')
