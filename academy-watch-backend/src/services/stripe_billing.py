"""Stripe Checkout, subscription projection, and idempotent webhook handling."""

from __future__ import annotations

import hashlib
import logging
import os
import re
from contextvars import ContextVar
from datetime import UTC, datetime, timedelta
from functools import wraps
from html import escape

import stripe
from flask import abort
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from src.config.stripe_config import (
    billing_enabled,
    configure_stripe,
    offered_products,
    product_for_price_id,
    resolve_price,
)
from src.models.billing import BillingCheckoutSession, BillingCustomer, BillingSubscription, StripeWebhookEvent
from src.models.league import UserAccount, db
from src.models.product_event import ProductEvent

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = frozenset({"active", "trialing", "past_due"})
_CLIENT_KEY_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
_email_intents: ContextVar[list[dict] | None] = ContextVar("billing_email_intents", default=None)


class BillingError(Exception):
    def __init__(self, code: str, status: int):
        super().__init__(code)
        self.code = code
        self.status = status


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _get(value, key, default=None):
    if value is None:
        return default
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _epoch_datetime(value) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=UTC).replace(tzinfo=None)
    except (TypeError, ValueError, OSError):
        return None


def _stripe_id(value) -> str | None:
    if isinstance(value, str):
        return value
    return _get(value, "id")


def require_billing_rail(view):
    """Hide a billing route completely while its rollout flag is off."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        if not billing_enabled():
            abort(404)
        return view(*args, **kwargs)

    return wrapped


def subscription_payload(row: BillingSubscription) -> dict:
    return {
        "id": row.id,
        "scope_type": row.scope_type,
        "scope_id": row.scope_id,
        "product_code": row.product_code,
        "price_code": row.price_code,
        "status": row.status,
        "is_active": row.status in ACTIVE_STATUSES,
        "current_period_end": row.current_period_end.isoformat() if row.current_period_end else None,
        "cancel_at_period_end": bool(row.cancel_at_period_end),
        "unit_amount": row.unit_amount,
        "currency": row.currency,
        "interval": row.interval,
    }


def ensure_customer(user) -> BillingCustomer:
    existing = BillingCustomer.query.filter_by(user_account_id=user.id).first()
    if existing is not None:
        return existing

    configure_stripe()
    customer = stripe.Customer.create(
        email=user.email,
        name=user.display_name,
        metadata={"user_id": str(user.id)},
        idempotency_key=f"customer:{user.id}",
    )
    row = BillingCustomer(user_account_id=user.id, stripe_customer_id=_get(customer, "id"))
    try:
        with db.session.begin_nested():
            db.session.add(row)
            db.session.flush()
        return row
    except IntegrityError:
        existing = BillingCustomer.query.filter_by(user_account_id=user.id).first()
        if existing is None:
            raise
        return existing


def active_subscription(scope_type, scope_id, product_code) -> BillingSubscription | None:
    return (
        BillingSubscription.query.filter(
            BillingSubscription.scope_type == scope_type,
            BillingSubscription.scope_id == scope_id,
            BillingSubscription.product_code == product_code,
            BillingSubscription.status.in_(ACTIVE_STATUSES),
        )
        .order_by(BillingSubscription.current_period_end.desc().nullslast(), BillingSubscription.id.desc())
        .first()
    )


def subscriptions_for_user(user) -> list[BillingSubscription]:
    return (
        BillingSubscription.query.filter(
            or_(
                BillingSubscription.purchaser_user_id == user.id,
                (BillingSubscription.scope_type == "user") & (BillingSubscription.scope_id == user.id),
            )
        )
        .order_by(BillingSubscription.created_at.desc(), BillingSubscription.id.desc())
        .all()
    )


def _checkout_key(scope_type: str, scope_id: int, product_code: str, user_id: int, client_key: str) -> str:
    return f"checkout:{scope_type}:{scope_id}:{product_code}:{user_id}:{client_key}"


def create_checkout(user, *, product_code, price_code, client_key, scope_id=None) -> dict:
    if not isinstance(client_key, str) or not _CLIENT_KEY_RE.fullmatch(client_key):
        raise BillingError("invalid_client_key", 400)
    if not isinstance(product_code, str) or not isinstance(price_code, str):
        raise BillingError("unknown_product", 400)

    product = offered_products().get(product_code)
    price_id = resolve_price(product_code, price_code)
    if product is None or price_id is None:
        raise BillingError("unknown_product", 400)
    if product["scope_type"] == "club_program":
        raise BillingError("product_not_available", 403)

    resolved_scope_id = user.id if product["scope_type"] == "user" else scope_id
    if active_subscription(product["scope_type"], resolved_scope_id, product_code) is not None:
        raise BillingError("already_subscribed", 409)

    now = utcnow()
    row = BillingCheckoutSession.query.filter_by(
        scope_type=product["scope_type"],
        scope_id=resolved_scope_id,
        product_code=product_code,
        purchaser_user_id=user.id,
        client_key=client_key,
    ).first()
    if row is not None and row.status == "open" and row.expires_at is not None and row.expires_at > now:
        return {"checkout_url": row.checkout_url, "session_id": row.stripe_session_id}

    customer = ensure_customer(user)
    if row is None:
        contender = BillingCheckoutSession(
            scope_type=product["scope_type"],
            scope_id=resolved_scope_id,
            product_code=product_code,
            price_code=price_code,
            purchaser_user_id=user.id,
            client_key=client_key,
        )
        try:
            with db.session.begin_nested():
                db.session.add(contender)
                db.session.flush()
            row = contender
        except IntegrityError:
            row = BillingCheckoutSession.query.filter_by(
                scope_type=product["scope_type"],
                scope_id=resolved_scope_id,
                product_code=product_code,
                purchaser_user_id=user.id,
                client_key=client_key,
            ).first()
            if row is None:
                raise
            if row.status == "open" and row.expires_at is not None and row.expires_at > now:
                return {"checkout_url": row.checkout_url, "session_id": row.stripe_session_id}
            row.price_code = price_code
            row.status = "open"
            row.completed_at = None
    else:
        row.price_code = price_code
        row.status = "open"
        row.completed_at = None
    db.session.flush()

    metadata = {
        "scope_type": product["scope_type"],
        "scope_id": str(resolved_scope_id),
        "product_code": product_code,
        "price_code": price_code,
        "purchaser_user_id": str(user.id),
        "app": "academy_watch",
    }
    base_url = (os.getenv("PUBLIC_BASE_URL") or "https://theacademywatch.com").strip().rstrip("/")
    configure_stripe()
    session = stripe.checkout.Session.create(
        mode="subscription",
        customer=customer.stripe_customer_id,
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{base_url}/account/billing?checkout=success&session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{base_url}/pricing?checkout=canceled",
        client_reference_id=str(row.id),
        allow_promotion_codes=True,
        metadata=metadata,
        subscription_data={"metadata": metadata},
        idempotency_key=_checkout_key(product["scope_type"], resolved_scope_id, product_code, user.id, client_key),
    )
    row.stripe_session_id = _get(session, "id")
    row.checkout_url = _get(session, "url")
    row.expires_at = _epoch_datetime(_get(session, "expires_at"))
    row.status = "open"
    db.session.add(
        ProductEvent(
            event_name="billing_checkout_started",
            user_email=user.email,
            props={"product_code": product_code, "price_code": price_code, "scope_type": product["scope_type"]},
        )
    )
    db.session.flush()
    return {"checkout_url": row.checkout_url, "session_id": row.stripe_session_id}


def create_portal_session(user) -> str:
    customer = BillingCustomer.query.filter_by(user_account_id=user.id).first()
    if customer is None:
        raise BillingError("no_billing_account", 409)
    base_url = (os.getenv("PUBLIC_BASE_URL") or "https://theacademywatch.com").strip().rstrip("/")
    configure_stripe()
    session = stripe.billing_portal.Session.create(
        customer=customer.stripe_customer_id,
        return_url=f"{base_url}/account/billing",
    )
    return _get(session, "url")


def _first_item(sub):
    items = _get(_get(sub, "items", {}), "data", []) or []
    return items[0] if items else None


def _queue_email(kind: str, row: BillingSubscription) -> None:
    intents = _email_intents.get()
    if intents is None or row.purchaser_user_id is None:
        return
    user = db.session.get(UserAccount, row.purchaser_user_id)
    if user is None or not user.email:
        return
    intents.append({"kind": kind, "recipient": user.email, "name": user.display_name or "there"})


def _write_transition_event(name: str, row: BillingSubscription) -> None:
    user = db.session.get(UserAccount, row.purchaser_user_id) if row.purchaser_user_id else None
    db.session.add(
        ProductEvent(
            event_name=name,
            user_email=user.email if user else None,
            props={"product_code": row.product_code, "price_code": row.price_code, "scope_type": row.scope_type},
        )
    )


def upsert_subscription(sub, *, event_created: int | None) -> BillingSubscription | None:
    subscription_id = _get(sub, "id")
    row = BillingSubscription.query.filter_by(stripe_subscription_id=subscription_id).first()
    if (
        row is not None
        and event_created is not None
        and row.last_event_created is not None
        and event_created < row.last_event_created
    ):
        return row

    item = _first_item(sub)
    price = _get(item, "price", {})
    price_id = _get(price, "id")
    metadata = _get(sub, "metadata", {}) or {}
    metadata_fields = ("scope_type", "scope_id", "product_code", "price_code", "purchaser_user_id")
    if all(_get(metadata, field) not in (None, "") for field in metadata_fields):
        try:
            scope_type = str(_get(metadata, "scope_type"))
            scope_id = int(_get(metadata, "scope_id"))
            product_code = str(_get(metadata, "product_code"))
            price_code = str(_get(metadata, "price_code"))
            purchaser_user_id = int(_get(metadata, "purchaser_user_id"))
        except (TypeError, ValueError) as exc:
            raise BillingError("unresolvable_subscription", 500) from exc
        if scope_type not in {"user", "club_program"}:
            raise BillingError("unresolvable_subscription", 500)
    else:
        product = product_for_price_id(price_id)
        customer_id = _stripe_id(_get(sub, "customer"))
        customer = BillingCustomer.query.filter_by(stripe_customer_id=customer_id).first()
        if product is None or customer is None:
            raise BillingError("unresolvable_subscription", 500)
        product_code, price_code = product
        scope_type = "user"
        scope_id = customer.user_account_id
        purchaser_user_id = customer.user_account_id

    previous_status = row.status if row is not None else None
    if row is None:
        row = BillingSubscription(stripe_subscription_id=subscription_id)
        db.session.add(row)

    recurring = _get(price, "recurring", {}) or {}
    customer_id = _stripe_id(_get(sub, "customer"))
    row.scope_type = scope_type
    row.scope_id = scope_id
    row.product_code = product_code
    row.price_code = price_code
    row.purchaser_user_id = purchaser_user_id
    row.stripe_customer_id = customer_id
    row.stripe_price_id = price_id
    row.status = str(_get(sub, "status") or "unknown")
    row.unit_amount = _get(price, "unit_amount")
    currency = _get(price, "currency")
    row.currency = str(currency).lower() if currency else None
    row.interval = _get(recurring, "interval")
    row.current_period_start = _epoch_datetime(_get(item, "current_period_start", _get(sub, "current_period_start")))
    row.current_period_end = _epoch_datetime(_get(item, "current_period_end", _get(sub, "current_period_end")))
    row.cancel_at_period_end = bool(_get(sub, "cancel_at_period_end", False))
    row.canceled_at = _epoch_datetime(_get(sub, "canceled_at"))
    if event_created is not None:
        row.last_event_created = event_created
    db.session.flush()

    project_entitlements(row)
    was_active = previous_status in ACTIVE_STATUSES
    is_active = row.status in ACTIVE_STATUSES
    if not was_active and is_active:
        _write_transition_event("billing_subscription_activated", row)
        _queue_email("subscription_activated", row)
    elif was_active and not is_active:
        _write_transition_event("billing_subscription_ended", row)
        _queue_email("subscription_ended", row)
    return row


def project_entitlements(row) -> None:
    if row.scope_type != "user" or row.product_code != "scout_pro":
        return
    user = db.session.get(UserAccount, row.scope_id)
    if user is not None:
        user.scout_tier = "pro" if active_subscription("user", row.scope_id, "scout_pro") else "free"


def _checkout_row(obj) -> BillingCheckoutSession | None:
    session_id = _get(obj, "id")
    row = BillingCheckoutSession.query.filter_by(stripe_session_id=session_id).first() if session_id else None
    if row is None:
        try:
            reference_id = int(_get(obj, "client_reference_id"))
        except (TypeError, ValueError):
            reference_id = None
        if reference_id is not None:
            row = db.session.get(BillingCheckoutSession, reference_id)
    return row


def _invoice_subscription_id(invoice) -> str | None:
    direct = _stripe_id(_get(invoice, "subscription"))
    if direct:
        return direct
    parent = _get(invoice, "parent", {}) or {}
    details = _get(parent, "subscription_details", {}) or {}
    return _stripe_id(_get(details, "subscription"))


def _retrieve_subscription(subscription_id: str):
    configure_stripe()
    return stripe.Subscription.retrieve(subscription_id, expand=["items.data.price"])


def _retrieve_event_watermark(subscription_id: str, event_created: int | None) -> int | None:
    row = BillingSubscription.query.filter_by(stripe_subscription_id=subscription_id).first()
    existing = row.last_event_created if row is not None else None
    if event_created is None:
        return existing
    if existing is None:
        return event_created
    return max(event_created, existing)


def _apply_event(event_type: str, obj, event_created: int | None) -> bool:
    if event_type == "checkout.session.completed":
        row = _checkout_row(obj)
        if row is not None:
            row.status = "complete"
            row.completed_at = utcnow()
        subscription_id = _stripe_id(_get(obj, "subscription"))
        if subscription_id:
            snapshot = _retrieve_subscription(subscription_id)
            upsert_subscription(
                snapshot,
                event_created=_retrieve_event_watermark(subscription_id, event_created),
            )
        return True
    if event_type == "checkout.session.expired":
        row = _checkout_row(obj)
        if row is not None:
            row.status = "expired"
        return True
    if event_type in {
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    }:
        subscription_id = _get(obj, "id")
        previous = BillingSubscription.query.filter_by(stripe_subscription_id=subscription_id).first()
        was_active = previous is not None and previous.status in ACTIVE_STATUSES
        row = upsert_subscription(obj, event_created=event_created)
        applied = row is not None and (event_created is None or row.last_event_created == event_created)
        if event_type == "customer.subscription.deleted" and applied and not was_active:
            _write_transition_event("billing_subscription_ended", row)
            _queue_email("subscription_ended", row)
        return True
    if event_type in {"invoice.paid", "invoice.payment_failed"}:
        subscription_id = _invoice_subscription_id(obj)
        row = None
        if subscription_id:
            snapshot = _retrieve_subscription(subscription_id)
            row = upsert_subscription(
                snapshot,
                event_created=_retrieve_event_watermark(subscription_id, event_created),
            )
        if event_type == "invoice.payment_failed" and row is not None:
            _queue_email("payment_failed", row)
        return True
    return False


def _send_email_intent(intent: dict) -> None:
    subjects = {
        "subscription_activated": "Your Scout Pro subscription is active",
        "subscription_ended": "Your Scout Pro subscription has ended",
        "payment_failed": "Your Scout Pro payment failed",
    }
    messages = {
        "subscription_activated": "Your Scout Pro subscription is now active.",
        "subscription_ended": "Your Scout Pro subscription has ended.",
        "payment_failed": "Stripe reported that your Scout Pro payment failed. Review your billing details.",
    }
    kind = intent["kind"]
    safe_name = escape(intent["name"])
    safe_message = escape(messages[kind])
    try:
        from src.services.email_service import email_service

        delivery = email_service.send_email(
            to=intent["recipient"],
            subject=subjects[kind],
            text=f"Hello {intent['name']},\n\n{messages[kind]}\n\nThe Academy Watch",
            html=f"<p>Hello {safe_name},</p><p>{safe_message}</p><p>The Academy Watch</p>",
            tags=[kind.replace("_", "-")],
            use_fallback=False,
        )
        if not getattr(delivery, "success", False):
            logger.warning("Billing status email was not delivered: %s", kind)
    except Exception:
        logger.exception("Billing status email dispatch failed: %s", kind)


def _record_failed_event(event_id: str, event_type: str, payload_hash: str, error: Exception) -> None:
    row = StripeWebhookEvent.query.filter_by(event_id=event_id).first()
    if row is None:
        row = StripeWebhookEvent(event_id=event_id, received_at=utcnow())
        db.session.add(row)
    row.event_type = event_type
    row.payload_hash = payload_hash
    row.status = "failed"
    row.error = str(error)[:2000]
    row.processed_at = None
    db.session.commit()


def handle_webhook(raw_body: bytes, signature_header: str | None) -> tuple[dict, int]:
    secret = (os.getenv("STRIPE_WEBHOOK_SECRET") or "").strip()
    if not secret:
        return {"error": "invalid_signature"}, 400
    try:
        event = stripe.Webhook.construct_event(raw_body, signature_header, secret)
    except Exception:
        return {"error": "invalid_signature"}, 400

    event_id = str(_get(event, "id"))
    event_type = str(_get(event, "type"))
    event_created = _get(event, "created")
    payload_hash = hashlib.sha256(raw_body).hexdigest()
    existing = StripeWebhookEvent.query.filter_by(event_id=event_id).first()
    if existing is not None and existing.status in {"processed", "ignored"}:
        return {"received": True, "duplicate": True}, 200

    if existing is None:
        try:
            with db.session.begin_nested():
                existing = StripeWebhookEvent(
                    event_id=event_id,
                    event_type=event_type,
                    payload_hash=payload_hash,
                    status="failed",
                    received_at=utcnow(),
                )
                db.session.add(existing)
                db.session.flush()
        except IntegrityError:
            existing = StripeWebhookEvent.query.filter_by(event_id=event_id).first()
            if existing is not None and existing.status in {"processed", "ignored"}:
                return {"received": True, "duplicate": True}, 200

    intents: list[dict] = []
    token = _email_intents.set(intents)
    try:
        obj = _get(_get(event, "data", {}), "object", {})
        applied = _apply_event(event_type, obj, int(event_created) if event_created is not None else None)
        existing.event_type = event_type
        existing.payload_hash = payload_hash
        existing.status = "processed" if applied else "ignored"
        existing.error = None
        existing.processed_at = utcnow()
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        logger.exception("Stripe webhook application failed for event %s", event_id)
        try:
            _record_failed_event(event_id, event_type, payload_hash, exc)
        except Exception:
            db.session.rollback()
            logger.exception("Failed to persist Stripe webhook failure for event %s", event_id)
        return {"error": "processing_failed"}, 500
    finally:
        _email_intents.reset(token)

    for intent in intents:
        _send_email_intent(intent)
    return {"received": True, "duplicate": False}, 200


def admin_summary() -> dict:
    now = utcnow()
    cutoff_30d = now - timedelta(days=30)
    cutoff_24h = now - timedelta(hours=24)
    active_rows = BillingSubscription.query.filter(BillingSubscription.status.in_(ACTIVE_STATUSES)).all()
    by_product: dict[str, int] = {}
    mrr_cents = 0
    for row in active_rows:
        by_product[row.product_code] = by_product.get(row.product_code, 0) + 1
        if row.unit_amount is not None and row.interval == "month":
            mrr_cents += row.unit_amount
        elif row.unit_amount is not None and row.interval == "year":
            mrr_cents += round(row.unit_amount / 12)
    return {
        "active_subscriptions": len(active_rows),
        "by_product": by_product,
        "mrr_cents": mrr_cents,
        "currency": "usd",
        "past_due": BillingSubscription.query.filter_by(status="past_due").count(),
        "canceled_last_30d": BillingSubscription.query.filter(BillingSubscription.canceled_at >= cutoff_30d).count(),
        "webhook_events_last_24h": StripeWebhookEvent.query.filter(
            StripeWebhookEvent.received_at >= cutoff_24h
        ).count(),
        "webhook_failed_last_24h": StripeWebhookEvent.query.filter(
            StripeWebhookEvent.received_at >= cutoff_24h,
            StripeWebhookEvent.status == "failed",
        ).count(),
        "checkout_sessions_open": BillingCheckoutSession.query.filter(
            BillingCheckoutSession.status == "open",
            BillingCheckoutSession.expires_at > now,
        ).count(),
    }


def cancel_subscriptions_for_account_deletion(user) -> int:
    rows = BillingSubscription.query.filter(
        BillingSubscription.scope_type == "user",
        BillingSubscription.scope_id == user.id,
        BillingSubscription.status.in_(ACTIVE_STATUSES),
    ).all()
    if not rows or not (os.getenv("STRIPE_SECRET_KEY") or "").strip():
        return 0
    configure_stripe()
    try:
        for row in rows:
            stripe.Subscription.cancel(row.stripe_subscription_id)
    except Exception as exc:
        raise BillingError("billing_cancel_failed", 503) from exc
    return len(rows)


__all__ = [
    "ACTIVE_STATUSES",
    "BillingError",
    "active_subscription",
    "admin_summary",
    "cancel_subscriptions_for_account_deletion",
    "create_checkout",
    "create_portal_session",
    "ensure_customer",
    "handle_webhook",
    "project_entitlements",
    "require_billing_rail",
    "subscription_payload",
    "subscriptions_for_user",
    "upsert_subscription",
]
