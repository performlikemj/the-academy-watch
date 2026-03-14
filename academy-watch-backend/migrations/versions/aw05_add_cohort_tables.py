"""Add academy cohort tables

Revision ID: aw05
Revises: aw04
Create Date: 2026-02-06

Creates academy_cohorts and cohort_members tables for tracking
groups of academy players and their career outcomes.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'aw05'
down_revision = 'f4e3f4f949de'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'academy_cohorts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('team_api_id', sa.Integer(), nullable=False),
        sa.Column('team_name', sa.String(200), nullable=True),
        sa.Column('team_logo', sa.String(500), nullable=True),
        sa.Column('league_api_id', sa.Integer(), nullable=False),
        sa.Column('league_name', sa.String(200), nullable=True),
        sa.Column('league_level', sa.String(30), nullable=True),
        sa.Column('season', sa.Integer(), nullable=False),

        # Analytics
        sa.Column('total_players', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('players_first_team', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('players_on_loan', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('players_still_academy', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('players_released', sa.Integer(), nullable=True, server_default='0'),

        # Sync tracking
        sa.Column('sync_status', sa.String(30), nullable=True, server_default='pending'),
        sa.Column('seeded_at', sa.DateTime(), nullable=True),
        sa.Column('journeys_synced_at', sa.DateTime(), nullable=True),
        sa.Column('seed_job_id', sa.String(36), nullable=True),
        sa.Column('sync_error', sa.Text(), nullable=True),

        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),

        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('team_api_id', 'league_api_id', 'season',
                            name='uq_academy_cohort'),
    )

    op.create_index('ix_academy_cohorts_team', 'academy_cohorts', ['team_api_id'])

    op.create_table(
        'cohort_members',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cohort_id', sa.Integer(), nullable=False),

        # Player identity
        sa.Column('player_api_id', sa.Integer(), nullable=False),
        sa.Column('player_name', sa.String(200), nullable=True),
        sa.Column('player_photo', sa.String(500), nullable=True),
        sa.Column('nationality', sa.String(100), nullable=True),
        sa.Column('birth_date', sa.String(20), nullable=True),
        sa.Column('position', sa.String(50), nullable=True),

        # Cohort stats
        sa.Column('appearances_in_cohort', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('goals_in_cohort', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('assists_in_cohort', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('minutes_in_cohort', sa.Integer(), nullable=True, server_default='0'),

        # Current snapshot
        sa.Column('current_club_api_id', sa.Integer(), nullable=True),
        sa.Column('current_club_name', sa.String(200), nullable=True),
        sa.Column('current_level', sa.String(30), nullable=True),
        sa.Column('current_status', sa.String(30), nullable=True, server_default="'unknown'"),

        # Career milestones
        sa.Column('first_team_debut_season', sa.Integer(), nullable=True),
        sa.Column('total_first_team_apps', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('total_clubs', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('total_loan_spells', sa.Integer(), nullable=True, server_default='0'),

        # Journey FK
        sa.Column('journey_id', sa.Integer(), nullable=True),

        # Sync tracking
        sa.Column('journey_synced', sa.Boolean(), nullable=True, server_default='false'),
        sa.Column('journey_sync_error', sa.Text(), nullable=True),

        sa.Column('created_at', sa.DateTime(), nullable=True),

        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['cohort_id'], ['academy_cohorts.id']),
        sa.ForeignKeyConstraint(['journey_id'], ['player_journeys.id']),
        sa.UniqueConstraint('cohort_id', 'player_api_id', name='uq_cohort_member'),
    )

    op.create_index('ix_cohort_members_cohort', 'cohort_members', ['cohort_id'])
    op.create_index('ix_cohort_members_player', 'cohort_members', ['player_api_id'])


def downgrade():
    op.drop_index('ix_cohort_members_player', 'cohort_members')
    op.drop_index('ix_cohort_members_cohort', 'cohort_members')
    op.drop_table('cohort_members')
    op.drop_index('ix_academy_cohorts_team', 'academy_cohorts')
    op.drop_table('academy_cohorts')
