"""merge heads

Revision ID: d1b517ce47c1
Revises: cu01, z8_rename
Create Date: 2026-03-22 00:38:26.210432

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd1b517ce47c1'
down_revision = ('cu01', 'z8_rename')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
