"""Opt-in maintenance recovery interleavings on a disposable local database."""

import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from threading import Event, local

import pytest
from flask import Flask
from sqlalchemy import event, make_url, text
from src.models.gol_credits import GolChatExecution, GolCreditLedger
from src.models.league import UserAccount, db
from src.models.product_event import ProductEvent
from src.services import gol_credits
from src.services.gol_availability import GolMaintenance

TABLES = [UserAccount.__table__, GolCreditLedger.__table__, GolChatExecution.__table__, ProductEvent.__table__]


@pytest.fixture
def pg_app(monkeypatch):
    uri = os.getenv("GOL_MAINTENANCE_TEST_POSTGRES_URL")
    if not uri:
        pytest.skip("set GOL_MAINTENANCE_TEST_POSTGRES_URL for local maintenance recovery regressions")
    parsed = make_url(uri)
    assert parsed.host in {"localhost", "127.0.0.1"} and parsed.database == "aw_golmf3"
    app = Flask(__name__)
    app.config.update(SQLALCHEMY_DATABASE_URI=uri, SQLALCHEMY_TRACK_MODIFICATIONS=False)
    db.init_app(app)
    monkeypatch.setenv("BILLING_ENABLED", "true")
    monkeypatch.setenv("GOL_FREE_ALLOWANCE", "1")
    monkeypatch.setenv("GOL_MAINTENANCE", "true")
    with app.app_context():
        assert db.session.execute(text("SELECT current_database()")).scalar_one() == "aw_golmf3"
        db.session.remove()
        db.metadata.create_all(db.engine, tables=TABLES)
        try:
            yield app
        finally:
            db.session.remove()
            db.metadata.drop_all(db.engine, tables=TABLES)
            db.engine.dispose()


@pytest.mark.parametrize("refund", [True, False])
def test_original_failure_wins_lock_before_paused_recovery(pg_app, monkeypatch, refund):
    user = UserAccount(email="recovery@example.test", display_name="Recovery", display_name_lower="recovery")
    db.session.add(user)
    db.session.commit()
    user_id = user.id
    first = gol_credits.reserve_question(user, "pg-recovery-question", question_hash="a" * 64)
    leader_locked, release_leader, retry_lock_started = Event(), Event(), Event()
    worker = local()
    original_lock = gol_credits._lock_user
    retry_writes = []

    def observed_lock(account_id):
        if worker.role == "retry":
            retry_lock_started.set()
        original_lock(account_id)
        if worker.role == "original" and not leader_locked.is_set():
            leader_locked.set()
            assert release_leader.wait(10)

    def capture(conn, cursor, statement, parameters, context, executemany):
        if getattr(worker, "role", None) == "retry" and statement.lstrip().split()[0].upper() in {
            "INSERT",
            "UPDATE",
            "DELETE",
            "REPLACE",
        }:
            retry_writes.append(statement)

    monkeypatch.setattr(gol_credits, "_lock_user", observed_lock)
    engine = db.engine
    event.listen(engine, "before_cursor_execute", capture)

    def original():
        with pg_app.app_context():
            worker.role = "original"
            account = db.session.get(UserAccount, user_id)
            gol_credits.finish_execution(
                account,
                first,
                failed=True,
                refund=refund,
                disconnect_delivered_chars=None if refund else 200,
            )

    def retry():
        with pg_app.app_context():
            worker.role = "retry"
            account = db.session.get(UserAccount, user_id)
            # The hint sees the old committed state while A holds its account lock.
            assert gol_credits.has_recoverable_question_debit(account, "pg-recovery-question") is True
            try:
                gol_credits.reserve_question(account, "pg-recovery-question", question_hash="a" * 64, recover_only=True)
            except GolMaintenance:
                assert not db.session().in_transaction()
                return "maintenance"
            pytest.fail("paused reservation admitted an attempt after the original failed")

    try:
        with ThreadPoolExecutor(max_workers=2) as workers:
            lead = workers.submit(original)
            assert leader_locked.wait(10)
            follow = workers.submit(retry)
            try:
                assert retry_lock_started.wait(10)
                with pytest.raises(TimeoutError):
                    follow.result(timeout=0.25)
            finally:
                release_leader.set()
            lead.result(timeout=10)
            assert follow.result(timeout=10) == "maintenance"
        db.session.expire_all()
        assert retry_writes == []
        assert GolCreditLedger.query.filter_by(kind="debit").count() == 1
        assert GolCreditLedger.query.filter_by(kind="reversal").count() == refund
        assert GolChatExecution.query.one().status == "failed"
        assert ProductEvent.query.filter_by(event_name="gol_question_debited").count() == 1
        assert gol_credits.balances(db.session.get(UserAccount, user_id))["free_questions_remaining"] == int(refund)
    finally:
        release_leader.set()
        event.remove(engine, "before_cursor_execute", capture)
