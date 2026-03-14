"""Add academy tracking tables

Revision ID: aw03
Revises: aw02
Create Date: 2026-01-30

Part of The Academy Watch refactor Phase 4. Creates tables for tracking
academy/youth player appearances:
- academy_leagues: Configuration for which youth leagues to sync
- academy_appearances: Player appearances in academy matches
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'aw03'
down_revision = 'aw02'
branch_labels = None
depends_on = None


def upgrade():
    # Create academy_leagues table
    op.create_table(
        'academy_leagues',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('api_league_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('country', sa.String(100), nullable=True),
        sa.Column('level', sa.String(20), nullable=False),
        sa.Column('season', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('parent_team_id', sa.Integer(), nullable=True),
        sa.Column('last_synced_at', sa.DateTime(), nullable=True),
        sa.Column('sync_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('api_league_id'),
        sa.ForeignKeyConstraint(['parent_team_id'], ['teams.id']),
    )

    # Create academy_appearances table
    op.create_table(
        'academy_appearances',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('player_id', sa.Integer(), nullable=False),
        sa.Column('player_name', sa.String(100), nullable=False),
        sa.Column('fixture_id', sa.Integer(), nullable=False),
        sa.Column('fixture_date', sa.Date(), nullable=False),
        sa.Column('home_team', sa.String(100), nullable=True),
        sa.Column('away_team', sa.String(100), nullable=True),
        sa.Column('competition', sa.String(100), nullable=True),
        sa.Column('academy_league_id', sa.Integer(), nullable=True),
        sa.Column('loaned_player_id', sa.Integer(), nullable=True),
        sa.Column('started', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('minutes_played', sa.Integer(), nullable=True),
        sa.Column('goals', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('assists', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('yellow_cards', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('red_cards', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('lineup_data', sa.JSON(), nullable=True),
        sa.Column('events_data', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['academy_league_id'], ['academy_leagues.id']),
        sa.ForeignKeyConstraint(['loaned_player_id'], ['loaned_players.id']),
        sa.UniqueConstraint('player_id', 'fixture_id', name='uq_academy_appearance_player_fixture'),
    )

    # Create indexes for academy_appearances
    op.create_index('ix_academy_appearances_player', 'academy_appearances', ['player_id'])
    op.create_index('ix_academy_appearances_fixture_date', 'academy_appearances', ['fixture_date'])
    op.create_index('ix_academy_appearances_loaned_player', 'academy_appearances', ['loaned_player_id'])


def downgrade():
    # Drop academy_appearances indexes and table
    op.drop_index('ix_academy_appearances_loaned_player', 'academy_appearances')
    op.drop_index('ix_academy_appearances_fixture_date', 'academy_appearances')
    op.drop_index('ix_academy_appearances_player', 'academy_appearances')
    op.drop_table('academy_appearances')

    # Drop academy_leagues table
    op.drop_table('academy_leagues')
