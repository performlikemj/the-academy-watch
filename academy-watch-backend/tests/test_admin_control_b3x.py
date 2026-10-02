"""Final review probes and staging admin failures reversed into regressions."""

import pytest
import sqlalchemy as sa
from src.models.admin_control import BillingCashEvent, SafeguardingCase, SafeguardingCaseEvent, now
from src.models.billing import BillingSubscription
from src.models.funding import ClubProgramClaim, ClubProgramProfileRevision, ClubProgramUpdate
from src.models.league import UserAccount, db
from src.models.p2_foundation import NotificationOutbox
from src.models.player_suppression import PlayerSuppression
from src.models.showcase import LocalPlayer, PlayerProfileClaim
from src.models.trust import ContentReport, ScoutVerification
from src.services.admin_control_names import player_names, target_names
from src.services.admin_control_safety import case_hide_intent
from test_admin_control import action, headers, program, report, user
from test_admin_control import control_app as _control_app
from test_admin_control_postgres import pg_control as _pg_control

control_app = _control_app
pg_control = _pg_control


def guardian_request():
    row = PlayerSuppression(
        player_api_id=321,
        reason_code="guardian_request",
        requester_role="guardian",
        requester_contact="guardian@example.test",
        request_statement="Original guardian evidence",
    )
    db.session.add(row)
    db.session.commit()
    return row


@pytest.mark.parametrize("guardian", [False, True])
def test_original_lift_preserves_open_report_case(control_app, guardian):
    from src.routes.player_suppression import player_suppression_bp

    control_app.register_blueprint(player_suppression_bp, url_prefix="/api")
    suppression = guardian_request() if guardian else None
    guardian_case = SafeguardingCase.query.filter_by(suppression_id=suppression.id).one() if guardian else None
    incident = report()
    client = control_app.test_client()
    assert action(client, incident, "hide").status_code == 200
    suppression = suppression or db.session.get(PlayerSuppression, incident.owned_suppression_id)
    before = (incident.status, incident.closed_at, incident.resolver_email, incident.first_action_at, incident.version)
    source = db.session.get(ContentReport, incident.report_id)
    source_before = (source.status, source.resolved_at, source.resolution_notes)
    response = client.post(
        f"/api/admin/suppressions/{suppression.id}/lift", headers=headers(), json={"notes": "Guardian lift"}
    )
    assert response.status_code == 200, response.text
    db.session.expire_all()
    assert (incident.status, incident.closed_at, incident.resolver_email, incident.first_action_at) == before[:4]
    assert incident.version == before[4] + 1
    assert incident.owned_suppression_id is None and not case_hide_intent(incident)
    assert (source.status, source.resolved_at, source.resolution_notes) == source_before
    assert (
        SafeguardingCaseEvent.query.filter_by(case_id=incident.id)
        .order_by(SafeguardingCaseEvent.id.desc())
        .first()
        .action
        == "source_lifted"
    )
    assert not any(f"safety:{incident.id}:closed:" in row.dedupe_key for row in NotificationOutbox.query.all())
    assert incident.id in [row["id"] for row in client.get("/api/admin/safety/cases", headers=headers()).json["rows"]]
    if guardian_case:
        assert guardian_case.status == "closed"


def test_nonowner_withdrawal_keeps_guardian_hold(control_app):
    suppression, incident = guardian_request(), report()
    client = control_app.test_client()
    assert action(client, incident, "hide").status_code == 200
    assert not incident.owned_suppression_id and case_hide_intent(incident)
    assert action(client, incident, "restore").status_code == 200
    assert suppression.status == "active" and not case_hide_intent(incident)
    assert suppression.request_statement == "Original guardian evidence"
    assert db.session.get(ContentReport, incident.report_id).status == "open"


def subscription(status, scope="club_program", amount=2900):
    db.session.add(
        BillingSubscription(
            scope_type=scope,
            scope_id=1,
            product_code="club",
            price_code="standard",
            stripe_customer_id="cus_test",
            stripe_subscription_id=f"sub_{status}_{scope}",
            stripe_price_id="price_test",
            status=status,
            unit_amount=amount,
            currency="gbp",
            interval="month",
        )
    )


def test_overview_queue_counts_and_paying_revenue(control_app):
    club, person = program(), user()
    db.session.add_all(
        [
            ClubProgramClaim(program_id=club.id, user_account_id=person.id, status="pending"),
            ClubProgramProfileRevision(program_id=club.id, submitted_by_user_id=person.id, status="pending"),
            ClubProgramUpdate(
                program_id=club.id, author_user_id=person.id, title="Pending update", body="Stored content"
            ),
            ScoutVerification(
                user_account_id=person.id,
                full_name="Test Scout",
                organization="Test",
                role_title="Scout",
                statement="Evidence",
            ),
            PlayerProfileClaim(local_player_id=9, user_account_id=person.id, relationship_type="player"),
        ]
    )
    report()
    subscription("active", amount=2000)
    subscription("past_due")
    subscription("trialing")
    subscription("active", "user", amount=2100)
    db.session.commit()
    client = control_app.test_client()
    response = client.get("/api/admin/control/overview", headers=headers())
    assert response.status_code == 200, response.text
    data = response.json
    counts = {row["key"]: row["count"] for row in data["queues"]}
    assert all(
        counts[key] == 1
        for key in (
            "club_claims",
            "club_profiles",
            "club_updates",
            "scout_verifications",
            "profile_claims",
            "reports",
            "safeguarding",
        )
    )
    assert data["overdue_safeguarding"] == 1 and data["total"] == sum(counts.values())
    assert data["revenue"]["active_subscriptions"] == 2
    assert data["revenue"]["mrr_by_currency"] == {"gbp": 4100}
    assert data["revenue"]["past_due"] == 1
    business = client.get("/api/admin/business/summary", headers=headers()).json
    assert business["paying_clubs"] == 1 and business["past_due_clubs"] == 1


@pytest.mark.parametrize("enabled", ["programs", "people", "safety", "business"])
def test_overview_independent_flags_auth_and_query_scope(control_app, monkeypatch, enabled):
    from src.routes.admin_control import FLAGS

    for page, flag in FLAGS.items():
        monkeypatch.setenv(flag, "1" if page == enabled else "0")
    client = control_app.test_client()
    assert client.get("/api/admin/control/overview").status_code == 401
    assert client.get("/api/admin/control/overview", headers={"X-API-Key": "test-control-key"}).status_code == 401
    assert client.get("/api/admin/control/overview", headers=headers(role="user")).status_code == 401
    queries = []

    def record(_conn, _cursor, statement, *_args):
        queries.append(statement)

    sa.event.listen(db.engine, "before_cursor_execute", record)
    try:
        response = client.get("/api/admin/control/overview", headers=headers())
    finally:
        sa.event.remove(db.engine, "before_cursor_execute", record)
    assert response.status_code == 200 and response.headers["Cache-Control"] == "no-store"
    keys = {row["key"] for row in response.json["queues"]}
    assert ("revenue" in response.json) == (enabled == "business")
    assert ("reports" in keys) == (enabled == "safety")
    assert ("club_claims" in keys) == (enabled == "programs")
    assert ("profile_claims" in keys) == (enabled == "people")
    if enabled != "safety":
        assert not any("safeguarding_cases" in query or "content_reports" in query for query in queries)


def test_people_sort_filter_escape_and_private_suspension(control_app):
    person = user()
    person.account_status, person.suspension_reason = "suspended", "PRIVATE SUSPENSION REASON"
    person.suspended_by, person.suspended_at = "admin@example.test", now()
    db.session.add_all(
        [
            UserAccount(email="z@example.test", display_name="zulu", display_name_lower="zulu"),
            UserAccount(email="a@example.test", display_name="Alpha_%", display_name_lower="alpha_%"),
        ]
    )
    db.session.commit()
    client = control_app.test_client()
    assert [row["display_name"] for row in client.get("/api/admin/people?limit=2", headers=headers()).json["rows"]] == [
        "Alpha_%",
        "Test Admin",
    ]
    assert [
        row["display_name"]
        for row in client.get("/api/admin/people?sort=name_desc&limit=2", headers=headers()).json["rows"]
    ] == ["zulu", "Test Person"]
    data = client.get("/api/admin/people?standing=suspended", headers=headers()).json
    assert len(data["rows"]) == 1 and "suspension" not in data["rows"][0] and "PRIVATE" not in str(data)
    detail = client.get(f"/api/admin/people/{person.id}", headers=headers()).json
    assert detail["person"]["suspension"] == {
        "reason": person.suspension_reason,
        "by": person.suspended_by,
        "at": person.suspended_at.isoformat() + "Z",
    }
    assert client.get("/api/admin/people?q=_%25", headers=headers()).json["total"] == 1
    assert client.get("/api/admin/people?limit=100000", headers=headers()).json["limit"] == 100
    for qs in ("standing=bogus", "sort=name;DROP TABLE", "q=" + "a" * 121, "offset=-1"):
        assert client.get("/api/admin/people?" + qs, headers=headers()).status_code == 400
    assert client.get(f"/api/admin/people/{person.id}", headers=headers(role="user")).status_code == 401


def test_names_signed_targets_inventory_business_and_batch_bound(control_app):
    db.session.add_all(
        [LocalPlayer(id=i, display_name=f"Community {i}", normalized_name=f"community {i}") for i in range(10, 60)]
    )
    db.session.commit()
    queries = []

    def record(_conn, _cursor, statement, *_args):
        queries.append(statement)

    sa.event.listen(db.engine, "before_cursor_execute", record)
    try:
        names = player_names([-i for i in range(9, 60)] + [321, 987])
    finally:
        sa.event.remove(db.engine, "before_cursor_execute", record)
    assert names[-9] == "Local Prospect" and names[321] == "Test Prospect"
    assert names[-59] == "Community 59" and 987 not in names and len(queries) == 2
    assert target_names([("player_profile", "local:9"), ("player_profile", "-9")]) == {
        ("player_profile", "local:9"): "Local Prospect",
        ("player_profile", "-9"): "Local Prospect",
    }
    incident = report("player_profile", "-9")
    client = control_app.test_client()
    assert client.get("/api/admin/safety/cases", headers=headers()).json["rows"][0]["target_name"] == "Local Prospect"
    assert (
        client.get(f"/api/admin/safety/cases/{incident.id}", headers=headers()).json["case"]["target_name"]
        == "Local Prospect"
    )
    assert action(client, incident, "hide").status_code == 200
    assert (
        client.get("/api/admin/safety/hidden", headers=headers()).json["suppressions"][0]["player_name"]
        == "Local Prospect"
    )
    club = program()
    db.session.add(
        BillingCashEvent(
            source_key="cash",
            stripe_event_id="evt_cash",
            kind="receipt",
            product_code="club",
            scope_type="club_program",
            scope_id=club.id,
            purchaser_user_id=user().id,
            amount_cents=1000,
            currency="gbp",
            occurred_at=now(),
        )
    )
    db.session.commit()
    assert client.get("/api/admin/business/summary", headers=headers()).json["rows"][0]["scope_name"] == "Test Program"


@pytest.mark.parametrize("guardian", [False, True])
def test_postgres_original_lift_preserves_report(pg_control, guardian):
    test_original_lift_preserves_open_report_case(pg_control, guardian)


def test_postgres_guardian_withdrawal(pg_control):
    test_nonowner_withdrawal_keeps_guardian_hold(pg_control)


@pytest.mark.parametrize("enabled", [False, True])
def test_legacy_admin_names_are_gated_and_batch_claims(control_app, monkeypatch, enabled):
    from src.models.contact import ContactRequest
    from src.routes.contact import contact_bp
    from src.routes.showcase import showcase_bp
    from src.routes.trust import trust_bp

    for blueprint in (contact_bp, showcase_bp, trust_bp):
        control_app.register_blueprint(blueprint, url_prefix="/api")
    monkeypatch.setenv("ADMIN_PEOPLE_ENABLED", "1" if enabled else "0")
    monkeypatch.setenv("ADMIN_SAFETY_ENABLED", "1" if enabled else "0")
    claim = PlayerProfileClaim(local_player_id=9, user_account_id=user().id, relationship_type="player")
    db.session.add_all(
        [
            claim,
            ContactRequest(
                id="test-contact",
                scout_user_id=user().id,
                player_api_id=-9,
                message="PRIVATE INTRODUCTION",
                expires_at=now(),
            ),
        ]
    )
    db.session.commit()
    # The report is deliberately held/private; this must only enrich admin reads.
    db.session.add(
        ContentReport(
            reporter_user_id=user().id,
            subject_type="player_profile",
            subject_id="-9",
            reason_code="privacy",
            details="PRIVATE EVIDENCE",
        )
    )
    db.session.commit()
    client = control_app.test_client()
    claims = client.get("/api/admin/showcase/claims", headers=headers()).json["claims"]
    if enabled:
        assert claims[0]["player_name"] == "Local Prospect"
        assert claims[0]["subject_label"] == "Local Prospect · Local #9"
    else:
        assert "subject_label" not in claims[0]
    contacts = client.get("/api/admin/contact/requests", headers=headers()).json["requests"]
    detail = client.get("/api/admin/contact/requests/test-contact", headers=headers()).json["request"]
    assert contacts[0]["player_name"] == detail["player_name"] == ("Local Prospect" if enabled else "Player -9")
    reports = client.get("/api/admin/reports", headers=headers()).json["reports"]
    assert (reports[0]["target"].get("name") == "Local Prospect") == enabled
    for path in ("/api/admin/showcase/claims", "/api/admin/contact/requests", "/api/admin/reports"):
        assert client.get(path).status_code == 401
    assert "PRIVATE INTRODUCTION" not in str(contacts)


def test_public_acknowledgment_confirms_receipt_without_identity_or_duplicate_oracle(control_app, monkeypatch):
    from src.routes.player_suppression import player_suppression_bp

    control_app.register_blueprint(player_suppression_bp, url_prefix="/api")
    monkeypatch.setenv("ADMIN_SAFETY_ENABLED", "0")
    client = control_app.test_client()
    body = {"requester_role": "guardian", "contact_email": "guardian@example.test", "statement": "Original evidence"}
    first = client.post("/api/players/321/takedown-request", json=body)
    repeat = client.post("/api/players/321/takedown-request", json={**body, "statement": "Replacement"})
    unknown = client.post("/api/players/999999/takedown-request", json=body)
    local = client.post("/api/local-players/9/takedown-request", json=body)
    assert first.status_code == repeat.status_code == unknown.status_code == local.status_code == 202
    assert first.json == repeat.json == unknown.json == local.json
    assert "received" in first.json["message"] and "does not replace or add" in first.json["message"]
    assert PlayerSuppression.query.filter_by(player_api_id=321).one().request_statement == "Original evidence"


def test_suspension_detail_never_enters_user_dto_export_or_auth_failure(control_app):
    from src.services.account import _SchemaView
    from src.services.admin_control_account import export_admin_control

    person = user()
    token = headers(email=person.email, role="user")
    person.account_status, person.suspension_reason = "suspended", "PRIVATE-REASON-SENTINEL"
    person.suspended_by, person.suspended_at = "private-actor@example.test", now()
    db.session.commit()
    export = export_admin_control(person, _SchemaView())
    for body in (person.to_dict(), export, control_app.test_client().post("/act", headers=token).json):
        assert "PRIVATE-REASON-SENTINEL" not in str(body)
        assert "private-actor@example.test" not in str(body)


@pytest.mark.parametrize("method", ["get", "post", "put", "patch", "delete", "head", "options"])
def test_overview_dark_matches_real_unrouted_app(monkeypatch, method):
    from src.main import app
    from src.routes.admin_control import FLAGS

    for flag in FLAGS.values():
        monkeypatch.setenv(flag, "0")
    client = app.test_client()
    dark = getattr(client, method)("/api/admin/control/overview")
    missing = getattr(client, method)("/api/admin/control/missing-b3x-route")
    assert dark.status_code == missing.status_code
    assert dark.headers.get("Allow") == missing.headers.get("Allow")
    assert dark.headers.get("Cache-Control") == missing.headers.get("Cache-Control")
    assert dark.data == missing.data


def test_claim_list_name_and_account_queries_are_constant_per_batch(control_app):
    from src.routes.showcase import showcase_bp

    control_app.register_blueprint(showcase_bp, url_prefix="/api")
    db.session.add(PlayerProfileClaim(local_player_id=9, user_account_id=user().id, relationship_type="player"))
    db.session.commit()
    client, auth = control_app.test_client(), headers()

    def read_count():
        queries = []

        def record(_conn, _cursor, statement, *_args):
            queries.append(statement)

        sa.event.listen(db.engine, "before_cursor_execute", record)
        try:
            response = client.get("/api/admin/showcase/claims", headers=auth)
        finally:
            sa.event.remove(db.engine, "before_cursor_execute", record)
        assert response.status_code == 200
        return len(queries), response.json["claims"]

    one, _ = read_count()
    for pid in range(10, 35):
        db.session.add(LocalPlayer(id=pid, display_name=f"Prospect {pid}", normalized_name=f"prospect {pid}"))
        db.session.add(PlayerProfileClaim(local_player_id=pid, user_account_id=user().id, relationship_type="player"))
    db.session.commit()
    many, rows = read_count()
    assert len(rows) == 26 and one == many and many <= 8
    assert all(row["player_name"] and row["subject_label"] for row in rows)


def test_hidden_inventory_does_not_select_or_decrypt_evidence(control_app, monkeypatch):
    suppression = guardian_request()
    suppression.status = "active"
    db.session.commit()
    db.session.expire_all()
    from src.services.player_suppression_crypto import EncryptedSuppressionText

    def forbidden(*_args):
        raise AssertionError("Inventory must not decrypt requester contact, statement or notes")

    monkeypatch.setattr(EncryptedSuppressionText, "process_result_value", forbidden)
    response = control_app.test_client().get("/api/admin/safety/hidden", headers=headers())
    assert response.status_code == 200 and response.json["suppressions"][0]["player_name"] == "Test Prospect"
