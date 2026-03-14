"""merge_bj01_and_wc01

Revision ID: 9872f1adcb09
Revises: bj01, wc01
Create Date: 2025-12-26 11:20:07.256717

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9872f1adcb09'
down_revision = ('bj01', 'wc01')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
