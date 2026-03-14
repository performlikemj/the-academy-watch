"""add api_confirmed_at to loaned_players

Revision ID: z6b7c8d9e0f1
Revises: wc01_add_writer_coverage_tables
Create Date: 2026-01-10

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'z6b7c8d9e0f1'
down_revision = 'cp02'
branch_labels = None
depends_on = None


def upgrade():
    # Add api_confirmed_at column to loaned_players
    # This tracks when API data confirmed a manually-entered loan
    op.add_column('loaned_players', sa.Column('api_confirmed_at', sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column('loaned_players', 'api_confirmed_at')
