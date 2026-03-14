"""Add sponsors table for self-serve sponsor management

Revision ID: sp01_sponsors
Revises: dq01_digest_queue
Create Date: 2025-11-28 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'sp01_sponsors'
down_revision = 'dq01_digest_queue'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'sponsors',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('image_url', sa.Text(), nullable=False),
        sa.Column('link_url', sa.Text(), nullable=False),
        sa.Column('description', sa.String(255), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('click_count', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    
    # Index for efficient ordering of active sponsors
    op.create_index(
        'ix_sponsors_active_order',
        'sponsors',
        ['is_active', 'display_order']
    )


def downgrade():
    op.drop_index('ix_sponsors_active_order', 'sponsors')
    op.drop_table('sponsors')

