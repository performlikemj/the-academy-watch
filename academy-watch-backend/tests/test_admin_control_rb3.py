"""RB3 adversarial probes reversed into regression assertions."""

from datetime import timedelta

import pytest
import sqlalchemy as sa
from flask import Flask
from src.models.admin_control import BillingCashEvent, SafeguardingCase, now
from src.models.billing import StripeWebhookEvent
from src.models.league import EmailToken, UserAccount, db
from src.models.p2_foundation import NotificationOutbox
from src.models.player_suppression import PlayerSuppression
from src.models.showcase import PlayerProfileClaim
from src.models.showcase_moderation import ShowcaseModerationEvent
from src.services.account_standing import require_account_access
from src.services.admin_control_safety import lazy_reconcile, reconcile_safety_boot, register_control_reconciliation
from test_admin_control import action, headers, program, report, user
from test_admin_control import control_app as _control_app

control_app = _control_app


def test_webhook_projection_failure_preserves_authoritative_commit_and_replay_repairs(control_app, monkeypatch):
    import src.services.admin_control_business as cash
    import src.services.stripe_billing as billing

    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "fixture")
    event = {
        "id": "evt_rb3",
        "type": "invoice.paid",
        "created": 1790812800,
        "data": {"object": {"id": "in_rb3", "currency": "usd", "amount_paid": 1500}},
    }
    monkeypatch.setattr(billing.stripe.Webhook, "construct_event", lambda *a: event)

    def apply(*a):
        user().display_name = "Billing committed"
        return True

    monkeypatch.setattr(billing, "_apply_event", apply)

    def remote(*a, **kw):
        assert not db.session().in_transaction()
        with db.engine.connect() as conn:
            assert (
                conn.execute(
                    sa.select(UserAccount.display_name).where(UserAccount.email == "person@example.test")
                ).scalar()
                == "Billing committed"
            )
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(cash, "_remote_rows", remote)
    assert billing.handle_webhook(b"fixture", "signature")[1] == 200
    assert StripeWebhookEvent.query.one().status == "processed"
    # A PostgreSQL-aborting projection error also cannot poison committed billing work.
    monkeypatch.setattr(
        cash,
        "_remote_rows",
        lambda *a, **kw: [
            {
                "id": "ip_rb3",
                "status": "paid",
                "amount_paid": 1500,
                "payment": {"type": "payment_intent", "payment_intent": "pi_rb3"},
            }
        ],
    )
    original = cash.project_cash

    def invalid(*a, **kw):
        db.session.execute(sa.text("select rb3_missing_column"))

    monkeypatch.setattr(cash, "project_cash", invalid)
    assert billing.handle_webhook(b"fixture", "signature")[1] == 200
    assert StripeWebhookEvent.query.one().status == "processed"
    monkeypatch.setattr(cash, "project_cash", original)
    for _ in range(2):
        assert billing.handle_webhook(b"fixture", "signature") == ({"received": True, "duplicate": True}, 200)
    assert BillingCashEvent.query.count() == 1


def test_boot_registration_does_not_touch_absent_schema_and_lazy_failure_is_throttled(monkeypatch):
    for flag in ("ADMIN_SAFETY_ENABLED", "ADMIN_BUSINESS_ENABLED"):
        monkeypatch.setenv(flag, "1")
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    db.init_app(app)
    register_control_reconciliation(app)
    with app.app_context():
        for which in ("safety", "business"):
            lazy_reconcile(app, which)
            assert which in app.extensions["b3_reconcile"]
            prior = app.extensions["b3_reconcile"][which]
            lazy_reconcile(app, which)
            assert prior == app.extensions["b3_reconcile"][which]


def test_club_case_restore_works_foundation_dark_and_cannot_lift_preexisting_or_renewed_hold(control_app, monkeypatch):
    row = program()
    case = report("club_program", str(row.id))
    client = control_app.test_client()
    monkeypatch.setenv("P2_FOUNDATION_ENABLED", "0")
    assert action(client, case, "hide").status_code == 200
    assert row.emergency_hidden
    assert action(client, case, "restore").status_code == 200
    assert not row.emergency_hidden
    assert action(client, case, "hide").status_code == 200
    # Independently renewed emergency hold is no longer case-owned.
    monkeypatch.setenv("P2_FOUNDATION_ENABLED", "1")
    assert (
        client.post(
            f"/api/admin/programs/{row.id}/emergency-hide", headers=headers(), json={"reason": "New concern"}
        ).status_code
        == 200
    )
    monkeypatch.setenv("P2_FOUNDATION_ENABLED", "0")
    assert action(client, case, "hide").status_code == 200  # cannot reclaim an independently renewed hold
    assert action(client, case, "restore").status_code == 400
    assert row.emergency_hidden


def test_existing_tools_sync_case_and_first_action(control_app):
    from src.routes.player_suppression import player_suppression_bp
    from src.routes.trust import trust_bp

    control_app.register_blueprint(trust_bp, url_prefix="/api")
    control_app.register_blueprint(player_suppression_bp, url_prefix="/api")
    case = report()
    client = control_app.test_client()
    assert (
        client.post(
            f"/api/admin/reports/{case.report_id}/resolve",
            headers=headers(),
            json={"status": "dismissed", "resolution_notes": "Reviewed source"},
        ).status_code
        == 200
    )
    assert case.status == "closed" and case.first_action_at is not None
    assert client.get("/api/admin/safety/cases", headers=headers()).json["overdue_count"] == 0
    source = PlayerSuppression(
        player_api_id=321,
        reason_code="player_request",
        requester_role="player",
        requester_contact=user().email,
        request_statement="Original evidence",
    )
    db.session.add(source)
    db.session.commit()
    incident = SafeguardingCase.query.filter_by(suppression_id=source.id).one()
    for kind, expected in (("activate", "investigating"), ("lift", "closed")):
        assert (
            client.post(
                f"/api/admin/suppressions/{source.id}/{kind}", headers=headers(), json={"notes": "Reviewed source"}
            ).status_code
            == 200
        )
        assert incident.status == expected and incident.first_action_at is not None


def test_hide_reconcile_is_idempotent_notification_dedupes_and_records_owner_event(control_app):
    case = report()
    db.session.add(
        PlayerProfileClaim(player_api_id=321, user_account_id=user().id, status="approved", relationship_type="player")
    )
    db.session.commit()
    client = control_app.test_client()
    for _ in range(3):
        assert action(client, case, "hide").status_code == 200
        reconcile_safety_boot(control_app)
    assert SafeguardingCase.query.count() == 1
    assert NotificationOutbox.query.count() == 1
    assert ShowcaseModerationEvent.query.filter_by(action="suppressed").count() == 1
    suppression = PlayerSuppression.query.one()
    assert suppression.updated_at == suppression.decided_at
    assert action(client, case, "close").status_code == 200
    assert client.get("/api/admin/safety/cases", headers=headers()).json["open_count"] == 0


def test_anonymous_duplicate_cannot_replace_evidence_or_select_notice_recipient(control_app):
    from src.routes.player_suppression import player_suppression_bp

    control_app.register_blueprint(player_suppression_bp, url_prefix="/api")
    client = control_app.test_client()
    for contact, statement in (("original@fixture.test", "Original evidence"), (user().email, "Attacker text")):
        assert (
            client.post(
                "/api/players/321/takedown-request",
                json={"requester_role": "player", "contact_email": contact, "statement": statement},
            ).status_code
            == 202
        )
    source = PlayerSuppression.query.one()
    assert source.requester_contact == "original@fixture.test" and source.request_statement == "Original evidence"
    case = SafeguardingCase.query.one()
    assert action(client, case, "hide").status_code == 200
    assert NotificationOutbox.query.count() == 0
    assert case.notification_state == "no_account_recipient"


def test_verify_wrong_code_same_body_status_and_query_class_and_valid_code_limited_rights(control_app):
    client = control_app.test_client()
    counts = [0]
    call_counts = []
    person_email = user().email

    @control_app.get("/rights")
    @require_account_access
    def rights():
        return {"ok": True}

    def before(*a):
        counts[-1] += 1

    sa.event.listen(db.engine, "before_cursor_execute", before)
    try:
        results = []
        for email, standing in (("unknown@fixture.test", None), (person_email, "active"), (person_email, "suspended")):
            if standing:
                user().account_status = standing
                db.session.commit()
            before_count = counts[0]
            response = client.post("/api/auth/verify-code", json={"email": email, "code": "wrong"})
            call_counts.append(counts[0] - before_count)
            results.append((response.status_code, response.json))
        assert results == [(400, {"error": "invalid or expired code"})] * 3
        assert len(set(call_counts)) == 1
    finally:
        sa.event.remove(db.engine, "before_cursor_execute", before)
    db.session.add(
        EmailToken(email=user().email, token="valid", purpose="login", expires_at=now() + timedelta(minutes=5))
    )
    db.session.commit()
    result = client.post("/api/auth/verify-code", json={"email": user().email, "code": "valid"})
    assert result.status_code == 403 and "suspend" not in result.json["error"]
    token = result.json["account_access_token"]

    assert client.get("/rights", headers={"Authorization": "Bearer " + token}).status_code == 200
    assert client.post("/act", headers={"Authorization": "Bearer " + token}).status_code == 401


@pytest.mark.parametrize(
    "path,flag",
    [
        ("/api/admin/people", "ADMIN_PEOPLE_ENABLED"),
        ("/api/admin/programs", "ADMIN_PROGRAMS_ENABLED"),
        ("/api/admin/safety/cases", "ADMIN_SAFETY_ENABLED"),
        ("/api/admin/business/summary", "ADMIN_BUSINESS_ENABLED"),
    ],
)
def test_dark_options_like_unknown_route(control_app, monkeypatch, path, flag):
    monkeypatch.setenv(flag, "0")
    client = control_app.test_client()
    actual = client.options(path)
    unknown = client.options("/api/admin/rb3-unknown")
    assert actual.status_code == unknown.status_code == 404
    assert actual.data == unknown.data and "Allow" not in actual.headers


@pytest.mark.parametrize("target", ["99999999999999999999", "local:7", "-5", "0"])
def test_invalid_missing_target_hide_is_400_atomic(control_app, target):
    case = report("player_profile", target)
    assert action(control_app.test_client(), case, "hide").status_code == 400
    assert PlayerSuppression.query.count() == 0 and case.first_action_at is None


def test_list_search_escaped_bounded_and_query_budget(control_app):
    db.session.add_all(
        [
            UserAccount(email=f"bulk{i}@fixture.test", display_name=f"Bulk {i}", display_name_lower=f"bulk {i}")
            for i in range(100)
        ]
    )
    db.session.commit()
    client = control_app.test_client()
    auth = headers()
    calls = []

    def before(*a):
        calls.append(1)

    sa.event.listen(db.engine, "before_cursor_execute", before)
    try:
        response = client.get("/api/admin/people?limit=100", headers=auth)
        assert len(response.json["rows"]) == 100 and len(calls) <= 12
    finally:
        sa.event.remove(db.engine, "before_cursor_execute", before)
    for endpoint in ("people", "programs"):
        for wildcard in ("%25", "_"):
            assert client.get(f"/api/admin/{endpoint}?q={wildcard}", headers=auth).json["total"] == 0
        assert client.get(f"/api/admin/{endpoint}?q=" + ("x" * 121), headers=auth).status_code == 400
        assert client.get(f"/api/admin/{endpoint}/9999999999999999999999", headers=auth).status_code == 400


def test_suspended_claim_curator_fail_before_side_effect(control_app):
    from src.routes.api import api_bp
    from src.routes.journalist import journalist_bp

    control_app.register_blueprint(journalist_bp, url_prefix="/api")
    control_app.register_blueprint(api_bp, url_prefix="/api")
    person = user()
    person.account_status = "suspended"
    person.claim_token = "claim"
    person.claim_token_expires_at = now() + timedelta(minutes=5)
    db.session.commit()
    client = control_app.test_client()
    assert client.post("/api/claim/complete", json={"token": "claim"}).status_code == 403
    assert client.post("/api/admin/curator-token", headers=headers(), json={"email": person.email}).status_code == 403
    db.session.refresh(person)
    assert person.claim_token == "claim" and person.claimed_at is None and not person.is_curator


def test_restore_reconcile_retains_suppression_source_identity(control_app):
    case = report()
    client = control_app.test_client()
    assert action(client, case, "hide").status_code == 200
    assert action(client, case, "restore").status_code == 200
    reconcile_safety_boot(control_app)
    assert SafeguardingCase.query.count() == 1
    assert case.suppression_id is not None and case.owned_suppression_id is None


def test_case_hide_preserves_existing_pending_statement_and_notes(control_app):
    source = PlayerSuppression(
        player_api_id=321,
        requester_role="player",
        reason_code="player_request",
        requester_contact="original@fixture.test",
        request_statement="Original statement",
        notes="Original pending moderation note",
        status="requested",
    )
    db.session.add(source)
    db.session.commit()
    case = report()
    assert action(control_app.test_client(), case, "hide").status_code == 200
    assert source.request_statement == "Original statement" and source.notes == "Original pending moderation note"


def test_last_owner_warning_ignores_suspended_or_inert_other_owners(control_app):
    from src.models.club_access import ClubAccessGrant
    from src.models.funding import ClubProgramClaim, ClubProgramManager
    from src.routes.admin_control import last_owner_programs

    row = program()
    owner = user()
    claim = ClubProgramClaim(program_id=row.id, user_account_id=owner.id, status="approved")
    db.session.add(claim)
    db.session.flush()
    db.session.add(
        ClubProgramManager(
            program_id=row.id,
            user_account_id=owner.id,
            source_claim_id=claim.id,
            status="active",
            granted_by="admin@example.test",
        )
    )
    db.session.add(ClubAccessGrant(program_id=row.id, user_account_id=owner.id, role="owner", status="active"))
    other = UserAccount.query.filter_by(email="admin@example.test").one()
    db.session.add(ClubAccessGrant(program_id=row.id, user_account_id=other.id, role="owner", status="active"))
    db.session.commit()
    assert last_owner_programs(owner.id) == [row.name]  # inert grant provides no safety net
    other_claim = ClubProgramClaim(program_id=row.id, user_account_id=other.id, status="approved")
    db.session.add(other_claim)
    db.session.flush()
    db.session.add(
        ClubProgramManager(
            program_id=row.id,
            user_account_id=other.id,
            source_claim_id=other_claim.id,
            status="active",
            granted_by="admin@example.test",
        )
    )
    db.session.commit()
    assert last_owner_programs(owner.id) == []
    other.account_status = "suspended"
    db.session.commit()
    assert last_owner_programs(owner.id) == [row.name]


def test_clubs_filter_requires_same_approved_claim_as_manager_badge(control_app):
    from src.models.funding import ClubProgramClaim, ClubProgramManager

    row = program()
    owner = user()
    claim = ClubProgramClaim(program_id=row.id, user_account_id=owner.id, status="pending")
    db.session.add(claim)
    db.session.flush()
    db.session.add(
        ClubProgramManager(
            program_id=row.id,
            user_account_id=owner.id,
            source_claim_id=claim.id,
            status="active",
            granted_by="admin@example.test",
        )
    )
    db.session.commit()
    client = control_app.test_client()
    assert client.get("/api/admin/people?role=clubs", headers=headers()).json["rows"] == []
    claim.status = "approved"
    db.session.commit()
    entry = client.get("/api/admin/people?role=clubs", headers=headers()).json["rows"][0]
    assert entry["id"] == owner.id and "club_manager" in entry["roles"]
