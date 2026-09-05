"""Append-only GOL credit ledger with mutable refund accounting on grants."""

from datetime import UTC, datetime

from src.models.league import db


def _utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class GolCreditLedger(db.Model):
    __tablename__ = "gol_credit_ledger"

    id = db.Column(db.Integer, primary_key=True)
    user_account_id = db.Column(
        db.Integer,
        db.ForeignKey("user_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    bucket = db.Column(db.String(20), nullable=False)
    kind = db.Column(db.String(20), nullable=False)
    delta = db.Column(db.Integer, nullable=False)
    idempotency_key = db.Column(db.String(120), unique=True, nullable=False)
    debit_id = db.Column(db.Integer, db.ForeignKey("gol_credit_ledger.id"), nullable=True)
    client_msg_id = db.Column(db.String(64))
    attempt = db.Column(db.Integer)
    stripe_event_id = db.Column(db.String(255))
    stripe_session_id = db.Column(db.String(255), unique=True)
    stripe_payment_intent_id = db.Column(db.String(255))
    pack_id = db.Column(db.String(40))
    amount_paid_cents = db.Column(db.Integer)
    currency = db.Column(db.String(3))
    refunded_cents = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    note = db.Column(db.String(200))
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=_utcnow_naive,
        server_default=db.func.now(),
    )

    __table_args__ = (
        db.CheckConstraint(
            "bucket IN ('free_allowance','prepaid')",
            name="ck_gol_credit_ledger_bucket",
        ),
        db.CheckConstraint(
            "kind IN ('grant','debit','reversal','adjustment')",
            name="ck_gol_credit_ledger_kind",
        ),
        db.CheckConstraint("delta <> 0", name="ck_gol_credit_ledger_delta_nonzero"),
        db.Index("ix_gol_credit_ledger_user_bucket", "user_account_id", "bucket"),
        db.Index("ix_gol_credit_ledger_payment_intent", "stripe_payment_intent_id"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_account_id": self.user_account_id,
            "bucket": self.bucket,
            "kind": self.kind,
            "delta": self.delta,
            "idempotency_key": self.idempotency_key,
            "debit_id": self.debit_id,
            "client_msg_id": self.client_msg_id,
            "attempt": self.attempt,
            "stripe_event_id": self.stripe_event_id,
            "stripe_session_id": self.stripe_session_id,
            "stripe_payment_intent_id": self.stripe_payment_intent_id,
            "pack_id": self.pack_id,
            "amount_paid_cents": self.amount_paid_cents,
            "currency": self.currency,
            "refunded_cents": self.refunded_cents,
            "note": self.note,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class GolChatExecution(db.Model):
    __tablename__ = "gol_chat_executions"

    id = db.Column(db.Integer, primary_key=True)
    user_account_id = db.Column(db.Integer, db.ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False)
    client_msg_id = db.Column(db.String(64), nullable=False)
    attempt = db.Column(db.Integer, nullable=False)
    debit_id = db.Column(db.Integer, db.ForeignKey("gol_credit_ledger.id"))
    status = db.Column(db.String(20), nullable=False)
    input_hash = db.Column(db.String(64), nullable=False)
    lease_generation = db.Column(db.Integer, nullable=False, default=1, server_default="1")
    lease_started_at = db.Column(db.DateTime, nullable=False, default=_utcnow_naive, server_default=db.func.now())
    response_text = db.Column(db.Text)
    response_events = db.Column(db.Text)
    recover_count = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow_naive, server_default=db.func.now())
    completed_at = db.Column(db.DateTime)

    __table_args__ = (
        db.UniqueConstraint("user_account_id", "client_msg_id", "attempt", name="uq_gol_chat_execution_attempt"),
        db.CheckConstraint("status IN ('running','completed','failed')", name="ck_gol_chat_execution_status"),
        db.Index("ix_gol_chat_executions_debit", "debit_id"),
    )

    def to_dict(self):
        return {
            "client_msg_id": self.client_msg_id,
            "attempt": self.attempt,
            "input_hash": self.input_hash,
            "status": self.status,
            "response_text": self.response_text,
            "response_events": self.response_events,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class GolPaymentSettlement(db.Model):
    __tablename__ = "gol_payment_settlements"

    id = db.Column(db.Integer, primary_key=True)
    stripe_payment_intent_id = db.Column(db.String(255), unique=True, nullable=False)
    grant_ledger_id = db.Column(db.Integer, db.ForeignKey("gol_credit_ledger.id", ondelete="SET NULL"), index=True)
    refund_target_cents = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    refund_applied_cents = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    last_refund_event_id = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow_naive, server_default=db.func.now())
    updated_at = db.Column(
        db.DateTime, nullable=False, default=_utcnow_naive, onupdate=_utcnow_naive, server_default=db.func.now()
    )


__all__ = ["GolChatExecution", "GolCreditLedger", "GolPaymentSettlement"]
