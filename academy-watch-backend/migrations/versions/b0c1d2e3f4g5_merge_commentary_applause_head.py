"""merge heads after adding commentary_applause

Revision ID: b0c1d2e3f4g5
Revises: 4398c3e41831, a7b8c9d0e1f2
Create Date: 2025-11-24 08:13:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b0c1d2e3f4g5"
down_revision = ("4398c3e41831", "a7b8c9d0e1f2")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
