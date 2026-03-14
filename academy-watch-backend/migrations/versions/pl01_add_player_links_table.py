"""Add player_links table

Revision ID: pl01
Revises: pc01
Create Date: 2026-02-17

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'pl01'
down_revision = 'pc01'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'player_links',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('player_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('user_accounts.id'), nullable=True),
        sa.Column('url', sa.String(500), nullable=False),
        sa.Column('title', sa.String(200), nullable=True),
        sa.Column('link_type', sa.String(30), server_default='article', nullable=True),
        sa.Column('status', sa.String(20), server_default='pending', nullable=True),
        sa.Column('upvotes', sa.Integer(), server_default=sa.text('0'), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
    )
    op.create_index('ix_player_links_player_id', 'player_links', ['player_id'])
    op.create_index('ix_player_links_status', 'player_links', ['status'])


def downgrade():
    op.drop_index('ix_player_links_status', table_name='player_links')
    op.drop_index('ix_player_links_player_id', table_name='player_links')
    op.drop_table('player_links')
