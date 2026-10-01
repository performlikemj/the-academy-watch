# ruff: noqa: F811
"""B2 adversarial boundaries, state machine and privacy; synthetic test identities only."""

from datetime import date, timedelta
from uuid import uuid4

import pytest
from src.auth import issue_user_token
from src.models.club_access import ClubAccessGrant
from src.models.funding import ClubProgram, ClubSquad
from src.models.league import UserAccount, db
from src.models.opportunities import ApplicationEvent, ApplicationNote, OpportunityApplication, now
from src.models.p2_foundation import NotificationOutbox
from src.models.showcase import LocalPlayer, PlayerProfileClaim
from src.routes.opportunities import opportunities_bp
from src.services import opportunities as service
from src.services.account import _SchemaView, build_account_export, delete_account
from src.services.opportunities_account import export_opportunities, purge_retained
from test_club_console import _headers, client, club_app  # noqa: F401


@pytest.fixture
def env(club_app, monkeypatch):
    for flag in ("OPPORTUNITIES_ENABLED", "APPLICATIONS_ENABLED", "P2_FOUNDATION_ENABLED", "CLUB_STAFF_ACCESS_ENABLED"):
        monkeypatch.setenv(flag, "true")
    club_app.register_blueprint(opportunities_bp, url_prefix="/api")
    service.register_notifications()
    people = {}
    for key in ("adult", "adult2", "minor", "guardian", "pending", "unknown", "year18"):
        user = UserAccount(email=f"b2-{key}@example.test", display_name=f"Test {key}", display_name_lower=f"test {key}")
        local = LocalPlayer(
            display_name=f"Test Player {key}",
            status="approved",
            birth_date=date(2000, 1, 1),
            birth_year=2000,
            provenance="user",
        )
        if key in {"unknown", "year18"}:
            local.birth_date = None
            local.birth_year = now().year - 18 if key == "year18" else None
        elif key == "minor":
            local.birth_date, local.birth_year = date(now().year - 16, 1, 1), now().year - 16
        db.session.add_all([user, local])
        db.session.flush()
        local.api_player_id = -local.id
        claim = PlayerProfileClaim(
            user_account_id=user.id,
            local_player_id=local.id,
            relationship_type="guardian" if key == "guardian" else "player",
            status="pending" if key == "pending" else "approved",
        )
        db.session.add(claim)
        db.session.flush()
        people[key] = dict(
            user=user.id,
            local=local.id,
            claim=claim.id,
            headers={"Authorization": f"Bearer {issue_user_token(user.email)['token']}"},
        )
    db.session.commit()
    for entry in people.values():
        user = db.session.get(UserAccount, entry["user"])
        entry["headers"] = {"Authorization": f"Bearer {issue_user_token(user.email)['token']}"}
    return {
        "pid": club_app.c2["program_a"],
        "other": club_app.c2["program_b"],
        "actor": club_app.c2["users"]["a"],
        "people": people,
    }


def details(**kw):
    result = dict(
        type="trial",
        title="Adult development trial",
        description="A test-only opportunity.",
        venue="Test ground",
        starts_at=service.iso(now() + timedelta(days=14)),
        ends_at=service.iso(now() + timedelta(days=14, hours=2)),
        closes_at=service.iso(now() + timedelta(days=7)),
        status="published",
        timezone="UTC",
        capacity=1,
    )
    result.update(kw)
    return result


def create(client, env, **kw):
    resp = client.post(f"/api/club/{env['pid']}/opportunities", headers=_headers("a"), json=details(**kw))
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["opportunity"]


def apply(client, env, opportunity, person="adult", **kw):
    who = env["people"][person]
    data = dict(
        claim_id=who["claim"],
        position="Midfielder",
        current_club="",
        contact_consent=True,
        client_request_id=str(uuid4()),
    )
    data.update(kw)
    return client.post(f"/api/opportunities/{opportunity['id']}/applications", headers=who["headers"], json=data)


def move(client, env, app, status, **kw):
    return client.post(
        f"/api/club/{env['pid']}/applications/{app['id']}/transition",
        headers=_headers("a"),
        json={"expected_version": app["version"], "status": status, **kw},
    )


def test_public_has_no_identity_or_capacity_before_reservation(client, env):
    row = create(client, env)
    assert row["capacity"] == 1
    app = apply(client, env, row).get_json()["application"]
    public = client.get(f"/api/opportunities/{row['id']}").get_json()["opportunity"]
    assert (
        not {"capacity", "places_left", "application_count", "creator_user_id", "applicant_user_id", "claim_id"}
        & public.keys()
    )
    for person in env["people"]:
        assert f"b2-{person}@example.test" not in str(public)
    assert "Test Player" not in str(client.get("/api/opportunities").get_json())
    assert app["status"] == "new"
    assert service.open_opportunity_counts([env["pid"], env["other"]]) == {env["pid"]: 1}


@pytest.mark.parametrize("person", ["minor", "guardian", "pending", "unknown", "year18"])
def test_only_approved_unambiguous_adult_self_claim_applies(client, env, person):
    row = create(client, env)
    assert apply(client, env, row, person).status_code == 403
    assert OpportunityApplication.query.count() == 0
    assert NotificationOutbox.query.count() == 0


def test_foreign_claim_and_child_payload_denied(client, env):
    row = create(client, env)
    assert apply(client, env, row, claim_id=env["people"]["adult2"]["claim"]).status_code == 403
    assert apply(client, env, row, child_name="Never stored").status_code == 422
    assert apply(client, env, row, contact_consent=False).status_code == 422


@pytest.mark.parametrize(
    "path,method",
    [
        ("/opportunities", "get"),
        ("/opportunities/{oid}", "get"),
        ("/club/{pid}/opportunities", "get"),
        ("/club/{pid}/opportunities", "post"),
        ("/club/{pid}/opportunities/{oid}", "patch"),
        ("/club/{pid}/opportunities/{oid}/close", "post"),
        ("/opportunities/{oid}/applications", "post"),
        ("/me/applications", "get"),
        ("/me/application-claims", "get"),
        ("/me/applications/{aid}", "get"),
        ("/me/applications/{aid}/withdraw", "post"),
        ("/me/applications/{aid}/trial-response", "post"),
        ("/club/{pid}/opportunities/{oid}/applications", "get"),
        ("/club/{pid}/applications/{aid}", "get"),
        ("/club/{pid}/applications/{aid}/transition", "post"),
        ("/club/{pid}/applications/{aid}/notes", "post"),
    ],
)
def test_flag_off_neutral_before_auth(client, env, monkeypatch, path, method):
    monkeypatch.setenv("OPPORTUNITIES_ENABLED", "false")
    url = "/api" + path.format(oid=uuid4(), aid=uuid4(), pid=env["pid"])
    assert getattr(client, method)(url).status_code == 404
    if method == "get":
        assert client.head(url).status_code == 404
    assert service.open_opportunity_counts([env["pid"]]) == {}


def test_application_flag_independent_and_no_side_effects(client, env, monkeypatch):
    row = create(client, env)
    monkeypatch.setenv("APPLICATIONS_ENABLED", "false")
    assert client.get("/api/opportunities").status_code == 200
    assert apply(client, env, row).status_code == 404
    assert client.get("/api/me/applications").status_code == 404
    assert OpportunityApplication.query.count() == 0


def test_cross_club_resources_and_roles_denied(client, env):
    row = create(client, env)
    app = apply(client, env, row).get_json()["application"]
    for suffix in (f"/opportunities/{row['id']}/applications", f"/applications/{app['id']}"):
        assert client.get(f"/api/club/{env['other']}{suffix}", headers=_headers("b")).status_code == 404
    assert (
        client.patch(
            f"/api/club/{env['other']}/opportunities/{row['id']}",
            headers=_headers("b"),
            json={"expected_version": 1, "title": "Hijack"},
        ).status_code
        == 404
    )
    for suffix in ("transition", "notes"):
        assert (
            client.post(
                f"/api/club/{env['other']}/applications/{app['id']}/{suffix}",
                headers=_headers("b"),
                json={"expected_version": 1, "status": "shortlisted", "body": "foreign"},
            ).status_code
            == 404
        )
    assert (
        client.get(f"/api/me/applications/{app['id']}", headers=env["people"]["adult2"]["headers"]).status_code == 404
    )
    for role in ("coach", "analyst", "viewer"):
        user = UserAccount(
            email=f"role-{role}@example.test", display_name=f"Role {role}", display_name_lower=f"role {role}"
        )
        db.session.add(user)
        db.session.flush()
        db.session.add(
            ClubAccessGrant(program_id=env["pid"], user_account_id=user.id, role=role, all_squads=True, status="active")
        )
        db.session.commit()
        h = {"Authorization": f"Bearer {issue_user_token(user.email)['token']}"}
        assert client.get(f"/api/club/{env['pid']}/opportunities", headers=h).status_code == 403


def test_hidden_club_closes_all_public_and_recruiting_but_allows_withdrawal(client, env, monkeypatch):
    row = create(client, env)
    app = apply(client, env, row).get_json()["application"]
    program = db.session.get(ClubProgram, env["pid"])
    program.emergency_hidden = True
    db.session.commit()
    monkeypatch.setenv("P2_FOUNDATION_ENABLED", "false")
    assert client.get(f"/api/opportunities/{row['id']}").status_code == 404
    assert client.get("/api/opportunities").get_json()["opportunities"] == []
    assert apply(client, env, row, "adult2").status_code == 404
    assert client.get(f"/api/club/{env['pid']}/opportunities", headers=_headers("a")).status_code == 403
    assert (
        client.post(
            f"/api/me/applications/{app['id']}/withdraw",
            headers=env["people"]["adult"]["headers"],
            json={"expected_version": app["version"]},
        ).status_code
        == 200
    )


def test_claim_revocation_suppression_and_identity_age_rechecked(client, env):
    row = create(client, env)
    app = apply(client, env, row).get_json()["application"]
    claim = db.session.get(PlayerProfileClaim, app["claim_id"])
    claim.status = "revoked"
    db.session.commit()
    assert move(client, env, app, "shortlisted").status_code == 404
    claim.status = "approved"
    db.session.commit()
    local = db.session.get(LocalPlayer, env["people"]["adult"]["local"])
    local.birth_date = date(now().year - 16, 1, 1)
    db.session.commit()
    assert move(client, env, app, "shortlisted").status_code == 404
    assert client.get(f"/api/club/{env['pid']}/applications/{app['id']}", headers=_headers("a")).status_code == 404


def test_idempotent_submit_dedupes_transactional_notifications(client, env):
    row = create(client, env)
    key = str(uuid4())
    first = apply(client, env, row, client_request_id=key)
    intents = NotificationOutbox.query.count()
    replay = apply(client, env, row, client_request_id=key)
    assert first.status_code == 201 and replay.status_code == 200
    assert first.get_json() == replay.get_json()
    assert NotificationOutbox.query.count() == intents
    assert apply(client, env, row, client_request_id=key, position="Other").status_code == 409
    assert apply(client, env, row).status_code == 409
    for intent in NotificationOutbox.query.all():
        assert intent.entity_type == "user_account"
        assert intent.entity_id == str(env["people"]["adult"]["user"])
        assert set(intent.payload) == {"application_id", "version", "state"}
    assert intents == 2


def test_explicit_transitions_conflict_and_private_notes(client, env):
    row = create(client, env)
    app = apply(client, env, row).get_json()["application"]
    assert move(client, env, app, "offer").status_code == 409
    shortlisted = move(client, env, app, "shortlisted")
    assert shortlisted.status_code == 200
    assert move(client, env, app, "rejected").status_code == 409
    assert ApplicationEvent.query.count() == 2
    assert (
        client.post(
            f"/api/club/{env['pid']}/applications/{app['id']}/notes",
            headers=_headers("a"),
            json={"body": "Private decision rationale"},
        ).status_code
        == 201
    )
    applicant = client.get(f"/api/me/applications/{app['id']}", headers=env["people"]["adult"]["headers"]).get_json()
    assert "Private decision rationale" not in str(applicant)
    assert "notes" not in applicant["application"] and "events" not in applicant["application"]
    assert "Private decision rationale" in str(
        client.get(f"/api/club/{env['pid']}/applications/{app['id']}", headers=_headers("a")).get_json()
    )


def test_reservations_accept_decline_capacity_and_cancel(client, env):
    row = create(client, env)
    a = apply(client, env, row).get_json()["application"]
    b = apply(client, env, row, "adult2").get_json()["application"]
    a = move(client, env, a, "shortlisted").get_json()["application"]
    b = move(client, env, b, "shortlisted").get_json()["application"]
    invite = dict(trial_at=service.iso(now() + timedelta(days=14)), trial_venue="Test trial venue")
    a = move(client, env, a, "invited", **invite).get_json()["application"]
    assert move(client, env, b, "invited", **invite).status_code == 409
    assert "places_left" not in client.get(f"/api/opportunities/{row['id']}").get_json()["opportunity"]
    assert move(client, env, a, "attended").status_code == 409
    h = env["people"]["adult"]["headers"]
    confirmed = client.post(
        f"/api/me/applications/{a['id']}/trial-response",
        headers=h,
        json={"expected_version": a["version"], "response": "accept"},
    )
    assert confirmed.status_code == 200 and confirmed.get_json()["application"]["reservation_state"] == "confirmed"
    a = confirmed.get_json()["application"]
    withdrawn = client.post(
        f"/api/me/applications/{a['id']}/withdraw", headers=h, json={"expected_version": a["version"]}
    )
    assert withdrawn.status_code == 200 and service.reservations(row["id"]) == 0
    b = move(client, env, b, "invited", **invite).get_json()["application"]
    cancelled = client.post(
        f"/api/club/{env['pid']}/opportunities/{row['id']}/close",
        headers=_headers("a"),
        json={"expected_version": row["version"], "status": "cancelled"},
    )
    assert cancelled.status_code == 200
    assert service.application(b["id"]).status == "rejected"
    assert service.reservations(row["id"]) == 0


def test_offer_and_signed_require_separate_enrollment(client, env):
    row = create(client, env)
    app = apply(client, env, row).get_json()["application"]
    obj = service.application(app["id"])
    obj.status = "attended"
    obj.trial_at = now() - timedelta(hours=1)
    obj.reservation_state = "confirmed"
    db.session.commit()
    app = service.application_dict(obj)
    app = move(client, env, app, "offer").get_json()["application"]
    assert move(client, env, app, "signed").status_code == 422
    assert move(client, env, app, "signed", enrollment_confirmed=True).status_code == 200
    assert service.application(app["id"]).retention_expires_at <= now() + timedelta(days=180)


@pytest.mark.parametrize(
    "change",
    [
        {"squad_id": 999999},
        {"capacity": 0},
        {"type": "wrong"},
        {"timezone": "Wrong/Zone"},
        {"starts_at": None},
        {"birth_year_min": 2006, "birth_year_max": 2000},
        {"closes_at": "2020-01-01T00:00:00Z"},
        {"starts_at": "2026-01-01"},
        {"creator_user_id": 1},
    ],
)
def test_opportunity_validation(client, env, change):
    assert client.post(
        f"/api/club/{env['pid']}/opportunities", headers=_headers("a"), json=details(**change)
    ).status_code == (400 if "timezone" in change or change.get("starts_at") == "2026-01-01" else 422)


def test_foreign_squad_draft_visibility_age_band_and_locked_edits(client, env):
    squad = ClubSquad(program_id=env["other"], name="Other squad", kind="other")
    db.session.add(squad)
    db.session.commit()
    assert (
        client.post(
            f"/api/club/{env['pid']}/opportunities", headers=_headers("a"), json=details(squad_id=squad.id)
        ).status_code
        == 422
    )
    draft = create(client, env, status="draft")
    assert client.get(f"/api/opportunities/{draft['id']}").status_code == 404
    assert apply(client, env, draft).status_code == 404
    row = create(client, env, birth_year_min=2010, birth_year_max=2011)
    assert apply(client, env, row).status_code == 403
    row = create(client, env)
    apply(client, env, row)
    assert (
        client.patch(
            f"/api/club/{env['pid']}/opportunities/{row['id']}",
            headers=_headers("a"),
            json={"expected_version": 1, "starts_at": service.iso(now() + timedelta(days=20))},
        ).status_code
        == 409
    )
    assert (
        client.patch(
            f"/api/club/{env['pid']}/opportunities/{row['id']}",
            headers=_headers("a"),
            json={"expected_version": 1, "title": "Updated title"},
        ).status_code
        == 409
    )


def test_privacy_export_erasure_and_retention_while_flags_off(client, env, monkeypatch):
    row = create(client, env, type="position", starts_at=None, ends_at=None)
    app = apply(client, env, row).get_json()["application"]
    client.post(
        f"/api/club/{env['pid']}/applications/{app['id']}/notes", headers=_headers("a"), json={"body": "Private note"}
    )
    user = db.session.get(UserAccount, env["people"]["adult"]["user"])
    exported = build_account_export(user)
    assert exported["recruiting"]["applications"][0]["id"] == app["id"]
    assert len(exported["recruiting"]["application_events"]) == 1
    manager = export_opportunities(db.session.get(UserAccount, env["actor"]), _SchemaView())
    assert manager["recruiting"]["authored_application_notes"][0]["body"] == "Private note"
    for flag in ("OPPORTUNITIES_ENABLED", "APPLICATIONS_ENABLED"):
        monkeypatch.setenv(flag, "false")
    service.application(app["id"]).retention_expires_at = now() - timedelta(seconds=1)
    db.session.commit()
    result = purge_retained()
    db.session.commit()
    assert (
        result["applications"] == 1
        and result["application_events"] == 1
        and result["application_notes"] == 1
        and result["notifications"] == 2
    )
    assert OpportunityApplication.query.count() == 0
    assert ApplicationEvent.query.count() == 0
    assert ApplicationNote.query.count() == 0
    assert NotificationOutbox.query.count() == 0


def test_real_account_delete_handles_application_fk_and_staff_actor(client, env):
    row = create(client, env)
    app = apply(client, env, row).get_json()["application"]
    move(client, env, app, "shortlisted")
    user = db.session.get(UserAccount, env["people"]["adult"]["user"])
    delete_account(user)
    assert OpportunityApplication.query.count() == 0 and ApplicationEvent.query.count() == 0
    assert NotificationOutbox.query.count() == 0


def test_transaction_rollback_removes_state_event_and_intent(client, env):
    row = create(client, env)
    app, _ = service.submit(
        row["id"],
        env["people"]["adult"]["user"],
        dict(
            claim_id=env["people"]["adult"]["claim"],
            position="Defender",
            contact_consent=True,
            client_request_id=str(uuid4()),
        ),
    )
    assert app.id
    db.session.rollback()
    assert (
        OpportunityApplication.query.count() == 0
        and ApplicationEvent.query.count() == 0
        and NotificationOutbox.query.count() == 0
    )


def test_delivery_rechecks_version_claim_hold_recipient_permission(client, env, monkeypatch):
    row = create(client, env)
    app = apply(client, env, row).get_json()["application"]
    intent = NotificationOutbox.query.filter_by(recipient_user_id=env["people"]["adult"]["user"]).one()
    user = db.session.get(UserAccount, intent.recipient_user_id)
    assert service.notification_eligible(intent, user)
    rendered = service.notification_render(intent, user)
    assert "/onboarding/player" in rendered["text"]
    assert "Test Player" not in str(rendered) and "b2-adult" not in str(rendered)
    newer = move(client, env, app, "shortlisted").get_json()["application"]
    assert not service.notification_eligible(intent, user)
    latest = (
        NotificationOutbox.query.filter_by(recipient_user_id=user.id).order_by(NotificationOutbox.id.desc()).first()
    )
    assert service.notification_eligible(latest, user)
    claim = db.session.get(PlayerProfileClaim, newer["claim_id"])
    claim.status = "revoked"
    db.session.commit()
    assert not service.notification_eligible(latest, user)
    claim.status = "approved"
    db.session.commit()
    program = db.session.get(ClubProgram, env["pid"])
    program.emergency_hidden = True
    db.session.commit()
    assert not service.notification_eligible(latest, user)
    program.emergency_hidden = False
    db.session.commit()
    manager_intent = (
        NotificationOutbox.query.filter_by(recipient_user_id=env["actor"])
        .order_by(NotificationOutbox.id.desc())
        .first()
    )
    manager = db.session.get(UserAccount, env["actor"])
    assert service.notification_eligible(manager_intent, manager)
    from src.models.funding import ClubProgramManager

    ClubProgramManager.query.filter_by(program_id=env["pid"], user_account_id=env["actor"]).one().status = "revoked"
    db.session.commit()
    assert not service.notification_eligible(manager_intent, manager)
    monkeypatch.setenv("APPLICATIONS_ENABLED", "false")
    assert not service.notification_eligible(latest, user)


@pytest.mark.parametrize("field", ["type", "gender_program", "status"])
def test_malformed_enum_objects_return_validation_error(client, env, field):
    resp = client.post(f"/api/club/{env['pid']}/opportunities", headers=_headers("a"), json=details(**{field: []}))
    assert resp.status_code == 422


def test_retention_is_bounded_and_closed_unexpired_rows_cannot_starve_purge(client, env):
    earlier = create(client, env)
    row = service.opportunity(earlier["id"])
    row.status, row.closed_at = "closed", now()
    row.closes_at = now() - timedelta(days=1)
    db.session.commit()
    opportunity = create(client, env)
    for person in ("adult", "adult2"):
        data = apply(client, env, opportunity, person).get_json()["application"]
        service.application(data["id"]).retention_expires_at = now() - timedelta(seconds=1)
        db.session.commit()
    assert purge_retained(limit=1)["applications"] == 1
    db.session.commit()
    assert OpportunityApplication.query.count() == 1
    assert purge_retained(limit=1)["applications"] == 1
    db.session.commit()
    assert OpportunityApplication.query.count() == 0


def test_staff_rejection_is_blocked_after_adult_claim_revoked(client, env):
    row = create(client, env)
    app = apply(client, env, row).get_json()["application"]
    db.session.get(PlayerProfileClaim, app["claim_id"]).status = "revoked"
    db.session.commit()
    assert move(client, env, app, "rejected").status_code == 404
