"""add transfer fee columns to tracked_players and player_journey_entries

Revision ID: z7_fees
Revises: z6b7c8d9e0f1
Create Date: 2026-03-16

"""
from alembic import op
import sqlalchemy as sa
from migrations._migration_helpers import add_column_safe


# revision identifiers, used by Alembic.
revision = 'z7_fees'
down_revision = 'z6b7c8d9e0f1'
branch_labels = None
depends_on = None


def upgrade():
    add_column_safe('tracked_players', sa.Column('sale_fee', sa.String(100), nullable=True))
    add_column_safe('player_journey_entries', sa.Column('transfer_fee', sa.String(100), nullable=True))


def downgrade():
    op.drop_column('player_journey_entries', 'transfer_fee')
    op.drop_column('tracked_players', 'sale_fee')
