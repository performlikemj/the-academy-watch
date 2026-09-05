"""Stripe Checkout, subscription projection, and idempotent webhook handling."""

from __future__ import annotations

import calendar
import hashlib
import logging
import os
import re
import time
from contextvars import ContextVar
from datetime import UTC, datetime, timedelta
from functools import wraps
from html import escape
from uuid import uuid4

import stripe
from flask import abort
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from src.config.stripe_config import (
    billing_enabled,
    configure_stripe,
    offered_packs,
    offered_products,
    price_details,
    product_for_price_id,
    resolve_price,
)
from src.models.billing import (
    BillingCheckoutSession,
    BillingCustomer,
    BillingSubscription,
    GolCheckoutTerms,
    StripeWebhookEvent,
)
from src.models.gol_credits import GolCreditLedger, GolPaymentSettlement
from src.models.league import UserAccount, db
from src.models.product_event import ProductEvent
from src.services.gol_credits import apply_refund, grant_purchase

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = frozenset({"active", "trialing", "past_due"})
TERMINAL_STATUSES = frozenset({"canceled", "incomplete_expired"})
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


def _expire_or_retrieve_checkout(row: BillingCheckoutSession):
    if not row.stripe_session_id:
        raise BillingError("checkout_expiry_failed", 500)
    configure_stripe()
    try:
        stripe.checkout.Session.expire(row.stripe_session_id)
    except stripe.InvalidRequestError:
        return stripe.checkout.Session.retrieve(row.stripe_session_id)
    return {"status": "expired"}


def _create_payment_checkout(user, *, pack_id: str, client_key: str) -> dict:
    pack = offered_packs().get(pack_id)
    if pack is None:
        raise BillingError("unknown_pack", 400)
    details = price_details(pack["price_id"])
    if not details:
        raise BillingError("checkout_unavailable", 503)
    if details.get("currency") != "usd":
        raise BillingError("unknown_pack", 400)

    db.session.execute(select(UserAccount.id).where(UserAccount.id == user.id).with_for_update())
    now = utcnow()
    row = BillingCheckoutSession.query.filter_by(
        scope_type="user",
        scope_id=user.id,
        product_code="gol",
        purchaser_user_id=user.id,
        client_key=client_key,
    ).first()
    if row is not None and row.status == "open":
        if row.price_code != pack_id:
            raise BillingError("client_key_conflict", 409)
        if row.expires_at is not None and row.expires_at > now:
            return {"checkout_url": row.checkout_url, "session_id": row.stripe_session_id}
    if row is not None and row.status == "complete":
        raise BillingError("client_key_conflict", 409)

    customer = ensure_customer(user)
    if row is None:
        contender = BillingCheckoutSession(
            scope_type="user",
            scope_id=user.id,
            product_code="gol",
            price_code=pack_id,
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
                scope_type="user",
                scope_id=user.id,
                product_code="gol",
                purchaser_user_id=user.id,
                client_key=client_key,
            ).first()
            if row is None:
                raise
            if row.status == "open":
                if row.price_code != pack_id:
                    raise BillingError("client_key_conflict", 409)
                if row.expires_at is not None and row.expires_at > now:
                    return {"checkout_url": row.checkout_url, "session_id": row.stripe_session_id}
            if row.status == "complete":
                raise BillingError("client_key_conflict", 409)

    row.price_code = pack_id
    row.status = "open"
    row.completed_at = None
    db.session.flush()

    # A pending purchase survives a crash after remote creation. Reuse its key and
    # immutable parameters, including when another request is still calling Stripe.
    terms = GolCheckoutTerms.query.filter_by(checkout_row_id=row.id, stripe_session_id=None).first()
    if terms is None:
        terms = GolCheckoutTerms(
            purchase_key=str(uuid4()),
            checkout_row_id=row.id,
            price_code=pack_id,
            credits=pack["credits"],
            unit_amount_cents=details["unit_amount"],
            currency=details["currency"],
            stripe_price_id=pack["price_id"],
        )
        db.session.add(terms)
    db.session.flush()
    terms_id, user_id, row_id = terms.id, user.id, row.id
    purchase_key, price_id, terms_pack = terms.purchase_key, terms.stripe_price_id, terms.price_code
    customer_id = customer.stripe_customer_id
    db.session.commit()  # Durable BEFORE Session.create, even if attachment never runs.

    metadata = {
        "kind": "credit_topup",
        "product_code": "gol",
        "pack_id": terms_pack,
        "user_id": str(user_id),
        "app": "academy_watch",
        "purchase_key": purchase_key,
    }
    base_url = (os.getenv("PUBLIC_BASE_URL") or "https://theacademywatch.com").strip().rstrip("/")
    configure_stripe()
    session = stripe.checkout.Session.create(
        mode="payment",
        customer=customer_id,
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{base_url}/account/billing?checkout=success&session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{base_url}/pricing?checkout=canceled",
        client_reference_id=purchase_key,
        metadata=metadata,
        payment_intent_data={"metadata": metadata},
        idempotency_key=f"checkout:gol:{terms_pack}:{user_id}:{client_key}:{purchase_key}",
    )
    db.session.execute(select(UserAccount.id).where(UserAccount.id == user_id).with_for_update())
    terms = db.session.execute(
        select(GolCheckoutTerms)
        .where(GolCheckoutTerms.id == terms_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one()
    _attach_terms(terms, _get(session, "id"))
    row = db.session.get(BillingCheckoutSession, row_id, populate_existing=True)
    latest_terms = GolCheckoutTerms.query.filter_by(checkout_row_id=row_id).order_by(GolCheckoutTerms.id.desc()).first()
    if row is not None and latest_terms is not None and latest_terms.id == terms_id:
        row.stripe_session_id = _get(session, "id")
        row.checkout_url = _get(session, "url")
        row.expires_at = _epoch_datetime(_get(session, "expires_at"))
        db.session.add(
            ProductEvent(
                event_name="billing_checkout_started",
                user_email=user.email,
                props={"product_code": "gol", "price_code": terms_pack, "scope_type": "user"},
            )
        )
    db.session.flush()
    return {"checkout_url": _get(session, "url"), "session_id": _get(session, "id")}


def create_checkout(
    user,
    *,
    client_key,
    pack_id=None,
    product_code=None,
    price_code=None,
    scope_id=None,
) -> dict:
    if not isinstance(client_key, str) or not _CLIENT_KEY_RE.fullmatch(client_key):
        raise BillingError("invalid_client_key", 400)
    payment_request = pack_id is not None
    subscription_request = product_code is not None or price_code is not None
    if payment_request == subscription_request:
        raise BillingError("invalid_checkout_request", 400)
    if payment_request:
        if not isinstance(pack_id, str):
            raise BillingError("unknown_pack", 400)
        return _create_payment_checkout(user, pack_id=pack_id, client_key=client_key)
    if not isinstance(product_code, str) or not isinstance(price_code, str):
        raise BillingError("unknown_product", 400)

    product = offered_products().get(product_code)
    price_id = resolve_price(product_code, price_code)
    if product is None or price_id is None:
        raise BillingError("unknown_product", 400)
    if product["scope_type"] == "club_program":
        raise BillingError("product_not_available", 403)

    resolved_scope_id = user.id if product["scope_type"] == "user" else scope_id
    db.session.execute(select(UserAccount.id).where(UserAccount.id == user.id).with_for_update())
    if active_subscription(product["scope_type"], resolved_scope_id, product_code) is not None:
        raise BillingError("already_subscribed", 409)

    now = utcnow()
    open_row = (
        BillingCheckoutSession.query.filter(
            BillingCheckoutSession.scope_type == product["scope_type"],
            BillingCheckoutSession.scope_id == resolved_scope_id,
            BillingCheckoutSession.product_code == product_code,
            BillingCheckoutSession.status == "open",
            BillingCheckoutSession.expires_at > now,
        )
        .order_by(BillingCheckoutSession.expires_at.desc(), BillingCheckoutSession.id.desc())
        .first()
    )
    if open_row is not None:
        if open_row.price_code == price_code:
            return {"checkout_url": open_row.checkout_url, "session_id": open_row.stripe_session_id}
        try:
            snapshot = _expire_or_retrieve_checkout(open_row)
        except stripe.InvalidRequestError:
            snapshot = {"status": "expired"}
        status = _get(snapshot, "status")
        if status == "expired":
            open_row.status = "expired"
        elif status == "complete":
            open_row.status = "complete"
            open_row.completed_at = open_row.completed_at or utcnow()
            raise BillingError("already_subscribed", 409)
        else:
            raise BillingError("checkout_expiry_failed", 503)

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
    idempotency_key = _checkout_key(product["scope_type"], resolved_scope_id, product_code, user.id, client_key)
    if row.stripe_session_id:
        attempt_at = row.expires_at or row.created_at
        if attempt_at is not None:
            idempotency_key = f"{idempotency_key}:{calendar.timegm(attempt_at.utctimetuple())}"
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
        idempotency_key=idempotency_key,
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


def upsert_subscription(
    sub,
    *,
    event_created: int | None,
    retrieve_on_stale: bool = False,
) -> BillingSubscription | None:
    subscription_id = _get(sub, "id")
    row = BillingSubscription.query.filter_by(stripe_subscription_id=subscription_id).first()
    if (
        row is not None
        and event_created is not None
        and row.last_event_created is not None
        and event_created < row.last_event_created
    ):
        if retrieve_on_stale:
            snapshot = _retrieve_subscription(subscription_id)
            return upsert_subscription(
                snapshot,
                event_created=_retrieve_event_watermark(subscription_id, event_created),
            )
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

    scope_user_id = None
    if scope_type == "user":
        scope_user_id = db.session.execute(
            select(UserAccount.id).where(UserAccount.id == scope_id).with_for_update()
        ).scalar_one_or_none()
        row = (
            db.session.execute(
                select(BillingSubscription)
                .where(BillingSubscription.stripe_subscription_id == subscription_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            .scalars()
            .one_or_none()
        )
        if (
            row is not None
            and event_created is not None
            and row.last_event_created is not None
            and event_created < row.last_event_created
        ):
            if retrieve_on_stale:
                snapshot = _retrieve_subscription(subscription_id)
                return upsert_subscription(
                    snapshot,
                    event_created=_retrieve_event_watermark(subscription_id, event_created),
                )
            return row

    if row is None and scope_type == "user" and scope_user_id is None:
        logger.info("Ignoring Stripe subscription %s for deleted user scope %s", subscription_id, scope_id)
        return None

    if row is not None and purchaser_user_id is not None and db.session.get(UserAccount, purchaser_user_id) is None:
        purchaser_user_id = None

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
    elif was_active and not is_active and active_subscription(row.scope_type, row.scope_id, row.product_code) is None:
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


def _retrieve_event_watermark(subscription_id: str, event_created: int | None) -> int:
    row = BillingSubscription.query.filter_by(stripe_subscription_id=subscription_id).first()
    existing = row.last_event_created if row is not None else None
    return max(value for value in (existing, event_created, int(time.time())) if value is not None)


def _cancel_duplicate_subscription(subscription_id: str) -> None:
    try:
        stripe.Subscription.cancel(subscription_id)
    except stripe.InvalidRequestError:
        snapshot = stripe.Subscription.retrieve(subscription_id)
        if _get(snapshot, "status") != "canceled":
            raise


def _expire_other_open_checkouts(
    completed: BillingCheckoutSession,
    kept_subscription_id: str | None,
) -> None:
    siblings = BillingCheckoutSession.query.filter(
        BillingCheckoutSession.scope_type == completed.scope_type,
        BillingCheckoutSession.scope_id == completed.scope_id,
        BillingCheckoutSession.product_code == completed.product_code,
        BillingCheckoutSession.status == "open",
        BillingCheckoutSession.id != completed.id,
    ).all()
    for sibling in siblings:
        if not sibling.stripe_session_id:
            sibling.status = "expired"
            continue
        snapshot = _expire_or_retrieve_checkout(sibling)
        status = _get(snapshot, "status")
        if status == "expired":
            sibling.status = "expired"
            continue
        if status == "complete":
            subscription_id = _stripe_id(_get(snapshot, "subscription"))
            if not subscription_id:
                raise BillingError("checkout_expiry_failed", 500)
            _cancel_duplicate_subscription(subscription_id)
            logger.warning(
                "Canceled duplicate Stripe subscription %s; keeping subscription %s",
                subscription_id,
                kept_subscription_id,
            )
            purchaser = db.session.get(UserAccount, completed.purchaser_user_id)
            db.session.add(
                ProductEvent(
                    event_name="billing_duplicate_canceled",
                    user_email=purchaser.email if purchaser else None,
                    props={
                        "kept_subscription_id": kept_subscription_id,
                        "canceled_subscription_id": subscription_id,
                        "product_code": completed.product_code,
                        "scope_type": completed.scope_type,
                    },
                )
            )
            sibling.status = "complete"
            sibling.completed_at = sibling.completed_at or utcnow()
            continue
        raise BillingError("checkout_expiry_failed", 500)


def _lock_gol_settlement(payment_intent_id):
    """All settlement decisions take this lock BEFORE the user/purchase lock."""
    if not payment_intent_id:
        return None
    if GolPaymentSettlement.query.filter_by(stripe_payment_intent_id=payment_intent_id).first() is None:
        try:
            with db.session.begin_nested():
                db.session.add(GolPaymentSettlement(stripe_payment_intent_id=payment_intent_id))
                db.session.flush()
        except IntegrityError:
            pass
    return db.session.execute(
        select(GolPaymentSettlement)
        .where(GolPaymentSettlement.stripe_payment_intent_id == payment_intent_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one()


def _settle_gol_refund(settlement, grant):
    settlement.grant_ledger_id = grant.id
    if settlement.refund_target_cents <= settlement.refund_applied_cents:
        return
    reversed_credits = apply_refund(
        payment_intent_id=settlement.stripe_payment_intent_id,
        cumulative_refunded_cents=settlement.refund_target_cents,
        stripe_event_id=settlement.last_refund_event_id,
    )
    settlement.refund_applied_cents = settlement.refund_target_cents
    if reversed_credits > 0:
        user = db.session.get(UserAccount, grant.user_account_id)
        db.session.add(
            ProductEvent(
                event_name="gol_credits_refunded",
                user_email=user.email if user else None,
                props={"credits": reversed_credits, "pack_id": grant.pack_id},
            )
        )


def _attach_terms(terms, session_id):
    if terms.stripe_session_id not in (None, session_id):
        raise BillingError("purchase_session_conflict", 500)
    terms.stripe_session_id = session_id
    terms.attached_at = terms.attached_at or utcnow()


def _purchase_event_exists(name, purchase_key):
    # JSONB lookup is confined to the rare orphan path, not normal fulfilment;
    # keep the existing event indexes rather than indexing every purchase key.
    return (
        ProductEvent.query.filter(
            ProductEvent.event_name == name,
            ProductEvent.props["purchase_key"].as_string() == purchase_key,
        ).first()
        is not None
    )


def _apply_gol_checkout(obj, event_id: str, *, require_paid: bool) -> bool:
    session_id = _get(obj, "id")
    if not session_id:
        return False
    payment_status = _get(obj, "payment_status")
    if require_paid and payment_status not in {"paid", "no_payment_required"}:
        # Unpaid completions cannot prove a charge, so they exit silently here
        # and never reach the orphan/manual-refund classification below.
        return False
    terms = GolCheckoutTerms.query.filter_by(stripe_session_id=session_id).first()
    if terms is None:
        purchase_key = _get(_get(obj, "metadata", {}), "purchase_key")
        terms = GolCheckoutTerms.query.filter_by(purchase_key=purchase_key).first() if purchase_key else None
    # Legacy lookup must be by exact session, never a reused client_reference_id.
    row = db.session.get(BillingCheckoutSession, terms.checkout_row_id) if terms and terms.checkout_row_id else None
    if terms is None:
        row = BillingCheckoutSession.query.filter_by(stripe_session_id=session_id, product_code="gol").first()
    payment_intent_id = _stripe_id(_get(obj, "payment_intent"))
    settlement = _lock_gol_settlement(payment_intent_id)
    user = None
    if row is not None and row.product_code == "gol":
        user = db.session.execute(
            select(UserAccount)
            .where(UserAccount.id == row.purchaser_user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).scalar_one_or_none()
    if terms is not None:
        terms = db.session.execute(
            select(GolCheckoutTerms)
            .where(GolCheckoutTerms.id == terms.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).scalar_one()
        _attach_terms(terms, session_id)
    if user is None or user.is_tombstone:
        if terms is not None and (not require_paid or payment_status == "paid"):
            if not (
                _purchase_event_exists("gol_orphaned_purchase", terms.purchase_key)
                or _purchase_event_exists("gol_credits_purchased", terms.purchase_key)
            ):
                db.session.add(
                    ProductEvent(
                        event_name="gol_orphaned_purchase",
                        props={
                            "purchase_key": terms.purchase_key,
                            "session_id": session_id,
                            "payment_intent": payment_intent_id,
                            "amount_total": _get(obj, "amount_total"),
                            "currency": _get(obj, "currency"),
                        },
                    )
                )
                logger.warning("Orphaned paid GOL purchase %s requires manual refund", session_id)
        else:
            logger.warning("Ignoring payment session without an owned GOL purchase: %s", session_id)
        return False
    if terms is not None:
        credits, pack_id = terms.credits, terms.price_code
        if _get(obj, "amount_total") != terms.unit_amount_cents:
            logger.warning("GOL checkout amount differs from purchase terms for session %s", session_id)
    else:
        logger.warning("Legacy GOL session %s has no purchase terms; using current pack", session_id)
        pack_id = row.price_code
        pack = offered_packs().get(pack_id)
        if pack is None:
            logger.warning("Unfulfillable legacy GOL purchase %s: pack no longer offered", session_id)
            # The user lock serializes the session-id dedupe for legacy purchases.
            existing_incident = ProductEvent.query.filter(
                ProductEvent.event_name == "gol_unfulfillable_legacy_purchase",
                ProductEvent.props["session_id"].as_string() == session_id,
            ).first()
            if existing_incident is None:
                db.session.add(
                    ProductEvent(
                        event_name="gol_unfulfillable_legacy_purchase",
                        props={
                            "session_id": session_id,
                            "payment_intent": payment_intent_id,
                            "amount_total": _get(obj, "amount_total"),
                            "currency": _get(obj, "currency"),
                            "pack_id": pack_id,
                        },
                    )
                )
            return False
        credits = pack["credits"]
    currency, amount_total = _get(obj, "currency"), _get(obj, "amount_total")
    if not currency or amount_total is None:
        raise BillingError("unresolvable_credit_purchase", 500)
    # The user lock serializes legacy grants; new purchases also hold their terms lock.
    existing = GolCreditLedger.query.filter_by(stripe_session_id=session_id).first()
    grant = grant_purchase(
        user,
        pack_id=pack_id,
        credits=credits,
        stripe_session_id=session_id,
        stripe_payment_intent_id=payment_intent_id,
        stripe_event_id=event_id,
        amount_paid_cents=amount_total,
        currency=currency,
    )
    if settlement is not None:
        _settle_gol_refund(settlement, grant)
    if row.stripe_session_id in (None, session_id):
        row.status = "complete"
        row.completed_at = row.completed_at or utcnow()
    if existing is None:
        props = {"pack_id": pack_id, "credits": grant.delta}
        if terms:
            props["purchase_key"] = terms.purchase_key
        db.session.add(ProductEvent(event_name="gol_credits_purchased", user_email=user.email, props=props))
    return True


def _apply_event(event_type: str, obj, event_created: int | None, event_id: str) -> bool:
    if event_type == "checkout.session.completed":
        row = _checkout_row(obj)
        if _get(obj, "mode") == "payment" or (row is not None and row.product_code == "gol"):
            return _apply_gol_checkout(obj, event_id, require_paid=True)
        subscription_id = _stripe_id(_get(obj, "subscription"))
        if row is not None:
            db.session.execute(select(UserAccount.id).where(UserAccount.id == row.purchaser_user_id).with_for_update())
            row.status = "complete"
            row.completed_at = utcnow()
            _expire_other_open_checkouts(row, subscription_id)
        if subscription_id:
            snapshot = _retrieve_subscription(subscription_id)
            upsert_subscription(
                snapshot,
                event_created=_retrieve_event_watermark(subscription_id, event_created),
            )
        return True
    if event_type == "checkout.session.async_payment_succeeded":
        return _apply_gol_checkout(obj, event_id, require_paid=False)
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
        snapshot = obj
        watermark = event_created
        if previous is not None and event_created is not None and previous.last_event_created == event_created:
            snapshot = _retrieve_subscription(subscription_id)
            watermark = _retrieve_event_watermark(subscription_id, event_created)
        upsert_subscription(snapshot, event_created=watermark, retrieve_on_stale=True)
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
    if event_type == "charge.refunded":
        payment_intent_id = _stripe_id(_get(obj, "payment_intent"))
        if not payment_intent_id:
            return False
        settlement = _lock_gol_settlement(payment_intent_id)
        settlement.refund_target_cents = max(settlement.refund_target_cents, int(_get(obj, "amount_refunded") or 0))
        settlement.last_refund_event_id = event_id
        candidate = GolCreditLedger.query.filter_by(stripe_payment_intent_id=payment_intent_id, kind="grant").first()
        if candidate is not None:
            db.session.execute(
                select(UserAccount.id).where(UserAccount.id == candidate.user_account_id).with_for_update()
            )
            # Re-read after locking: account deletion may have removed the grant while we waited.
            grant = db.session.get(GolCreditLedger, candidate.id, populate_existing=True)
            if grant is not None:
                _settle_gol_refund(settlement, grant)
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
    row = (
        db.session.execute(
            select(StripeWebhookEvent)
            .where(StripeWebhookEvent.event_id == event_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        .scalars()
        .one_or_none()
    )
    if row is None:
        row = StripeWebhookEvent(event_id=event_id, received_at=utcnow())
        db.session.add(row)
    elif row.status in {"processed", "ignored"}:
        logger.info("Stripe webhook event %s was already %s; preserving terminal status", event_id, row.status)
        db.session.commit()
        return
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

    claim_existing = existing is not None
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
            claim_existing = True

    if claim_existing:
        existing = (
            db.session.execute(
                select(StripeWebhookEvent)
                .where(StripeWebhookEvent.event_id == event_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            .scalars()
            .one_or_none()
        )
        if existing is None:
            raise RuntimeError("Stripe webhook event disappeared while claiming retry")
        if existing.status != "failed":
            return {"received": True, "duplicate": True}, 200

    intents: list[dict] = []
    token = _email_intents.set(intents)
    try:
        obj = _get(_get(event, "data", {}), "object", {})
        applied = _apply_event(
            event_type,
            obj,
            int(event_created) if event_created is not None else None,
            event_id,
        )
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
    mrr_by_currency: dict[str, int] = {}
    active_currencies: set[str | None] = set()
    for row in active_rows:
        by_product[row.product_code] = by_product.get(row.product_code, 0) + 1
        currency = row.currency.lower() if row.currency else None
        active_currencies.add(currency)
        if currency is None:
            continue
        mrr_by_currency.setdefault(currency, 0)
        if row.unit_amount is not None and row.interval == "month":
            mrr_by_currency[currency] += row.unit_amount
        elif row.unit_amount is not None and row.interval == "year":
            mrr_by_currency[currency] += round(row.unit_amount / 12)
    known_currencies = {currency for currency in active_currencies if currency}
    if not known_currencies:
        mrr_cents = 0
        currency = "usd"
    elif len(known_currencies) > 1:
        mrr_cents = None
        currency = None
    else:
        single_currency = next(iter(known_currencies))
        mrr_cents = mrr_by_currency[single_currency]
        currency = single_currency
    gross_cents, refunded_cents = (
        db.session.query(
            func.coalesce(func.sum(GolCreditLedger.amount_paid_cents), 0),
            func.coalesce(func.sum(GolCreditLedger.refunded_cents), 0),
        )
        .filter(
            GolCreditLedger.kind == "grant",
            GolCreditLedger.bucket == "prepaid",
            GolCreditLedger.currency == "usd",
        )
        .one()
    )
    grant_rows = GolCreditLedger.query.filter_by(kind="grant", bucket="prepaid")
    credits_granted = (
        db.session.query(func.coalesce(func.sum(GolCreditLedger.delta), 0))
        .filter(
            GolCreditLedger.kind == "grant",
            GolCreditLedger.bucket == "prepaid",
        )
        .scalar()
    )
    other_currency_grants = grant_rows.filter(GolCreditLedger.currency != "usd").count()
    credits_reversed = -int(
        db.session.query(func.coalesce(func.sum(GolCreditLedger.delta), 0))
        .filter(
            GolCreditLedger.kind == "reversal",
            GolCreditLedger.bucket == "prepaid",
            GolCreditLedger.debit_id.is_(None),
        )
        .scalar()
    )
    prepaid_debits = int(
        db.session.query(func.coalesce(func.sum(GolCreditLedger.delta), 0))
        .filter(GolCreditLedger.kind == "debit", GolCreditLedger.bucket == "prepaid")
        .scalar()
    )
    question_reversals = int(
        db.session.query(func.coalesce(func.sum(GolCreditLedger.delta), 0))
        .filter(
            GolCreditLedger.kind == "reversal",
            GolCreditLedger.bucket == "prepaid",
            GolCreditLedger.debit_id.is_not(None),
        )
        .scalar()
    )
    credits_outstanding = int(
        db.session.query(func.coalesce(func.sum(GolCreditLedger.delta), 0))
        .filter(GolCreditLedger.bucket == "prepaid")
        .scalar()
    )
    negative_balances = (
        db.session.query(GolCreditLedger.user_account_id)
        .filter(GolCreditLedger.bucket == "prepaid")
        .group_by(GolCreditLedger.user_account_id)
        .having(func.sum(GolCreditLedger.delta) < 0)
        .count()
    )
    return {
        "active_subscriptions": len(active_rows),
        "by_product": by_product,
        "mrr_by_currency": mrr_by_currency,
        "mrr_cents": mrr_cents,
        "currency": currency,
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
        "gol": {
            "gross_cents": int(gross_cents),
            "refunded_cents": int(refunded_cents),
            "currency": "usd",
            "other_currency_grants": other_currency_grants,
            "credits_granted": int(credits_granted),
            "credits_reversed": credits_reversed,
            "credits_spent": -prepaid_debits + question_reversals,
            "credits_outstanding": credits_outstanding,
            "negative_balances": negative_balances,
        },
    }


def cancel_subscriptions_for_account_deletion(user) -> int:
    rows = BillingSubscription.query.filter(
        BillingSubscription.scope_type == "user",
        BillingSubscription.scope_id == user.id,
        BillingSubscription.status.notin_(TERMINAL_STATUSES),
    ).all()
    checkout_rows = BillingCheckoutSession.query.filter(
        BillingCheckoutSession.status == "open",
        or_(
            BillingCheckoutSession.purchaser_user_id == user.id,
            (BillingCheckoutSession.scope_type == "user") & (BillingCheckoutSession.scope_id == user.id),
        ),
    ).all()
    now = utcnow()
    payable_checkout_rows = []
    for checkout in checkout_rows:
        if not checkout.stripe_session_id:
            checkout.status = "expired"
        elif checkout.product_code == "gol":
            # Payment-mode Sessions need a remote preflight even after their
            # local expiry: a completed payment may still be awaiting webhook delivery.
            payable_checkout_rows.append(checkout)
        elif checkout.expires_at is not None and checkout.expires_at <= now:
            checkout.status = "expired"
        else:
            payable_checkout_rows.append(checkout)
    if not rows and not payable_checkout_rows:
        return 0
    if not (os.getenv("STRIPE_SECRET_KEY") or "").strip():
        raise BillingError("billing_cancel_failed", 503)
    configure_stripe()
    canceled_subscription_ids = set()
    try:
        for row in rows:
            _cancel_duplicate_subscription(row.stripe_subscription_id)
            canceled_subscription_ids.add(row.stripe_subscription_id)
        for checkout in payable_checkout_rows:
            try:
                snapshot = _expire_or_retrieve_checkout(checkout)
            except stripe.InvalidRequestError:
                checkout.status = "expired"
                continue
            status = _get(snapshot, "status")
            if status == "expired":
                checkout.status = "expired"
                continue
            if status == "complete":
                if checkout.product_code == "gol":
                    checkout.status = "complete"
                    checkout.completed_at = checkout.completed_at or utcnow()
                    if _get(snapshot, "payment_status") == "paid":
                        logger.info(
                            "Forfeiting completed GOL Checkout Session %s during account deletion before webhook grant",
                            checkout.stripe_session_id,
                        )
                    continue
                subscription_id = _stripe_id(_get(snapshot, "subscription"))
                if subscription_id and subscription_id not in canceled_subscription_ids:
                    stripe.Subscription.cancel(subscription_id)
                    canceled_subscription_ids.add(subscription_id)
                checkout.status = "complete"
                checkout.completed_at = checkout.completed_at or utcnow()
                continue
            raise BillingError("billing_cancel_failed", 503)
    except BillingError:
        raise
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
