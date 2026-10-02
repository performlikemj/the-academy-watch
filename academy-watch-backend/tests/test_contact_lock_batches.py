# ruff: noqa: F811
"""RC1XV3-O: flows that call the lock helper more than once in one transaction (SQLite is enough:
the helper's 'extend backwards -> retry' rule is pure Python)."""

from uuid import uuid4

from src.models.club_invitation import utcnow
from src.models.league import UserAccount, db
from src.models.player_feedback import PlayerFeedback
from src.models.showcase import PlayerProfileClaim
from src.services.account import delete_account
from test_club_console import _admin_headers, _headers
from test_club_console import club_app as club_app  # noqa: F401
from test_club_invitations import decide
from test_club_invitations import pilot as pilot  # noqa: F401
from test_player_feedback import client as client  # noqa: F401


def invite(client, program, signed_id, key):
    r = client.post(
        f"/api/club/{program}/invitations",
        json={"player_api_id": signed_id, "client_request_id": str(uuid4())},
        headers=_headers(key),
    )
    assert r.status_code == 201, r.json
    return r.json["invitation"]["id"]


def publish(client, program, inv, key):
    r = client.post(
        f"/api/club/{program}/player-feedback",
        json={"invitation_id": inv, "client_request_id": str(uuid4()), "title": "T", "body": "B"},
        headers=_headers(key),
    )
    assert r.status_code == 201, r.json
    return r.json["feedback"]


def test_player_lists_feedback_from_two_clubs(client, pilot, club_app):
    a, b = club_app.c2["program_a"], club_app.c2["program_b"]
    ia = invite(client, a, 7001, "a")
    assert decide(client, ia).status_code == 200
    publish(client, a, ia, "a")
    ib = invite(client, b, 7001, "b")
    rb = decide(client, ib)
    assert rb.status_code == 200, rb.json
    publish(client, b, ib, "b")
    r = client.get("/api/me/player-feedback?player_api_id=7001", headers=_headers("scout"))
    print("PLAYER LIST", r.status_code, r.json)
    assert r.status_code == 200, r.json
    assert len(r.json["feedback"]) == PlayerFeedback.query.count()


def test_manager_lists_feedback_two_players_second_claims_other_club(client, pilot, club_app):
    a, b = club_app.c2["program_a"], club_app.c2["program_b"]
    i1 = invite(client, a, 7001, "a")
    assert decide(client, i1).status_code == 200
    publish(client, a, i1, "a")
    i2 = invite(client, a, -pilot["local"].id, "a")
    assert decide(client, i2).status_code == 200
    publish(client, a, i2, "a")
    # the provider-claim player says (on their claim) that their club is B; first-listed thread is the local one
    pilot["claim"].club_program_id = b
    db.session.commit()
    r = client.get(f"/api/club/{a}/player-feedback", headers=_headers("a"))
    print("MANAGER LIST", r.status_code, r.json if r.status_code != 200 else len(r.json["feedback"]))
    assert r.status_code == 200, r.json
    assert len(r.json["feedback"]) == 2


def test_purge_job_two_players(client, pilot, club_app):
    a, b = club_app.c2["program_a"], club_app.c2["program_b"]
    i1 = invite(client, a, 7001, "a")
    assert decide(client, i1).status_code == 200
    publish(client, a, i1, "a")
    i2 = invite(client, a, -pilot["local"].id, "a")
    assert decide(client, i2).status_code == 200
    publish(client, a, i2, "a")
    pilot["claim"].club_program_id = b
    pilot["local_claim"].club_program_id = None
    db.session.commit()
    r = client.post("/api/admin/player-feedback/purge", json={"dry_run": True}, headers=_admin_headers())
    print("PURGE", r.status_code, r.json)
    assert r.status_code == 200, r.json
    assert r.json["scanned"] == 2


def test_manager_who_invited_two_players_deletes_account(client, pilot, club_app):
    a, b = club_app.c2["program_a"], club_app.c2["program_b"]
    i1 = invite(client, a, 7001, "a")
    assert decide(client, i1).status_code == 200
    i2 = invite(client, a, -pilot["local"].id, "a")
    assert decide(client, i2).status_code == 200
    pilot["claim"].club_program_id = b
    pilot["local_claim"].club_program_id = None
    db.session.commit()
    manager = db.session.get(UserAccount, club_app.c2["users"]["a"])
    try:
        delete_account(manager)
        db.session.commit()
        outcome = "deleted"
    except Exception as exc:  # noqa: BLE001
        db.session.rollback()
        outcome = f"{type(exc).__name__}: {str(exc)[:120]}"
    print("DELETE MANAGER", outcome)
    assert outcome == "deleted"


def test_purge_job_feedback_from_two_clubs(client, pilot, club_app):
    a, b = club_app.c2["program_a"], club_app.c2["program_b"]
    ia = invite(client, a, 7001, "a")
    assert decide(client, ia).status_code == 200
    publish(client, a, ia, "a")
    ib = invite(client, b, 7001, "b")
    assert decide(client, ib).status_code == 200
    publish(client, b, ib, "b")
    r = client.post("/api/admin/player-feedback/purge", json={"dry_run": True}, headers=_admin_headers())
    print("PURGE2", r.status_code, r.json)
    assert r.status_code == 200, r.json


def _delete(user_id):
    user = db.session.get(UserAccount, user_id)
    try:
        delete_account(user)
        db.session.commit()
        assert db.session.get(UserAccount, user_id) is None
        return "deleted"
    except Exception as exc:  # noqa: BLE001
        db.session.rollback()
        return f"{type(exc).__name__}: {getattr(getattr(exc, 'orig', None), 'sqlstate', None)} {str(exc)[:80]}"


def test_manager_deletes_account_second_invited_player_claims_other_club(client, pilot, club_app):
    a, b = club_app.c2["program_a"], club_app.c2["program_b"]
    i1 = invite(client, a, 7001, "a")
    assert decide(client, i1).status_code == 200
    i2 = invite(client, a, -pilot["local"].id, "a")
    assert decide(client, i2).status_code == 200
    pilot["claim"].club_program_id = None
    pilot["local_claim"].club_program_id = b  # second claim (higher id) names club B
    db.session.commit()
    outcome = _delete(club_app.c2["users"]["a"])
    print("DELETE MANAGER (2nd player other club)", outcome)
    assert outcome == "deleted"


def test_manager_who_is_also_a_scout_with_a_request_deletes_account(client, pilot, club_app):
    from src.models.contact import ContactRequest

    a = club_app.c2["program_a"]
    i1 = invite(client, a, 7001, "a")
    assert decide(client, i1).status_code == 200
    other = PlayerProfileClaim(
        player_api_id=7002,
        user_account_id=club_app.c2["users"]["b"],
        relationship_type="player",
        status="approved",
        reviewed_at=utcnow(),
    )
    db.session.add(other)
    db.session.flush()
    db.session.add(
        ContactRequest(
            scout_user_id=club_app.c2["users"]["a"],
            player_api_id=7002,
            claim_id=other.id,
            status="withdrawn",
            routing_mode="direct",
            message="old request",
            expires_at=utcnow(),
        )
    )
    db.session.commit()
    outcome = _delete(club_app.c2["users"]["a"])
    print("DELETE MANAGER+SCOUT", outcome)
    assert outcome == "deleted"


def test_player_with_two_clubs_deletes_account(client, pilot, club_app):
    a, b = club_app.c2["program_a"], club_app.c2["program_b"]
    ia = invite(client, a, 7001, "a")
    assert decide(client, ia).status_code == 200
    publish(client, a, ia, "a")
    ib = invite(client, b, 7001, "b")
    assert decide(client, ib).status_code == 200
    publish(client, b, ib, "b")
    outcome = _delete(club_app.c2["users"]["scout"])
    print("DELETE PLAYER 2 CLUBS", outcome)
    assert outcome == "deleted"


def test_feedback_lists_do_not_lock_or_write(client, pilot, club_app):
    from sqlalchemy import event

    a, b = club_app.c2["program_a"], club_app.c2["program_b"]
    ia = invite(client, a, 7001, "a")
    assert decide(client, ia).status_code == 200
    first = publish(client, a, ia, "a")
    ib = invite(client, b, 7001, "b")
    assert decide(client, ib).status_code == 200
    second = publish(client, b, ib, "b")
    statements = []
    locking_queries = []
    from sqlalchemy.orm import Query

    original = Query.with_for_update

    def lock(query, *args, **kwargs):
        locking_queries.append(True)
        return original(query, *args, **kwargs)

    from unittest.mock import patch

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(db.engine, "before_cursor_execute", record)
    try:
        with patch.object(Query, "with_for_update", lock):
            response = client.get("/api/me/player-feedback?player_api_id=7001", headers=_headers("scout"))
            assert response.status_code == 200
            assert {row["id"] for row in response.json["feedback"]} == {first["id"], second["id"]}
            for program, key in ((a, "a"), (b, "b")):
                response = client.get(f"/api/club/{program}/player-feedback", headers=_headers(key))
                assert response.status_code == 200 and len(response.json["feedback"]) == 1
    finally:
        event.remove(db.engine, "before_cursor_execute", record)
    assert not locking_queries
    assert not [
        sql
        for sql in statements
        if "FOR UPDATE" in sql or sql.lstrip().upper().startswith(("UPDATE", "DELETE", "INSERT"))
    ]
