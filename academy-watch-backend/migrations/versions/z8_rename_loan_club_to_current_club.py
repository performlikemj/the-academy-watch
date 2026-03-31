"""rename loan_club columns to current_club on tracked_players

Revision ID: z8_rename
Revises: z7_fees
Create Date: 2026-03-17

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'z8_rename'
down_revision = 'z7_fees'
branch_labels = None
depends_on = None


def _column_exists(table, column):
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = :table AND column_name = :column"
    ), {'table': table, 'column': column})
    return result.scalar() is not None


def upgrade():
    # Skip if already renamed (columns were applied out-of-band)
    if _column_exists('tracked_players', 'loan_club_api_id'):
        op.alter_column('tracked_players', 'loan_club_api_id',
                        new_column_name='current_club_api_id')
    if _column_exists('tracked_players', 'loan_club_name'):
        op.alter_column('tracked_players', 'loan_club_name',
                        new_column_name='current_club_name')


def downgrade():
    op.alter_column('tracked_players', 'current_club_api_id',
                    new_column_name='loan_club_api_id')
    op.alter_column('tracked_players', 'current_club_name',
                    new_column_name='loan_club_name')
