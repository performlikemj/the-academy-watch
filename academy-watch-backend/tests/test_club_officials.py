"""Tests for club-official claims, affiliation decisions, and player vouching.

The module owns an isolated in-memory SQLite app. Social-proof HTTP is always
replaced at the ``social_proof.requests`` boundary, so these tests never make a
real network request.
"""

import json
import re
from datetime import UTC, datetime
from io import BytesIO

import pytest
from flask import Flask
from src.auth import _ensure_user_account, issue_user_token
from src.models.league import League, Team, db
from src.models.showcase import (
    ClubOfficialClaim,
    LocalClub,
    PlayerClubAffiliation,
    PlayerProfileClaim,
    PlayerShowcaseProfile,
)
from src.services import social_proof

ADMIN_KEY = "test-admin-key"
PLAYER_ID = 5001
OTHER_PLAYER_ID = 5002
TEAM_ID = 4401
OTHER_TEAM_ID = 4402
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
    """Small streaming ``requests.Response`` stand-in."""

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


def _fake_get(monkeypatch, responses):
    """Patch ``requests.Session`` with an ordered response queue."""
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


def _seed_team(team_id=TEAM_ID, name="Northbridge United", *, season=2025):
    league = League.query.filter_by(league_id=39).first()
    if league is None:
        league = League(league_id=39, name="Premier League", country="England", season=2025)
        db.session.add(league)
        db.session.flush()
    team = Team(
        team_id=team_id,
        name=name,
        country="England",
        season=season,
        league_id=league.id,
        is_active=True,
    )
    db.session.add(team)
    db.session.flush()
    return team


def _seed_local_club(
    name="Northside Juniors",
    *,
    status="verified",
    merged_into_local_club_id=None,
):
    club = LocalClub(
        name=name,
        normalized_name=LocalClub.normalize_name(name),
        country="England",
        city="Leeds",
        level="youth",
        status=status,
        provenance="user",
        merged_into_local_club_id=merged_into_local_club_id,
    )
    db.session.add(club)
    db.session.flush()
    return club


def _seed_official_claim(
    email="official@example.com",
    *,
    team_api_id=None,
    local_club_id=None,
    status="pending",
    code="AW-CLUBCODE",
    proof_url=None,
    verification_status="unverified",
):
    user = _make_user(email)
    claim = ClubOfficialClaim(
        user_account_id=user.id,
        team_api_id=team_api_id,
        local_club_id=local_club_id,
        role_title="Academy Director",
        message="I manage the academy.",
        status=status,
        verification_code=code,
        verification_proof_url=proof_url,
        verification_status=verification_status,
    )
    db.session.add(claim)
    db.session.commit()
    return user, claim


def _seed_player_claim(
    *,
    player_api_id=PLAYER_ID,
    email="player@example.com",
    status="pending",
    code="AW-PLAYERCODE",
    verification_status="unverified",
    verification_checked_at=None,
):
    user = _make_user(email)
    claim = PlayerProfileClaim(
        player_api_id=player_api_id,
        user_account_id=user.id,
        relationship_type="player",
        status=status,
        verification_code=code,
        verification_status=verification_status,
        verification_checked_at=verification_checked_at,
    )
    db.session.add(claim)
    db.session.commit()
    return user, claim


def _seed_affiliation(
    *,
    player_api_id=PLAYER_ID,
    team_api_id=None,
    local_club_id=None,
    status="pending",
    review_note=None,
):
    affiliation = PlayerClubAffiliation(
        player_api_id=player_api_id,
        team_api_id=team_api_id,
        local_club_id=local_club_id,
        season="2025/26",
        status=status,
        review_note=review_note,
    )
    db.session.add(affiliation)
    db.session.commit()
    return affiliation


class TestClubClaimSubmission:
    def test_requires_auth(self, client):
        response = client.post(
            "/api/clubs/claim",
            json={"team_api_id": TEAM_ID, "role_title": "Academy Director"},
        )

        assert response.status_code == 401

    def test_team_claim_sanitizes_fields_and_resolves_latest_name(self, app, client):
        with app.app_context():
            _seed_team(name="Northbridge Old Name", season=2024)
            _seed_team(name="Northbridge United", season=2025)
            db.session.commit()

        response = client.post(
            "/api/clubs/claim",
            json={
                "team_api_id": TEAM_ID,
                "role_title": " <b>Academy Director</b> ",
                "message": f"<script>{'M' * 900}</script>",
            },
            headers=_user_headers("official@example.com"),
        )

        assert response.status_code == 201, response.get_json()
        claim = response.get_json()["claim"]
        assert claim["team_api_id"] == TEAM_ID
        assert claim["local_club_id"] is None
        assert claim["club_name"] == "Northbridge United"
        assert claim["role_title"] == "Academy Director"
        assert claim["message"] == "M" * 900
        assert claim["status"] == "pending"
        assert CODE_PATTERN.fullmatch(claim["verification_code"])
        assert claim["verification_status"] == "unverified"

    def test_reference_xor_and_active_local_club_validation(self, app, client):
        with app.app_context():
            active = _seed_local_club("Active Club", status="pending")
            merged = _seed_local_club("Merged Club", status="merged")
            rejected = _seed_local_club("Rejected Club", status="rejected")
            db.session.commit()
            active_id = active.id
            invalid_local_ids = (merged.id, rejected.id, 999999)

        payloads = [
            {"role_title": "Coach"},
            {"team_api_id": TEAM_ID, "local_club_id": active_id, "role_title": "Coach"},
            {"team_api_id": 0, "role_title": "Coach"},
            {"team_api_id": -1, "role_title": "Coach"},
            {"team_api_id": "4401", "role_title": "Coach"},
            {"team_api_id": True, "role_title": "Coach"},
            *({"local_club_id": club_id, "role_title": "Coach"} for club_id in invalid_local_ids),
        ]
        headers = _user_headers("official@example.com")

        for payload in payloads:
            response = client.post("/api/clubs/claim", json=payload, headers=headers)
            assert response.status_code == 400, (payload, response.get_json())

        with app.app_context():
            assert ClubOfficialClaim.query.count() == 0

    def test_role_title_is_required_and_bounded_after_sanitizing(self, client):
        headers = _user_headers("official@example.com")
        for role_title in (None, "x", "x" * 101, 123):
            payload = {"team_api_id": TEAM_ID}
            if role_title is not None:
                payload["role_title"] = role_title
            response = client.post("/api/clubs/claim", json=payload, headers=headers)
            assert response.status_code == 400, (role_title, response.get_json())

        too_long_message = client.post(
            "/api/clubs/claim",
            json={"team_api_id": TEAM_ID, "role_title": "Coach", "message": "x" * 1001},
            headers=headers,
        )
        assert too_long_message.status_code == 400, too_long_message.get_json()

    @pytest.mark.parametrize("status", ["pending", "approved"])
    def test_active_duplicate_is_409(self, app, client, status):
        with app.app_context():
            _seed_official_claim(team_api_id=TEAM_ID, status=status)

        response = client.post(
            "/api/clubs/claim",
            json={"team_api_id": TEAM_ID, "role_title": "Head Coach"},
            headers=_user_headers("official@example.com"),
        )

        assert response.status_code == 409, response.get_json()

    def test_active_duplicate_follows_one_local_merge_hop(self, app, client):
        with app.app_context():
            canonical = _seed_local_club("Canonical Academy", status="verified")
            merged = _seed_local_club(
                "Former Academy Name",
                status="merged",
                merged_into_local_club_id=canonical.id,
            )
            db.session.commit()
            canonical_id = canonical.id
            _seed_official_claim(local_club_id=merged.id, status="approved")

        response = client.post(
            "/api/clubs/claim",
            json={"local_club_id": canonical_id, "role_title": "Head Coach"},
            headers=_user_headers("official@example.com"),
        )

        assert response.status_code == 409, response.get_json()

    def test_pending_claim_quota_rejects_sixth_outstanding_claim(self, app, client):
        with app.app_context():
            for offset in range(5):
                _seed_official_claim(team_api_id=10_000 + offset)

        response = client.post(
            "/api/clubs/claim",
            json={"team_api_id": 20_000, "role_title": "Head Coach"},
            headers=_user_headers("official@example.com"),
        )

        assert response.status_code == 429, response.get_json()
        assert response.get_json() == {"error": "pending club-official claim limit reached (5)"}
        with app.app_context():
            user = _ensure_user_account("official@example.com")
            assert (
                ClubOfficialClaim.query.filter_by(
                    user_account_id=user.id,
                    status="pending",
                ).count()
                == 5
            )


class TestClubClaimVerification:
    def test_me_claims_is_owner_scoped_and_lazily_mints_code(self, app, client):
        with app.app_context():
            _seed_team()
            _, own = _seed_official_claim(team_api_id=TEAM_ID, code=None)
            _seed_official_claim(
                email="other-official@example.com",
                team_api_id=OTHER_TEAM_ID,
                code="AW-OTHERCODE",
            )
            own_id = own.id

        response = client.get(
            "/api/me/club-claims",
            headers=_user_headers("official@example.com"),
        )

        assert response.status_code == 200, response.get_json()
        claims = response.get_json()["claims"]
        assert len(claims) == 1
        claim = claims[0]
        assert claim["id"] == own_id
        assert claim["club_name"] == "Northbridge United"
        assert CODE_PATTERN.fullmatch(claim["verification_code"])
        assert {
            "verification_proof_url",
            "verification_status",
            "verification_checked_at",
            "verification_note",
            "verification_method",
        }.issubset(claim)
        with app.app_context():
            assert CODE_PATTERN.fullmatch(db.session.get(ClubOfficialClaim, own_id).verification_code)

    def test_code_found_updates_advisory_status(self, app, client, monkeypatch):
        code = "AW-ABCDEFGH"
        with app.app_context():
            _seed_team()
            _, claim = _seed_official_claim(team_api_id=TEAM_ID, code=code)
            claim_id = claim.id
        calls = _fake_get(monkeypatch, [FakeResponse(f"Public club bio: {code.lower()}".encode())])

        response = client.post(
            f"/api/me/club-claims/{claim_id}/verify",
            json={"proof_url": "https://instagram.com/northbridge-united"},
            headers=_user_headers("official@example.com"),
        )

        assert response.status_code == 200, response.get_json()
        verified = response.get_json()["claim"]
        assert verified["status"] == "pending"
        assert verified["verification_status"] == "code_found"
        assert verified["verification_checked_at"]
        assert verified["verification_note"]
        assert verified["verification_proof_url"] == "https://instagram.com/northbridge-united"
        assert verified["club_name"] == "Northbridge United"
        assert "verification_code" not in verified
        assert len(calls) == 1

    def test_code_not_found_is_a_normal_200_result(self, app, client, monkeypatch):
        with app.app_context():
            _, claim = _seed_official_claim(team_api_id=TEAM_ID, code="AW-ABCDEFGH")
            claim_id = claim.id
        _fake_get(monkeypatch, [FakeResponse(b"A public club profile without the token")])

        response = client.post(
            f"/api/me/club-claims/{claim_id}/verify",
            json={"proof_url": "https://x.com/northbridge-united"},
            headers=_user_headers("official@example.com"),
        )

        assert response.status_code == 200, response.get_json()
        verified = response.get_json()["claim"]
        assert verified["verification_status"] == "code_not_found"
        assert verified["verification_checked_at"]
        assert verified["verification_note"]

    def test_invalid_proof_url_is_rejected_before_fetch(self, app, client, monkeypatch):
        with app.app_context():
            _, claim = _seed_official_claim(team_api_id=TEAM_ID)
            claim_id = claim.id
        _forbid_fetch(monkeypatch)

        response = client.post(
            f"/api/me/club-claims/{claim_id}/verify",
            json={"proof_url": "https://example.com/northbridge"},
            headers=_user_headers("official@example.com"),
        )

        assert response.status_code == 400, response.get_json()

    def test_non_owner_gets_404_without_fetch(self, app, client, monkeypatch):
        with app.app_context():
            _, claim = _seed_official_claim(team_api_id=TEAM_ID)
            claim_id = claim.id
        _forbid_fetch(monkeypatch)

        response = client.post(
            f"/api/me/club-claims/{claim_id}/verify",
            json={"proof_url": "https://instagram.com/northbridge"},
            headers=_user_headers("stranger@example.com"),
        )

        assert response.status_code == 404, response.get_json()

    def test_non_pending_claim_is_409_without_fetch(self, app, client, monkeypatch):
        with app.app_context():
            _, claim = _seed_official_claim(team_api_id=TEAM_ID, status="approved")
            claim_id = claim.id
        _forbid_fetch(monkeypatch)

        response = client.post(
            f"/api/me/club-claims/{claim_id}/verify",
            json={"proof_url": "https://instagram.com/northbridge"},
            headers=_user_headers("official@example.com"),
        )

        assert response.status_code == 409, response.get_json()


class TestMyClubDashboard:
    def test_shape_merge_hop_matching_and_player_code_stripping(self, app, client):
        checked_at = datetime(2026, 7, 14, 10, 0, tzinfo=UTC)
        with app.app_context():
            canonical = _seed_local_club("Northside Academy", status="verified")
            merged = _seed_local_club(
                "Northside Juniors Old",
                status="merged",
                merged_into_local_club_id=canonical.id,
            )
            other = _seed_local_club("Other Academy", status="verified")
            db.session.commit()
            canonical_id = canonical.id
            merged_id = merged.id
            other_id = other.id

            _, official_claim = _seed_official_claim(
                local_club_id=canonical_id,
                status="approved",
                code="AW-OFFICIALSECRET",
            )
            pending_affiliation = _seed_affiliation(
                player_api_id=PLAYER_ID,
                local_club_id=merged_id,
                status="pending",
                review_note="Awaiting the club",
            )
            self_reported_affiliation = _seed_affiliation(
                player_api_id=OTHER_PLAYER_ID,
                local_club_id=canonical_id,
                status="self_reported",
                review_note="Admin accepted the report",
            )
            _seed_affiliation(
                player_api_id=5003,
                local_club_id=merged_id,
                status="rejected",
                review_note="Rejected report",
            )
            _seed_affiliation(player_api_id=5004, local_club_id=other_id, status="pending")

            _, first_player_claim = _seed_player_claim(
                player_api_id=PLAYER_ID,
                email="first-player@example.com",
                code="AW-FIRSTPLAYERSECRET",
                verification_status="code_found",
                verification_checked_at=checked_at,
            )
            _, second_player_claim = _seed_player_claim(
                player_api_id=OTHER_PLAYER_ID,
                email="second-player@example.com",
                code="AW-SECONDPLAYERSECRET",
            )
            _seed_player_claim(player_api_id=5003, email="rejected-aff-player@example.com")
            _seed_player_claim(player_api_id=5004, email="other-club-player@example.com")
            _seed_player_claim(
                player_api_id=PLAYER_ID,
                email="already-approved@example.com",
                status="approved",
            )
            official_claim_id = official_claim.id
            expected_affiliation_ids = {pending_affiliation.id, self_reported_affiliation.id}
            expected_player_claim_ids = {first_player_claim.id, second_player_claim.id}

        response = client.get("/api/me/club", headers=_user_headers("official@example.com"))

        assert response.status_code == 200, response.get_json()
        clubs = response.get_json()["clubs"]
        assert len(clubs) == 1
        club = clubs[0]
        assert club["claim"]["id"] == official_claim_id
        assert club["club_name"] == "Northside Academy"
        assert {item["id"] for item in club["pending_affiliations"]} == expected_affiliation_ids
        assert {item["status"] for item in club["pending_affiliations"]} == {"pending", "self_reported"}
        assert all("review_note" in item for item in club["pending_affiliations"])

        player_claims = club["vouchable_player_claims"]
        assert {item["id"] for item in player_claims} == expected_player_claim_ids
        assert all("verification_code" not in item for item in player_claims)
        first = next(item for item in player_claims if item["id"] == first_player_claim.id)
        assert first["verification_status"] == "code_found"
        assert first["verification_checked_at"]

        serialized = json.dumps(response.get_json())
        assert "verification_code" not in serialized
        assert "AW-OFFICIALSECRET" not in serialized
        assert "AW-FIRSTPLAYERSECRET" not in serialized
        assert "AW-SECONDPLAYERSECRET" not in serialized


class TestClubAffiliationDecisions:
    def test_confirm_marks_pending_affiliation_club_confirmed(self, app, client):
        with app.app_context():
            _seed_team()
            _seed_official_claim(team_api_id=TEAM_ID, status="approved")
            affiliation = _seed_affiliation(team_api_id=TEAM_ID, status="pending")
            affiliation_id = affiliation.id

        response = client.post(
            f"/api/me/club/affiliations/{affiliation_id}/confirm",
            headers=_user_headers("official@example.com"),
        )

        assert response.status_code == 200, response.get_json()
        assert response.get_json()["affiliation"]["status"] == "club_confirmed"
        with app.app_context():
            stored = db.session.get(PlayerClubAffiliation, affiliation_id)
            assert stored.status == "club_confirmed"
            assert stored.reviewed_by == "official@example.com"
            assert stored.reviewed_at is not None

    def test_reject_allows_self_reported_and_sanitizes_note(self, app, client):
        with app.app_context():
            _seed_official_claim(team_api_id=TEAM_ID, status="approved")
            affiliation = _seed_affiliation(team_api_id=TEAM_ID, status="self_reported")
            affiliation_id = affiliation.id

        response = client.post(
            f"/api/me/club/affiliations/{affiliation_id}/reject",
            json={"note": " <b>Player is not registered here</b> "},
            headers=_user_headers("official@example.com"),
        )

        assert response.status_code == 200, response.get_json()
        rejected = response.get_json()["affiliation"]
        assert rejected["status"] == "rejected"
        assert rejected["review_note"] == "Player is not registered here"
        with app.app_context():
            stored = db.session.get(PlayerClubAffiliation, affiliation_id)
            assert stored.reviewed_by == "official@example.com"
            assert stored.reviewed_at is not None

    @pytest.mark.parametrize("action", ["confirm", "reject"])
    def test_absent_and_unauthorized_affiliation_are_uniform_404(self, app, client, action):
        with app.app_context():
            _seed_official_claim(team_api_id=OTHER_TEAM_ID, status="approved")
            affiliation = _seed_affiliation(team_api_id=TEAM_ID, status="club_confirmed")
            affiliation_id = affiliation.id

        unauthorized = client.post(
            f"/api/me/club/affiliations/{affiliation_id}/{action}",
            headers=_user_headers("official@example.com"),
        )
        absent = client.post(
            f"/api/me/club/affiliations/999999/{action}",
            headers=_user_headers("official@example.com"),
        )

        assert unauthorized.status_code == absent.status_code == 404
        assert unauthorized.get_json() == absent.get_json() == {"error": "affiliation not found"}
        with app.app_context():
            assert db.session.get(PlayerClubAffiliation, affiliation_id).status == "club_confirmed"

    @pytest.mark.parametrize(
        ("action", "expected_status"),
        [("confirm", "club_confirmed"), ("reject", "rejected")],
    )
    def test_verified_local_club_official_can_decide_affiliation(
        self,
        app,
        client,
        action,
        expected_status,
    ):
        with app.app_context():
            club = _seed_local_club(status="verified")
            _seed_official_claim(local_club_id=club.id, status="approved")
            affiliation = _seed_affiliation(local_club_id=club.id, status="pending")
            affiliation_id = affiliation.id

        response = client.post(
            f"/api/me/club/affiliations/{affiliation_id}/{action}",
            json={} if action == "reject" else None,
            headers=_user_headers("official@example.com"),
        )

        assert response.status_code == 200, response.get_json()
        assert response.get_json()["affiliation"]["status"] == expected_status

    @pytest.mark.parametrize("action", ["confirm", "reject"])
    def test_pending_local_club_official_cannot_decide_affiliation(self, app, client, action):
        with app.app_context():
            club = _seed_local_club(status="pending")
            _seed_official_claim(local_club_id=club.id, status="approved")
            affiliation = _seed_affiliation(local_club_id=club.id, status="pending")
            affiliation_id = affiliation.id

        response = client.post(
            f"/api/me/club/affiliations/{affiliation_id}/{action}",
            json={} if action == "reject" else None,
            headers=_user_headers("official@example.com"),
        )

        assert response.status_code == 404, response.get_json()
        assert response.get_json() == {"error": "affiliation not found"}
        with app.app_context():
            assert db.session.get(PlayerClubAffiliation, affiliation_id).status == "pending"

    @pytest.mark.parametrize(
        ("action", "status"),
        [("confirm", "club_confirmed"), ("reject", "rejected")],
    )
    def test_non_reviewable_affiliation_is_409(self, app, client, action, status):
        with app.app_context():
            _seed_official_claim(team_api_id=TEAM_ID, status="approved")
            affiliation = _seed_affiliation(team_api_id=TEAM_ID, status=status)
            affiliation_id = affiliation.id

        response = client.post(
            f"/api/me/club/affiliations/{affiliation_id}/{action}",
            json={} if action == "reject" else None,
            headers=_user_headers("official@example.com"),
        )

        assert response.status_code == 409, response.get_json()


class TestPlayerClaimVouching:
    def test_vouch_approves_identity_but_leaves_content_pending(self, app, client):
        with app.app_context():
            canonical = _seed_local_club("Northside Academy", status="verified")
            merged = _seed_local_club(
                "Old Northside Academy",
                status="merged",
                merged_into_local_club_id=canonical.id,
            )
            db.session.commit()
            canonical_id = canonical.id
            merged_id = merged.id
            _seed_official_claim(local_club_id=canonical_id, status="approved")
            _seed_affiliation(local_club_id=merged_id, status="pending")
            _, player_claim = _seed_player_claim(code="AW-PLAYERSECRET")
            profile = PlayerShowcaseProfile(
                player_api_id=PLAYER_ID,
                bio="Pending owner content",
                status="pending",
            )
            db.session.add(profile)
            db.session.commit()
            player_claim_id = player_claim.id

        response = client.post(
            f"/api/me/club/player-claims/{player_claim_id}/vouch",
            headers=_user_headers("official@example.com"),
        )

        assert response.status_code == 200, response.get_json()
        vouched = response.get_json()["claim"]
        assert vouched["status"] == "approved"
        assert vouched["verification_method"] == "vouch"
        assert vouched["verification_note"] == "Vouched by a verified Northside Academy official"
        assert vouched["reviewed_by"] == "official@example.com"
        assert vouched["reviewed_at"]
        assert "verification_code" not in vouched
        assert "AW-PLAYERSECRET" not in json.dumps(response.get_json())

        with app.app_context():
            stored_claim = db.session.get(PlayerProfileClaim, player_claim_id)
            assert stored_claim.status == "approved"
            assert stored_claim.verification_code == "AW-PLAYERSECRET"
            assert PlayerShowcaseProfile.query.filter_by(player_api_id=PLAYER_ID).one().status == "pending"

        public = client.get(f"/api/players/{PLAYER_ID}/showcase")
        assert public.status_code == 200, public.get_json()
        assert public.get_json()["claim_status"] == "claimed"
        assert public.get_json()["profile"] is None

    def test_api_team_official_can_vouch_for_player_claim(self, app, client):
        with app.app_context():
            _seed_official_claim(team_api_id=TEAM_ID, status="approved")
            _seed_affiliation(team_api_id=TEAM_ID, status="pending")
            _, player_claim = _seed_player_claim()
            player_claim_id = player_claim.id

        response = client.post(
            f"/api/me/club/player-claims/{player_claim_id}/vouch",
            headers=_user_headers("official@example.com"),
        )

        assert response.status_code == 200, response.get_json()
        assert response.get_json()["claim"]["status"] == "approved"

    def test_pending_local_club_official_cannot_vouch_for_player_claim(self, app, client):
        with app.app_context():
            club = _seed_local_club(status="pending")
            _seed_official_claim(local_club_id=club.id, status="approved")
            _seed_affiliation(local_club_id=club.id, status="pending")
            _, player_claim = _seed_player_claim()
            player_claim_id = player_claim.id

        response = client.post(
            f"/api/me/club/player-claims/{player_claim_id}/vouch",
            headers=_user_headers("official@example.com"),
        )

        assert response.status_code == 404, response.get_json()
        assert response.get_json() == {"error": "player claim not found"}
        with app.app_context():
            assert db.session.get(PlayerProfileClaim, player_claim_id).status == "pending"

    def test_absent_and_unauthorized_player_claim_are_uniform_404(self, app, client):
        with app.app_context():
            _seed_official_claim(team_api_id=TEAM_ID, status="approved")
            _seed_affiliation(team_api_id=OTHER_TEAM_ID, status="pending")
            _, player_claim = _seed_player_claim(status="approved")
            player_claim_id = player_claim.id

        unauthorized = client.post(
            f"/api/me/club/player-claims/{player_claim_id}/vouch",
            headers=_user_headers("official@example.com"),
        )
        absent = client.post(
            "/api/me/club/player-claims/999999/vouch",
            headers=_user_headers("official@example.com"),
        )

        assert unauthorized.status_code == absent.status_code == 404
        assert unauthorized.get_json() == absent.get_json() == {"error": "player claim not found"}
        with app.app_context():
            assert db.session.get(PlayerProfileClaim, player_claim_id).status == "approved"

    def test_non_pending_player_claim_is_409(self, app, client):
        with app.app_context():
            _seed_official_claim(team_api_id=TEAM_ID, status="approved")
            _seed_affiliation(team_api_id=TEAM_ID, status="club_confirmed")
            _, player_claim = _seed_player_claim(status="approved")
            player_claim_id = player_claim.id

        response = client.post(
            f"/api/me/club/player-claims/{player_claim_id}/vouch",
            headers=_user_headers("official@example.com"),
        )

        assert response.status_code == 409, response.get_json()


class TestAdminClubClaims:
    def test_list_filters_status_and_includes_club_name_and_code(self, app, client):
        with app.app_context():
            _seed_team()
            _, pending = _seed_official_claim(team_api_id=TEAM_ID, code="AW-ADMINVISIBLE")
            _seed_official_claim(
                email="approved-official@example.com",
                team_api_id=OTHER_TEAM_ID,
                status="approved",
            )
            pending_id = pending.id

        response = client.get(
            "/api/admin/club-claims?status=pending",
            headers=_admin_headers(),
        )

        assert response.status_code == 200, response.get_json()
        claims = response.get_json()["claims"]
        assert [claim["id"] for claim in claims] == [pending_id]
        assert claims[0]["club_name"] == "Northbridge United"
        assert claims[0]["verification_code"] == "AW-ADMINVISIBLE"

    @pytest.mark.parametrize(
        ("starting_status", "action", "expected_status"),
        [
            ("pending", "approve", "approved"),
            ("pending", "reject", "rejected"),
            ("approved", "revoke", "revoked"),
        ],
    )
    def test_review_transitions(self, app, client, starting_status, action, expected_status):
        with app.app_context():
            _, claim = _seed_official_claim(team_api_id=TEAM_ID, status=starting_status)
            claim_id = claim.id

        response = client.post(
            f"/api/admin/club-claims/{claim_id}/review",
            json={"action": action, "note": "<b>Checked by operations</b>"},
            headers=_admin_headers(),
        )

        assert response.status_code == 200, response.get_json()
        reviewed = response.get_json()["claim"]
        assert reviewed["status"] == expected_status
        assert reviewed["reviewed_by"] == "admin@test.com"
        assert reviewed["reviewed_at"]
        assert "verification_code" not in reviewed
        with app.app_context():
            stored = db.session.get(ClubOfficialClaim, claim_id)
            assert stored.status == expected_status
            assert stored.review_note == "Checked by operations"

    @pytest.mark.parametrize(
        ("starting_status", "action"),
        [("approved", "approve"), ("approved", "reject"), ("pending", "revoke")],
    )
    def test_review_rejects_invalid_transition(self, app, client, starting_status, action):
        with app.app_context():
            _, claim = _seed_official_claim(team_api_id=TEAM_ID, status=starting_status)
            claim_id = claim.id

        response = client.post(
            f"/api/admin/club-claims/{claim_id}/review",
            json={"action": action},
            headers=_admin_headers(),
        )

        assert response.status_code == 409, response.get_json()

    def test_recheck_uses_stored_proof_url(self, app, client, monkeypatch):
        code = "AW-ABCDEFGH"
        proof_url = "https://youtube.com/@northbridge"
        with app.app_context():
            _, claim = _seed_official_claim(
                team_api_id=TEAM_ID,
                code=code,
                proof_url=proof_url,
                verification_status="code_not_found",
            )
            claim_id = claim.id
        calls = _fake_get(monkeypatch, [FakeResponse(f"About the club {code}".encode())])

        response = client.post(
            f"/api/admin/club-claims/{claim_id}/recheck",
            headers=_admin_headers(),
        )

        assert response.status_code == 200, response.get_json()
        checked = response.get_json()["claim"]
        assert checked["verification_status"] == "code_found"
        assert checked["verification_checked_at"]
        assert "verification_code" not in checked
        assert calls[0][0] == proof_url

    def test_recheck_without_proof_url_is_400_without_fetch(self, app, client, monkeypatch):
        with app.app_context():
            _, claim = _seed_official_claim(team_api_id=TEAM_ID, proof_url=None)
            claim_id = claim.id
        _forbid_fetch(monkeypatch)

        response = client.post(
            f"/api/admin/club-claims/{claim_id}/recheck",
            headers=_admin_headers(),
        )

        assert response.status_code == 400, response.get_json()


def test_club_claim_code_never_appears_in_public_showcase(app, client):
    club_secret = "AW-CLUBPUBLICSECRET"
    player_secret = "AW-PLAYERPUBLICSECRET"
    with app.app_context():
        _seed_official_claim(team_api_id=TEAM_ID, status="approved", code=club_secret)
        _seed_player_claim(status="approved", code=player_secret)
        _seed_affiliation(team_api_id=TEAM_ID, status="club_confirmed")

    response = client.get(f"/api/players/{PLAYER_ID}/showcase")

    assert response.status_code == 200, response.get_json()
    serialized = json.dumps(response.get_json())
    assert "verification_code" not in serialized
    assert club_secret not in serialized
    assert player_secret not in serialized
