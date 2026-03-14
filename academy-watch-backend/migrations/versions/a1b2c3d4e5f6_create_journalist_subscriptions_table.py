"""create journalist_subscriptions table

Revision ID: a1b2c3d4e5f6
Revises: z5a6b7c8d9e0
Create Date: 2025-11-21 11:40:00.000000

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime, timezone

# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'z5a6b7c8d9e0'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'journalist_subscriptions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('subscriber_user_id', sa.Integer(), nullable=False),
        sa.Column('journalist_user_id', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['journalist_user_id'], ['user_accounts.id'], ),
        sa.ForeignKeyConstraint(['subscriber_user_id'], ['user_accounts.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('subscriber_user_id', 'journalist_user_id', name='uq_journalist_subscription')
    )


def downgrade():
    op.drop_table('journalist_subscriptions')
