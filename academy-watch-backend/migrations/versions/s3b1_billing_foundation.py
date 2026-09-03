"""Add the Stripe billing foundation.

Revision ID: s3b1
Revises: cb01
Create Date: 2026-09-03

Every DDL operation is guarded for the production schema's pre-apply drift.
"""

import sqlalchemy as sa
from alembic import op
from migrations._migration_helpers import create_index_safe, index_exists, table_exists

revision = "s3b1"
down_revision = "cb01"
branch_labels = None
depends_on = None

SUBSCRIPTION_SCOPE_INDEX = "ix_billing_subscriptions_scope"
SUBSCRIPTION_PURCHASER_INDEX = "ix_billing_subscriptions_purchaser_user_id"


def _enable_rls(table: str) -> None:
    if table_exists(table) and op.get_bind().dialect.name != "sqlite":
        op.execute(sa.text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))


def upgrade():
    if not table_exists("stripe_webhook_events"):
        op.create_table(
            "stripe_webhook_events",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("event_id", sa.String(length=255), nullable=False),
            sa.Column("event_type", sa.String(length=120), nullable=False),
            sa.Column("payload_hash", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("error", sa.Text()),
            sa.Column("received_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("processed_at", sa.DateTime()),
            sa.CheckConstraint(
                "status IN ('processed','ignored','failed')",
                name="ck_stripe_webhook_events_status",
            ),
            sa.UniqueConstraint("event_id", name="uq_stripe_webhook_events_event_id"),
        )
    _enable_rls("stripe_webhook_events")

    if not table_exists("billing_customers"):
        op.create_table(
            "billing_customers",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "user_account_id",
                sa.Integer(),
                sa.ForeignKey("user_accounts.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("stripe_customer_id", sa.String(length=255), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("user_account_id", name="uq_billing_customers_user_account_id"),
            sa.UniqueConstraint("stripe_customer_id", name="uq_billing_customers_stripe_customer_id"),
        )
    _enable_rls("billing_customers")

    if not table_exists("billing_subscriptions"):
        op.create_table(
            "billing_subscriptions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("scope_type", sa.String(length=20), nullable=False),
            sa.Column("scope_id", sa.Integer(), nullable=False),
            sa.Column("product_code", sa.String(length=40), nullable=False),
            sa.Column("price_code", sa.String(length=20), nullable=False),
            sa.Column(
                "purchaser_user_id",
                sa.Integer(),
                sa.ForeignKey("user_accounts.id", ondelete="SET NULL"),
            ),
            sa.Column("stripe_customer_id", sa.String(length=255), nullable=False),
            sa.Column("stripe_subscription_id", sa.String(length=255), nullable=False),
            sa.Column("stripe_price_id", sa.String(length=255), nullable=False),
            sa.Column("status", sa.String(length=30), nullable=False),
            sa.Column("unit_amount", sa.Integer()),
            sa.Column("currency", sa.String(length=3)),
            sa.Column("interval", sa.String(length=10)),
            sa.Column("current_period_start", sa.DateTime()),
            sa.Column("current_period_end", sa.DateTime()),
            sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("canceled_at", sa.DateTime()),
            sa.Column("last_event_created", sa.Integer()),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.CheckConstraint(
                "scope_type IN ('user','club_program')",
                name="ck_billing_subscriptions_scope_type",
            ),
            sa.UniqueConstraint("stripe_subscription_id", name="uq_billing_subscriptions_stripe_subscription_id"),
        )
    if table_exists("billing_subscriptions"):
        create_index_safe(
            SUBSCRIPTION_SCOPE_INDEX,
            "billing_subscriptions",
            ["scope_type", "scope_id", "product_code"],
        )
        create_index_safe(
            SUBSCRIPTION_PURCHASER_INDEX,
            "billing_subscriptions",
            ["purchaser_user_id"],
        )
    _enable_rls("billing_subscriptions")

    if not table_exists("billing_checkout_sessions"):
        op.create_table(
            "billing_checkout_sessions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("scope_type", sa.String(length=20), nullable=False),
            sa.Column("scope_id", sa.Integer(), nullable=False),
            sa.Column("product_code", sa.String(length=40), nullable=False),
            sa.Column("price_code", sa.String(length=20), nullable=False),
            sa.Column(
                "purchaser_user_id",
                sa.Integer(),
                sa.ForeignKey("user_accounts.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("client_key", sa.String(length=64), nullable=False),
            sa.Column("stripe_session_id", sa.String(length=255)),
            sa.Column("checkout_url", sa.Text()),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
            sa.Column("expires_at", sa.DateTime()),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("completed_at", sa.DateTime()),
            sa.CheckConstraint(
                "scope_type IN ('user','club_program')",
                name="ck_billing_checkout_sessions_scope_type",
            ),
            sa.CheckConstraint(
                "status IN ('open','complete','expired')",
                name="ck_billing_checkout_sessions_status",
            ),
            sa.UniqueConstraint("stripe_session_id", name="uq_billing_checkout_sessions_stripe_session_id"),
            sa.UniqueConstraint(
                "scope_type",
                "scope_id",
                "product_code",
                "purchaser_user_id",
                "client_key",
                name="uq_billing_checkout_idem",
            ),
        )
    _enable_rls("billing_checkout_sessions")


def downgrade():
    if table_exists("billing_checkout_sessions"):
        op.drop_table("billing_checkout_sessions")
    if table_exists("billing_subscriptions"):
        if index_exists(SUBSCRIPTION_PURCHASER_INDEX):
            op.drop_index(SUBSCRIPTION_PURCHASER_INDEX, table_name="billing_subscriptions")
        if index_exists(SUBSCRIPTION_SCOPE_INDEX):
            op.drop_index(SUBSCRIPTION_SCOPE_INDEX, table_name="billing_subscriptions")
        op.drop_table("billing_subscriptions")
    if table_exists("billing_customers"):
        op.drop_table("billing_customers")
    if table_exists("stripe_webhook_events"):
        op.drop_table("stripe_webhook_events")
