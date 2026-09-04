"""Authentication and Scout Pro access tests for GOL compute routes."""

from datetime import datetime

import pytest
from flask import Flask
from src.auth import issue_user_token
from src.extensions import limiter
from src.models.billing import BillingSubscription
from src.models.league import UserAccount, db

GOL_POSTS = (
    ("/api/gol/chat", {"message": "Who is in form?", "client_msg_id": "gol-access-1"}),
    ("/api/gol/export-pdf", {"messages": [{"role": "user", "content": "Who is in form?"}]}),
)


class _StubGolService:
    def __init__(self, session_id=None, model_override=None):
        self.session_id = session_id
        self.model_override = model_override

    def chat(self, message, history, session_id):
        yield {"event": "done", "data": {"message": message, "session_id": session_id}}

    def get_suggestions(self):
        return ["A free suggestion"]


@pytest.fixture
def app(monkeypatch):
    from src.routes.gol import gol_bp
    from src.services import gol_service, pdf_renderer

    for name in (
        "BILLING_ENABLED",
        "SCOUT_PRO_LAUNCHED_AT",
        "SCOUT_PRO_GRANDFATHER_UNTIL",
        "STRIPE_SECRET_KEY",
        "STRIPE_WEBHOOK_SECRET",
        "STRIPE_PRICE_SCOUT_PRO_MONTHLY",
        "STRIPE_PRICE_SCOUT_PRO_YEARLY",
        "STRIPE_PRICE_GOL_STARTER",
        "STRIPE_PRICE_GOL_TOPUP",
        "GOL_STARTER_CREDITS",
        "GOL_TOPUP_CREDITS",
        "GOL_FREE_ALLOWANCE",
    ):
        monkeypatch.delenv(name, raising=False)

    monkeypatch.setattr(gol_service, "GolService", _StubGolService)
    monkeypatch.setattr(
        pdf_renderer,
        "render_gol_chat_pdf",
        lambda messages: (b"%PDF-stub", "gol-chat.pdf"),
    )

    test_app = Flask(__name__)
    test_app.config.update(
        TESTING=True,
        SECRET_KEY="gol-access-test-secret",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        RATELIMIT_ENABLED=False,
    )
    db.init_app(test_app)
    limiter.init_app(test_app)
    test_app.register_blueprint(gol_bp, url_prefix="/api")

    with test_app.app_context():
        db.create_all()
        yield test_app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def _add_user(*, email="gol@example.com", created_at=None):
    user = UserAccount(
        email=email,
        display_name="GOL User",
        display_name_lower=email,
        display_name_confirmed=True,
        created_at=created_at or datetime(2026, 9, 2),
        scout_tier="free",
    )
    db.session.add(user)
    db.session.commit()
    return user


def _headers(user, *, role="user"):
    token = issue_user_token(user.email, role=role)["token"]
    return {"Authorization": f"Bearer {token}"}


def _add_subscription(user):
    subscription = BillingSubscription(
        scope_type="user",
        scope_id=user.id,
        product_code="scout_pro",
        price_code="monthly",
        purchaser_user_id=user.id,
        stripe_customer_id=f"customer_test_{user.id}",
        stripe_subscription_id=f"subscription_test_{user.id}",
        stripe_price_id="price_test_monthly",
        status="active",
        unit_amount=900,
        currency="usd",
        interval="month",
    )
    db.session.add(subscription)
    db.session.commit()


def _assert_passed_gate(response, path):
    assert response.status_code == 200
    if path.endswith("/chat"):
        assert response.mimetype == "text/event-stream"
        assert "event: done" in response.get_data(as_text=True)
    else:
        assert response.mimetype == "application/pdf"
        assert response.data == b"%PDF-stub"


@pytest.mark.parametrize(("path", "payload"), GOL_POSTS)
@pytest.mark.parametrize("billing_enabled", (False, True), ids=("dark", "lit"))
def test_anonymous_compute_routes_require_login(client, monkeypatch, path, payload, billing_enabled):
    if billing_enabled:
        monkeypatch.setenv("BILLING_ENABLED", "true")

    response = client.post(path, json=payload)

    try:
        assert response.status_code == 401
        assert response.get_json() == {"error": "missing auth token"}
    finally:
        response.close()


@pytest.mark.parametrize(("path", "payload"), GOL_POSTS)
def test_signed_in_user_passes_when_billing_is_off(app, client, path, payload):
    user = _add_user()

    response = client.post(path, json=payload, headers=_headers(user))

    try:
        _assert_passed_gate(response, path)
    finally:
        response.close()


@pytest.mark.parametrize(("path", "payload"), GOL_POSTS)
def test_free_user_uses_allowance_when_billing_is_on(app, client, monkeypatch, path, payload):
    monkeypatch.setenv("BILLING_ENABLED", "true")
    user = _add_user()

    response = client.post(path, json=payload, headers=_headers(user))

    try:
        _assert_passed_gate(response, path)
    finally:
        response.close()


@pytest.mark.parametrize(("path", "payload"), GOL_POSTS)
@pytest.mark.parametrize("entitlement", ("subscription", "grandfather"))
def test_entitled_user_passes_when_billing_is_on(app, client, monkeypatch, path, payload, entitlement):
    monkeypatch.setenv("BILLING_ENABLED", "true")
    if entitlement == "grandfather":
        monkeypatch.setenv("SCOUT_PRO_LAUNCHED_AT", "2026-09-01T00:00:00Z")
        monkeypatch.setenv("SCOUT_PRO_GRANDFATHER_UNTIL", "2099-10-01T00:00:00Z")
        user = _add_user(created_at=datetime(2026, 8, 31))
    else:
        user = _add_user()
        _add_subscription(user)

    response = client.post(path, json=payload, headers=_headers(user))

    try:
        _assert_passed_gate(response, path)
    finally:
        response.close()


@pytest.mark.parametrize(("path", "payload"), GOL_POSTS)
def test_admin_without_subscription_passes_when_billing_is_on(app, client, monkeypatch, path, payload):
    monkeypatch.setenv("BILLING_ENABLED", "true")
    user = _add_user(email="admin@example.com")

    response = client.post(path, json=payload, headers=_headers(user, role="admin"))

    try:
        _assert_passed_gate(response, path)
    finally:
        response.close()


def test_suggestions_remain_anonymous_and_free(client, monkeypatch):
    monkeypatch.setenv("BILLING_ENABLED", "true")

    response = client.get("/api/gol/suggestions")

    assert response.status_code == 200
    assert response.get_json() == {"suggestions": ["A free suggestion"]}
