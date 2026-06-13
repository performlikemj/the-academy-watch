"""Tests for the `applied` flag on dry-run-capable admin repair endpoints.

The dry-run trap is real: counters look identical between a dry and a live
run, so each endpoint now states explicitly whether it mutated anything:

- POST /api/admin/journeys/recompute-academy
- POST /api/admin/players/backfill-names
- POST /api/scout/admin/send-digests
"""

import pytest
from flask import Flask
from src.models.league import db

# Imported for db.create_all() side effects (table registration): the
# journey endpoints query these models at request time.
from src.models.weekly import FixturePlayerStats  # noqa: F401

ADMIN_KEY = "test-admin-key"


@pytest.fixture
def journey_app(monkeypatch):
    monkeypatch.setenv("SKIP_API_HANDSHAKE", "1")
    monkeypatch.setenv("API_USE_STUB_DATA", "true")
    monkeypatch.setenv("ADMIN_API_KEY", ADMIN_KEY)
    monkeypatch.setenv("ADMIN_IP_WHITELIST", "")

    from src.routes.journey import journey_bp

    flask_app = Flask(__name__)
    flask_app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret-key",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )

    db.init_app(flask_app)
    flask_app.register_blueprint(journey_bp, url_prefix="/api")

    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def scout_app(monkeypatch):
    monkeypatch.setenv("SKIP_API_HANDSHAKE", "1")
    monkeypatch.setenv("API_USE_STUB_DATA", "true")
    monkeypatch.setenv("ADMIN_API_KEY", ADMIN_KEY)
    monkeypatch.setenv("ADMIN_IP_WHITELIST", "")

    from src.routes.scout import scout_bp

    flask_app = Flask(__name__)
    flask_app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret-key",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )

    db.init_app(flask_app)
    flask_app.register_blueprint(scout_bp, url_prefix="/api")

    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()


def _admin_headers():
    from src.auth import issue_user_token

    token = issue_user_token("admin@test.com", role="admin")["token"]
    return {"Authorization": f"Bearer {token}", "X-API-Key": ADMIN_KEY}


class TestRecomputeAcademyApplied:
    def test_default_dry_run_is_not_applied(self, journey_app):
        client = journey_app.test_client()
        res = client.post("/api/admin/journeys/recompute-academy", json={}, headers=_admin_headers())
        assert res.status_code == 200
        data = res.get_json()
        assert data["dry_run"] is True
        assert data["applied"] is False

    def test_live_run_is_applied(self, journey_app):
        client = journey_app.test_client()
        res = client.post("/api/admin/journeys/recompute-academy", json={"dry_run": False}, headers=_admin_headers())
        assert res.status_code == 200
        data = res.get_json()
        assert data["dry_run"] is False
        assert data["applied"] is True


class TestBackfillNamesApplied:
    def test_default_dry_run_is_not_applied(self, journey_app):
        client = journey_app.test_client()
        res = client.post("/api/admin/players/backfill-names", json={}, headers=_admin_headers())
        assert res.status_code == 200
        data = res.get_json()
        assert data["dry_run"] is True
        assert data["applied"] is False

    def test_live_run_is_applied(self, journey_app):
        client = journey_app.test_client()
        res = client.post("/api/admin/players/backfill-names", json={"dry_run": False}, headers=_admin_headers())
        assert res.status_code == 200
        data = res.get_json()
        assert data["dry_run"] is False
        assert data["applied"] is True


class TestScoutDigestsApplied:
    @pytest.fixture(autouse=True)
    def _stub_digest_service(self, monkeypatch):
        self.calls = []

        def fake_send(dry_run=True, limit=50, api_client=None, cursor=0):
            self.calls.append({"dry_run": dry_run, "limit": limit, "cursor": cursor})
            return {
                "sent": 0,
                "skipped": 0,
                "users_considered": 0,
                "previews": [],
                "next_cursor": None,
            }

        import src.services.scout_digest_service as digest_module

        monkeypatch.setattr(digest_module, "send_scout_digests", fake_send)

    def test_default_dry_run_is_not_applied(self, scout_app):
        client = scout_app.test_client()
        res = client.post("/api/scout/admin/send-digests", json={}, headers=_admin_headers())
        assert res.status_code == 200
        data = res.get_json()
        assert data["dry_run"] is True
        assert data["applied"] is False
        assert data["next_cursor"] is None
        assert self.calls == [{"dry_run": True, "limit": 50, "cursor": 0}]

    def test_live_run_is_applied(self, scout_app):
        client = scout_app.test_client()
        res = client.post(
            "/api/scout/admin/send-digests", json={"dry_run": False, "limit": 10, "cursor": 5}, headers=_admin_headers()
        )
        assert res.status_code == 200
        data = res.get_json()
        assert data["dry_run"] is False
        assert data["applied"] is True
        assert self.calls == [{"dry_run": False, "limit": 10, "cursor": 5}]
