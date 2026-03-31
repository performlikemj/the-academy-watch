"""rename loan_club columns to current_club on tracked_players

Revision ID: z8_rename
Revises: z7_fees
Create Date: 2026-03-17

"""
from alembic import op
from migrations.versions._migration_helpers import column_exists


# revision identifiers, used by Alembic.
revision = 'z8_rename'
down_revision = 'z7_fees'
branch_labels = None
depends_on = None


def upgrade():
    if column_exists('tracked_players', 'loan_club_api_id'):
        op.alter_column('tracked_players', 'loan_club_api_id',
                        new_column_name='current_club_api_id')
    if column_exists('tracked_players', 'loan_club_name'):
        op.alter_column('tracked_players', 'loan_club_name',
                        new_column_name='current_club_name')


def downgrade():
    op.alter_column('tracked_players', 'current_club_api_id',
                    new_column_name='loan_club_api_id')
    op.alter_column('tracked_players', 'current_club_name',
                    new_column_name='loan_club_name')
