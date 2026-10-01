# ruff: noqa: F401, F811
"""A2F8 regressions: a club has at most one active owner, even under concurrent admin assigns.

Two layers, each tested on its own:

- the service takes the ``club_programs`` row lock before it reads the current owner, so concurrent
  assigns queue up and the later one is a clean transfer;
- ``uq_club_access_grants_one_active_owner`` (partial unique index) refuses a second active owner
  in the database, and that refusal surfaces as a 409 ``owner_conflict`` rather than a 500.

The SQLite cases run everywhere.  The PostgreSQL cases need real row locks and opt in through
``P2A2_TEST_DATABASE_URL`` (localhost/``aw_p2_a2`` migrated to ``p2a2``).  All data is synthetic.
"""

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, BrokenBarrierError
from uuid import uuid4

import pytest
import sqlalchemy as sa
from flask import Flask
from sqlalchemy.exc import IntegrityError
from src.auth import issue_user_token
from src.extensions import limiter
from src.models.club_access import ClubAccessGrant
from src.models.funding import ClubProgram, ClubProgramClaim, ClubProgramManager, FundingLeague
from src.models.league import UserAccount, db
from src.models.p2_foundation import AdminActionEvent
from src.routes.club_access import club_access_bp
from src.services import club_access as access_service
from test_club_console import ADMIN_KEY, _admin_headers, _grant_program_manager, _headers, client, club_app
from test_club_staff_access import _email, _join, env

OWNER_INDEX = "uq_club_access_grants_one_active_owner"


def _assign(client, pid, user_id, reason="Verified with the club secretary"):
    return client.post(
        f"/api/admin/programs/{pid}/owner",
        json={"user_account_id": user_id, "reason": reason},
        headers=_admin_headers(),
    )


def _active_owner_ids(pid):
    db.session.expire_all()
    rows = ClubAccessGrant.query.filter_by(program_id=pid, role="owner", status="active").all()
    return [row.user_account_id for row in rows]


@pytest.fixture
def second_manager(env, club_app):
    """Manager "b" becomes a second claim-verified manager of the club that "a" already owns."""
    user_id = club_app.c2["users"]["b"]
    _grant_program_manager(env["pid"], user_id)
    db.session.commit()
    return user_id


# ---------------------------------------------------------------------------
# SQLite: the database rule and its 409 mapping
# ---------------------------------------------------------------------------


def test_database_refuses_a_second_active_owner(env, second_manager):
    db.session.add(ClubAccessGrant(program_id=env["pid"], user_account_id=second_manager, role="owner"))
    with pytest.raises(IntegrityError):
        db.session.flush()
    db.session.rollback()
    # Revoked owner rows are history, not owners: any number may exist beside the active one.
    db.session.add(
        ClubAccessGrant(program_id=env["pid"], user_account_id=second_manager, role="owner", status="revoked")
    )
    db.session.commit()
    assert len(_active_owner_ids(env["pid"])) == 1


def test_owner_index_collision_is_a_clean_409(env, client, club_app, second_manager, monkeypatch):
    """A writer that did not see the current owner (the race the lock closes) loses with a 409."""
    first = club_app.c2["users"]["a"]
    events = AdminActionEvent.query.filter_by(action="club_access_owner_assigned").count()
    monkeypatch.setattr(access_service, "_active_owners_locked", lambda program_id: [])
    resp = _assign(client, env["pid"], second_manager)
    assert resp.status_code == 409 and resp.get_json() == {"error": "owner_conflict"}
    monkeypatch.undo()
    # Nothing of the losing attempt survived: same single owner, no audit row, session still usable.
    assert _active_owner_ids(env["pid"]) == [first]
    assert AdminActionEvent.query.filter_by(action="club_access_owner_assigned").count() == events
    assert ClubAccessGrant.query.filter_by(program_id=env["pid"], user_account_id=second_manager).count() == 0


def test_transfer_revokes_the_previous_owner_first(env, client, club_app, second_manager):
    first = club_app.c2["users"]["a"]
    resp = _assign(client, env["pid"], second_manager, "Handover agreed by the committee")
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["grant"]["role"] == "owner"
    assert _active_owner_ids(env["pid"]) == [second_manager]
    old = ClubAccessGrant.query.filter_by(program_id=env["pid"], user_account_id=first).one()
    assert old.status == "revoked" and old.revoked_at is not None
    # And back again: the revoked row is reactivated, never duplicated.
    assert _assign(client, env["pid"], first).status_code == 200
    assert _active_owner_ids(env["pid"]) == [first]
    assert ClubAccessGrant.query.filter_by(program_id=env["pid"]).count() == 2
    # Re-assigning the sitting owner is a no-op.
    version = ClubAccessGrant.query.filter_by(program_id=env["pid"], user_account_id=first).one().version
    assert _assign(client, env["pid"], first).status_code == 200
    assert ClubAccessGrant.query.filter_by(program_id=env["pid"], user_account_id=first).one().version == version


@pytest.mark.parametrize("operation", ["assign", "remove"])
def test_owner_changes_lock_the_program_before_reading_owners(env, client, second_manager, monkeypatch, operation):
    order = []
    lock, read = access_service._lock_program, access_service._active_owners_locked
    monkeypatch.setattr(access_service, "_lock_program", lambda pid: order.append(("lock", pid)) or lock(pid))
    monkeypatch.setattr(access_service, "_active_owners_locked", lambda pid: order.append(("read", pid)) or read(pid))
    if operation == "assign":
        resp = _assign(client, env["pid"], second_manager)
    else:
        resp = client.delete(f"/api/admin/programs/{env['pid']}/owner", json={"reason": "t"}, headers=_admin_headers())
    assert resp.status_code == 200, resp.get_json()
    assert order == [("lock", env["pid"]), ("read", env["pid"])]


def test_no_club_route_can_promote_to_owner(env, client):
    """Owner comes only from the admin assign; invites and grant edits cannot reach it."""
    coach = _join(client, env, "coach", "coach", squads=[env["sa"]])
    grant_id = ClubAccessGrant.query.filter_by(program_id=env["pid"], user_account_id=env["users"]["coach"]).one().id
    resp = client.patch(f"{env['base']}/access/{grant_id}", json={"role": "owner"}, headers=_headers("a"))
    assert resp.status_code == 422 and resp.get_json()["error"] == "invalid_role"
    resp = client.post(
        f"{env['base']}/staff-invites",
        json={"email": _email("stranger"), "role": "owner", "all_squads": True},
        headers=_headers("a"),
    )
    assert resp.status_code == 422 and resp.get_json()["error"] == "invalid_role"
    assert coach["access"]["role"] == "coach" and len(_active_owner_ids(env["pid"])) == 1


# ---------------------------------------------------------------------------
# Real PostgreSQL: two admins assign different managers at the same moment
# ---------------------------------------------------------------------------

POSTGRES_URL = os.getenv("P2A2_TEST_DATABASE_URL")
needs_postgres = pytest.mark.skipif(not POSTGRES_URL, reason="set P2A2_TEST_DATABASE_URL (localhost/aw_p2_a2 at p2a2)")


@pytest.fixture
def pg(monkeypatch):
    url = sa.engine.make_url(POSTGRES_URL)
    assert url.database == "aw_p2_a2" and url.host in {"localhost", "127.0.0.1"}
    monkeypatch.setenv("ADMIN_API_KEY", ADMIN_KEY)
    monkeypatch.setenv("ADMIN_IP_WHITELIST", "")
    monkeypatch.setenv("CLUB_STAFF_ACCESS_ENABLED", "true")
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SECRET_KEY="a2f8-postgres-fixture-secret",
        SQLALCHEMY_DATABASE_URI=POSTGRES_URL,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        RATELIMIT_ENABLED=False,
    )
    db.init_app(app)
    limiter.init_app(app)
    app.register_blueprint(club_access_bp, url_prefix="/api")
    tag = uuid4().hex[:12]
    with app.app_context():
        assert db.session.execute(sa.text("select current_database()")).scalar() == "aw_p2_a2"
        assert db.session.execute(sa.text("select version_num from alembic_version")).scalar() == "p2a2"
        # The index under test is the one the migration built, not one from create_all.
        assert db.session.execute(
            sa.text("select count(*) from pg_indexes where indexname = :name"), {"name": OWNER_INDEX}
        ).scalar()
        league = FundingLeague(
            name=f"A2F8 League {tag}",
            country="Japan",
            region="Kanto",
            level="youth_regional",
            age_bands=["U18"],
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
            name=f"A2F8 Club {tag}",
            legal_name=f"A2F8 Club {tag} Association",
            slug=f"a2f8-{tag}",
            country="Japan",
            region="Kanto",
            platform_status="approved",
        )
        users = [
            UserAccount(email=f"a2f8-{n}-{tag}@fixture.invalid", display_name=f"A2F8 {n}", display_name_lower=n + tag)
            for n in ("one", "two")
        ]
        db.session.add_all([program, *users])
        db.session.flush()
        for user in users:
            _grant_program_manager(program.id, user.id)
        db.session.commit()
        ids = {"app": app, "pid": program.id, "league": league.id, "users": [u.id for u in users]}
        ids["admin"] = _admin_headers()
        db.session.remove()
    yield ids
    with app.app_context():
        db.session.rollback()
        pid = ids["pid"]
        # admin_action_events is append-only: its rows stay until the scratch database is dropped.
        db.session.execute(sa.delete(ClubAccessGrant).where(ClubAccessGrant.program_id == pid))
        db.session.execute(sa.delete(ClubProgramManager).where(ClubProgramManager.program_id == pid))
        db.session.execute(sa.delete(ClubProgramClaim).where(ClubProgramClaim.program_id == pid))
        db.session.execute(sa.delete(ClubProgram).where(ClubProgram.id == pid))
        db.session.execute(sa.delete(FundingLeague).where(FundingLeague.id == ids["league"]))
        db.session.execute(sa.delete(UserAccount).where(UserAccount.id.in_(ids["users"])))
        db.session.commit()
        db.session.remove()
        db.engine.dispose()


def _owners(pg):
    with pg["app"].app_context():
        rows = ClubAccessGrant.query.filter_by(program_id=pg["pid"], role="owner").all()
        out = {status: [r.user_account_id for r in rows if r.status == status] for status in ("active", "revoked")}
        db.session.remove()
    return out


def _race(pg, monkeypatch, *, meet_timeout):
    """Both admins post at once; each pauses right after reading the current owners.

    Returns the two responses plus whether the two requests ever held the "no owner yet" read at
    the same time (the precondition of the original bug).
    """
    start, meet = Barrier(2), Barrier(2)
    read = access_service._active_owners_locked

    def read_then_wait(program_id):
        rows = read(program_id)
        try:
            meet.wait(timeout=meet_timeout)
        except BrokenBarrierError:
            pass
        return rows

    monkeypatch.setattr(access_service, "_active_owners_locked", read_then_wait)
    admin = pg["admin"]

    def post(user_id):
        start.wait(timeout=10)
        resp = (
            pg["app"]
            .test_client()
            .post(
                f"/api/admin/programs/{pg['pid']}/owner",
                json={"user_account_id": user_id, "reason": "Synthetic concurrent assign"},
                headers=admin,
            )
        )
        return user_id, resp.status_code, resp.get_json()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [f.result(timeout=60) for f in [pool.submit(post, uid) for uid in pg["users"]]]
    monkeypatch.undo()
    return results, not meet.broken


@needs_postgres
def test_concurrent_assigns_queue_on_the_program_lock_and_leave_one_owner(pg, monkeypatch):
    results, overlapped = _race(pg, monkeypatch, meet_timeout=2)
    # The second request never reached the owner read while the first was still open.
    assert not overlapped
    assert [status for _, status, _ in results] == [200, 200], results
    owners = _owners(pg)
    assert len(owners["active"]) == 1 and len(owners["revoked"]) == 1, owners
    assert set(owners["active"] + owners["revoked"]) == set(pg["users"])
    # The later request was a transfer: it replaced exactly the earlier request's owner.
    with pg["app"].app_context():
        counts = sorted(
            event.event_metadata["replaced_grant_count"]
            for event in AdminActionEvent.query.filter_by(
                action="club_access_owner_assigned", target_id=str(pg["pid"])
            ).all()
        )
        db.session.remove()
    assert counts == [0, 1]


@needs_postgres
def test_without_the_lock_the_index_still_allows_only_one_owner(pg, monkeypatch):
    """Bypass the service lock entirely (as an out-of-band writer would): the database decides."""
    monkeypatch.setattr(access_service, "_lock_program", lambda program_id: None)
    results, overlapped = _race(pg, monkeypatch, meet_timeout=20)
    assert overlapped, "both requests must have read 'no owner' together for this to prove anything"
    by_status = {status: (uid, body) for uid, status, body in results}
    assert sorted(by_status) == [200, 409], results
    assert by_status[409][1] == {"error": "owner_conflict"}
    owners = _owners(pg)
    assert owners == {"active": [by_status[200][0]], "revoked": []}


@needs_postgres
def test_repeated_races_and_assign_versus_remove_never_leave_two_owners(pg):
    admin = pg["admin"]
    url = f"/api/admin/programs/{pg['pid']}/owner"

    def assign(user_id):
        resp = pg["app"].test_client().post(url, json={"user_account_id": user_id, "reason": "race"}, headers=admin)
        return resp.status_code

    def remove(_):
        return pg["app"].test_client().delete(url, json={"reason": "race"}, headers=admin).status_code

    for round_no in range(12):
        calls = [(assign, pg["users"][0]), (assign, pg["users"][1])]
        if round_no % 3 == 2:
            calls.append((remove, None))
        with ThreadPoolExecutor(max_workers=len(calls)) as pool:
            statuses = [f.result(timeout=60) for f in [pool.submit(fn, arg) for fn, arg in calls]]
        assert all(status in (200, 404) for status in statuses), statuses
        assert len(_owners(pg)["active"]) <= 1
    assert (
        pg["app"]
        .test_client()
        .post(url, json={"user_account_id": pg["users"][0], "reason": "final"}, headers=admin)
        .status_code
        == 200
    )
    assert _owners(pg)["active"] == [pg["users"][0]]
