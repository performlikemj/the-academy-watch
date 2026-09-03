"""S3-P1 Scout Pro entitlement tests (derivation, gates, /auth/me fields).

Subscriptions are seeded as `BillingSubscription` rows directly — no Stripe network,
no webhook. All gates must be no-ops while `BILLING_ENABLED` is unset (D1).
"""

from datetime import UTC, datetime, timedelta

import pytest
from flask import Flask
from src.auth import issue_user_token
from src.extensions import limiter
from src.models.billing import BillingSubscription
from src.models.league import UserAccount, db
from src.services.scout_entitlements import (
    FREE_LIST_LIMIT,
    is_pro,
    list_limit_for,
    scout_entitlements,
)

LAUNCHED_AT = "2026-09-01T00:00:00Z"
LAUNCHED_NAIVE = datetime(2026, 9, 1)
GRANDFATHER_UNTIL = "2099-01-01T00:00:00Z"
UNTIL_NAIVE = datetime(2099, 1, 1)
PRE_LAUNCH = datetime(2026, 8, 15)


@pytest.fixture
def entitlements_app(monkeypatch):
    """Minimal app with the scout + auth blueprints; billing env cleared (dark)."""
    from src.routes.auth_routes import auth_bp
    from src.routes.scout import scout_bp

    for name in (
        "BILLING_ENABLED",
        "STRIPE_SECRET_KEY",
        "STRIPE_WEBHOOK_SECRET",
        "STRIPE_PRICE_SCOUT_PRO_MONTHLY",
        "STRIPE_PRICE_SCOUT_PRO_YEARLY",
        "STRIPE_PRICE_CLUB_BUNDLE_MONTHLY",
        "STRIPE_PRICE_CLUB_BUNDLE_YEARLY",
        "SCOUT_PRO_LAUNCHED_AT",
        "SCOUT_PRO_GRANDFATHER_UNTIL",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SKIP_API_HANDSHAKE", "1")
    monkeypatch.setenv("API_USE_STUB_DATA", "true")

    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SECRET_KEY="scout-entitlement-secret",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        RATELIMIT_ENABLED=False,
    )
    db.init_app(app)
    limiter.init_app(app)
    app.register_blueprint(scout_bp, url_prefix="/api")
    app.register_blueprint(auth_bp, url_prefix="/api")

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(entitlements_app):
    return entitlements_app.test_client()


def _add_user(email="scout@example.com", *, created_at=None, scout_tier="free"):
    user = UserAccount(
        email=email,
        display_name="Test Scout",
        display_name_lower=email,
        display_name_confirmed=True,
        scout_tier=scout_tier,
        created_at=created_at,
    )
    db.session.add(user)
    db.session.commit()
    return user


def _headers(user):
    return {"Authorization": f"Bearer {issue_user_token(user.email)['token']}"}


def _subscription(
    user, *, status="active", product_code="scout_pro", stripe_subscription_id="sub_scout_1", **overrides
):
    row = BillingSubscription(
        scope_type="user",
        scope_id=user.id,
        product_code=product_code,
        price_code="monthly",
        purchaser_user_id=user.id,
        stripe_customer_id=f"cus_{user.id}",
        stripe_subscription_id=stripe_subscription_id,
        stripe_price_id="price_test_monthly",
        status=status,
        unit_amount=900,
        currency="usd",
        interval="month",
        current_period_start=datetime(2026, 9, 1),
        current_period_end=datetime(2026, 10, 1),
    )
    for key, value in overrides.items():
        setattr(row, key, value)
    db.session.add(row)
    db.session.commit()
    return row


def _enable_billing(monkeypatch):
    monkeypatch.setenv("BILLING_ENABLED", "true")
    monkeypatch.setenv("SCOUT_PRO_LAUNCHED_AT", LAUNCHED_AT)
    monkeypatch.setenv("SCOUT_PRO_GRANDFATHER_UNTIL", GRANDFATHER_UNTIL)


def _pin_max_lists(monkeypatch, value=10):
    """Pin MAX_FOLLOW_LISTS so tests do not depend on the ambient environment."""
    import src.routes.scout as scout_module

    monkeypatch.setattr(scout_module, "MAX_FOLLOW_LISTS", value)
    return value


# --------------------------------------------------------------------------- #
# Derivation per source
# --------------------------------------------------------------------------- #


class TestDerivation:
    def test_billing_disabled_leaves_everything_open(self, entitlements_app, monkeypatch):
        max_lists = _pin_max_lists(monkeypatch)
        user = _add_user()
        payload = scout_entitlements(user)
        assert payload["billing_enabled"] is False
        assert payload["tier"] == "free"
        assert payload["source"] == "billing_disabled"
        assert payload["features"] == {"csv_export": True, "custom_lists_max": max_lists}

    def test_billing_disabled_keeps_projection_tier(self, entitlements_app):
        user = _add_user(scout_tier="pro")
        payload = scout_entitlements(user)
        assert payload["tier"] == "pro"
        assert payload["source"] == "billing_disabled"
        assert payload["features"]["csv_export"] is True

    def test_active_subscription_is_pro(self, entitlements_app, monkeypatch):
        monkeypatch.setenv("BILLING_ENABLED", "true")
        max_lists = _pin_max_lists(monkeypatch)
        user = _add_user()
        _subscription(user)
        payload = scout_entitlements(user)
        assert payload["billing_enabled"] is True
        assert payload["tier"] == "pro"
        assert payload["source"] == "subscription"
        assert payload["subscription_status"] == "active"
        assert payload["current_period_end"] == "2026-10-01T00:00:00"
        assert payload["cancel_at_period_end"] is False
        assert payload["features"] == {"csv_export": True, "custom_lists_max": max_lists}
        assert is_pro(user) is True
        assert list_limit_for(user) == max_lists

    def test_past_due_subscription_still_entitles(self, entitlements_app, monkeypatch):
        monkeypatch.setenv("BILLING_ENABLED", "true")
        user = _add_user()
        _subscription(user, status="past_due")
        assert scout_entitlements(user)["tier"] == "pro"

    def test_cancel_at_period_end_surfaces_while_active(self, entitlements_app, monkeypatch):
        monkeypatch.setenv("BILLING_ENABLED", "true")
        user = _add_user()
        _subscription(user, cancel_at_period_end=True)
        payload = scout_entitlements(user)
        assert payload["tier"] == "pro"
        assert payload["cancel_at_period_end"] is True

    def test_canceled_subscription_is_free(self, entitlements_app, monkeypatch):
        monkeypatch.setenv("BILLING_ENABLED", "true")
        user = _add_user()
        _subscription(user, status="canceled")
        payload = scout_entitlements(user)
        assert payload["tier"] == "free"
        assert payload["source"] == "none"
        assert payload["features"] == {"csv_export": False, "custom_lists_max": FREE_LIST_LIMIT}
        assert is_pro(user) is False
        assert list_limit_for(user) == FREE_LIST_LIMIT

    def test_other_product_does_not_entitle(self, entitlements_app, monkeypatch):
        monkeypatch.setenv("BILLING_ENABLED", "true")
        user = _add_user()
        _subscription(user, product_code="club_bundle", stripe_subscription_id="sub_club_1")
        assert scout_entitlements(user)["source"] == "none"

    def test_grandfathered_pre_launch_account_is_pro(self, entitlements_app, monkeypatch):
        monkeypatch.setenv("BILLING_ENABLED", "true")
        monkeypatch.setenv("SCOUT_PRO_LAUNCHED_AT", LAUNCHED_AT)
        monkeypatch.setenv("SCOUT_PRO_GRANDFATHER_UNTIL", GRANDFATHER_UNTIL)
        max_lists = _pin_max_lists(monkeypatch)
        user = _add_user(created_at=PRE_LAUNCH)
        payload = scout_entitlements(user, now=datetime(2026, 9, 3))
        assert payload["tier"] == "pro"
        assert payload["source"] == "grandfather"
        assert payload["grandfathered_until"] == "2099-01-01T00:00:00"
        assert payload["features"]["csv_export"] is True
        assert payload["features"]["custom_lists_max"] == max_lists

    def test_created_exactly_at_launch_is_not_grandfathered(self, entitlements_app, monkeypatch):
        monkeypatch.setenv("BILLING_ENABLED", "true")
        monkeypatch.setenv("SCOUT_PRO_LAUNCHED_AT", LAUNCHED_AT)
        monkeypatch.setenv("SCOUT_PRO_GRANDFATHER_UNTIL", GRANDFATHER_UNTIL)
        user = _add_user(created_at=LAUNCHED_NAIVE)
        assert scout_entitlements(user, now=datetime(2026, 9, 3))["source"] == "none"

    def test_now_exactly_at_until_is_not_grandfathered(self, entitlements_app, monkeypatch):
        monkeypatch.setenv("BILLING_ENABLED", "true")
        monkeypatch.setenv("SCOUT_PRO_LAUNCHED_AT", LAUNCHED_AT)
        monkeypatch.setenv("SCOUT_PRO_GRANDFATHER_UNTIL", GRANDFATHER_UNTIL)
        user = _add_user(created_at=PRE_LAUNCH)
        assert scout_entitlements(user, now=UNTIL_NAIVE - timedelta(seconds=1))["source"] == "grandfather"
        assert scout_entitlements(user, now=UNTIL_NAIVE)["source"] == "none"

    def test_aware_inputs_are_normalised_to_naive_utc(self, entitlements_app, monkeypatch):
        monkeypatch.setenv("BILLING_ENABLED", "true")
        monkeypatch.setenv("SCOUT_PRO_LAUNCHED_AT", "2026-09-01T02:00:00+02:00")  # == 00:00 UTC
        monkeypatch.setenv("SCOUT_PRO_GRANDFATHER_UNTIL", "2099-01-01T01:00:00+01:00")  # == 00:00 UTC
        # Aware created_at 30 minutes AFTER the (normalised) launch instant.
        user_after = _add_user(email="after@example.com", created_at=datetime(2026, 9, 1, 0, 30, tzinfo=UTC))
        assert scout_entitlements(user_after, now=datetime(2026, 9, 3))["source"] == "none"
        # Naive created_at 30 minutes BEFORE the (normalised) launch instant.
        user_before = _add_user(email="before@example.com", created_at=datetime(2026, 8, 31, 23, 30))
        payload = scout_entitlements(user_before, now=datetime(2026, 9, 3))
        assert payload["source"] == "grandfather"
        assert payload["grandfathered_until"] == "2099-01-01T00:00:00"

    def test_timezone_less_envs_disable_grandfathering(self, entitlements_app, monkeypatch):
        monkeypatch.setenv("BILLING_ENABLED", "true")
        monkeypatch.setenv("SCOUT_PRO_LAUNCHED_AT", "2026-09-01T00:00:00")
        monkeypatch.setenv("SCOUT_PRO_GRANDFATHER_UNTIL", "2099-01-01T00:00:00")
        user = _add_user(created_at=PRE_LAUNCH)
        assert scout_entitlements(user, now=datetime(2026, 9, 3))["source"] == "none"

    def test_malformed_envs_disable_grandfathering_without_raising(self, entitlements_app, monkeypatch):
        monkeypatch.setenv("BILLING_ENABLED", "true")
        monkeypatch.setenv("SCOUT_PRO_LAUNCHED_AT", "not-a-date")
        monkeypatch.setenv("SCOUT_PRO_GRANDFATHER_UNTIL", "")
        user = _add_user(created_at=PRE_LAUNCH)
        assert scout_entitlements(user, now=datetime(2026, 9, 3))["source"] == "none"

    def test_post_launch_account_is_never_grandfathered(self, entitlements_app, monkeypatch):
        monkeypatch.setenv("BILLING_ENABLED", "true")
        monkeypatch.setenv("SCOUT_PRO_LAUNCHED_AT", LAUNCHED_AT)
        monkeypatch.setenv("SCOUT_PRO_GRANDFATHER_UNTIL", GRANDFATHER_UNTIL)
        user = _add_user()  # created now, i.e. after the 2026-09-01 launch
        assert scout_entitlements(user, now=datetime(2026, 9, 3))["source"] == "none"

    def test_entitlements_tolerate_a_missing_account(self, entitlements_app, monkeypatch):
        monkeypatch.setenv("BILLING_ENABLED", "true")
        payload = scout_entitlements(None)
        assert payload["tier"] == "free"
        assert payload["source"] == "none"


# --------------------------------------------------------------------------- #
# CSV export gate
# --------------------------------------------------------------------------- #


class TestCsvExportGate:
    def test_free_account_gets_scout_pro_403(self, client, monkeypatch):
        monkeypatch.setenv("BILLING_ENABLED", "true")
        user = _add_user()
        resp = client.get("/api/scout/export.csv", headers=_headers(user))
        assert resp.status_code == 403
        assert resp.get_json() == {"error": "scout_pro_required", "feature": "csv_export", "upgrade_path": "/pricing"}

    def test_pro_account_exports(self, client, monkeypatch):
        monkeypatch.setenv("BILLING_ENABLED", "true")
        user = _add_user()
        _subscription(user)
        resp = client.get("/api/scout/export.csv", headers=_headers(user))
        assert resp.status_code == 200
        assert resp.data.startswith(b"player_id")

    def test_grandfathered_account_exports(self, client, monkeypatch):
        _enable_billing(monkeypatch)
        user = _add_user(created_at=PRE_LAUNCH)
        resp = client.get("/api/scout/export.csv", headers=_headers(user))
        assert resp.status_code == 200

    def test_dark_rail_keeps_export_open_for_free_accounts(self, client):
        user = _add_user()
        resp = client.get("/api/scout/export.csv", headers=_headers(user))
        assert resp.status_code == 200
        assert resp.data.startswith(b"player_id")


# --------------------------------------------------------------------------- #
# Custom-list gate
# --------------------------------------------------------------------------- #


class TestListLimit:
    def test_free_account_fourth_list_is_403(self, client, monkeypatch):
        monkeypatch.setenv("BILLING_ENABLED", "true")
        _pin_max_lists(monkeypatch)
        user = _add_user()
        headers = _headers(user)
        for i in range(FREE_LIST_LIMIT):
            assert client.post("/api/scout/lists", json={"name": f"List {i}"}, headers=headers).status_code == 201
        resp = client.post("/api/scout/lists", json={"name": "One too many"}, headers=headers)
        assert resp.status_code == 403
        assert resp.get_json() == {
            "error": "scout_pro_required",
            "feature": "custom_lists",
            "upgrade_path": "/pricing",
        }

    def test_pro_account_proceeds_to_the_existing_ten_cap_409(self, client, monkeypatch):
        import src.routes.scout as scout_module

        monkeypatch.setenv("BILLING_ENABLED", "true")
        user = _add_user()
        _subscription(user)
        headers = _headers(user)
        for i in range(scout_module.MAX_FOLLOW_LISTS):
            resp = client.post("/api/scout/lists", json={"name": f"Pro list {i}"}, headers=headers)
            assert resp.status_code == 201, resp.get_json()
        resp = client.post("/api/scout/lists", json={"name": "Over the cap"}, headers=headers)
        assert resp.status_code == 409
        assert "list limit reached" in resp.get_json()["error"]

    def test_dark_rail_list_behaviour_is_unchanged(self, client, monkeypatch):
        import src.routes.scout as scout_module

        monkeypatch.setattr(scout_module, "MAX_FOLLOW_LISTS", 1)
        user = _add_user()
        headers = _headers(user)
        assert client.post("/api/scout/lists", json={"name": "One"}, headers=headers).status_code == 201
        resp = client.post("/api/scout/lists", json={"name": "Two"}, headers=headers)
        assert resp.status_code == 409
        assert "list limit reached" in resp.get_json()["error"]


# --------------------------------------------------------------------------- #
# /auth/me fields
# --------------------------------------------------------------------------- #


class TestAuthMeFields:
    def test_dark_auth_me_exposes_open_features(self, client, monkeypatch):
        max_lists = _pin_max_lists(monkeypatch)
        user = _add_user()
        data = client.get("/api/auth/me", headers=_headers(user)).get_json()
        assert data["scout_tier"] == "free"
        assert data["scout_pro"] == {
            "enabled": False,
            "tier": "free",
            "features": {"csv_export": True, "custom_lists_max": max_lists},
        }

    def test_dark_auth_me_keeps_projection_tier(self, client):
        user = _add_user(scout_tier="pro")
        data = client.get("/api/auth/me", headers=_headers(user)).get_json()
        assert data["scout_tier"] == "pro"
        assert data["scout_pro"]["enabled"] is False
        assert data["scout_pro"]["features"]["csv_export"] is True

    def test_lit_auth_me_derives_pro_from_subscription(self, client, monkeypatch):
        monkeypatch.setenv("BILLING_ENABLED", "true")
        user = _add_user()  # projection column still "free" — derivation wins
        _subscription(user)
        max_lists = _pin_max_lists(monkeypatch)
        data = client.get("/api/auth/me", headers=_headers(user)).get_json()
        assert data["scout_tier"] == "pro"
        assert data["scout_pro"] == {
            "enabled": True,
            "tier": "pro",
            "features": {"csv_export": True, "custom_lists_max": max_lists},
        }

    def test_lit_auth_me_free_account_is_gated(self, client, monkeypatch):
        monkeypatch.setenv("BILLING_ENABLED", "true")
        user = _add_user()
        data = client.get("/api/auth/me", headers=_headers(user)).get_json()
        assert data["scout_tier"] == "free"
        assert data["scout_pro"] == {
            "enabled": True,
            "tier": "free",
            "features": {"csv_export": False, "custom_lists_max": FREE_LIST_LIMIT},
        }


# --------------------------------------------------------------------------- #
# GET /api/scout/entitlements
# --------------------------------------------------------------------------- #


class TestEntitlementsEndpoint:
    def test_dark_returns_neutral_404_for_anonymous_probe(self, client):
        assert client.get("/api/scout/entitlements").status_code == 404

    def test_dark_returns_neutral_404_even_authenticated(self, client):
        user = _add_user()
        assert client.get("/api/scout/entitlements", headers=_headers(user)).status_code == 404

    def test_lit_returns_entitlements(self, client, monkeypatch):
        monkeypatch.setenv("BILLING_ENABLED", "true")
        user = _add_user()
        _subscription(user)
        resp = client.get("/api/scout/entitlements", headers=_headers(user))
        assert resp.status_code == 200
        payload = resp.get_json()["entitlements"]
        assert payload["tier"] == "pro"
        assert payload["source"] == "subscription"
        assert payload["features"]["csv_export"] is True

    def test_lit_still_requires_auth(self, client, monkeypatch):
        monkeypatch.setenv("BILLING_ENABLED", "true")
        assert client.get("/api/scout/entitlements").status_code == 401
