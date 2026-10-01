"""B3 security boundaries, transactions, honest finance and rollback behaviour."""

from datetime import UTC, timedelta
from unittest.mock import Mock

import pytest
from flask import Flask, jsonify
from itsdangerous import BadSignature
from src.auth import (
    _user_serializer,
    issue_user_token,
    media_token_claims,
    mint_media_token,
    require_user_auth,
    resolve_bearer_user,
)
from src.extensions import limiter
from src.models.admin_control import BillingCashEvent, SafeguardingCase, SafeguardingCaseEvent, now
from src.models.funding import ClubProgram, ClubProgramClaim, ClubProgramManager, FundingLeague
from src.models.gol_credits import GolCreditLedger
from src.models.league import EmailToken, UserAccount, db
from src.models.p2_foundation import AdminActionEvent, NotificationOutbox
from src.models.player_suppression import PlayerSuppression
from src.models.showcase import PlayerProfileClaim
from src.models.trust import ContentReport, ScoutVerification
from src.routes.admin_control import admin_control_bp
from src.routes.admin_programs import admin_programs_bp
from src.routes.auth_routes import auth_bp
from src.services.account import _SchemaView
from src.services.account_standing import is_account_active
from src.services.admin_control_account import erase_admin_control, export_admin_control
from src.services.admin_control_business import project_cash
from src.services.admin_control_safety import register_safety
from src.services.club_access import club_actor_allowed, resolve_club_access
from src.services.notification_outbox import dispatch_due


@pytest.fixture
def control_app(monkeypatch):
    for flag in (
        "ADMIN_PROGRAMS_ENABLED",
        "ADMIN_PEOPLE_ENABLED",
        "ADMIN_SAFETY_ENABLED",
        "ADMIN_BUSINESS_ENABLED",
        "P2_FOUNDATION_ENABLED",
    ):
        monkeypatch.setenv(flag, "1")
    monkeypatch.setenv("ADMIN_API_KEY", "test-control-key")
    monkeypatch.setenv("ADMIN_EMAILS", "admin@example.test")
    monkeypatch.setenv("PLAYER_SUPPRESSION_ENCRYPTION_KEY", "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=")
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SECRET_KEY="control-test",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        RATELIMIT_ENABLED=False,
    )
    db.init_app(app)
    limiter.init_app(app)
    for blueprint in (admin_control_bp, admin_programs_bp, auth_bp):
        app.register_blueprint(blueprint, url_prefix="/api")
    register_safety()

    @app.get("/optional")
    def optional():
        try:
            user = resolve_bearer_user()
        except (BadSignature, LookupError):
            user = None
        return jsonify(authenticated=user is not None)

    @app.post("/act")
    @require_user_auth
    def do_act():
        return jsonify(ok=True)

    with app.app_context():
        db.create_all()
        admin = UserAccount(email="admin@example.test", display_name="Test Admin", display_name_lower="admin")
        user = UserAccount(email="person@example.test", display_name="Test Person", display_name_lower="person")
        db.session.add_all([admin, user])
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


def user():
    return UserAccount.query.filter_by(email="person@example.test").one()


def headers(email="admin@example.test", role="admin"):
    return {"Authorization": "Bearer " + issue_user_token(email, role=role)["token"], "X-API-Key": "test-control-key"}


def program():
    league = FundingLeague(
        name="Test League",
        country="JP",
        region="Test",
        level="recreational",
        gender_program="both",
        season_calendar="calendar_year",
        data_tier="self_reported",
        registry_status="approved",
        admission_state="open",
    )
    db.session.add(league)
    db.session.flush()
    row = ClubProgram(
        funding_league_id=league.id,
        name="Test Program",
        legal_name="Test Program",
        slug="test-program",
        country="JP",
        region="Test",
        platform_status="approved",
    )
    db.session.add(row)
    db.session.commit()
    return row


@pytest.mark.parametrize(
    "path,flag",
    [
        ("/api/admin/programs", "ADMIN_PROGRAMS_ENABLED"),
        ("/api/admin/people", "ADMIN_PEOPLE_ENABLED"),
        ("/api/admin/safety/cases", "ADMIN_SAFETY_ENABLED"),
        ("/api/admin/safety/hidden", "ADMIN_SAFETY_ENABLED"),
        ("/api/admin/business/summary", "ADMIN_BUSINESS_ENABLED"),
    ],
)
def test_pages_dark_and_admin_only(control_app, monkeypatch, path, flag):
    client = control_app.test_client()
    assert client.get(path).status_code == 401
    assert client.get(path, headers=headers("person@example.test", "user")).status_code == 401
    h = headers()
    assert client.get(path, headers={"Authorization": h["Authorization"]}).status_code == 401
    assert client.get(path, headers=h).status_code == 200
    monkeypatch.setenv(flag, "0")
    assert client.get(path, headers=h).status_code == 404
    assert client.get(path).status_code == 404


def test_suspend_blocks_issued_tokens_otp_optional_and_media_then_restore_needs_fresh_login(control_app, monkeypatch):
    client = control_app.test_client()
    h = headers("person@example.test", "user")
    admin = headers()
    person = user()
    media = mint_media_token(12, email=person.email, club_user_id=person.id)["token"]
    db.session.add(
        EmailToken(token="test-code", email=person.email, purpose="login", expires_at=now() + timedelta(minutes=5))
    )
    db.session.commit()
    assert client.post("/act", headers=h).status_code == 200
    response = client.post(f"/api/admin/users/{person.id}/suspend", headers=admin, json={"reason": "Reported misuse"})
    assert response.status_code == 200
    assert not is_account_active(person.id)
    assert client.post("/act", headers=h).status_code == 401
    assert client.get("/optional", headers=h).json == {"authenticated": False}
    with control_app.test_request_context():
        assert media_token_claims(media, 12) is None
    assert client.post("/api/auth/verify-code", json={"email": person.email, "code": "test-code"}).status_code == 403
    send = Mock()
    monkeypatch.setattr("src.routes.auth_routes._send_login_code", send)
    assert client.post("/api/auth/request-code", json={"email": person.email}).status_code == 200
    send.assert_not_called()
    assert EmailToken.query.filter_by(email=person.email).count() == 0
    with pytest.raises(ValueError):
        issue_user_token(person.email)
    assert (
        client.post(
            f"/api/admin/users/{person.id}/restore", headers=admin, json={"reason": "Review completed"}
        ).status_code
        == 200
    )
    assert client.post("/act", headers=h).status_code == 401
    assert client.post("/act", headers=headers("person@example.test", "user")).status_code == 200
    assert (
        AdminActionEvent.query.filter(AdminActionEvent.action.in_(("account_suspend", "account_restore"))).count() == 2
    )


def test_suspended_allowlisted_admin_cannot_use_dual_auth_and_self_suspend_refused(control_app):
    client = control_app.test_client()
    admin = UserAccount.query.filter_by(email="admin@example.test").one()
    h = headers()
    assert client.post(f"/api/admin/users/{admin.id}/suspend", headers=h, json={"reason": "Self"}).status_code == 409
    admin.account_status = "suspended"
    db.session.commit()
    assert client.get("/api/admin/people", headers=h).status_code == 401


def test_suspension_survives_flag_rollback_legacy_token_also_denied(control_app, monkeypatch):
    person = user()
    token = _user_serializer().dumps({"email": person.email, "role": "user"})
    person.account_status = "suspended"
    db.session.commit()
    monkeypatch.setenv("ADMIN_PEOPLE_ENABLED", "0")
    assert control_app.test_client().post("/act", headers={"Authorization": "Bearer " + token}).status_code == 401


def test_suspension_rejects_service_grants(control_app, monkeypatch):
    row = program()
    person = user()
    claim = ClubProgramClaim(program_id=row.id, user_account_id=person.id, status="approved")
    db.session.add(claim)
    db.session.flush()
    db.session.add(
        ClubProgramManager(
            program_id=row.id,
            user_account_id=person.id,
            source_claim_id=claim.id,
            status="active",
            granted_by="admin@example.test",
        )
    )
    db.session.commit()
    for flag in ("0", "1"):
        monkeypatch.setenv("CLUB_STAFF_ACCESS_ENABLED", flag)
        assert resolve_club_access(person.id, row.id) is not None
        assert club_actor_allowed(db.session, row.id, person.id, "players.view")
        person.account_status = "suspended"
        db.session.commit()
        assert resolve_club_access(person.id, row.id) is None
        assert not club_actor_allowed(db.session, row.id, person.id, "players.view")
        person.account_status = "active"
        db.session.commit()


def test_people_allowlist_derives_roles_without_private_notes(control_app):
    person = user()
    person.bio = "PRIVATE BIO SENTINEL"
    db.session.add(
        PlayerProfileClaim(
            player_api_id=999,
            user_account_id=person.id,
            status="approved",
            relationship_type="guardian",
            message="PRIVATE CLAIM NOTE",
        )
    )
    db.session.add(
        ScoutVerification(
            user_account_id=person.id,
            full_name="Test",
            organization="Test",
            role_title="Scout",
            statement="PRIVATE VERIFICATION",
            evidence_urls=[],
            status="approved",
        )
    )
    db.session.commit()
    response = control_app.test_client().get("/api/admin/people", headers=headers())
    payload = response.json
    entry = next(row for row in payload["rows"] if row["id"] == person.id)
    assert entry["roles"] == ["guardian", "verified_scout"]
    assert "PRIVATE" not in response.text
    assert set(entry) == {
        "id",
        "display_name",
        "email",
        "account_status",
        "created_at",
        "last_login_at",
        "roles",
        "programs",
        "approved_claims",
        "scout_verification",
    }
    assert response.headers["Cache-Control"] == "no-store"


def report(target_type="player_profile", target_id="321"):
    row = ContentReport(
        reporter_user_id=user().id,
        subject_type=target_type,
        subject_id=target_id,
        reason_code="privacy",
        details="Reported evidence",
        created_at=now() - timedelta(hours=25),
    )
    db.session.add(row)
    db.session.commit()
    return SafeguardingCase.query.filter_by(report_id=row.id).one()


def action(client, incident, kind, h=None):
    return client.post(
        f"/api/admin/safety/cases/{incident.id}/actions",
        headers=h or headers(),
        json={"action": kind, "reason": "Case review", "version": incident.version},
    )


def test_case_intake_is_atomic_and_24h_due(control_app):
    case = report()
    assert case.first_action_due_at - case.received_at == timedelta(hours=24)
    assert SafeguardingCaseEvent.query.filter_by(case_id=case.id, action="received").count() == 1
    payload = control_app.test_client().get("/api/admin/safety/cases", headers=headers()).json
    assert payload["overdue_count"] == 1
    assert payload["minor_public_audit"] == "not_available"
    source = ContentReport(reporter_user_id=user().id, subject_type="other", subject_id="none", reason_code="other")
    db.session.add(source)
    db.session.flush()
    db.session.rollback()
    assert SafeguardingCase.query.count() == 1


def test_hide_close_never_lifts_suppression_and_outbox_rechecks_recipient(control_app):
    case = report()
    client = control_app.test_client()
    response = action(client, case, "hide")
    assert response.status_code == 200, response.json
    suppression = PlayerSuppression.query.filter_by(player_api_id=321).one()
    assert suppression.status == "active"
    assert case.first_action_at is not None
    assert SafeguardingCase.query.count() == 1
    assert NotificationOutbox.query.count() == 1
    assert action(client, case, "close").status_code == 200
    assert suppression.status == "active"
    assert NotificationOutbox.query.count() == 2
    sent = []
    summary = dispatch_due(send=lambda **kw: sent.append(kw) or Mock(success=True, provider="test", message_id="test"))
    assert summary["sent"] == 2
    assert all("321" not in message["text"] and "Reported evidence" not in message["text"] for message in sent)


def test_preexisting_suppression_and_program_hide_survive_case_close(control_app):
    row = program()
    row.emergency_hidden = True
    db.session.commit()
    case = report("club_program", str(row.id))
    client = control_app.test_client()
    assert action(client, case, "hide").status_code == 200
    assert case.held_program_id is None
    assert action(client, case, "close").status_code == 200
    assert row.emergency_hidden


def test_case_detail_audits_only_source_evidence_and_conflicts_reject(control_app):
    case = report()
    client = control_app.test_client()
    h = headers()
    assert (
        client.get(f"/api/admin/safety/cases/{case.id}", headers=h).json["evidence"]["statement"] == "Reported evidence"
    )
    assert AdminActionEvent.query.filter_by(action="safeguarding_evidence_read").count() == 1
    assert (
        client.post(
            f"/api/admin/safety/cases/{case.id}/actions",
            headers=h,
            json={"action": "hide", "reason": "Review", "version": 0},
        ).status_code
        == 409
    )
    assert action(client, case, "investigate", headers("person@example.test", "user")).status_code == 401
    assert PlayerSuppression.query.count() == 0


def test_unsupported_target_never_fakes_hidden_and_reason_required(control_app):
    case = report("contact_message", "message-id")
    assert action(control_app.test_client(), case, "hide").status_code == 400
    assert case.first_action_at is None
    assert AdminActionEvent.query.count() == 0
    assert (
        control_app.test_client().post(f"/api/admin/users/{user().id}/suspend", headers=headers(), json={}).status_code
        == 400
    )
    assert user().account_status == "active"


def test_money_per_currency_date_filtered_not_mrr_refunds_dedupe(control_app):
    event = {
        "id": "in_test",
        "amount_paid": 5000,
        "currency": "eur",
        "payment_intent": "pi_eur",
        "status_transitions": {"paid_at": 1790812800},
    }
    project_cash("invoice.paid", event, "evt_paid", 1790812800)
    project_cash("invoice.paid", event, "evt_paid_duplicate", 1790812800)
    refund = {
        "id": "ch_test",
        "currency": "eur",
        "payment_intent": "pi_eur",
        "refunds": {"data": [{"id": "re_test", "amount": 1000, "created": 1790812801, "status": "succeeded"}]},
    }
    project_cash("charge.refunded", refund, "evt_refund", 1790812801)
    project_cash("charge.refunded", refund, "evt_refund_duplicate", 1790812801)
    db.session.add(
        GolCreditLedger(
            user_account_id=user().id,
            bucket="prepaid",
            kind="grant",
            delta=100,
            idempotency_key="test-paid",
            amount_paid_cents=2000,
            currency="usd",
            stripe_payment_intent_id="pi_usd",
            created_at=now(),
        )
    )
    db.session.commit()
    assert BillingCashEvent.query.count() == 2
    response = control_app.test_client().get(
        "/api/admin/business/summary?from=2026-09-01&to=2026-10-31", headers=headers()
    )
    assert response.status_code == 200
    assert response.json["currencies"] == {
        "EUR": {"money_in_cents": 5000, "refunds_cents": 1000},
        "USD": {"money_in_cents": 2000, "refunds_cents": 0},
    }
    assert "https://dashboard.stripe.com/payments/pi_eur" in response.text
    assert (
        control_app.test_client()
        .get("/api/admin/business/summary?from=2026-10-01&to=2026-09-01", headers=headers())
        .status_code
        == 400
    )


def test_freeze_read_only_coupling_and_no_refund_endpoint(control_app, monkeypatch):
    monkeypatch.setenv("API_FOOTBALL_FROZEN", "1")
    monkeypatch.setenv("NEWSLETTERS_FROZEN", "0")
    client = control_app.test_client()
    assert client.get("/api/admin/business/summary", headers=headers()).json["freeze"] == {
        "api_football": True,
        "newsletters_configured": False,
        "newsletters_effective": True,
    }
    assert client.post("/api/admin/business/summary", headers=headers(), json={"freeze": False}).status_code == 405


def test_privacy_exports_safe_cases_and_cash_then_erases_identity(control_app):
    case = report()
    project_cash(
        "invoice.paid",
        {"id": "in_private", "amount_paid": 400, "currency": "usd", "payment_intent": "pi_private"},
        "evt_private",
        1790812800,
    )
    cash = BillingCashEvent.query.one()
    cash.purchaser_user_id, cash.scope_type, cash.scope_id = user().id, "user", user().id
    db.session.commit()
    export = export_admin_control(user(), _SchemaView())
    assert export["safeguarding_cases"][0]["id"] == case.id
    assert export["billing_cash"][0]["amount_cents"] == 400
    assert "Reported evidence" not in str(export)
    erase_admin_control(user().id, user().email, _SchemaView())
    db.session.commit()
    db.session.refresh(cash)
    assert cash.purchaser_user_id is None and cash.scope_id is None


def test_local_report_namespace_hides_local_suppression(control_app):
    incident = report("player_profile", "local:9")
    response = action(control_app.test_client(), incident, "hide")
    assert response.status_code == 200, response.json
    assert PlayerSuppression.query.filter_by(local_player_id=9).one().status == "active"


def test_modern_invoice_payments_actual_amounts_and_truncated_refund_pagination(control_app, monkeypatch):
    import src.services.admin_control_business as business

    paid = {
        "id": "inpay_test",
        "status": "paid",
        "amount_paid": 2500,
        "payment": {"type": "payment_intent", "payment_intent": "pi_modern"},
        "status_transitions": {"paid_at": 1790812800},
    }
    fetch = Mock(return_value=[paid])
    monkeypatch.setattr(business, "_remote_rows", fetch)
    business.project_cash(
        "invoice.paid", {"id": "in_modern", "currency": "gbp", "amount_paid": 9999}, "evt_modern", 1790812800
    )
    assert BillingCashEvent.query.one().amount_cents == 2500
    fetch.assert_called_once_with("InvoicePayment", invoice="in_modern")
    fetch.reset_mock()
    fetch.return_value = [{"id": "re_modern", "amount": 500, "created": 1790812801, "status": "succeeded"}]
    business.project_cash(
        "charge.refunded",
        {
            "id": "ch_modern",
            "currency": "gbp",
            "payment_intent": "pi_modern",
            "refunds": {"data": [], "has_more": True},
        },
        "evt_refund_modern",
        1790812801,
    )
    assert BillingCashEvent.query.filter_by(kind="refund").one().amount_cents == 500
    fetch.assert_called_once_with("Refund", charge="ch_modern")


def test_gol_cash_projection_does_not_double_count_and_survives_erasure(control_app):
    person = user()
    grant = GolCreditLedger(
        user_account_id=person.id,
        bucket="prepaid",
        kind="grant",
        delta=100,
        idempotency_key="paid-gol",
        stripe_session_id="cs_test",
        stripe_payment_intent_id="pi_gol",
        amount_paid_cents=2000,
        currency="usd",
        created_at=now(),
    )
    db.session.add(grant)
    db.session.flush()
    project_cash(
        "checkout.session.completed",
        {
            "id": "cs_test",
            "mode": "payment",
            "payment_status": "paid",
            "amount_total": 2000,
            "currency": "usd",
            "payment_intent": "pi_gol",
        },
        "evt_gol",
        int(now().replace(tzinfo=UTC).timestamp()),
    )
    db.session.commit()
    client = control_app.test_client()
    assert (
        client.get("/api/admin/business/summary", headers=headers()).json["currencies"]["USD"]["money_in_cents"] == 2000
    )
    erase_admin_control(person.id, person.email, _SchemaView())
    db.session.delete(grant)
    db.session.commit()
    assert (
        client.get("/api/admin/business/summary", headers=headers()).json["currencies"]["USD"]["money_in_cents"] == 2000
    )


def test_consent_capability_rechecks_account_recipient(control_app, monkeypatch):
    from src.models.contact import ContactRequest
    from src.services.contact import issue_club_consent_token, load_club_consent_token

    claim = PlayerProfileClaim(
        user_account_id=user().id, player_api_id=1, relationship_type="player", status="approved"
    )
    db.session.add(claim)
    db.session.flush()
    contact = ContactRequest(
        scout_user_id=user().id,
        player_api_id=1,
        claim_id=claim.id,
        message="Private",
        expires_at=now() + timedelta(days=1),
        routing_mode="club_included",
    )
    db.session.add(contact)
    db.session.commit()
    monkeypatch.setattr(
        "src.services.contact.resolve_club_courtesy_target", lambda **kw: {"contact_email": user().email}
    )
    token = issue_club_consent_token(contact.id, "grant")
    assert load_club_consent_token(token) is not None
    user().account_status = "suspended"
    db.session.commit()
    assert load_club_consent_token(token) is None
    monkeypatch.setattr(
        "src.services.contact.resolve_club_courtesy_target", lambda **kw: {"contact_email": "legacy@example.test"}
    )
    assert load_club_consent_token(token) is not None


def test_boot_reconciles_requests_received_while_dark_and_preserves_case_actions(control_app, monkeypatch):
    from src.services.admin_control_safety import reconcile_safety_boot

    monkeypatch.setenv("ADMIN_SAFETY_ENABLED", "0")
    db.session.add(
        ContentReport(
            reporter_user_id=user().id,
            subject_type="other",
            subject_id="test-import",
            reason_code="other",
            created_at=now() - timedelta(days=2),
        )
    )
    db.session.commit()
    assert SafeguardingCase.query.count() == 0
    reconcile_safety_boot(control_app)
    assert SafeguardingCase.query.count() == 0
    monkeypatch.setenv("ADMIN_SAFETY_ENABLED", "1")
    reconcile_safety_boot(control_app)
    incident = SafeguardingCase.query.one()
    assert incident.first_action_due_at - incident.received_at == timedelta(hours=24)
    assert action(control_app.test_client(), incident, "investigate").status_code == 200
    reconcile_safety_boot(control_app)
    assert SafeguardingCase.query.count() == 1
    assert incident.status == "investigating"


def test_deleted_bound_admin_token_is_not_an_unbound_admin(control_app):
    token = headers()
    admin = UserAccount.query.filter_by(email="admin@example.test").one()
    db.session.delete(admin)
    db.session.commit()
    assert control_app.test_client().get("/api/admin/people", headers=token).status_code == 401
