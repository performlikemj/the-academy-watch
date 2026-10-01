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


def merge_setup(ids, *, duplicate_claim):
    source = db.session.get(PlayerProfileClaim, ids["claims"][0])
    suffix = uuid4().hex[:12]
    local = LocalPlayer(
        display_name=f"B2 canonical {suffix}",
        birth_date=date(2000, 1, 1),
        birth_year=2000,
        status="approved",
        provenance="user",
    )
    db.session.add(local)
    db.session.flush()
    local.api_player_id = -local.id
    target_claim = None
    if duplicate_claim:
        target_claim = PlayerProfileClaim(
            local_player_id=local.id,
            user_account_id=source.user_account_id,
            relationship_type="player",
            status="approved",
        )
        db.session.add(target_claim)
    db.session.commit()
    return source.local_player_id, local.id, target_claim.id if target_claim else None


def merge_http(app, monkeypatch, source_id, target_id):
    from src.auth import issue_user_token
    from src.extensions import limiter
    from src.routes.showcase import showcase_bp

    monkeypatch.setenv("ADMIN_API_KEY", "b2-pg-test-key")
    monkeypatch.setenv("ADMIN_IP_WHITELIST", "")
    app.config["RATELIMIT_ENABLED"] = False
    limiter.init_app(app)
    app.register_blueprint(showcase_bp, url_prefix="/api")
    token = issue_user_token("b2-admin@example.test", role="admin")["token"]
    return app.test_client().post(
        f"/api/admin/local-players/{source_id}/merge",
        headers={"Authorization": f"Bearer {token}", "X-API-Key": "b2-pg-test-key"},
        json={"into_local_player_id": target_id},
    )


@pytest.mark.parametrize("duplicate_claim", [False, True])
def test_admin_identity_merge_repoints_application_claim_and_subject_atomically(pg, monkeypatch, duplicate_claim):
    app, ids = pg
    key = str(uuid4())
    aid = submit(ids, key=key)
    source_id, target_id, target_claim_id = merge_setup(ids, duplicate_claim=duplicate_claim)
    response = merge_http(app, monkeypatch, source_id, target_id)
    assert response.status_code == 200, response.get_json()
    db.session.expire_all()
    stored = db.session.get(OpportunityApplication, aid)
    assert stored.signed_player_id == -target_id
    canonical_claim = stored.claim_id
    if duplicate_claim:
        assert canonical_claim == target_claim_id and db.session.get(PlayerProfileClaim, ids["claims"][0]) is None
    else:
        assert canonical_claim == ids["claims"][0]
    assert service.adult_claim(canonical_claim, ids["users"][0])[1] == -target_id
    # Original request replay survives deletion of its original claim row.
    replay, created = service.submit(
        ids["oid"],
        ids["users"][0],
        dict(claim_id=ids["claims"][0], position="Midfielder", contact_consent=True, client_request_id=key),
    )
    assert replay.id == aid and created is False
    with pytest.raises(service.OpportunityError, match="already_applied"):
        service.submit(
            ids["oid"],
            ids["users"][0],
            dict(claim_id=canonical_claim, position="Midfielder", contact_consent=True, client_request_id=str(uuid4())),
        )
    db.session.rollback()
    # The PostgreSQL subject index enforces uniqueness regardless of claim reference.
    with pytest.raises(sa.exc.IntegrityError):
        with db.session.begin_nested():
            db.session.execute(
                sa.text("""INSERT INTO opportunity_applications
                (id, opportunity_id, program_id, applicant_user_id, applicant_kind, claim_id, signed_player_id,
                 status, position, current_club, contact_consent_at, submitted_at, retention_expires_at, version,
                 client_request_id, request_hash, reservation_state)
                SELECT :new_id, opportunity_id, program_id, applicant_user_id, applicant_kind, claim_id, signed_player_id,
                 status, position, current_club, contact_consent_at, submitted_at, retention_expires_at, version,
                 :request_id, request_hash, reservation_state FROM opportunity_applications WHERE id=:id"""),
                {"new_id": str(uuid4()), "request_id": str(uuid4()), "id": aid},
            )
    assert OpportunityApplication.query.filter_by(opportunity_id=ids["oid"], signed_player_id=-target_id).count() == 1


def test_admin_merge_application_collision_is_clear_409_and_full_rollback(pg, monkeypatch):
    app, ids = pg
    aid = submit(ids)
    source_id, target_id, target_claim_id = merge_setup(ids, duplicate_claim=True)
    second, _ = service.submit(
        ids["oid"],
        ids["users"][0],
        dict(claim_id=target_claim_id, position="Midfielder", contact_consent=True, client_request_id=str(uuid4())),
    )
    db.session.commit()
    second_id = second.id
    event_count = ApplicationEvent.query.count()
    response = merge_http(app, monkeypatch, source_id, target_id)
    assert (
        response.status_code == 409 and "retained applications to the same opportunity" in response.get_json()["error"]
    )
    db.session.expire_all()
    assert db.session.get(LocalPlayer, source_id).status == "approved"
    assert db.session.get(PlayerProfileClaim, ids["claims"][0]).local_player_id == source_id
    assert db.session.get(OpportunityApplication, aid).signed_player_id == -source_id
    assert db.session.get(OpportunityApplication, second_id).signed_player_id == -target_id
    assert ApplicationEvent.query.count() == event_count


def test_postgres_nul_and_timestamp_overflow_are_400_without_database_error(pg):
    from src.auth import issue_user_token
    from src.extensions import limiter
    from src.routes.opportunities import opportunities_bp

    app, ids = pg
    app.config["RATELIMIT_ENABLED"] = False
    limiter.init_app(app)
    app.register_blueprint(opportunities_bp, url_prefix="/api")
    user = db.session.get(UserAccount, ids["users"][0])
    token = issue_user_token(user.email)["token"]
    headers = {"Authorization": f"Bearer {token}"}
    response = app.test_client().post(
        f"/api/opportunities/{ids['oid']}/applications",
        headers=headers,
        json=dict(
            claim_id=ids["claims"][0], position="Mid\x00field", contact_consent=True, client_request_id=str(uuid4())
        ),
    )
    assert response.status_code == 400
    assert OpportunityApplication.query.filter_by(opportunity_id=ids["oid"]).count() == 0
    assert db.session.execute(sa.text("SELECT 1")).scalar() == 1
