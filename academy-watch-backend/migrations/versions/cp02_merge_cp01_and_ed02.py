"""Merge cp01 and ed02 heads

Revision ID: cp02
Revises: cp01, ed02
Create Date: 2025-01-07
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'cp02'
down_revision = ('cp01', 'ed02')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
