"""Maintenance switch for the assistant."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import Flask
from src.auth import issue_user_token
from src.extensions import limiter
from src.models.gol_credits import GolChatExecution, GolCreditLedger
from src.models.league import UserAccount, db
from src.routes import gol
from src.services import gol_service
from src.services.gol_availability import (
    GolMaintenance,
    assistant_under_maintenance,
    maintenance_enabled,
    maintenance_payload,
)
from src.services.gol_credits import balances


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
    assert suggestions.json == {"suggestions": [], "maintenance": True, **maintenance_payload()}
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
    assert events[-2:] == [
        {"event": "error", "data": maintenance_payload()},
        {"event": "done", "data": {}},
    ]
    service.df_cache.get_frames.assert_not_called()
    service.client.chat.completions.create.assert_called_once()
