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


__all__ = ["GolCreditLedger"]
