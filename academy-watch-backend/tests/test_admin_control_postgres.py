"""Real PostgreSQL RB3 isolation/idempotency probes, isolated schema in own scratch DB."""

import os
from uuid import uuid4

import pytest
import sqlalchemy as sa
from flask import Flask
from src.models.follow import PlayerShadow
from src.models.league import UserAccount, db
from src.routes.admin_control import admin_control_bp
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
    schema = "b3f1_" + uuid4().hex
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
    app.register_blueprint(admin_control_bp, url_prefix="/api")
    for flag in ("ADMIN_SAFETY_ENABLED", "ADMIN_BUSINESS_ENABLED", "P2_FOUNDATION_ENABLED"):
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
