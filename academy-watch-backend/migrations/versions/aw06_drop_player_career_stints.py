"""Drop deprecated player_career_stints table

Revision ID: aw06
Revises: aw05
Create Date: 2026-02-06

The PlayerCareerStint model has been superseded by PlayerJourney +
PlayerJourneyEntry which provide richer career data sourced from
API-Football's season history.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'aw06'
down_revision = 'aw05'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_table('player_career_stints')


def downgrade():
    op.create_table(
        'player_career_stints',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('player_id', sa.Integer(), nullable=False, index=True),
        sa.Column('player_name', sa.String(100), nullable=False),
        sa.Column('loaned_player_id', sa.Integer(), sa.ForeignKey('loaned_players.id'), nullable=True),
        sa.Column('team_api_id', sa.Integer(), nullable=False),
        sa.Column('team_name', sa.String(100), nullable=False),
        sa.Column('team_logo', sa.String(255)),
        sa.Column('city', sa.String(100)),
        sa.Column('country', sa.String(100)),
        sa.Column('latitude', sa.Float()),
        sa.Column('longitude', sa.Float()),
        sa.Column('stint_type', sa.String(20), nullable=False),
        sa.Column('level', sa.String(20)),
        sa.Column('start_date', sa.Date()),
        sa.Column('end_date', sa.Date()),
        sa.Column('is_current', sa.Boolean(), default=False),
        sa.Column('sequence', sa.Integer(), nullable=False, default=1),
        sa.Column('created_at', sa.DateTime()),
        sa.Column('updated_at', sa.DateTime()),
        sa.UniqueConstraint('player_id', 'team_api_id', 'stint_type', 'sequence',
                           name='uq_player_career_stint'),
    )
