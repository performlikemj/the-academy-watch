"""add stripe models

Revision ID: s1t2r3i4p5e6
Revises: a1b2c3d4e5f6
Create Date: 2025-11-24 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 's1t2r3i4p5e6'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    # Create stripe_connected_accounts table
    op.create_table(
        'stripe_connected_accounts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('journalist_user_id', sa.Integer(), nullable=False),
        sa.Column('stripe_account_id', sa.String(255), nullable=False),
        sa.Column('onboarding_complete', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('payouts_enabled', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('charges_enabled', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('details_submitted', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['journalist_user_id'], ['user_accounts.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('journalist_user_id'),
        sa.UniqueConstraint('stripe_account_id')
    )

    # Create stripe_subscription_plans table
    op.create_table(
        'stripe_subscription_plans',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('journalist_user_id', sa.Integer(), nullable=False),
        sa.Column('stripe_product_id', sa.String(255), nullable=False),
        sa.Column('stripe_price_id', sa.String(255), nullable=False),
        sa.Column('price_amount', sa.Integer(), nullable=False),
        sa.Column('currency', sa.String(3), nullable=False, server_default='usd'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['journalist_user_id'], ['user_accounts.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('stripe_price_id')
    )

    # Create stripe_subscriptions table
    op.create_table(
        'stripe_subscriptions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('subscriber_user_id', sa.Integer(), nullable=False),
        sa.Column('journalist_user_id', sa.Integer(), nullable=False),
        sa.Column('stripe_subscription_id', sa.String(255), nullable=False),
        sa.Column('stripe_customer_id', sa.String(255), nullable=False),
        sa.Column('status', sa.String(50), nullable=False),
        sa.Column('current_period_start', sa.DateTime(), nullable=True),
        sa.Column('current_period_end', sa.DateTime(), nullable=True),
        sa.Column('cancel_at_period_end', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['subscriber_user_id'], ['user_accounts.id'], ),
        sa.ForeignKeyConstraint(['journalist_user_id'], ['user_accounts.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('stripe_subscription_id'),
        sa.UniqueConstraint('subscriber_user_id', 'journalist_user_id', name='uq_stripe_subscription')
    )

    # Create stripe_platform_revenue table
    op.create_table(
        'stripe_platform_revenue',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('period_start', sa.Date(), nullable=False),
        sa.Column('period_end', sa.Date(), nullable=False),
        sa.Column('total_revenue_cents', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('platform_fee_cents', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('subscription_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('stripe_platform_revenue')
    op.drop_table('stripe_subscriptions')
    op.drop_table('stripe_subscription_plans')
    op.drop_table('stripe_connected_accounts')

