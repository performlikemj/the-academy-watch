"""Tests for the advisory social-profile claim verification ladder.

Network access is always replaced at the ``social_proof.requests`` boundary.
The automated result helps an admin review a claim; it never approves one.
"""

import json
import re
from io import BytesIO

import pytest
from flask import Flask
from src.auth import _ensure_user_account, issue_user_token
from src.models.league import db
from src.models.showcase import PlayerProfileClaim
from src.services import social_proof

ADMIN_KEY = "test-admin-key"
PLAYER_ID = 5001
CODE_PATTERN = re.compile(r"^AW-[ABCDEFGHJKLMNPQRSTUVWXYZ23456789]{8}$")


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("SKIP_API_HANDSHAKE", "1")
    monkeypatch.setenv("API_USE_STUB_DATA", "true")
    monkeypatch.setenv("ADMIN_API_KEY", ADMIN_KEY)
    monkeypatch.setenv("ADMIN_IP_WHITELIST", "")

    from src.routes.showcase import showcase_bp

    flask_app = Flask(__name__)
    flask_app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret-key",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        RATELIMIT_ENABLED=False,
    )

    db.init_app(flask_app)
    flask_app.register_blueprint(showcase_bp, url_prefix="/api")

    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


class FakeResponse:
    """Small requests.Response stand-in supporting streaming and redirect tests."""

    def __init__(self, body=b"", *, status_code=200, headers=None, encoding="utf-8"):
        self._body = body
        self.status_code = status_code
        self.headers = headers or {}
        self.encoding = encoding
        self.raw = BytesIO(body)
        self.closed = False

    @property
    def content(self):
        return self._body

    @property
    def text(self):
        return self._body.decode(self.encoding or "utf-8", errors="replace")

    def iter_content(self, chunk_size=1, decode_unicode=False):
        del decode_unicode
        for start in range(0, len(self._body), chunk_size):
            yield self._body[start : start + chunk_size]

    def close(self):
        self.closed = True


def _user_headers(email):
    token = issue_user_token(email)["token"]
    return {"Authorization": f"Bearer {token}"}


def _admin_headers():
    token = issue_user_token("admin@test.com", role="admin")["token"]
    return {"Authorization": f"Bearer {token}", "X-API-Key": ADMIN_KEY}


def _make_user(email):
    user = _ensure_user_account(email)
    db.session.commit()
    return user


def _seed_claim(
    email="owner@example.com",
    *,
    status="pending",
    code="AW-ABCDEFGH",
    proof_url=None,
    verification_status="unverified",
):
    user = _make_user(email)
    claim = PlayerProfileClaim(
        player_api_id=PLAYER_ID,
        user_account_id=user.id,
        relationship_type="player",
        status=status,
        verification_code=code,
        verification_proof_url=proof_url,
        verification_status=verification_status,
    )
    db.session.add(claim)
    db.session.commit()
    return user, claim


def _fake_get(monkeypatch, responses):
    """Patch requests.Session with an ordered response queue and return calls."""
    queued = list(responses)
    calls = []

    class FakeCookies:
        def clear(self):
            return None

    class FakeSession:
        def __init__(self):
            self.trust_env = True
            self.cookies = FakeCookies()
            self.headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.close()

        def get(self, url, **kwargs):
            calls.append((url, kwargs | {"session_headers": dict(self.headers), "trust_env": self.trust_env}))
            if not queued:
                raise AssertionError("unexpected network fetch")
            response = queued.pop(0)
            if isinstance(response, Exception):
                raise response
            return response

        def close(self):
            return None

    monkeypatch.setattr(social_proof.requests, "Session", FakeSession)
    return calls


def _forbid_fetch(monkeypatch):
    class ForbiddenSession:
        def __init__(self, *args, **kwargs):
            raise AssertionError(f"unexpected network session: {args!r} {kwargs!r}")

    monkeypatch.setattr(social_proof.requests, "Session", ForbiddenSession)


class TestClaimCodeLifecycle:
    def test_creation_mints_code_and_returns_full_verification_shape(self, client):
        response = client.post(
            f"/api/players/{PLAYER_ID}/claim",
            json={"relationship_type": "player", "message": "This is me"},
            headers=_user_headers("owner@example.com"),
        )

        assert response.status_code == 201, response.get_json()
        claim = response.get_json()["claim"]
        assert CODE_PATTERN.fullmatch(claim["verification_code"])
        assert {
            key: claim[key]
            for key in (
                "verification_proof_url",
                "verification_status",
                "verification_checked_at",
                "verification_note",
                "verification_method",
            )
        } == {
            "verification_proof_url": None,
            "verification_status": "unverified",
            "verification_checked_at": None,
            "verification_note": None,
            "verification_method": None,
        }

    def test_me_claims_lazily_mints_and_persists_legacy_code(self, app, client):
        with app.app_context():
            _, claim = _seed_claim(code=None)
            claim_id = claim.id

        response = client.get("/api/me/claims", headers=_user_headers("owner@example.com"))

        assert response.status_code == 200, response.get_json()
        claims = response.get_json()["claims"]
        assert len(claims) == 1
        legacy_claim = claims[0]
        assert CODE_PATTERN.fullmatch(legacy_claim["verification_code"])
        assert legacy_claim["verification_proof_url"] is None
        assert legacy_claim["verification_status"] == "unverified"
        assert legacy_claim["verification_checked_at"] is None
        assert legacy_claim["verification_note"] is None
        assert legacy_claim["verification_method"] is None
        with app.app_context():
            assert db.session.get(PlayerProfileClaim, claim_id).verification_code == claims[0]["verification_code"]


class TestProofUrlBoundary:
    @pytest.mark.parametrize(
        "url",
        [
            "http://instagram.com/academy-player",
            "https://example.com/academy-player",
            "https://127.0.0.1/academy-player",
            "https://instagram.com:443/academy-player",
            "https://claimant@instagram.com/academy-player",
        ],
    )
    def test_invalid_url_is_400_before_fetch(self, app, client, monkeypatch, url):
        with app.app_context():
            _, claim = _seed_claim()
            claim_id = claim.id
        _forbid_fetch(monkeypatch)

        response = client.post(
            f"/api/me/claims/{claim_id}/verify",
            json={"proof_url": url},
            headers=_user_headers("owner@example.com"),
        )

        assert response.status_code == 400, response.get_json()
        error = response.get_json()["error"]
        assert "instagram.com" in error
        assert "youtube.com" in error

    def test_cross_host_redirect_is_refused_even_when_both_hosts_are_allowed(self, monkeypatch):
        calls = _fake_get(
            monkeypatch,
            [
                FakeResponse(
                    status_code=302,
                    headers={"Location": "https://tiktok.com/@academy-player"},
                )
            ],
        )

        result = social_proof.check_proof("https://instagram.com/academy-player", "AW-ABCDEFGH")

        assert result["found"] is False
        assert "redirect" in result["note"].lower()
        assert len(calls) == 1

    def test_body_is_capped_at_two_megabytes(self, monkeypatch):
        code = "AW-ABCDEFGH"
        body = (b"x" * (2 * 1024 * 1024)) + code.lower().encode()
        calls = _fake_get(monkeypatch, [FakeResponse(body)])

        result = social_proof.check_proof("https://instagram.com/academy-player", code)

        assert result["found"] is False
        assert code not in result["note"]
        assert len(calls) == 1
        _, kwargs = calls[0]
        assert kwargs["timeout"] == (3.05, 6)
        assert kwargs["allow_redirects"] is False
        assert kwargs["stream"] is True
        request_headers = kwargs.get("headers", {}) | kwargs.get("session_headers", {})
        assert request_headers.get("User-Agent")
        assert not {"Authorization", "Cookie"}.intersection(request_headers)
        assert kwargs["trust_env"] is False

    def test_network_errors_are_returned_as_advisory_notes(self, monkeypatch):
        _fake_get(monkeypatch, [RuntimeError("simulated timeout")])

        result = social_proof.check_proof("https://instagram.com/academy-player", "AW-ABCDEFGH")

        assert result["found"] is False
        assert result["note"]


class TestClaimantVerification:
    def test_code_found_updates_advisory_status(self, app, client, monkeypatch):
        code = "AW-ABCDEFGH"
        with app.app_context():
            _, claim = _seed_claim(code=code)
            claim_id = claim.id
        calls = _fake_get(monkeypatch, [FakeResponse(f"Public bio: {code.lower()}".encode())])

        response = client.post(
            f"/api/me/claims/{claim_id}/verify",
            json={"proof_url": "https://instagram.com/academy-player"},
            headers=_user_headers("owner@example.com"),
        )

        assert response.status_code == 200, response.get_json()
        claim = response.get_json()["claim"]
        assert claim["status"] == "pending"
        assert claim["verification_status"] == "code_found"
        assert claim["verification_checked_at"]
        assert claim["verification_note"]
        assert claim["verification_proof_url"] == "https://instagram.com/academy-player"
        assert len(calls) == 1
        with app.app_context():
            stored = db.session.get(PlayerProfileClaim, claim_id)
            assert stored.status == "pending"
            assert stored.verification_status == "code_found"

    def test_code_not_found_is_normal_200_outcome(self, app, client, monkeypatch):
        with app.app_context():
            _, claim = _seed_claim()
            claim_id = claim.id
        _fake_get(monkeypatch, [FakeResponse(b"A public profile without the verification token")])

        response = client.post(
            f"/api/me/claims/{claim_id}/verify",
            json={"proof_url": "https://x.com/academy-player"},
            headers=_user_headers("owner@example.com"),
        )

        assert response.status_code == 200, response.get_json()
        claim = response.get_json()["claim"]
        assert claim["verification_status"] == "code_not_found"
        assert claim["verification_checked_at"]
        assert claim["verification_note"]

    def test_non_owner_cannot_verify(self, app, client, monkeypatch):
        with app.app_context():
            _, claim = _seed_claim()
            claim_id = claim.id
        _forbid_fetch(monkeypatch)

        response = client.post(
            f"/api/me/claims/{claim_id}/verify",
            json={"proof_url": "https://instagram.com/academy-player"},
            headers=_user_headers("stranger@example.com"),
        )

        assert response.status_code in (403, 404), response.get_json()

    def test_non_pending_claim_returns_409(self, app, client, monkeypatch):
        with app.app_context():
            _, claim = _seed_claim(status="approved")
            claim_id = claim.id
        _forbid_fetch(monkeypatch)

        response = client.post(
            f"/api/me/claims/{claim_id}/verify",
            json={"proof_url": "https://instagram.com/academy-player"},
            headers=_user_headers("owner@example.com"),
        )

        assert response.status_code == 409, response.get_json()


class TestAdminRecheck:
    def test_recheck_uses_stored_url_and_updates_result(self, app, client, monkeypatch):
        code = "AW-ABCDEFGH"
        proof_url = "https://youtube.com/@academy-player"
        with app.app_context():
            _, claim = _seed_claim(code=code, proof_url=proof_url, verification_status="code_not_found")
            claim_id = claim.id
        calls = _fake_get(monkeypatch, [FakeResponse(f"About {code}".encode())])

        response = client.post(
            f"/api/admin/showcase/claims/{claim_id}/recheck",
            headers=_admin_headers(),
        )

        assert response.status_code == 200, response.get_json()
        claim = response.get_json()["claim"]
        assert claim["verification_status"] == "code_found"
        assert claim["verification_checked_at"]
        assert calls[0][0] == proof_url

    def test_recheck_without_stored_url_is_400_without_fetch(self, app, client, monkeypatch):
        with app.app_context():
            _, claim = _seed_claim(proof_url=None)
            claim_id = claim.id
        _forbid_fetch(monkeypatch)

        response = client.post(
            f"/api/admin/showcase/claims/{claim_id}/recheck",
            headers=_admin_headers(),
        )

        assert response.status_code == 400, response.get_json()

    def test_admin_list_includes_verification_fields(self, app, client):
        with app.app_context():
            _seed_claim(proof_url="https://facebook.com/academy-player")

        response = client.get("/api/admin/showcase/claims", headers=_admin_headers())

        assert response.status_code == 200, response.get_json()
        claim = response.get_json()["claims"][0]
        assert {
            "verification_code",
            "verification_proof_url",
            "verification_status",
            "verification_checked_at",
            "verification_note",
            "verification_method",
        }.issubset(claim)


def test_verification_code_never_appears_in_public_showcase(app, client):
    code = "AW-ABCDEFGH"
    with app.app_context():
        _seed_claim(status="approved", code=code, verification_status="code_found")

    response = client.get(f"/api/players/{PLAYER_ID}/showcase")

    assert response.status_code == 200, response.get_json()
    assert response.get_json()["claim_status"] == "claimed"
    serialized = json.dumps(response.get_json())
    assert "verification_code" not in serialized
    assert code not in serialized
