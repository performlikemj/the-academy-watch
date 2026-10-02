# ruff: noqa: F811
"""RC1XV3-O: own pairings on real PostgreSQL. First contender keeps its first row lock until the second attempts one."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier, Event, local

import pytest
import sqlalchemy as sa
from src.models.contact import ContactMessage, ContactOutcome, ContactRequest
from src.models.league import db
from src.services import club_player_publication as publication
from test_club_player_publication_postgres import pg  # noqa: F401
from test_contact_lock_matrix_postgres import execute, setup_world


def world(pg, monkeypatch, mode, *, pending=False, consent_pending=False, second_thread=False):
    actions = (("accept",) if pending else ()) + (("consent",) if consent_pending else ()) + ("message_scout",)
    app, ids, tokens = setup_world(pg, monkeypatch, actions, mode)
    with app.app_context():
        if second_thread:
            now = publication.now()
            r2 = ContactRequest(
                scout_user_id=ids["other_scout"],
                player_api_id=-ids["local"],
                claim_id=ids["claim"],
                status="accepted",
                club_first=mode == "club",
                routing_mode="club_included",
                club_program_id=ids["program"],
                club_consent_status="granted",
                message="second thread",
                responded_at=now,
                expires_at=now + timedelta(days=7),
            )
            db.session.add(r2)
            db.session.commit()
            ids["request2"] = r2.id
        db.session.remove()
    return app, ids, tokens


def act(app, ids, tokens, action, marker):
    def call(role, method, url, data=None):
        with app.test_client() as client:
            r = client.open(url, method=method, headers={"Authorization": "Bearer " + tokens[role]}, json=data)
            return r.status_code, r.get_json()

    base = f"/api/contact/requests/{ids['request']}"
    if action == "message_other":
        return call("other_scout", "POST", f"/api/contact/requests/{ids['request2']}/messages", {"body": marker})
    if action == "list_other":
        return call("other_scout", "GET", f"/api/contact/requests/{ids['request2']}/messages")
    if action == "outcome_player":
        return call("player", "POST", base + "/outcome", {"stage": "contacted", "notes": marker})
    if action == "delete_scout":
        return call("scout", "POST", "/api/account/delete", {"confirm": "DELETE"})
    if action == "delete_club":
        return call("club", "POST", "/api/account/delete", {"confirm": "DELETE"})
    if action == "feedback_list_player":
        return call("player", "GET", f"/api/me/player-feedback?player_api_id={-ids['local']}")
    if action == "feedback_list_club":
        return call("club", "GET", f"/api/club/{ids['program']}/player-feedback")
    if action == "requests_scout":
        return call("scout", "GET", "/api/contact/requests?box=sent")
    if action == "requests_player":
        return call("player", "GET", "/api/contact/requests?box=inbox")
    return execute(app, ids, tokens, action, marker)


def pair(app, ids, tokens, first, second, hold=True):
    owns, attempted, finished = Event(), Event(), Event()
    thread = local()
    with app.app_context():
        engine = db.engine
    errors = []

    def before(conn, cursor, statement, parameters, context, executemany):
        if "FOR UPDATE" in statement and getattr(thread, "role", None) == "second":
            attempted.set()

    def after(conn, cursor, statement, parameters, context, executemany):
        if getattr(thread, "role", None) == "first" and "FOR UPDATE" in statement and not owns.is_set():
            owns.set()
            attempted.wait(5)

    def err(context):
        errors.append((getattr(thread, "role", None), getattr(context.original_exception, "sqlstate", None)))

    if hold:
        sa.event.listen(engine, "before_cursor_execute", before)
        sa.event.listen(engine, "after_cursor_execute", after)
    sa.event.listen(engine, "handle_error", err)
    barrier = Barrier(2)

    def run(role, action):
        thread.role = role
        try:
            if hold:
                if role == "second":
                    owns.wait(10) or finished.is_set()
            else:
                barrier.wait(10)
            return act(app, ids, tokens, action, f"{role}-{action}")
        finally:
            if role == "first":
                finished.set()
                owns.set()
            else:
                attempted.set()

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            a, b = pool.submit(run, "first", first), pool.submit(run, "second", second)
            results = (a.result(40), b.result(40))
    finally:
        if hold:
            sa.event.remove(engine, "before_cursor_execute", before)
            sa.event.remove(engine, "after_cursor_execute", after)
        sa.event.remove(engine, "handle_error", err)
    return results, errors


def brief(result):
    status, body = result
    body = body or {}
    return status, body.get("code") or body.get("error")


def check(app, ids, name, first, second, results, errors):
    with app.app_context():
        r1 = db.session.get(ContactRequest, ids["request"])
        state = (r1.status, r1.club_consent_status) if r1 else None
        stored = {m.body for m in ContactMessage.query.all()}
        outcomes = {o.notes for o in ContactOutcome.query.all()}
        lost = []
        for role, action, (status, body) in (("first", first, results[0]), ("second", second, results[1])):
            marker = f"{role}-{action}"
            if action.startswith("message") and status == 201 and marker not in stored:
                gone = r1 is None or ("request2" in ids and db.session.get(ContactRequest, ids["request2"]) is None)
                lost.append((marker, "thread deleted" if gone else "LOST"))
            if action.startswith("outcome") and status == 201 and marker not in outcomes and r1 is not None:
                lost.append((marker, "LOST"))
        db.session.rollback()
        db.session.remove()
    line = f"RC1XV3-O {name}: {first}={brief(results[0])} {second}={brief(results[1])} final={state} sqlerrors={errors} lost={lost}"
    print(line)
    assert all(r[0] < 500 for r in results), line
    assert any(r[0] in {200, 201} for r in results), line
    if {first, second} <= {
        "message_scout",
        "message_other",
        "list_other",
        "message_player",
        "message_club",
        "outcome_player",
        "feedback_list_player",
        "feedback_list_club",
        "requests_player",
        "requests_scout",
    }:
        assert all(r[0] in {200, 201} for r in results), line
    if {first, second} == {"delete_club", "feedback"}:
        assert not errors, line
        assert 200 in [r[0] for r in results], line
    assert not [x for x in lost if x[1] == "LOST"], line
    return line


CASES = [
    # mode, kwargs, first, second
    ("club", dict(second_thread=True), "message_scout", "message_other"),
    ("club", dict(second_thread=True), "message_other", "revoke"),
    ("club", dict(second_thread=True), "list_other", "message_player"),
    ("club", dict(second_thread=True), "delete_scout", "message_other"),
    ("ordinary", dict(second_thread=True), "message_scout", "message_other"),
    ("ordinary", dict(), "outcome_player", "accept"),
    ("club", dict(), "outcome_player", "accept"),
    ("ordinary", dict(), "outcome_player", "message_club"),
    ("club", dict(consent_pending=True), "delete_scout", "consent"),
    ("ordinary", dict(consent_pending=True), "delete_scout", "consent"),
    ("club", dict(), "delete_scout", "message_player"),
    ("ordinary", dict(), "delete_club", "message_scout"),
    ("club", dict(), "delete_club", "message_scout"),
    ("club", dict(), "delete_club", "feedback"),
    ("ordinary", dict(), "delete_club", "feedback"),
    ("ordinary", dict(), "erasure", "feedback_list_club"),
    ("club", dict(), "feedback_list_player", "message_player"),
    ("ordinary", dict(), "feedback_list_club", "message_club"),
    ("club", dict(pending=True), "accept", "requests_scout"),
    ("ordinary", dict(), "requests_player", "message_club"),
    ("ordinary", dict(), "application", "message_player"),
    ("ordinary", dict(), "invitation", "message_scout"),
    ("club", dict(), "showcase", "message_scout"),
    ("club", dict(), "public_withdraw", "message_scout"),
    ("club", dict(), "review_reject", "message_player"),
]


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("case", CASES, ids=lambda c: f"{c[0]}-{c[2]}-{c[3]}")
def test_pair(pg, monkeypatch, case, reverse):
    mode, kwargs, left, right = case
    app, ids, tokens = world(pg, monkeypatch, mode, **kwargs)
    first, second = (right, left) if reverse else (left, right)
    results, errors = pair(app, ids, tokens, first, second)
    check(app, ids, f"HOLD {mode}", first, second, results, errors)


FREE = [c for c in CASES if c[2] in {"message_scout", "outcome_player", "delete_scout", "delete_club"}]


@pytest.mark.parametrize("round_", range(3))
@pytest.mark.parametrize("case", FREE, ids=lambda c: f"{c[0]}-{c[2]}-{c[3]}")
def test_free(pg, monkeypatch, case, round_):
    mode, kwargs, left, right = case
    app, ids, tokens = world(pg, monkeypatch, mode, **kwargs)
    results, errors = pair(app, ids, tokens, left, right, hold=False)
    check(app, ids, f"FREE {mode}", left, right, results, errors)
