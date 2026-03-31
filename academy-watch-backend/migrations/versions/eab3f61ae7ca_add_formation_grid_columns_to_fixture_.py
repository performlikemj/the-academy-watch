"""add formation grid columns to fixture_player_stats

Revision ID: eab3f61ae7ca
Revises: d1b517ce47c1
Create Date: 2026-03-22 00:38:36.627664

"""
from alembic import op
import sqlalchemy as sa
from migrations._migration_helpers import add_column_safe

# revision identifiers, used by Alembic.
revision = 'eab3f61ae7ca'
down_revision = 'd1b517ce47c1'
branch_labels = None
depends_on = None


def upgrade():
    add_column_safe('fixture_player_stats', sa.Column('formation', sa.String(length=20), nullable=True))
    add_column_safe('fixture_player_stats', sa.Column('grid', sa.String(length=10), nullable=True))
    add_column_safe('fixture_player_stats', sa.Column('formation_position', sa.String(length=10), nullable=True))


def downgrade():
    with op.batch_alter_table('fixture_player_stats', schema=None) as batch_op:
        batch_op.drop_column('formation_position')
        batch_op.drop_column('grid')
        batch_op.drop_column('formation')
