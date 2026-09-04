"""GC-P0 GOL credit ledger, Checkout, webhook, streaming, and deletion contracts."""

import json
import time
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest
import stripe
from flask import Flask
from src.auth import issue_user_token
from src.extensions import limiter
from src.models.billing import BillingCheckoutSession, BillingSubscription, StripeWebhookEvent
from src.models.gol_credits import GolCreditLedger
from src.models.league import UserAccount, db
from src.models.product_event import ProductEvent
from src.services.gol_credits import apply_refund, grant_purchase, reserve_question

WEBHOOK_SECRET = "gol_webhook_test_placeholder"


class _StubGolService:
    events = [{"event": "done", "data": {"ok": True}}]

    def __init__(self, session_id=None, model_override=None):
        self.session_id = session_id
        self.model_override = model_override

    def chat(self, message, history, session_id):
        yield from self.events

    def get_suggestions(self):
        return ["A suggestion"]


@pytest.fixture
def app(monkeypatch):
    from src.routes.account import account_bp
    from src.routes.auth_routes import auth_bp
    from src.routes.billing import _non_usd_pack_warnings, _price_cache, billing_bp
    from src.routes.gol import gol_bp
    from src.routes.scout import scout_bp
    from src.services import gol_service, pdf_renderer

    for name in (
        "BILLING_ENABLED",
        "GOL_FREE_ALLOWANCE",
        "STRIPE_SECRET_KEY",
        "STRIPE_WEBHOOK_SECRET",
        "STRIPE_PRICE_GOL_STARTER",
        "STRIPE_PRICE_GOL_TOPUP",
        "GOL_STARTER_CREDITS",
        "GOL_TOPUP_CREDITS",
        "STRIPE_PRICE_SCOUT_PRO_MONTHLY",
        "STRIPE_PRICE_SCOUT_PRO_YEARLY",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ADMIN_API_KEY", "gol-admin-key")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.com")
    monkeypatch.setattr(gol_service, "GolService", _StubGolService)
    monkeypatch.setattr(pdf_renderer, "render_gol_chat_pdf", lambda messages: (b"%PDF-gol", "gol.pdf"))
    _StubGolService.events = [{"event": "done", "data": {"ok": True}}]
    _price_cache.clear()
    _non_usd_pack_warnings.clear()

    test_app = Flask(__name__)
    test_app.config.update(
        TESTING=True,
        SECRET_KEY="gol-credits-test-secret",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        RATELIMIT_ENABLED=False,
    )
    db.init_app(test_app)
    limiter.init_app(test_app)
    test_app.register_blueprint(gol_bp, url_prefix="/api")
    test_app.register_blueprint(billing_bp, url_prefix="/api")
    test_app.register_blueprint(account_bp, url_prefix="/api")
    test_app.register_blueprint(scout_bp, url_prefix="/api")
    test_app.register_blueprint(auth_bp, url_prefix="/api")

    with test_app.app_context():
        db.create_all()
        yield test_app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def _user(email="gol@example.com"):
    user = UserAccount(
        email=email,
        display_name="GOL User",
        display_name_lower=email,
        display_name_confirmed=True,
        scout_tier="free",
    )
    db.session.add(user)
    db.session.commit()
    return user


def _headers(user, *, role="user"):
    return {"Authorization": f"Bearer {issue_user_token(user.email, role=role)['token']}"}


def _enable(monkeypatch):
    monkeypatch.setenv("BILLING_ENABLED", "true")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", WEBHOOK_SECRET)


def _packs(monkeypatch):
    monkeypatch.setenv("STRIPE_PRICE_GOL_STARTER", "price_gol_starter")
    monkeypatch.setenv("GOL_STARTER_CREDITS", "7")
    monkeypatch.setenv("STRIPE_PRICE_GOL_TOPUP", "price_gol_topup")
    monkeypatch.setenv("GOL_TOPUP_CREDITS", "4")
    monkeypatch.setattr(stripe.Price, "retrieve", lambda price_id: {"unit_amount": 2000, "currency": "usd"})


def _event(event_id, event_type, obj):
    return {
        "id": event_id,
        "object": "event",
        "type": event_type,
        "created": int(time.time()),
        "data": {"object": obj},
    }


def _post_event(client, event):
    raw = json.dumps(event, separators=(",", ":")).encode()
    timestamp = int(time.time())
    signature = stripe.WebhookSignature._compute_signature(f"{timestamp}.{raw.decode()}", WEBHOOK_SECRET)
    return client.post(
        "/api/billing/stripe/webhook",
        data=raw,
        headers={"Stripe-Signature": f"t={timestamp},v1={signature}", "Content-Type": "application/json"},
    )


def _checkout(user, session_id, *, pack_id="gol_starter"):
    row = BillingCheckoutSession(
        scope_type="user",
        scope_id=user.id,
        product_code="gol",
        price_code=pack_id,
        purchaser_user_id=user.id,
        client_key=f"key_{session_id}",
        stripe_session_id=session_id,
        checkout_url=f"https://checkout.example/{session_id}",
        status="open",
        expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1),
    )
    db.session.add(row)
    db.session.commit()
    return row


def _completed(session_id, *, paid=True, payment_intent="pi_gol", amount=2000):
    return {
        "id": session_id,
        "mode": "payment",
        "payment_status": "paid" if paid else "unpaid",
        "payment_intent": payment_intent,
        "amount_total": amount,
        "currency": "usd",
    }


def test_catalog_ignores_pack_only_product_and_resolves_valid_packs(monkeypatch):
    from src.config.stripe_config import offered_packs, offered_products, product_for_price_id, resolve_price

    _packs(monkeypatch)
    assert "gol" not in offered_products()
    assert resolve_price("gol", "gol_starter") is None
    assert product_for_price_id("price_gol_starter") is None
    assert offered_packs() == {
        "gol_starter": {"price_id": "price_gol_starter", "credits": 7, "label": "Starter"},
        "gol_topup": {"price_id": "price_gol_topup", "credits": 4, "label": "Top up"},
    }
    monkeypatch.setenv("GOL_TOPUP_CREDITS", "0")
    assert "gol_topup" not in offered_packs()


def test_dark_chat_needs_no_client_id_and_never_queries_ledger(app, client, monkeypatch):
    user = _user()
    from src.services import gol_credits

    monkeypatch.setattr(gol_credits, "_balance_values", Mock(side_effect=AssertionError("ledger queried")))
    response = client.post("/api/gol/chat", json={"message": "Who is in form?"}, headers=_headers(user))
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert body.startswith("event: usage")
    assert '"bucket": "disabled"' in body
    assert GolCreditLedger.query.count() == 0


def test_lit_chat_uses_three_free_questions_then_returns_json_402(app, client, monkeypatch):
    _enable(monkeypatch)
    user = _user()
    for number in range(3):
        response = client.post(
            "/api/gol/chat",
            json={"message": "Question", "client_msg_id": f"message_{number}"},
            headers=_headers(user),
        )
        assert response.status_code == 200
        assert response.get_data(as_text=True).startswith("event: usage")
    exhausted = client.post(
        "/api/gol/chat",
        json={"message": "One more", "client_msg_id": "message_3"},
        headers=_headers(user),
    )
    assert exhausted.status_code == 402
    assert exhausted.mimetype == "application/json"
    assert exhausted.get_json() == {
        "error": "credits_exhausted",
        "feature": "gol_chat",
        "free_questions_remaining": 0,
        "credit_balance": 0,
        "top_up_path": "/account/billing",
    }


def test_lit_chat_validation_and_service_init_happen_before_reservation(app, client, monkeypatch):
    _enable(monkeypatch)
    user = _user()
    assert client.post(
        "/api/gol/chat", data="[]", content_type="application/json", headers=_headers(user)
    ).get_json() == {"error": "invalid_json"}
    invalid_id = client.post("/api/gol/chat", json={"message": "Question"}, headers=_headers(user))
    assert invalid_id.status_code == 400
    assert invalid_id.get_json() == {"error": "invalid_client_msg_id"}
    from src.services import gol_service

    monkeypatch.setattr(gol_service, "GolService", Mock(side_effect=RuntimeError("offline")))
    unavailable = client.post(
        "/api/gol/chat",
        json={"message": "Question", "client_msg_id": "service_down"},
        headers=_headers(user),
    )
    assert unavailable.status_code == 503
    assert GolCreditLedger.query.count() == 0


def test_same_message_is_one_debit_and_error_refund_allows_attempt_two(app, client, monkeypatch):
    _enable(monkeypatch)
    user = _user()
    payload = {"message": "Question", "client_msg_id": "same_msg_id"}
    first = client.post("/api/gol/chat", json=payload, headers=_headers(user)).get_data(as_text=True)
    second = client.post("/api/gol/chat", json=payload, headers=_headers(user)).get_data(as_text=True)
    assert '"debited": true' in first
    assert '"debited": false' in second
    assert GolCreditLedger.query.filter_by(kind="debit").count() == 1

    _StubGolService.events = [
        {"event": "error", "data": {"message": "failed"}},
        {"event": "error", "data": {"message": "failed again"}},
    ]
    error_payload = {"message": "Question", "client_msg_id": "error_msg_id"}
    errored = client.post("/api/gol/chat", json=error_payload, headers=_headers(user)).get_data(as_text=True)
    debit = GolCreditLedger.query.filter_by(client_msg_id="error_msg_id", kind="debit").one()
    assert errored.count('"refunded": true') == 1
    assert GolCreditLedger.query.filter_by(idempotency_key=f"refund:{debit.id}").count() == 1

    _StubGolService.events = [{"event": "done", "data": {"ok": True}}]
    client.post("/api/gol/chat", json=error_payload, headers=_headers(user)).get_data()
    attempts = [
        row.attempt for row in GolCreditLedger.query.filter_by(client_msg_id="error_msg_id", kind="debit").all()
    ]
    assert attempts == [1, 2]


def test_exhausted_user_cannot_reuse_client_id_for_a_different_question(app, client, monkeypatch):
    _enable(monkeypatch)
    user = _user()
    headers = _headers(user)
    first_id = "bound_msg_id"
    for number in range(3):
        response = client.post(
            "/api/gol/chat",
            json={
                "message": "Original question" if number == 0 else f"Question {number}",
                "client_msg_id": first_id if number == 0 else f"bound_msg_{number}",
            },
            headers=headers,
        )
        assert response.status_code == 200
        response.get_data()
    exhausted = client.post(
        "/api/gol/chat",
        json={"message": "No balance", "client_msg_id": "bound_msg_3"},
        headers=headers,
    )
    assert exhausted.status_code == 402
    ledger_count = GolCreditLedger.query.count()

    reused = client.post(
        "/api/gol/chat",
        json={"message": "A brand new question", "client_msg_id": first_id},
        headers=headers,
    )
    assert reused.status_code == 409
    assert reused.mimetype == "application/json"
    assert reused.get_json() == {"error": "client_msg_id_reused"}
    assert GolCreditLedger.query.count() == ledger_count

    retry = client.post(
        "/api/gol/chat",
        json={"message": "  ORIGINAL   Question ", "client_msg_id": first_id},
        headers=headers,
    )
    retry_body = retry.get_data(as_text=True)
    assert retry.status_code == 200
    assert '"debited": false' in retry_body
    debit = GolCreditLedger.query.filter_by(client_msg_id=first_id, kind="debit").one()
    from src.services.gol_credits import refund_question

    assert refund_question(user, first_id) is True
    assert GolCreditLedger.query.filter_by(idempotency_key=f"refund:{debit.id}").count() == 1


def test_stream_exception_refunds_but_client_disconnect_does_not(app, client, monkeypatch):
    _enable(monkeypatch)
    user = _user()

    def raising_chat(self, message, history, session_id):
        yield {"event": "token", "data": {"text": "partial"}}
        raise RuntimeError("stream failed")

    monkeypatch.setattr(_StubGolService, "chat", raising_chat)
    failed = client.post(
        "/api/gol/chat",
        json={"message": "Question", "client_msg_id": "stream_error"},
        headers=_headers(user),
    ).get_data(as_text=True)
    debit = GolCreditLedger.query.filter_by(client_msg_id="stream_error", kind="debit").one()
    assert failed.index("event: error") < failed.index('"refunded": true')
    assert GolCreditLedger.query.filter_by(idempotency_key=f"refund:{debit.id}").count() == 1

    response = client.post(
        "/api/gol/chat",
        json={"message": "Question", "client_msg_id": "disconnect_msg"},
        headers=_headers(user),
        buffered=False,
    )
    assert next(response.response).decode().startswith("event: usage")
    response.close()
    disconnect_debit = GolCreditLedger.query.filter_by(client_msg_id="disconnect_msg", kind="debit").one()
    assert GolCreditLedger.query.filter_by(idempotency_key=f"refund:{disconnect_debit.id}").count() == 0


def test_admin_and_pdf_export_never_debit(app, client, monkeypatch):
    _enable(monkeypatch)
    user = _user("admin@example.com")
    chat = client.post(
        "/api/gol/chat",
        json={"message": "Admin question", "client_msg_id": "admin_msg"},
        headers=_headers(user, role="admin"),
    )
    assert '"bucket": "exempt"' in chat.get_data(as_text=True)
    pdf = client.post(
        "/api/gol/export-pdf",
        json={"messages": [{"role": "user", "content": "Question"}]},
        headers=_headers(user),
    )
    assert pdf.status_code == 200
    assert GolCreditLedger.query.count() == 0


def test_payment_checkout_metadata_and_client_key_conflict(app, client, monkeypatch):
    _enable(monkeypatch)
    _packs(monkeypatch)
    user = _user()
    db.session.add(
        BillingSubscription(
            scope_type="user",
            scope_id=user.id,
            product_code="scout_pro",
            price_code="monthly",
            purchaser_user_id=user.id,
            stripe_customer_id="cus_existing_pro",
            stripe_subscription_id="sub_existing_pro",
            stripe_price_id="price_existing_pro",
            status="active",
        )
    )
    db.session.commit()
    customer = Mock(return_value={"id": "cus_gol"})
    session = Mock(
        return_value={
            "id": "cs_gol",
            "url": "https://checkout.example/gol",
            "expires_at": int(time.time()) + 3600,
        }
    )
    monkeypatch.setattr(stripe.Customer, "create", customer)
    monkeypatch.setattr(stripe.checkout.Session, "create", session)
    response = client.post(
        "/api/billing/checkout",
        json={"pack_id": "gol_starter", "client_key": "checkout_key"},
        headers=_headers(user),
    )
    assert response.status_code == 200
    kwargs = session.call_args.kwargs
    expected_metadata = {
        "kind": "credit_topup",
        "product_code": "gol",
        "pack_id": "gol_starter",
        "user_id": str(user.id),
        "app": "academy_watch",
    }
    assert kwargs["mode"] == "payment"
    assert kwargs["metadata"] == expected_metadata
    assert kwargs["payment_intent_data"] == {"metadata": expected_metadata}
    assert "subscription_data" not in kwargs
    assert "allow_promotion_codes" not in kwargs
    assert kwargs["idempotency_key"] == f"checkout:gol:gol_starter:{user.id}:checkout_key"

    conflict = client.post(
        "/api/billing/checkout",
        json={"pack_id": "gol_topup", "client_key": "checkout_key"},
        headers=_headers(user),
    )
    assert conflict.status_code == 409
    assert conflict.get_json() == {"error": "client_key_conflict"}
    assert session.call_count == 1


def test_config_omits_non_usd_pack_and_checkout_xor_is_enforced(app, client, monkeypatch):
    _enable(monkeypatch)
    _packs(monkeypatch)

    def retrieve(price_id):
        currency = "eur" if price_id == "price_gol_topup" else "usd"
        return {"unit_amount": 2000, "currency": currency}

    monkeypatch.setattr(stripe.Price, "retrieve", retrieve)
    config = client.get("/api/billing/config").get_json()
    assert config["packs"] == [
        {"pack_id": "gol_starter", "label": "Starter", "credits": 7, "unit_amount": 2000, "currency": "usd"}
    ]
    user = _user()
    both = client.post(
        "/api/billing/checkout",
        json={
            "pack_id": "gol_starter",
            "product_code": "scout_pro",
            "price_code": "monthly",
            "client_key": "both_keys",
        },
        headers=_headers(user),
    )
    assert both.status_code == 400
    assert both.get_json() == {"error": "invalid_checkout_request"}


def test_non_usd_pack_is_rejected_at_checkout_but_completed_charge_is_granted(app, client, monkeypatch):
    _enable(monkeypatch)
    _packs(monkeypatch)
    user = _user()
    monkeypatch.setattr(stripe.Price, "retrieve", lambda price_id: {"unit_amount": 1800, "currency": "eur"})
    session_create = Mock()
    monkeypatch.setattr(stripe.checkout.Session, "create", session_create)
    rejected = client.post(
        "/api/billing/checkout",
        json={"pack_id": "gol_starter", "client_key": "non_usd_key"},
        headers=_headers(user),
    )
    assert rejected.status_code == 400
    assert rejected.get_json() == {"error": "unknown_pack"}
    session_create.assert_not_called()

    _checkout(user, "cs_non_usd")
    completed = _completed("cs_non_usd")
    completed["currency"] = "eur"
    fulfilled = _post_event(client, _event("evt_non_usd", "checkout.session.completed", completed))
    assert fulfilled.status_code == 200
    grant = GolCreditLedger.query.filter_by(stripe_session_id="cs_non_usd").one()
    assert grant.currency == "eur"


def test_pack_price_lookup_failure_makes_checkout_temporarily_unavailable(app, client, monkeypatch):
    _enable(monkeypatch)
    _packs(monkeypatch)
    user = _user()
    monkeypatch.setattr(stripe.Price, "retrieve", Mock(side_effect=RuntimeError("price lookup failed")))
    session_create = Mock()
    monkeypatch.setattr(stripe.checkout.Session, "create", session_create)

    response = client.post(
        "/api/billing/checkout",
        json={"pack_id": "gol_starter", "client_key": "lookup_failure"},
        headers=_headers(user),
    )

    assert response.status_code == 503
    assert response.get_json() == {"error": "checkout_unavailable"}
    session_create.assert_not_called()


def test_paid_unpaid_async_and_missing_local_checkout_webhooks(app, client, monkeypatch):
    _enable(monkeypatch)
    _packs(monkeypatch)
    user = _user()
    _checkout(user, "cs_paid")
    paid = _event("evt_paid", "checkout.session.completed", _completed("cs_paid"))
    response = _post_event(client, paid)
    assert response.get_json() == {"received": True, "duplicate": False}
    assert GolCreditLedger.query.filter_by(kind="grant", delta=7).count() == 1
    assert _post_event(client, paid).get_json() == {"received": True, "duplicate": True}
    assert GolCreditLedger.query.filter_by(kind="grant").count() == 1

    _checkout(user, "cs_unpaid", pack_id="gol_topup")
    assert (
        _post_event(
            client,
            _event("evt_unpaid", "checkout.session.completed", _completed("cs_unpaid", paid=False)),
        ).status_code
        == 200
    )
    assert GolCreditLedger.query.filter_by(stripe_session_id="cs_unpaid").count() == 0

    _checkout(user, "cs_async", pack_id="gol_topup")
    async_response = _post_event(
        client,
        _event(
            "evt_async",
            "checkout.session.async_payment_succeeded",
            _completed("cs_async", payment_intent="pi_async"),
        ),
    )
    assert async_response.status_code == 200
    assert GolCreditLedger.query.filter_by(stripe_session_id="cs_async", delta=4).count() == 1

    missing = _post_event(
        client,
        _event("evt_missing", "checkout.session.completed", _completed("cs_missing")),
    )
    assert missing.status_code == 500
    assert StripeWebhookEvent.query.filter_by(event_id="evt_missing", status="failed").count() == 1


@pytest.mark.parametrize("payment_status", ("paid", "no_payment_required"))
def test_zero_amount_completed_checkout_grants_without_payment_intent(app, client, monkeypatch, payment_status):
    _enable(monkeypatch)
    _packs(monkeypatch)
    user = _user()
    session_id = f"cs_zero_{payment_status}"
    _checkout(user, session_id)
    completed = _completed(session_id, payment_intent=None, amount=0)
    completed["payment_status"] = payment_status
    response = _post_event(client, _event(f"evt_zero_{payment_status}", "checkout.session.completed", completed))
    assert response.status_code == 200
    grant = GolCreditLedger.query.filter_by(stripe_session_id=session_id).one()
    assert grant.stripe_payment_intent_id is None
    assert grant.amount_paid_cents == 0
    assert (
        apply_refund(
            payment_intent_id=None,
            cumulative_refunded_cents=0,
            stripe_event_id="evt_zero_refund",
        )
        == 0
    )


def test_expired_payment_checkout_uses_a_new_stripe_idempotency_key(app, client, monkeypatch):
    _enable(monkeypatch)
    _packs(monkeypatch)
    user = _user()
    monkeypatch.setattr(stripe.Customer, "create", Mock(return_value={"id": "cus_retry"}))
    session_create = Mock(
        side_effect=[
            {"id": "cs_retry_one", "url": "https://checkout.example/one", "expires_at": int(time.time()) + 3600},
            {"id": "cs_retry_two", "url": "https://checkout.example/two", "expires_at": int(time.time()) + 7200},
        ]
    )
    monkeypatch.setattr(stripe.checkout.Session, "create", session_create)
    payload = {"pack_id": "gol_starter", "client_key": "retry_checkout"}
    first = client.post("/api/billing/checkout", json=payload, headers=_headers(user))
    assert first.status_code == 200
    first_key = session_create.call_args.kwargs["idempotency_key"]
    row = BillingCheckoutSession.query.filter_by(stripe_session_id="cs_retry_one").one()
    row.expires_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1)
    db.session.commit()

    second = client.post("/api/billing/checkout", json=payload, headers=_headers(user))
    assert second.status_code == 200
    second_key = session_create.call_args.kwargs["idempotency_key"]
    assert first_key != second_key
    assert second_key.startswith(f"checkout:gol:gol_starter:{user.id}:retry_checkout:")


def test_refund_target_math_reverses_three_then_four_and_tracks_cumulative(app, monkeypatch):
    _enable(monkeypatch)
    user = _user()
    grant_purchase(
        user,
        pack_id="gol_starter",
        credits=7,
        stripe_session_id="cs_refund",
        stripe_payment_intent_id="pi_refund",
        stripe_event_id="evt_grant",
        amount_paid_cents=2000,
        currency="usd",
    )
    db.session.commit()
    assert (
        apply_refund(
            payment_intent_id="pi_refund",
            cumulative_refunded_cents=1000,
            stripe_event_id="evt_half",
        )
        == 3
    )
    db.session.commit()
    assert (
        apply_refund(
            payment_intent_id="pi_refund",
            cumulative_refunded_cents=2000,
            stripe_event_id="evt_full",
        )
        == 4
    )
    db.session.commit()
    assert (
        apply_refund(
            payment_intent_id="pi_refund",
            cumulative_refunded_cents=2000,
            stripe_event_id="evt_replay",
        )
        == 0
    )
    db.session.commit()
    assert [row.delta for row in GolCreditLedger.query.filter_by(kind="reversal").order_by(GolCreditLedger.id)] == [
        -3,
        -4,
    ]
    assert GolCreditLedger.query.filter_by(kind="grant").one().refunded_cents == 2000


def test_charge_refund_webhook_updates_grant_and_unknown_payment_is_ignored(app, client, monkeypatch):
    _enable(monkeypatch)
    user = _user()
    grant_purchase(
        user,
        pack_id="gol_starter",
        credits=7,
        stripe_session_id="cs_charge_refund",
        stripe_payment_intent_id="pi_charge_refund",
        stripe_event_id="evt_grant",
        amount_paid_cents=2000,
        currency="usd",
    )
    db.session.commit()
    refunded = _post_event(
        client,
        _event(
            "evt_charge_refund",
            "charge.refunded",
            {"payment_intent": "pi_charge_refund", "amount_refunded": 1000},
        ),
    )
    assert refunded.status_code == 200
    assert GolCreditLedger.query.filter_by(kind="reversal", delta=-3).count() == 1
    unknown = _post_event(
        client,
        _event("evt_unknown_refund", "charge.refunded", {"payment_intent": "pi_unknown", "amount_refunded": 500}),
    )
    assert unknown.status_code == 200
    assert StripeWebhookEvent.query.filter_by(event_id="evt_unknown_refund", status="ignored").count() == 1


def test_billing_me_auth_me_and_negative_admin_summary_agree(app, client, monkeypatch):
    _enable(monkeypatch)
    user = _user()
    eur_user = _user("gol-eur@example.com")
    db.session.add_all(
        [
            GolCreditLedger(
                user_account_id=user.id,
                bucket="prepaid",
                kind="grant",
                delta=2,
                idempotency_key="grant:summary",
                stripe_session_id="cs_summary",
                stripe_payment_intent_id="pi_summary",
                pack_id="gol_starter",
                amount_paid_cents=2000,
                currency="usd",
                refunded_cents=1000,
            ),
            GolCreditLedger(
                user_account_id=eur_user.id,
                bucket="prepaid",
                kind="grant",
                delta=5,
                idempotency_key="grant:summary-eur",
                stripe_session_id="cs_summary_eur",
                stripe_payment_intent_id="pi_summary_eur",
                pack_id="gol_starter",
                amount_paid_cents=1800,
                currency="eur",
                refunded_cents=600,
            ),
            GolCreditLedger(
                user_account_id=user.id,
                bucket="prepaid",
                kind="adjustment",
                delta=-3,
                idempotency_key="adjustment:summary",
            ),
        ]
    )
    db.session.commit()
    billing = client.get("/api/billing/me", headers=_headers(user)).get_json()["gol"]
    auth = client.get("/api/auth/me", headers=_headers(user)).get_json()["scout_pro"]["features"]
    assert billing["free_questions_remaining"] == auth["free_questions_remaining"] == 3
    assert billing["credit_balance"] == auth["credit_balance"] == -1
    admin_headers = {"Authorization": _headers(user, role="admin")["Authorization"], "X-API-Key": "gol-admin-key"}
    summary = client.get("/api/admin/billing/summary", headers=admin_headers).get_json()["gol"]
    assert summary == {
        "gross_cents": 2000,
        "refunded_cents": 1000,
        "currency": "usd",
        "other_currency_grants": 1,
        "credits_granted": 7,
        "credits_reversed": 0,
        "credits_spent": 0,
        "credits_outstanding": 4,
        "negative_balances": 1,
    }


def test_account_export_and_delete_forfeit_balance_and_count_rows(app, client):
    user = _user()
    db.session.add(
        GolCreditLedger(
            user_account_id=user.id,
            bucket="prepaid",
            kind="grant",
            delta=5,
            idempotency_key="grant:delete",
            stripe_session_id="cs_delete_gol",
            stripe_payment_intent_id="pi_delete_gol",
            pack_id="gol_starter",
            amount_paid_cents=2000,
            currency="usd",
        )
    )
    db.session.commit()
    exported = client.get("/api/account/export", headers=_headers(user)).get_json()
    assert exported["gol_credit_ledger"][0]["delta"] == 5
    response = client.post("/api/account/delete", json={"confirm": "DELETE"}, headers=_headers(user))
    assert response.status_code == 200
    counts = response.get_json()["counts"]
    assert counts["deleted"]["gol_credit_ledger"] == 1
    assert counts["forfeited_credits"] == 5
    assert GolCreditLedger.query.count() == 0
    event = ProductEvent.query.filter_by(event_name="gol_credits_forfeited").one()
    assert event.user_email is None
    assert event.props == {"credits": 5}


def test_account_delete_marks_paid_gol_checkout_complete_without_subscription_or_grant(app, client, monkeypatch):
    user = _user()
    _checkout(user, "cs_delete_pending")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "billing_secret_test_placeholder")
    monkeypatch.setattr(
        stripe.checkout.Session,
        "expire",
        Mock(side_effect=stripe.InvalidRequestError("Checkout complete", param=None)),
    )
    monkeypatch.setattr(
        stripe.checkout.Session,
        "retrieve",
        Mock(return_value={"status": "complete", "mode": "payment", "payment_status": "paid"}),
    )
    cancel = Mock()
    monkeypatch.setattr(stripe.Subscription, "cancel", cancel)
    response = client.post("/api/account/delete", json={"confirm": "DELETE"}, headers=_headers(user))
    assert response.status_code == 200
    cancel.assert_not_called()
    assert GolCreditLedger.query.count() == 0


def test_integrity_error_loser_path_returns_winning_debit(app, monkeypatch):
    """SQLite cannot exercise row locking; simulate the savepoint loser after a concurrent winner."""
    _enable(monkeypatch)
    user = _user()
    question_hash = "a" * 64
    real_begin_nested = db.session.begin_nested
    inserted = False

    def race_begin_nested(*args, **kwargs):
        nonlocal inserted
        if not inserted:
            inserted = True
            db.session.execute(
                GolCreditLedger.__table__.insert().values(
                    user_account_id=user.id,
                    bucket="free_allowance",
                    kind="debit",
                    delta=-1,
                    idempotency_key=f"q:{user.id}:race_msg:1",
                    client_msg_id="race_msg",
                    attempt=1,
                    note=question_hash,
                )
            )
        return real_begin_nested(*args, **kwargs)

    monkeypatch.setattr(db.session, "begin_nested", race_begin_nested)
    result = reserve_question(user, "race_msg", question_hash=question_hash)
    assert result["debited"] is False
    assert result["attempt"] == 1
    assert inserted is True
    assert GolCreditLedger.query.filter_by(kind="debit").count() == 1
