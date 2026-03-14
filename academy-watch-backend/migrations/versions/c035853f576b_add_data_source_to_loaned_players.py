"""add data source to loaned players

Revision ID: c035853f576b
Revises: 163a55803b67
Create Date: 2025-09-26 23:40:42.573536

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c035853f576b'
down_revision = '163a55803b67'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('loaned_players', sa.Column('data_source', sa.String(length=50), nullable=False, server_default='api-football'))
    op.add_column('loaned_players', sa.Column('can_fetch_stats', sa.Boolean(), nullable=False, server_default=sa.true()))
    op.execute("UPDATE loaned_players SET data_source='api-football' WHERE data_source IS NULL")
    op.execute("UPDATE loaned_players SET can_fetch_stats = TRUE WHERE can_fetch_stats IS NULL")
    op.alter_column('loaned_players', 'data_source', server_default=None)
    op.alter_column('loaned_players', 'can_fetch_stats', server_default=None)


def downgrade():
    op.drop_column('loaned_players', 'can_fetch_stats')
    op.drop_column('loaned_players', 'data_source')
