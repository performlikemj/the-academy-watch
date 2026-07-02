"""Tests for the product-analytics endpoints.

Exercises the real blueprint path via a Flask test client:
- POST /api/events: batch accept + persistence, invalid-name drop, oversize
  rejection, anonymous vs. token-attributed identity.
- GET /api/admin/analytics/summary: SQL aggregation correctness across days,
  and the dual-factor admin gate.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from flask import Flask
from src.models.league import db
from src.models.product_event import ProductEvent

ADMIN_KEY = "test-admin-key"


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("SKIP_API_HANDSHAKE", "1")
    monkeypatch.setenv("API_USE_STUB_DATA", "true")
    monkeypatch.setenv("ADMIN_API_KEY", ADMIN_KEY)
    monkeypatch.setenv("ADMIN_IP_WHITELIST", "")

    from src.routes.events import events_bp

    template_dir = Path(__file__).resolve().parent.parent / "src" / "templates"
    flask_app = Flask(__name__, template_folder=str(template_dir))
    flask_app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret-key",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        RATELIMIT_ENABLED=False,
    )
    db.init_app(flask_app)
    flask_app.register_blueprint(events_bp, url_prefix="/api")

    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def _headers(email="scout@example.com"):
    from src.auth import issue_user_token

    return {"Authorization": f"Bearer {issue_user_token(email)['token']}"}


def _admin_headers():
    from src.auth import issue_user_token

    token = issue_user_token("admin@example.com", role="admin")["token"]
    return {"Authorization": f"Bearer {token}", "X-API-Key": ADMIN_KEY}


# ---------------------------------------------------------------------------
# POST /api/events
# ---------------------------------------------------------------------------


def test_batch_accept_and_persist(client, app):
    payload = {
        "events": [
            {"name": "pageview", "path": "/scout", "session_id": "s1"},
            {"name": "search_performed", "props": {"surface": "scout"}, "session_id": "s1"},
            {"name": "list_created", "session_id": "s1"},
        ]
    }
    res = client.post("/api/events", json=payload)
    assert res.status_code == 202
    assert res.get_json() == {"accepted": 3}

    with app.app_context():
        rows = ProductEvent.query.order_by(ProductEvent.id).all()
        assert [r.event_name for r in rows] == ["pageview", "search_performed", "list_created"]
        assert rows[0].path == "/scout"
        assert rows[1].props == {"surface": "scout"}
        # No token → anonymous.
        assert all(r.user_email is None for r in rows)
        # created_at populated by server default.
        assert all(r.created_at is not None for r in rows)


def test_invalid_names_dropped(client, app):
    payload = {
        "events": [
            {"name": "pageview", "path": "/a"},
            {"name": "not_a_real_event", "path": "/b"},
            {"name": "follow_added"},
            {"name": ""},
            {"path": "/no-name"},
        ]
    }
    res = client.post("/api/events", json=payload)
    assert res.status_code == 202
    # Only the two allowlisted names survive; the batch still succeeds.
    assert res.get_json() == {"accepted": 2}

    with app.app_context():
        names = sorted(r.event_name for r in ProductEvent.query.all())
        assert names == ["follow_added", "pageview"]


def test_oversize_batch_rejected(client, app):
    payload = {"events": [{"name": "pageview", "path": f"/p{i}"} for i in range(26)]}
    res = client.post("/api/events", json=payload)
    assert res.status_code == 413

    with app.app_context():
        assert ProductEvent.query.count() == 0


def test_non_list_body_rejected(client):
    assert client.post("/api/events", json={"events": "nope"}).status_code == 400


def test_anonymous_ok(client, app):
    res = client.post("/api/events", json={"events": [{"name": "pageview", "path": "/"}]})
    assert res.status_code == 202
    with app.app_context():
        row = ProductEvent.query.one()
        assert row.user_email is None


def test_identity_resolved_from_token(client, app):
    res = client.post(
        "/api/events",
        json={"events": [{"name": "claim_submitted", "props": {"player_api_id": 42}}]},
        headers=_headers("scout@example.com"),
    )
    assert res.status_code == 202
    with app.app_context():
        row = ProductEvent.query.one()
        assert row.user_email == "scout@example.com"


def test_beacon_content_type_parsed(client, app):
    # navigator.sendBeacon sends a Blob; the handler uses force=True to parse it.
    res = client.post(
        "/api/events",
        data='{"events": [{"name": "pageview", "path": "/beacon"}]}',
        content_type="text/plain;charset=UTF-8",
    )
    assert res.status_code == 202
    assert res.get_json() == {"accepted": 1}
    with app.app_context():
        assert ProductEvent.query.count() == 1


# ---------------------------------------------------------------------------
# GET /api/admin/analytics/summary
# ---------------------------------------------------------------------------


def _seed_summary(app):
    with app.app_context():
        now = datetime.now(UTC).replace(tzinfo=None)
        yesterday = now - timedelta(days=1)
        long_ago = now - timedelta(days=40)
        rows = [
            ProductEvent(event_name="pageview", path="/a", session_id="s1", created_at=now),
            ProductEvent(event_name="pageview", path="/a", session_id="s2", created_at=now),
            ProductEvent(event_name="pageview", path="/b", session_id="s1", created_at=now),
            ProductEvent(event_name="follow_added", session_id="s1", created_at=yesterday),
            ProductEvent(event_name="follow_added", session_id="s2", created_at=yesterday),
            # Outside a 7-day window — must be excluded.
            ProductEvent(event_name="pageview", path="/old", session_id="s9", created_at=long_ago),
        ]
        db.session.add_all(rows)
        db.session.commit()


def test_summary_aggregates(client, app):
    _seed_summary(app)
    res = client.get("/api/admin/analytics/summary?days=7", headers=_admin_headers())
    assert res.status_code == 200
    body = res.get_json()

    assert body["days"] == 7
    # 40-day-old pageview excluded by the window.
    assert body["totals"] == {"pageview": 3, "follow_added": 2}

    # Two calendar days in-window (today + yesterday), counts sum to 5.
    assert len(body["daily"]) == 2
    assert sum(d["count"] for d in body["daily"]) == 5

    # Pageviews only, top 10, ordered by count desc.
    top = {p["path"]: p["count"] for p in body["top_paths"]}
    assert top == {"/a": 2, "/b": 1}
    assert body["top_paths"][0]["path"] == "/a"

    # Distinct sessions in-window: s1, s2 (s9 is out of window).
    assert body["distinct_sessions"] == 2


def test_summary_days_capped(client, app):
    _seed_summary(app)
    res = client.get("/api/admin/analytics/summary?days=1000", headers=_admin_headers())
    assert res.status_code == 200
    body = res.get_json()
    assert body["days"] == 90
    # With a 90-day window the old pageview is now counted.
    assert body["totals"]["pageview"] == 4


def test_summary_requires_admin(client):
    # No credentials at all.
    assert client.get("/api/admin/analytics/summary").status_code == 401
    # A plain (non-admin) user token must not pass the admin gate.
    assert client.get("/api/admin/analytics/summary", headers=_headers()).status_code == 401
