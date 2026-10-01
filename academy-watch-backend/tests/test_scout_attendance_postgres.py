"""Opt-in C4 disposable Postgres locks, DB uniqueness, RLS and real outbox dispatch."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from types import SimpleNamespace
from uuid import uuid4

import pytest
import sqlalchemy as sa
from flask import Flask
from src.models.funding import ClubProgram, ClubProgramClaim, ClubProgramManager, FundingLeague
from src.models.league import UserAccount, db
from src.models.opportunities import now
from src.models.p2_foundation import NotificationOutbox
from src.models.scout_attendance import ScoutAttendance
from src.models.trust import ScoutVerification
from src.services import opportunities
from src.services import scout_attendance as service
from src.services.notification_outbox import dispatch_due


@pytest.fixture
def pg(monkeypatch):
    uri = os.getenv("C4_POSTGRES_URL")
    if not uri:
        pytest.skip("C4_POSTGRES_URL opt-in")
    parsed = sa.engine.make_url(uri)
    assert parsed.database == "aw_p2_c4" and parsed.host in {"localhost", "127.0.0.1"}
    app = Flask(__name__)
    app.config.update(SQLALCHEMY_DATABASE_URI=uri, SQLALCHEMY_TRACK_MODIFICATIONS=False, SECRET_KEY="c4-test-only")
    db.init_app(app)
    for flag in [
        "SCOUT_ATTEND_ENABLED",
        "OPPORTUNITIES_ENABLED",
        "CLUB_DIRECTORY_ENABLED",
        "CLUB_STAFF_ACCESS_ENABLED",
        "P2_FOUNDATION_ENABLED",
    ]:
        monkeypatch.setenv(flag, "true")
    service.register_notifications()
    with app.app_context():
        assert db.session.execute(sa.text("SELECT current_database()")).scalar() == "aw_p2_c4"
        assert db.session.execute(
            sa.text("SELECT relrowsecurity FROM pg_class WHERE relname='scout_attendance_requests'")
        ).scalar()
        # Each dispatch probe owns the whole disposable database outbox.
        NotificationOutbox.query.filter_by(template="c4_attendance").delete()
        ScoutAttendance.query.delete()
        db.session.commit()
        suffix = uuid4().hex[:10]
        league = FundingLeague(
            name="C4 TEST ONLY " + suffix,
            country="Test",
            region="Test",
            level="recreational",
            gender_program="both",
            season_calendar="calendar_year",
            data_tier="self_reported",
            registry_status="approved",
            admission_state="open",
        )
        users = [
            UserAccount(
                email=f"c4-pg-{i}-{suffix}@example.test",
                display_name=f"C4 TEST ONLY {i} {suffix}",
                display_name_lower=f"c4 test only {i} {suffix}",
            )
            for i in range(2)
        ]
        db.session.add_all([league, *users])
        db.session.flush()
        club = ClubProgram(
            funding_league_id=league.id,
            name="C4 TEST ONLY " + suffix,
            legal_name="TEST ONLY",
            slug="c4-test-" + suffix,
            country="Test",
            region="Test",
            platform_status="approved",
        )
        db.session.add(club)
        db.session.flush()
        claim = ClubProgramClaim(
            program_id=club.id, user_account_id=users[0].id, relationship_type="club_official", status="approved"
        )
        db.session.add(claim)
        db.session.flush()
        db.session.add(
            ClubProgramManager(
                program_id=club.id,
                user_account_id=users[0].id,
                source_claim_id=claim.id,
                status="active",
                granted_by="test",
            )
        )
        db.session.add(
            ScoutVerification(
                user_account_id=users[1].id,
                full_name="C4 TEST ONLY Scout",
                organization="TEST ONLY",
                role_title="Scout",
                statement="Test only",
                status="approved",
            )
        )
        db.session.commit()
        post = opportunities.save_opportunity(
            club.id,
            users[0].id,
            {
                "type": "trial",
                "title": "C4 TEST ONLY trial",
                "description": "Synthetic test only",
                "venue": "Test venue",
                "starts_at": opportunities.iso(now() + timedelta(days=14)),
                "closes_at": opportunities.iso(now() + timedelta(days=7)),
                "status": "published",
                "birth_year_max": 2005,
            },
        )
        db.session.commit()
        ids = {"pid": club.id, "oid": post.id, "actor": users[0].id, "scout": users[1].id}
        yield app, ids
        db.session.rollback()
        db.session.remove()


def race(app, functions):
    barrier = Barrier(len(functions))

    def execute(function):
        with app.app_context():
            barrier.wait(timeout=15)
            try:
                result = function()
                db.session.commit()
                return result
            except service.Error as exc:
                db.session.rollback()
                return exc.code
            finally:
                db.session.remove()

    with ThreadPoolExecutor(max_workers=len(functions)) as pool:
        return list(pool.map(execute, functions))


def test_concurrent_duplicate_one_row_audit_and_two_intents(pg):
    app, ids = pg

    def submit():
        row, created = service.submit(ids["oid"], ids["scout"], {"note": "test only", "no_approach_confirmed": True})
        return created

    results = race(app, [submit, submit])
    assert sorted(results) == [False, True]
    assert ScoutAttendance.query.filter_by(opportunity_id=ids["oid"]).count() == 1
    row = ScoutAttendance.query.filter_by(opportunity_id=ids["oid"]).first()
    assert NotificationOutbox.query.filter_by(template="c4_attendance", entity_id=str(ids["scout"])).count() == 2
    assert row.version == 1


def test_concurrent_decisions_one_wins_and_revocation_notices_are_neutral(pg):
    app, ids = pg
    row, _ = service.submit(ids["oid"], ids["scout"], {"note": "test only", "no_approach_confirmed": True})
    db.session.commit()
    rid = row.id

    def accept():
        return service.decide(
            rid,
            ids["pid"],
            ids["actor"],
            {"decision": "accepted", "expected_version": 1, "arrival_instructions": "Test only reception"},
        ).status

    def decline():
        return service.decide(rid, ids["pid"], ids["actor"], {"decision": "declined", "expected_version": 1}).status

    result = race(app, [accept, decline])
    assert "version_conflict" in result and ("accepted" in result or "declined" in result)
    ScoutVerification.query.filter_by(user_account_id=ids["scout"]).update({"status": "revoked"})
    db.session.commit()
    service.revoke_ineligible()
    db.session.commit()
    sent = []
    dispatch_due(
        limit=100,
        send=lambda **kw: sent.append(kw) or SimpleNamespace(success=True, provider="test", message_id="test"),
    )
    assert not any("Test only reception" in str(m) for m in sent)
    intents = NotificationOutbox.query.filter_by(template="c4_attendance", entity_id=str(ids["scout"])).all()
    assert intents
    assert all(i.status == "cancelled" for i in intents if i.payload["state"] in {"pending", "accepted"})
    assert all(i.status == "sent" for i in intents if i.payload["state"] in {"declined", "revoked"})


def test_rc4_accept_vs_withdraw_race_six_rounds(pg):
    app, ids = pg
    for _ in range(6):
        row, _ = service.submit(ids["oid"], ids["scout"], {"note": "test only", "no_approach_confirmed": True})
        db.session.commit()
        rid = row.id

        def accept():
            return service.decide(
                rid,
                ids["pid"],
                ids["actor"],
                {"decision": "accepted", "expected_version": 1, "arrival_instructions": "TEST ONLY gate"},
            ).status

        def withdraw():
            return service.withdraw(rid, ids["scout"], {"expected_version": 1}).status

        result = race(app, [accept, withdraw])
        assert "version_conflict" in result and len(set(result) & {"accepted", "withdrawn"}) == 1
        db.session.expire_all()
        final = db.session.get(ScoutAttendance, rid)
        assert final.version == 2
        assert (final.status == "withdrawn") == (final.arrival_instructions == "")
        ScoutAttendance.query.filter_by(id=rid).delete()
        db.session.commit()


def test_rc4_hold_defers_without_attempt_then_lift_delivers_and_erasure(pg):
    from src.services.account import _SchemaView
    from src.services.scout_attendance_account import erase_attendance

    app, ids = pg
    row, _ = service.submit(ids["oid"], ids["scout"], {"note": "test only", "no_approach_confirmed": True})
    db.session.commit()
    service.decide(
        row.id,
        ids["pid"],
        ids["actor"],
        {"decision": "accepted", "expected_version": 1, "arrival_instructions": "TEST ONLY gate"},
    )
    db.session.commit()
    db.session.get(ClubProgram, ids["pid"]).emergency_hidden = True
    db.session.commit()
    sent = []
    dispatch_due(
        limit=500,
        send=lambda **kw: sent.append(kw) or SimpleNamespace(success=True, provider="test", message_id="test"),
    )
    db.session.expire_all()
    current = [
        i
        for i in NotificationOutbox.query.filter_by(template="c4_attendance", entity_id=str(ids["scout"]))
        if i.payload["version"] == 2
    ]
    assert len(current) == 2 and all(i.status == "retry" and i.attempts == 0 for i in current)
    assert not any("attendance" in str(m).lower() for m in sent)
    db.session.get(ClubProgram, ids["pid"]).emergency_hidden = False
    for intent in current:
        intent.next_attempt_at = now() - timedelta(seconds=1)
    db.session.commit()
    dispatch_due(
        limit=500,
        send=lambda **kw: sent.append(kw) or SimpleNamespace(success=True, provider="test", message_id="test"),
    )
    db.session.expire_all()
    assert all(db.session.get(NotificationOutbox, i.id).status == "sent" for i in current)
    assert sum("attendance" in str(m).lower() for m in sent) == 2
    assert not any("TEST ONLY gate" in str(m) for m in sent)
    assert erase_attendance(ids["actor"], _SchemaView())["scout_attendance"]["decision_actors_redacted"] == 1
    db.session.commit()
    assert db.session.get(ScoutAttendance, row.id).decision_user_id is None
    assert erase_attendance(ids["scout"], _SchemaView())["scout_attendance"]["deleted"] == 1
    db.session.commit()
    assert NotificationOutbox.query.filter_by(template="c4_attendance", entity_id=str(ids["scout"])).count() == 0


@pytest.mark.parametrize("new_request", [False, True])
def test_rc4_trust_revoke_vs_admission_no_live_untrusted_permission(pg, new_request):
    app, ids = pg
    rid = None
    if not new_request:
        row, _ = service.submit(ids["oid"], ids["scout"], {"note": "test only", "no_approach_confirmed": True})
        db.session.commit()
        rid = row.id

    def admit():
        if new_request:
            return service.submit(ids["oid"], ids["scout"], {"note": "test only", "no_approach_confirmed": True})[
                0
            ].status
        return service.decide(
            rid,
            ids["pid"],
            ids["actor"],
            {"decision": "accepted", "expected_version": 1, "arrival_instructions": "TEST ONLY gate"},
        ).status

    def revoke():
        service.revoke_user(ids["scout"])
        ScoutVerification.query.filter_by(user_account_id=ids["scout"]).one().status = "revoked"
        return "revoked"

    result = race(app, [admit, revoke])
    assert "revoked" in result
    db.session.expire_all()
    row = ScoutAttendance.query.filter_by(opportunity_id=ids["oid"]).first()
    assert row is None or (row.status == "revoked" and row.arrival_instructions == "")
    if row:
        current = [
            i
            for i in NotificationOutbox.query.filter_by(template="c4_attendance", entity_id=str(ids["scout"]))
            if i.payload["state"] == "revoked" and i.recipient_user_id == ids["actor"]
        ]
        assert current and service.eligible(current[-1], db.session.get(UserAccount, ids["actor"]))


def test_rc4_scout_index_real_pg_plan(pg):
    app, ids = pg
    definition = db.session.execute(
        sa.text("SELECT indexdef FROM pg_indexes WHERE indexname='ix_scout_attendance_scout'")
    ).scalar()
    assert "(scout_user_id, id)" in definition
    db.session.execute(sa.text("SET LOCAL enable_seqscan=off"))
    plan = (
        db.session.execute(
            sa.text("EXPLAIN SELECT id FROM scout_attendance_requests WHERE scout_user_id=:uid ORDER BY id LIMIT 31"),
            {"uid": ids["scout"]},
        )
        .scalars()
        .all()
    )
    assert "ix_scout_attendance_scout" in " ".join(plan), plan
    print("RC4 scout index plan:", " | ".join(plan))
