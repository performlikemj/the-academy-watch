"""Transactional balances, debits, purchase grants, and refunds for GOL."""

from __future__ import annotations

import os

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from src.config.stripe_config import billing_enabled
from src.models.gol_credits import GolCreditLedger
from src.models.league import UserAccount, db
from src.models.product_event import ProductEvent


class CreditsExhausted(Exception):
    def __init__(self, free_questions_remaining: int, credit_balance: int):
        super().__init__("GOL credits exhausted")
        self.free_questions_remaining = free_questions_remaining
        self.credit_balance = credit_balance


class ClientMsgIdReused(Exception):
    """A client message id was presented for a different normalized question."""


def free_allowance() -> int:
    try:
        return max(0, int((os.getenv("GOL_FREE_ALLOWANCE") or "3").strip()))
    except (TypeError, ValueError):
        return 3


def _lock_user(user_id: int) -> None:
    # SELECT ... FOR UPDATE is a no-op on SQLite; production PostgreSQL serializes per-user ledger mutations.
    db.session.execute(select(UserAccount.id).where(UserAccount.id == user_id).with_for_update())


def _balance_values(user_id: int) -> dict:
    totals = dict(
        db.session.query(
            GolCreditLedger.bucket,
            func.coalesce(func.sum(GolCreditLedger.delta), 0),
        )
        .filter(GolCreditLedger.user_account_id == user_id)
        .group_by(GolCreditLedger.bucket)
        .all()
    )
    return {
        "free_questions_remaining": max(0, free_allowance() + int(totals.get("free_allowance", 0))),
        "credit_balance": int(totals.get("prepaid", 0)),
    }


def balances(user) -> dict:
    return _balance_values(user.id)


def _latest_debit(user_id: int, client_msg_id: str) -> GolCreditLedger | None:
    return (
        GolCreditLedger.query.filter_by(
            user_account_id=user_id,
            client_msg_id=client_msg_id,
            kind="debit",
        )
        .order_by(GolCreditLedger.attempt.desc(), GolCreditLedger.id.desc())
        .first()
    )


def _has_reversal(row_id: int) -> bool:
    return GolCreditLedger.query.filter_by(kind="reversal", debit_id=row_id).first() is not None


def _reservation_payload(bucket: str, values: dict, *, debited: bool, attempt: int | None) -> dict:
    return {
        "bucket": bucket,
        **values,
        "debited": debited,
        "attempt": attempt,
    }


def reserve_question(user, client_msg_id, *, question_hash, role="user") -> dict:
    """Reserve one question credit and commit before streaming begins."""
    if not billing_enabled():
        return _reservation_payload(
            "disabled",
            {"free_questions_remaining": free_allowance(), "credit_balance": 0},
            debited=False,
            attempt=None,
        )
    if role == "admin":
        values = balances(user)
        db.session.commit()
        return _reservation_payload("exempt", values, debited=False, attempt=None)

    try:
        _lock_user(user.id)
        latest = _latest_debit(user.id, client_msg_id)
        if latest is not None:
            if latest.note != question_hash:
                db.session.rollback()
                raise ClientMsgIdReused
            if not _has_reversal(latest.id):
                values = _balance_values(user.id)
                db.session.commit()
                return _reservation_payload(latest.bucket, values, debited=False, attempt=latest.attempt)

        prior_attempt = (
            db.session.query(func.max(GolCreditLedger.attempt))
            .filter_by(user_account_id=user.id, client_msg_id=client_msg_id, kind="debit")
            .scalar()
            or 0
        )
        attempt = int(prior_attempt) + 1
        before = _balance_values(user.id)
        if before["free_questions_remaining"] > 0:
            bucket = "free_allowance"
        elif before["credit_balance"] > 0:
            bucket = "prepaid"
        else:
            db.session.rollback()
            raise CreditsExhausted(**before)

        debit = GolCreditLedger(
            user_account_id=user.id,
            bucket=bucket,
            kind="debit",
            delta=-1,
            idempotency_key=f"q:{user.id}:{client_msg_id}:{attempt}",
            client_msg_id=client_msg_id,
            attempt=attempt,
            note=question_hash,
        )
        try:
            with db.session.begin_nested():
                db.session.add(debit)
                db.session.flush()
        except IntegrityError:
            winner = _latest_debit(user.id, client_msg_id)
            if winner is None or _has_reversal(winner.id):
                raise
            if winner.note != question_hash:
                db.session.rollback()
                raise ClientMsgIdReused
            values = _balance_values(user.id)
            db.session.commit()
            return _reservation_payload(winner.bucket, values, debited=False, attempt=winner.attempt)

        db.session.add(
            ProductEvent(
                event_name="gol_question_debited",
                user_email=user.email,
                props={"bucket": bucket},
            )
        )
        values = _balance_values(user.id)
        db.session.commit()
        return _reservation_payload(bucket, values, debited=True, attempt=attempt)
    except CreditsExhausted:
        raise
    except Exception:
        db.session.rollback()
        raise


def refund_question(user, client_msg_id) -> bool:
    """Compensate the latest unrefunded question debit, if one exists."""
    try:
        _lock_user(user.id)
        debit = _latest_debit(user.id, client_msg_id)
        if debit is None or _has_reversal(debit.id):
            db.session.commit()
            return False
        reversal = GolCreditLedger(
            user_account_id=user.id,
            bucket=debit.bucket,
            kind="reversal",
            delta=1,
            idempotency_key=f"refund:{debit.id}",
            debit_id=debit.id,
            client_msg_id=client_msg_id,
            attempt=debit.attempt,
        )
        try:
            with db.session.begin_nested():
                db.session.add(reversal)
                db.session.flush()
        except IntegrityError:
            db.session.commit()
            return False
        db.session.commit()
        return True
    except Exception:
        db.session.rollback()
        raise


def grant_purchase(
    user,
    *,
    pack_id,
    credits,
    stripe_session_id,
    stripe_payment_intent_id,
    stripe_event_id,
    amount_paid_cents,
    currency,
) -> GolCreditLedger:
    existing = GolCreditLedger.query.filter_by(stripe_session_id=stripe_session_id).first()
    if existing is not None:
        return existing
    row = GolCreditLedger(
        user_account_id=user.id,
        bucket="prepaid",
        kind="grant",
        delta=int(credits),
        idempotency_key=f"grant:{stripe_session_id}",
        stripe_event_id=stripe_event_id,
        stripe_session_id=stripe_session_id,
        stripe_payment_intent_id=stripe_payment_intent_id,
        pack_id=pack_id,
        amount_paid_cents=int(amount_paid_cents),
        currency=str(currency).lower(),
    )
    try:
        with db.session.begin_nested():
            db.session.add(row)
            db.session.flush()
        return row
    except IntegrityError:
        existing = GolCreditLedger.query.filter_by(stripe_session_id=stripe_session_id).first()
        if existing is None:
            raise
        return existing


def apply_refund(*, payment_intent_id, cumulative_refunded_cents, stripe_event_id) -> int:
    if not payment_intent_id:
        return 0
    candidate = (
        GolCreditLedger.query.filter_by(
            stripe_payment_intent_id=payment_intent_id,
            kind="grant",
        )
        .order_by(GolCreditLedger.id.asc())
        .first()
    )
    if candidate is None:
        return 0
    if not candidate.amount_paid_cents or candidate.amount_paid_cents <= 0:
        return 0

    _lock_user(candidate.user_account_id)
    grant = (
        db.session.execute(
            select(GolCreditLedger)
            .where(
                GolCreditLedger.id == candidate.id,
                GolCreditLedger.kind == "grant",
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        .scalars()
        .one()
    )
    cumulative = max(0, int(cumulative_refunded_cents or 0))
    target = min(grant.delta, grant.delta * cumulative // grant.amount_paid_cents)
    already_reversed = -int(
        db.session.query(func.coalesce(func.sum(GolCreditLedger.delta), 0))
        .filter_by(
            kind="reversal",
            debit_id=None,
            bucket="prepaid",
            stripe_payment_intent_id=payment_intent_id,
        )
        .scalar()
    )
    to_reverse = target - already_reversed
    if to_reverse > 0:
        db.session.add(
            GolCreditLedger(
                user_account_id=grant.user_account_id,
                bucket="prepaid",
                kind="reversal",
                delta=-to_reverse,
                idempotency_key=f"refund:{payment_intent_id}:{cumulative}",
                stripe_event_id=stripe_event_id,
                stripe_payment_intent_id=payment_intent_id,
            )
        )
    grant.refunded_cents = max(grant.refunded_cents or 0, cumulative)
    db.session.flush()
    return max(0, to_reverse)


def purchases_for_user(user) -> list[dict]:
    grants = (
        GolCreditLedger.query.filter_by(user_account_id=user.id, bucket="prepaid", kind="grant")
        .order_by(GolCreditLedger.created_at.desc(), GolCreditLedger.id.desc())
        .all()
    )
    purchases = []
    for grant in grants:
        refunded_credits = -int(
            db.session.query(func.coalesce(func.sum(GolCreditLedger.delta), 0))
            .filter_by(
                kind="reversal",
                debit_id=None,
                bucket="prepaid",
                stripe_payment_intent_id=grant.stripe_payment_intent_id,
            )
            .scalar()
        )
        purchases.append(
            {
                "stripe_session_id": grant.stripe_session_id,
                "pack_id": grant.pack_id,
                "credits": grant.delta,
                "amount_paid_cents": grant.amount_paid_cents,
                "currency": grant.currency,
                "refunded_credits": refunded_credits,
                "created_at": grant.created_at.isoformat() if grant.created_at else None,
            }
        )
    return purchases


def forfeit_for_deletion(user) -> dict:
    values = balances(user)
    deleted = GolCreditLedger.query.filter_by(user_account_id=user.id).delete(synchronize_session=False)
    db.session.flush()
    return {
        "ledger_rows": deleted,
        "forfeited_credits": max(0, values["credit_balance"]),
    }


__all__ = [
    "ClientMsgIdReused",
    "CreditsExhausted",
    "apply_refund",
    "balances",
    "forfeit_for_deletion",
    "free_allowance",
    "grant_purchase",
    "purchases_for_user",
    "refund_question",
    "reserve_question",
]
