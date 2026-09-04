"""Scout Pro entitlement derivation and ungated data-route regressions."""

from datetime import UTC, datetime

import pytest
from flask import Flask
from src.auth import issue_user_token
from src.extensions import limiter
from src.models.billing import BillingSubscription
from src.models.follow import FollowList
from src.models.league import UserAccount, db
from src.services.scout_entitlements import is_pro, scout_entitlements


@pytest.fixture
def app(monkeypatch):
    from src.routes.auth_routes import auth_bp
    from src.routes.scout import scout_bp

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

    test_app = Flask(__name__)
    test_app.config.update(
        TESTING=True,
        SECRET_KEY="scout-entitlements-test-secret",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        RATELIMIT_ENABLED=False,
    )
    db.init_app(test_app)
    limiter.init_app(test_app)
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


def _add_user(*, email="scout@example.com", created_at=None, scout_tier="free"):
    user = UserAccount(
        email=email,
        display_name="Test Scout",
        display_name_lower=email,
        display_name_confirmed=True,
        created_at=created_at or datetime(2026, 1, 1),
        scout_tier=scout_tier,
    )
    db.session.add(user)
    db.session.commit()
    return user


def _headers(user, *, role="user"):
    token = issue_user_token(user.email, role=role)["token"]
    return {"Authorization": f"Bearer {token}"}


def _add_subscription(user, *, status="active", current_period_end=None, cancel_at_period_end=False):
    row = BillingSubscription(
        scope_type="user",
        scope_id=user.id,
        product_code="scout_pro",
        price_code="monthly",
        purchaser_user_id=user.id,
        stripe_customer_id=f"customer_test_{user.id}",
        stripe_subscription_id=f"subscription_test_{user.id}_{status}",
        stripe_price_id="price_test_monthly",
        status=status,
        unit_amount=900,
        currency="usd",
        interval="month",
        current_period_end=current_period_end,
        cancel_at_period_end=cancel_at_period_end,
    )
    db.session.add(row)
    db.session.commit()
    return row


def _enable_billing(monkeypatch):
    monkeypatch.setenv("BILLING_ENABLED", "true")


def _enable_grandfathering(monkeypatch):
    monkeypatch.setenv("SCOUT_PRO_LAUNCHED_AT", "2026-09-01T00:00:00Z")
    monkeypatch.setenv("SCOUT_PRO_GRANDFATHER_UNTIL", "2026-10-01T00:00:00+00:00")


def test_billing_disabled_preserves_projection_and_ungates_gol(app):
    user = _add_user(scout_tier="pro")

    result = scout_entitlements(user)

    assert result == {
        "billing_enabled": False,
        "tier": "pro",
        "source": "billing_disabled",
        "subscription_status": None,
        "current_period_end": None,
        "cancel_at_period_end": False,
        "grandfathered_until": None,
        "features": {"gol_chat": True, "free_questions_remaining": 3, "credit_balance": 0},
    }
    assert is_pro(user) is True


def test_active_subscription_is_entitlement_truth(app, monkeypatch):
    _enable_billing(monkeypatch)
    period_end = datetime(2026, 10, 2, 3, 4, 5)
    user = _add_user(scout_tier="free")
    _add_subscription(user, status="past_due", current_period_end=period_end, cancel_at_period_end=True)

    result = scout_entitlements(user)

    assert result == {
        "billing_enabled": True,
        "tier": "pro",
        "source": "subscription",
        "subscription_status": "past_due",
        "current_period_end": "2026-10-02T03:04:05",
        "cancel_at_period_end": True,
        "grandfathered_until": None,
        "features": {"gol_chat": True, "free_questions_remaining": 3, "credit_balance": 0},
    }


def test_prelaunch_account_is_grandfathered_before_window_end(app, monkeypatch):
    _enable_billing(monkeypatch)
    _enable_grandfathering(monkeypatch)
    user = _add_user(created_at=datetime(2026, 8, 31, 23, 59, 59))

    result = scout_entitlements(user, now=datetime(2026, 9, 30, 23, 59, 59, tzinfo=UTC))

    assert result == {
        "billing_enabled": True,
        "tier": "pro",
        "source": "grandfather",
        "subscription_status": None,
        "current_period_end": None,
        "cancel_at_period_end": False,
        "grandfathered_until": "2026-10-01T00:00:00",
        "features": {"gol_chat": True, "free_questions_remaining": 3, "credit_balance": 0},
    }


@pytest.mark.parametrize(
    ("created_at", "now"),
    (
        (datetime(2026, 9, 1), datetime(2026, 9, 15)),
        (datetime(2026, 8, 31, 23, 59, 59), datetime(2026, 10, 1)),
    ),
)
def test_grandfather_boundaries_are_exclusive(app, monkeypatch, created_at, now):
    _enable_billing(monkeypatch)
    _enable_grandfathering(monkeypatch)
    user = _add_user(created_at=created_at)

    result = scout_entitlements(user, now=now)

    assert result == {
        "billing_enabled": True,
        "tier": "free",
        "source": "none",
        "subscription_status": None,
        "current_period_end": None,
        "cancel_at_period_end": False,
        "grandfathered_until": None,
        "features": {"gol_chat": True, "free_questions_remaining": 3, "credit_balance": 0},
    }


@pytest.mark.parametrize(
    ("launched_at", "grandfather_until"),
    (
        ("not-a-date", "2026-10-01T00:00:00Z"),
        ("2026-09-01T00:00:00", "2026-10-01T00:00:00Z"),
        ("2026-09-01T00:00:00Z", "2026-10-01T00:00:00"),
    ),
)
def test_invalid_or_timezone_less_grandfather_envs_are_ignored(app, monkeypatch, launched_at, grandfather_until):
    _enable_billing(monkeypatch)
    monkeypatch.setenv("SCOUT_PRO_LAUNCHED_AT", launched_at)
    monkeypatch.setenv("SCOUT_PRO_GRANDFATHER_UNTIL", grandfather_until)
    user = _add_user(created_at=datetime(2026, 8, 1))

    result = scout_entitlements(user, now=datetime(2026, 9, 15))

    assert result["tier"] == "free"
    assert result["source"] == "none"
    assert result["features"] == {"gol_chat": True, "free_questions_remaining": 3, "credit_balance": 0}


def test_csv_export_allows_free_user_when_billing_enabled(app, client, monkeypatch):
    _enable_billing(monkeypatch)
    user = _add_user()

    response = client.get("/api/scout/export.csv", headers=_headers(user))

    assert response.status_code == 200
    assert response.mimetype == "text/csv"


def test_free_user_can_create_fourth_custom_list_when_billing_enabled(app, client, monkeypatch):
    _enable_billing(monkeypatch)
    user = _add_user()
    db.session.add_all(
        [FollowList(user_account_id=user.id, name=f"List {number}", is_default=False) for number in range(1, 4)]
    )
    db.session.commit()

    response = client.post("/api/scout/lists", json={"name": "List 4"}, headers=_headers(user))

    assert response.status_code == 201
    assert FollowList.query.filter_by(user_account_id=user.id, is_default=False).count() == 4


def test_free_user_still_reaches_existing_ten_list_cap(app, client, monkeypatch):
    _enable_billing(monkeypatch)
    user = _add_user()
    headers = _headers(user)

    for number in range(1, 11):
        response = client.post("/api/scout/lists", json={"name": f"List {number}"}, headers=headers)
        assert response.status_code == 201

    response = client.post("/api/scout/lists", json={"name": "List 11"}, headers=headers)
    assert response.status_code == 409
    assert response.get_json() == {"error": "list limit reached (10)"}


def test_auth_me_includes_dark_scout_fields(app, client):
    user = _add_user(scout_tier="pro")

    response = client.get("/api/auth/me", headers=_headers(user))

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["scout_tier"] == "pro"
    assert payload["scout_pro"] == {
        "enabled": False,
        "tier": "pro",
        "features": {"gol_chat": True, "free_questions_remaining": 3, "credit_balance": 0},
    }


def test_auth_me_includes_lit_subscription_fields(app, client, monkeypatch):
    _enable_billing(monkeypatch)
    user = _add_user(scout_tier="free")
    _add_subscription(user)

    response = client.get("/api/auth/me", headers=_headers(user))

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["scout_tier"] == "pro"
    assert payload["scout_pro"] == {
        "enabled": True,
        "tier": "pro",
        "features": {"gol_chat": True, "free_questions_remaining": 3, "credit_balance": 0},
    }


def test_admin_entitlement_payloads_enable_gol_when_billing_is_lit(app, client, monkeypatch):
    _enable_billing(monkeypatch)
    user = _add_user(email="admin@example.com", scout_tier="free")
    headers = _headers(user, role="admin")

    auth_me = client.get("/api/auth/me", headers=headers)
    entitlements = client.get("/api/scout/entitlements", headers=headers)

    assert auth_me.status_code == 200
    assert auth_me.get_json()["scout_pro"] == {
        "enabled": True,
        "tier": "free",
        "features": {"gol_chat": True, "free_questions_remaining": 3, "credit_balance": 0},
    }
    assert entitlements.status_code == 200
    assert entitlements.get_json()["entitlements"]["features"] == {
        "gol_chat": True,
        "free_questions_remaining": 3,
        "credit_balance": 0,
    }


def test_entitlements_route_is_neutral_404_while_dark_even_anonymously(client):
    response = client.get("/api/scout/entitlements")

    assert response.status_code == 404
    assert response.get_json() is None


def test_entitlements_route_returns_derived_payload_when_lit(app, client, monkeypatch):
    _enable_billing(monkeypatch)
    user = _add_user()

    response = client.get("/api/scout/entitlements", headers=_headers(user))

    assert response.status_code == 200
    assert response.get_json()["entitlements"]["features"] == {
        "gol_chat": True,
        "free_questions_remaining": 3,
        "credit_balance": 0,
    }
