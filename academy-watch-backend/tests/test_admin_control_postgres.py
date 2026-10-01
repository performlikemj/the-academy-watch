"""Real PostgreSQL RB3 isolation/idempotency probes, isolated schema in own scratch DB."""

import os
from uuid import uuid4

import pytest
import sqlalchemy as sa
from flask import Flask
from src.extensions import limiter
from src.models.follow import PlayerShadow
from src.models.league import UserAccount, db
from src.routes.admin_control import admin_control_bp
from src.routes.admin_programs import admin_programs_bp
from src.routes.auth_routes import auth_bp
from src.services.admin_control_safety import register_safety
from test_admin_control_rb3 import (
    test_hide_reconcile_is_idempotent_notification_dedupes_and_records_owner_event as check_cases,
)
from test_admin_control_rb3 import (
    test_webhook_projection_failure_preserves_authoritative_commit_and_replay_repairs as check_webhook,
)


@pytest.fixture
def pg_control(monkeypatch):
    uri = os.getenv("P2_B3_TEST_DATABASE_URL")
    if not uri:
        pytest.skip("set P2_B3_TEST_DATABASE_URL for isolated PostgreSQL regressions")
    url = sa.engine.make_url(uri)
    assert url.host in {"localhost", "127.0.0.1"} and url.database == "aw_p2_b3"
    schema = "b3f2_" + uuid4().hex
    engine = sa.create_engine(uri)
    with engine.begin() as conn:
        conn.execute(sa.text(f"CREATE SCHEMA {schema}"))
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SECRET_KEY="control-test",
        SQLALCHEMY_DATABASE_URI=uri,
        SQLALCHEMY_ENGINE_OPTIONS={"connect_args": {"options": f"-csearch_path={schema}"}},
    )
    db.init_app(app)
    app.config["RATELIMIT_ENABLED"] = False
    limiter.init_app(app)
    for blueprint in (admin_control_bp, admin_programs_bp, auth_bp):
        app.register_blueprint(blueprint, url_prefix="/api")
    for flag in (
        "ADMIN_PROGRAMS_ENABLED",
        "ADMIN_PEOPLE_ENABLED",
        "ADMIN_SAFETY_ENABLED",
        "ADMIN_BUSINESS_ENABLED",
        "P2_FOUNDATION_ENABLED",
    ):
        monkeypatch.setenv(flag, "1")
    monkeypatch.setenv("ADMIN_API_KEY", "test-control-key")
    monkeypatch.setenv("ADMIN_EMAILS", "admin@example.test")
    monkeypatch.setenv("PLAYER_SUPPRESSION_ENCRYPTION_KEY", "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=")
    register_safety()
    try:
        with app.app_context():
            db.create_all()
            db.session.add_all(
                [
                    UserAccount(email="admin@example.test", display_name="Admin", display_name_lower="admin"),
                    UserAccount(email="person@example.test", display_name="Person", display_name_lower="person"),
                    PlayerShadow(player_api_id=321, player_name="Prospect"),
                ]
            )
            db.session.commit()
            yield app
            db.session.remove()
    finally:
        with engine.begin() as conn:
            conn.execute(sa.text(f"DROP SCHEMA {schema} CASCADE"))
        engine.dispose()


def test_postgres_cash_failure_aborts_only_projection_replay_repairs(pg_control, monkeypatch):
    check_webhook(pg_control, monkeypatch)


def test_postgres_case_hide_reconcile_has_no_phantom_case(pg_control):
    check_cases(pg_control)


@pytest.mark.parametrize("target", ["player", "club"])
def test_postgres_repeat_hide_restore_hide(pg_control, target):
    from test_admin_control_rb3v import test_repeat_hide_restore_hide_succeeds_and_dedupes as check

    check(pg_control, target)


def test_postgres_old_tool_lift_then_report_resolution(pg_control):
    from test_admin_control_rb3v import (
        test_old_tool_lift_then_report_resolution_succeeds_without_duplicate_email as check,
    )

    check(pg_control)


@pytest.mark.parametrize("sql_failure", [False, True])
def test_postgres_notification_failure_isolated(pg_control, monkeypatch, sql_failure):
    from test_admin_control_rb3v import test_notification_collision_or_sql_failure_never_aborts_admin_action as check

    check(pg_control, monkeypatch, sql_failure)


@pytest.mark.parametrize("refund_first", [False, True])
def test_postgres_signed_stripe_cash_replay_out_of_order(pg_control, monkeypatch, refund_first):
    from test_admin_control_rb3v import test_real_signed_stripe_invoice_refund_replay_out_of_order_records_cash as check

    check(pg_control, monkeypatch, refund_first)


def test_postgres_real_stripe_lists_and_reconcile(pg_control, monkeypatch):
    from test_admin_control_rb3v import test_real_stripe_list_pages_and_reconciliation as check

    check(pg_control, monkeypatch)


def test_postgres_takedown_cycles_preserve_evidence(pg_control):
    from test_admin_control_rb3v import (
        test_takedown_hide_restore_hide_preserves_original_evidence_and_separate_admin_reason as check,
    )

    check(pg_control)


def test_postgres_sibling_case_ownership(pg_control):
    from test_admin_control_rb3v import test_report_hide_syncs_sibling_without_taking_requesters_hold_ownership as check

    check(pg_control)


def test_postgres_huge_offset_rejected(pg_control):
    from test_admin_control_rb3v import test_huge_offset_is_400 as check

    for path in ("people", "programs", "safety/cases", "business/summary"):
        check(pg_control, path)
