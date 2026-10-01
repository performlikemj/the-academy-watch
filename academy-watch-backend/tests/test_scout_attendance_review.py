# ruff: noqa: F811
"""RC4 probes reversed into assertions: lifecycle, trust, bounded reads and JSON."""

from datetime import timedelta
from uuid import uuid4

import pytest
import sqlalchemy as sa
from src.models.league import UserAccount, db
from src.models.opportunities import ClubOpportunity, OpportunityApplication, now
from src.models.p2_foundation import AdminActionEvent, NotificationOutbox
from src.models.scout_attendance import ScoutAttendance
from src.models.trust import ScoutVerification
from src.models.video import VideoMatch
from src.services import scout_attendance as service
from src.services.account import _SchemaView
from src.services.scout_attendance_account import export_attendance
from test_club_console import _headers, client, club_app  # noqa: F401
from test_opportunities import apply, env  # noqa: F401
from test_scout_attendance import answer, ask, c4, trial  # noqa: F401


def today(client, c4):
    response = client.get(f"/api/club/{c4['pid']}/today", headers=_headers("a"))
    assert response.status_code == 200, response.get_json()
    return response.get_json()


@pytest.mark.parametrize("closed", [False, True])
@pytest.mark.parametrize("decision", ["accepted", "declined"])
def test_m1_deadline_passed_future_session_still_decidable(client, c4, closed, decision):
    post = trial(client, c4)
    row = ask(client, c4, post).get_json()["attendance"]
    opp = db.session.get(ClubOpportunity, post["id"])
    opp.closes_at = now() - timedelta(minutes=1)
    if closed:
        opp.status = "closed"
    db.session.commit()
    assert today(client, c4)["queues"]["attendance"][0]["id"] == row["id"]
    assert answer(client, c4, row, decision=decision).status_code == 200
    assert ScoutAttendance.query.one().status == decision


@pytest.mark.parametrize("read", ["today", "mine", "decision", "job"])
def test_m1_started_session_expires_pending_and_notifies_once(client, c4, read):
    post = trial(client, c4)
    row = ask(client, c4, post).get_json()["attendance"]
    db.session.get(ClubOpportunity, post["id"]).starts_at = now() - timedelta(seconds=1)
    db.session.commit()
    if read == "today":
        assert today(client, c4)["queues"]["attendance"] == []
    elif read == "mine":
        history = client.get("/api/me/scout-attendance", headers=c4["scout_headers"]).get_json()["attendance"]
        assert history[0]["status"] == "expired"
    elif read == "decision":
        assert answer(client, c4, row).status_code == 409
    else:
        assert service.expire_pending() == 1
        db.session.commit()
    stored = db.session.get(ScoutAttendance, row["id"])
    assert (stored.status, stored.version, stored.arrival_instructions) == ("expired", 2, "")
    notices = NotificationOutbox.query.filter_by(template="c4_attendance").all()
    current = [i for i in notices if i.payload["state"] == "expired"]
    assert len(current) == 2
    user = db.session.get(UserAccount, c4["scout"])
    assert service.eligible(next(i for i in current if i.recipient_user_id == user.id), user)
    assert "expired" in service.render(current[0], user)["text"]
    assert service.expire_pending() == 0


@pytest.mark.parametrize("youth", [False, True])
def test_m2_accepted_visible_and_rescind_is_versioned_audited_notified(client, c4, youth):
    post = trial(client, c4)
    if youth:
        db.session.get(ClubOpportunity, post["id"]).birth_year_max = now().year - 16
        db.session.commit()
    row = ask(client, c4, post).get_json()["attendance"]
    accepted = answer(client, c4, row).get_json()["attendance"]
    queues = today(client, c4)["queues"]
    assert queues["attendance"] == []
    accepted_row = queues["accepted_attendance"][0]
    assert accepted_row["opportunity_id"] == post["id"]
    assert accepted_row["scout"] == {"name": "Test Scout", "organization": "Test organization", "verified": True}
    assert answer(client, c4, row, decision="declined").status_code == 409
    rescinded = answer(client, c4, accepted, decision="declined")
    assert rescinded.status_code == 200
    assert rescinded.get_json()["attendance"]["status"] == "declined"
    assert "arrival_instructions" not in rescinded.get_json()["attendance"]
    assert ScoutAttendance.query.one().arrival_instructions == ""
    assert today(client, c4)["queues"]["accepted_attendance"] == []
    assert AdminActionEvent.query.filter_by(action="scout_attendance_declined").count() == 1
    intents = [
        i for i in NotificationOutbox.query.filter_by(template="c4_attendance") if i.payload["state"] == "declined"
    ]
    assert len(intents) == 2
    assert "withdrawn by the club" in service.render(intents[0], db.session.get(UserAccount, c4["scout"]))["text"]


@pytest.mark.parametrize("state", ["pending", "accepted"])
@pytest.mark.parametrize("loss", ["verification", "suspension"])
def test_m2_trust_loss_atomically_revokes_and_tells_club(client, c4, state, loss, monkeypatch):
    post = trial(client, c4)
    row = ask(client, c4, post).get_json()["attendance"]
    if state == "accepted":
        assert answer(client, c4, row).status_code == 200
    # Safety/erasure survives rollout rollback. Templates still gate actual delivery.
    monkeypatch.setenv("SCOUT_ATTEND_ENABLED", "false")
    if loss == "verification":
        ScoutVerification.query.filter_by(user_account_id=c4["scout"]).one().status = "revoked"
    else:
        db.session.get(UserAccount, c4["scout"]).account_status = "suspended"
    db.session.commit()
    stored = db.session.get(ScoutAttendance, row["id"])
    assert stored.status == "revoked" and stored.arrival_instructions == ""
    assert stored.version == (3 if state == "accepted" else 2)
    notices = [
        i for i in NotificationOutbox.query.filter_by(template="c4_attendance") if i.payload["state"] == "revoked"
    ]
    assert len(notices) == 2
    club_intent = next(i for i in notices if i.recipient_user_id == c4["actor"])
    monkeypatch.setenv("SCOUT_ATTEND_ENABLED", "true")
    actor = db.session.get(UserAccount, c4["actor"])
    assert service.eligible(club_intent, actor)
    assert "no longer valid" in service.render(club_intent, actor)["text"]
    assert today(client, c4)["queues"]["accepted_attendance"] == []
    assert (
        "arrival_instructions"
        not in export_attendance(db.session.get(UserAccount, c4["scout"]), _SchemaView())["scout_attendance"][0]
    )


@pytest.mark.parametrize("state", ["closed", "cancelled"])
def test_l1_session_lifecycle_notifies_accepted_scout(client, c4, state):
    post = trial(client, c4)
    row = ask(client, c4, post).get_json()["attendance"]
    assert answer(client, c4, row).status_code == 200
    response = client.post(
        f"/api/club/{c4['pid']}/opportunities/{post['id']}/close",
        headers=_headers("a"),
        json={"expected_version": post["version"], "status": state},
    )
    assert response.status_code == 200, response.get_json()
    stored = ScoutAttendance.query.one()
    assert (stored.status, stored.version) == ("cancelled" if state == "cancelled" else "accepted", 3)
    history = client.get("/api/me/scout-attendance", headers=c4["scout_headers"]).get_json()["attendance"]
    assert history[0]["status"] == stored.status
    if state == "cancelled":
        assert stored.arrival_instructions == "" and "arrival_instructions" not in history[0]
    notices = [i for i in NotificationOutbox.query.filter_by(template="c4_attendance") if i.payload["version"] == 3]
    assert len(notices) == 2
    user = db.session.get(UserAccount, c4["scout"])
    intent = next(i for i in notices if i.recipient_user_id == user.id)
    assert service.eligible(intent, user)
    assert state in service.render(intent, user)["text"]


@pytest.mark.parametrize("body", [b"[" * 2000 + b"]" * 2000, b'{"q":', b"[]", b"null", b"", b"\xff"])
def test_l2_anonymous_deep_invalid_json_is_400(client, c4, body):
    response = client.post("/api/opportunities/search", data=body, content_type="application/json")
    assert response.status_code == 400
    assert response.get_json() == {"error": "invalid_payload"}


def test_l6_withdrawn_can_request_again_once_and_identical_retries_dedupe(client, c4):
    post = trial(client, c4)
    row = ask(client, c4, post).get_json()["attendance"]

    def withdraw(row):
        response = client.post(
            f"/api/me/scout-attendance/{row['id']}/withdraw",
            headers=c4["scout_headers"],
            json={"expected_version": row["version"]},
        )
        assert response.status_code == 200
        return response.get_json()["attendance"]

    first = withdraw(row)
    assert first["can_request_again"] is True
    retry = ask(client, c4, post, note="Changed my mind, please")
    assert retry.status_code == 200
    row = retry.get_json()["attendance"]
    assert (row["status"], row["version"]) == ("pending", 3)
    assert ask(client, c4, post, note="Changed my mind, please").get_json()["attendance"] == row
    assert withdraw(row)["can_request_again"] is False
    assert ask(client, c4, post).get_json()["error"] == "request_retry_used"
    assert ScoutAttendance.query.count() == 1 and ScoutAttendance.query.one().request_count == 2


@pytest.mark.parametrize("loss", ["verification", "suspension"])
def test_l7_export_fresh_trust_even_after_sql_bulk_moderation(client, c4, loss):
    post = trial(client, c4)
    row = ask(client, c4, post).get_json()["attendance"]
    assert answer(client, c4, row).status_code == 200
    if loss == "verification":
        ScoutVerification.query.filter_by(user_account_id=c4["scout"]).update({"status": "revoked"})
    else:
        UserAccount.query.filter_by(id=c4["scout"]).update({"account_status": "suspended"})
    db.session.commit()
    user = db.session.get(UserAccount, c4["scout"], populate_existing=True)
    assert "arrival_instructions" not in export_attendance(user, _SchemaView())["scout_attendance"][0]
    assert service.revoke_ineligible() == 1
    db.session.commit()
    assert ScoutAttendance.query.one().status == "revoked"


def seed_requests(c4, post, count, *, state="pending"):
    for i in range(count):
        user = UserAccount(
            email=f"rc4-s{i}@example.test", display_name=f"TEST ONLY {i}", display_name_lower=f"test only {i}"
        )
        db.session.add(user)
        db.session.flush()
        db.session.add(
            ScoutVerification(
                user_account_id=user.id,
                full_name=f"TEST ONLY {i}",
                organization="TEST ONLY",
                role_title="Scout",
                statement="Test only",
                status="approved",
            )
        )
        db.session.add(
            ScoutAttendance(
                opportunity_id=post["id"],
                program_id=c4["pid"],
                scout_user_id=user.id,
                status=state,
                retention_expires_at=now() + timedelta(days=90),
            )
        )
    db.session.commit()


def test_l4_today_50_pending_constant_queries_and_limit_before_materialization(client, c4):
    post = trial(client, c4)
    seed_requests(c4, post, 50)
    headers = _headers("a")

    def measured():
        statements = []

        def before(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        sa.event.listen(db.engine, "before_cursor_execute", before)
        try:
            response = client.get(f"/api/club/{c4['pid']}/today", headers=headers)
        finally:
            sa.event.remove(db.engine, "before_cursor_execute", before)
        assert response.status_code == 200
        return response.get_json(), statements

    many, statements = measured()
    assert len(many["queues"]["attendance"]) == 30 and many["attendance_has_more"] is True
    assert len(statements) <= 24, statements
    print(f"RC4 Today 50 pending: {len(statements)} SQL statements")
    for row in ScoutAttendance.query.order_by(ScoutAttendance.id).offset(1).all():
        db.session.delete(row)
    db.session.commit()
    one, smaller = measured()
    assert len(one["queues"]["attendance"]) == 1
    assert len(smaller) == len(statements)
    print(f"RC4 Today 1 pending: {len(smaller)} SQL statements")


def test_m2_accepted_pagination_and_unauthorized_metadata_omitted(client, c4):
    post = trial(client, c4)
    seed_requests(c4, post, 50, state="accepted")
    data = today(client, c4)
    assert len(data["queues"]["accepted_attendance"]) == 30
    more = client.get(
        f"/api/club/{c4['pid']}/today?accepted_after={data['accepted_next_cursor']}", headers=_headers("a")
    ).get_json()
    assert len(more["queues"]["accepted_attendance"]) == 20 and more["accepted_next_cursor"] is None
    assert len({r["id"] for r in data["queues"]["accepted_attendance"] + more["queues"]["accepted_attendance"]}) == 50


def test_l4_application_and_match_backlogs_are_capped(client, c4):
    post = trial(client, c4)
    original = apply(client, c4, post).get_json()["application"]
    source = db.session.get(OpportunityApplication, original["id"])
    for i in range(110):
        values = {c.name: getattr(source, c.name) for c in source.__table__.columns if c.name != "id"}
        values.update(client_request_id=str(uuid4()), signed_player_id=90000 + i)
        db.session.add(OpportunityApplication(**values))
        db.session.add(VideoMatch(club_program_id=c4["pid"], status="uploaded", opponent_name=f"TEST ONLY {i}"))
    db.session.commit()
    data = today(client, c4)
    assert data["applications_partial"] is True
    assert sum(p["total"] for p in data["queues"]["applications"]) <= 100
    assert len(data["queues"]["team_sheet"]) == 30 and data["matches_has_more"] is True


def test_l5_model_has_scout_leading_index(c4):
    indexes = sa.inspect(db.engine).get_indexes("scout_attendance_requests")
    assert next(i for i in indexes if i["name"] == "ix_scout_attendance_scout")["column_names"] == [
        "scout_user_id",
        "id",
    ]
