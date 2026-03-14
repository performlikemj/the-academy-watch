"""Add journalist attribution fields

Revision ID: ja01
Revises: wc01
Create Date: 2025-12-27
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'ja01'
down_revision = '9872f1adcb09'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('user_accounts', sa.Column('attribution_url', sa.String(length=500), nullable=True))
    op.add_column('user_accounts', sa.Column('attribution_name', sa.String(length=120), nullable=True))


def downgrade():
    op.drop_column('user_accounts', 'attribution_name')
    op.drop_column('user_accounts', 'attribution_url')
