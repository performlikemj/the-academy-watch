"""Stripe billing persistence and webhook idempotency models."""

from datetime import UTC, datetime

from src.models.league import db


def _utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


_timestamp = dict(nullable=False, default=_utcnow_naive, server_default=db.func.now())


class StripeWebhookEvent(db.Model):
    __tablename__ = "stripe_webhook_events"

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.String(255), unique=True, nullable=False)
    event_type = db.Column(db.String(120), nullable=False)
    payload_hash = db.Column(db.String(64), nullable=False)
    status = db.Column(db.String(20), nullable=False)
    error = db.Column(db.Text)
    received_at = db.Column(db.DateTime, **_timestamp)
    processed_at = db.Column(db.DateTime)

    __table_args__ = (
        db.CheckConstraint("status IN ('processed','ignored','failed')", name="ck_stripe_webhook_events_status"),
    )


class BillingCustomer(db.Model):
    __tablename__ = "billing_customers"

    id = db.Column(db.Integer, primary_key=True)
    user_account_id = db.Column(
        db.Integer,
        db.ForeignKey("user_accounts.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    stripe_customer_id = db.Column(db.String(255), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, **_timestamp)
    updated_at = db.Column(db.DateTime, onupdate=_utcnow_naive, **_timestamp)


class BillingSubscription(db.Model):
    __tablename__ = "billing_subscriptions"

    id = db.Column(db.Integer, primary_key=True)
    scope_type = db.Column(db.String(20), nullable=False)
    scope_id = db.Column(db.Integer, nullable=False)
    product_code = db.Column(db.String(40), nullable=False)
    price_code = db.Column(db.String(20), nullable=False)
    purchaser_user_id = db.Column(db.Integer, db.ForeignKey("user_accounts.id", ondelete="SET NULL"), index=True)
    stripe_customer_id = db.Column(db.String(255), nullable=False)
    stripe_subscription_id = db.Column(db.String(255), unique=True, nullable=False)
    stripe_price_id = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(30), nullable=False)
    unit_amount = db.Column(db.Integer)
    currency = db.Column(db.String(3))
    interval = db.Column(db.String(10))
    current_period_start = db.Column(db.DateTime)
    current_period_end = db.Column(db.DateTime)
    cancel_at_period_end = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    canceled_at = db.Column(db.DateTime)
    last_event_created = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, **_timestamp)
    updated_at = db.Column(db.DateTime, onupdate=_utcnow_naive, **_timestamp)

    __table_args__ = (
        db.CheckConstraint("scope_type IN ('user','club_program')", name="ck_billing_subscriptions_scope_type"),
        db.Index("ix_billing_subscriptions_scope", "scope_type", "scope_id", "product_code"),
    )


class BillingCheckoutSession(db.Model):
    __tablename__ = "billing_checkout_sessions"

    id = db.Column(db.Integer, primary_key=True)
    scope_type = db.Column(db.String(20), nullable=False)
    scope_id = db.Column(db.Integer, nullable=False)
    product_code = db.Column(db.String(40), nullable=False)
    price_code = db.Column(db.String(20), nullable=False)
    purchaser_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    client_key = db.Column(db.String(64), nullable=False)
    stripe_session_id = db.Column(db.String(255), unique=True)
    checkout_url = db.Column(db.Text)
    status = db.Column(db.String(20), nullable=False, default="open", server_default="open")
    expires_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, **_timestamp)
    completed_at = db.Column(db.DateTime)

    __table_args__ = (
        db.CheckConstraint("scope_type IN ('user','club_program')", name="ck_billing_checkout_sessions_scope_type"),
        db.CheckConstraint("status IN ('open','complete','expired')", name="ck_billing_checkout_sessions_status"),
        db.UniqueConstraint(
            "scope_type",
            "scope_id",
            "product_code",
            "purchaser_user_id",
            "client_key",
            name="uq_billing_checkout_idem",
        ),
    )


__all__ = ["BillingCheckoutSession", "BillingCustomer", "BillingSubscription", "StripeWebhookEvent"]
