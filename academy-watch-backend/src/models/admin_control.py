"""B3 cases, append-only actions and authoritative cash/deployment projections."""

from datetime import UTC, datetime

from src.models.league import db


def now():
    return datetime.now(UTC).replace(tzinfo=None)


class SafeguardingCase(db.Model):
    __tablename__ = "safeguarding_cases"
    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey("content_reports.id", ondelete="SET NULL"), unique=True)
    suppression_id = db.Column(db.Integer, db.ForeignKey("player_suppressions.id", ondelete="SET NULL"), unique=True)
    target_type = db.Column(db.String(40), nullable=False)
    target_id = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="open", server_default="open")
    received_at = db.Column(db.DateTime, nullable=False, default=now)
    first_action_due_at = db.Column(db.DateTime, nullable=False)
    first_action_at = db.Column(db.DateTime)
    closed_at = db.Column(db.DateTime)
    resolver_email = db.Column(db.String(254))
    version = db.Column(db.Integer, nullable=False, default=1, server_default="1")
    # Only holds CREATED by this case may be lifted by it.
    held_program_id = db.Column(db.Integer, db.ForeignKey("club_programs.id", ondelete="SET NULL"))
    owned_suppression_id = db.Column(db.Integer, db.ForeignKey("player_suppressions.id", ondelete="SET NULL"))
    notification_state = db.Column(db.String(30), nullable=False, default="none", server_default="none")
    __table_args__ = (
        db.CheckConstraint("status IN ('open','investigating','closed')", name="ck_safeguarding_case_status"),
        db.Index("ix_safeguarding_cases_due", "status", "first_action_due_at", "id"),
    )


class SafeguardingCaseEvent(db.Model):
    __tablename__ = "safeguarding_case_events"
    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(
        db.Integer, db.ForeignKey("safeguarding_cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    action = db.Column(db.String(40), nullable=False)
    actor_email = db.Column(db.String(254), nullable=False)
    reason = db.Column(db.String(2000), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=now)


class BillingCashEvent(db.Model):
    """One actual receipt/refund; never infer cash from subscription prices."""

    __tablename__ = "billing_cash_events"
    id = db.Column(db.Integer, primary_key=True)
    source_key = db.Column(db.String(255), nullable=False, unique=True)
    stripe_event_id = db.Column(db.String(255), nullable=False)
    kind = db.Column(db.String(20), nullable=False)
    amount_cents = db.Column(db.Integer, nullable=False)
    currency = db.Column(db.String(3), nullable=False)
    occurred_at = db.Column(db.DateTime, nullable=False, index=True)
    product_code = db.Column(db.String(40), nullable=False)
    scope_type = db.Column(db.String(20))
    scope_id = db.Column(db.Integer)
    purchaser_user_id = db.Column(db.Integer, db.ForeignKey("user_accounts.id", ondelete="SET NULL"))
    payment_intent_id = db.Column(db.String(255), index=True)
    invoice_id = db.Column(db.String(255))
    __table_args__ = (
        db.CheckConstraint("kind IN ('receipt','refund')", name="ck_billing_cash_events_kind"),
        db.CheckConstraint("amount_cents >= 0", name="ck_billing_cash_events_amount"),
    )


class BusinessDeploymentState(db.Model):
    __tablename__ = "business_deployment_states"
    id = db.Column(db.Integer, primary_key=True)
    deployment_id = db.Column(db.String(200), nullable=False, unique=True)
    api_football_frozen = db.Column(db.Boolean, nullable=False)
    newsletters_configured_frozen = db.Column(db.Boolean, nullable=False)
    newsletters_effective_frozen = db.Column(db.Boolean, nullable=False)
    observed_at = db.Column(db.DateTime, nullable=False, default=now)
