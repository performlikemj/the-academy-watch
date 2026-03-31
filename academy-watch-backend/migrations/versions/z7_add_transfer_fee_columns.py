"""add transfer fee columns to tracked_players and player_journey_entries

Revision ID: z7_fees
Revises: z6b7c8d9e0f1
Create Date: 2026-03-16

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'z7_fees'
down_revision = 'z6b7c8d9e0f1'
branch_labels = None
depends_on = None


def _column_exists(table, column):
    """Check if a column already exists (handles out-of-band additions)."""
    from alembic import op as _op
    conn = _op.get_bind()
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = :table AND column_name = :column"
    ), {'table': table, 'column': column})
    return result.scalar() is not None


def upgrade():
    if not _column_exists('tracked_players', 'sale_fee'):
        op.add_column('tracked_players', sa.Column('sale_fee', sa.String(100), nullable=True))
    if not _column_exists('player_journey_entries', 'transfer_fee'):
        op.add_column('player_journey_entries', sa.Column('transfer_fee', sa.String(100), nullable=True))


def downgrade():
    op.drop_column('player_journey_entries', 'transfer_fee')
    op.drop_column('tracked_players', 'sale_fee')
