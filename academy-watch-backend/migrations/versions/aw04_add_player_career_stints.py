"""Add player career stints table for journey map

Revision ID: aw04
Revises: aw03
Create Date: 2026-02-05

Creates the player_career_stints table to track each stop in a player's
career journey (academy -> loans -> first team) with geographic coordinates
for map visualization.
"""
from alembic import op
import sqlalchemy as sa
from migrations._migration_helpers import table_exists, create_index_safe


# revision identifiers, used by Alembic.
revision = 'aw04'
down_revision = 'aw03'
branch_labels = None
depends_on = None


def upgrade():
    if not table_exists('player_career_stints'):
        op.create_table(
            'player_career_stints',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('player_id', sa.Integer(), nullable=False),
            sa.Column('player_name', sa.String(100), nullable=False),
            sa.Column('loaned_player_id', sa.Integer(), nullable=True),
            sa.Column('team_api_id', sa.Integer(), nullable=False),
            sa.Column('team_name', sa.String(100), nullable=False),
            sa.Column('team_logo', sa.String(255), nullable=True),
            sa.Column('city', sa.String(100), nullable=True),
            sa.Column('country', sa.String(100), nullable=True),
            sa.Column('latitude', sa.Float(), nullable=True),
            sa.Column('longitude', sa.Float(), nullable=True),
            sa.Column('stint_type', sa.String(20), nullable=False),
            sa.Column('level', sa.String(20), nullable=True),
            sa.Column('start_date', sa.Date(), nullable=True),
            sa.Column('end_date', sa.Date(), nullable=True),
            sa.Column('is_current', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('sequence', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['loaned_player_id'], ['loaned_players.id']),
            sa.UniqueConstraint('player_id', 'team_api_id', 'stint_type', 'sequence',
                              name='uq_player_career_stint'),
        )

    create_index_safe('ix_player_career_stints_player', 'player_career_stints', ['player_id'])
    create_index_safe('ix_player_career_stints_loaned_player', 'player_career_stints', ['loaned_player_id'])


def downgrade():
    op.drop_index('ix_player_career_stints_loaned_player', 'player_career_stints')
    op.drop_index('ix_player_career_stints_player', 'player_career_stints')
    op.drop_table('player_career_stints')
