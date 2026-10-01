"""Final review-duel probes reversed into regression tests (X/O union)."""

import pytest
from src.models.admin_control import SafeguardingCase, SafeguardingCaseEvent, now
from src.models.league import UserAccount, db
from src.models.player_suppression import PlayerSuppression
from src.models.trust import ContentReport
from src.services.account import _SchemaView
from src.services.admin_control_account import erase_admin_control
from src.services.admin_control_safety import reconcile_safety_boot
from test_admin_control import action, headers, program, report
from test_admin_control import control_app as _control_app

control_app = _control_app


@pytest.mark.parametrize("closed", [False, True])
@pytest.mark.parametrize("target", ["player", "club"])
def test_second_case_hide_survives_first_restore(control_app, target, closed):
    kind, tid = ("club_program", str(program().id)) if target == "club" else ("player_profile", "321")
    a, b = report(kind, tid), report(kind, tid)
    client = control_app.test_client()
    assert action(client, a, "hide").status_code == 200
    assert action(client, b, "hide").status_code == 200
    if closed:
        assert action(client, b, "close").status_code == 200
    response = action(client, a, "restore")
    assert response.status_code == 400
    assert "another case" in response.json["error"].lower()
    assert client.get(f"/api/admin/safety/cases/{b.id}", headers=headers()).json["case"]["hidden"]


def test_dark_sibling_options_has_no_wildcard_post(monkeypatch):
    from src.main import app

    monkeypatch.setenv("ADMIN_PEOPLE_ENABLED", "0")
    response = app.test_client().options("/api/admin/users/1/author-permission")
    assert set(response.headers["Allow"].split(", ")) == {"GET", "HEAD", "OPTIONS", "PUT"}


@pytest.mark.parametrize("status", ["requested", "active"])
def test_dark_duplicate_contract_preserves_original_evidence(control_app, monkeypatch, status):
    from src.routes.player_suppression import player_suppression_bp

    control_app.register_blueprint(player_suppression_bp, url_prefix="/api")
    monkeypatch.setenv("ADMIN_SAFETY_ENABLED", "0")
    client = control_app.test_client()

    def submit(contact, statement):
        return client.post(
            "/api/players/321/takedown-request",
            json={
                "requester_role": "guardian",
                "contact_email": contact,
                "statement": statement,
            },
        )

    first = submit("original@example.test", "Original evidence")
    row = PlayerSuppression.query.one()
    row.status = status
    db.session.commit()
    before = row.updated_at
    second = submit("replacement@example.test", "Replacement evidence")
    unknown = client.post(
        "/api/players/999999/takedown-request",
        json={
            "requester_role": "guardian",
            "contact_email": "unknown@example.test",
            "statement": "Unknown evidence",
        },
    )
    assert first.status_code == second.status_code == unknown.status_code == 202
    assert first.json == second.json == unknown.json
    assert "does not replace or add" in second.json["message"]
    assert (row.requester_contact, row.request_statement, row.updated_at) == (
        "original@example.test",
        "Original evidence",
        before,
    )
    assert SafeguardingCase.query.count() == 0


@pytest.mark.parametrize("source_type", ["report", "suppression"])
def test_reconcile_repairs_preapply_window_but_preserves_case_decisions(control_app, source_type):
    client = control_app.test_client()
    if source_type == "report":
        case = report()
        source = db.session.get(ContentReport, case.report_id)
        source.status, source.resolved_at = "resolved", now()
    else:
        source = PlayerSuppression(
            player_api_id=321,
            reason_code="guardian_request",
            requester_role="guardian",
            requester_contact="guardian@example.test",
            request_statement="Original evidence",
        )
        db.session.add(source)
        db.session.commit()
        case = SafeguardingCase.query.filter_by(suppression_id=source.id).one()
        source.status, source.decided_at = "lifted", now()
    db.session.commit()
    stale_id = case.id
    protected = report("player_profile", "321")
    assert action(client, protected, "hide").status_code == 200
    held_id = protected.owned_suppression_id
    # Main in the preapply window does not emit case events or update cases.
    db.session.commit()
    for _ in range(2):
        reconcile_safety_boot(control_app)
    db.session.expire_all()
    repaired = db.session.get(SafeguardingCase, stale_id)
    assert repaired.status == "closed" and repaired.first_action_at is not None
    assert protected.status == "investigating" and protected.owned_suppression_id == held_id
    assert PlayerSuppression.query.filter_by(id=held_id).one().status == "active"


def test_hidden_inventory_metadata_and_page_31(control_app):
    db.session.add_all(
        [
            PlayerSuppression(
                player_api_id=1000 + i,
                reason_code="admin_other",
                requester_role="other",
                requester_contact="fixture",
                request_statement="Fixture",
                status="active",
            )
            for i in range(35)
        ]
    )
    db.session.commit()
    client = control_app.test_client()
    first = client.get("/api/admin/safety/hidden?limit=30", headers=headers()).json
    assert len(first["suppressions"]) == 30
    assert first["suppression_total"] == 35 and first["suppression_has_more"]
    second = client.get("/api/admin/safety/hidden?limit=30&suppression_offset=30", headers=headers()).json
    assert len(second["suppressions"]) == 5 and not second["suppression_has_more"]
    assert second["program_offset"] == 0
    assert not ({row["id"] for row in first["suppressions"]} & {row["id"] for row in second["suppressions"]})


def test_erase_case_generated_copies_preserves_requester_evidence_and_hold(control_app):
    case = report()
    assert action(control_app.test_client(), case, "hide").status_code == 200
    generated = db.session.get(PlayerSuppression, case.suppression_id)
    # Recreate the reviewed-head persisted copies, which must also be erased.
    generated.requester_contact = "admin@example.test"
    generated.request_statement = generated.notes = "Admin private reason"
    genuine = PlayerSuppression(
        player_api_id=999,
        reason_code="guardian_request",
        requester_role="guardian",
        requester_contact="admin@example.test",
        request_statement="Genuine guardian evidence",
        status="active",
    )
    db.session.add(genuine)
    db.session.commit()
    admin = UserAccount.query.filter_by(email="admin@example.test").one()
    erase_admin_control(admin.id, admin.email, _SchemaView())
    db.session.commit()
    assert generated.requester_contact == "Account deleted"
    assert generated.request_statement == generated.notes == "[redacted]"
    assert (
        genuine.requester_contact == "admin@example.test" and genuine.request_statement == "Genuine guardian evidence"
    )
    assert generated.status == genuine.status == "active"
    assert case.owned_suppression_id == generated.id
    assert SafeguardingCaseEvent.query.filter_by(case_id=case.id, action="hide").one().actor_email == "Account deleted"


def test_auth_me_checks_standing_once_and_does_not_cache_across_requests(control_app, monkeypatch):
    import src.services.account_standing as standing
    from src.auth import issue_user_token
    from test_admin_control import user

    person = user()
    token = issue_user_token(person.email, role="scout")["token"]
    original = standing.assert_token_standing
    decodes = []

    def verify(payload):
        decodes.append(payload)
        return original(payload)

    monkeypatch.setattr(standing, "assert_token_standing", verify)
    client = control_app.test_client()
    h = {"Authorization": "Bearer " + token}
    response = client.get("/api/auth/me", headers=h)
    assert response.status_code == 200 and response.json["role"] == "scout"
    assert len(decodes) == 1
    person.account_status, person.auth_epoch = "suspended", 1
    db.session.commit()
    assert client.get("/api/auth/me", headers=h).status_code == 401
    person.account_status, person.auth_epoch = "active", 2
    db.session.commit()
    assert client.get("/api/auth/me", headers=h).status_code == 401
    fresh = issue_user_token(person.email)["token"]
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer " + fresh}).status_code == 200


@pytest.mark.parametrize("target", ["player", "club"])
def test_closed_nonowner_can_withdraw_intent_then_owner_restores(control_app, target):
    kind, tid = ("club_program", str(program().id)) if target == "club" else ("player_profile", "321")
    a, b = report(kind, tid), report(kind, tid)
    client = control_app.test_client()
    for case in (a, b):
        assert action(client, case, "hide").status_code == 200
    assert action(client, b, "close").status_code == 200
    withdrawn = action(client, b, "restore")
    assert withdrawn.status_code == 200 and withdrawn.json["case"]["hidden"]
    assert not withdrawn.json["case"]["hold_requested"]
    assert action(client, a, "restore").status_code == 200
    assert not client.get(f"/api/admin/safety/cases/{a.id}", headers=headers()).json["case"]["hidden"]


@pytest.mark.parametrize("target", ["player", "club"])
def test_original_tool_lift_retires_nonowner_intent_before_new_cycle(control_app, target):
    from src.routes.player_suppression import player_suppression_bp

    control_app.register_blueprint(player_suppression_bp, url_prefix="/api")
    kind, tid = ("club_program", str(program().id)) if target == "club" else ("player_profile", "321")
    a, b = report(kind, tid), report(kind, tid)
    client = control_app.test_client()
    for case in (a, b):
        assert action(client, case, "hide").status_code == 200
    assert action(client, b, "close").status_code == 200
    if target == "club":
        response = client.post(
            f"/api/admin/programs/{tid}/emergency-lift", headers=headers(), json={"reason": "Shared hold reviewed"}
        )
    else:
        response = client.post(
            f"/api/admin/suppressions/{a.suppression_id}/lift",
            headers=headers(),
            json={"notes": "Shared hold reviewed"},
        )
    assert response.status_code == 200
    assert not client.get(f"/api/admin/safety/cases/{b.id}", headers=headers()).json["case"]["hold_requested"]
    c = report(kind, tid)
    assert action(client, c, "hide").status_code == 200
    assert action(client, c, "restore").status_code == 200


def test_club_aliases_share_lock_and_hold_intent(control_app):
    from src.services.admin_control_safety import _target_lock_id

    tid = str(program().id)
    alias = "00" + tid
    assert _target_lock_id("club_program", tid) == _target_lock_id("club_program", alias)
    a, b = report("club_program", tid), report("club_program", alias)
    client = control_app.test_client()
    for case in (a, b):
        assert action(client, case, "hide").status_code == 200
    assert action(client, b, "close").status_code == 200
    assert action(client, a, "restore").status_code == 400
    assert action(client, b, "restore").status_code == 200
    assert action(client, a, "restore").status_code == 200
