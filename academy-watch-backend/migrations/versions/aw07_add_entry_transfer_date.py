"""Add transfer_date column to player_journey_entries

Revision ID: aw07
Revises: aw06
Create Date: 2026-02-06

Stores the date a player transferred/loaned to a club so we can
determine the actual current club when multiple entries share the
same season and sort priority.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'aw07'
down_revision = 'aw06'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'player_journey_entries',
        sa.Column('transfer_date', sa.String(20), nullable=True),
    )


def downgrade():
    op.drop_column('player_journey_entries', 'transfer_date')
