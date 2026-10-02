"""Maintenance switch for the assistant."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import Flask
from sqlalchemy import event
from src.auth import issue_user_token
from src.extensions import limiter
from src.models.gol_credits import GolChatExecution, GolCreditLedger
from src.models.league import UserAccount, db
from src.models.product_event import ProductEvent
from src.routes import gol
from src.services import gol_service
from src.services.gol_availability import (
    GolMaintenance,
    assistant_under_maintenance,
    maintenance_enabled,
    maintenance_payload,
)
from src.services.gol_credits import balances

_REAL_GOL_SERVICE = gol_service.GolService


@pytest.mark.parametrize("state", ["switch", "missing"])
@pytest.mark.parametrize("ending", ["text", "empty", "eof", "final_token"])
def test_active_provider_stream_stops_and_refunds(app, monkeypatch, state, ending):
    user, headers, body = _metered_question(app, monkeypatch)
    body = {**body, "client_msg_id": "active-stream-question"}
    closed = Mock()

    def chunk(text, finish=None):
        return SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content=text, tool_calls=None), finish_reason=finish)]
        )

    def stream():
        try:
            yield chunk("Before ", "stop" if ending == "final_token" else None)
            _pause(monkeypatch, state)
            if ending == "text":
                yield chunk("AFTER SWITCH", "stop")
            elif ending == "empty":
                yield SimpleNamespace(choices=[])
            if ending != "eof":
                pytest.fail("provider stream was consumed past maintenance")
        finally:
            closed()

    provider = Mock()
    provider.chat.completions.create.return_value = stream()
    monkeypatch.setattr(gol_service, "OpenAI", Mock(return_value=provider))
    monkeypatch.setattr(gol_service, "GolService", _REAL_GOL_SERVICE)
    response = app.test_client().post("/api/gol/chat", json=body, headers=headers)
    assert response.status_code == 200
    if ending == "final_token":
        frames = iter(response.response)
        prefix = [next(frames), next(frames)]  # Usage and the token, before accepting its stop.
        _pause(monkeypatch, state)
        text = b"".join(prefix + list(frames)).decode()
    else:
        text = response.text
    assert '"error": "maintenance"' in text
    assert "Before " in text
    assert "AFTER SWITCH" not in text
    assert "event: done" not in text
    assert '"refunded": true' in text
    closed.assert_called_once()
    execution = GolChatExecution.query.filter_by(client_msg_id=body["client_msg_id"]).one()
    assert execution.status == "failed"
    assert not execution.response_text
    assert GolCreditLedger.query.filter_by(kind="reversal", debit_id=execution.debit_id).count() == 1
    assert balances(user)["free_questions_remaining"] == 2
    monkeypatch.setenv("GOL_MAINTENANCE", "false")
    monkeypatch.setenv("OPENAI_API_KEY", "test-not-a-real-key")
    provider.chat.completions.create.return_value = iter([chunk("Recovered answer", "stop")])
    retry = app.test_client().post("/api/gol/chat", json=body, headers=headers)
    assert "Recovered answer" in retry.text
    assert "event: done" in retry.text
    assert GolChatExecution.query.filter_by(client_msg_id=body["client_msg_id"], attempt=2).one().status == "completed"
    assert GolCreditLedger.query.filter_by(kind="reversal").count() == 1
    assert balances(user)["free_questions_remaining"] == 1


@pytest.mark.parametrize("state", ["switch", "missing"])
@pytest.mark.parametrize("role", ["user", "admin"])
def test_unmetered_active_stream_refuses_completion(app, monkeypatch, state, role):
    user = UserAccount(email="unmetered@example.com", display_name="Test", display_name_lower="test")
    db.session.add(user)
    db.session.commit()
    headers = {"Authorization": f"Bearer {issue_user_token(user.email, role=role)['token']}"}
    closed = Mock()

    def stream():
        try:
            yield SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(content="Before", tool_calls=None),
                        finish_reason=None,
                    )
                ]
            )
            _pause(monkeypatch, state)
            yield SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(content="AFTER SWITCH", tool_calls=None),
                        finish_reason="stop",
                    )
                ]
            )
        finally:
            closed()

    provider = Mock()
    provider.chat.completions.create.return_value = stream()
    monkeypatch.setattr(gol_service, "OpenAI", Mock(return_value=provider))
    response = app.test_client().post("/api/gol/chat", json={"message": "Hello"}, headers=headers)
    assert '"error": "maintenance"' in response.text
    assert "AFTER SWITCH" not in response.text
    assert "event: done" not in response.text
    assert GolChatExecution.query.count() == GolCreditLedger.query.count() == 0
    closed.assert_called_once()


@pytest.mark.parametrize("state", ["switch", "missing"])
@pytest.mark.parametrize("failed_state", ["refunded", "withheld"])
@pytest.mark.parametrize("exhausted", [False, True])
def test_failed_question_retries_during_maintenance_write_nothing(app, monkeypatch, state, failed_state, exhausted):
    user, headers, body = _metered_question(app, monkeypatch)
    execution = GolChatExecution.query.one()
    execution.status = "failed"
    debit = GolCreditLedger.query.filter_by(kind="debit").one()
    if failed_state == "refunded":
        db.session.add(
            GolCreditLedger(
                user_account_id=user.id,
                bucket=debit.bucket,
                kind="reversal",
                delta=1,
                debit_id=debit.id,
                idempotency_key=f"refund:{debit.id}",
                client_msg_id=debit.client_msg_id,
                attempt=debit.attempt,
            )
        )
    else:
        debit.note += ";refund_withheld=true"
    db.session.commit()
    if exhausted:
        monkeypatch.setenv("GOL_FREE_ALLOWANCE", "0")
    _pause(monkeypatch, state)
    before = balances(user)
    counts = (GolCreditLedger.query.count(), GolChatExecution.query.count(), ProductEvent.query.count())
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().split()[0].upper() in {"INSERT", "UPDATE", "DELETE", "REPLACE"}:
            statements.append(statement)

    provider = Mock(side_effect=AssertionError("provider construction"))
    monkeypatch.setattr(gol_service, "OpenAI", provider)
    event.listen(db.engine, "before_cursor_execute", capture)
    try:
        for _ in range(3):
            response = app.test_client().post("/api/gol/chat", json=body, headers=headers)
            assert response.status_code == 503
            assert response.json == maintenance_payload()
            assert response.headers["Retry-After"] == "60"
        assert statements == []
    finally:
        event.remove(db.engine, "before_cursor_execute", capture)
    assert (GolCreditLedger.query.count(), GolChatExecution.query.count(), ProductEvent.query.count()) == counts
    assert balances(user) == before
    provider.assert_not_called()


@pytest.fixture
def app(monkeypatch):
    monkeypatch.delenv("GOL_MAINTENANCE", raising=False)
    monkeypatch.setenv("GOL_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-not-a-real-key")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("BILLING_ENABLED", "false")
    test_app = Flask(__name__)
    test_app.config.update(
        TESTING=True,
        SECRET_KEY="maintenance-test",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        RATELIMIT_ENABLED=False,
    )
    db.init_app(test_app)
    limiter.init_app(test_app)
    test_app.register_blueprint(gol.gol_bp, url_prefix="/api")
    with test_app.app_context():
        db.create_all()
        yield test_app
        db.session.remove()
        db.drop_all()


@pytest.mark.parametrize("value", ["1", "true", " YES ", "On", "false", "0", "off", "garbage", "", None])
def test_maintenance_switch_values(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("GOL_MAINTENANCE", raising=False)
    else:
        monkeypatch.setenv("GOL_MAINTENANCE", value)
    assert maintenance_enabled() is (value in {"1", "true", " YES ", "On"})


@pytest.mark.parametrize("billing", ["true", "false"])
@pytest.mark.parametrize("role", ["user", "admin"])
@pytest.mark.parametrize("state", ["switch", "openai", "openrouter", "blank"])
def test_maintenance_preserves_account_and_skips_work(app, monkeypatch, billing, role, state):
    monkeypatch.setenv("BILLING_ENABLED", billing)
    if state == "switch":
        monkeypatch.setenv("GOL_MAINTENANCE", "true")
    elif state == "blank":
        monkeypatch.setenv("OPENAI_API_KEY", "  ")
    elif state == "openrouter":
        monkeypatch.setenv("GOL_PROVIDER", "openrouter")
    else:
        monkeypatch.delenv("OPENAI_API_KEY")
    user = UserAccount(email="maintenance@example.com", display_name="Test User", display_name_lower="test user")
    db.session.add(user)
    db.session.commit()
    before = balances(user)
    headers = {"Authorization": f"Bearer {issue_user_token(user.email, role=role)['token']}"}
    provider = Mock(side_effect=AssertionError("provider construction"))
    service = Mock(side_effect=AssertionError("service construction"))
    reserve = Mock(side_effect=AssertionError("reservation"))
    monkeypatch.setattr(gol_service, "OpenAI", provider)
    monkeypatch.setattr(gol_service, "GolService", service)
    monkeypatch.setattr(gol, "reserve_question", reserve)
    response = app.test_client().post(
        "/api/gol/chat", json={"message": "Hello", "client_msg_id": "maintenance-1"}, headers=headers
    )
    assert response.status_code == 503
    assert response.json == maintenance_payload()
    assert response.headers["Retry-After"] == "60"
    assert response.headers["Cache-Control"] == "no-store"
    assert balances(user) == before
    assert GolChatExecution.query.count() == 0
    assert GolCreditLedger.query.count() == 0
    provider.assert_not_called()
    service.assert_not_called()
    reserve.assert_not_called()
    suggestions = app.test_client().get("/api/gol/suggestions")
    assert suggestions.status_code == 200
    assert suggestions.json == {"suggestions": [], "maintenance": True, "retry_after": 60, **maintenance_payload()}
    assert suggestions.headers["Retry-After"] == "60"
    assert suggestions.headers["Cache-Control"] == "no-store"
    service.assert_not_called()


@pytest.mark.parametrize("state", ["switch", "missing"])
def test_maintenance_service_and_tool_entry(app, monkeypatch, state):
    if state == "switch":
        monkeypatch.setenv("GOL_MAINTENANCE", "on")
    else:
        monkeypatch.delenv("OPENAI_API_KEY")
    provider = Mock()
    monkeypatch.setattr(gol_service, "OpenAI", provider)
    with pytest.raises(GolMaintenance, match="under maintenance"):
        gol_service.GolService()
    provider.assert_not_called()
    service = gol_service.GolService.__new__(gol_service.GolService)
    service.df_cache = Mock()
    execute = Mock()
    monkeypatch.setattr(gol_service, "execute_analysis", execute)
    assert service._execute_tool("run_analysis", {"code": "result = 1"}) == {
        "result_type": "error",
        **maintenance_payload(),
    }
    service.df_cache.get_frames.assert_not_called()
    execute.assert_not_called()


def test_switch_off_restores_chat(app, monkeypatch):
    user = UserAccount(
        email="available@example.com", display_name="Available User", display_name_lower="available user"
    )
    db.session.add(user)
    db.session.commit()
    client = Mock()
    client.chat.return_value = iter([{"event": "done", "data": {}}])
    monkeypatch.setattr(gol_service, "GolService", Mock(return_value=client))
    headers = {"Authorization": f"Bearer {issue_user_token(user.email)['token']}"}
    monkeypatch.setenv("GOL_MAINTENANCE", "true")
    assert app.test_client().post("/api/gol/chat", json={"message": "Hello"}, headers=headers).status_code == 503
    monkeypatch.setenv("GOL_MAINTENANCE", "false")
    response = app.test_client().post("/api/gol/chat", json={"message": "Hello"}, headers=headers)
    assert response.status_code == 200
    assert "event: done" in response.text
    client.chat.assert_called_once()


@pytest.mark.parametrize("provider", ["openai", "openrouter"])
def test_selected_provider_controls_availability(app, monkeypatch, provider):
    monkeypatch.setenv("GOL_PROVIDER", provider)
    monkeypatch.setenv("OPENAI_API_KEY", "test-not-a-real-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-not-a-real-key")
    monkeypatch.delenv("OPENAI_API_KEY" if provider == "openrouter" else "OPENROUTER_API_KEY")
    assert assistant_under_maintenance() is False
    constructor = Mock()
    monkeypatch.setattr(gol_service, "OpenAI", constructor)
    gol_service.GolService()
    constructor.assert_called_once()


def test_maintenance_stops_completion_before_provider(app, monkeypatch):
    service = gol_service.GolService.__new__(gol_service.GolService)
    service.client = Mock()
    monkeypatch.setenv("GOL_MAINTENANCE", "true")
    assert list(service._run_completion([])) == [
        {"event": "error", "data": maintenance_payload()},
        {"event": "done", "data": {}},
    ]
    service.client.chat.completions.create.assert_not_called()


def test_maintenance_stops_completion_at_tool_entry(app, monkeypatch):
    service = gol_service.GolService.__new__(gol_service.GolService)
    service.model = "test-model"
    service.df_cache = Mock()
    service.client = Mock()
    call = SimpleNamespace(
        index=0, id="test-call", function=SimpleNamespace(name="run_analysis", arguments='{"code":"result = 1"}')
    )
    delta = SimpleNamespace(content=None, tool_calls=[call])

    def stream():
        monkeypatch.setenv("GOL_MAINTENANCE", "true")
        yield SimpleNamespace(choices=[SimpleNamespace(delta=delta, finish_reason="tool_calls")])

    service.client.chat.completions.create.return_value = stream()
    events = list(service._run_completion([]))
    assert events == [
        {"event": "error", "data": maintenance_payload()},
    ]
    service.df_cache.get_frames.assert_not_called()
    service.client.chat.completions.create.assert_called_once()


def _metered_question(app, monkeypatch):
    monkeypatch.setenv("BILLING_ENABLED", "true")
    user = UserAccount(email="recovery@example.com", display_name="Test User", display_name_lower="test user")
    db.session.add(user)
    db.session.commit()
    headers = {"Authorization": f"Bearer {issue_user_token(user.email)['token']}"}
    body = {"message": "Hello", "client_msg_id": "recovery-question"}
    service = Mock()
    service.chat.side_effect = lambda *args: iter(
        [
            {"event": "token", "data": {"content": "Stored answer"}},
            {"event": "done", "data": {}},
        ]
    )
    monkeypatch.setattr(gol_service, "GolService", Mock(return_value=service))
    response = app.test_client().post("/api/gol/chat", json=body, headers=headers)
    assert response.status_code == 200
    assert "event: done" in response.text
    assert balances(user)["free_questions_remaining"] == 2
    return user, headers, body


def _pause(monkeypatch, state):
    if state == "switch":
        monkeypatch.setenv("GOL_MAINTENANCE", "true")
    else:
        monkeypatch.delenv("OPENAI_API_KEY")


@pytest.mark.parametrize("state", ["switch", "missing"])
@pytest.mark.parametrize("execution_state", ["completed", "live", "stale"])
def test_existing_debit_keeps_replay_inflight_and_refund(app, monkeypatch, state, execution_state):
    user, headers, body = _metered_question(app, monkeypatch)
    execution = GolChatExecution.query.one()
    if execution_state != "completed":
        execution.status = "running"
        execution.lease_started_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(
            minutes=6 if execution_state == "stale" else 0
        )
        db.session.commit()
    _pause(monkeypatch, state)
    provider = Mock(side_effect=AssertionError("provider construction"))
    monkeypatch.setattr(gol_service, "OpenAI", provider)
    response = app.test_client().post("/api/gol/chat", json=body, headers=headers)
    if execution_state == "completed":
        assert response.status_code == 200
        assert 'event: replace\ndata: {"content": "Stored answer"}' in response.text
        assert "event: done" in response.text
        assert GolChatExecution.query.one().status == "completed"
    elif execution_state == "live":
        assert response.status_code == 409
        assert response.json == {"error": "in_flight"}
        assert GolChatExecution.query.one().status == "running"
    else:
        assert response.status_code == 503
        assert response.json == maintenance_payload()
        assert GolChatExecution.query.one().status == "failed"
        assert GolChatExecution.query.one().lease_generation == 2
    assert GolCreditLedger.query.filter_by(kind="debit").count() == 1
    assert GolCreditLedger.query.filter_by(kind="reversal").count() == (execution_state == "stale")
    assert balances(user)["free_questions_remaining"] == (3 if execution_state == "stale" else 2)
    provider.assert_not_called()


@pytest.mark.parametrize(
    "body", [None, {}, {"client_msg_id": "short"}, {"message": "New", "client_msg_id": "fresh-question"}]
)
def test_new_or_foreign_question_has_zero_writes(app, monkeypatch, body):
    user, _, _ = _metered_question(app, monkeypatch)
    other = UserAccount(email="other@example.com", display_name="Other", display_name_lower="other")
    db.session.add(other)
    db.session.commit()
    headers = {"Authorization": f"Bearer {issue_user_token(other.email)['token']}"}
    monkeypatch.setenv("GOL_MAINTENANCE", "true")
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().split()[0].upper() in {"INSERT", "UPDATE", "DELETE", "REPLACE"}:
            statements.append(statement)

    event.listen(db.engine, "before_cursor_execute", capture)
    try:
        for request_body in [body, {"message": "Hello", "client_msg_id": "recovery-question"}]:
            response = app.test_client().post("/api/gol/chat", json=request_body, headers=headers)
            assert response.status_code == 503
            assert response.json == maintenance_payload()
        assert statements == []
    finally:
        event.remove(db.engine, "before_cursor_execute", capture)
    assert GolChatExecution.query.count() == 1
    assert GolCreditLedger.query.count() == 1
    assert balances(user)["free_questions_remaining"] == 2
    assert balances(other)["free_questions_remaining"] == 3


@pytest.mark.parametrize("boundary", ["post_reservation", "mid_stream"])
@pytest.mark.parametrize("state", ["switch", "missing"])
def test_operational_control_after_debit_refunds_and_allows_same_id(app, monkeypatch, boundary, state):
    user, headers, body = _metered_question(app, monkeypatch)
    body = {**body, "client_msg_id": "new-interrupted-question"}
    if boundary == "post_reservation":
        original_reserve = gol.reserve_question

        def reserve(*args, **kwargs):
            result = original_reserve(*args, **kwargs)
            _pause(monkeypatch, state)
            return result

        monkeypatch.setattr(gol, "reserve_question", reserve)
    else:
        # Use the real completion entry to produce the maintenance event.
        service = _REAL_GOL_SERVICE.__new__(_REAL_GOL_SERVICE)

        service.client = Mock()

        def chat(*args):
            yield {"event": "token", "data": {"content": "Partial answer"}}
            _pause(monkeypatch, state)
            yield from service._run_completion([])

        monkeypatch.setattr(gol_service, "GolService", Mock(return_value=SimpleNamespace(chat=chat)))
    response = app.test_client().post("/api/gol/chat", json=body, headers=headers)
    if boundary == "post_reservation":
        assert response.status_code == 503
        assert response.json == maintenance_payload()
    else:
        assert response.status_code == 200
        assert '"error": "maintenance"' in response.text
        assert '"refunded": true' in response.text
        assert "Partial answer" in response.text
        assert "event: done" not in response.text
        service.client.chat.completions.create.assert_not_called()
    assert balances(user)["free_questions_remaining"] == 2
    assert GolCreditLedger.query.filter_by(kind="reversal").count() == 1
    assert GolChatExecution.query.filter_by(client_msg_id=body["client_msg_id"]).one().status == "failed"
    monkeypatch.setenv("GOL_MAINTENANCE", "false")
    monkeypatch.setenv("OPENAI_API_KEY", "test-not-a-real-key")
    if boundary == "post_reservation":
        monkeypatch.setattr(gol, "reserve_question", original_reserve)
    healthy = Mock()
    healthy.chat.return_value = iter([{"event": "done", "data": {}}])
    monkeypatch.setattr(gol_service, "GolService", Mock(return_value=healthy))
    retry = app.test_client().post("/api/gol/chat", json=body, headers=headers)
    assert retry.status_code == 200
    assert "event: done" in retry.text
    assert balances(user)["free_questions_remaining"] == 1
    assert GolChatExecution.query.filter_by(client_msg_id=body["client_msg_id"], attempt=2).one().status == "completed"
