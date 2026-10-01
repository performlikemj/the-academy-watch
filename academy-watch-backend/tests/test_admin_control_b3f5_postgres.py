"""Two-admin real PostgreSQL schedules from the final review-duel."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
import sqlalchemy as sa
from src.models.admin_control import SafeguardingCase, SafeguardingCaseEvent
from src.models.league import UserAccount, db
from src.models.player_suppression import PlayerSuppression
from src.services import admin_control_safety as safety
from test_admin_control import headers, report
from test_admin_control_postgres import pg_control as _pg_control

pg_control = _pg_control


@pytest.mark.parametrize("guardian", [False, True])
@pytest.mark.parametrize("first_index", [0, 1])
def test_two_admin_hides_serialize_without_unique_failure_or_deadlock(pg_control, monkeypatch, guardian, first_index):
    if guardian:
        pending = PlayerSuppression(
            player_api_id=321,
            reason_code="guardian_request",
            requester_role="guardian",
            requester_contact="guardian@example.test",
            request_statement="Original guardian evidence",
        )
        db.session.add(pending)
        db.session.commit()
        first = SafeguardingCase.query.filter_by(suppression_id=pending.id).one()
    else:
        first = report()
    second = report()
    ids = [first.id, second.id]
    db.session.add(
        UserAccount(email="second.admin@example.test", display_name="Second Admin", display_name_lower="second admin")
    )
    db.session.commit()
    monkeypatch.setenv("ADMIN_EMAILS", "admin@example.test,second.admin@example.test")
    credentials = [headers(), headers("second.admin@example.test")]
    # Release the fixture's read transaction before competing request sessions.
    engine = db.engine
    db.session.commit()
    locked, release = threading.Event(), threading.Event()
    original = safety._hide

    def hide(case, *args):
        if case.id == ids[first_index] and not locked.is_set():
            locked.set()
            assert release.wait(timeout=10)
        return original(case, *args)

    monkeypatch.setattr(safety, "_hide", hide)

    def request(index, version=1):
        return pg_control.test_client().post(
            f"/api/admin/safety/cases/{ids[index]}/actions",
            headers=credentials[index],
            json={"version": version, "action": "hide", "reason": "Independent admin hide"},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        winner = pool.submit(request, first_index)
        assert locked.wait(timeout=10)
        loser = pool.submit(request, 1 - first_index)
        try:
            deadline = time.monotonic() + 5
            with engine.connect() as observer:
                while not observer.execute(
                    sa.text("SELECT count(*) FROM pg_locks WHERE locktype='advisory' AND NOT granted")
                ).scalar():
                    assert time.monotonic() < deadline
                    time.sleep(0.02)
            assert not loser.done()
        finally:
            release.set()
        results = [winner.result(timeout=10), loser.result(timeout=10)]
    assert results[0].status_code == 200
    assert results[1].status_code in {200, 409}
    if results[1].status_code == 409:
        with pg_control.app_context():
            version = db.session.get(SafeguardingCase, ids[1 - first_index]).version
        assert request(1 - first_index, version).status_code == 200
    db.session.expire_all()
    assert PlayerSuppression.query.filter_by(player_api_id=321, status="active").count() == 1
    assert (
        SafeguardingCaseEvent.query.filter(
            SafeguardingCaseEvent.case_id.in_(ids), SafeguardingCaseEvent.action == "hide"
        ).count()
        == 2
    )
    if guardian:
        assert db.session.get(PlayerSuppression, pending.id).request_statement == "Original guardian evidence"


@pytest.mark.parametrize("target", ["player", "club"])
@pytest.mark.parametrize("closed", [False, True])
def test_postgres_second_hide_survives_restore(pg_control, target, closed):
    from test_admin_control_b3f5 import test_second_case_hide_survives_first_restore as check

    check(pg_control, target, closed)


def test_postgres_erasure_of_case_copies(pg_control):
    from test_admin_control_b3f5 import test_erase_case_generated_copies_preserves_requester_evidence_and_hold as check

    check(pg_control)


@pytest.mark.parametrize("source_type", ["report", "suppression"])
def test_postgres_preapply_window_repair(pg_control, source_type):
    from test_admin_control_b3f5 import test_reconcile_repairs_preapply_window_but_preserves_case_decisions as check

    check(pg_control, source_type)


def test_unique_index_winner_from_old_writer_is_reloaded_in_savepoint(pg_control):
    case = report()
    engine = db.engine
    injected = []

    def before(conn, cursor, statement, parameters, context, many):
        if statement.startswith("INSERT INTO player_suppressions") and not injected:
            injected.append(True)
            with engine.begin() as old_writer:
                old_writer.execute(
                    PlayerSuppression.__table__.insert().values(
                        player_api_id=321,
                        reason_code="guardian_request",
                        requester_role="guardian",
                        requester_contact="guardian@example.test",
                        request_statement="Old writer genuine evidence",
                        status="requested",
                    )
                )

    sa.event.listen(engine, "before_cursor_execute", before)
    try:
        from test_admin_control import action

        response = action(pg_control.test_client(), case, "hide")
    finally:
        sa.event.remove(engine, "before_cursor_execute", before)
    assert response.status_code == 200
    assert injected
    winner = PlayerSuppression.query.one()
    assert winner.status == "active" and winner.request_statement == "Old writer genuine evidence"
    assert case.suppression_id is None and case.owned_suppression_id is None
    assert SafeguardingCaseEvent.query.filter_by(case_id=case.id, action="hide").count() == 1


def test_full_http_pg_admin_erase_after_hide_and_flag_rollback(pg_control, monkeypatch):
    import importlib.util
    from pathlib import Path

    from src.auth import issue_user_token
    from src.models.admin_control import BillingCashEvent, now
    from src.routes.account import account_bp
    from test_admin_control import action

    pg_control.register_blueprint(account_bp, url_prefix="/api")
    spec = importlib.util.spec_from_file_location(
        "erase_test_p2b3", Path(__file__).parents[1] / "migrations/versions/p2b3_admin_control.py"
    )
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    schema = db.session.execute(sa.text("SELECT current_schema()")).scalar()
    db.session.execute(sa.text(migration.EVENT_GUARD.replace("public.", schema + ".")))
    db.session.commit()
    case = report()
    client = pg_control.test_client()
    assert action(client, case, "hide").status_code == 200
    assert action(client, case, "restore").status_code == 200
    assert action(client, case, "hide").status_code == 200
    assert action(client, case, "close").status_code == 200
    admin = UserAccount.query.filter_by(email="admin@example.test").one()
    token, uid, sid, cid = issue_user_token(admin.email)["token"], admin.id, case.suppression_id, case.id
    generated = db.session.get(PlayerSuppression, sid)
    generated.requester_contact = admin.email
    generated.request_statement = generated.notes = "Case review"
    db.session.add(
        PlayerSuppression(
            player_api_id=999,
            reason_code="guardian_request",
            requester_role="guardian",
            requester_contact=admin.email,
            request_statement="Genuine requester evidence",
            status="active",
        )
    )
    db.session.add(
        BillingCashEvent(
            source_key="erase-fixture",
            stripe_event_id="evt_erase",
            kind="receipt",
            amount_cents=1234,
            currency="usd",
            occurred_at=now(),
            product_code="gol",
            purchaser_user_id=uid,
            scope_type="user",
            scope_id=uid,
        )
    )
    db.session.commit()
    for flag in ("ADMIN_SAFETY_ENABLED", "ADMIN_PEOPLE_ENABLED", "ADMIN_PROGRAMS_ENABLED", "ADMIN_BUSINESS_ENABLED"):
        monkeypatch.setenv(flag, "0")
    response = client.post(
        "/api/account/delete", headers={"Authorization": "Bearer " + token}, json={"confirm": "DELETE"}
    )
    assert response.status_code == 200, response.json
    assert response.json["deleted"]
    db.session.expire_all()
    assert db.session.get(UserAccount, uid) is None
    generated = db.session.get(PlayerSuppression, sid)
    assert (generated.requester_contact, generated.request_statement, generated.notes) == (
        "Account deleted",
        "[redacted]",
        "[redacted]",
    )
    assert generated.status == "active"
    genuine = PlayerSuppression.query.filter_by(player_api_id=999).one()
    assert (
        genuine.requester_contact == "admin@example.test" and genuine.request_statement == "Genuine requester evidence"
    )
    assert genuine.status == "active"
    assert not SafeguardingCaseEvent.query.filter_by(actor_email="admin@example.test").count()
    assert db.session.get(SafeguardingCase, cid).owned_suppression_id == sid
    cash = BillingCashEvent.query.one()
    assert cash.amount_cents == 1234 and cash.purchaser_user_id is None and cash.scope_id is None


def test_postgres_club_aliases_share_target(pg_control):
    from test_admin_control_b3f5 import test_club_aliases_share_lock_and_hold_intent as check

    check(pg_control)
