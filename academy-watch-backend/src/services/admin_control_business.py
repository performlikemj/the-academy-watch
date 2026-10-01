"""Cash projection from verified Stripe events, plus separately labelled GOL history."""

import os
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from src.models.admin_control import BillingCashEvent, BusinessDeploymentState
from src.models.billing import BillingCustomer, BillingSubscription
from src.models.gol_credits import GolCreditLedger
from src.models.league import db
from src.utils.data_mode import api_football_frozen, newsletters_frozen


def enabled():
    return os.getenv("ADMIN_BUSINESS_ENABLED", "").lower() in {"1", "true", "yes", "on"}


def _id(value):
    return value if isinstance(value, str) else (value or {}).get("id")


def _remote_rows(resource, **params):
    import stripe
    from src.config.stripe_config import configure_stripe

    configure_stripe()
    rows = []
    for _ in range(10):
        page = getattr(stripe, resource).list(limit=100, **params)
        items = page.get("data", [])
        rows.extend(items)
        if not page.get("has_more"):
            return rows
        if not items:
            break
        params["starting_after"] = items[-1]["id"]
    raise ValueError("cash projection pagination exceeded; retry/reconcile required")


def project_cash(event_type, obj, event_id, created):
    """Caller has verified webhook signature; inserts share its idempotent transaction."""
    if not enabled():
        return
    currency = str(obj.get("currency") or "").lower()
    if len(currency) != 3 or not currency.isalpha():
        return
    customer = BillingCustomer.query.filter_by(stripe_customer_id=_id(obj.get("customer"))).first()
    base = dict(
        stripe_event_id=event_id,
        currency=currency,
        product_code="unmapped",
        purchaser_user_id=customer.user_account_id if customer else None,
    )
    if event_type in {"checkout.session.completed", "checkout.session.async_payment_succeeded"}:
        if obj.get("mode") != "payment" or obj.get("payment_status") != "paid":
            return
        grant = GolCreditLedger.query.filter_by(stripe_session_id=obj.get("id"), kind="grant").first()
        # Verified payment receipt survives subsequent account/GOL-ledger erasure.
        base.update(
            product_code="gol" if grant else "unmapped",
            purchaser_user_id=grant.user_account_id if grant else None,
            scope_type="user" if grant else None,
            scope_id=grant.user_account_id if grant else None,
        )
        values = [
            dict(
                base,
                source_key=f"gol:{obj['id']}",
                kind="receipt",
                amount_cents=obj.get("amount_total"),
                occurred_at=datetime.fromtimestamp(created, UTC).replace(tzinfo=None),
                payment_intent_id=_id(obj.get("payment_intent")),
            )
        ]
    elif event_type == "invoice.paid":
        # Legacy invoice receipts count only payment-backed, zero-balance cash.
        # Modern invoice payments supply their own actual paid amount below.
        payment_intent = _id(obj.get("payment_intent"))
        charge = _id(obj.get("charge"))
        payments = (obj.get("payments") or {}).get("data", [])
        if (obj.get("payments") or {}).get("has_more") or (not payment_intent and not charge and not payments):
            payments = _remote_rows("InvoicePayment", invoice=obj["id"])
        if not payment_intent and not charge and not payments:
            return
        if not payments and (obj.get("paid_out_of_band") or obj.get("starting_balance", 0) != 0):
            return
        amount = obj.get("amount_paid")
        subscription_id = _id(obj.get("subscription")) or _id(
            ((obj.get("parent") or {}).get("subscription_details") or {}).get("subscription")
        )
        subscription = (
            BillingSubscription.query.filter_by(stripe_subscription_id=subscription_id).first()
            if subscription_id
            else None
        )
        if subscription:
            base.update(
                product_code=subscription.product_code,
                scope_type=subscription.scope_type,
                scope_id=subscription.scope_id,
                purchaser_user_id=subscription.purchaser_user_id,
            )
        paid_at = ((obj.get("status_transitions") or {}).get("paid_at")) or created
        values = [
            dict(
                base,
                source_key=f"invoice:{obj['id']}",
                kind="receipt",
                amount_cents=amount,
                occurred_at=datetime.fromtimestamp(paid_at, UTC).replace(tzinfo=None),
                payment_intent_id=payment_intent,
                invoice_id=obj["id"],
            )
        ]
        if payments:
            values = []
            for payment in payments:
                if payment.get("status") != "paid":
                    continue
                paid_at = ((payment.get("status_transitions") or {}).get("paid_at")) or created
                ref = payment.get("payment") or {}
                if ref.get("type") not in {"payment_intent", "charge"}:
                    continue
                values.append(
                    dict(
                        base,
                        source_key=f"invoice_payment:{payment['id']}",
                        kind="receipt",
                        amount_cents=payment.get("amount_paid"),
                        occurred_at=datetime.fromtimestamp(paid_at, UTC).replace(tzinfo=None),
                        payment_intent_id=_id(ref.get("payment_intent")),
                        invoice_id=obj["id"],
                    )
                )
    elif event_type == "charge.refunded":
        payment_intent = _id(obj.get("payment_intent"))
        grant = (
            GolCreditLedger.query.filter_by(stripe_payment_intent_id=payment_intent, kind="grant").first()
            if payment_intent
            else None
        )
        receipt = (
            BillingCashEvent.query.filter_by(payment_intent_id=payment_intent, kind="receipt").first()
            if payment_intent
            else None
        )
        if grant:
            base.update(
                product_code="gol",
                scope_type="user",
                scope_id=grant.user_account_id,
                purchaser_user_id=grant.user_account_id,
            )
        elif receipt:
            base.update(
                product_code=receipt.product_code,
                scope_type=receipt.scope_type,
                scope_id=receipt.scope_id,
                purchaser_user_id=receipt.purchaser_user_id,
            )
        values = []
        # Individual refund IDs/timestamps give accurate date filters and dedupe.
        # Never count a cumulative amount again for each charge.refunded event.
        refunds = (obj.get("refunds") or {}).get("data", [])
        if (obj.get("refunds") or {}).get("has_more") or "refunds" not in obj:
            refunds = _remote_rows("Refund", charge=obj["id"])
        for refund in refunds:
            if refund.get("status") != "succeeded":
                continue
            values.append(
                dict(
                    base,
                    source_key=f"refund:{refund['id']}",
                    kind="refund",
                    amount_cents=refund.get("amount"),
                    occurred_at=datetime.fromtimestamp(refund["created"], UTC).replace(tzinfo=None),
                    payment_intent_id=payment_intent,
                    invoice_id=_id(obj.get("invoice")),
                )
            )
    else:
        return
    for value in values:
        if (
            isinstance(value["amount_cents"], bool)
            or not isinstance(value["amount_cents"], int)
            or value["amount_cents"] < 0
        ):
            continue
        if BillingCashEvent.query.filter_by(source_key=value["source_key"]).first():
            continue
        try:
            with db.session.begin_nested():
                db.session.add(BillingCashEvent(**value))
                db.session.flush()
        except IntegrityError:
            if not BillingCashEvent.query.filter_by(source_key=value["source_key"]).first():
                raise


def observe_deployment():
    """CLI/deploy job records env truth once per supplied immutable deployment ID."""
    deployment = (os.getenv("CONTAINER_APP_REVISION") or os.getenv("AW_DEPLOYMENT_ID") or "").strip()
    if not deployment or not enabled():
        return None
    configured = os.getenv("NEWSLETTERS_FROZEN", "").lower() in {"1", "true", "yes", "on"}
    row = BusinessDeploymentState.query.filter_by(deployment_id=deployment).first()
    if row is None:
        row = BusinessDeploymentState(
            deployment_id=deployment[:200],
            api_football_frozen=api_football_frozen(),
            newsletters_configured_frozen=configured,
            newsletters_effective_frozen=newsletters_frozen(),
        )
        db.session.add(row)
    return row


def money_query(start, end):
    cash = sa.select(
        sa.literal("billing").label("source"),
        BillingCashEvent.id.label("id"),
        BillingCashEvent.kind.label("kind"),
        BillingCashEvent.amount_cents.label("amount_cents"),
        BillingCashEvent.currency.label("currency"),
        BillingCashEvent.occurred_at.label("occurred_at"),
        BillingCashEvent.product_code.label("product_code"),
        BillingCashEvent.purchaser_user_id.label("purchaser_user_id"),
        BillingCashEvent.payment_intent_id.label("payment_intent_id"),
        BillingCashEvent.scope_type.label("scope_type"),
        BillingCashEvent.scope_id.label("scope_id"),
    ).where(BillingCashEvent.occurred_at >= start, BillingCashEvent.occurred_at < end)
    gol = sa.select(
        sa.literal("gol").label("source"),
        GolCreditLedger.id.label("id"),
        sa.literal("receipt").label("kind"),
        GolCreditLedger.amount_paid_cents.label("amount_cents"),
        GolCreditLedger.currency.label("currency"),
        GolCreditLedger.created_at.label("occurred_at"),
        sa.literal("gol").label("product_code"),
        GolCreditLedger.user_account_id.label("purchaser_user_id"),
        GolCreditLedger.stripe_payment_intent_id.label("payment_intent_id"),
        sa.literal("user").label("scope_type"),
        GolCreditLedger.user_account_id.label("scope_id"),
    ).where(
        GolCreditLedger.kind == "grant",
        GolCreditLedger.bucket == "prepaid",
        GolCreditLedger.amount_paid_cents.is_not(None),
        GolCreditLedger.created_at >= start,
        GolCreditLedger.created_at < end,
        ~sa.exists().where(BillingCashEvent.source_key == sa.literal("gol:") + GolCreditLedger.stripe_session_id),
    )
    return cash.union_all(gol).subquery()


def record_business_boot(app):
    if not enabled() or not (os.getenv("CONTAINER_APP_REVISION") or os.getenv("AW_DEPLOYMENT_ID")):
        return
    with app.app_context():
        try:
            with db.session.begin_nested():
                observe_deployment()
                db.session.flush()
            db.session.commit()
        except IntegrityError:
            # Concurrent workers observing the same immutable revision.
            db.session.rollback()
