"""Opt-in retained consent and real row-lock races on C1's disposable database."""

import importlib.util
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date
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


def test_postgres_erasure_clears_publication_claim_foreign_key(pg):
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
    user = db.session.get(UserAccount, ids["adult"])
    delete_account(user)
    db.session.commit()
    assert db.session.get(Publication, row_id) is None
    assert db.session.get(UserAccount, ids["adult"]) is None
    assert not public_adult_ids([-ids["local"]])
