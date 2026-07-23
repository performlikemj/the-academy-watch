"""FC-B2/B3 contact-rail lifecycle, routing, privacy, and migration tests."""

from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from flask import Flask
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from src.auth import _ensure_user_account, issue_user_token
from src.extensions import limiter
from src.models.contact import ContactAuditEvent, ContactMessage, ContactOutcome, ContactRequest
from src.models.follow import Follow, FollowList
from src.models.league import UserAccount, db
from src.models.scout_watchlist import ScoutWatchlistEntry
from src.models.showcase import PlayerProfileClaim
from src.models.trust import ContentReport, ScoutVerification
from src.services.contact import utcnow

ADMIN_KEY = "contact-admin-test-key"


@pytest.fixture
def contact_app(monkeypatch):
    monkeypatch.setenv("CONTACT_RAIL_ENABLED", "true")
    monkeypatch.setenv("CONTACT_REQUEST_EXPIRY_DAYS", "14")
    monkeypatch.setenv("CONTACT_DECLINE_COOLDOWN_DAYS", "30")
    monkeypatch.setenv("ADMIN_API_KEY", ADMIN_KEY)
    monkeypatch.setenv("ADMIN_IP_WHITELIST", "")

    from src.routes.contact import contact_bp
    from src.routes.showcase import showcase_bp
    from src.routes.trust import trust_bp

    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SECRET_KEY="contact-fixture-secret",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        RATELIMIT_ENABLED=True,
    )
    db.init_app(app)
    limiter.init_app(app)
    app.register_blueprint(showcase_bp, url_prefix="/api")
    app.register_blueprint(contact_bp, url_prefix="/api")
    app.register_blueprint(trust_bp, url_prefix="/api")

    with app.app_context():
        limiter.reset()
        # Keep FC-B3's narrow registry bridges deterministic even when another
        # collected test module registers the full F2 schemas in shared metadata.
        with db.engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE club_programs ("
                    "id INTEGER PRIMARY KEY, name VARCHAR(180) NOT NULL, contact_email VARCHAR(254))"
                )
            )
            connection.execute(
                text(
                    "CREATE TABLE club_program_managers ("
                    "id INTEGER PRIMARY KEY, program_id INTEGER NOT NULL, "
                    "user_account_id INTEGER NOT NULL, status VARCHAR(20) NOT NULL)"
                )
            )
        db.create_all()
        yield app
        limiter.reset()
        db.session.remove()
        db.drop_all()
        with db.engine.begin() as connection:
            connection.execute(text("DROP TABLE IF EXISTS club_program_managers"))
            connection.execute(text("DROP TABLE IF EXISTS club_programs"))


@pytest.fixture
def client(contact_app):
    return contact_app.test_client()


def _headers(email: str):
    user = UserAccount.query.filter_by(email=email).first()
    if user is None:
        user = _ensure_user_account(email)
        db.session.commit()
    return user, {"Authorization": f"Bearer {issue_user_token(email)['token']}"}


def _admin_headers():
    token = issue_user_token("contact-admin@example.com", role="admin")["token"]
    return {"Authorization": f"Bearer {token}", "X-API-Key": ADMIN_KEY}


def _verified_scout(email: str):
    user, headers = _headers(email)
    db.session.add(
        ScoutVerification(
            user_account_id=user.id,
            full_name="Alex Scout",
            organization="Fixture Recruitment",
            role_title="Scout",
            statement="I recruit adult academy players.",
            evidence_urls=["https://example.com/scout"],
            status="approved",
            reviewed_at=utcnow(),
        )
    )
    db.session.commit()
    return user, headers


def _claim(
    email: str,
    player_api_id: int,
    *,
    status="approved",
    relationship_type="player",
    contract_status=None,
    current_club_name=None,
    club_program_id=None,
):
    user, headers = _headers(email)
    contract_status = contract_status or ("free_agent" if relationship_type == "player" else "unknown")
    claim = PlayerProfileClaim(
        user_account_id=user.id,
        player_api_id=player_api_id,
        relationship_type=relationship_type,
        contract_status=contract_status,
        current_club_name=current_club_name,
        club_program_id=club_program_id,
        status=status,
        reviewed_at=utcnow() if status == "approved" else None,
    )
    db.session.add(claim)
    db.session.commit()
    return user, headers, claim


def _create(
    client,
    headers,
    player_api_id: int,
    message="Hello from <b>recruitment</b>",
    *,
    permission_attestation=None,
):
    payload = {"player_api_id": player_api_id, "message": message}
    if permission_attestation is not None:
        payload["permission_attestation"] = permission_attestation
    return client.post(
        "/api/contact/requests",
        json=payload,
        headers=headers,
    )


def _club_program(program_id: int, name: str, *, contact_email=None):
    db.session.execute(
        text("INSERT INTO club_programs (id, name, contact_email) VALUES (:program_id, :name, :contact_email)"),
        {"program_id": program_id, "name": name, "contact_email": contact_email},
    )
    db.session.commit()


def _club_manager(program_id: int, email: str, *, status="active"):
    user, headers = _headers(email)
    next_id = db.session.execute(text("SELECT coalesce(max(id), 0) + 1 FROM club_program_managers")).scalar_one()
    db.session.execute(
        text(
            "INSERT INTO club_program_managers (id, program_id, user_account_id, status) "
            "VALUES (:id, :program_id, :user_account_id, :status)"
        ),
        {"id": next_id, "program_id": program_id, "user_account_id": user.id, "status": status},
    )
    db.session.commit()
    return user, headers


def _seed_contact(client, *, suffix="base", player_api_id=5001):
    scout, scout_headers = _verified_scout(f"scout-{suffix}@example.com")
    player, player_headers, claim = _claim(f"player-{suffix}@example.com", player_api_id)
    created = _create(client, scout_headers, player_api_id)
    assert created.status_code == 201, created.get_json()
    return scout, scout_headers, player, player_headers, claim, created.get_json()["contact_request"]


class TestContactLifecycle:
    def test_create_accept_messages_outcomes_and_every_audit(self, client):
        scout, scout_headers, player, player_headers, claim, request_payload = _seed_contact(client)
        request_id = request_payload["id"]
        UUID(request_id)
        assert request_payload["message"] == "Hello from recruitment"
        assert request_payload["status"] == "pending"
        assert request_payload["participants"]["scout"]["display_name"] == scout.display_name
        assert request_payload["participants"]["player"]["display_name"] == player.display_name
        stored_request = ContactRequest.query.one()
        assert stored_request.claim_id == claim.id
        assert stored_request.expires_at - stored_request.created_at == timedelta(days=14)

        inbox = client.get("/api/contact/requests?box=inbox&limit=1&offset=0", headers=player_headers)
        assert inbox.status_code == 200
        assert inbox.get_json()["total"] == 1
        assert inbox.get_json()["requests"][0]["id"] == request_id

        accepted = client.post(f"/api/contact/requests/{request_id}/accept", headers=player_headers)
        assert accepted.status_code == 200
        assert accepted.get_json()["contact_request"]["status"] == "accepted"

        scout_message = client.post(
            f"/api/contact/requests/{request_id}/messages",
            json={"body": "Can we arrange a <script>alert(1)</script> call?"},
            headers=scout_headers,
        )
        assert scout_message.status_code == 201, scout_message.get_json()
        scout_message_payload = scout_message.get_json()["message"]
        UUID(scout_message_payload["id"])
        assert "<" not in scout_message_payload["body"]
        assert scout_message_payload["sender_role"] == "scout"

        player_message = client.post(
            f"/api/contact/requests/{request_id}/messages",
            json={"body": "Yes, tomorrow works."},
            headers=player_headers,
        )
        assert player_message.status_code == 201
        assert player_message.get_json()["message"]["sender_role"] == "player"

        thread = client.get(f"/api/contact/requests/{request_id}/messages", headers=player_headers)
        assert thread.status_code == 200
        assert thread.get_json()["total"] == 2
        assert [row["sender_role"] for row in thread.get_json()["messages"]] == ["scout", "player"]
        second_page = client.get(
            f"/api/contact/requests/{request_id}/messages?limit=1&offset=1",
            headers=player_headers,
        )
        assert second_page.status_code == 200
        assert second_page.get_json()["total"] == 2
        assert [row["sender_role"] for row in second_page.get_json()["messages"]] == ["player"]

        contacted = client.post(
            f"/api/contact/requests/{request_id}/outcome",
            json={
                "stage": "contacted",
                "notes": "<b>Intro call</b> complete",
                "occurred_at": "2026-07-16T09:30:00Z",
            },
            headers=player_headers,
        )
        assert contacted.status_code == 201, contacted.get_json()
        assert contacted.get_json()["outcome"]["notes"] == "Intro call complete"

        signed = client.post(
            f"/api/contact/requests/{request_id}/outcome",
            json={"stage": "signed", "notes": "Terms agreed"},
            headers=scout_headers,
        )
        assert signed.status_code == 201
        assert signed.get_json()["contact_request"]["latest_outcome"]["stage"] == "signed"

        historical = client.post(
            f"/api/contact/requests/{request_id}/outcome",
            json={
                "stage": "trial_scheduled",
                "notes": "Backfilled historical milestone",
                "occurred_at": "2026-01-10T12:00:00Z",
            },
            headers=player_headers,
        )
        assert historical.status_code == 201
        assert historical.get_json()["contact_request"]["latest_outcome"]["stage"] == "signed"
        assert ContactOutcome.query.count() == 3

        events = ContactAuditEvent.query.order_by(ContactAuditEvent.id).all()
        assert [event.event_type for event in events] == [
            "created",
            "accepted",
            "message_sent",
            "message_sent",
            "outcome_reported",
            "outcome_reported",
            "outcome_reported",
        ]
        assert [event.actor_user_id for event in events] == [
            scout.id,
            player.id,
            scout.id,
            player.id,
            player.id,
            scout.id,
            player.id,
        ]

    def test_message_sender_role_is_historical_not_recomputed_from_claim_state(self, client):
        _, scout_headers, _, player_headers, claim, request_payload = _seed_contact(
            client,
            suffix="stable-role",
            player_api_id=5051,
        )
        request_id = request_payload["id"]
        assert client.post(f"/api/contact/requests/{request_id}/accept", headers=player_headers).status_code == 200
        sent = client.post(
            f"/api/contact/requests/{request_id}/messages",
            json={"body": "This was sent as the player."},
            headers=player_headers,
        )
        assert sent.status_code == 201
        assert sent.get_json()["message"]["sender_role"] == "player"

        claim.status = "revoked"
        db.session.commit()
        thread = client.get(f"/api/contact/requests/{request_id}/messages", headers=scout_headers)
        assert thread.status_code == 200
        assert thread.get_json()["messages"][0]["sender_role"] == "player"
        assert ContactMessage.query.one().sender_role == "player"

    def test_decline_cooldown_then_rerequest_after_tunable_window(self, client, monkeypatch):
        _, scout_headers, _, player_headers, _, request_payload = _seed_contact(
            client, suffix="decline", player_api_id=5101
        )
        request_id = request_payload["id"]
        declined = client.post(f"/api/contact/requests/{request_id}/decline", headers=player_headers)
        assert declined.status_code == 200
        assert declined.get_json()["contact_request"]["status"] == "declined"

        cooldown = _create(client, scout_headers, 5101)
        assert cooldown.status_code == 409
        assert cooldown.get_json()["code"] == "decline_cooldown_active"

        monkeypatch.setenv("CONTACT_DECLINE_COOLDOWN_DAYS", "1")
        row = db.session.get(ContactRequest, request_id)
        row.responded_at = utcnow() - timedelta(days=2)
        db.session.commit()
        retried = _create(client, scout_headers, 5101, message="Following up after the cooldown")
        assert retried.status_code == 201, retried.get_json()
        assert ContactRequest.query.count() == 2
        assert [event.event_type for event in ContactAuditEvent.query.order_by(ContactAuditEvent.id)] == [
            "created",
            "declined",
            "created",
        ]

    def test_withdraw_is_initiating_scout_only(self, client):
        _, scout_headers, _, player_headers, _, request_payload = _seed_contact(
            client, suffix="withdraw", player_api_id=5201
        )
        request_id = request_payload["id"]
        forbidden = client.post(f"/api/contact/requests/{request_id}/withdraw", headers=player_headers)
        assert forbidden.status_code == 403
        withdrawn = client.post(f"/api/contact/requests/{request_id}/withdraw", headers=scout_headers)
        assert withdrawn.status_code == 200
        assert withdrawn.get_json()["contact_request"]["status"] == "withdrawn"
        assert [event.event_type for event in ContactAuditEvent.query.order_by(ContactAuditEvent.id)] == [
            "created",
            "withdrawn",
        ]

    def test_lazy_expiry_is_once_only_and_unblocks_new_request(self, client):
        _, scout_headers, _, player_headers, _, request_payload = _seed_contact(
            client, suffix="expiry", player_api_id=5301
        )
        request_id = request_payload["id"]
        row = db.session.get(ContactRequest, request_id)
        row.expires_at = utcnow() - timedelta(seconds=1)
        db.session.commit()

        first_read = client.get("/api/contact/requests?box=sent", headers=scout_headers)
        assert first_read.status_code == 200
        assert first_read.get_json()["requests"][0]["status"] == "expired"
        expiry_events = ContactAuditEvent.query.filter_by(event_type="expired").all()
        assert len(expiry_events) == 1
        assert expiry_events[0].actor_user_id is None

        second_read = client.get("/api/contact/requests?box=inbox", headers=player_headers)
        assert second_read.status_code == 200
        assert len(ContactAuditEvent.query.filter_by(event_type="expired").all()) == 1

        replacement = _create(client, scout_headers, 5301, message="A fresh request after expiry")
        assert replacement.status_code == 201, replacement.get_json()
        assert ContactRequest.query.filter_by(status="pending").count() == 1

    def test_request_expiry_window_is_env_tunable(self, client, monkeypatch):
        monkeypatch.setenv("CONTACT_REQUEST_EXPIRY_DAYS", "2")
        _seed_contact(client, suffix="expiry-window", player_api_id=5351)
        row = ContactRequest.query.one()
        assert row.expires_at - row.created_at == timedelta(days=2)

    def test_duplicate_pending_and_accepted_requests_are_blocked(self, client):
        scout, scout_headers, _, player_headers, claim, request_payload = _seed_contact(
            client, suffix="duplicate", player_api_id=5401
        )
        duplicate = _create(client, scout_headers, 5401)
        assert duplicate.status_code == 409
        assert duplicate.get_json()["code"] == "active_request_exists"
        assert ContactRequest.query.count() == 1
        assert ContactAuditEvent.query.filter_by(event_type="created").count() == 1

        # The database partial unique index remains the final concurrency guard,
        # independently of the route's friendly preflight check.
        now = utcnow()
        db.session.add(
            ContactRequest(
                scout_user_id=scout.id,
                player_api_id=5401,
                claim_id=claim.id,
                message="Direct duplicate",
                status="pending",
                created_at=now,
                expires_at=now + timedelta(days=14),
            )
        )
        with pytest.raises(IntegrityError):
            db.session.flush()
        db.session.rollback()
        assert ContactRequest.query.count() == 1

        accepted = client.post(
            f"/api/contact/requests/{request_payload['id']}/accept",
            headers=player_headers,
        )
        assert accepted.status_code == 200
        still_duplicate = _create(client, scout_headers, 5401)
        assert still_duplicate.status_code == 409
        assert ContactRequest.query.count() == 1


class TestContactAuthorizationAndFlag:
    def test_unverified_scout_and_unclaimed_player_have_clear_codes(self, client):
        _, unverified_headers = _headers("unverified@example.com")
        _claim("claimed-player@example.com", 5501)
        unverified = _create(client, unverified_headers, 5501)
        assert unverified.status_code == 403
        assert unverified.get_json()["code"] == "scout_not_verified"

        _, verified_headers = _verified_scout("verified-no-target@example.com")
        unclaimed = _create(client, verified_headers, 999999)
        assert unclaimed.status_code == 403
        assert unclaimed.get_json()["code"] == "player_not_claimable"

        _claim("agent-only@example.com", 5502, relationship_type="agent")
        agent_claim = _create(client, verified_headers, 5502)
        assert agent_claim.status_code == 403
        assert agent_claim.get_json()["code"] == "player_not_claimable"

    def test_thread_and_outcome_hide_request_from_non_participant(self, client):
        _, scout_headers, _, player_headers, _, request_payload = _seed_contact(
            client, suffix="private", player_api_id=5601
        )
        request_id = request_payload["id"]
        _, stranger_headers = _headers("stranger@example.com")

        assert client.get(f"/api/contact/requests/{request_id}/messages", headers=scout_headers).status_code == 409
        assert (
            client.post(
                f"/api/contact/requests/{request_id}/messages",
                json={"body": "Too soon"},
                headers=player_headers,
            ).status_code
            == 409
        )
        assert client.post(f"/api/contact/requests/{request_id}/accept", headers=scout_headers).status_code == 403
        assert client.post(f"/api/contact/requests/{request_id}/accept", headers=stranger_headers).status_code == 403
        assert client.get(f"/api/contact/requests/{request_id}/messages", headers=stranger_headers).status_code == 404
        assert (
            client.post(
                f"/api/contact/requests/{request_id}/messages",
                json={"body": "Intrusion"},
                headers=stranger_headers,
            ).status_code
            == 404
        )
        assert (
            client.post(
                f"/api/contact/requests/{request_id}/outcome",
                json={"stage": "signed"},
                headers=stranger_headers,
            ).status_code
            == 404
        )

        assert client.post(f"/api/contact/requests/{request_id}/accept", headers=player_headers).status_code == 200
        assert client.get(f"/api/contact/requests/{request_id}/messages", headers=stranger_headers).status_code == 404

    def test_revoked_claimant_loses_direct_request_access(self, client):
        _, scout_headers, _, player_headers, claim, request_payload = _seed_contact(
            client, suffix="revoked", player_api_id=5651
        )
        request_id = request_payload["id"]
        claim.status = "revoked"
        db.session.commit()

        inbox = client.get("/api/contact/requests?box=inbox", headers=player_headers)
        assert inbox.status_code == 200
        assert inbox.get_json()["requests"] == []
        assert client.post(f"/api/contact/requests/{request_id}/accept", headers=player_headers).status_code == 403
        assert client.get(f"/api/contact/requests/{request_id}/messages", headers=player_headers).status_code == 404

        # The initiating scout retains their own historical sent record.
        sent = client.get("/api/contact/requests?box=sent", headers=scout_headers)
        assert sent.status_code == 200
        assert sent.get_json()["requests"][0]["id"] == request_id

    def test_flag_off_hides_every_new_user_route_before_auth(self, client, monkeypatch):
        monkeypatch.setenv("CONTACT_RAIL_ENABLED", "false")
        hidden_routes = (
            ("POST", "/api/contact/requests", {"player_api_id": 1, "message": "hidden"}),
            ("GET", "/api/contact/requests?box=sent", None),
            ("GET", "/api/contact/requests?box=inbox", None),
            ("GET", "/api/contact/requests?box=club", None),
            ("POST", "/api/contact/requests/opaque-id/accept", None),
            ("POST", "/api/contact/requests/opaque-id/decline", None),
            ("POST", "/api/contact/requests/opaque-id/club-consent", {"action": "grant"}),
            ("POST", "/api/contact/requests/opaque-id/withdraw", None),
            ("GET", "/api/contact/requests/opaque-id/messages", None),
            ("POST", "/api/contact/requests/opaque-id/messages", {"body": "hidden"}),
            ("POST", "/api/contact/requests/opaque-id/outcome", {"stage": "contacted"}),
            ("GET", "/api/showcase/mine/interest-signals", None),
            ("OPTIONS", "/api/contact/requests", None),
            ("DELETE", "/api/contact/requests", None),
            ("OPTIONS", "/api/showcase/mine/interest-signals", None),
        )
        for method, path, payload in hidden_routes:
            response = client.open(path, method=method, json=payload)
            assert response.status_code == 404, (method, path, response.get_json())

        monkeypatch.delenv("CONTACT_RAIL_ENABLED")
        assert client.get("/api/showcase/mine/interest-signals").status_code == 404

    @pytest.mark.parametrize("flag_state", ["true", "false"])
    def test_participant_can_report_message_regardless_of_contact_flag(self, client, monkeypatch, flag_state):
        _, scout_headers, _, player_headers, _, request_payload = _seed_contact(
            client, suffix="report", player_api_id=5701
        )
        request_id = request_payload["id"]
        assert client.post(f"/api/contact/requests/{request_id}/accept", headers=player_headers).status_code == 200
        message = client.post(
            f"/api/contact/requests/{request_id}/messages",
            json={"body": "A reportable participant message"},
            headers=scout_headers,
        ).get_json()["message"]

        monkeypatch.setenv("CONTACT_RAIL_ENABLED", flag_state)
        report = client.post(
            "/api/reports",
            json={
                "subject_type": "contact_message",
                "subject_id": message["id"],
                "reason_code": "participant_safety",
                "details": "Please review this message.",
            },
            headers=player_headers,
        )
        assert report.status_code == 201, report.get_json()
        assert report.get_json()["report"]["subject_id"] == message["id"]
        assert ContentReport.query.filter_by(subject_type="contact_message").count() == 1

        admin_queue = client.get("/api/admin/reports?status=open", headers=_admin_headers())
        assert admin_queue.status_code == 200
        assert admin_queue.get_json()["reports"][0]["subject_id"] == message["id"]


class TestContractStatusRouting:
    def test_free_agent_keeps_direct_behavior(self, client):
        _, scout_headers = _verified_scout("direct-routing-scout@example.com")
        _claim("direct-routing-player@example.com", 5801, contract_status="free_agent")

        response = _create(client, scout_headers, 5801)

        assert response.status_code == 201
        payload = response.get_json()["contact_request"]
        assert payload["routing_mode"] == "direct"
        assert payload["club_program_id"] is None
        assert payload["club_consent_status"] is None
        assert payload["permission_attestation"] is False

    def test_club_included_requires_both_gates_and_supports_three_party_thread(self, client):
        _club_program(101, "On Platform FC")
        club_manager, club_headers = _club_manager(101, "included-manager@example.com")
        scout, scout_headers = _verified_scout("included-scout@example.com")
        player, player_headers, _ = _claim(
            "included-player@example.com",
            5802,
            contract_status="contracted",
            current_club_name="On Platform FC",
            club_program_id=101,
        )

        created = _create(client, scout_headers, 5802)
        assert created.status_code == 201, created.get_json()
        request_payload = created.get_json()["contact_request"]
        request_id = request_payload["id"]
        assert request_payload["routing_mode"] == "club_included"
        assert request_payload["club_consent_status"] == "pending"
        assert request_payload["participants"]["club"] == {
            "club_program_id": 101,
            "display_name": "On Platform FC",
        }

        club_box = client.get("/api/contact/requests?box=club", headers=club_headers)
        assert club_box.status_code == 200
        assert [row["id"] for row in club_box.get_json()["requests"]] == [request_id]

        accepted = client.post(f"/api/contact/requests/{request_id}/accept", headers=player_headers)
        assert accepted.status_code == 200
        blocked = client.get(f"/api/contact/requests/{request_id}/messages", headers=scout_headers)
        assert blocked.status_code == 409
        assert blocked.get_json()["code"] == "club_consent_required"

        consent = client.post(
            f"/api/contact/requests/{request_id}/club-consent",
            json={"action": "grant", "note": "<b>Authorized</b> by the sporting director"},
            headers=club_headers,
        )
        assert consent.status_code == 200, consent.get_json()
        consent_payload = consent.get_json()["contact_request"]
        assert consent_payload["club_consent_status"] == "granted"
        assert consent_payload["club_consent_note"] == "Authorized by the sporting director"
        assert consent_payload["messaging_open"] is True

        club_message = client.post(
            f"/api/contact/requests/{request_id}/messages",
            json={"body": "The club is included in this conversation."},
            headers=club_headers,
        )
        assert club_message.status_code == 201, club_message.get_json()
        assert club_message.get_json()["message"]["sender_role"] == "club"

        thread = client.get(f"/api/contact/requests/{request_id}/messages", headers=player_headers)
        assert thread.status_code == 200
        assert [row["sender_role"] for row in thread.get_json()["messages"]] == ["club"]
        events = ContactAuditEvent.query.order_by(ContactAuditEvent.id).all()
        assert [event.event_type for event in events] == [
            "created",
            "accepted",
            "club_consent_granted",
            "message_sent",
        ]
        assert [event.actor_user_id for event in events] == [scout.id, player.id, club_manager.id, club_manager.id]

    def test_club_grant_alone_does_not_open_messaging(self, client):
        _club_program(102, "Consent First FC")
        _, club_headers = _club_manager(102, "consent-first-manager@example.com")
        _, scout_headers = _verified_scout("consent-first-scout@example.com")
        _, player_headers, _ = _claim(
            "consent-first-player@example.com",
            5803,
            contract_status="contracted",
            club_program_id=102,
        )
        request_id = _create(client, scout_headers, 5803).get_json()["contact_request"]["id"]

        granted = client.post(
            f"/api/contact/requests/{request_id}/club-consent",
            json={"action": "grant"},
            headers=club_headers,
        )
        assert granted.status_code == 200
        assert granted.get_json()["contact_request"]["messaging_open"] is False
        assert client.get(f"/api/contact/requests/{request_id}/messages", headers=club_headers).status_code == 409

        accepted = client.post(f"/api/contact/requests/{request_id}/accept", headers=player_headers)
        assert accepted.status_code == 200
        assert accepted.get_json()["contact_request"]["messaging_open"] is True

    def test_club_decline_blocks_messaging_and_uses_existing_cooldown(self, client):
        _club_program(103, "Decline FC")
        club_manager, club_headers = _club_manager(103, "decline-manager@example.com")
        _, scout_headers = _verified_scout("decline-routing-scout@example.com")
        _, player_headers, _ = _claim(
            "decline-routing-player@example.com",
            5804,
            contract_status="contracted",
            club_program_id=103,
        )
        request_id = _create(client, scout_headers, 5804).get_json()["contact_request"]["id"]
        assert client.post(f"/api/contact/requests/{request_id}/accept", headers=player_headers).status_code == 200

        declined = client.post(
            f"/api/contact/requests/{request_id}/club-consent",
            json={"action": "decline", "note": "No permission"},
            headers=club_headers,
        )
        assert declined.status_code == 200
        assert declined.get_json()["contact_request"]["status"] == "declined"
        assert declined.get_json()["contact_request"]["messaging_open"] is False
        blocked = client.get(f"/api/contact/requests/{request_id}/messages", headers=scout_headers)
        assert blocked.status_code == 409
        assert blocked.get_json()["code"] == "club_consent_declined"
        event = ContactAuditEvent.query.filter_by(event_type="club_consent_declined").one()
        assert event.actor_user_id == club_manager.id
        assert event.event_metadata == {"note": "No permission"}

        replacement = _create(client, scout_headers, 5804, message="New request after club decline")
        assert replacement.status_code == 409
        assert replacement.get_json()["code"] == "decline_cooldown_active"
        assert ContactRequest.query.count() == 1

        row = db.session.get(ContactRequest, request_id)
        row.responded_at = utcnow() - timedelta(days=31)
        db.session.commit()
        after_cooldown = _create(client, scout_headers, 5804, message="New request after cooldown")
        assert after_cooldown.status_code == 201, after_cooldown.get_json()
        assert ContactRequest.query.count() == 2

    def test_player_accepted_club_pending_request_still_expires(self, client):
        _club_program(107, "Unresponsive Club FC")
        _, club_headers = _club_manager(107, "unresponsive-manager@example.com")
        _, scout_headers = _verified_scout("unresponsive-scout@example.com")
        _, player_headers, _ = _claim(
            "unresponsive-player@example.com",
            5810,
            contract_status="contracted",
            club_program_id=107,
        )
        request_id = _create(client, scout_headers, 5810).get_json()["contact_request"]["id"]
        assert client.post(f"/api/contact/requests/{request_id}/accept", headers=player_headers).status_code == 200
        row = db.session.get(ContactRequest, request_id)
        row.expires_at = utcnow() - timedelta(seconds=1)
        db.session.commit()

        late_grant = client.post(
            f"/api/contact/requests/{request_id}/club-consent",
            json={"action": "grant"},
            headers=club_headers,
        )
        assert late_grant.status_code == 409
        assert late_grant.get_json()["code"] == "request_expired"
        listed = client.get("/api/contact/requests?box=sent", headers=scout_headers)
        assert listed.status_code == 200
        assert listed.get_json()["requests"][0]["status"] == "expired"
        assert ContactAuditEvent.query.filter_by(event_type="expired").count() == 1
        replacement = _create(client, scout_headers, 5810)
        assert replacement.status_code == 201, replacement.get_json()

    def test_off_platform_requires_strict_permission_then_player_acceptance_opens(self, client):
        _, scout_headers = _verified_scout("notified-scout@example.com")
        _, player_headers, _ = _claim(
            "notified-player@example.com",
            5805,
            contract_status="contracted",
            current_club_name="Off Platform FC",
        )

        missing = _create(client, scout_headers, 5805)
        assert missing.status_code == 400
        assert missing.get_json()["code"] == "attestation_required"
        assert "current club's permission" in missing.get_json()["error"]
        string_true = _create(client, scout_headers, 5805, permission_attestation="true")
        assert string_true.status_code == 400
        assert string_true.get_json()["code"] == "attestation_required"

        created = _create(client, scout_headers, 5805, permission_attestation=True)
        assert created.status_code == 201, created.get_json()
        payload = created.get_json()["contact_request"]
        request_id = payload["id"]
        assert payload["routing_mode"] == "club_notified"
        assert payload["permission_attestation"] is True
        assert payload["permission_attested_at"] is not None
        assert [event.event_type for event in ContactAuditEvent.query.order_by(ContactAuditEvent.id)] == [
            "created",
            "scout_permission_attested",
        ]

        assert client.post(f"/api/contact/requests/{request_id}/accept", headers=player_headers).status_code == 200
        message = client.post(
            f"/api/contact/requests/{request_id}/messages",
            json={"body": "Permission is recorded."},
            headers=scout_headers,
        )
        assert message.status_code == 201

    def test_unknown_is_conservatively_routed_as_contracted(self, client):
        _, scout_headers = _verified_scout("unknown-routing-scout@example.com")
        _claim("unknown-routing-player@example.com", 5806, contract_status="unknown")

        missing = _create(client, scout_headers, 5806)
        assert missing.status_code == 400
        assert missing.get_json()["code"] == "attestation_required"
        created = _create(client, scout_headers, 5806, permission_attestation=True)
        assert created.status_code == 201
        assert created.get_json()["contact_request"]["routing_mode"] == "club_notified"

    def test_unknown_with_managed_link_uses_club_included_path(self, client):
        _club_program(108, "Unknown Status FC")
        _club_manager(108, "unknown-status-manager@example.com")
        _, scout_headers = _verified_scout("unknown-managed-scout@example.com")
        _claim(
            "unknown-managed-player@example.com",
            5811,
            contract_status="unknown",
            club_program_id=108,
        )

        created = _create(client, scout_headers, 5811)
        assert created.status_code == 201, created.get_json()
        payload = created.get_json()["contact_request"]
        assert payload["routing_mode"] == "club_included"
        assert payload["club_consent_status"] == "pending"
        assert payload["permission_attestation"] is False

    def test_club_box_and_consent_are_scoped_to_active_program_grants(self, client):
        _club_program(104, "Manager One FC")
        _club_program(105, "Manager Two FC")
        _, manager_one_headers = _club_manager(104, "manager-one@example.com")
        _, manager_two_headers = _club_manager(105, "manager-two@example.com")
        _, revoked_manager_headers = _club_manager(104, "revoked-manager@example.com", status="revoked")
        _, stranger_headers = _headers("not-a-manager@example.com")
        _, scout_headers = _verified_scout("manager-scope-scout@example.com")
        _, player_one_headers, _ = _claim(
            "manager-scope-player-one@example.com",
            5807,
            contract_status="contracted",
            club_program_id=104,
        )
        _claim("manager-scope-player-two@example.com", 5808, contract_status="contracted", club_program_id=105)
        request_one = _create(client, scout_headers, 5807).get_json()["contact_request"]["id"]
        request_two = _create(client, scout_headers, 5808).get_json()["contact_request"]["id"]

        box_one = client.get("/api/contact/requests?box=club", headers=manager_one_headers)
        assert [row["id"] for row in box_one.get_json()["requests"]] == [request_one]
        box_two = client.get("/api/contact/requests?box=club", headers=manager_two_headers)
        assert [row["id"] for row in box_two.get_json()["requests"]] == [request_two]
        revoked_box = client.get("/api/contact/requests?box=club", headers=revoked_manager_headers)
        assert revoked_box.get_json()["requests"] == []
        assert (
            client.post(
                f"/api/contact/requests/{request_one}/club-consent",
                json={"action": "grant"},
                headers=manager_two_headers,
            ).status_code
            == 404
        )

        assert client.post(f"/api/contact/requests/{request_one}/accept", headers=player_one_headers).status_code == 200
        assert (
            client.post(
                f"/api/contact/requests/{request_one}/club-consent",
                json={"action": "grant"},
                headers=manager_one_headers,
            ).status_code
            == 200
        )
        assert (
            client.get(f"/api/contact/requests/{request_one}/messages", headers=manager_one_headers).status_code == 200
        )
        for denied_headers in (manager_two_headers, revoked_manager_headers, stranger_headers):
            assert (
                client.get(f"/api/contact/requests/{request_one}/messages", headers=denied_headers).status_code == 404
            )
            assert (
                client.post(
                    f"/api/contact/requests/{request_one}/messages",
                    json={"body": "This must stay private."},
                    headers=denied_headers,
                ).status_code
                == 404
            )
        assert (
            client.post(
                f"/api/contact/requests/{request_one}/club-consent",
                json={"action": "grant"},
                headers=stranger_headers,
            ).status_code
            == 404
        )
        assert (
            client.post(
                f"/api/contact/requests/{request_one}/club-consent",
                json={"action": "grant"},
                headers=revoked_manager_headers,
            ).status_code
            == 404
        )

    def test_linked_club_notice_uses_only_stored_program_email_and_audits_success(self, client, monkeypatch):
        _club_program(106, "Notice FC", contact_email="contact@notice-fc.example")
        scout, scout_headers = _verified_scout("notice-scout@example.com")
        player, _, _ = _claim(
            "notice-player@example.com",
            5809,
            contract_status="contracted",
            club_program_id=106,
        )
        scout.display_name = "Private Scout Name"
        player.display_name = "Private Player Name"
        db.session.commit()
        sends = []

        from src.services.email_service import email_service

        def fake_send_email(**kwargs):
            sends.append(kwargs)
            return SimpleNamespace(success=True, provider="mailgun", message_id="fixture-message")

        monkeypatch.setattr(email_service, "send_email", fake_send_email)
        private_message = "Confidential recruitment assessment"
        created = _create(
            client,
            scout_headers,
            5809,
            message=private_message,
            permission_attestation=True,
        )

        assert created.status_code == 201, created.get_json()
        assert created.get_json()["contact_request"]["routing_mode"] == "club_notified"
        assert len(sends) == 1
        assert sends[0]["to"] == "contact@notice-fc.example"
        assert sends[0]["use_fallback"] is False
        rendered = " ".join(str(sends[0][key]) for key in ("subject", "html", "text"))
        for private_value in (
            scout.email,
            player.email,
            scout.display_name,
            player.display_name,
            private_message,
        ):
            assert private_value not in rendered
        events = ContactAuditEvent.query.order_by(ContactAuditEvent.id).all()
        assert [event.event_type for event in events] == [
            "created",
            "scout_permission_attested",
            "club_notice_sent",
        ]
        assert events[-1].event_metadata == {
            "club_program_id": 106,
            "provider": "mailgun",
            "message_id": "fixture-message",
        }
        assert "contact@notice-fc.example" not in str(events[-1].event_metadata)

    def test_named_club_notice_requires_one_exact_stored_registry_match(self, client, monkeypatch):
        _club_program(109, "Named Notice FC", contact_email="hello@named-notice.example")
        _, scout_headers = _verified_scout("named-notice-scout@example.com")
        _claim(
            "named-notice-player@example.com",
            5812,
            contract_status="contracted",
            current_club_name="named notice fc",
        )
        sends = []

        from src.services.email_service import email_service

        def fake_send_email(**kwargs):
            sends.append(kwargs)
            return SimpleNamespace(success=True, provider="mailgun", message_id="named-fixture")

        monkeypatch.setattr(email_service, "send_email", fake_send_email)
        created = _create(client, scout_headers, 5812, permission_attestation=True)

        assert created.status_code == 201, created.get_json()
        assert [send["to"] for send in sends] == ["hello@named-notice.example"]
        assert ContactAuditEvent.query.filter_by(event_type="club_notice_sent").count() == 1


class TestContactLimits:
    def test_plain_text_fields_are_bounded_and_occurred_at_is_validated(self, client):
        _, scout_headers = _verified_scout("bounded-scout@example.com")
        _, player_headers, _ = _claim("bounded-player@example.com", 5901)

        oversized_request = _create(client, scout_headers, 5901, message="x" * 2001)
        assert oversized_request.status_code == 400
        assert "at most 2000" in oversized_request.get_json()["error"]

        created = _create(client, scout_headers, 5901, message="A bounded introduction")
        assert created.status_code == 201
        request_id = created.get_json()["contact_request"]["id"]
        assert client.post(f"/api/contact/requests/{request_id}/accept", headers=player_headers).status_code == 200

        oversized_message = client.post(
            f"/api/contact/requests/{request_id}/messages",
            json={"body": "x" * 2001},
            headers=scout_headers,
        )
        assert oversized_message.status_code == 400
        oversized_notes = client.post(
            f"/api/contact/requests/{request_id}/outcome",
            json={"stage": "contacted", "notes": "x" * 2001},
            headers=player_headers,
        )
        assert oversized_notes.status_code == 400
        invalid_occurred_at = client.post(
            f"/api/contact/requests/{request_id}/outcome",
            json={"stage": "contacted", "occurred_at": "not-a-date"},
            headers=player_headers,
        )
        assert invalid_occurred_at.status_code == 400
        assert ContactMessage.query.count() == 0
        assert ContactOutcome.query.count() == 0

    def test_request_limit_is_per_verified_scout(self, client):
        _, scout_headers = _verified_scout("rate-scout@example.com")
        for offset in range(11):
            _claim(f"rate-player-{offset}@example.com", 6000 + offset)
        for offset in range(10):
            response = _create(client, scout_headers, 6000 + offset, message=f"Introduction {offset}")
            assert response.status_code == 201, response.get_json()

        limited = _create(client, scout_headers, 6010, message="Eleventh introduction")
        assert limited.status_code == 429

        _, independent_headers = _verified_scout("other-rate-scout@example.com")
        independent = _create(client, independent_headers, 6010, message="Independent scout bucket")
        assert independent.status_code == 201, independent.get_json()

    def test_message_post_limit_is_per_participant(self, client):
        _, scout_headers, _, player_headers, _, request_payload = _seed_contact(
            client, suffix="message-rate", player_api_id=6101
        )
        request_id = request_payload["id"]
        assert client.post(f"/api/contact/requests/{request_id}/accept", headers=player_headers).status_code == 200
        for index in range(60):
            sent = client.post(
                f"/api/contact/requests/{request_id}/messages",
                json={"body": f"Message {index}"},
                headers=scout_headers,
            )
            assert sent.status_code == 201, (index, sent.get_json())
        limited = client.post(
            f"/api/contact/requests/{request_id}/messages",
            json={"body": "Message 61"},
            headers=scout_headers,
        )
        assert limited.status_code == 429

        independent = client.post(
            f"/api/contact/requests/{request_id}/messages",
            json={"body": "Player response"},
            headers=player_headers,
        )
        assert independent.status_code == 201
        assert ContactMessage.query.count() == 61
        assert ContactAuditEvent.query.filter_by(event_type="message_sent").count() == 61


class TestInterestSignals:
    def test_aggregates_are_correct_distinct_and_identity_free(self, client):
        owner, owner_headers, _ = _claim("signal-owner@example.com", 7001)
        _claim("signal-owner@example.com", 7002)
        _claim("signal-owner@example.com", 7003, status="pending")
        _claim("signal-owner@example.com", 7004, relationship_type="agent")

        now = utcnow()
        week_start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=now.weekday())
        old = week_start - timedelta(days=2)
        watcher_a, _ = _headers("watcher-a@example.com")
        watcher_b, _ = _headers("watcher-b@example.com")
        watcher_c, _ = _headers("watcher-c@example.com")
        db.session.add_all(
            [
                ScoutWatchlistEntry(user_account_id=watcher_a.id, player_api_id=7001, created_at=old),
                ScoutWatchlistEntry(user_account_id=watcher_b.id, player_api_id=7001, created_at=now),
            ]
        )

        active_a = FollowList(user_account_id=watcher_a.id, name="Prospects A", is_active=True, is_default=False)
        active_a_two = FollowList(user_account_id=watcher_a.id, name="Prospects A2", is_active=True, is_default=False)
        active_b = FollowList(user_account_id=watcher_b.id, name="Prospects B", is_active=True, is_default=False)
        active_c = FollowList(user_account_id=watcher_c.id, name="Prospects C", is_active=True, is_default=False)
        default_mirror = FollowList(user_account_id=owner.id, name="My Watchlist", is_active=True, is_default=True)
        inactive = FollowList(user_account_id=owner.id, name="Paused", is_active=False, is_default=False)
        db.session.add_all([active_a, active_a_two, active_b, active_c, default_mirror, inactive])
        db.session.flush()
        db.session.add_all(
            [
                Follow(list_id=active_a.id, kind="player", selector={"player_api_id": 7001}, created_at=now),
                Follow(list_id=active_a_two.id, kind="player", selector={"player_api_id": 7001}, created_at=old),
                Follow(list_id=active_b.id, kind="player", selector={"player_api_id": 7001}, created_at=old),
                Follow(list_id=active_c.id, kind="player", selector={"player_api_id": 7001}, created_at=now),
                Follow(list_id=default_mirror.id, kind="player", selector={"player_api_id": 7001}, created_at=now),
                Follow(list_id=inactive.id, kind="player", selector={"player_api_id": 7001}, created_at=now),
                Follow(list_id=active_b.id, kind="geo", selector={"mode": "nationality", "value": "Japan"}),
            ]
        )
        db.session.commit()

        response = client.get("/api/showcase/mine/interest-signals", headers=owner_headers)
        assert response.status_code == 200, response.get_json()
        payload = response.get_json()
        assert payload["week_start"].startswith(week_start.date().isoformat())
        assert payload["interest_signals"] == [
            {
                "player_api_id": 7001,
                "watchlists": {"total": 2, "added_this_week": 1},
                "follows": {"total": 3, "added_this_week": 1},
            },
            {
                "player_api_id": 7002,
                "watchlists": {"total": 0, "added_this_week": 0},
                "follows": {"total": 0, "added_this_week": 0},
            },
        ]

        forbidden_keys = {
            "user_id",
            "user_account_id",
            "email",
            "display_name",
            "list_id",
            "list_name",
            "follow_id",
            "selector",
            "note",
            "last_snapshot",
        }

        def all_keys(value):
            if isinstance(value, dict):
                return set(value) | set().union(*(all_keys(item) for item in value.values()), set())
            if isinstance(value, list):
                return set().union(*(all_keys(item) for item in value), set())
            return set()

        assert not (all_keys(payload) & forbidden_keys)
        assert "watcher-a@example.com" not in response.get_data(as_text=True)

    def test_no_approved_player_claims_returns_empty(self, client):
        _, headers = _headers("no-player-claims@example.com")
        _claim("no-player-claims@example.com", 7101, relationship_type="agent")
        response = client.get("/api/showcase/mine/interest-signals", headers=headers)
        assert response.status_code == 200
        assert response.get_json()["interest_signals"] == []


def test_fc02_is_guarded_single_parent_and_enables_rls_for_all_tables():
    migration = Path(__file__).resolve().parents[1] / "migrations" / "versions" / "fc02_contact_rail.py"
    source = migration.read_text()
    assert 'revision = "fc02"' in source
    assert 'down_revision = "fc01"' in source
    assert "PR #636" in source and "gf01" in source
    assert "if not table_exists" in source
    assert "create_index_safe" in source
    assert "status IN ('pending', 'accepted')" in source
    assert "for table_name in NEW_TABLES" in source
    assert source.count("ENABLE ROW LEVEL SECURITY") == 1
    for table_name in (
        "contact_requests",
        "contact_messages",
        "contact_audit_events",
        "contact_outcomes",
    ):
        assert f'"{table_name}"' in source


def test_fc03_is_guarded_order_neutral_and_extends_contact_contract():
    migration = Path(__file__).resolve().parents[1] / "migrations" / "versions" / "fc03_contract_status_routing.py"
    source = migration.read_text()
    assert 'revision = "fc03"' in source
    assert 'down_revision = "fc02"' in source
    assert "PR #636" in source and "gf01" in source
    assert "If ``gf01`` lands first" in source
    assert "If the FC stack lands first" in source
    assert "add_column_safe" in source
    assert "table_exists" in source
    assert "column_exists" in source
    assert "index_exists" in source
    assert "op.create_table" not in source
    assert "creates no table" in source
    for column_name in (
        "contract_status",
        "status_contradiction",
        "routing_mode",
        "club_program_id",
        "club_consent_status",
        "permission_attestation",
        "sender_role",
        "contact_email",
    ):
        assert f'"{column_name}"' in source
    for event_type in (
        "club_consent_granted",
        "club_consent_declined",
        "club_notice_sent",
        "scout_permission_attested",
    ):
        assert event_type in source
    assert "fk_contact_requests_club_consent_by_user" in source
    assert "fc03_legacy_unknown_contract" in source
    assert "club_consent_status IS DISTINCT FROM 'granted'" in source
