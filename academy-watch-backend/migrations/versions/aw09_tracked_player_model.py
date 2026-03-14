"""Create tracked_players table

Revision ID: aw09
Revises: aw08
Create Date: 2026-02-07

New TrackedPlayer model for the Academy Watch redesign.
One row per player per parent club — replaces per-window LoanedPlayer duplication.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'aw09'
down_revision = 'aw08'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'tracked_players',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('player_api_id', sa.Integer(), nullable=False, index=True),
        sa.Column('player_name', sa.String(200), nullable=False),
        sa.Column('photo_url', sa.String(500)),
        sa.Column('position', sa.String(50)),
        sa.Column('nationality', sa.String(100)),
        sa.Column('birth_date', sa.String(20)),
        sa.Column('age', sa.Integer()),
        sa.Column('team_id', sa.Integer(), sa.ForeignKey('teams.id'), nullable=False, index=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='academy'),
        sa.Column('current_level', sa.String(20)),
        sa.Column('loan_club_api_id', sa.Integer()),
        sa.Column('loan_club_name', sa.String(200)),
        sa.Column('data_source', sa.String(30), nullable=False, server_default='api-football'),
        sa.Column('data_depth', sa.String(20), nullable=False, server_default='full_stats'),
        sa.Column('journey_id', sa.Integer(), sa.ForeignKey('player_journeys.id')),
        sa.Column('notes', sa.Text()),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint('player_api_id', 'team_id', name='uq_tracked_player_team'),
    )


def downgrade():
    op.drop_table('tracked_players')
