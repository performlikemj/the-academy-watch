"""Opt-in retained consent and real row-lock races on C1's disposable database."""

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
from src.models.club_player_publication import ClubPlayerPublication as Publication
from src.models.funding import ClubProgram, ClubProgramClaim, ClubProgramManager, ClubRosterMember, FundingLeague
from src.models.league import UserAccount, db
from src.models.showcase import LocalPlayer
from src.services import club_player_publication as service
from src.services.public_adult import public_adult_ids


@pytest.fixture
def pg(monkeypatch):
    uri = os.getenv("C1_POSTGRES_URL")
    if not uri:
        pytest.skip("C1_POSTGRES_URL opt-in")
    parsed = sa.engine.make_url(uri)
    assert parsed.database == "aw_p2_c1" and parsed.host in {"localhost", "127.0.0.1"}
    app = Flask(__name__)
    app.config.update(SQLALCHEMY_DATABASE_URI=uri, SQLALCHEMY_TRACK_MODIFICATIONS=False, SECRET_KEY="c1-test")
    db.init_app(app)
    monkeypatch.setenv("CLUB_PLAYER_PUBLICATION_ENABLED", "true")
    suffix = uuid4().hex[:12]
    with app.app_context():
        assert db.session.execute(sa.text("SELECT current_database()")).scalar() == "aw_p2_c1"
        assert db.session.execute(sa.text("SELECT version_num FROM alembic_version")).scalar() == "p2c1"
        league = FundingLeague(
            name=f"C1 Test {suffix}",
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
            name=f"C1 Test {suffix}",
            legal_name="Test only",
            slug=f"c1-test-{suffix}",
            country="Test",
            region="Test",
            platform_status="approved",
        )
        owner = UserAccount(
            email=f"c1-owner-{suffix}@example.test",
            display_name=f"C1 Owner {suffix}",
            display_name_lower=f"c1 owner {suffix}",
        )
        adult = UserAccount(
            email=f"c1-adult-{suffix}@example.test",
            display_name=f"C1 Adult {suffix}",
            display_name_lower=f"c1 adult {suffix}",
        )
        db.session.add_all([program, owner, adult])
        db.session.flush()
        manager_claim = ClubProgramClaim(
            program_id=program.id, user_account_id=owner.id, relationship_type="club_official", status="approved"
        )
        db.session.add(manager_claim)
        db.session.flush()
        db.session.add(
            ClubProgramManager(
                program_id=program.id,
                user_account_id=owner.id,
                source_claim_id=manager_claim.id,
                status="active",
                granted_by="test",
            )
        )
        local = LocalPlayer(
            display_name=f"C1 Test Adult {suffix}",
            provenance="club",
            origin_program_id=program.id,
            birth_date=date(2000, 1, 1),
            birth_year=2000,
            status="pending",
        )
        db.session.add(local)
        db.session.flush()
        local.api_player_id = -local.id
        db.session.add(ClubRosterMember(program_id=program.id, local_player_id=local.id, added_by_user_id=owner.id))
        db.session.commit()
        ids = dict(program=program.id, local=local.id, owner=owner.id, adult=adult.id, email=adult.email)
        yield app, ids
        db.session.rollback()
        db.session.remove()


def make_invite(ids):
    row, token = service.invite(ids["program"], ids["local"], ids["owner"], {"recipient_email": ids["email"]})
    db.session.commit()
    return row.id, token


def make_consented(ids):
    row_id, token = make_invite(ids)
    user = db.session.get(UserAccount, ids["adult"])
    row = service.redeem(user, {"token": token, "self_claim": True})
    service.consent(
        row,
        user.id,
        {"expected_version": row.version, "public_profile_consent": True, "consent_version": service.CONSENT_VERSION},
    )
    db.session.commit()
    return row_id


def race(app, work):
    barrier = Barrier(2)

    def run(index):
        with app.app_context():
            barrier.wait(timeout=10)
            try:
                result = work(index)
                db.session.commit()
                return result
            except service.PublicationError as exc:
                db.session.rollback()
                return exc.code
            finally:
                db.session.remove()

    with ThreadPoolExecutor(max_workers=2) as pool:
        return list(pool.map(run, [0, 1]))


def test_postgres_single_use_claim(pg):
    app, ids = pg
    row_id, token = make_invite(ids)

    def work(index):
        user = db.session.get(UserAccount, ids["adult"])
        service.redeem(user, {"token": token, "self_claim": True})
        return "claimed"

    assert sorted(race(app, work)) == ["claimed", "invite_unavailable"]
    db.session.expire_all()
    assert db.session.get(Publication, row_id).claimed_at


def test_postgres_review_vs_withdraw_one_version_wins(pg):
    app, ids = pg
    row_id = make_consented(ids)
    version = db.session.get(Publication, row_id).version

    def work(index):
        row = Publication.query.filter_by(id=row_id).populate_existing().with_for_update().one()
        if index:
            service.expect_version(row, {"expected_version": version})
            service.revoke(row)
            return "changed"
        service.review(
            row,
            "c1-test-reviewer",
            {"expected_version": version, "action": "approve", "reason": "Synthetic adult fixture review"},
        )
        return "changed"

    assert sorted(race(app, work)) == ["changed", "version_conflict"]
    db.session.expire_all()
    row = db.session.get(Publication, row_id)
    if not row.withdrawn_at:
        service.revoke(row)
        db.session.commit()
    assert not public_adult_ids([-ids["local"]])


def test_postgres_migration_reapply_rls_and_retention_guard(pg):
    app, ids = pg
    make_invite(ids)
    path = Path(__file__).parents[1] / "migrations/versions/p2c1_club_player_publication.py"
    spec = importlib.util.spec_from_file_location("c1_migration_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    db.session.commit()
    with db.engine.begin() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            module.upgrade()
            module.upgrade()
            with pytest.raises(RuntimeError, match="retained publication consent"):
                module.downgrade()
        assert (
            connection.execute(
                sa.text("SELECT relrowsecurity FROM pg_class WHERE oid='public.club_player_publications'::regclass")
            ).scalar()
            is True
        )
        assert (
            connection.execute(
                sa.text(
                    "SELECT column_default FROM information_schema.columns WHERE table_name='contact_requests' AND column_name='club_first'"
                )
            ).scalar()
            == "false"
        )
        assert (
            connection.execute(
                sa.text(
                    "SELECT is_nullable FROM information_schema.columns WHERE table_name='club_player_publications' AND column_name='recipient_email'"
                )
            ).scalar()
            == "YES"
        )
        assert (
            connection.execute(sa.text("SELECT indexdef FROM pg_indexes WHERE indexname='ix_publication_local_player'"))
            .scalar()
            .endswith("(local_player_id)")
        )


def test_postgres_erasure_clears_publication_claim_foreign_key(pg):
    from src.models.contact import ContactAuditEvent, ContactRequest
    from src.services.account import delete_account

    app, ids = pg
    row_id = make_consented(ids)
    row = Publication.query.filter_by(id=row_id).with_for_update().one()
    service.review(
        row,
        "c1-test-reviewer",
        {"expected_version": row.version, "action": "approve", "reason": "Synthetic adult fixture review"},
    )
    db.session.commit()
    assert public_adult_ids([-ids["local"]])
    request = ContactRequest(
        scout_user_id=ids["owner"],
        player_api_id=-ids["local"],
        claim_id=row.claim_id,
        club_first=True,
        routing_mode="club_included",
        club_program_id=ids["program"],
        club_consent_status="pending",
        message="Withheld PostgreSQL erasure fixture",
        expires_at=service.now() + timedelta(days=7),
    )
    db.session.add(request)
    db.session.flush()
    request_id = request.id
    db.session.add(ContactAuditEvent(contact_request_id=request.id, actor_user_id=ids["owner"], event_type="created"))
    db.session.commit()
    user = db.session.get(UserAccount, ids["adult"])
    delete_account(user)
    db.session.commit()
    assert db.session.get(Publication, row_id) is None
    assert db.session.get(UserAccount, ids["adult"]) is None
    assert not public_adult_ids([-ids["local"]])
    assert ContactRequest.query.filter_by(id=request_id).count() == 0
    assert ContactAuditEvent.query.filter_by(contact_request_id=request_id).count() == 0


def test_postgres_invite_email_privacy_retains_evidence_while_dark(pg, monkeypatch):
    from src.services.club_player_publication_account import purge_invited_emails

    app, ids = pg
    id_, token = make_invite(ids)
    row = db.session.get(Publication, id_)
    row.invite_expires_at = service.now() - timedelta(seconds=1)
    db.session.commit()
    monkeypatch.setenv("CLUB_PLAYER_PUBLICATION_ENABLED", "false")
    assert purge_invited_emails(limit=1)["invited_emails_purged"] == 1
    db.session.commit()
    db.session.expire_all()
    row = db.session.get(Publication, id_)
    assert row.recipient_email is row.invite_token_hash is row.invite_expires_at is None
    assert row.adult_invited_at and row.association_confirmed_at and row.creator_user_id == ids["owner"]


def test_postgres_recovery_keeps_retired_claim_and_creates_fresh_keys(pg):
    from src.models.showcase import PlayerProfileClaim

    app, ids = pg
    id_ = make_consented(ids)
    row = db.session.get(Publication, id_)
    service.review(
        row,
        "c1-test-reviewer",
        {"expected_version": row.version, "action": "approve", "reason": "Original independent review"},
    )
    old_id = row.claim_id
    service.revoke(row, club=True)
    db.session.commit()
    row, token = service.invite(
        ids["program"], ids["local"], ids["owner"], {"recipient_email": ids["email"], "expected_version": row.version}
    )
    db.session.commit()
    assert row.claim_id is None and row.consented_at is None
    user = db.session.get(UserAccount, ids["adult"])
    service.redeem(user, {"token": token, "self_claim": True})
    db.session.commit()
    assert row.claim_id != old_id
    old = db.session.get(PlayerProfileClaim, old_id)
    assert old.local_player_id == ids["local"] and old.status == "revoked"
    assert old.verification_method == "club_vouch_retired"
    assert not public_adult_ids([-ids["local"]])
    service.consent(
        row,
        user.id,
        {"expected_version": row.version, "public_profile_consent": True, "consent_version": service.CONSENT_VERSION},
    )
    service.review(
        row,
        "c1-test-reviewer",
        {"expected_version": row.version, "action": "approve", "reason": "Fresh independent review"},
    )
    db.session.commit()
    assert public_adult_ids([-ids["local"]])
    assert PlayerProfileClaim.query.filter_by(local_player_id=ids["local"], user_account_id=ids["adult"]).count() == 2
    # The relaxation applies only to C1 retired evidence; another active claim still conflicts.
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError), db.session.begin_nested():
        db.session.add(
            PlayerProfileClaim(
                local_player_id=ids["local"], user_account_id=ids["adult"], relationship_type="player", status="pending"
            )
        )
        db.session.flush()


def test_postgres_recovery_version_race(pg):
    app, ids = pg
    id_ = make_consented(ids)
    row = db.session.get(Publication, id_)
    service.revoke(row, club=True)
    db.session.commit()
    version = row.version

    def work(index):
        service.invite(
            ids["program"], ids["local"], ids["owner"], {"recipient_email": ids["email"], "expected_version": version}
        )
        return "invited"

    assert sorted(race(app, work)) == ["invited", "version_conflict"]


@pytest.mark.parametrize("entry", ["preapply", "migration"])
def test_postgres_ddl_timeout_rolls_back_then_retries(pg, entry):
    import time

    import psycopg

    app, _ids = pg
    uri = sa.engine.make_url(os.environ["C1_POSTGRES_URL"])
    arguments = dict(dbname=uri.database, host=uri.host, user=uri.username, port=uri.port or 5432)
    script = (Path(__file__).parents[1] / "migrations/maintenance/p2c1_preapply.sql").read_text()
    connections = [psycopg.connect(**arguments) for _ in range(3)]
    blocker, ddl, reader = connections
    db.session.commit()
    with blocker.cursor() as cursor:
        cursor.execute("SELECT 1 FROM club_player_publications LIMIT 1")

    def run_ddl():
        began = time.monotonic()
        try:
            if entry == "preapply":
                with ddl.cursor() as cursor:
                    cursor.execute(script)
            else:
                path = Path(__file__).parents[1] / "migrations/versions/p2c1_club_player_publication.py"
                spec = importlib.util.spec_from_file_location("c1_timeout_migration", path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                engine = sa.create_engine(os.environ["C1_POSTGRES_URL"])
                try:
                    with engine.begin() as connection:
                        with Operations.context(MigrationContext.configure(connection)):
                            module.upgrade()
                finally:
                    engine.dispose()
            return None, time.monotonic() - began
        except Exception as error:
            return getattr(getattr(error, "orig", error), "sqlstate", None), time.monotonic() - began
        finally:
            ddl.rollback()

    def later_read():
        with reader.cursor() as cursor:
            cursor.execute("SET LOCAL statement_timeout='10s'")
            cursor.execute("SELECT 1 FROM club_player_publications LIMIT 1")
            return cursor.fetchall()

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            future = pool.submit(run_ddl)
            time.sleep(1)
            read = pool.submit(later_read)
            time.sleep(0.2)
            assert not future.done() and not read.done()
            state, elapsed = future.result(timeout=10)
            assert state == "55P03", (state, elapsed)
            assert 4.5 <= elapsed < 8, elapsed
            assert read.result(timeout=5)
        # The original reader remains open: the later reader resumes solely
        # because the failed DDL transaction rolled back.
        blocker.rollback()
        reader.rollback()
        state, _elapsed = run_ddl()
        assert state is None
    finally:
        for connection in connections:
            connection.close()


@pytest.mark.parametrize("expired", [False, True])
def test_expiry_cleanup_retains_creation_lock_through_insert(pg, monkeypatch, expired):
    """X4 real probe/control: withdrawal must wait after the final routing read."""
    from threading import Event

    import src.routes.contact as routes
    from src.auth import issue_user_token
    from src.extensions import limiter
    from src.models.contact import ContactRequest
    from src.models.trust import ScoutVerification

    app, ids = pg
    monkeypatch.setenv("CONTACT_RAIL_ENABLED", "true")
    app.config["RATELIMIT_ENABLED"] = False
    limiter.init_app(app)
    app.register_blueprint(routes.contact_bp, url_prefix="/api")
    pubid = make_consented(ids)
    row = Publication.query.filter_by(id=pubid).with_for_update().one()
    service.review(
        row, "reviewer", {"action": "approve", "reason": "Expiry race control", "expected_version": row.version}
    )
    db.session.add(
        ScoutVerification(
            user_account_id=ids["owner"],
            full_name="Synthetic scout",
            organization="Synthetic fixture",
            role_title="Scout",
            statement="Synthetic fixture",
            status="approved",
        )
    )
    db.session.add(
        ContactRequest(
            scout_user_id=ids["owner"],
            player_api_id=-ids["local"],
            claim_id=row.claim_id,
            status="pending" if expired else "expired",
            club_first=True,
            routing_mode="club_included",
            club_program_id=ids["program"],
            club_consent_status="pending",
            message="Preceding request",
            expires_at=service.now() - timedelta(days=1),
        )
    )
    db.session.commit()
    token = issue_user_token(db.session.get(UserAccount, ids["owner"]).email)["token"]
    db.session.commit()
    db.session.remove()
    ready, attempted = Event(), Event()
    original = routes.routing_mode_for_claim

    def routing(claim, *, platform_belief=None):
        result = original(claim, platform_belief=platform_belief)
        ready.set()
        assert attempted.wait(10), "Competing transaction must finish its lock attempt"
        return result

    monkeypatch.setattr(routes, "routing_mode_for_claim", routing)

    def create():
        with app.test_client() as client:
            response = client.post(
                "/api/contact/requests",
                headers={"Authorization": "Bearer " + token},
                json={"player_api_id": -ids["local"], "message": "Racing new introduction"},
            )
            return response.status_code, response.json

    def withdraw():
        assert ready.wait(10)
        with app.app_context():
            try:
                db.session.execute(sa.text("SET LOCAL lock_timeout = '1s'"))
                with pytest.raises(sa.exc.OperationalError) as error:
                    Publication.query.filter_by(id=pubid).with_for_update().one()
                assert error.value.orig.sqlstate == "55P03", "both expiry and no-expiry retain the publication lock"
            finally:
                db.session.rollback()
                db.session.remove()
                attempted.set()

    with ThreadPoolExecutor(max_workers=2) as pool:
        request = pool.submit(create)
        withdrawal = pool.submit(withdraw)
        withdrawal.result(timeout=15)
        status, payload = request.result(timeout=15)
    assert status == 201, payload
    contact = db.session.get(ContactRequest, payload["contact_request"]["id"])
    assert contact.status == "pending"
    # A withdrawal after creation wins in the ordinary serial order and closes the inserted row.
    row = Publication.query.filter_by(id=pubid).populate_existing().with_for_update().one()
    service.revoke(row)
    db.session.commit()
    assert db.session.get(ContactRequest, contact.id).status == "withdrawn"
    service.consent(
        row,
        ids["adult"],
        {"expected_version": row.version, "public_profile_consent": True, "consent_version": service.CONSENT_VERSION},
    )
    service.review(
        row, "reviewer", {"expected_version": row.version, "action": "approve", "reason": "Fresh independent review"}
    )
    db.session.commit()
    assert contact.status == "withdrawn"
    assert not service.scout_counterpart_available(contact)


def test_expiry_commit_gap_rechecks_withdrawn_publication(pg, monkeypatch):
    """A real withdrawal during the cleanup commit gap is refused after reacquisition."""
    import src.routes.contact as routes
    from src.auth import issue_user_token
    from src.extensions import limiter
    from src.models.contact import ContactRequest
    from src.models.trust import ScoutVerification

    app, ids = pg
    monkeypatch.setenv("CONTACT_RAIL_ENABLED", "true")
    app.config["RATELIMIT_ENABLED"] = False
    limiter.init_app(app)
    app.register_blueprint(routes.contact_bp, url_prefix="/api")
    pubid = make_consented(ids)
    row = Publication.query.filter_by(id=pubid).with_for_update().one()
    service.review(row, "reviewer", {"action": "approve", "reason": "Commit gap race", "expected_version": row.version})
    db.session.add(
        ScoutVerification(
            user_account_id=ids["owner"],
            full_name="Synthetic scout",
            organization="Synthetic fixture",
            role_title="Scout",
            statement="Synthetic fixture",
            status="approved",
        )
    )
    db.session.add(
        ContactRequest(
            scout_user_id=ids["owner"],
            player_api_id=-ids["local"],
            claim_id=row.claim_id,
            status="pending",
            club_first=True,
            routing_mode="club_included",
            club_program_id=ids["program"],
            club_consent_status="pending",
            message="Expired request",
            expires_at=service.now() - timedelta(days=1),
        )
    )
    db.session.commit()
    token = issue_user_token(db.session.get(UserAccount, ids["owner"]).email)["token"]
    db.session.commit()
    original = routes._expire_visible_rows

    def expire(query):
        changed = original(query)
        assert changed
        # Separate real connection/transaction while creation's expiry helper has released its lock.
        with app.app_context():
            row = Publication.query.filter_by(id=pubid).with_for_update().one()
            service.revoke(row)
            db.session.commit()
            db.session.remove()
        return changed

    monkeypatch.setattr(routes, "_expire_visible_rows", expire)
    with app.test_client() as client:
        response = client.post(
            "/api/contact/requests",
            headers={"Authorization": "Bearer " + token},
            json={"player_api_id": -ids["local"], "message": "Creation after withdrawn permissions"},
        )
    assert response.status_code == 403, response.json
    assert ContactRequest.query.filter_by(player_api_id=-ids["local"], status="pending").count() == 0


def test_postgres_legacy_archive_repair_keeps_authors_separate(pg):
    from src.models.club_player_publication import RetiredClubShowcase
    from src.services.account import _SchemaView
    from src.services.club_player_publication_account import export_publications, purge_invited_emails

    _app, ids = pg
    pubid = make_consented(ids)
    row = db.session.get(Publication, pubid)
    archive = RetiredClubShowcase(
        local_player_id=ids["local"],
        claim_id=row.claim_id,
        user_account_id=ids["adult"],
        content={
            "player_links": [{"user_id": ids["owner"], "url": "https://example.test/other-author"}],
            "player_showcase_profiles": [{"updated_by_user_id": ids["adult"], "bio": "Claimant own bio"}],
        },
    )
    db.session.add(archive)
    db.session.commit()
    archive_id = archive.id
    owner = db.session.get(UserAccount, ids["owner"])
    data = export_publications(owner, _SchemaView())
    assert "https://example.test/other-author" in str(data["retired_club_showcases"])
    assert "user_id" not in str(data["retired_club_showcases"])
    own = export_publications(db.session.get(UserAccount, ids["adult"]), _SchemaView())
    assert "other-author" not in str(own)
    assert "Claimant own bio" in str(own["retired_club_showcases"])
    db.session.rollback()
    original = db.session.get(RetiredClubShowcase, archive_id)
    assert original.user_account_id == ids["adult"] and "player_links" in original.content
    export_publications(owner, _SchemaView())
    db.session.commit()
    assert RetiredClubShowcase.query.filter_by(local_player_id=ids["local"]).count() == 2
    purge_invited_emails(at=service.now() + timedelta(days=181))
    db.session.commit()
    assert RetiredClubShowcase.query.filter_by(local_player_id=ids["local"]).count() == 0


def test_postgres_erased_canonical_club_identity_can_publish_again(pg):
    from src.models.follow import PlayerShadow
    from src.services.account import delete_account

    _app, ids = pg
    pubid = make_consented(ids)
    row = Publication.query.filter_by(id=pubid).with_for_update().one()
    service.review(
        row,
        "reviewer",
        {"action": "approve", "reason": "Original independent approval", "expected_version": row.version},
    )
    db.session.commit()
    delete_account(db.session.get(UserAccount, ids["adult"]))
    db.session.commit()
    assert db.session.get(Publication, pubid) is None
    assert PlayerShadow.query.filter_by(player_api_id=-ids["local"]).count() == 1
    suffix = uuid4().hex[:12]
    person = UserAccount(
        email=f"returning-{suffix}@example.test",
        display_name=f"Returning claimant {suffix}",
        display_name_lower=f"returning claimant {suffix}",
    )
    db.session.add(person)
    db.session.commit()
    row, token = service.invite(ids["program"], ids["local"], ids["owner"], {"recipient_email": person.email})
    service.redeem(person, {"token": token, "self_claim": True})
    service.consent(
        row,
        person.id,
        {"expected_version": row.version, "public_profile_consent": True, "consent_version": service.CONSENT_VERSION},
    )
    service.review(
        row,
        "reviewer",
        {"action": "approve", "reason": "Fresh returning identity review", "expected_version": row.version},
    )
    db.session.commit()
    assert public_adult_ids([-ids["local"]]) == {-ids["local"]}
