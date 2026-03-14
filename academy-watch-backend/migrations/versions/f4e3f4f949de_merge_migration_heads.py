"""merge_migration_heads

Revision ID: f4e3f4f949de
Revises: aw04, x2y3z4a5b6c7
Create Date: 2026-02-06 09:43:49.921252

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f4e3f4f949de'
down_revision = ('aw04', 'x2y3z4a5b6c7')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
