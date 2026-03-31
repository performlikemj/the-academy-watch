"""Drop loaned_players and supplemental_loans tables

Revision ID: aw13
Revises: aw12
Create Date: 2026-03-31

Final cleanup: removes the legacy AcademyPlayer (loaned_players) and
SupplementalLoan (supplemental_loans) tables. All data has been
migrated to TrackedPlayer.
"""
from alembic import op
import sqlalchemy as sa
from migrations._migration_helpers import table_exists


# revision identifiers, used by Alembic.
revision = 'aw13'
down_revision = 'aw12'
branch_labels = None
depends_on = None


def upgrade():
    if table_exists('supplemental_loans'):
        op.drop_table('supplemental_loans')
    if table_exists('loaned_players'):
        op.drop_table('loaned_players')


def downgrade():
    # Recreate loaned_players (minimal schema for rollback)
    op.create_table(
        'loaned_players',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('player_id', sa.Integer(), nullable=False),
        sa.Column('player_name', sa.String(100), nullable=False),
        sa.Column('primary_team_id', sa.Integer(), nullable=True),
        sa.Column('primary_team_name', sa.String(100), nullable=False),
        sa.Column('loan_team_id', sa.Integer(), nullable=True),
        sa.Column('loan_team_name', sa.String(100), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('created_at', sa.DateTime()),
        sa.Column('updated_at', sa.DateTime()),
    )

    op.create_table(
        'supplemental_loans',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('player_name', sa.String(120), nullable=False),
        sa.Column('parent_team_name', sa.String(120), nullable=False),
        sa.Column('loan_team_name', sa.String(120), nullable=False),
        sa.Column('season_year', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime()),
        sa.Column('updated_at', sa.DateTime()),
    )
