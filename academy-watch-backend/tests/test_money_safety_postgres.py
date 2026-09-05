"""Opt-in, disposable LOCAL PostgreSQL tests for locks and guarded migration DDL.

MS_M1_TEST_POSTGRES_URL must identify a throwaway database on loopback.
The fixture creates and drops the money tables. Never point it at a shared DB.
"""

import importlib.util
import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier, Event, local
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from flask import Flask
from sqlalchemy import inspect, make_url, text
from src.models.billing import BillingCheckoutSession, GolCheckoutTerms
from src.models.gol_credits import GolChatExecution, GolCreditLedger, GolPaymentSettlement
from src.models.league import UserAccount, db
from src.models.product_event import ProductEvent
from src.services import stripe_billing
from src.services.gol_credits import QuestionInFlight, balances, finish_execution, reserve_question

BASE = [UserAccount.__table__, BillingCheckoutSession.__table__, GolCreditLedger.__table__, ProductEvent.__table__]
NEW = [GolChatExecution.__table__, GolPaymentSettlement.__table__, GolCheckoutTerms.__table__]


def _migration():
    path = Path(__file__).parents[1] / "migrations/versions/s3e1_money_safety.py"
    spec = importlib.util.spec_from_file_location("money_safety_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def pg_app(monkeypatch):
    url = os.getenv("MS_M1_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Set MS_M1_TEST_POSTGRES_URL to a disposable local PostgreSQL database")
    parsed = make_url(url)
    assert parsed.host in {"localhost", "127.0.0.1"} and parsed.database == "ms_m1_test"
    application = Flask(__name__)
    application.config.update(SQLALCHEMY_DATABASE_URI=url, SQLALCHEMY_TRACK_MODIFICATIONS=False)
    db.init_app(application)
    monkeypatch.setenv("BILLING_ENABLED", "true")
    with application.app_context():
        db.metadata.create_all(db.engine, tables=BASE)
        with db.engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
            _migration().upgrade()
        yield application
        db.session.remove()
        db.metadata.drop_all(db.engine, tables=NEW + BASE)
        db.engine.dispose()


def _seed(*, precreate_settlement=False):
    user = UserAccount(email="locks@example.test", display_name="Locks", display_name_lower="locks")
    db.session.add(user)
    db.session.flush()
    row = BillingCheckoutSession(
        scope_type="user",
        scope_id=user.id,
        product_code="gol",
        price_code="gol_starter",
        purchaser_user_id=user.id,
        client_key="pg_checkout",
        stripe_session_id="cs_pg",
    )
    db.session.add(row)
    db.session.flush()
    db.session.add(
        GolCheckoutTerms(
            purchase_key=str(uuid4()),
            checkout_row_id=row.id,
            stripe_session_id="cs_pg",
            price_code="gol_starter",
            credits=7,
            unit_amount_cents=2000,
            currency="usd",
            stripe_price_id="price_fake",
        )
    )
    if precreate_settlement:
        db.session.add(GolPaymentSettlement(stripe_payment_intent_id="pi_pg"))
    db.session.commit()
    return user.id


@pytest.mark.parametrize("first", ["refund", "grant"])
def test_settlement_lock_closes_refund_no_grant_and_grant_no_hold_interleaving(pg_app, first):
    user_id = _seed()
    first_ready, release_first, second_started = Event(), Event(), Event()

    def apply(kind):
        if kind == "refund":
            stripe_billing._apply_event(
                "charge.refunded", {"payment_intent": "pi_pg", "amount_refunded": 2000}, 1, "evt_pg_refund"
            )
        else:
            stripe_billing._apply_gol_checkout(
                {
                    "id": "cs_pg",
                    "mode": "payment",
                    "payment_status": "paid",
                    "payment_intent": "pi_pg",
                    "currency": "usd",
                    "amount_total": 2000,
                },
                "evt_pg_grant",
                require_paid=True,
            )

    def leader():
        with pg_app.app_context():
            apply(first)
            db.session.flush()
            first_ready.set()
            assert release_first.wait(5)
            db.session.commit()

    def follower():
        with pg_app.app_context():
            second_started.set()
            apply("grant" if first == "refund" else "refund")
            db.session.commit()

    with ThreadPoolExecutor(max_workers=2) as workers:
        lead = workers.submit(leader)
        assert first_ready.wait(5)
        follow = workers.submit(follower)
        try:
            assert second_started.wait(5)
            with pytest.raises(TimeoutError):
                follow.result(timeout=0.25)
        finally:
            release_first.set()
        lead.result(timeout=5)
        follow.result(timeout=5)
    db.session.expire_all()
    assert balances(db.session.get(UserAccount, user_id))["credit_balance"] == 0
    settlement = GolPaymentSettlement.query.one()
    assert settlement.refund_target_cents == settlement.refund_applied_cents == 2000
    assert GolCreditLedger.query.filter_by(kind="reversal").one().delta == -7


def test_two_reclaimers_only_one_generation_wins_on_postgres(pg_app):
    user_id = _seed()
    first = reserve_question(db.session.get(UserAccount, user_id), "pg_question", question_hash="a" * 64)
    execution = GolChatExecution.query.one()
    execution.lease_started_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=6)
    db.session.commit()
    barrier = Barrier(2)

    def reclaim():
        with pg_app.app_context():
            user = db.session.get(UserAccount, user_id)
            barrier.wait(timeout=5)
            try:
                return reserve_question(user, "pg_question", question_hash="a" * 64)
            except QuestionInFlight:
                return None

    with ThreadPoolExecutor(max_workers=2) as workers:
        futures = [workers.submit(reclaim) for _ in range(2)]
        results = [future.result(timeout=5) for future in futures]
    assert sum(result is not None for result in results) == 1
    db.session.expire_all()
    assert GolChatExecution.query.one().lease_generation == 2
    assert not finish_execution(db.session.get(UserAccount, user_id), first, failed=True)
    assert GolCreditLedger.query.filter_by(kind="reversal").count() == 0


def test_migration_upgrade_downgrade_guards_rls_indexes_and_model_columns(pg_app):
    db.session.remove()
    migration = _migration()
    with db.engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        migration.upgrade()  # Already created by the fixture: verify pre-apply drift.
        inspector = inspect(conn)
        for table in NEW:
            assert {col["name"] for col in inspector.get_columns(table.name)} == set(table.columns.keys())
            assert (
                conn.execute(
                    text("SELECT relrowsecurity FROM pg_class WHERE relname = :name"), {"name": table.name}
                ).scalar_one()
                is True
            )
        for name, table, _ in migration.INDEXES:
            assert name in {index["name"] for index in inspector.get_indexes(table)}
        migration.downgrade()
        migration.downgrade()
        assert all(not inspect(conn).has_table(table.name) for table in NEW)
        migration.upgrade()


def test_existing_settlement_blocks_on_select_for_update_before_any_mutation(pg_app, monkeypatch):
    user_id = _seed(precreate_settlement=True)
    leader_locked, release_leader = Event(), Event()
    follower_started, follower_acquired = Event(), Event()
    worker = local()
    original_lock = stripe_billing._lock_gol_settlement

    def observed_lock(intent):
        if worker.role == "follower":
            follower_started.set()
        settlement = original_lock(intent)
        if worker.role == "leader":
            # Pause before changing any settlement field or acquiring the user
            # lock: only SELECT FOR UPDATE can block the second handler here.
            leader_locked.set()
            assert release_leader.wait(5)
        else:
            follower_acquired.set()
        return settlement

    monkeypatch.setattr(stripe_billing, "_lock_gol_settlement", observed_lock)

    def refund():
        with pg_app.app_context():
            worker.role = "leader"
            stripe_billing._apply_event(
                "charge.refunded", {"payment_intent": "pi_pg", "amount_refunded": 2000}, 1, "evt_row_refund"
            )
            db.session.commit()

    def grant():
        with pg_app.app_context():
            worker.role = "follower"
            stripe_billing._apply_gol_checkout(
                {
                    "id": "cs_pg",
                    "mode": "payment",
                    "payment_status": "paid",
                    "payment_intent": "pi_pg",
                    "currency": "usd",
                    "amount_total": 2000,
                },
                "evt_row_grant",
                require_paid=True,
            )
            db.session.commit()

    with ThreadPoolExecutor(max_workers=2) as workers:
        lead = workers.submit(refund)
        assert leader_locked.wait(5)
        follow = workers.submit(grant)
        try:
            assert follower_started.wait(5)
            assert not follower_acquired.wait(0.5), "settlement SELECT FOR UPDATE did not block the follower"
        finally:
            release_leader.set()
            lead.result(timeout=5)
            follow.result(timeout=5)
    assert follower_acquired.is_set()
    db.session.expire_all()
    settlement = GolPaymentSettlement.query.one()
    assert settlement.refund_target_cents == settlement.refund_applied_cents == 2000
    assert balances(db.session.get(UserAccount, user_id))["credit_balance"] == 0
