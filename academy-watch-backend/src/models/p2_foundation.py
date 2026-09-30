"""Private Phase 2 notification intents and privileged action history."""

from datetime import UTC, datetime

from sqlalchemy import event
from src.models.league import db


class NotificationOutbox(db.Model):
    __tablename__ = "notification_outbox"
    __table_args__ = (
        db.Index("uq_notification_outbox_dedupe", "dedupe_key", unique=True),
        db.Index("ix_notification_outbox_due", "status", "next_attempt_at", "id"),
        db.CheckConstraint("attempts >= 0", name="ck_notification_outbox_attempts"),
        db.CheckConstraint(
            "status IN ('pending', 'retry', 'sending', 'sent', 'cancelled', 'failed')",
            name="ck_notification_outbox_status",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    dedupe_key = db.Column(db.String(200), nullable=False)
    recipient_user_id = db.Column(db.Integer, db.ForeignKey("user_accounts.id"), nullable=False)
    event_type = db.Column(db.String(80), nullable=False)
    entity_type = db.Column(db.String(80), nullable=False)
    entity_id = db.Column(db.String(80), nullable=False)
    template = db.Column(db.String(80), nullable=False)
    payload = db.Column(db.JSON, nullable=False, default=dict)
    status = db.Column(db.String(20), nullable=False, default="pending", server_default="pending")
    attempts = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    next_attempt_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), server_default=db.func.now()
    )
    lease_token = db.Column(db.String(36))
    lease_expires_at = db.Column(db.DateTime(timezone=True))
    provider = db.Column(db.String(40))
    provider_message_id = db.Column(db.String(254))
    last_error = db.Column(db.String(80))
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), server_default=db.func.now()
    )
    sent_at = db.Column(db.DateTime(timezone=True))


class AdminActionEvent(db.Model):
    __tablename__ = "admin_action_events"
    __table_args__ = (db.Index("ix_admin_action_events_target", "target_type", "target_id", "created_at"),)

    id = db.Column(db.Integer, primary_key=True)
    actor_email = db.Column(db.String(254), nullable=False)
    action = db.Column(db.String(80), nullable=False)
    target_type = db.Column(db.String(80), nullable=False)
    target_id = db.Column(db.String(80), nullable=False)
    reason = db.Column(db.String(2000), nullable=False)
    event_metadata = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), server_default=db.func.now()
    )


@event.listens_for(AdminActionEvent, "before_update")
@event.listens_for(AdminActionEvent, "before_delete")
def _append_only(_mapper, _connection, _target):
    raise ValueError("admin action events are append-only; identity redaction uses account erasure")
