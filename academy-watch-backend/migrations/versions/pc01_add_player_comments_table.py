"""Add player_comments table

Revision ID: pc01
Revises: rc01
Create Date: 2026-02-17

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'pc01'
down_revision = 'rc01'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'player_comments',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('player_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('user_accounts.id'), nullable=True),
        sa.Column('author_email', sa.String(255), nullable=False),
        sa.Column('author_name', sa.String(120), nullable=True),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('is_deleted', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
    )
    op.create_index('ix_player_comments_player_id', 'player_comments', ['player_id'])


def downgrade():
    op.drop_index('ix_player_comments_player_id', table_name='player_comments')
    op.drop_table('player_comments')
