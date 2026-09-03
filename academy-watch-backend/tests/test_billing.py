"""S3-P0 Stripe billing foundation contract tests."""

import json
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import stripe
from flask import Flask
from src.auth import issue_user_token
from src.extensions import limiter
from src.models.billing import BillingCheckoutSession, BillingCustomer, BillingSubscription, StripeWebhookEvent
from src.models.league import UserAccount, db
from src.routes.events import ALLOWED_EVENTS

WEBHOOK_SECRET = "billing_webhook_test_placeholder"


@pytest.fixture
def billing_app(monkeypatch):
    from src.routes.account import account_bp
    from src.routes.billing import _price_cache, billing_bp

    for name in (
        "BILLING_ENABLED",
        "STRIPE_SECRET_KEY",
        "STRIPE_WEBHOOK_SECRET",
        "STRIPE_PRICE_SCOUT_PRO_MONTHLY",
        "STRIPE_PRICE_SCOUT_PRO_YEARLY",
        "STRIPE_PRICE_CLUB_BUNDLE_MONTHLY",
        "STRIPE_PRICE_CLUB_BUNDLE_YEARLY",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ADMIN_API_KEY", "billing-admin-key")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.com")
    _price_cache.clear()

    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SECRET_KEY="billing-fixture-secret",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        RATELIMIT_ENABLED=True,
    )
    db.init_app(app)
    limiter.init_app(app)
    app.register_blueprint(billing_bp, url_prefix="/api")
    app.register_blueprint(account_bp, url_prefix="/api")

    with app.app_context():
        limiter.reset()
        db.create_all()
        yield app
        limiter.reset()
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(billing_app):
    return billing_app.test_client()


def _add_user(email="scout@example.com", user_id=None):
    user = UserAccount(
        id=user_id,
        email=email,
        display_name="Test Scout",
        display_name_lower=email,
        display_name_confirmed=True,
        scout_tier="free",
    )
    db.session.add(user)
    db.session.commit()
    return user


def _headers(user):
    return {"Authorization": f"Bearer {issue_user_token(user.email)['token']}"}


def _admin_headers():
    token = issue_user_token("admin@example.com", role="admin")["token"]
    return {"Authorization": f"Bearer {token}", "X-API-Key": "billing-admin-key"}


def _subscription(
    user,
    *,
    subscription_id="sub_test_one",
    status="active",
    price_id="price_test_monthly",
    price_code="monthly",
    event_end=None,
):
    now = int(time.time())
    return {
        "id": subscription_id,
        "customer": f"cus_{user.id}",
        "status": status,
        "metadata": {
            "scope_type": "user",
            "scope_id": str(user.id),
            "product_code": "scout_pro",
            "price_code": price_code,
            "purchaser_user_id": str(user.id),
        },
        "items": {
            "data": [
                {
                    "price": {
                        "id": price_id,
                        "unit_amount": 900 if price_code == "monthly" else 9600,
                        "currency": "usd",
                        "recurring": {"interval": "month" if price_code == "monthly" else "year"},
                    },
                    "current_period_start": now - 60,
                    "current_period_end": event_end or now + 3600,
                }
            ]
        },
        "cancel_at_period_end": False,
        "canceled_at": now if status == "canceled" else None,
    }


def _event(event_id, event_type, obj, created=None):
    return {
        "id": event_id,
        "object": "event",
        "type": event_type,
        "created": created or int(time.time()),
        "data": {"object": obj},
    }


def _signed(event):
    raw = json.dumps(event, separators=(",", ":")).encode()
    timestamp = int(time.time())
    signed_payload = f"{timestamp}.{raw.decode()}"
    signature = stripe.WebhookSignature._compute_signature(signed_payload, WEBHOOK_SECRET)
    return raw, f"t={timestamp},v1={signature}"


def _post_event(client, event):
    raw, signature = _signed(event)
    return client.post(
        "/api/billing/stripe/webhook",
        data=raw,
        headers={"Stripe-Signature": signature, "Content-Type": "application/json"},
    )


def _enable(monkeypatch):
    monkeypatch.setenv("BILLING_ENABLED", "true")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", WEBHOOK_SECRET)


def _mock_checkout(monkeypatch):
    customer_create = Mock(return_value={"id": "cus_checkout"})
    session_create = Mock()

    def make_session(**kwargs):
        number = session_create.call_count
        return {
            "id": f"cs_test_{number}",
            "url": f"https://checkout.example/{number}",
            "expires_at": int(time.time()) + 3600,
        }

    session_create.side_effect = make_session
    monkeypatch.setattr(stripe.Customer, "create", customer_create)
    monkeypatch.setattr(stripe.checkout.Session, "create", session_create)
    return customer_create, session_create


def test_stripe_configuration_is_resolved_at_call_time(monkeypatch):
    from src.config.stripe_config import (
        billing_enabled,
        configure_stripe,
        offered_products,
        product_for_price_id,
        resolve_price,
    )

    monkeypatch.setattr(stripe, "api_key", None)
    monkeypatch.delenv("BILLING_ENABLED", raising=False)
    monkeypatch.delenv("STRIPE_PRICE_SCOUT_PRO_MONTHLY", raising=False)
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    assert billing_enabled() is False
    assert offered_products() == {}
    assert resolve_price("scout_pro", "monthly") is None

    monkeypatch.setenv("BILLING_ENABLED", "YES")
    monkeypatch.setenv("STRIPE_PRICE_SCOUT_PRO_MONTHLY", "price_runtime")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "billing_runtime_key")
    assert billing_enabled() is True
    assert resolve_price("scout_pro", "monthly") == "price_runtime"
    assert product_for_price_id("price_runtime") == ("scout_pro", "monthly")
    configure_stripe()
    assert stripe.api_key == "billing_runtime_key"


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/api/billing/stripe/webhook"),
        ("get", "/api/billing/config"),
        ("get", "/api/billing/me"),
        ("post", "/api/billing/checkout"),
        ("post", "/api/billing/portal"),
        ("get", "/api/admin/billing/summary"),
        ("options", "/api/billing/checkout"),
        ("get", "/api/billing/checkout"),
        ("options", "/api/admin/billing/summary"),
        ("post", "/api/admin/billing/summary"),
    ],
)
def test_billing_routes_are_dark_by_default(client, method, path):
    assert getattr(client, method)(path).status_code == 404


def test_bad_or_missing_signature_writes_no_event(client, monkeypatch):
    monkeypatch.setenv("BILLING_ENABLED", "true")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", WEBHOOK_SECRET)
    response = client.post(
        "/api/billing/stripe/webhook",
        data=b"{}",
        headers={"Stripe-Signature": "t=1,v1=bad"},
    )
    assert response.status_code == 400
    assert response.get_json() == {"error": "invalid_signature"}
    assert StripeWebhookEvent.query.count() == 0

    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET")
    response = client.post("/api/billing/stripe/webhook", data=b"{}")
    assert response.status_code == 400
    assert StripeWebhookEvent.query.count() == 0


def test_subscription_lifecycle_replay_ordering_and_email_after_commit(client, monkeypatch):
    _enable(monkeypatch)
    user = _add_user()
    sent = []

    def send_email(**kwargs):
        assert StripeWebhookEvent.query.filter_by(status="processed").count() >= 1
        sent.append(kwargs)
        return SimpleNamespace(success=True)

    from src.services.email_service import email_service

    monkeypatch.setattr(email_service, "send_email", send_email)
    active = _subscription(user, status="active")
    created = _event("evt_created", "customer.subscription.created", active, created=200)

    response = _post_event(client, created)
    assert response.status_code == 200
    assert response.get_json() == {"received": True, "duplicate": False}
    row = BillingSubscription.query.one()
    assert row.status == "active"
    assert db.session.get(UserAccount, user.id).scout_tier == "pro"
    assert StripeWebhookEvent.query.filter_by(status="processed").count() == 1
    assert len(sent) == 1

    response = _post_event(client, created)
    assert response.get_json() == {"received": True, "duplicate": True}
    assert BillingSubscription.query.count() == 1
    assert StripeWebhookEvent.query.count() == 1
    assert len(sent) == 1

    older = _subscription(user, status="canceled")
    response = _post_event(
        client,
        _event("evt_old", "customer.subscription.updated", older, created=100),
    )
    assert response.status_code == 200
    assert BillingSubscription.query.one().status == "active"
    assert db.session.get(UserAccount, user.id).scout_tier == "pro"

    deleted = _subscription(user, status="canceled")
    response = _post_event(
        client,
        _event("evt_deleted", "customer.subscription.deleted", deleted, created=300),
    )
    assert response.status_code == 200
    assert BillingSubscription.query.one().status == "canceled"
    assert db.session.get(UserAccount, user.id).scout_tier == "free"
    assert len(sent) == 2
    assert sent[-1]["subject"] == "Your Scout Pro subscription has ended"


def test_failed_webhook_is_persisted_then_retried(client, monkeypatch):
    _enable(monkeypatch)
    user = _add_user()
    import src.services.stripe_billing as billing_service

    original = billing_service.upsert_subscription
    monkeypatch.setattr(billing_service, "upsert_subscription", Mock(side_effect=RuntimeError("apply broke")))
    event = _event("evt_retry", "customer.subscription.created", _subscription(user))
    response = _post_event(client, event)
    assert response.status_code == 500
    failed = StripeWebhookEvent.query.one()
    assert failed.status == "failed"
    assert "apply broke" in failed.error

    monkeypatch.setattr(billing_service, "upsert_subscription", original)
    response = _post_event(client, event)
    assert response.status_code == 200
    assert response.get_json()["duplicate"] is False
    assert StripeWebhookEvent.query.one().status == "processed"
    assert BillingSubscription.query.one().status == "active"


def test_checkout_idempotency_validation_and_active_conflict(client, monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setenv("STRIPE_PRICE_SCOUT_PRO_MONTHLY", "price_monthly")
    monkeypatch.setenv("STRIPE_PRICE_CLUB_BUNDLE_MONTHLY", "price_club")
    user = _add_user()
    headers = _headers(user)
    _, session_create = _mock_checkout(monkeypatch)
    payload = {"product_code": "scout_pro", "price_code": "monthly", "client_key": "client_key_1"}

    first = client.post("/api/billing/checkout", json=payload, headers=headers)
    assert first.status_code == 200
    assert BillingCheckoutSession.query.count() == 1
    second = client.post("/api/billing/checkout", json=payload, headers=headers)
    assert second.get_json() == first.get_json()
    assert session_create.call_count == 1

    payload["client_key"] = "client_key_2"
    assert client.post("/api/billing/checkout", json=payload, headers=headers).status_code == 200
    assert session_create.call_count == 2

    club = {"product_code": "club_bundle", "price_code": "monthly", "client_key": "client_key_3"}
    assert client.post("/api/billing/checkout", json=club, headers=headers).get_json() == {
        "error": "product_not_available"
    }
    bad_key = {"product_code": "scout_pro", "price_code": "monthly", "client_key": "short"}
    assert client.post("/api/billing/checkout", json=bad_key, headers=headers).get_json() == {
        "error": "invalid_client_key"
    }
    assert client.post("/api/billing/checkout", json=[], headers=headers).get_json() == {"error": "invalid_json"}

    monkeypatch.delenv("STRIPE_PRICE_SCOUT_PRO_MONTHLY")
    unknown = client.post("/api/billing/checkout", json=payload, headers=headers)
    assert unknown.status_code == 400
    assert unknown.get_json() == {"error": "unknown_product"}

    monkeypatch.setenv("STRIPE_PRICE_SCOUT_PRO_MONTHLY", "price_monthly")
    db.session.add(
        BillingSubscription(
            scope_type="user",
            scope_id=user.id,
            product_code="scout_pro",
            price_code="monthly",
            purchaser_user_id=user.id,
            stripe_customer_id="cus_checkout",
            stripe_subscription_id="sub_active",
            stripe_price_id="price_monthly",
            status="active",
        )
    )
    db.session.commit()
    payload["client_key"] = "client_key_4"
    response = client.post("/api/billing/checkout", json=payload, headers=headers)
    assert response.status_code == 409
    assert response.get_json() == {"error": "already_subscribed"}


def test_expired_checkout_can_be_recreated_with_same_client_key(client, monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setenv("STRIPE_PRICE_SCOUT_PRO_MONTHLY", "price_monthly")
    user = _add_user()
    headers = _headers(user)
    _, session_create = _mock_checkout(monkeypatch)
    payload = {"product_code": "scout_pro", "price_code": "monthly", "client_key": "same_client_key"}
    first = client.post("/api/billing/checkout", json=payload, headers=headers).get_json()

    expired_event = _event(
        "evt_expired",
        "checkout.session.expired",
        {"id": first["session_id"], "client_reference_id": str(BillingCheckoutSession.query.one().id)},
    )
    assert _post_event(client, expired_event).status_code == 200
    assert BillingCheckoutSession.query.one().status == "expired"
    second = client.post("/api/billing/checkout", json=payload, headers=headers)
    assert second.status_code == 200
    assert second.get_json()["session_id"] != first["session_id"]
    assert session_create.call_count == 2
    assert BillingCheckoutSession.query.count() == 1


def test_config_price_lookup_failure_omits_money(client, monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setenv("STRIPE_PRICE_SCOUT_PRO_MONTHLY", "price_good")
    monkeypatch.setenv("STRIPE_PRICE_SCOUT_PRO_YEARLY", "price_bad")

    def retrieve(price_id):
        if price_id == "price_bad":
            raise RuntimeError("lookup unavailable")
        return {"unit_amount": 900, "currency": "USD"}

    monkeypatch.setattr(stripe.Price, "retrieve", retrieve)
    response = client.get("/api/billing/config")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    prices = response.get_json()["products"][0]["prices"]
    assert prices[0] == {"price_code": "monthly", "interval": "month", "unit_amount": 900, "currency": "usd"}
    assert prices[1] == {"price_code": "yearly", "interval": "year"}


def test_billing_me_and_portal(client, monkeypatch):
    _enable(monkeypatch)
    user = _add_user()
    headers = _headers(user)
    response = client.get("/api/billing/me", headers=headers)
    assert response.get_json() == {"enabled": True, "has_billing_account": False, "subscriptions": []}
    response = client.post("/api/billing/portal", headers=headers)
    assert response.status_code == 409
    assert response.get_json() == {"error": "no_billing_account"}

    db.session.add(BillingCustomer(user_account_id=user.id, stripe_customer_id="cus_portal"))
    db.session.add(
        BillingSubscription(
            scope_type="user",
            scope_id=user.id,
            product_code="scout_pro",
            price_code="monthly",
            purchaser_user_id=user.id,
            stripe_customer_id="cus_portal",
            stripe_subscription_id="sub_portal",
            stripe_price_id="price_portal",
            status="active",
            unit_amount=900,
            currency="usd",
            interval="month",
            current_period_end=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=30),
        )
    )
    db.session.commit()
    portal = Mock(return_value={"url": "https://billing.example/portal"})
    monkeypatch.setattr(stripe.billing_portal.Session, "create", portal)
    response = client.post("/api/billing/portal", headers=headers)
    assert response.get_json() == {"portal_url": "https://billing.example/portal"}
    portal.assert_called_once_with(customer="cus_portal", return_url="https://example.com/account/billing")

    payload = client.get("/api/billing/me", headers=headers).get_json()
    assert payload["has_billing_account"] is True
    assert payload["subscriptions"][0]["is_active"] is True
    assert payload["subscriptions"][0]["unit_amount"] == 900


def test_admin_summary_mrr_and_auth(client, monkeypatch):
    _enable(monkeypatch)
    one = _add_user("one@example.com", 101)
    two = _add_user("two@example.com", 102)
    now = datetime.now(UTC).replace(tzinfo=None)
    for user, interval, amount, suffix in ((one, "month", 900, "m"), (two, "year", 9600, "y")):
        db.session.add(
            BillingSubscription(
                scope_type="user",
                scope_id=user.id,
                product_code="scout_pro",
                price_code="monthly" if interval == "month" else "yearly",
                purchaser_user_id=user.id,
                stripe_customer_id=f"cus_{suffix}",
                stripe_subscription_id=f"sub_{suffix}",
                stripe_price_id=f"price_{suffix}",
                status="active",
                unit_amount=amount,
                currency="usd",
                interval=interval,
                current_period_end=now + timedelta(days=30),
            )
        )
    db.session.add(
        BillingCheckoutSession(
            scope_type="user",
            scope_id=one.id,
            product_code="scout_pro",
            price_code="monthly",
            purchaser_user_id=one.id,
            client_key="summary_key",
            status="open",
            expires_at=now + timedelta(hours=1),
        )
    )
    db.session.commit()
    assert client.get("/api/admin/billing/summary").status_code == 401
    response = client.get("/api/admin/billing/summary", headers=_admin_headers())
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["active_subscriptions"] == 2
    assert payload["by_product"] == {"scout_pro": 2}
    assert payload["mrr_cents"] == 1700
    assert payload["checkout_sessions_open"] == 1


def test_account_delete_cancels_active_subscription_and_exports_billing(client, monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "billing_secret_test_placeholder")
    user = _add_user()
    db.session.add(BillingCustomer(user_account_id=user.id, stripe_customer_id="cus_delete"))
    db.session.add(
        BillingSubscription(
            scope_type="user",
            scope_id=user.id,
            product_code="scout_pro",
            price_code="monthly",
            purchaser_user_id=user.id,
            stripe_customer_id="cus_delete",
            stripe_subscription_id="sub_delete",
            stripe_price_id="price_delete",
            status="active",
        )
    )
    db.session.commit()
    headers = _headers(user)
    exported = client.get("/api/account/export", headers=headers).get_json()
    assert exported["billing"]["has_billing_account"] is True
    assert exported["billing"]["subscriptions"][0]["product_code"] == "scout_pro"

    cancel = Mock(return_value={"id": "sub_delete", "status": "canceled"})
    monkeypatch.setattr(stripe.Subscription, "cancel", cancel)
    response = client.post("/api/account/delete", json={"confirm": "DELETE"}, headers=headers)
    assert response.status_code == 200
    cancel.assert_called_once_with("sub_delete")
    assert response.get_json()["counts"]["deleted"]["billing_subscriptions"] == 1
    assert db.session.get(UserAccount, user.id) is None


def test_account_delete_aborts_when_stripe_cancel_fails(client, monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "billing_secret_test_placeholder")
    user = _add_user()
    db.session.add(
        BillingSubscription(
            scope_type="user",
            scope_id=user.id,
            product_code="scout_pro",
            price_code="monthly",
            purchaser_user_id=user.id,
            stripe_customer_id="cus_delete_fail",
            stripe_subscription_id="sub_delete_fail",
            stripe_price_id="price_delete_fail",
            status="active",
        )
    )
    db.session.commit()
    monkeypatch.setattr(stripe.Subscription, "cancel", Mock(side_effect=RuntimeError("Stripe unavailable")))
    response = client.post("/api/account/delete", json={"confirm": "DELETE"}, headers=_headers(user))
    assert response.status_code == 503
    assert response.get_json() == {"error": "billing_cancel_failed"}
    assert db.session.get(UserAccount, user.id) is not None


def test_client_event_allowlist_has_only_public_billing_events():
    assert "checkout_started" in ALLOWED_EVENTS
    assert "checkout_completed" in ALLOWED_EVENTS
    assert "billing_checkout_started" not in ALLOWED_EVENTS
