"""merge_sponsors_and_saves_heads

Revision ID: a5632964f34c
Revises: sp01_sponsors, sv01_add_saves
Create Date: 2025-12-01 17:02:09.567869

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a5632964f34c'
down_revision = ('sp01_sponsors', 'sv01_add_saves')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
