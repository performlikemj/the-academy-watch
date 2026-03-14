"""add newsletters_active to teams

Revision ID: p2q3r4s5t6u7
Revises: n0o1p2q3r4s5
Create Date: 2025-11-09 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'p2q3r4s5t6u7'
down_revision = 'n0o1p2q3r4s5'
branch_labels = None
depends_on = None


def upgrade():
    # Add newsletters_active column to teams table
    op.add_column('teams', sa.Column('newsletters_active', sa.Boolean(), nullable=True))
    # Set default value for existing rows
    op.execute('UPDATE teams SET newsletters_active = FALSE WHERE newsletters_active IS NULL')
    # Make column non-nullable
    op.alter_column('teams', 'newsletters_active', nullable=False, server_default=sa.text('FALSE'))


def downgrade():
    op.drop_column('teams', 'newsletters_active')






