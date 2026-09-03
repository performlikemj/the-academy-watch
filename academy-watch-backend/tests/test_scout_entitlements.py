"""S3-P1 Scout Pro entitlement derivation and route gates."""

from datetime import UTC, datetime

import pytest
from flask import Flask
from src.auth import issue_user_token
from src.extensions import limiter
from src.models.billing import BillingSubscription
from src.models.follow import Follow, FollowList
from src.models.league import UserAccount, db
from src.services.scout_entitlements import FREE_LIST_LIMIT, is_pro, list_limit_for, scout_entitlements

CUSTOM_LISTS_REQUIRED = {
    "error": "scout_pro_required",
    "feature": "custom_lists",
    "upgrade_path": "/pricing",
}


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


def _headers(user):
    token = issue_user_token(user.email)["token"]
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


def _add_custom_lists(user, count, *, include_default=False, with_follows=False):
    if include_default:
        db.session.add(FollowList(user_account_id=user.id, name="My Watchlist", is_default=True))
    lists = [
        FollowList(user_account_id=user.id, name=f"List {number}", is_default=False) for number in range(1, count + 1)
    ]
    db.session.add_all(lists)
    db.session.flush()
    follow_ids = []
    if with_follows:
        for number, follow_list in enumerate(lists, start=1):
            follow = Follow(
                list_id=follow_list.id,
                kind="geo",
                selector={"countries": [f"Country {number}"], "match": "playing_in"},
                label=f"Playing in: Country {number}",
            )
            db.session.add(follow)
            db.session.flush()
            follow_ids.append(follow.id)
    db.session.commit()
    return lists, follow_ids


def _enable_billing(monkeypatch):
    monkeypatch.setenv("BILLING_ENABLED", "true")


def _enable_grandfathering(monkeypatch):
    monkeypatch.setenv("SCOUT_PRO_LAUNCHED_AT", "2026-09-01T00:00:00Z")
    monkeypatch.setenv("SCOUT_PRO_GRANDFATHER_UNTIL", "2026-10-01T00:00:00+00:00")


def test_billing_disabled_preserves_projection_and_ungates_features(app, monkeypatch):
    import src.routes.scout as scout_module

    monkeypatch.setattr(scout_module, "MAX_FOLLOW_LISTS", 7)
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
        "features": {"csv_export": True, "custom_lists_max": 7},
    }
    assert is_pro(user) is True
    assert list_limit_for(user) == 7


def test_active_subscription_is_entitlement_truth(app, monkeypatch):
    _enable_billing(monkeypatch)
    period_end = datetime(2026, 10, 2, 3, 4, 5)
    user = _add_user(scout_tier="free")
    _add_subscription(user, status="past_due", current_period_end=period_end, cancel_at_period_end=True)

    result = scout_entitlements(user)

    assert result["tier"] == "pro"
    assert result["source"] == "subscription"
    assert result["subscription_status"] == "past_due"
    assert result["current_period_end"] == "2026-10-02T03:04:05"
    assert result["cancel_at_period_end"] is True
    assert result["grandfathered_until"] is None
    assert result["features"] == {"csv_export": True, "custom_lists_max": 10}


def test_prelaunch_account_is_grandfathered_before_window_end(app, monkeypatch):
    _enable_billing(monkeypatch)
    _enable_grandfathering(monkeypatch)
    user = _add_user(created_at=datetime(2026, 8, 31, 23, 59, 59))

    result = scout_entitlements(user, now=datetime(2026, 9, 30, 23, 59, 59, tzinfo=UTC))

    assert result["tier"] == "pro"
    assert result["source"] == "grandfather"
    assert result["grandfathered_until"] == "2026-10-01T00:00:00"
    assert result["features"]["csv_export"] is True


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

    assert result["tier"] == "free"
    assert result["source"] == "none"
    assert result["grandfathered_until"] is None


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
    assert result["features"] == {"csv_export": False, "custom_lists_max": FREE_LIST_LIMIT}


def test_csv_export_rejects_free_user_with_exact_shape(app, client, monkeypatch):
    _enable_billing(monkeypatch)
    user = _add_user()

    response = client.get("/api/scout/export.csv", headers=_headers(user))

    assert response.status_code == 403
    assert response.get_json() == {
        "error": "scout_pro_required",
        "feature": "csv_export",
        "upgrade_path": "/pricing",
    }


def test_csv_export_allows_subscribed_user(app, client, monkeypatch):
    _enable_billing(monkeypatch)
    user = _add_user()
    _add_subscription(user)

    response = client.get("/api/scout/export.csv", headers=_headers(user))

    assert response.status_code == 200
    assert response.mimetype == "text/csv"


def test_csv_export_allows_grandfathered_user(app, client, monkeypatch):
    _enable_billing(monkeypatch)
    _enable_grandfathering(monkeypatch)
    user = _add_user(created_at=datetime(2026, 8, 1))

    response = client.get("/api/scout/export.csv", headers=_headers(user))

    assert response.status_code == 200
    assert response.mimetype == "text/csv"


def test_default_list_does_not_consume_free_custom_list_entitlement(app, client, monkeypatch):
    _enable_billing(monkeypatch)
    user = _add_user()
    _add_custom_lists(user, FREE_LIST_LIMIT - 1, include_default=True)
    headers = _headers(user)

    response = client.post("/api/scout/lists", json={"name": "List 3"}, headers=headers)
    assert response.status_code == 201

    response = client.post("/api/scout/lists", json={"name": "List 4"}, headers=headers)
    assert response.status_code == 403
    assert response.get_json() == CUSTOM_LISTS_REQUIRED


def test_free_user_can_read_and_delete_over_limit_lists_but_cannot_mutate_them(app, client, monkeypatch):
    _enable_billing(monkeypatch)
    user = _add_user()
    lists, follow_ids = _add_custom_lists(user, 5, with_follows=True)
    headers = _headers(user)
    follow_payload = {
        "kind": "query",
        "selector": {"scout_args": {"position": "Attacker"}},
    }

    for index, follow_list in enumerate(lists):
        response = client.post(f"/api/scout/lists/{follow_list.id}/follows", json=follow_payload, headers=headers)
        if index < FREE_LIST_LIMIT:
            assert response.status_code == 201
        else:
            assert response.status_code == 403
            assert response.get_json() == CUSTOM_LISTS_REQUIRED

    listing = client.get("/api/scout/lists", headers=headers)
    assert listing.status_code == 200
    assert [row["id"] for row in listing.get_json()["lists"]] == [follow_list.id for follow_list in lists]

    assert (
        client.patch(f"/api/scout/lists/{lists[2].id}", json={"is_active": False}, headers=headers).status_code == 200
    )
    blocked_patch = client.patch(f"/api/scout/lists/{lists[3].id}", json={"is_active": False}, headers=headers)
    assert blocked_patch.status_code == 403
    assert blocked_patch.get_json() == CUSTOM_LISTS_REQUIRED

    allowed_remove = client.delete(f"/api/scout/lists/{lists[2].id}/follows/{follow_ids[2]}", headers=headers)
    assert allowed_remove.status_code == 200
    blocked_remove = client.delete(f"/api/scout/lists/{lists[3].id}/follows/{follow_ids[3]}", headers=headers)
    assert blocked_remove.status_code == 403
    assert blocked_remove.get_json() == CUSTOM_LISTS_REQUIRED

    delete_list = client.delete(f"/api/scout/lists/{lists[4].id}", headers=headers)
    assert delete_list.status_code == 200
    assert delete_list.get_json() == {"deleted": True}


@pytest.mark.parametrize("mode", ("pro", "billing_off"))
def test_over_limit_list_mutations_are_ungated_for_pro_or_dark_billing(app, client, monkeypatch, mode):
    user = _add_user()
    if mode == "pro":
        _enable_billing(monkeypatch)
        _add_subscription(user)
    lists, follow_ids = _add_custom_lists(user, 5, with_follows=True)
    target = lists[4]
    headers = _headers(user)

    added = client.post(
        f"/api/scout/lists/{target.id}/follows",
        json={"kind": "query", "selector": {"scout_args": {"position": "Attacker"}}},
        headers=headers,
    )
    assert added.status_code == 201
    assert client.patch(f"/api/scout/lists/{target.id}", json={"is_active": False}, headers=headers).status_code == 200
    assert client.delete(f"/api/scout/lists/{target.id}/follows/{follow_ids[4]}", headers=headers).status_code == 200


def test_list_creation_recounts_after_acquiring_user_lock(app, client, monkeypatch):
    _enable_billing(monkeypatch)
    user = _add_user()
    _add_custom_lists(user, FREE_LIST_LIMIT - 1)
    headers = _headers(user)
    real_execute = db.session.execute
    competing_create_inserted = False

    def execute_with_competing_create(statement, *args, **kwargs):
        nonlocal competing_create_inserted
        result = real_execute(statement, *args, **kwargs)
        if not competing_create_inserted and getattr(statement, "_for_update_arg", None) is not None:
            competing_create_inserted = True
            db.session.add(FollowList(user_account_id=user.id, name="Competing list", is_default=False))
            db.session.flush()
        return result

    monkeypatch.setattr(db.session, "execute", execute_with_competing_create)

    response = client.post("/api/scout/lists", json={"name": "Requested list"}, headers=headers)

    assert competing_create_inserted is True
    assert response.status_code == 403
    assert response.get_json() == CUSTOM_LISTS_REQUIRED
    assert FollowList.query.filter_by(user_account_id=user.id, is_default=False).count() == FREE_LIST_LIMIT
    assert FollowList.query.filter_by(user_account_id=user.id, name="Requested list").first() is None


def test_pro_user_reaches_existing_ten_list_cap(app, client, monkeypatch):
    _enable_billing(monkeypatch)
    user = _add_user()
    _add_subscription(user)
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
        "features": {"csv_export": True, "custom_lists_max": 10},
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
        "features": {"csv_export": True, "custom_lists_max": 10},
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
    assert response.get_json()["entitlements"]["source"] == "none"
