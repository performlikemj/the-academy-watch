"""RB3V probes: real provider objects, case cycles and private account rights."""

import hashlib
import hmac
import json
import time
from datetime import timedelta
from unittest.mock import Mock

import pytest
import sqlalchemy as sa
import stripe
from src.auth import _user_serializer, issue_user_token
from src.models.admin_control import BillingCashEvent, SafeguardingCase, now
from src.models.league import EmailToken, UserAccount, db
from src.models.p2_foundation import NotificationOutbox
from src.models.player_suppression import PlayerSuppression
from src.models.trust import ContentReport
from src.routes.account import account_bp
from src.routes.billing import billing_bp
from src.routes.player_suppression import player_suppression_bp
from src.routes.trust import trust_bp
from src.services.admin_control_safety import reconcile_safety_boot
from src.services.notification_outbox import dispatch_due
from test_admin_control import action, headers, program, report, user
from test_admin_control import control_app as _control_app

control_app = _control_app


@pytest.mark.parametrize("target", ["player", "club"])
def test_repeat_hide_restore_hide_succeeds_and_dedupes(control_app, target):
    case = report("club_program", str(program().id)) if target == "club" else report()
    client = control_app.test_client()
    for kind in ("hide", "restore", "hide"):
        response = action(client, case, kind)
        assert response.status_code == 200, response.json
    assert NotificationOutbox.query.count() == 1
    assert NotificationOutbox.query.one().payload == {"case_id": case.id, "state": "hidden"}
    reconcile_safety_boot(control_app)
    assert SafeguardingCase.query.count() == 1


def test_old_tool_lift_then_report_resolution_succeeds_without_duplicate_email(control_app):
    control_app.register_blueprint(player_suppression_bp, url_prefix="/api")
    control_app.register_blueprint(trust_bp, url_prefix="/api")
    case = report()
    client = control_app.test_client()
    assert action(client, case, "hide").status_code == 200
    source_id = case.owned_suppression_id
    assert (
        client.post(f"/api/admin/suppressions/{source_id}/lift", headers=headers(), json={"notes": "Lift"}).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/admin/reports/{case.report_id}/resolve",
            headers=headers(),
            json={"status": "resolved", "resolution_notes": "Complete"},
        ).status_code
        == 200
    )
    assert db.session.get(ContentReport, case.report_id).status == "resolved"
    assert case.status == "closed"
    assert NotificationOutbox.query.count() == 2


@pytest.mark.parametrize("sql_failure", [False, True])
def test_notification_collision_or_sql_failure_never_aborts_admin_action(control_app, monkeypatch, sql_failure):
    import src.services.admin_control_safety as safety

    case = report()
    if sql_failure:

        def enqueue_failure(**kwargs):
            db.session.execute(sa.text("SELECT rb3v_missing_column"))

        monkeypatch.setattr(safety, "enqueue", enqueue_failure)
    else:
        db.session.add(
            NotificationOutbox(
                dedupe_key=f"safety:{case.id}:hidden:{user().id}",
                recipient_user_id=user().id,
                event_type="safeguarding_update",
                entity_type="user_account",
                entity_id=str(user().id),
                template="safeguarding_update",
                payload={"case_id": case.id, "version": 1, "state": "hidden"},
            )
        )
        db.session.commit()
    assert action(control_app.test_client(), case, "hide").status_code == 200
    assert PlayerSuppression.query.one().status == "active"
    assert case.notification_state == ("failed" if sql_failure else "deduplicated")
    assert NotificationOutbox.query.count() == (0 if sql_failure else 1)


def signed_event(event_id, event_type, obj, created):
    payload = json.dumps(
        {"id": event_id, "object": "event", "type": event_type, "created": created, "data": {"object": obj}},
        separators=(",", ":"),
    ).encode()
    timestamp = int(time.time())
    signature = hmac.new(b"whsec_rb3v", str(timestamp).encode() + b"." + payload, hashlib.sha256).hexdigest()
    return payload, f"t={timestamp},v1={signature}"


@pytest.mark.parametrize("refund_first", [False, True])
def test_real_signed_stripe_invoice_refund_replay_out_of_order_records_cash(control_app, monkeypatch, refund_first):
    from src.services.stripe_billing import handle_webhook

    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_rb3v")
    invoice = signed_event(
        "evt_invoice_rb3v",
        "invoice.paid",
        {
            "id": "in_rb3v",
            "object": "invoice",
            "currency": "usd",
            "amount_paid": 1500,
            "payment_intent": "pi_rb3v",
            "status_transitions": {"paid_at": 1790812800},
        },
        1790812800,
    )
    refund = signed_event(
        "evt_refund_rb3v",
        "charge.refunded",
        {
            "id": "ch_rb3v",
            "object": "charge",
            "currency": "usd",
            "payment_intent": "pi_rb3v",
            "amount_refunded": 250,
            "refunds": {
                "object": "list",
                "has_more": False,
                "data": [
                    {"id": "re_rb3v", "object": "refund", "status": "succeeded", "amount": 250, "created": 1790899200}
                ],
            },
        },
        1790899200,
    )
    real = stripe.Webhook.construct_event(*invoice, "whsec_rb3v")
    assert not isinstance(real, dict) and not isinstance(real.data.object, dict)
    events = (refund, invoice) if refund_first else (invoice, refund)
    for event in events + events:
        assert handle_webhook(*event)[1] == 200
    rows = {row.source_key: row for row in BillingCashEvent.query.all()}
    assert set(rows) == {"invoice:in_rb3v", "refund:re_rb3v"}
    assert (rows["invoice:in_rb3v"].amount_cents, rows["invoice:in_rb3v"].kind) == (1500, "receipt")
    assert (rows["refund:re_rb3v"].amount_cents, rows["refund:re_rb3v"].kind) == (250, "refund")
    assert all(row.currency == "usd" for row in rows.values())
    assert rows["refund:re_rb3v"].occurred_at > rows["invoice:in_rb3v"].occurred_at


def test_real_stripe_list_pages_and_reconciliation(control_app, monkeypatch):
    import src.services.admin_control_business as cash

    monkeypatch.setattr("src.config.stripe_config.configure_stripe", lambda: None)
    page = stripe.ListObject.construct_from(
        {
            "object": "list",
            "has_more": False,
            "data": [
                {
                    "id": "ip_rb3v",
                    "object": "invoice_payment",
                    "status": "paid",
                    "amount_paid": 1400,
                    "payment": {"type": "payment_intent", "payment_intent": "pi_modern"},
                }
            ],
        },
        "fixture",
    )
    monkeypatch.setattr(stripe.InvoicePayment, "list", lambda **kw: page)
    event = stripe.Event.construct_from(
        {
            "id": "evt_modern",
            "type": "invoice.paid",
            "created": 1790812800,
            "data": {
                "object": {
                    "id": "in_modern",
                    "object": "invoice",
                    "currency": "usd",
                    "payments": {"object": "list", "has_more": True, "data": []},
                }
            },
        },
        "fixture",
    )
    event_page = stripe.ListObject.construct_from({"object": "list", "data": [event]}, "fixture")
    monkeypatch.setattr(stripe.Event, "list", lambda **kw: event_page)
    cash.reconcile_cash()
    cash.reconcile_cash()
    assert BillingCashEvent.query.one().source_key == "invoice_payment:ip_rb3v"
    assert BillingCashEvent.query.one().amount_cents == 1400


def test_subscription_emails_sent_before_projection_provider_io(control_app, monkeypatch):
    import src.services.admin_control_business as cash
    import src.services.stripe_billing as billing

    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_rb3v")
    calls = []

    def apply(*args):
        billing._email_intents.get().append({"fixture": True})
        return True

    monkeypatch.setattr(billing, "_apply_event", apply)
    monkeypatch.setattr(billing, "_send_email_intent", lambda intent: calls.append("email"))
    monkeypatch.setattr(cash, "project_cash_isolated", lambda *args: calls.append("projection"))
    assert billing.handle_webhook(*signed_event("evt_order", "invoice.paid", {"id": "in_order"}, 1790812800))[1] == 200
    assert calls == ["email", "projection"]


def test_sensitive_suspension_reason_excluded_from_otp_export_and_user_dtos(control_app):
    control_app.register_blueprint(account_bp, url_prefix="/api")
    client = control_app.test_client()
    sensitive = "Parent Jane Doe reported grooming of Child Sensitive Sentinel"
    assert (
        client.post(f"/api/admin/users/{user().id}/suspend", headers=headers(), json={"reason": sensitive}).status_code
        == 200
    )
    db.session.add(
        EmailToken(
            email=user().email, token="valid-sensitive", purpose="login", expires_at=now() + timedelta(minutes=5)
        )
    )
    db.session.commit()
    login = client.post("/api/auth/verify-code", json={"email": user().email, "code": "valid-sensitive"})
    assert login.status_code == 403
    export = client.get(
        "/api/account/export", headers={"Authorization": "Bearer " + login.json["account_access_token"]}
    )
    assert export.status_code == 200, export.json
    assert export.json["account_standing"] == {"status": "suspended", "suspended_at": user().suspended_at.isoformat()}
    assert sensitive.encode() not in export.data + login.data
    assert user().suspension_reason == sensitive


def test_safety_dark_syncs_report_without_queuing_or_sending_notices(control_app, monkeypatch):
    control_app.register_blueprint(trust_bp, url_prefix="/api")
    case = report()
    assert action(control_app.test_client(), case, "hide").status_code == 200
    monkeypatch.setenv("ADMIN_SAFETY_ENABLED", "0")
    assert (
        control_app.test_client()
        .post(
            f"/api/admin/reports/{case.report_id}/resolve",
            headers=headers(),
            json={"status": "dismissed", "resolution_notes": "Reviewed"},
        )
        .status_code
        == 200
    )
    assert case.status == "closed" and case.notification_state == "safety_disabled"
    assert NotificationOutbox.query.count() == 1
    sender = Mock()
    assert dispatch_due(send=sender)["cancelled"] == 1
    sender.assert_not_called()


def pending_request():
    source = PlayerSuppression(
        player_api_id=321,
        reason_code="guardian_request",
        requester_role="guardian",
        requester_contact="original@fixture.test",
        request_statement="Guardian original evidence",
        notes="Original private note",
        status="requested",
    )
    db.session.add(source)
    db.session.commit()
    return source, SafeguardingCase.query.filter_by(suppression_id=source.id).one()


def test_takedown_hide_restore_hide_preserves_original_evidence_and_separate_admin_reason(control_app):
    source, case = pending_request()
    client = control_app.test_client()
    for kind in ("hide", "restore", "hide"):
        assert action(client, case, kind).status_code == 200
    reconcile_safety_boot(control_app)
    assert case.suppression_id == source.id
    assert (
        source.request_statement == "Guardian original evidence" and source.requester_contact == "original@fixture.test"
    )
    assert source.reason_code == "guardian_request"
    assert SafeguardingCase.query.count() == 1
    assert PlayerSuppression.query.count() == 1
    detail = client.get(f"/api/admin/safety/cases/{case.id}", headers=headers()).json
    assert detail["evidence"]["statement"] == "Guardian original evidence"
    assert any(event["reason"] == "Case review" for event in detail["events"])


def test_report_hide_syncs_sibling_without_taking_requesters_hold_ownership(control_app):
    source, sibling = pending_request()
    case = report()
    client = control_app.test_client()
    assert action(client, case, "hide").status_code == 200
    assert source.status == "active" and sibling.status == "investigating" and sibling.first_action_at is not None
    assert case.owned_suppression_id is None
    assert client.get(f"/api/admin/safety/cases/{case.id}", headers=headers()).json["case"]["owns_hold"] is False
    assert action(client, case, "restore").status_code == 400
    assert source.status == "active" and sibling.status == "investigating"
    assert source.request_statement == "Guardian original evidence"
    reconcile_safety_boot(control_app)
    assert SafeguardingCase.query.count() == 2


@pytest.mark.parametrize(
    "method,path,flag",
    [
        ("POST", "/api/admin/people", "ADMIN_PEOPLE_ENABLED"),
        ("GET", "/api/admin/users/1/suspend", "ADMIN_PEOPLE_ENABLED"),
        ("DELETE", "/api/admin/programs/1", "ADMIN_PROGRAMS_ENABLED"),
        ("PUT", "/api/admin/safety/cases/1", "ADMIN_SAFETY_ENABLED"),
        ("POST", "/api/admin/business/summary", "ADMIN_BUSINESS_ENABLED"),
        ("GET", "/api/admin/people", "ADMIN_PEOPLE_ENABLED"),
        ("OPTIONS", "/api/admin/people", "ADMIN_PEOPLE_ENABLED"),
    ],
)
def test_dark_wrong_methods_have_unknown_route_body_and_headers(control_app, monkeypatch, method, path, flag):
    monkeypatch.setenv(flag, "0")
    client = control_app.test_client()
    actual = client.open(path, method=method)
    unknown = client.open("/api/admin/rb3v-unknown", method=method)
    assert actual.status_code == unknown.status_code == 404
    assert actual.data == unknown.data
    assert dict(actual.headers) == dict(unknown.headers)


@pytest.mark.parametrize("path", ["people", "programs", "safety/cases", "business/summary"])
def test_huge_offset_is_400(control_app, path):
    assert (
        control_app.test_client()
        .get(f"/api/admin/{path}?offset=99999999999999999999999", headers=headers())
        .status_code
        == 400
    )


@pytest.mark.parametrize(
    "auth", [None, "Bearer ", "Basic malformed", "Bearer malformed", "expired", "bad-payload", "missing-account"]
)
def test_flag_off_account_rights_auth_matches_normal_bearer_bytes(control_app, monkeypatch, auth):
    control_app.register_blueprint(account_bp, url_prefix="/api")
    control_app.register_blueprint(billing_bp, url_prefix="/api")
    for flag in (
        "ADMIN_PEOPLE_ENABLED",
        "ADMIN_PROGRAMS_ENABLED",
        "ADMIN_SAFETY_ENABLED",
        "ADMIN_BUSINESS_ENABLED",
        "P2_FOUNDATION_ENABLED",
    ):
        monkeypatch.setenv(flag, "0")
    monkeypatch.setenv("BILLING_ENABLED", "1")
    if auth == "expired":
        with monkeypatch.context() as clock:
            clock.setattr("itsdangerous.timed.TimestampSigner.get_timestamp", lambda self: 1)
            auth = "Bearer " + issue_user_token(user().email)["token"]
    elif auth == "bad-payload":
        auth = "Bearer " + _user_serializer().dumps({"email": 7})
    elif auth == "missing-account":
        auth = "Bearer " + _user_serializer().dumps({"email": "missing@fixture.test"})
    h = {"Authorization": auth} if auth is not None else {}
    client = control_app.test_client()
    expected = client.post("/act", headers=h)
    assert expected.status_code == 401
    for method, path in (
        ("GET", "/api/account/export"),
        ("POST", "/api/account/delete"),
        ("POST", "/api/billing/portal"),
    ):
        response = client.open(path, method=method, headers=h)
        assert (response.status_code, response.data) == (expected.status_code, expected.data)


def test_last_owner_uses_verified_managers_when_staff_access_dark(control_app, monkeypatch):
    from src.models.funding import ClubProgramClaim, ClubProgramManager
    from src.routes.admin_control import last_owner_programs

    monkeypatch.setenv("CLUB_STAFF_ACCESS_ENABLED", "0")
    row = program()
    owner = user()

    def manager(person, status):
        claim = ClubProgramClaim(program_id=row.id, user_account_id=person.id, status=status)
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
        return claim

    manager(owner, "approved")
    assert last_owner_programs(owner.id) == [row.name]
    other = UserAccount.query.filter_by(email="admin@example.test").one()
    claim = manager(other, "pending")
    assert last_owner_programs(owner.id) == [row.name]
    claim.status = "approved"
    db.session.commit()
    assert last_owner_programs(owner.id) == []
    other.account_status = "suspended"
    db.session.commit()
    assert last_owner_programs(owner.id) == [row.name]
