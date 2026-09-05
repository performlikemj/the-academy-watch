"""P2 claimant pinning, withdrawal, migration recovery, and concurrency attacks."""

from datetime import date, timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from src.models.club_invitation import ClubInvitation, utcnow
from src.models.funding import ClubProgram, ClubProgramManager, ClubRosterMember
from src.models.league import db
from src.models.showcase import LocalPlayer, PlayerProfileClaim
from src.models.tracked_player import TrackedPlayer
from test_club_console import _grant_program_manager, _headers
from test_club_console import client as client
from test_club_console import club_app as club_app


@pytest.fixture
def pilot(club_app, monkeypatch):
    monkeypatch.setenv("PILOT_CLUB_RELATIONSHIPS_ENABLED", "true")
    claim = PlayerProfileClaim(
        player_api_id=7001,
        user_account_id=club_app.c2["users"]["scout"],
        relationship_type="player",
        status="approved",
        reviewed_at=utcnow(),
    )
    local = LocalPlayer(
        display_name="Synthetic P2 Player",
        birth_date=date(2000, 1, 1),
        country="Japan",
        status="approved",
        created_by_user_id=claim.user_account_id,
    )
    db.session.add_all([claim, local])
    db.session.flush()
    local.api_player_id = -local.id
    local_claim = PlayerProfileClaim(
        local_player_id=local.id,
        user_account_id=claim.user_account_id,
        relationship_type="player",
        status="approved",
        reviewed_at=utcnow(),
    )
    db.session.add(local_claim)
    db.session.commit()
    return {
        "program": club_app.c2["program_a"],
        "claim": claim,
        "local_claim": local_claim,
        "local": local,
        "user": claim.user_account_id,
    }


def create(client, pilot, signed_id=7001, request_id=None, key="a"):
    return client.post(
        f"/api/club/{pilot['program']}/invitations",
        json={"player_api_id": signed_id, "client_request_id": request_id or str(uuid4())},
        headers=_headers(key),
    )


def decide(client, invitation_id, action="accept", key="scout"):
    return client.post(f"/api/me/club-invitations/{invitation_id}/{action}", json={}, headers=_headers(key))


def invitation(client, pilot, signed_id=7001):
    response = create(client, pilot, signed_id)
    assert response.status_code == 201, response.json
    return response.json["invitation"]["id"]


@pytest.mark.parametrize("local", [False, True])
def test_acceptance_pins_claim_and_preserves_identity(client, pilot, local):
    signed_id = -pilot["local"].id if local else 7001
    claim = pilot["local_claim"] if local else pilot["claim"]
    before = claim.to_dict()
    row_id = invitation(client, pilot, signed_id)
    response = decide(client, row_id)
    assert response.status_code == 200, response.json
    assert response.json["invitation"]["status"] == "accepted"
    assert response.headers["Cache-Control"] == "private, no-store"
    member = ClubRosterMember.query.one()
    assert member.requires_player_acceptance and member.accepted_invitation_id == row_id
    assert member.local_player_id == (pilot["local"].id if local else None)
    assert claim.to_dict() == before
    assert pilot["local"].created_by_user_id == pilot["user"]
    assert decide(client, row_id).json == {"error": "invitation_already_resolved"}
    assert ClubRosterMember.query.count() == 1


def test_create_replay_changed_payload_and_double_create(client, pilot):
    request_id = str(uuid4())
    first = create(client, pilot, request_id=request_id)
    replay = create(client, pilot, request_id=request_id)
    assert replay.status_code == 200 and first.json == replay.json
    assert create(client, pilot, -pilot["local"].id, request_id).json == {"error": "client_request_id_reused"}
    assert create(client, pilot).json == {"error": "invitation_exists"}
    assert ClubInvitation.query.count() == 1


def test_multiple_claimants_pin_newest_and_wrong_recipient_neutral(client, pilot, club_app):
    other = PlayerProfileClaim(
        player_api_id=7001,
        user_account_id=club_app.c2["users"]["b"],
        relationship_type="player",
        status="approved",
        reviewed_at=utcnow() + timedelta(seconds=1),
    )
    db.session.add(other)
    db.session.commit()
    row_id = invitation(client, pilot)
    assert ClubInvitation.query.one().claim_id == other.id
    assert decide(client, row_id).status_code == 404
    assert (
        client.get("/api/me/club-invitations?player_api_id=7001", headers=_headers("scout")).json["invitations"] == []
    )
    assert decide(client, row_id, key="b").status_code == 200


@pytest.mark.parametrize("action", ["accept", "decline"])
def test_expiry_boundary_and_replacement(client, pilot, action):
    row_id = invitation(client, pilot)
    row = db.session.get(ClubInvitation, row_id)
    with patch("src.models.club_invitation.utcnow", return_value=row.expires_at):
        assert decide(client, row_id, action).json == {"error": "invitation_expired"}
        assert row.status == "expired"
        assert create(client, pilot).status_code == 201
    assert ClubRosterMember.query.count() == 0


def test_inviter_revoked_then_second_manager_after_acceptance(client, pilot, club_app):
    row_id = invitation(client, pilot)
    manager = ClubProgramManager.query.filter_by(
        program_id=pilot["program"], user_account_id=club_app.c2["users"]["a"]
    ).one()
    manager.status = "revoked"
    db.session.commit()
    assert decide(client, row_id).json == {"error": "invitation_unavailable"}
    manager.status = "active"
    db.session.commit()
    assert decide(client, row_id).status_code == 200
    _grant_program_manager(pilot["program"], club_app.c2["users"]["b"])
    manager.status = "revoked"
    db.session.commit()
    path = f"/api/club/{pilot['program']}/invitations/{row_id}/revoke"
    first = client.post(path, json={}, headers=_headers("b"))
    assert first.status_code == 200
    assert client.post(path, json={}, headers=_headers("b")).json == first.json
    assert ClubRosterMember.query.count() == 0


@pytest.mark.parametrize(
    "state",
    [
        "unknown-age",
        "minor",
        "hidden",
        "suspended",
        "self",
        "revoked-claim",
        "agent",
        "guardian",
        "club_official",
        "suppressed",
    ],
)
def test_unavailable_subject_and_authority(client, pilot, club_app, state):
    player = TrackedPlayer.query.filter_by(player_api_id=7001).one()
    if state == "unknown-age":
        player.birth_date = None
    elif state == "minor":
        player.birth_date = "2015-01-01"
    elif state == "hidden":
        db.session.get(ClubProgram, pilot["program"]).emergency_hidden = True
    elif state == "suspended":
        db.session.get(ClubProgram, pilot["program"]).platform_status = "suspended"
    elif state == "self":
        pilot["claim"].user_account_id = club_app.c2["users"]["a"]
    elif state == "revoked-claim":
        pilot["claim"].status = "revoked"
    elif state == "suppressed":
        from src.models.player_suppression import PlayerSuppression

        db.session.add(
            PlayerSuppression(
                player_api_id=7001,
                status="active",
                reason_code="player_request",
                requester_role="player",
                requester_contact="test@example.com",
                request_statement="Synthetic suppression",
            )
        )
    else:
        pilot["claim"].relationship_type = state
    db.session.commit()
    response = create(client, pilot)
    assert response.status_code in {403, 404}, response.json
    assert ClubInvitation.query.count() == 0


@pytest.mark.parametrize("state", ["merged", "graduated", "unknown-age", "minor"])
def test_local_identity_invalidated_before_acceptance(client, pilot, state):
    row_id = invitation(client, pilot, -pilot["local"].id)
    local = pilot["local"]
    if state == "merged":
        local.status = "merged"
    elif state == "graduated":
        local.api_player_id = 7002
    elif state == "unknown-age":
        local.birth_date = None
        local.birth_year = None
    elif state == "minor":
        local.birth_date = date(2015, 1, 1)
        local.birth_year = 2015
    db.session.commit()
    assert decide(client, row_id).status_code == 404
    assert ClubRosterMember.query.count() == 0


@pytest.mark.parametrize(
    "body",
    [
        [],
        None,
        True,
        {},
        {"player_api_id": True, "client_request_id": str(uuid4())},
        {"player_api_id": 0, "client_request_id": str(uuid4())},
        {"player_api_id": 2147483648, "client_request_id": str(uuid4())},
        {"player_api_id": 7001, "client_request_id": "x" * 100},
        {"player_api_id": 7001, "client_request_id": str(uuid4()), "recipient_email": "private@example.com"},
    ],
)
def test_create_body_validation(client, pilot, body):
    response = client.post(f"/api/club/{pilot['program']}/invitations", json=body, headers=_headers("a"))
    assert response.status_code == 400 and response.json == {"error": "invalid_request"}
    assert response.headers["Cache-Control"] == "private, no-store"


def test_wrong_program_and_disabled_authority_order(client, pilot, club_app, monkeypatch):
    row_id = invitation(client, pilot)
    path = f"/api/club/{club_app.c2['program_b']}/invitations/{row_id}/revoke"
    assert client.post(path, json={}, headers=_headers("b")).json == {"error": "invitation_not_found"}
    monkeypatch.setenv("PILOT_CLUB_RELATIONSHIPS_ENABLED", "false")
    assert create(client, pilot).json == {"error": "not_found"}
    assert create(client, pilot, key="scout").json == {"error": "Club manager access denied"}
    assert decide(client, row_id, key="b").json == {"error": "invitation_not_found"}
    assert decide(client, row_id).json == {"error": "not_found"}
    assert ClubInvitation.query.count() == 1 and ClubRosterMember.query.count() == 0


def test_existing_roster_reused_no_provider_authority_and_lost_fk_denies(client, pilot):
    from src.routes.club import _ClubResultConflict, _member_subject, _result_player

    player = TrackedPlayer.query.filter_by(player_api_id=7001).one()
    player.current_club_api_id = 98765
    # Also remove academy ownership: private acceptance must not authorize provider results.
    program = db.session.get(ClubProgram, pilot["program"])
    program.team_api_id = 98766
    db.session.commit()
    added = client.post(f"/api/club/{pilot['program']}/roster", json={"player_api_id": 7001}, headers=_headers("a"))
    member_id = added.json["member"]["id"]
    row_id = invitation(client, pilot)
    assert decide(client, row_id).json["invitation"]["roster_member_id"] == member_id
    roster = client.get(f"/api/club/{pilot['program']}/roster", headers=_headers("a"))
    assert roster.json["members"][0]["public_stats_allowed"] is False
    member = db.session.get(ClubRosterMember, member_id)
    member.accepted_invitation_id = None
    db.session.commit()
    assert _member_subject(member) == (None, None)
    with pytest.raises(_ClubResultConflict):
        _result_player(member)


def test_foreign_local_attachment_denied_then_acceptance(client, pilot):
    response = client.post(
        f"/api/club/{pilot['program']}/roster", json={"local_player_id": pilot["local"].id}, headers=_headers("a")
    )
    assert response.status_code == 404
    assert decide(client, invitation(client, pilot, -pilot["local"].id)).status_code == 200


def test_roster_failure_rolls_back_entire_acceptance(client, pilot):
    row_id = invitation(client, pilot)
    from sqlalchemy import event

    def fail(*args):
        raise RuntimeError("private failure detail")

    event.listen(ClubRosterMember, "before_insert", fail)
    try:
        response = decide(client, row_id)
    finally:
        event.remove(ClubRosterMember, "before_insert", fail)
    assert response.json == {"error": "invitation_operation_failed"}
    assert db.session.get(ClubInvitation, row_id).status == "pending"
    assert ClubRosterMember.query.count() == 0


def test_decline_replay_and_recipient_pagination(client, pilot):
    row_id = invitation(client, pilot)
    assert decide(client, row_id, "decline").status_code == 200
    assert decide(client, row_id, "decline").json == {"error": "invitation_already_resolved"}
    second = invitation(client, pilot, -pilot["local"].id)
    page = client.get("/api/me/club-invitations?limit=1", headers=_headers("scout")).json
    assert page["invitations"][0]["id"] == second and page["next_before"] == second
    next_page = client.get(f"/api/me/club-invitations?before={second}", headers=_headers("scout")).json
    assert [row["id"] for row in next_page["invitations"]] == [row_id]
    assert client.get(f"/api/me/club-invitations?before={second}", headers=_headers("b")).status_code == 404


@pytest.fixture
def postgres_app(club_app, pilot):
    import os

    import sqlalchemy as sa
    from flask import Flask
    from flask_migrate import Migrate
    from src.extensions import limiter
    from src.routes.club import club_bp
    from src.routes.showcase import showcase_bp

    url = os.getenv("PILOT_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("PILOT_TEST_POSTGRES_URL unset; disposable PostgreSQL required")
    assert sa.engine.make_url(url).database.startswith("pilot_p2_"), "Use a disposable pilot_p2_ database"
    from src.models.league import TeamProfile

    db.session.add_all(
        [TeamProfile(team_id=9911, name="Synthetic Club A"), TeamProfile(team_id=9912, name="Synthetic Club B")]
    )
    db.session.commit()
    seeds = [
        (table, [dict(row) for row in db.session.execute(sa.select(table)).mappings()])
        for table in db.metadata.sorted_tables
    ]
    app = Flask("pilot-postgres")
    app.config.update(
        TESTING=True,
        SECRET_KEY=club_app.config["SECRET_KEY"],
        SQLALCHEMY_DATABASE_URI=url,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        RATELIMIT_ENABLED=False,
    )
    db.init_app(app)
    limiter.init_app(app)
    app.register_blueprint(club_bp, url_prefix="/api")
    app.register_blueprint(showcase_bp, url_prefix="/api")
    Migrate(app, db)
    with app.app_context():
        with db.engine.begin() as connection:
            connection.execute(sa.text("DROP SCHEMA public CASCADE"))
            connection.execute(sa.text("CREATE SCHEMA public"))
        # This unrelated legacy table requires PostgreSQL 15; P2 supports the supplied PG14.
        db.metadata.create_all(
            db.engine,
            tables=[
                t
                for t in db.metadata.sorted_tables
                if t.name not in {"player_transfer_events", "transfer_admin_events"}
            ],
        )
        for table, rows in seeds:
            if rows:
                db.session.execute(sa.insert(table), rows)
        db.session.commit()
        # Restore sequences after explicit seed IDs.
        for table, rows in seeds:
            if rows and "id" in table.c and isinstance(table.c.id.type, sa.Integer):
                db.session.execute(
                    sa.text(
                        "SELECT setval(pg_get_serial_sequence(:table, 'id'), (SELECT max(id) FROM "
                        + table.name
                        + "), true)"
                    ),
                    {"table": table.name},
                )
        db.session.commit()
        yield app
        db.session.remove()
        db.engine.dispose()


@pytest.mark.parametrize("state", ["fresh", "pre-applied", "partial"])
def test_postgres_online_migration_recovery(postgres_app, state):
    from pathlib import Path

    import sqlalchemy as sa
    from flask_migrate import stamp, upgrade

    directory = str(Path(__file__).resolve().parents[1] / "migrations")
    with db.engine.begin() as connection:
        if state != "pre-applied":
            connection.execute(sa.text("ALTER TABLE club_roster_members DROP COLUMN accepted_invitation_id"))
            connection.execute(sa.text("ALTER TABLE club_roster_members DROP COLUMN requires_player_acceptance"))
            connection.execute(sa.text("DROP TABLE club_invitations"))
        if state == "partial":
            connection.execute(
                sa.text("CREATE TABLE club_invitations (id varchar(36) NOT NULL, program_id integer NOT NULL)")
            )
            connection.execute(
                sa.text(
                    "ALTER TABLE club_roster_members ADD COLUMN requires_player_acceptance boolean NOT NULL DEFAULT false"
                )
            )
    stamp(directory=directory, revision="s3e1")
    upgrade(directory=directory, revision="s4a1")
    with db.engine.connect() as connection:
        inspector = sa.inspect(connection)
        assert len(inspector.get_columns("club_invitations")) == 14
        assert len(inspector.get_foreign_keys("club_invitations")) == 5
        assert len(inspector.get_check_constraints("club_invitations")) == 3
        assert len(inspector.get_unique_constraints("club_invitations")) == 1
        assert inspector.get_pk_constraint("club_invitations")["constrained_columns"] == ["id"]
        indexes = {row["name"]: row for row in inspector.get_indexes("club_invitations")}
        assert indexes["uq_club_invitation_active"]["unique"]
        assert "pending" in str(indexes["uq_club_invitation_active"]["dialect_options"]["postgresql_where"])
        assert (
            connection.scalar(sa.text("SELECT relrowsecurity FROM pg_class WHERE oid = 'club_invitations'::regclass"))
            is True
        )
        assert connection.scalar(sa.text("SELECT count(*) FROM pg_policies WHERE tablename = 'club_invitations'")) == 0
        assert connection.scalar(sa.text("SELECT version_num FROM alembic_version")) == "s4a1"
        assert {c["name"] for c in inspector.get_columns("club_roster_members")} >= {
            "accepted_invitation_id",
            "requires_player_acceptance",
        }
    # Execute an actual second online upgrade from the declared parent.
    stamp(directory=directory, revision="s3e1")
    upgrade(directory=directory, revision="s4a1")


def test_postgres_concurrent_acceptance_exclusion(postgres_app, pilot):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    with postgres_app.test_client() as http:
        row_id = invitation(http, pilot)
    barrier = Barrier(2)

    def worker():
        with postgres_app.app_context(), postgres_app.test_client() as http:
            barrier.wait(timeout=10)
            result = decide(http, row_id)
            return result.status_code, result.json

    db.session.remove()
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: worker(), range(2)))
    assert sorted(status for status, _ in outcomes) == [200, 409], outcomes
    assert next(body for status, body in outcomes if status == 409) == {"error": "invitation_already_resolved"}
    assert ClubRosterMember.query.count() == 1
    assert db.session.get(ClubInvitation, row_id).status == "accepted"


def test_postgres_concurrent_create_replay(postgres_app, pilot):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    request_id = str(uuid4())
    barrier = Barrier(2)

    def worker():
        with postgres_app.app_context(), postgres_app.test_client() as http:
            barrier.wait(timeout=10)
            result = create(http, pilot, request_id=request_id)
            return result.status_code, result.json

    db.session.remove()
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: worker(), range(2)))
    assert sorted(status for status, _ in outcomes) == [200, 201], outcomes
    assert outcomes[0][1] == outcomes[1][1]
    assert ClubInvitation.query.count() == 1


def test_withdrawal_cannot_be_reattached_as_legacy_roster(client, pilot):
    row_id = invitation(client, pilot)
    assert decide(client, row_id).status_code == 200
    assert decide(client, row_id, "revoke").status_code == 200
    response = client.post(f"/api/club/{pilot['program']}/roster", json={"player_api_id": 7001}, headers=_headers("a"))
    assert response.json == {"error": "club_relationship_required"}
    assert ClubRosterMember.query.count() == 0


@pytest.mark.parametrize("sqlstate", ["40001", "40P01"])
def test_transaction_conflicts_rollback_with_retry_contract(client, pilot, sqlstate):
    from sqlalchemy.exc import OperationalError

    class Conflict(Exception):
        pass

    error = Conflict()
    error.sqlstate = sqlstate
    with patch("src.routes.club.create_invitation", side_effect=OperationalError("redacted", {}, error)):
        response = create(client, pilot)
    assert response.status_code == 409 and response.json == {"error": "retry_conflict"}
    assert ClubInvitation.query.count() == 0


def test_rate_rejection_is_json_private_and_flag_precedes_limiting(client, pilot, club_app, monkeypatch):
    from src.extensions import limiter

    monkeypatch.setattr(limiter, "enabled", True)
    monkeypatch.setitem(club_app.config, "RATELIMIT_ENABLED", True)
    limiter.init_app(club_app)
    limiter.reset()
    try:
        monkeypatch.setenv("PILOT_CLUB_RELATIONSHIPS_ENABLED", "false")
        for _ in range(22):
            assert create(client, pilot).status_code == 404
        monkeypatch.setenv("PILOT_CLUB_RELATIONSHIPS_ENABLED", "true")
        for _ in range(20):
            response = client.post(f"/api/club/{pilot['program']}/invitations", json={}, headers=_headers("a"))
            assert response.status_code == 400
        limited = create(client, pilot)
        assert limited.status_code == 429 and limited.json == {"error": "rate_limit_exceeded"}
        assert int(limited.headers["Retry-After"]) > 0
        assert limited.headers["Cache-Control"] == "private, no-store"
    finally:
        limiter.reset()


def test_postgres_withdrawal_serializes_stale_message_admission(postgres_app, pilot, club_app):
    import time
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    import sqlalchemy as sa
    from src.models.club_invitation import resolve_invitation
    from src.models.contact import ContactRequest
    from src.services.contact import messaging_is_open
    from test_local_club_attestation import contacts

    with postgres_app.test_client() as http:
        row_id = invitation(http, pilot, -pilot["local"].id)
        assert decide(http, row_id).status_code == 200
    # Use PG-bound claim rows, not detached SQLite seed objects.
    pg_pilot = {
        **pilot,
        "claim": db.session.get(PlayerProfileClaim, pilot["claim"].id),
        "local_claim": db.session.get(PlayerProfileClaim, pilot["local_claim"].id),
    }
    contact_id = contacts(pg_pilot, club_app)[0].id
    db.session.remove()
    invitation_row = db.session.get(ClubInvitation, row_id)
    resolve_invitation(db.session, invitation_row, pilot["user"], "revoke")
    # Keep withdrawal uncommitted while a second connection loads the old state.
    loaded = Event()
    info = {}

    def admit():
        with postgres_app.app_context():
            row = db.session.get(ContactRequest, contact_id)
            assert row.status == "accepted"
            info["pid"] = db.session.scalar(sa.text("SELECT pg_backend_pid()"))
            loaded.set()
            result = messaging_is_open(row)
            db.session.rollback()
            return result

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(admit)
        assert loaded.wait(timeout=5)
        try:
            deadline = time.monotonic() + 5
            blocked = False
            while time.monotonic() < deadline:
                with db.engine.connect() as connection:
                    blocked = connection.scalar(
                        sa.text("SELECT wait_event_type = 'Lock' FROM pg_stat_activity WHERE pid = :pid"),
                        {"pid": info["pid"]},
                    )
                if blocked:
                    break
                time.sleep(0.02)
            assert blocked, "Message admission must wait on withdrawal contact-row lock"
        finally:
            db.session.commit()
        assert future.result(timeout=5) is False
