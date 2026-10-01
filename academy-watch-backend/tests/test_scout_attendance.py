# ruff: noqa: F811
"""Attendance auth/state/no-applicant-leakage, Today capability scopes and approved-pin distance."""

from datetime import timedelta
from uuid import uuid4

import pytest
from src.auth import issue_user_token
from src.models.club_access import ClubAccessGrant
from src.models.funding import ClubProgram, ClubProgramProfileRevision, ClubSquad
from src.models.league import UserAccount, db
from src.models.opportunities import ClubOpportunity, now
from src.models.p2_foundation import AdminActionEvent, NotificationOutbox
from src.models.scout_attendance import ScoutAttendance
from src.models.trust import ScoutVerification
from src.models.video import VideoMatch
from src.routes.scout_attendance import scout_attendance_bp
from src.services import scout_attendance as service
from src.services.account import _SchemaView
from src.services.scout_attendance_account import erase_attendance, export_attendance, purge_expired
from test_club_console import _headers, client, club_app  # noqa: F401
from test_opportunities import apply, create, env  # noqa: F401


@pytest.fixture
def c4(club_app, env, monkeypatch):
    monkeypatch.setenv("SCOUT_ATTEND_ENABLED", "true")
    monkeypatch.setenv("CLUB_DIRECTORY_ENABLED", "true")
    club_app.register_blueprint(scout_attendance_bp, url_prefix="/api")
    service.register_notifications()
    scout_id = club_app.c2["users"]["scout"]
    db.session.add(
        ScoutVerification(
            user_account_id=scout_id,
            full_name="Test Scout",
            organization="Test organization",
            role_title="Scout",
            statement="Test only",
            status="approved",
        )
    )
    db.session.commit()
    env["scout"] = scout_id
    env["scout_headers"] = _headers("scout")
    return env


def ask(client, c4, post, **data):
    return client.post(
        f"/api/opportunities/{post['id']}/attendance",
        headers=c4["scout_headers"],
        json={"note": "Please let me observe.", "no_approach_confirmed": True, **data},
    )


def trial(client, c4, **kw):
    return create(client, c4, birth_year_max=2005, **kw)


def answer(client, c4, row, **kw):
    return client.post(
        f"/api/club/{c4['pid']}/attendance/{row['id']}/decision",
        headers=_headers("a"),
        json={
            "decision": "accepted",
            "expected_version": row["version"],
            "arrival_instructions": "Report to reception.",
            **kw,
        },
    )


def test_one_event_lifecycle_atomic_audit_intents_and_no_applicant_access(client, c4):
    post = trial(client, c4)
    app = apply(client, c4, post).get_json()["application"]
    before = NotificationOutbox.query.count()
    response = ask(client, c4, post)
    assert response.status_code == 201, response.get_json()
    row = response.get_json()["attendance"]
    assert ask(client, c4, post).status_code == 200
    assert ScoutAttendance.query.count() == 1
    assert NotificationOutbox.query.count() == before + 2
    assert AdminActionEvent.query.filter_by(action="scout_attendance_requested").count() == 1
    assert ask(client, c4, post, note="Different").status_code == 409
    assert "applicant" not in str(row) and "claim_id" not in str(row)
    for suffix in [f"/opportunities/{post['id']}/applications", f"/applications/{app['id']}"]:
        assert client.get(f"/api/club/{c4['pid']}{suffix}", headers=c4["scout_headers"]).status_code == 403
    accepted = answer(client, c4, row)
    assert accepted.status_code == 200, accepted.get_json()
    assert accepted.get_json()["attendance"]["arrival_instructions"] == "Report to reception."
    assert answer(client, c4, row).status_code == 409
    today = client.get(f"/api/club/{c4['pid']}/today", headers=_headers("a"))
    assert today.status_code == 200, today.get_json()
    assert today.get_json()["queues"]["applications"][0]["new"] == 1
    assert today.get_json()["queues"]["attendance"] == []
    assert accepted.headers["Cache-Control"] == "no-store"
    got = client.get("/api/me/scout-attendance", headers=c4["scout_headers"]).get_json()["attendance"][0]
    withdrawn = client.post(
        f"/api/me/scout-attendance/{row['id']}/withdraw",
        headers=c4["scout_headers"],
        json={"expected_version": got["version"]},
    )
    assert withdrawn.status_code == 200
    assert "arrival_instructions" not in withdrawn.get_json()["attendance"]


def test_unverified_revoked_suspended_denied_and_not_stored(client, c4):
    post = trial(client, c4)
    for state in ("revoked", "pending", "rejected"):
        verification = ScoutVerification.query.filter_by(user_account_id=c4["scout"]).first()
        verification.status = state
        db.session.commit()
        assert ask(client, c4, post).status_code == 403
    assert ScoutAttendance.query.count() == 0
    verification.status = "approved"
    db.session.get(UserAccount, c4["scout"]).account_status = "suspended"
    db.session.commit()
    assert ask(client, c4, post).status_code == 401


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "draft"},
        {"status": "closed"},
        {"birth_year_max": now().year - 16},
        {"birth_year_max": None},
        {"type": "position", "starts_at": None, "ends_at": None},
    ],
)
def test_only_published_explicit_adult_event(client, c4, changes):
    post = create(
        client, c4, **{"birth_year_max": 2005, **{k: v for k, v in changes.items() if k != "status" or v != "closed"}}
    )
    if changes.get("status") == "closed":
        db.session.get(ClubOpportunity, post["id"]).status = "closed"
        db.session.commit()
    assert ask(client, c4, post).status_code == 404


def test_confirmation_validation_no_cross_club_or_other_scout(client, c4):
    post = trial(client, c4)
    assert ask(client, c4, post, no_approach_confirmed=False).status_code == 422
    assert ask(client, c4, post, child_name="Never stored").status_code == 400
    assert ask(client, c4, post, note="x" * 501).status_code == 422
    row = ask(client, c4, post).get_json()["attendance"]
    assert (
        client.post(
            f"/api/club/{c4['other']}/attendance/{row['id']}/decision",
            headers=_headers("b"),
            json={"decision": "declined", "expected_version": 1},
        ).status_code
        == 404
    )
    assert client.get(f"/api/club/{c4['pid']}/today", headers=_headers("b")).status_code == 403
    assert (
        client.post(
            f"/api/me/scout-attendance/{row['id']}/withdraw", headers=_headers("a"), json={"expected_version": 1}
        ).status_code
        == 403
    )
    assert answer(client, c4, row, arrival_instructions="").status_code == 422
    assert answer(client, c4, row, decision="declined").status_code == 200


def test_hide_revocation_erasure_delivery_rechecks(client, c4, monkeypatch):
    post = trial(client, c4)
    row = ask(client, c4, post).get_json()["attendance"]
    intent = NotificationOutbox.query.filter_by(template="c4_attendance", recipient_user_id=c4["scout"]).first()
    user = db.session.get(UserAccount, c4["scout"])
    assert service.eligible(intent, user)
    monkeypatch.setenv("SCOUT_ATTEND_ENABLED", "false")
    assert not service.eligible(intent, user)
    monkeypatch.setenv("SCOUT_ATTEND_ENABLED", "true")
    db.session.get(ClubProgram, c4["pid"]).emergency_hidden = True
    db.session.commit()
    assert not service.eligible(intent, user)
    assert client.get("/api/me/scout-attendance", headers=c4["scout_headers"]).get_json()["attendance"] == []
    db.session.get(ClubProgram, c4["pid"]).emergency_hidden = False
    db.session.commit()
    assert service.eligible(intent, user)
    verification = ScoutVerification.query.filter_by(user_account_id=c4["scout"]).first()
    verification.status = "revoked"
    db.session.commit()
    assert not service.eligible(intent, user)
    verification.status = "approved"
    db.session.commit()
    assert export_attendance(user, _SchemaView())["scout_attendance"][0]["id"] == row["id"]
    monkeypatch.setenv("SCOUT_ATTEND_ENABLED", "false")
    assert erase_attendance(user.id, _SchemaView())["scout_attendance"]["deleted"] == 1
    db.session.commit()
    assert NotificationOutbox.query.filter_by(template="c4_attendance").count() == 0


@pytest.mark.parametrize("role", ["coach", "analyst", "viewer", "manager"])
def test_today_role_queue_allowlist(client, c4, role):
    post = trial(client, c4)
    ask(client, c4, post)
    user = UserAccount(email=f"c4-{role}@example.test", display_name=role, display_name_lower=role)
    db.session.add(user)
    db.session.flush()
    db.session.add(
        ClubAccessGrant(program_id=c4["pid"], user_account_id=user.id, role=role, all_squads=True, status="active")
    )
    db.session.commit()
    headers = {"Authorization": "Bearer " + issue_user_token(user.email)["token"]}
    response = client.get(f"/api/club/{c4['pid']}/today", headers=headers)
    assert response.status_code == 200, response.get_json()
    queues = response.get_json()["queues"]
    assert "attendance" not in queues and "introductions" not in queues
    assert ("applications" in queues) == (role == "manager")
    assert "team_sheet" in queues and "analysing" in queues
    row = ScoutAttendance.query.first()
    assert (
        client.post(
            f"/api/club/{c4['pid']}/attendance/{row.id}/decision",
            headers=headers,
            json={"decision": "declined", "expected_version": 1},
        ).status_code
        == 403
    )


def test_scoped_today_never_exposes_legacy_or_other_squad_analysis(client, c4):
    user = UserAccount(email="scope-c4@example.test", display_name="Scoped", display_name_lower="scoped")
    squad = ClubSquad(program_id=c4["pid"], name="Test squad", kind="first_team")
    db.session.add_all([user, squad])
    db.session.flush()
    db.session.add(
        ClubAccessGrant(program_id=c4["pid"], user_account_id=user.id, role="coach", all_squads=True, status="active")
    )
    db.session.add_all(
        [
            VideoMatch(
                club_program_id=c4["pid"],
                squad_id=squad.id,
                status="processing",
                opponent_name="Private opponent",
                uploaded_at=now(),
                blob_etag="x",
                scoped_ready_etag="x",
                scoped_snapshot="x",
            ),
            VideoMatch(
                club_program_id=c4["pid"],
                status="uploaded",
                opponent_name="Unassigned opponent",
                uploaded_at=now(),
                blob_etag="x",
            ),
        ]
    )
    db.session.commit()
    headers = {"Authorization": "Bearer " + issue_user_token(user.email)["token"]}
    queues = client.get(f"/api/club/{c4['pid']}/today", headers=headers).get_json()["queues"]
    assert queues["analysing"] == [] and queues["team_sheet"] == []
    manager = client.get(f"/api/club/{c4['pid']}/today", headers=_headers("a")).get_json()["queues"]
    assert len(manager["analysing"]) == 1 and len(manager["team_sheet"]) == 1
    assert "blob" not in str(manager) and "player_name" not in str(manager)
    from src.services.club_access import record_coverage

    scoped = VideoMatch.query.filter_by(opponent_name="Private opponent").one()
    record_coverage(scoped, origin=True)
    db.session.commit()
    queues = client.get(f"/api/club/{c4['pid']}/today", headers=headers).get_json()["queues"]
    assert [m["id"] for m in queues["analysing"]] == [scoped.id]
    assert queues["team_sheet"] == []
    scoped.scoped_ready_etag = "replacing"
    db.session.commit()
    assert client.get(f"/api/club/{c4['pid']}/today", headers=headers).get_json()["queues"]["analysing"] == []


def test_distance_approved_pin_unknown_exclusion_and_body_only(client, c4):
    one, two = trial(client, c4), create(client, c4, birth_year_max=2005, title="Further test trial")
    db.session.get(ClubOpportunity, two["id"]).program_id = c4["other"]
    for pid, lat in [(c4["pid"], 35.0), (c4["other"], 36.0)]:
        revision = ClubProgramProfileRevision(
            program_id=pid, submitted_by_user_id=c4["actor"], status="approved", latitude=lat, longitude=139.0
        )
        db.session.add(revision)
        db.session.flush()
        db.session.get(ClubProgram, pid).approved_profile_revision_id = revision.id
    db.session.add(
        ClubProgramProfileRevision(
            program_id=c4["other"], submitted_by_user_id=c4["actor"], status="pending", latitude=35.0, longitude=139.0
        )
    )
    db.session.commit()
    response = client.post(
        "/api/opportunities/search", json={"lat": 35.0, "lng": 139.0, "radius_km": 50, "adult_sessions": True}
    )
    assert response.status_code == 200, response.get_json()
    assert [r["id"] for r in response.get_json()["opportunities"]] == [one["id"]]
    assert response.get_json()["opportunities"][0]["distance_km"] == 0
    all_rows = client.post("/api/opportunities/search", json={"lat": 35.0, "lng": 139.0}).get_json()["opportunities"]
    assert all_rows[1]["distance_km"] == pytest.approx(111.2, abs=0.1)
    assert client.get("/api/opportunities?lat=35&lng=139").status_code == 400
    for payload in [
        {"lat": 35},
        {"lat": True, "lng": 139},
        {"lat": "nan", "lng": 139},
        {"radius_km": 50},
        {"lat": 35, "lng": 139, "radius_km": 251},
        {"page": 101},
        {"type": []},
        {"type": {}},
    ]:
        assert client.post("/api/opportunities/search", json=payload).status_code == 400
    assert "latitude" not in str(response.get_json()) and "capacity" not in str(response.get_json())
    assert client.post("/api/opportunities/search", json={}).get_json()["opportunities"][0]["distance_km"] is None


@pytest.mark.parametrize(
    "path,method",
    [
        ("/scout-attendance/features", "get"),
        ("/opportunities/search", "post"),
        ("/opportunities/{oid}/attendance", "post"),
        ("/me/scout-attendance", "get"),
        ("/me/scout-attendance/{rid}/withdraw", "post"),
        ("/club/{pid}/today", "get"),
        ("/club/{pid}/attendance/{rid}/decision", "post"),
    ],
)
def test_dark_neutral_before_auth(client, c4, monkeypatch, path, method):
    monkeypatch.setenv("SCOUT_ATTEND_ENABLED", "false")
    url = "/api" + path.format(oid=uuid4(), rid=uuid4(), pid=c4["pid"])
    assert getattr(client, method)(url).status_code == 404
    if method == "get":
        assert client.head(url).status_code == 404


def test_retention_independent_of_flags(client, c4, monkeypatch):
    post = trial(client, c4)
    ask(client, c4, post)
    row = ScoutAttendance.query.first()
    row.retention_expires_at = now() - timedelta(seconds=1)
    db.session.commit()
    monkeypatch.setenv("SCOUT_ATTEND_ENABLED", "false")
    assert purge_expired() == 1
    db.session.commit()
    assert ScoutAttendance.query.count() == 0


@pytest.mark.parametrize("club_app", [True], indirect=True)
def test_per_account_rate_limit(client, c4, club_app, monkeypatch):
    from src.extensions import limiter

    monkeypatch.setattr(limiter, "enabled", True)
    club_app.config["RATELIMIT_ENABLED"] = True
    limiter.init_app(club_app)
    limiter.reset()
    post = trial(client, c4)
    for _ in range(10):
        assert ask(client, c4, post).status_code in {200, 201}
    assert ask(client, c4, post).status_code == 429
    assert ScoutAttendance.query.count() == 1


def test_chunked_size_limit_before_json_and_invalid_decision(client, c4):
    from io import BytesIO

    response = client.open(
        "/api/opportunities/search",
        method="POST",
        content_type="application/json",
        input_stream=BytesIO(b'{"lat":35,"lng":139,"padding":"' + b"x" * 5000 + b'"}'),
        environ_overrides={"CONTENT_LENGTH": "", "wsgi.input_terminated": True},
    )
    assert response.status_code == 413
    post = trial(client, c4)
    row = ask(client, c4, post).get_json()["attendance"]
    assert answer(client, c4, row, decision=[]).status_code == 422


def test_outbox_failure_rolls_back_request_and_audit(client, c4, monkeypatch):
    post = trial(client, c4)
    before = AdminActionEvent.query.count()

    def fail(**kwargs):
        raise RuntimeError("injected outbox failure")

    monkeypatch.setattr(service, "enqueue", fail)
    with pytest.raises(RuntimeError):
        service.submit(post["id"], c4["scout"], {"note": "test only", "no_approach_confirmed": True})
    db.session.rollback()
    assert ScoutAttendance.query.count() == 0
    assert AdminActionEvent.query.count() == before


def test_real_spa_dark_methods_headers_and_body_parity(client, c4, club_app, monkeypatch):
    from flask import make_response

    def serve(path=""):
        response = make_response("test only SPA fallback", 200)
        response.headers["Cache-Control"] = "test-only-baseline"
        return response

    club_app.add_url_rule("/<path:path>", "serve", serve, methods=["GET"])
    monkeypatch.setenv("SCOUT_ATTEND_ENABLED", "false")
    paths = [
        "/scout-attendance/features",
        "/opportunities/search",
        "/me/scout-attendance",
        f"/club/{c4['pid']}/today",
        f"/opportunities/{uuid4()}/attendance",
    ]
    for method in ("GET", "HEAD", "POST", "PUT", "DELETE", "OPTIONS"):
        baseline = client.open("/api/c4-test-only-unregistered", method=method)
        for path in paths:
            response = client.open("/api" + path, method=method)
            assert response.status_code == baseline.status_code
            assert response.data == baseline.data
            for header in ("Cache-Control", "Content-Type"):
                assert response.headers.get(header) == baseline.headers.get(header)
            assert set(response.headers.get("Allow", "").split(", ")) == set(
                baseline.headers.get("Allow", "").split(", ")
            )


def test_closed_event_cannot_be_accepted_but_history_remains(client, c4):
    post = trial(client, c4)
    row = ask(client, c4, post).get_json()["attendance"]
    db.session.get(ClubOpportunity, post["id"]).status = "closed"
    db.session.commit()
    assert answer(client, c4, row).status_code == 404
    assert client.get(f"/api/club/{c4['pid']}/today", headers=_headers("a")).get_json()["queues"]["attendance"] == []
    history = client.get("/api/me/scout-attendance", headers=c4["scout_headers"]).get_json()["attendance"]
    assert history[0]["id"] == row["id"]
