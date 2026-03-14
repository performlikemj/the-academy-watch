"""Merge newsletter and supplemental loan heads

Revision ID: ab12cd34ef56
Revises: 7d2c3e4f5a6b, 9g0b1c2d3e4f
Create Date: 2025-10-07 17:20:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ab12cd34ef56'
down_revision = ('7d2c3e4f5a6b', '9g0b1c2d3e4f')
branch_labels = None
depends_on = None


def upgrade():
    """No-op merge to reconcile divergent heads."""
    pass


def downgrade():
    """Downgrade simply splits the heads again."""
    pass
