"""S3-P0 Stripe billing foundation contract tests."""

import json
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import stripe
from flask import Flask
from sqlalchemy import event
from src.auth import issue_user_token
from src.extensions import limiter
from src.models.billing import BillingCheckoutSession, BillingCustomer, BillingSubscription, StripeWebhookEvent
from src.models.league import UserAccount, db
from src.models.product_event import ProductEvent
from src.routes.events import ALLOWED_EVENTS

WEBHOOK_SECRET = "billing_webhook_test_placeholder"


@pytest.fixture
def billing_app(monkeypatch):
    from src.routes.account import account_bp
    from src.routes.billing import _price_cache, billing_bp
    from src.routes.scout import scout_bp

    for name in (
        "BILLING_ENABLED",
        "STRIPE_SECRET_KEY",
        "STRIPE_WEBHOOK_SECRET",
        "STRIPE_PRICE_SCOUT_PRO_MONTHLY",
        "STRIPE_PRICE_SCOUT_PRO_YEARLY",
        "STRIPE_PRICE_CLUB_BUNDLE_MONTHLY",
        "STRIPE_PRICE_CLUB_BUNDLE_YEARLY",
        "STRIPE_PRICE_GOL_STARTER",
        "STRIPE_PRICE_GOL_TOPUP",
        "GOL_STARTER_CREDITS",
        "GOL_TOPUP_CREDITS",
        "GOL_FREE_ALLOWANCE",
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
    app.register_blueprint(scout_bp, url_prefix="/api")
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


def _add_checkout(user, session_id, client_key, *, expires_at=None):
    row = BillingCheckoutSession(
        scope_type="user",
        scope_id=user.id,
        product_code="scout_pro",
        price_code="monthly",
        purchaser_user_id=user.id,
        client_key=client_key,
        stripe_session_id=session_id,
        checkout_url=f"https://checkout.example/{client_key}",
        status="open",
        expires_at=expires_at or datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1),
    )
    db.session.add(row)
    return row


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
        ("options", "/api/scout/entitlements"),
        ("post", "/api/scout/entitlements"),
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


def test_signed_non_object_webhook_body_is_rejected_without_a_write(client, monkeypatch):
    _enable(monkeypatch)
    raw, signature = _signed([])
    response = client.post(
        "/api/billing/stripe/webhook",
        data=raw,
        headers={"Stripe-Signature": signature, "Content-Type": "application/json"},
    )
    assert response.status_code == 400
    assert response.get_json() == {"error": "invalid_signature"}
    assert StripeWebhookEvent.query.count() == 0


def test_subscription_lifecycle_replay_ordering_and_email_after_commit(client, monkeypatch):
    _enable(monkeypatch)
    user = _add_user()
    sent = []
    real_commit = db.session.commit
    commit_count = 0
    enforce_first_send_order = True

    def counted_commit():
        nonlocal commit_count
        commit_count += 1
        return real_commit()

    def send_email(**kwargs):
        if enforce_first_send_order:
            assert commit_count == 1
        sent.append(kwargs)
        return SimpleNamespace(success=True)

    from src.services.email_service import email_service

    monkeypatch.setattr(email_service, "send_email", send_email)
    monkeypatch.setattr(db.session, "commit", counted_commit)
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
    assert commit_count == 1
    enforce_first_send_order = False
    monkeypatch.setattr(db.session, "commit", real_commit)

    response = _post_event(client, created)
    assert response.get_json() == {"received": True, "duplicate": True}
    assert BillingSubscription.query.count() == 1
    assert StripeWebhookEvent.query.count() == 1
    assert len(sent) == 1

    older = _subscription(user, status="canceled")
    authoritative_active = _subscription(user, status="active")
    deleted = _subscription(user, status="canceled")
    retrieve = Mock(side_effect=[authoritative_active, deleted])
    monkeypatch.setattr(stripe.Subscription, "retrieve", retrieve)
    response = _post_event(
        client,
        _event("evt_old", "customer.subscription.updated", older, created=100),
    )
    assert response.status_code == 200
    assert BillingSubscription.query.one().status == "active"
    assert db.session.get(UserAccount, user.id).scout_tier == "pro"

    response = _post_event(
        client,
        _event("evt_deleted", "customer.subscription.deleted", deleted, created=300),
    )
    assert response.status_code == 200
    assert BillingSubscription.query.one().status == "canceled"
    assert db.session.get(UserAccount, user.id).scout_tier == "free"
    assert len(sent) == 2
    assert sent[-1]["subject"] == "Your Scout Pro subscription has ended"
    assert retrieve.call_count == 2


def test_late_webhook_after_account_deletion_with_fk_enforcement(client, monkeypatch):
    engine = db.engine

    def enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    event.listen(engine, "connect", enable_sqlite_foreign_keys)
    raw_connection = engine.raw_connection()
    try:
        enable_sqlite_foreign_keys(raw_connection.driver_connection, None)
    finally:
        raw_connection.close()

    try:
        _enable(monkeypatch)
        monkeypatch.setenv("STRIPE_SECRET_KEY", "billing_secret_test_placeholder")
        user = _add_user("late-webhook@example.com")
        user_id = user.id
        deleted = _subscription(user, subscription_id="sub_late_delete", status="canceled")
        db.session.add(
            BillingSubscription(
                scope_type="user",
                scope_id=user.id,
                product_code="scout_pro",
                price_code="monthly",
                purchaser_user_id=user.id,
                stripe_customer_id=f"cus_{user.id}",
                stripe_subscription_id="sub_late_delete",
                stripe_price_id="price_test_monthly",
                status="active",
            )
        )
        db.session.commit()
        cancel = Mock(return_value={"id": "sub_late_delete", "status": "canceled"})
        monkeypatch.setattr(stripe.Subscription, "cancel", cancel)

        response = client.post("/api/account/delete", json={"confirm": "DELETE"}, headers=_headers(user))
        assert response.status_code == 200
        assert db.session.get(UserAccount, user_id) is None
        assert BillingSubscription.query.count() == 0

        response = _post_event(
            client,
            _event("evt_late_delete", "customer.subscription.deleted", deleted, created=300),
        )

        assert response.status_code == 200
        assert response.get_json() == {"received": True, "duplicate": False}
        assert BillingSubscription.query.count() == 0
        assert StripeWebhookEvent.query.filter_by(event_id="evt_late_delete", status="processed").count() == 1
    finally:
        event.remove(engine, "connect", enable_sqlite_foreign_keys)


def test_existing_subscription_clears_a_missing_purchaser(client):
    user = _add_user("deleted-purchaser@example.com")
    user_id = user.id
    row = BillingSubscription(
        scope_type="user",
        scope_id=user_id,
        product_code="scout_pro",
        price_code="monthly",
        purchaser_user_id=user_id,
        stripe_customer_id=f"cus_{user_id}",
        stripe_subscription_id="sub_missing_purchaser",
        stripe_price_id="price_test_monthly",
        status="active",
    )
    db.session.add(row)
    db.session.commit()
    db.session.execute(UserAccount.__table__.delete().where(UserAccount.id == user_id))
    db.session.commit()
    db.session.expire_all()
    from src.services.stripe_billing import upsert_subscription

    updated = _subscription(
        SimpleNamespace(id=user_id),
        subscription_id="sub_missing_purchaser",
        status="active",
    )
    upsert_subscription(updated, event_created=300)

    assert BillingSubscription.query.one().purchaser_user_id is None


def test_deleted_subscription_that_was_never_active_has_no_ended_notification(client, monkeypatch):
    _enable(monkeypatch)
    user = _add_user("incomplete@example.com")
    sent = []
    from src.services.email_service import email_service

    monkeypatch.setattr(
        email_service,
        "send_email",
        lambda **kwargs: sent.append(kwargs) or SimpleNamespace(success=True),
    )
    deleted = _subscription(user, subscription_id="sub_never_active", status="incomplete_expired")

    response = _post_event(
        client,
        _event("evt_never_active_deleted", "customer.subscription.deleted", deleted, created=300),
    )

    assert response.status_code == 200
    assert BillingSubscription.query.one().status == "incomplete_expired"
    assert ProductEvent.query.filter_by(event_name="billing_subscription_ended").count() == 0
    assert sent == []


def test_unknown_deleted_duplicate_is_silent_while_kept_subscription_is_active(client, monkeypatch):
    _enable(monkeypatch)
    user = _add_user()
    db.session.add(
        BillingSubscription(
            scope_type="user",
            scope_id=user.id,
            product_code="scout_pro",
            price_code="monthly",
            purchaser_user_id=user.id,
            stripe_customer_id=f"cus_{user.id}",
            stripe_subscription_id="sub_kept_active",
            stripe_price_id="price_test_monthly",
            status="active",
        )
    )
    db.session.commit()
    sent = []
    from src.services.email_service import email_service

    monkeypatch.setattr(
        email_service,
        "send_email",
        lambda **kwargs: sent.append(kwargs) or SimpleNamespace(success=True),
    )
    deleted = _subscription(user, subscription_id="sub_unknown_duplicate", status="canceled")

    response = _post_event(
        client,
        _event("evt_unknown_duplicate_deleted", "customer.subscription.deleted", deleted, created=300),
    )

    assert response.status_code == 200
    assert BillingSubscription.query.filter_by(stripe_subscription_id="sub_kept_active").one().status == "active"
    assert ProductEvent.query.filter_by(event_name="billing_subscription_ended").count() == 0
    assert sent == []


def test_known_ended_duplicate_is_silent_until_last_subscription_ends(client, monkeypatch):
    _enable(monkeypatch)
    user = _add_user()
    user.scout_tier = "pro"
    for subscription_id in ("sub_ending_duplicate", "sub_kept_duplicate"):
        db.session.add(
            BillingSubscription(
                scope_type="user",
                scope_id=user.id,
                product_code="scout_pro",
                price_code="monthly",
                purchaser_user_id=user.id,
                stripe_customer_id=f"cus_{user.id}",
                stripe_subscription_id=subscription_id,
                stripe_price_id="price_test_monthly",
                status="active",
                last_event_created=100,
            )
        )
    db.session.commit()
    sent = []
    from src.services.email_service import email_service

    monkeypatch.setattr(
        email_service,
        "send_email",
        lambda **kwargs: sent.append(kwargs) or SimpleNamespace(success=True),
    )

    first_ended = _subscription(user, subscription_id="sub_ending_duplicate", status="canceled")
    response = _post_event(
        client,
        _event("evt_known_duplicate_ended", "customer.subscription.updated", first_ended, created=200),
    )

    assert response.status_code == 200
    assert ProductEvent.query.filter_by(event_name="billing_subscription_ended").count() == 0
    assert sent == []
    assert db.session.get(UserAccount, user.id).scout_tier == "pro"

    last_ended = _subscription(user, subscription_id="sub_kept_duplicate", status="canceled")
    response = _post_event(
        client,
        _event("evt_last_subscription_ended", "customer.subscription.updated", last_ended, created=300),
    )

    assert response.status_code == 200
    assert ProductEvent.query.filter_by(event_name="billing_subscription_ended").count() == 1
    assert [message["subject"] for message in sent] == ["Your Scout Pro subscription has ended"]
    assert db.session.get(UserAccount, user.id).scout_tier == "free"


def test_upsert_subscription_locks_user_before_reload_and_rechecks_watermark(client):
    user = _add_user()
    import src.services.stripe_billing as billing_service

    persisted = BillingSubscription(
        scope_type="user",
        scope_id=user.id,
        product_code="scout_pro",
        price_code="monthly",
        purchaser_user_id=user.id,
        stripe_customer_id=f"cus_{user.id}",
        stripe_subscription_id="sub_user_lock",
        stripe_price_id="price_test_monthly",
        status="active",
        last_event_created=100,
    )
    user.scout_tier = "pro"
    db.session.add(persisted)
    db.session.commit()
    stale = db.session.get(BillingSubscription, persisted.id)
    db.session.execute(
        BillingSubscription.__table__.update()
        .where(BillingSubscription.id == persisted.id)
        .values(last_event_created=300)
    )
    stale.__dict__["last_event_created"] = 100
    older = _subscription(user, subscription_id="sub_user_lock", status="canceled")
    statements = []

    def capture_sql(_connection, _cursor, statement, _parameters, context, _executemany):
        compiled_statement = getattr(getattr(context, "compiled", None), "statement", None)
        has_for_update = getattr(compiled_statement, "_for_update_arg", None) is not None
        statements.append((" ".join(statement.split()), has_for_update))

    event.listen(db.engine, "before_cursor_execute", capture_sql)
    try:
        row = billing_service.upsert_subscription(older, event_created=200)
    finally:
        event.remove(db.engine, "before_cursor_execute", capture_sql)

    assert row.stripe_subscription_id == "sub_user_lock"
    user_select = next(
        index
        for index, (sql, has_for_update) in enumerate(statements)
        if "FROM user_accounts" in sql and has_for_update
    )
    subscription_selects = [
        (index, has_for_update)
        for index, (sql, has_for_update) in enumerate(statements)
        if sql.startswith("SELECT") and "FROM billing_subscriptions" in sql
    ]
    assert len(subscription_selects) == 2
    assert subscription_selects[-1][1] is True
    assert user_select < subscription_selects[-1][0]
    assert row.status == "active"
    assert row.last_event_created == 300
    assert db.session.get(UserAccount, user.id).scout_tier == "pro"


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


def test_failed_webhook_retry_rechecks_status_after_row_lock(client, monkeypatch):
    _enable(monkeypatch)
    event_id = "evt_failed_claim"
    db.session.add(
        StripeWebhookEvent(
            event_id=event_id,
            event_type="customer.subscription.updated",
            payload_hash="0" * 64,
            status="failed",
            received_at=datetime.now(UTC).replace(tzinfo=None),
        )
    )
    db.session.commit()
    import src.services.stripe_billing as billing_service

    apply_event = Mock(side_effect=AssertionError("duplicate retry must not apply"))
    monkeypatch.setattr(billing_service, "_apply_event", apply_event)
    real_execute = db.session.execute

    def process_after_claim(statement, *args, **kwargs):
        result = real_execute(statement, *args, **kwargs)
        if getattr(statement, "_for_update_arg", None) is not None and "stripe_webhook_events" in str(statement):
            locked = result.scalars().one_or_none()
            locked.status = "processed"
            return SimpleNamespace(scalars=lambda: SimpleNamespace(one_or_none=lambda: locked))
        return result

    monkeypatch.setattr(db.session, "execute", process_after_claim)
    response = _post_event(
        client,
        _event(event_id, "customer.subscription.updated", {"id": "sub_claim"}),
    )

    assert response.status_code == 200
    assert response.get_json() == {"received": True, "duplicate": True}
    apply_event.assert_not_called()


@pytest.mark.parametrize("terminal_status", ["processed", "ignored"])
def test_failed_event_record_preserves_concurrently_terminal_status(client, terminal_status):
    import src.services.stripe_billing as billing_service

    processed_at = datetime.now(UTC).replace(tzinfo=None)
    row = StripeWebhookEvent(
        event_id=f"evt_preserve_{terminal_status}",
        event_type="customer.subscription.updated",
        payload_hash="a" * 64,
        status=terminal_status,
        error=None,
        received_at=processed_at - timedelta(seconds=1),
        processed_at=processed_at,
    )
    db.session.add(row)
    db.session.commit()

    billing_service._record_failed_event(
        row.event_id,
        "invoice.payment_failed",
        "b" * 64,
        RuntimeError("late worker failure"),
    )

    db.session.expire_all()
    preserved = StripeWebhookEvent.query.one()
    assert preserved.status == terminal_status
    assert preserved.event_type == "customer.subscription.updated"
    assert preserved.payload_hash == "a" * 64
    assert preserved.error is None
    assert preserved.processed_at == processed_at


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
    different_key = client.post("/api/billing/checkout", json=payload, headers=headers)
    assert different_key.get_json() == first.get_json()
    assert session_create.call_count == 1
    assert BillingCheckoutSession.query.count() == 1

    club = {"product_code": "club_bundle", "price_code": "monthly", "client_key": "client_key_3"}
    assert client.post("/api/billing/checkout", json=club, headers=headers).get_json() == {
        "error": "product_not_available"
    }
    bad_key = {"product_code": "scout_pro", "price_code": "monthly", "client_key": "short"}
    assert client.post("/api/billing/checkout", json=bad_key, headers=headers).get_json() == {
        "error": "invalid_client_key"
    }
    assert client.post("/api/billing/checkout", json=[], headers=headers).get_json() == {"error": "invalid_json"}
    for field in ("product_code", "price_code"):
        typed_payload = {
            "product_code": "scout_pro",
            "price_code": "monthly",
            "client_key": f"typed_{field}",
        }
        typed_payload[field] = []
        response = client.post("/api/billing/checkout", json=typed_payload, headers=headers)
        assert response.status_code == 400
        assert response.get_json() == {"error": "unknown_product"}

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


def test_checkout_price_change_expires_open_session_and_creates_replacement(client, monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setenv("STRIPE_PRICE_SCOUT_PRO_MONTHLY", "price_monthly")
    monkeypatch.setenv("STRIPE_PRICE_SCOUT_PRO_YEARLY", "price_yearly")
    user = _add_user()
    headers = _headers(user)
    _, session_create = _mock_checkout(monkeypatch)
    monthly = client.post(
        "/api/billing/checkout",
        json={"product_code": "scout_pro", "price_code": "monthly", "client_key": "monthly_key"},
        headers=headers,
    )
    assert monthly.status_code == 200
    expire = Mock(side_effect=stripe.InvalidRequestError("Checkout Session is not open", param=None))
    retrieve = Mock(return_value={"id": "cs_test_1", "status": "expired"})
    monkeypatch.setattr(stripe.checkout.Session, "expire", expire)
    monkeypatch.setattr(stripe.checkout.Session, "retrieve", retrieve)

    yearly = client.post(
        "/api/billing/checkout",
        json={"product_code": "scout_pro", "price_code": "yearly", "client_key": "yearly_key"},
        headers=headers,
    )

    assert yearly.status_code == 200
    assert yearly.get_json()["session_id"] == "cs_test_2"
    expire.assert_called_once_with("cs_test_1")
    retrieve.assert_called_once_with("cs_test_1")
    assert session_create.call_count == 2
    assert session_create.call_args.kwargs["line_items"] == [{"price": "price_yearly", "quantity": 1}]
    assert BillingCheckoutSession.query.filter_by(price_code="monthly", status="expired").count() == 1
    assert BillingCheckoutSession.query.filter_by(price_code="yearly", status="open").count() == 1


def test_customer_unique_race_recovers_and_checkout_commits(client, monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setenv("STRIPE_PRICE_SCOUT_PRO_MONTHLY", "price_monthly")
    user = _add_user()
    headers = _headers(user)

    def create_competing_customer(**_kwargs):
        db.session.add(BillingCustomer(user_account_id=user.id, stripe_customer_id="cus_race_winner"))
        db.session.commit()
        return {"id": "cus_race_winner"}

    customer_create = Mock(side_effect=create_competing_customer)
    checkout_create = Mock(
        return_value={
            "id": "cs_customer_race",
            "url": "https://checkout.example/customer-race",
            "expires_at": int(time.time()) + 3600,
        }
    )
    monkeypatch.setattr(stripe.Customer, "create", customer_create)
    monkeypatch.setattr(stripe.checkout.Session, "create", checkout_create)

    response = client.post(
        "/api/billing/checkout",
        json={"product_code": "scout_pro", "price_code": "monthly", "client_key": "customer_race"},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "checkout_url": "https://checkout.example/customer-race",
        "session_id": "cs_customer_race",
    }
    customer_create.assert_called_once()
    checkout_create.assert_called_once()

    db.session.remove()
    assert BillingCustomer.query.count() == 1
    assert BillingCustomer.query.one().stripe_customer_id == "cus_race_winner"
    assert BillingCheckoutSession.query.count() == 1
    assert BillingCheckoutSession.query.one().stripe_session_id == "cs_customer_race"


def test_checkout_unique_race_returns_winner_without_second_stripe_call(client, monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setenv("STRIPE_PRICE_SCOUT_PRO_MONTHLY", "price_monthly")
    user = _add_user()
    headers = _headers(user)
    customer = BillingCustomer(user_account_id=user.id, stripe_customer_id="cus_race")
    db.session.add(customer)
    db.session.commit()

    import src.services.stripe_billing as billing_service

    def concurrent_winner(_user):
        db.session.add(
            BillingCheckoutSession(
                scope_type="user",
                scope_id=user.id,
                product_code="scout_pro",
                price_code="monthly",
                purchaser_user_id=user.id,
                client_key="checkout_race",
                stripe_session_id="cs_race_winner",
                checkout_url="https://checkout.example/winner",
                status="open",
                expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1),
            )
        )
        db.session.commit()
        return customer

    checkout_create = Mock(side_effect=AssertionError("loser must not call Stripe"))
    monkeypatch.setattr(billing_service, "ensure_customer", concurrent_winner)
    monkeypatch.setattr(stripe.checkout.Session, "create", checkout_create)
    response = client.post(
        "/api/billing/checkout",
        json={"product_code": "scout_pro", "price_code": "monthly", "client_key": "checkout_race"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.get_json() == {
        "checkout_url": "https://checkout.example/winner",
        "session_id": "cs_race_winner",
    }
    assert BillingCheckoutSession.query.count() == 1
    checkout_create.assert_not_called()


def test_checkout_completion_expires_open_sibling(client, monkeypatch):
    _enable(monkeypatch)
    user = _add_user()
    now = datetime.now(UTC).replace(tzinfo=None)
    completed = BillingCheckoutSession(
        scope_type="user",
        scope_id=user.id,
        product_code="scout_pro",
        price_code="monthly",
        purchaser_user_id=user.id,
        client_key="completed_checkout",
        stripe_session_id="cs_completed",
        checkout_url="https://checkout.example/completed",
        status="open",
        expires_at=now + timedelta(hours=1),
    )
    sibling = BillingCheckoutSession(
        scope_type="user",
        scope_id=user.id,
        product_code="scout_pro",
        price_code="yearly",
        purchaser_user_id=user.id,
        client_key="sibling_checkout",
        stripe_session_id="cs_sibling",
        checkout_url="https://checkout.example/sibling",
        status="open",
        expires_at=now + timedelta(hours=1),
    )
    db.session.add_all([completed, sibling])
    db.session.commit()
    call_order = []
    real_execute = db.session.execute

    def tracked_execute(statement, *args, **kwargs):
        if getattr(statement, "_for_update_arg", None) is not None:
            call_order.append("user_lock")
        return real_execute(statement, *args, **kwargs)

    def expire_sibling(_session_id):
        call_order.append("expire")
        return {"id": "cs_sibling", "status": "expired"}

    expire = Mock(side_effect=expire_sibling)
    monkeypatch.setattr(db.session, "execute", tracked_execute)
    monkeypatch.setattr(stripe.checkout.Session, "expire", expire)

    response = _post_event(
        client,
        _event(
            "evt_checkout_completed_sibling",
            "checkout.session.completed",
            {"id": "cs_completed"},
        ),
    )

    assert response.status_code == 200
    assert db.session.get(BillingCheckoutSession, completed.id).status == "complete"
    assert db.session.get(BillingCheckoutSession, sibling.id).status == "expired"
    expire.assert_called_once_with("cs_sibling")
    assert call_order == ["user_lock", "expire"]


def test_checkout_completion_locally_expires_sibling_without_stripe_session(client, monkeypatch):
    _enable(monkeypatch)
    user = _add_user()
    completed = _add_checkout(user, "cs_completed_local_only", "completed_local_only")
    sibling = _add_checkout(user, None, "sibling_local_only")
    db.session.commit()
    expire = Mock(side_effect=AssertionError("a local-only checkout has nothing to expire at Stripe"))
    monkeypatch.setattr(stripe.checkout.Session, "expire", expire)

    response = _post_event(
        client,
        _event(
            "evt_sibling_local_only",
            "checkout.session.completed",
            {"id": "cs_completed_local_only"},
        ),
    )

    assert response.status_code == 200
    assert db.session.get(BillingCheckoutSession, completed.id).status == "complete"
    assert db.session.get(BillingCheckoutSession, sibling.id).status == "expired"
    expire.assert_not_called()


@pytest.mark.parametrize(
    ("remote_status", "expected_status", "subscription_id"),
    [("expired", "expired", None), ("complete", "complete", "sub_duplicate")],
)
def test_checkout_completion_reconciles_closed_sibling(
    client,
    monkeypatch,
    remote_status,
    expected_status,
    subscription_id,
):
    _enable(monkeypatch)
    user = _add_user()
    completed = _add_checkout(user, "cs_completed_reconcile", "completed_reconcile")
    sibling = _add_checkout(user, "cs_sibling_reconcile", "sibling_reconcile")
    db.session.commit()
    not_open = stripe.InvalidRequestError("Checkout Session is not open", param=None)
    expire = Mock(side_effect=not_open)
    retrieve = Mock(
        return_value={
            "id": "cs_sibling_reconcile",
            "status": remote_status,
            "subscription": subscription_id,
        }
    )
    cancel = Mock(return_value={"id": subscription_id, "status": "canceled"})
    monkeypatch.setattr(stripe.checkout.Session, "expire", expire)
    monkeypatch.setattr(stripe.checkout.Session, "retrieve", retrieve)
    monkeypatch.setattr(stripe.Subscription, "cancel", cancel)

    response = _post_event(
        client,
        _event(
            f"evt_sibling_{remote_status}",
            "checkout.session.completed",
            {"id": "cs_completed_reconcile"},
        ),
    )

    assert response.status_code == 200
    assert db.session.get(BillingCheckoutSession, completed.id).status == "complete"
    assert db.session.get(BillingCheckoutSession, sibling.id).status == expected_status
    expire.assert_called_once_with("cs_sibling_reconcile")
    retrieve.assert_called_once_with("cs_sibling_reconcile")
    if subscription_id:
        cancel.assert_called_once_with(subscription_id)
    else:
        cancel.assert_not_called()


def test_checkout_completion_records_duplicate_cancellation(client, monkeypatch, caplog):
    _enable(monkeypatch)
    user = _add_user("duplicate-checkout@example.com")
    completed = _add_checkout(user, "cs_kept", "kept_checkout")
    sibling = _add_checkout(user, "cs_duplicate", "duplicate_checkout")
    db.session.commit()
    monkeypatch.setattr(
        stripe.checkout.Session,
        "expire",
        Mock(side_effect=stripe.InvalidRequestError("Checkout Session is not open", param=None)),
    )
    monkeypatch.setattr(
        stripe.checkout.Session,
        "retrieve",
        Mock(return_value={"status": "complete", "subscription": "sub_duplicate"}),
    )
    cancel = Mock(return_value={"id": "sub_duplicate", "status": "canceled"})
    retrieve = Mock(return_value=_subscription(user, subscription_id="sub_kept", status="active"))
    monkeypatch.setattr(stripe.Subscription, "cancel", cancel)
    monkeypatch.setattr(stripe.Subscription, "retrieve", retrieve)
    from src.services.email_service import email_service

    monkeypatch.setattr(email_service, "send_email", Mock(return_value=SimpleNamespace(success=True)))
    caplog.set_level("WARNING", logger="src.services.stripe_billing")

    response = _post_event(
        client,
        _event(
            "evt_duplicate_canceled",
            "checkout.session.completed",
            {"id": completed.stripe_session_id, "subscription": "sub_kept"},
        ),
    )

    assert response.status_code == 200
    assert db.session.get(BillingCheckoutSession, sibling.id).status == "complete"
    cancel.assert_called_once_with("sub_duplicate")
    retrieve.assert_called_once_with("sub_kept", expand=["items.data.price"])
    duplicate_event = ProductEvent.query.filter_by(event_name="billing_duplicate_canceled").one()
    assert duplicate_event.props == {
        "kept_subscription_id": "sub_kept",
        "canceled_subscription_id": "sub_duplicate",
        "product_code": "scout_pro",
        "scope_type": "user",
    }
    assert "sub_kept" in caplog.text
    assert "sub_duplicate" in caplog.text


def test_checkout_completion_transient_sibling_expiry_failure_retries(client, monkeypatch):
    _enable(monkeypatch)
    user = _add_user()
    completed = _add_checkout(user, "cs_completed_retry", "completed_retry")
    sibling = _add_checkout(user, "cs_sibling_retry", "sibling_retry")
    db.session.commit()
    monkeypatch.setattr(stripe.checkout.Session, "expire", Mock(side_effect=RuntimeError("Stripe unavailable")))

    response = _post_event(
        client,
        _event(
            "evt_sibling_retry",
            "checkout.session.completed",
            {"id": "cs_completed_retry"},
        ),
    )

    assert response.status_code == 500
    db.session.expire_all()
    assert db.session.get(BillingCheckoutSession, completed.id).status == "open"
    assert db.session.get(BillingCheckoutSession, sibling.id).status == "open"
    assert StripeWebhookEvent.query.filter_by(event_id="evt_sibling_retry", status="failed").count() == 1


def test_checkout_completion_duplicate_subscription_cancel_failure_retries(client, monkeypatch):
    _enable(monkeypatch)
    user = _add_user()
    completed = _add_checkout(user, "cs_completed_cancel_retry", "completed_cancel_retry")
    sibling = _add_checkout(user, "cs_sibling_cancel_retry", "sibling_cancel_retry")
    db.session.commit()
    monkeypatch.setattr(
        stripe.checkout.Session,
        "expire",
        Mock(side_effect=stripe.InvalidRequestError("Checkout Session is not open", param=None)),
    )
    monkeypatch.setattr(
        stripe.checkout.Session,
        "retrieve",
        Mock(return_value={"status": "complete", "subscription": "sub_duplicate_fail"}),
    )
    monkeypatch.setattr(stripe.Subscription, "cancel", Mock(side_effect=RuntimeError("Stripe unavailable")))

    response = _post_event(
        client,
        _event(
            "evt_sibling_cancel_retry",
            "checkout.session.completed",
            {"id": "cs_completed_cancel_retry"},
        ),
    )

    assert response.status_code == 500
    db.session.expire_all()
    assert db.session.get(BillingCheckoutSession, completed.id).status == "open"
    assert db.session.get(BillingCheckoutSession, sibling.id).status == "open"


def test_checkout_completion_accepts_duplicate_subscription_already_canceled(client, monkeypatch):
    _enable(monkeypatch)
    user = _add_user()
    completed = _add_checkout(user, "cs_completed_already_canceled", "completed_already_canceled")
    sibling = _add_checkout(user, "cs_sibling_already_canceled", "sibling_already_canceled")
    db.session.commit()
    monkeypatch.setattr(
        stripe.checkout.Session,
        "expire",
        Mock(side_effect=stripe.InvalidRequestError("Checkout Session is not open", param=None)),
    )
    monkeypatch.setattr(
        stripe.checkout.Session,
        "retrieve",
        Mock(return_value={"status": "complete", "subscription": "sub_already_canceled"}),
    )
    cancel = Mock(side_effect=stripe.InvalidRequestError("Subscription is canceled", param=None))
    retrieve_subscription = Mock(return_value={"id": "sub_already_canceled", "status": "canceled"})
    monkeypatch.setattr(stripe.Subscription, "cancel", cancel)
    monkeypatch.setattr(stripe.Subscription, "retrieve", retrieve_subscription)

    response = _post_event(
        client,
        _event(
            "evt_sibling_already_canceled",
            "checkout.session.completed",
            {"id": "cs_completed_already_canceled"},
        ),
    )

    assert response.status_code == 200
    assert db.session.get(BillingCheckoutSession, completed.id).status == "complete"
    assert db.session.get(BillingCheckoutSession, sibling.id).status == "complete"
    cancel.assert_called_once_with("sub_already_canceled")
    retrieve_subscription.assert_called_once_with("sub_already_canceled")


def test_checkout_completion_retries_when_duplicate_subscription_is_not_canceled(client, monkeypatch):
    _enable(monkeypatch)
    user = _add_user()
    completed = _add_checkout(user, "cs_completed_still_active", "completed_still_active")
    sibling = _add_checkout(user, "cs_sibling_still_active", "sibling_still_active")
    db.session.commit()
    monkeypatch.setattr(
        stripe.checkout.Session,
        "expire",
        Mock(side_effect=stripe.InvalidRequestError("Checkout Session is not open", param=None)),
    )
    monkeypatch.setattr(
        stripe.checkout.Session,
        "retrieve",
        Mock(return_value={"status": "complete", "subscription": "sub_still_active"}),
    )
    monkeypatch.setattr(
        stripe.Subscription,
        "cancel",
        Mock(side_effect=stripe.InvalidRequestError("Subscription cannot be canceled", param=None)),
    )
    retrieve_subscription = Mock(return_value={"id": "sub_still_active", "status": "active"})
    monkeypatch.setattr(stripe.Subscription, "retrieve", retrieve_subscription)

    response = _post_event(
        client,
        _event(
            "evt_sibling_still_active",
            "checkout.session.completed",
            {"id": "cs_completed_still_active"},
        ),
    )

    assert response.status_code == 500
    db.session.expire_all()
    assert db.session.get(BillingCheckoutSession, completed.id).status == "open"
    assert db.session.get(BillingCheckoutSession, sibling.id).status == "open"
    retrieve_subscription.assert_called_once_with("sub_still_active")


def test_expired_checkout_can_be_recreated_with_same_client_key(client, monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setenv("STRIPE_PRICE_SCOUT_PRO_MONTHLY", "price_monthly")
    monkeypatch.setenv("STRIPE_PRICE_SCOUT_PRO_YEARLY", "price_yearly")
    user = _add_user()
    headers = _headers(user)
    _, session_create = _mock_checkout(monkeypatch)
    first_payload = {"product_code": "scout_pro", "price_code": "monthly", "client_key": "same_client_key"}
    first = client.post("/api/billing/checkout", json=first_payload, headers=headers).get_json()
    first_key = session_create.call_args.kwargs["idempotency_key"]
    assert first_key == f"checkout:user:{user.id}:scout_pro:{user.id}:same_client_key"

    expired_event = _event(
        "evt_expired",
        "checkout.session.expired",
        {"id": first["session_id"], "client_reference_id": str(BillingCheckoutSession.query.one().id)},
    )
    assert _post_event(client, expired_event).status_code == 200
    assert BillingCheckoutSession.query.one().status == "expired"
    second_payload = {"product_code": "scout_pro", "price_code": "yearly", "client_key": "same_client_key"}
    second = client.post("/api/billing/checkout", json=second_payload, headers=headers)
    assert second.status_code == 200
    assert second.get_json()["checkout_url"].startswith("https://checkout.example/")
    assert second.get_json()["session_id"] != first["session_id"]
    assert session_create.call_count == 2
    assert session_create.call_args.kwargs["idempotency_key"] != first_key
    assert session_create.call_args.kwargs["line_items"] == [{"price": "price_yearly", "quantity": 1}]
    assert BillingCheckoutSession.query.count() == 1


def test_config_price_lookup_failure_omits_money(client, monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setenv("STRIPE_PRICE_SCOUT_PRO_MONTHLY", "price_good")
    monkeypatch.setenv("STRIPE_PRICE_SCOUT_PRO_YEARLY", "price_bad")

    def retrieve(price_id):
        if price_id == "price_bad":
            raise RuntimeError("lookup unavailable")
        return {"unit_amount": 900, "currency": "USD"}

    retrieve_mock = Mock(side_effect=retrieve)
    monkeypatch.setattr(stripe.Price, "retrieve", retrieve_mock)
    response = client.get("/api/billing/config")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    prices = response.get_json()["products"][0]["prices"]
    assert prices[0] == {"price_code": "monthly", "interval": "month", "unit_amount": 900, "currency": "usd"}
    assert prices[1] == {"price_code": "yearly", "interval": "year"}
    assert client.get("/api/billing/config").status_code == 200
    assert retrieve_mock.call_count == 2


def test_retrieved_subscription_uses_existing_event_watermark(client, monkeypatch):
    _enable(monkeypatch)
    user = _add_user()
    db.session.add(
        BillingSubscription(
            scope_type="user",
            scope_id=user.id,
            product_code="scout_pro",
            price_code="monthly",
            purchaser_user_id=user.id,
            stripe_customer_id=f"cus_{user.id}",
            stripe_subscription_id="sub_watermark",
            stripe_price_id="price_test_monthly",
            status="canceled",
            last_event_created=150,
        )
    )
    db.session.commit()

    retrieved = _subscription(user, subscription_id="sub_watermark", status="active")
    monkeypatch.setattr(stripe.Subscription, "retrieve", Mock(return_value=retrieved))
    sent = []
    from src.services.email_service import email_service

    monkeypatch.setattr(
        email_service,
        "send_email",
        lambda **kwargs: sent.append(kwargs) or SimpleNamespace(success=True),
    )
    completed = _event(
        "evt_checkout_completed_watermark",
        "checkout.session.completed",
        {"id": "cs_watermark", "subscription": "sub_watermark"},
        created=100,
    )
    retrieved_after = int(time.time())
    assert _post_event(client, completed).status_code == 200
    row = BillingSubscription.query.one()
    assert row.status == "active"
    assert row.last_event_created >= retrieved_after

    stale = _subscription(user, subscription_id="sub_watermark", status="canceled")
    updated = _event("evt_stale_after_checkout", "customer.subscription.updated", stale, created=90)
    assert _post_event(client, updated).status_code == 200
    assert BillingSubscription.query.one().status == "active"
    assert not any(message["subject"] == "Your Scout Pro subscription has ended" for message in sent)


def test_equal_subscription_watermark_uses_authoritative_snapshot(client, monkeypatch):
    _enable(monkeypatch)
    user = _add_user()
    event_created = 200
    current = _subscription(user, subscription_id="sub_equal_watermark", status="active")
    assert (
        _post_event(
            client,
            _event("evt_equal_current", "customer.subscription.updated", current, created=event_created),
        ).status_code
        == 200
    )

    authoritative = _subscription(user, subscription_id="sub_equal_watermark", status="active")
    retrieve = Mock(return_value=authoritative)
    monkeypatch.setattr(stripe.Subscription, "retrieve", retrieve)
    stale = _subscription(user, subscription_id="sub_equal_watermark", status="canceled")
    retrieved_after = int(time.time())
    response = _post_event(
        client,
        _event("evt_equal_stale", "customer.subscription.updated", stale, created=event_created),
    )

    assert response.status_code == 200
    row = BillingSubscription.query.one()
    assert row.status == "active"
    assert row.last_event_created >= retrieved_after
    retrieve.assert_called_once_with("sub_equal_watermark", expand=["items.data.price"])


def test_retrieved_invoice_snapshot_blocks_intermediate_stale_subscription_event(client, monkeypatch):
    _enable(monkeypatch)
    user = _add_user()
    subscription_id = "sub_invoice_watermark"
    invoice_created = int(time.time()) - 100
    active = _subscription(user, subscription_id=subscription_id, status="active")
    assert (
        _post_event(
            client,
            _event(
                "evt_before_invoice",
                "customer.subscription.updated",
                active,
                created=invoice_created - 10,
            ),
        ).status_code
        == 200
    )
    sent = []
    from src.services.email_service import email_service

    monkeypatch.setattr(
        email_service,
        "send_email",
        lambda **kwargs: sent.append(kwargs) or SimpleNamespace(success=True),
    )
    canceled = _subscription(user, subscription_id=subscription_id, status="canceled")
    retrieve = Mock(return_value=canceled)
    monkeypatch.setattr(stripe.Subscription, "retrieve", retrieve)
    retrieved_after = int(time.time())
    invoice = _event(
        "evt_old_invoice",
        "invoice.paid",
        {"subscription": subscription_id},
        created=invoice_created,
    )
    assert _post_event(client, invoice).status_code == 200
    assert BillingSubscription.query.one().status == "canceled"
    assert BillingSubscription.query.one().last_event_created >= retrieved_after
    retrieve.assert_called_once_with(subscription_id, expand=["items.data.price"])

    sent.clear()
    stale = _subscription(user, subscription_id=subscription_id, status="active")
    stale_event = _event(
        "evt_between_invoice_and_retrieval",
        "customer.subscription.updated",
        stale,
        created=invoice_created + 50,
    )
    assert _post_event(client, stale_event).status_code == 200
    assert BillingSubscription.query.one().status == "canceled"
    assert retrieve.call_count == 2
    assert not any(message["subject"] == "Your Scout Pro subscription is active" for message in sent)


def test_billing_me_and_portal(client, monkeypatch):
    _enable(monkeypatch)
    user = _add_user()
    headers = _headers(user)
    response = client.get("/api/billing/me", headers=headers)
    assert response.get_json() == {
        "enabled": True,
        "has_billing_account": False,
        "subscriptions": [],
        "gol": {
            "free_allowance": 3,
            "free_questions_remaining": 3,
            "credit_balance": 0,
            "purchases": [],
        },
    }
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
    assert client.get("/api/admin/billing/summary").status_code == 401
    empty = client.get("/api/admin/billing/summary", headers=_admin_headers()).get_json()
    assert empty["mrr_by_currency"] == {}
    assert empty["mrr_cents"] == 0
    assert empty["currency"] == "usd"

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
    response = client.get("/api/admin/billing/summary", headers=_admin_headers())
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["active_subscriptions"] == 2
    assert payload["by_product"] == {"scout_pro": 2}
    assert payload["mrr_by_currency"] == {"usd": 1700}
    assert payload["mrr_cents"] == 1700
    assert payload["currency"] == "usd"
    assert payload["checkout_sessions_open"] == 1

    three = _add_user("three@example.com", 103)
    db.session.add(
        BillingSubscription(
            scope_type="user",
            scope_id=three.id,
            product_code="scout_pro",
            price_code="monthly",
            purchaser_user_id=three.id,
            stripe_customer_id="cus_eur",
            stripe_subscription_id="sub_eur",
            stripe_price_id="price_eur",
            status="active",
            unit_amount=500,
            currency="eur",
            interval="month",
            current_period_end=now + timedelta(days=30),
        )
    )
    db.session.commit()
    mixed = client.get("/api/admin/billing/summary", headers=_admin_headers()).get_json()
    assert mixed["mrr_by_currency"] == {"eur": 500, "usd": 1700}
    assert mixed["mrr_cents"] is None
    assert mixed["currency"] is None


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
    db.session.add(
        BillingCheckoutSession(
            scope_type="user",
            scope_id=user.id,
            product_code="scout_pro",
            price_code="monthly",
            purchaser_user_id=user.id,
            client_key="delete_checkout",
            stripe_session_id="cs_delete",
            checkout_url="https://checkout.example/delete",
            status="open",
            expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1),
        )
    )
    db.session.commit()
    headers = _headers(user)
    exported = client.get("/api/account/export", headers=headers).get_json()
    assert exported["billing"]["has_billing_account"] is True
    assert exported["billing"]["subscriptions"][0]["product_code"] == "scout_pro"

    cancel = Mock(return_value={"id": "sub_delete", "status": "canceled"})
    expire = Mock(return_value={"id": "cs_delete", "status": "expired"})
    monkeypatch.setattr(stripe.Subscription, "cancel", cancel)
    monkeypatch.setattr(stripe.checkout.Session, "expire", expire)
    response = client.post("/api/account/delete", json={"confirm": "DELETE"}, headers=headers)
    assert response.status_code == 200
    cancel.assert_called_once_with("sub_delete")
    expire.assert_called_once_with("cs_delete")
    assert response.get_json()["counts"]["deleted"]["billing_subscriptions"] == 1
    assert response.get_json()["counts"]["deleted"]["billing_checkout_sessions"] == 1
    assert db.session.get(UserAccount, user.id) is None


def test_account_deletion_accepts_subscription_already_canceled_remotely(client, monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "billing_secret_test_placeholder")
    user = _add_user()
    db.session.add(
        BillingSubscription(
            scope_type="user",
            scope_id=user.id,
            product_code="scout_pro",
            price_code="monthly",
            purchaser_user_id=user.id,
            stripe_customer_id="cus_delete_already_canceled",
            stripe_subscription_id="sub_delete_already_canceled",
            stripe_price_id="price_delete_already_canceled",
            status="active",
        )
    )
    db.session.commit()
    cancel = Mock(side_effect=stripe.InvalidRequestError("Subscription already canceled", param=None))
    retrieve = Mock(return_value={"id": "sub_delete_already_canceled", "status": "canceled"})
    monkeypatch.setattr(stripe.Subscription, "cancel", cancel)
    monkeypatch.setattr(stripe.Subscription, "retrieve", retrieve)
    from src.services.stripe_billing import cancel_subscriptions_for_account_deletion

    assert cancel_subscriptions_for_account_deletion(user) == 1
    cancel.assert_called_once_with("sub_delete_already_canceled")
    retrieve.assert_called_once_with("sub_delete_already_canceled")


@pytest.mark.parametrize(("status", "should_cancel"), [("incomplete", True), ("canceled", False)])
def test_account_delete_cancels_every_non_terminal_subscription(client, monkeypatch, status, should_cancel):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "billing_secret_test_placeholder")
    user = _add_user()
    subscription_id = f"sub_delete_{status}"
    db.session.add(
        BillingSubscription(
            scope_type="user",
            scope_id=user.id,
            product_code="scout_pro",
            price_code="monthly",
            purchaser_user_id=user.id,
            stripe_customer_id=f"cus_delete_{status}",
            stripe_subscription_id=subscription_id,
            stripe_price_id=f"price_delete_{status}",
            status=status,
        )
    )
    db.session.commit()
    cancel = Mock(return_value={"id": subscription_id, "status": "canceled"})
    monkeypatch.setattr(stripe.Subscription, "cancel", cancel)

    response = client.post("/api/account/delete", json={"confirm": "DELETE"}, headers=_headers(user))

    assert response.status_code == 200
    if should_cancel:
        cancel.assert_called_once_with(subscription_id)
    else:
        cancel.assert_not_called()
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


def test_account_delete_aborts_when_checkout_expiry_fails(client, monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "billing_secret_test_placeholder")
    user = _add_user()
    db.session.add(
        BillingCheckoutSession(
            scope_type="user",
            scope_id=user.id,
            product_code="scout_pro",
            price_code="monthly",
            purchaser_user_id=user.id,
            client_key="delete_expire_fail",
            stripe_session_id="cs_delete_fail",
            status="open",
            expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1),
        )
    )
    db.session.commit()
    monkeypatch.setattr(stripe.checkout.Session, "expire", Mock(side_effect=RuntimeError("Stripe unavailable")))

    response = client.post("/api/account/delete", json={"confirm": "DELETE"}, headers=_headers(user))

    assert response.status_code == 503
    assert response.get_json() == {"error": "billing_cancel_failed"}
    assert db.session.get(UserAccount, user.id) is not None
    assert BillingCheckoutSession.query.filter_by(stripe_session_id="cs_delete_fail", status="open").count() == 1


def test_account_delete_retrieves_already_expired_checkout(client, monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "billing_secret_test_placeholder")
    user = _add_user()
    _add_checkout(user, "cs_already_expired", "delete_expired_checkout")
    db.session.commit()
    expire = Mock(side_effect=stripe.InvalidRequestError("Checkout Session is not open", param=None))
    retrieve = Mock(return_value={"id": "cs_already_expired", "status": "expired"})
    monkeypatch.setattr(stripe.checkout.Session, "expire", expire)
    monkeypatch.setattr(stripe.checkout.Session, "retrieve", retrieve)

    response = client.post("/api/account/delete", json={"confirm": "DELETE"}, headers=_headers(user))

    assert response.status_code == 200
    assert db.session.get(UserAccount, user.id) is None
    expire.assert_called_once_with("cs_already_expired")
    retrieve.assert_called_once_with("cs_already_expired")


def test_account_delete_cancels_subscription_from_completed_checkout(client, monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "billing_secret_test_placeholder")
    user = _add_user()
    _add_checkout(user, "cs_completed_before_webhook", "delete_completed_checkout")
    db.session.commit()
    monkeypatch.setattr(
        stripe.checkout.Session,
        "expire",
        Mock(side_effect=stripe.InvalidRequestError("Checkout Session is not open", param=None)),
    )
    retrieve = Mock(
        return_value={
            "id": "cs_completed_before_webhook",
            "status": "complete",
            "subscription": "sub_completed_before_webhook",
        }
    )
    cancel = Mock(return_value={"id": "sub_completed_before_webhook", "status": "canceled"})
    monkeypatch.setattr(stripe.checkout.Session, "retrieve", retrieve)
    monkeypatch.setattr(stripe.Subscription, "cancel", cancel)

    response = client.post("/api/account/delete", json={"confirm": "DELETE"}, headers=_headers(user))

    assert response.status_code == 200
    retrieve.assert_called_once_with("cs_completed_before_webhook")
    cancel.assert_called_once_with("sub_completed_before_webhook")
    assert db.session.get(UserAccount, user.id) is None


def test_account_delete_aborts_when_completed_checkout_subscription_cancel_fails(client, monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "billing_secret_test_placeholder")
    user = _add_user()
    _add_checkout(user, "cs_completed_cancel_fail", "delete_completed_cancel_fail")
    db.session.commit()
    monkeypatch.setattr(
        stripe.checkout.Session,
        "expire",
        Mock(side_effect=stripe.InvalidRequestError("Checkout Session is not open", param=None)),
    )
    monkeypatch.setattr(
        stripe.checkout.Session,
        "retrieve",
        Mock(return_value={"status": "complete", "subscription": "sub_completed_cancel_fail"}),
    )
    monkeypatch.setattr(stripe.Subscription, "cancel", Mock(side_effect=RuntimeError("Stripe unavailable")))

    response = client.post("/api/account/delete", json={"confirm": "DELETE"}, headers=_headers(user))

    assert response.status_code == 503
    assert response.get_json() == {"error": "billing_cancel_failed"}
    assert db.session.get(UserAccount, user.id) is not None


def test_account_delete_allows_checkout_missing_under_configured_key(client, monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "billing_secret_test_placeholder")
    user = _add_user()
    _add_checkout(user, "cs_resource_missing", "delete_resource_missing")
    db.session.commit()
    invalid_request = stripe.InvalidRequestError("No such Checkout Session", param="id")
    monkeypatch.setattr(stripe.checkout.Session, "expire", Mock(side_effect=invalid_request))
    retrieve = Mock(side_effect=stripe.InvalidRequestError("No such Checkout Session", param="id"))
    monkeypatch.setattr(stripe.checkout.Session, "retrieve", retrieve)

    response = client.post("/api/account/delete", json={"confirm": "DELETE"}, headers=_headers(user))

    assert response.status_code == 200
    retrieve.assert_called_once_with("cs_resource_missing")
    assert db.session.get(UserAccount, user.id) is None


def test_account_delete_skips_time_expired_checkout_without_key(client, monkeypatch):
    user = _add_user()
    _add_checkout(
        user,
        "cs_time_expired",
        "delete_time_expired",
        expires_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1),
    )
    db.session.commit()
    expire = Mock()
    retrieve = Mock()
    monkeypatch.setattr(stripe.checkout.Session, "expire", expire)
    monkeypatch.setattr(stripe.checkout.Session, "retrieve", retrieve)

    response = client.post("/api/account/delete", json={"confirm": "DELETE"}, headers=_headers(user))

    assert response.status_code == 200
    expire.assert_not_called()
    retrieve.assert_not_called()
    assert db.session.get(UserAccount, user.id) is None


@pytest.mark.parametrize("billing_row", ["active_subscription", "incomplete_subscription", "checkout"])
def test_account_delete_requires_secret_for_payable_billing_rows(client, monkeypatch, billing_row):
    user = _add_user()
    if billing_row.endswith("_subscription"):
        db.session.add(
            BillingSubscription(
                scope_type="user",
                scope_id=user.id,
                product_code="scout_pro",
                price_code="monthly",
                purchaser_user_id=user.id,
                stripe_customer_id="cus_missing_key",
                stripe_subscription_id=f"sub_missing_key_{billing_row}",
                stripe_price_id="price_missing_key",
                status=billing_row.removesuffix("_subscription"),
            )
        )
    else:
        db.session.add(
            BillingCheckoutSession(
                scope_type="user",
                scope_id=user.id,
                product_code="scout_pro",
                price_code="monthly",
                purchaser_user_id=user.id,
                client_key="missing_key_checkout",
                stripe_session_id="cs_missing_key",
                status="open",
                expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1),
            )
        )
    db.session.commit()
    cancel = Mock()
    expire = Mock()
    monkeypatch.setattr(stripe.Subscription, "cancel", cancel)
    monkeypatch.setattr(stripe.checkout.Session, "expire", expire)

    response = client.post("/api/account/delete", json={"confirm": "DELETE"}, headers=_headers(user))

    assert response.status_code == 503
    assert response.get_json() == {"error": "billing_cancel_failed"}
    assert db.session.get(UserAccount, user.id) is not None
    cancel.assert_not_called()
    expire.assert_not_called()


def test_account_delete_locks_user_before_scanning_billing_rows(client, monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "billing_secret_test_placeholder")
    user = _add_user()
    headers = _headers(user)
    checkout = BillingCheckoutSession(
        scope_type="user",
        scope_id=user.id,
        product_code="scout_pro",
        price_code="monthly",
        purchaser_user_id=user.id,
        client_key="checkout_during_lock",
        stripe_session_id="cs_checkout_during_lock",
        status="open",
        expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1),
    )
    real_execute = db.session.execute
    inserted = False

    def insert_checkout_before_lock(statement, *args, **kwargs):
        nonlocal inserted
        if not inserted and getattr(statement, "_for_update_arg", None) is not None:
            inserted = True
            db.session.add(checkout)
            db.session.flush()
        return real_execute(statement, *args, **kwargs)

    expire = Mock(return_value={"id": "cs_checkout_during_lock", "status": "expired"})
    monkeypatch.setattr(db.session, "execute", insert_checkout_before_lock)
    monkeypatch.setattr(stripe.checkout.Session, "expire", expire)

    response = client.post("/api/account/delete", json={"confirm": "DELETE"}, headers=headers)

    assert response.status_code == 200
    assert inserted is True
    expire.assert_called_once_with("cs_checkout_during_lock")
    assert db.session.get(UserAccount, user.id) is None


def test_account_delete_without_billing_rows_needs_no_stripe_key(client):
    user = _add_user()

    response = client.post("/api/account/delete", json={"confirm": "DELETE"}, headers=_headers(user))

    assert response.status_code == 200
    assert db.session.get(UserAccount, user.id) is None


def test_client_event_allowlist_has_only_public_billing_events():
    assert "checkout_started" in ALLOWED_EVENTS
    assert "checkout_completed" in ALLOWED_EVENTS
    assert "billing_checkout_started" not in ALLOWED_EVENTS
    assert "billing_duplicate_canceled" not in ALLOWED_EVENTS
