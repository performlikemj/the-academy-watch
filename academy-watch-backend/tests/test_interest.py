"""Interest intake, admin authorization, export and cross-language contracts."""

import csv
import io
import re
from pathlib import Path

import pytest
from flask import Flask
from src.auth import issue_user_token
from src.extensions import limiter
from src.models.interest import INTEREST_FEATURES, INTEREST_ROLES, InterestSignup
from src.models.league import db
from src.routes.interest import interest_bp


@pytest.fixture
def interest_app(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "interest-test-key")
    monkeypatch.setenv("ADMIN_IP_WHITELIST", "")
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SECRET_KEY="interest-test-secret",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        RATELIMIT_ENABLED=True,
    )
    db.init_app(app)
    limiter.init_app(app)
    limiter.enabled = False
    app.register_blueprint(interest_bp, url_prefix="/api")
    with app.app_context():
        limiter.reset()
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(interest_app):
    return interest_app.test_client()


@pytest.fixture
def admin_headers(interest_app):
    return {
        "Authorization": f"Bearer {issue_user_token('admin@example.com', role='admin')['token']}",
        "X-API-Key": "interest-test-key",
    }


def test_create_normalizes_and_persists(client):
    response = client.post(
        "/api/interest",
        json={"email": " Player@Example.com ", "feature": "early_access", "role": "player", "source_path": "/"},
    )
    assert response.status_code == 201
    assert response.json == {"status": "ok"}
    row = InterestSignup.query.one()
    assert (row.email, row.role, row.source_path) == ("player@example.com", "player", "/")
    assert row.created_at


def test_duplicate_is_idempotent_per_feature(client):
    payload = {"email": "player@example.com", "feature": "early_access"}
    assert client.post("/api/interest", json=payload).status_code == 201
    duplicate = client.post("/api/interest", json={**payload, "email": "PLAYER@example.com", "role": "scout"})
    assert duplicate.status_code == 200
    assert duplicate.json == {"status": "already"}
    assert InterestSignup.query.one().role is None
    assert client.post("/api/interest", json={**payload, "feature": "opportunities"}).status_code == 201
    assert InterestSignup.query.count() == 2


@pytest.mark.parametrize(
    "email", ["", "invalid", "a@b", "a b@example.com", "a@exa\nmple.com", None, [], 42, "x" * 250 + "@example.com"]
)
def test_bad_email(client, email):
    assert client.post("/api/interest", json={"email": email, "feature": "early_access"}).status_code == 400
    assert InterestSignup.query.count() == 0


@pytest.mark.parametrize("feature", ["unknown", None, [], {}, 4])
def test_bad_feature(client, feature):
    assert client.post("/api/interest", json={"email": "a@example.com", "feature": feature}).status_code == 400


@pytest.mark.parametrize(
    "field,value",
    [
        ("role", "manager"),
        ("role", []),
        ("role", False),
        ("source_path", False),
        ("role", ["club"]),
        ("source_path", "https://example.com"),
        ("source_path", ["/"]),
        ("source_path", "/" + "x" * 500),
    ],
)
def test_bad_optional_fields(client, field, value):
    assert (
        client.post(
            "/api/interest", json={"email": "a@example.com", "feature": "early_access", field: value}
        ).status_code
        == 400
    )


def test_honeypot_returns_success_without_storing(client):
    response = client.post("/api/interest", json={"website": "https://spam.example", "email": "bad", "feature": "bad"})
    assert response.status_code == 201
    assert response.json == {"status": "ok"}
    assert InterestSignup.query.count() == 0


@pytest.mark.parametrize("payload", [None, [], "bad", 123])
def test_requires_json_object(client, payload):
    assert client.post("/api/interest", json=payload).status_code == 400


def test_existing_limiter_caps_public_intake(client, monkeypatch):
    monkeypatch.setattr(limiter, "enabled", True)
    limiter.reset()
    for _ in range(10):
        assert client.post("/api/interest", json={"email": "bad", "feature": "early_access"}).status_code == 400
    assert client.post("/api/interest", json={"email": "bad", "feature": "early_access"}).status_code == 429
    assert InterestSignup.query.count() == 0
    limiter.reset()


def test_admin_auth_requires_both_factors(client, admin_headers):
    for url in ("/api/admin/interest", "/api/admin/interest?format=csv"):
        assert client.get(url).status_code == 401
        assert client.get(url, headers={"X-API-Key": "interest-test-key"}).status_code == 401
        assert client.get(url, headers={"Authorization": admin_headers["Authorization"]}).status_code == 401
        assert client.get(url, headers={**admin_headers, "X-API-Key": "wrong-key"}).status_code == 403
        user_token = issue_user_token("scout@example.com", role="user")["token"]
        assert client.get(url, headers={**admin_headers, "Authorization": f"Bearer {user_token}"}).status_code == 401


def test_counts_newest_and_csv(client, admin_headers):
    for email, feature, role in [
        ("first@example.com", "early_access", "club"),
        ("second@example.com", "early_access", None),
        ("third@example.com", "opportunities", "scout"),
    ]:
        assert (
            client.post(
                "/api/interest", json={"email": email, "feature": feature, "role": role, "source_path": "/clubs"}
            ).status_code
            == 201
        )
    report = client.get("/api/admin/interest?limit=1", headers=admin_headers)
    assert report.json["total"] == 3
    assert report.json["counts"]["feature"]["early_access"] == 2
    assert report.json["counts"]["role"]["unspecified"] == 1
    assert [row["email"] for row in report.json["rows"]] == ["third@example.com"]
    assert report.headers["Cache-Control"] == "no-store"
    export = client.get("/api/admin/interest?format=csv", headers=admin_headers)
    assert export.status_code == 200
    assert export.mimetype == "text/csv"
    assert "attachment" in export.headers["Content-Disposition"]
    rows = list(csv.DictReader(io.StringIO(export.text)))
    assert len(rows) == 3
    assert rows[0]["email"] == "third@example.com"
    assert rows[0]["created_at"].endswith("Z")


def test_csv_formula_cells_are_inert(client, admin_headers):
    client.post("/api/interest", json={"email": "+formula@example.com", "feature": "early_access"})
    export = client.get("/api/admin/interest?format=csv", headers=admin_headers)
    assert list(csv.DictReader(io.StringIO(export.text)))[0]["email"] == "'+formula@example.com"


def test_frontend_constants_match_backend():
    source = (Path(__file__).resolve().parents[2] / "academy-watch-frontend/src/lib/interest.js").read_text()
    for name, expected in (("INTEREST_FEATURES", INTEREST_FEATURES), ("INTEREST_ROLES", INTEREST_ROLES)):
        block = re.search(rf"export const {name} = \[(.*?)\]", source, re.S)
        assert block
        assert tuple(re.findall(r"'([^']+)'", block.group(1))) == expected
