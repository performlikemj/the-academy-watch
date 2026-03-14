"""Add is_curator flag to user_accounts

Revision ID: cu01
Revises: pl01
Create Date: 2026-03-11

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'cu01'
down_revision = 'pl01'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('user_accounts', sa.Column('is_curator', sa.Boolean(), nullable=False, server_default=sa.text('false')))


def downgrade():
    op.drop_column('user_accounts', 'is_curator')
