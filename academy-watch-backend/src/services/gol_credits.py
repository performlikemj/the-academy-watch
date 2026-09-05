"""Transactional balances, debits, purchase grants, and refunds for GOL."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from src.config.stripe_config import billing_enabled
from src.models.gol_credits import GolChatExecution, GolCreditLedger
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


class QuestionInFlight(Exception):
    pass


class QuestionRecoveryExhausted(Exception):
    pass


def _now():
    return datetime.now(UTC).replace(tzinfo=None)


def _refund_debit(debit):
    if debit is None or _has_reversal(debit.id):
        return False
    db.session.add(
        GolCreditLedger(
            user_account_id=debit.user_account_id,
            bucket=debit.bucket,
            kind="reversal",
            delta=1,
            idempotency_key=f"refund:{debit.id}",
            debit_id=debit.id,
            client_msg_id=debit.client_msg_id,
            attempt=debit.attempt,
        )
    )
    db.session.flush()
    return True


def _execution_reservation(debit, question_hash, *, debited):
    execution = (
        GolChatExecution.query.filter_by(
            user_account_id=debit.user_account_id,
            client_msg_id=debit.client_msg_id,
            attempt=debit.attempt,
        )
        .populate_existing()
        .first()
    )
    if execution is None:
        execution = GolChatExecution(
            user_account_id=debit.user_account_id,
            client_msg_id=debit.client_msg_id,
            attempt=debit.attempt,
            debit_id=debit.id,
            status="running",
            input_hash=question_hash,
        )
        db.session.add(execution)
        db.session.flush()
    elif execution.status == "running" and not debited:
        cutoff = _now() - timedelta(minutes=5)
        if execution.lease_started_at >= cutoff:
            raise QuestionInFlight
        if execution.recover_count >= 2:
            changed = db.session.execute(
                update(GolChatExecution)
                .where(
                    GolChatExecution.id == execution.id,
                    GolChatExecution.lease_generation == execution.lease_generation,
                    GolChatExecution.status == "running",
                    GolChatExecution.lease_started_at < cutoff,
                )
                .values(status="failed", completed_at=_now())
                .execution_options(synchronize_session=False)
            ).rowcount
            if changed != 1:
                raise QuestionInFlight
            _refund_debit(debit)
            db.session.commit()
            raise QuestionRecoveryExhausted
        # Generation also fences two reclaimers which read the same old lease.
        claimed = db.session.execute(
            update(GolChatExecution)
            .where(
                GolChatExecution.id == execution.id,
                GolChatExecution.status == "running",
                GolChatExecution.lease_generation == execution.lease_generation,
                GolChatExecution.lease_started_at < cutoff,
                GolChatExecution.recover_count < 2,
            )
            .values(
                lease_generation=GolChatExecution.lease_generation + 1,
                recover_count=GolChatExecution.recover_count + 1,
                lease_started_at=_now(),
            )
            .execution_options(synchronize_session=False)
        ).rowcount
        if claimed != 1:
            raise QuestionInFlight
        db.session.refresh(execution)
    payload = _reservation_payload(
        debit.bucket, _balance_values(debit.user_account_id), debited=debited, attempt=debit.attempt
    )
    payload.update(
        debit_id=debit.id,
        execution_id=execution.id,
        lease_generation=execution.lease_generation,
        replay=execution.status == "completed",
        response_text=execution.response_text,
        response_events=execution.terminal_events,
        response_meta=execution.response_meta,
    )
    db.session.commit()
    return payload


def reserve_question(user, client_msg_id, *, question_hash, role="user") -> dict:
    """Commit the debit and its execution lease together under the user lock."""
    if not billing_enabled():
        return _reservation_payload(
            "disabled", {"free_questions_remaining": free_allowance(), "credit_balance": 0}, debited=False, attempt=None
        )
    if role == "admin":
        values = balances(user)
        db.session.commit()
        return _reservation_payload("exempt", values, debited=False, attempt=None)
    try:
        _lock_user(user.id)
        latest = _latest_debit(user.id, client_msg_id)
        if latest is not None:
            if (latest.note or "").partition(";")[0] != question_hash:
                raise ClientMsgIdReused
            if not _has_reversal(latest.id):
                execution = GolChatExecution.query.filter_by(debit_id=latest.id).first()
                if execution is not None and execution.status == "failed":
                    # A long client disconnect remains charged, including on retry.
                    if ";refund_withheld=true" not in (latest.note or ""):
                        _refund_debit(latest)
                else:
                    return _execution_reservation(latest, question_hash, debited=False)
        attempt = (latest.attempt if latest else 0) + 1
        before = _balance_values(user.id)
        if before["free_questions_remaining"] > 0:
            bucket = "free_allowance"
        elif before["credit_balance"] > 0:
            bucket = "prepaid"
        else:
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
                db.session.add(
                    GolChatExecution(
                        user_account_id=user.id,
                        client_msg_id=client_msg_id,
                        attempt=attempt,
                        debit_id=debit.id,
                        status="running",
                        input_hash=question_hash,
                    )
                )
                db.session.flush()
        except IntegrityError:
            winner = _latest_debit(user.id, client_msg_id)
            if winner is None or _has_reversal(winner.id):
                raise
            if (winner.note or "").partition(";")[0] != question_hash:
                raise ClientMsgIdReused
            return _execution_reservation(winner, question_hash, debited=False)
        db.session.add(ProductEvent(event_name="gol_question_debited", user_email=user.email, props={"bucket": bucket}))
        return _execution_reservation(debit, question_hash, debited=True)
    except Exception:
        db.session.rollback()
        raise


def refund_question(user, client_msg_id, *, debit_id=None, attempt=None) -> bool:
    """Compensate an exact debit; legacy callers retain latest-debit behavior."""
    try:
        _lock_user(user.id)
        if debit_id is not None:
            debit = GolCreditLedger.query.filter_by(
                id=debit_id, user_account_id=user.id, client_msg_id=client_msg_id, kind="debit"
            ).first()
        elif attempt is not None:
            debit = GolCreditLedger.query.filter_by(
                user_account_id=user.id, client_msg_id=client_msg_id, attempt=attempt, kind="debit"
            ).first()
        else:
            debit = _latest_debit(user.id, client_msg_id)
        refunded = _refund_debit(debit)
        db.session.commit()
        return refunded
    except Exception:
        db.session.rollback()
        raise


def finish_execution(
    user,
    reservation,
    *,
    response_text=None,
    response_events=None,
    failed=False,
    refund=True,
    disconnect_delivered_chars=None,
    partial=False,
):
    """Fence stale workers and commit completion or exact compensation atomically."""
    if not reservation.get("execution_id"):
        return False
    try:
        _lock_user(user.id)
        changed = db.session.execute(
            update(GolChatExecution)
            .where(
                GolChatExecution.id == reservation["execution_id"],
                GolChatExecution.user_account_id == user.id,
                GolChatExecution.lease_generation == reservation["lease_generation"],
                GolChatExecution.status == "running",
            )
            .values(
                status="failed" if failed else "completed",
                completed_at=_now(),
                response_text=response_text,
                response_events=json.dumps(
                    {
                        "events": response_events or [],
                        "response_meta": {
                            "partial": True,
                            "delivered_chars": disconnect_delivered_chars,
                        },
                    }
                    if partial
                    else response_events or []
                ),
            )
            .execution_options(synchronize_session=False)
        ).rowcount
        if changed != 1:
            db.session.rollback()
            return False
        if disconnect_delivered_chars is not None:
            debit = db.session.get(GolCreditLedger, reservation["debit_id"])
            # Keep the fingerprint prefix; append the disconnect disposition without
            # adding schema. Retries must not undo a deliberately retained charge.
            fingerprint = (debit.note or "").partition(";")[0]
            debit.note = (
                f"{fingerprint};disconnect_delivered_chars={disconnect_delivered_chars}"
                f";refund_withheld={str(not refund).lower()}"
            )
        if failed and refund:
            # refund_question commits the guarded failure and exact reversal together.
            return refund_question(
                user,
                db.session.get(GolChatExecution, reservation["execution_id"]).client_msg_id,
                debit_id=reservation["debit_id"],
            )
        db.session.commit()
        return not failed
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
