"""Scout verification and content-report trust prerequisite tests."""

from pathlib import Path

import pytest
from flask import Flask
from src.auth import _ensure_user_account, issue_user_token
from src.extensions import limiter
from src.models.league import UserAccount, db
from src.models.trust import ContentReport, ScoutVerification
from src.routes.auth_routes import auth_bp
from src.routes.trust import trust_bp

ADMIN_KEY = "trust-admin-test-key"


@pytest.fixture
def trust_app(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", ADMIN_KEY)
    monkeypatch.setenv("ADMIN_IP_WHITELIST", "")

    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SECRET_KEY="trust-fixture-secret",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        RATELIMIT_ENABLED=True,
    )
    db.init_app(app)
    limiter.init_app(app)
    app.register_blueprint(trust_bp, url_prefix="/api")
    app.register_blueprint(auth_bp, url_prefix="/api")

    with app.app_context():
        limiter.reset()
        db.create_all()
        yield app
        limiter.reset()
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(trust_app):
    return trust_app.test_client()


def _user_headers(email="scout-fixture@example.com"):
    user = UserAccount.query.filter_by(email=email).first()
    if user is None:
        user = _ensure_user_account(email)
        db.session.commit()
    token = issue_user_token(email)["token"]
    return user, {"Authorization": f"Bearer {token}"}


def _admin_headers():
    token = issue_user_token("trust-admin@example.com", role="admin")["token"]
    return {"Authorization": f"Bearer {token}", "X-API-Key": ADMIN_KEY}


def _verification_payload(**overrides):
    payload = {
        "full_name": "Alex Scout",
        "organization": "Fixture Scouting Network",
        "role_title": "First-team scout",
        "statement": "I scout academy players for our recruitment team.",
        "evidence_urls": ["https://example.com/scouting-profile"],
    }
    payload.update(overrides)
    return payload


def _report_payload(index=1, **overrides):
    payload = {
        "subject_type": "player_profile",
        "subject_id": str(5000 + index),
        "reason_code": "misleading_information",
        "details": f"Fixture report details {index}",
    }
    payload.update(overrides)
    return payload


class TestScoutVerificationLifecycle:
    def test_apply_duplicate_approve_derive_and_revoke(self, client):
        user, headers = _user_headers()

        created = client.post("/api/scout/verification", json=_verification_payload(), headers=headers)
        assert created.status_code == 201, created.get_json()
        verification = created.get_json()["verification"]
        assert verification["status"] == "pending"
        assert verification["evidence_urls"] == ["https://example.com/scouting-profile"]

        duplicate = client.post("/api/scout/verification", json=_verification_payload(), headers=headers)
        assert duplicate.status_code == 409
        assert ScoutVerification.query.count() == 1

        queue = client.get("/api/admin/scout-verifications?status=pending", headers=_admin_headers())
        assert queue.status_code == 200
        assert queue.get_json()["total"] == 1
        assert queue.get_json()["verifications"][0]["user_email"] == user.email

        approved = client.post(
            f"/api/admin/scout-verifications/{verification['id']}/approve",
            json={"review_notes": "<b>Evidence confirmed</b>"},
            headers=_admin_headers(),
        )
        assert approved.status_code == 200, approved.get_json()
        approved_body = approved.get_json()["verification"]
        assert approved_body["status"] == "approved"
        assert approved_body["review_notes"] == "Evidence confirmed"
        assert approved_body["reviewed_by"] == "trust-admin@example.com"

        own_status = client.get("/api/scout/verification", headers=headers)
        assert own_status.status_code == 200
        assert own_status.get_json()["verification"]["status"] == "approved"

        me = client.get("/api/auth/me", headers=headers)
        assert me.status_code == 200
        assert me.get_json()["is_verified_scout"] is True
        assert user.to_dict()["is_verified_scout"] is True

        revoked = client.post(
            f"/api/admin/scout-verifications/{verification['id']}/revoke",
            json={"revocation_reason": "Organization withdrew the credential"},
            headers=_admin_headers(),
        )
        assert revoked.status_code == 200, revoked.get_json()
        assert revoked.get_json()["verification"]["status"] == "revoked"
        assert revoked.get_json()["verification"]["revocation_reason"] == "Organization withdrew the credential"

        me_after_revoke = client.get("/api/auth/me", headers=headers)
        assert me_after_revoke.status_code == 200
        assert me_after_revoke.get_json()["is_verified_scout"] is False
        assert user.to_dict()["is_verified_scout"] is False

    def test_rejected_resubmissions_are_limited_to_three_per_hour(self, client):
        _, headers = _user_headers("resubmit-scout@example.com")
        admin = _admin_headers()

        for attempt in range(3):
            submitted = client.post(
                "/api/scout/verification",
                json=_verification_payload(statement=f"Application attempt {attempt}"),
                headers=headers,
            )
            assert submitted.status_code == 201, submitted.get_json()
            verification_id = submitted.get_json()["verification"]["id"]
            rejected = client.post(
                f"/api/admin/scout-verifications/{verification_id}/reject",
                json={"review_notes": f"Insufficient evidence attempt {attempt}"},
                headers=admin,
            )
            assert rejected.status_code == 200, rejected.get_json()

        limited = client.post("/api/scout/verification", json=_verification_payload(), headers=headers)
        assert limited.status_code == 429
        assert ScoutVerification.query.count() == 3

    def test_verification_validation_and_admin_auth(self, client):
        assert client.post("/api/scout/verification", json=_verification_payload()).status_code == 401

        _, headers = _user_headers("validation-scout@example.com")
        insecure_url = client.post(
            "/api/scout/verification",
            json=_verification_payload(evidence_urls=["http://example.com/not-secure"]),
            headers=headers,
        )
        assert insecure_url.status_code == 400

        empty_evidence = client.post(
            "/api/scout/verification",
            json=_verification_payload(evidence_urls=[]),
            headers=headers,
        )
        assert empty_evidence.status_code == 400

        too_long = client.post(
            "/api/scout/verification",
            json=_verification_payload(full_name="x" * 201),
            headers=headers,
        )
        assert too_long.status_code == 400

        _, object_headers = _user_headers("object-validation-scout@example.com")
        non_object = client.post("/api/scout/verification", json=["not", "an", "object"], headers=object_headers)
        assert non_object.status_code == 400

        plain_user = client.get("/api/admin/scout-verifications", headers=headers)
        assert plain_user.status_code in (401, 403)
        invalid_filter = client.get("/api/admin/scout-verifications?status=unknown", headers=_admin_headers())
        assert invalid_filter.status_code == 400

    def test_review_notes_required_and_transitions_are_strict(self, client):
        _, headers = _user_headers("review-scout@example.com")
        created = client.post("/api/scout/verification", json=_verification_payload(), headers=headers)
        verification_id = created.get_json()["verification"]["id"]
        admin = _admin_headers()

        missing_notes = client.post(f"/api/admin/scout-verifications/{verification_id}/approve", json={}, headers=admin)
        assert missing_notes.status_code == 400
        non_object = client.post(
            f"/api/admin/scout-verifications/{verification_id}/approve", json=["not-an-object"], headers=admin
        )
        assert non_object.status_code == 400

        rejected = client.post(
            f"/api/admin/scout-verifications/{verification_id}/reject",
            json={"reason": "Identity could not be confirmed"},
            headers=admin,
        )
        assert rejected.status_code == 200
        invalid_approve = client.post(
            f"/api/admin/scout-verifications/{verification_id}/approve",
            json={"review_notes": "Late approval"},
            headers=admin,
        )
        assert invalid_approve.status_code == 409
        assert client.post("/api/admin/scout-verifications/999999/revoke", json={}, headers=admin).status_code == 404


class TestContentReports:
    def test_report_submit_list_resolve_and_sanitize(self, client):
        user, headers = _user_headers("reporter@example.com")
        created = client.post(
            "/api/reports",
            json=_report_payload(
                reason_code="MISLEADING_INFORMATION",
                details="<script>alert(1)</script><b>Wrong club history</b>",
            ),
            headers=headers,
        )
        assert created.status_code == 201, created.get_json()
        report = created.get_json()["report"]
        assert report["status"] == "open"
        assert report["reason_code"] == "misleading_information"
        assert "<script>" not in report["details"]
        assert "<b>" not in report["details"]
        assert "Wrong club history" in report["details"]

        listed = client.get("/api/admin/reports?status=open", headers=_admin_headers())
        assert listed.status_code == 200
        listed_body = listed.get_json()
        assert listed_body["total"] == 1
        assert listed_body["reports"][0]["reporter_user_id"] == user.id
        assert listed_body["reports"][0]["reporter_email"] == user.email

        resolved = client.post(
            f"/api/admin/reports/{report['id']}/resolve",
            json={"status": "resolved", "resolution_notes": "<i>Profile corrected</i>"},
            headers=_admin_headers(),
        )
        assert resolved.status_code == 200, resolved.get_json()
        resolved_report = resolved.get_json()["report"]
        assert resolved_report["status"] == "resolved"
        assert resolved_report["resolution_notes"] == "Profile corrected"
        assert resolved_report["resolved_at"] is not None

        resolved_queue = client.get("/api/admin/reports?status=resolved", headers=_admin_headers())
        assert resolved_queue.status_code == 200
        assert [row["id"] for row in resolved_queue.get_json()["reports"]] == [report["id"]]
        repeated = client.post(
            f"/api/admin/reports/{report['id']}/resolve",
            json={"status": "dismissed", "resolution_notes": "Second decision"},
            headers=_admin_headers(),
        )
        assert repeated.status_code == 409

    @pytest.mark.parametrize(
        "payload",
        [
            _report_payload(subject_type="article"),
            _report_payload(subject_id=123),
            _report_payload(reason_code="x" * 81),
            _report_payload(details="x" * 2001),
            _report_payload(details={"not": "text"}),
        ],
    )
    def test_report_validation(self, client, payload):
        _, headers = _user_headers("report-validation@example.com")
        response = client.post("/api/reports", json=payload, headers=headers)
        assert response.status_code == 400

    def test_report_and_admin_endpoints_require_auth(self, client):
        assert client.post("/api/reports", json=_report_payload()).status_code == 401
        _, user_headers = _user_headers("plain-report-user@example.com")
        assert client.get("/api/admin/reports", headers=user_headers).status_code in (401, 403)

        non_object = client.post("/api/reports", json=["not-an-object"], headers=user_headers)
        assert non_object.status_code == 400

    def test_resolution_validation_and_filters(self, client):
        _, headers = _user_headers("resolution-validation@example.com")
        report_id = client.post("/api/reports", json=_report_payload(), headers=headers).get_json()["report"]["id"]
        admin = _admin_headers()

        invalid_filter = client.get("/api/admin/reports?status=pending", headers=admin)
        assert invalid_filter.status_code == 400
        invalid_status = client.post(
            f"/api/admin/reports/{report_id}/resolve",
            json={"status": "reviewing", "resolution_notes": "Not terminal"},
            headers=admin,
        )
        assert invalid_status.status_code == 400
        missing_notes = client.post(
            f"/api/admin/reports/{report_id}/resolve",
            json={"status": "dismissed"},
            headers=admin,
        )
        assert missing_notes.status_code == 400
        non_object = client.post(f"/api/admin/reports/{report_id}/resolve", json=["not-an-object"], headers=admin)
        assert non_object.status_code == 400
        dismissed = client.post(
            f"/api/admin/reports/{report_id}/resolve",
            json={"status": "dismissed", "resolution_notes": "Report was not substantiated"},
            headers=admin,
        )
        assert dismissed.status_code == 200
        assert dismissed.get_json()["report"]["status"] == "dismissed"
        assert (
            client.post(
                "/api/admin/reports/999999/resolve",
                json={"status": "dismissed", "resolution_notes": "Not found"},
                headers=admin,
            ).status_code
            == 404
        )

    def test_report_rate_limit_is_per_authenticated_user(self, client):
        _, headers = _user_headers("rate-limited-reporter@example.com")
        for index in range(10):
            response = client.post("/api/reports", json=_report_payload(index=index), headers=headers)
            assert response.status_code == 201, response.get_json()

        limited = client.post("/api/reports", json=_report_payload(index=99), headers=headers)
        assert limited.status_code == 429

        _, other_headers = _user_headers("independent-reporter@example.com")
        independent = client.post("/api/reports", json=_report_payload(index=100), headers=other_headers)
        assert independent.status_code == 201
        assert ContentReport.query.count() == 11


def test_fc01_is_guarded_single_parent_and_enables_rls_for_both_tables():
    migration = Path(__file__).resolve().parents[1] / "migrations" / "versions" / "fc01_trust_prerequisites.py"
    source = migration.read_text()
    assert 'down_revision = "tre01"' in source
    assert '"scout_verifications"' in source
    assert '"content_reports"' in source
    assert "for table_name in NEW_TABLES" in source
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "if not table_exists" in source
