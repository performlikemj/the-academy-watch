"""Opt-in real locks/triggers/FKs on the lane's disposable PostgreSQL copy only."""

import importlib.util
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from flask import Flask
from src.models.funding import ClubProgram, ClubProgramClaim, ClubProgramManager, FundingLeague
from src.models.league import UserAccount, db
from src.models.opportunities import ApplicationEvent, ApplicationNote, ClubOpportunity, OpportunityApplication, now
from src.models.p2_foundation import NotificationOutbox
from src.models.showcase import LocalPlayer, PlayerProfileClaim
from src.services import opportunities as service
from src.services.account import _SchemaView, delete_account
from src.services.opportunities_account import erase_opportunities, purge_retained


@pytest.fixture
def pg(monkeypatch):
    uri = os.getenv("B2_POSTGRES_URL")
    if not uri:
        pytest.skip("B2_POSTGRES_URL opt-in")
    parsed = sa.engine.make_url(uri)
    assert parsed.database == "aw_p2_b2" and parsed.host in {"localhost", "127.0.0.1"}
    app = Flask(__name__)
    app.config.update(SQLALCHEMY_DATABASE_URI=uri, SQLALCHEMY_TRACK_MODIFICATIONS=False, SECRET_KEY="b2-test")
    db.init_app(app)
    for flag in ("OPPORTUNITIES_ENABLED", "APPLICATIONS_ENABLED", "P2_FOUNDATION_ENABLED", "CLUB_STAFF_ACCESS_ENABLED"):
        monkeypatch.setenv(flag, "true")
    service.register_notifications()
    with app.app_context():
        assert db.session.execute(sa.text("SELECT current_database()")).scalar() == "aw_p2_b2"
        assert db.session.execute(sa.text("SELECT version_num FROM alembic_version")).scalar() == "p2b2"
        suffix = uuid4().hex[:12]
        league = FundingLeague(
            name=f"B2 Test {suffix}",
            country="Test",
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
        program = ClubProgram(
            funding_league_id=league.id,
            name=f"B2 Test Club {suffix}",
            legal_name="Test only",
            slug=f"b2-test-{suffix}",
            country="Test",
            region="Test",
            platform_status="approved",
        )
        users = [
            UserAccount(
                email=f"b2-pg-{i}-{suffix}@example.test",
                display_name=f"B2 PG {i} {suffix}",
                display_name_lower=f"b2 pg {i} {suffix}",
            )
            for i in range(3)
        ]
        db.session.add_all([program, *users])
        db.session.flush()
        manager_claim = ClubProgramClaim(
            program_id=program.id, user_account_id=users[0].id, relationship_type="club_official", status="approved"
        )
        db.session.add(manager_claim)
        db.session.flush()
        db.session.add(
            ClubProgramManager(
                program_id=program.id,
                user_account_id=users[0].id,
                source_claim_id=manager_claim.id,
                status="active",
                granted_by="test",
            )
        )
        claims = []
        for i in (1, 2):
            local = LocalPlayer(
                display_name=f"B2 Test Adult {i} {suffix}",
                birth_date=date(2000, 1, 1),
                birth_year=2000,
                status="approved",
                created_by_user_id=users[i].id,
            )
            db.session.add(local)
            db.session.flush()
            local.api_player_id = -local.id
            claim = PlayerProfileClaim(
                local_player_id=local.id, user_account_id=users[i].id, relationship_type="player", status="approved"
            )
            db.session.add(claim)
            db.session.flush()
            claims.append(claim.id)
        db.session.commit()
        ids = dict(pid=program.id, actor=users[0].id, users=[u.id for u in users[1:]], claims=claims)
        row = service.save_opportunity(
            program.id,
            users[0].id,
            dict(
                type="trial",
                title=f"B2 Test Trial {suffix}",
                description="Synthetic test opportunity only",
                venue="Test venue",
                starts_at=service.iso(now() + timedelta(days=7)),
                closes_at=service.iso(now() + timedelta(days=3)),
                status="published",
                capacity=1,
            ),
        )
        db.session.commit()
        ids["oid"] = row.id
        yield app, ids
        db.session.rollback()
        db.session.remove()


def submit(ids, i=0, key=None):
    row, _ = service.submit(
        ids["oid"],
        ids["users"][i],
        dict(
            claim_id=ids["claims"][i],
            position="Midfielder",
            contact_consent=True,
            client_request_id=key or str(uuid4()),
        ),
    )
    db.session.commit()
    return row.id


def race(app, functions):
    barrier = Barrier(2)

    def run(fn):
        with app.app_context():
            barrier.wait(timeout=10)
            try:
                value = fn()
                db.session.commit()
                return value
            except service.OpportunityError as exc:
                db.session.rollback()
                return exc.code
            finally:
                db.session.remove()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run, fn) for fn in functions]
        return [f.result(timeout=30) for f in futures]


def test_concurrent_expected_version_has_one_event_and_one_winner(pg):
    app, ids = pg
    aid = submit(ids)

    def move():
        row = service.transition(ids["pid"], ids["actor"], aid, {"expected_version": 1, "status": "shortlisted"})
        return row.status

    results = race(app, [move, move])
    assert sorted(results) == ["shortlisted", "version_conflict"]
    db.session.expire_all()
    assert service.application(aid).version == 2
    assert ApplicationEvent.query.filter_by(application_id=aid).count() == 2
    assert NotificationOutbox.query.filter(NotificationOutbox.payload["application_id"].as_string() == aid).count() == 4


def test_concurrent_invites_cannot_overbook(pg):
    app, ids = pg
    aids = [submit(ids, i) for i in (0, 1)]
    for aid in aids:
        service.transition(ids["pid"], ids["actor"], aid, {"expected_version": 1, "status": "shortlisted"})
    db.session.commit()

    def invite(aid):
        def fn():
            return service.transition(
                ids["pid"],
                ids["actor"],
                aid,
                dict(
                    expected_version=2,
                    status="invited",
                    trial_at=service.iso(now() + timedelta(days=7)),
                    trial_venue="Test venue",
                ),
            ).status

        return fn

    assert sorted(race(app, [invite(a) for a in aids])) == ["invited", "trial_full"]
    db.session.expire_all()
    assert service.reservations(ids["oid"]) == 1


def test_concurrent_submit_idempotency_dedupes_events_and_outbox(pg):
    app, ids = pg
    key = str(uuid4())

    def apply():
        row, created = service.submit(
            ids["oid"],
            ids["users"][0],
            dict(claim_id=ids["claims"][0], position="Midfielder", contact_consent=True, client_request_id=key),
        )
        return created

    assert sorted(race(app, [apply, apply])) == [False, True]
    db.session.expire_all()
    assert OpportunityApplication.query.filter_by(opportunity_id=ids["oid"]).count() == 1
    aid = OpportunityApplication.query.filter_by(opportunity_id=ids["oid"]).one().id
    assert ApplicationEvent.query.filter_by(application_id=aid).count() == 1
    assert NotificationOutbox.query.filter(NotificationOutbox.payload["application_id"].as_string() == aid).count() == 2


def test_event_guard_and_account_privacy_exception(pg):
    _, ids = pg
    aid = submit(ids)
    for sql in (
        "UPDATE application_events SET reason_code='changed' WHERE application_id=:id",
        "DELETE FROM application_events WHERE application_id=:id",
        "TRUNCATE application_events",
    ):
        with pytest.raises(sa.exc.DBAPIError, match="append-only"):
            with db.session.begin_nested():
                db.session.execute(sa.text(sql), {"id": aid})
    service.add_note(ids["pid"], ids["actor"], aid, {"body": "Synthetic private note"})
    db.session.commit()
    counts = erase_opportunities(ids["actor"], _SchemaView())
    db.session.commit()
    assert counts["recruiting"]["authored_notes"] == 1
    assert ApplicationEvent.query.filter_by(application_id=aid).one().actor_user_id == ids["users"][0]
    counts = erase_opportunities(ids["users"][0], _SchemaView())
    db.session.commit()
    assert counts["recruiting"]["applications"] == 1
    assert ApplicationEvent.query.filter_by(application_id=aid).count() == 0


def test_retention_erases_notes_events_intents_even_dark(pg, monkeypatch):
    _, ids = pg
    aid = submit(ids)
    service.add_note(ids["pid"], ids["actor"], aid, {"body": "Synthetic private note"})
    service.application(aid).retention_expires_at = now() - timedelta(days=1)
    db.session.commit()
    monkeypatch.setenv("OPPORTUNITIES_ENABLED", "false")
    counts = purge_retained()
    db.session.commit()
    assert counts["applications"] >= 1
    assert db.session.get(OpportunityApplication, aid) is None
    assert ApplicationEvent.query.filter_by(application_id=aid).count() == 0
    assert ApplicationNote.query.filter_by(application_id=aid).count() == 0
    assert NotificationOutbox.query.filter(NotificationOutbox.payload["application_id"].as_string() == aid).count() == 0


def test_real_account_delete_all_application_fks(pg):
    _, ids = pg
    aid = submit(ids)
    service.transition(ids["pid"], ids["actor"], aid, {"expected_version": 1, "status": "shortlisted"})
    db.session.commit()
    delete_account(db.session.get(UserAccount, ids["users"][0]))
    assert db.session.get(OpportunityApplication, aid) is None
    assert ApplicationEvent.query.filter_by(application_id=aid).count() == 0


def test_rls_guarded_reapply_and_downgrade_refuses_retained_data(pg, monkeypatch):
    _, ids = pg
    tables = ("club_opportunities", "opportunity_applications", "application_events", "application_notes")
    for table in tables:
        assert (
            db.session.execute(
                sa.text("SELECT relrowsecurity FROM pg_class WHERE oid=CAST(:table AS regclass)"), {"table": table}
            ).scalar()
            is True
        )
    path = Path(__file__).parents[1] / "migrations/versions/p2b2_opportunities.py"
    spec = importlib.util.spec_from_file_location("p2b2_test", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with Operations.context(MigrationContext.configure(db.session.connection())):
        migration.upgrade()
        migration.upgrade()
        with pytest.raises(RuntimeError, match="refusing to downgrade"):
            migration.downgrade()
    db.session.commit()
    assert db.session.get(ClubOpportunity, ids["oid"])
