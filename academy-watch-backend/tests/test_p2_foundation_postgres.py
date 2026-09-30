"""Real PostgreSQL regressions; opt in only against the isolated A1 database.

P2_FOUNDATION_TEST_DATABASE_URL must identify localhost/aw_p2_a1 upgraded p2a1.
No real provider calls. No schema drops; audit history remains until DB cleanup.
"""

import importlib.util
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from flask import Flask
from sqlalchemy.exc import DBAPIError
from src.models.league import UserAccount, db
from src.models.p2_foundation import AdminActionEvent, NotificationOutbox
from src.services.admin_audit import record_admin_event
from src.services.email_service import EmailResult
from src.services.notification_outbox import dispatch_due, enqueue, register_template


@pytest.fixture
def pg_app(monkeypatch):
    uri = os.getenv("P2_FOUNDATION_TEST_DATABASE_URL")
    if not uri:
        pytest.skip("set P2_FOUNDATION_TEST_DATABASE_URL for isolated PostgreSQL regressions")
    url = sa.engine.make_url(uri)
    assert url.database == "aw_p2_a1" and url.host in {"localhost", "127.0.0.1"}
    import src.services.notification_outbox as outbox

    monkeypatch.setattr(outbox, "_templates", {})
    monkeypatch.setenv("P2_FOUNDATION_ENABLED", "1")
    app = Flask(__name__)
    app.config.update(SQLALCHEMY_DATABASE_URI=uri, SQLALCHEMY_TRACK_MODIFICATIONS=False, TESTING=True)
    db.init_app(app)
    with app.app_context():
        assert db.session.execute(sa.text("select current_database()")).scalar() == "aw_p2_a1"
        users = []
        yield users
        db.session.rollback()
        db.session.execute(sa.delete(NotificationOutbox).where(NotificationOutbox.recipient_user_id.in_(users)))
        db.session.execute(sa.delete(UserAccount).where(UserAccount.id.in_(users)))
        db.session.commit()
        db.session.remove()


def _intent(users, template, key):
    unique = uuid4().hex
    user = UserAccount(email=f"{unique}@fixture.invalid", display_name="Fixture", display_name_lower=unique)
    db.session.add(user)
    db.session.flush()
    users.append(user.id)
    row = enqueue(
        dedupe_key=f"{key}:{unique}",
        recipient_user_id=user.id,
        event_type="fixture",
        entity_type="fixture",
        entity_id=1,
        template=template,
        payload={"version": 1},
    )
    db.session.commit()
    return row.id, user.id


def _message(row, user):
    return {"subject": "Fixture", "html": "<p>Sign in.</p>", "text": "Sign in."}


@pytest.mark.parametrize("broken_callback", ["eligible", "render"])
def test_invalid_sql_callback_retries_and_next_row_dispatches(pg_app, broken_callback):
    def invalid(row, user):
        db.session.execute(sa.text("select p2a1_definitely_missing_sql_column"))

    register_template(
        "broken",
        eligible=invalid if broken_callback == "eligible" else lambda r, u: True,
        render=invalid if broken_callback == "render" else _message,
    )
    register_template("good", eligible=lambda r, u: True, render=_message)
    broken, _ = _intent(pg_app, "broken", "broken")
    good, uid = _intent(pg_app, "good", "good")
    sent = []

    def provider(**kwargs):
        assert not db.session().in_transaction()
        # Proves provider call does not retain account locks (including FK-blocking FOR UPDATE).
        with db.engine.begin() as connection:
            connection.execute(sa.text("SET LOCAL lock_timeout = '200ms'"))
            connection.execute(sa.text("select id from user_accounts where id=:uid for update"), {"uid": uid})
        sent.append(kwargs["to"])
        return EmailResult(success=True, provider="fixture")

    summary = dispatch_due(limit=2, now=datetime.now(UTC) + timedelta(seconds=1), send=provider)
    assert summary["retry"] == summary["sent"] == 1 and summary["errors"] == 0
    row = db.session.get(NotificationOutbox, broken)
    assert row.status == "retry" and row.attempts == 1 and row.last_error == "delivery_failed"
    assert db.session.get(NotificationOutbox, good).status == "sent" and len(sent) == 1


@pytest.mark.parametrize("erase_intent", [False, True])
def test_provider_tombstone_race_does_not_finalize_sent_or_resurrect(pg_app, erase_intent):
    register_template("good", eligible=lambda r, u: True, render=_message)
    row_id, uid = _intent(pg_app, "good", "erase")

    def provider(**kwargs):
        assert not db.session().in_transaction()
        with db.engine.begin() as connection:
            connection.execute(sa.text("SET LOCAL lock_timeout = '200ms'"))
            connection.execute(sa.text("update user_accounts set is_tombstone=true where id=:uid"), {"uid": uid})
            if erase_intent:
                connection.execute(sa.text("delete from notification_outbox where id=:id"), {"id": row_id})
        return EmailResult(success=True, provider="fixture")

    summary = dispatch_due(limit=1, now=datetime.now(UTC) + timedelta(seconds=1), send=provider)
    assert summary["sent"] == summary["errors"] == 0
    row = db.session.get(NotificationOutbox, row_id)
    if erase_intent:
        assert row is None
    else:
        assert row.status == "cancelled" and row.lease_token is None


def test_audit_truncate_repeat_redaction_and_downgrade_are_rejected(pg_app):
    actor = f"{uuid4().hex}@fixture.invalid"
    event = record_admin_event(actor, "fixture", "fixture", 1, "Fixture")
    db.session.commit()
    event_id = event.id
    for statement in [
        "TRUNCATE admin_action_events",
        "DELETE FROM admin_action_events WHERE id=:id",
        "UPDATE admin_action_events SET reason='mutated' WHERE id=:id",
    ]:
        with pytest.raises(DBAPIError, match="append-only"):
            with db.session.begin_nested():
                db.session.execute(sa.text(statement), {"id": event_id})
        db.session.rollback()
    db.session.execute(
        sa.text(
            "UPDATE admin_action_events SET actor_email='Account deleted', reason='[redacted]', event_metadata='{}' WHERE id=:id"
        ),
        {"id": event_id},
    )
    db.session.commit()
    with pytest.raises(DBAPIError, match="append-only"):
        with db.session.begin_nested():
            db.session.execute(
                sa.text(
                    "UPDATE admin_action_events SET actor_email='Account deleted', reason='[redacted]', event_metadata='{}' WHERE id=:id"
                ),
                {"id": event_id},
            )
    db.session.rollback()
    path = Path(__file__).resolve().parents[1] / "migrations" / "versions" / "p2a1_foundation.py"
    spec = importlib.util.spec_from_file_location("p2a1_fixture_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with Operations.context(MigrationContext.configure(db.session.connection())):
        with pytest.raises(RuntimeError, match="nonempty admin_action_events"):
            migration.downgrade()
    db.session.rollback()
    assert db.session.get(AdminActionEvent, event_id).reason == "[redacted]"
    rls = (
        db.session.execute(
            sa.text(
                "select relrowsecurity from pg_class where relname in ('notification_outbox','admin_action_events')"
            )
        )
        .scalars()
        .all()
    )
    assert rls == [True, True]


@pytest.mark.parametrize("failure", ["sql", "exception"])
def test_provider_failure_retries_without_aborting_next_row(pg_app, failure):
    register_template("good", eligible=lambda r, u: True, render=_message)
    first, uid = _intent(pg_app, "good", "provider-failure")
    second, _ = _intent(pg_app, "good", "provider-success")
    failed_email = db.session.get(UserAccount, uid).email
    db.session.rollback()

    def provider(**kwargs):
        assert not db.session().in_transaction()
        if kwargs["to"] == failed_email:
            if failure == "sql":
                db.session.execute(sa.text("select p2a1_definitely_missing_sql_column"))
            raise RuntimeError("private provider failure text")
        return EmailResult(success=True, provider="fixture")

    summary = dispatch_due(limit=2, now=datetime.now(UTC) + timedelta(seconds=1), send=provider)
    assert summary["retry"] == summary["sent"] == 1 and summary["errors"] == 0
    assert db.session.get(NotificationOutbox, first).attempts == 1
    assert db.session.get(NotificationOutbox, first).last_error == "delivery_failed"
    assert db.session.get(NotificationOutbox, second).status == "sent"
