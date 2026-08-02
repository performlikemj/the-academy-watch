import importlib
import sys

import pytest


def test_api_client_constructor_handshake_failure_is_non_fatal(monkeypatch):
    from src.api_football_client import APIFootballClient

    monkeypatch.delenv("SKIP_API_HANDSHAKE", raising=False)
    monkeypatch.setenv("API_USE_STUB_DATA", "false")

    quota_error = "API-Football daily request quota exhausted"

    def raise_quota_error(_self):
        raise RuntimeError(quota_error)

    monkeypatch.setattr(APIFootballClient, "_check_quota_limit", raise_quota_error)

    api_client = APIFootballClient(api_key="dummy-key")

    assert api_client.handshake_failed is True
    with pytest.raises(RuntimeError, match=quota_error):
        api_client.get_player_profile(123)
    with pytest.raises(RuntimeError, match=quota_error):
        api_client.handshake()


def test_overview_uses_local_season_when_client_handshake_fails(client, monkeypatch):
    from src.models.league import Team, db
    from src.models.tracked_player import TrackedPlayer
    from src.routes import api as api_module
    from src.utils.academy_window import current_stats_season

    season = current_stats_season()
    team = Team(team_id=33, name="Manchester United", country="England", season=season, is_active=True)
    db.session.add(team)
    db.session.flush()
    db.session.add(
        TrackedPlayer(
            player_api_id=1001,
            player_name="Quota Safe Player",
            team_id=team.id,
            status="on_loan",
            is_active=True,
        )
    )
    db.session.commit()

    construction_attempts = []

    class HandshakeFailingClient:
        def __init__(self):
            construction_attempts.append(None)
            self.handshake()

        def handshake(self):
            raise RuntimeError("API-Football daily request quota exhausted")

    monkeypatch.setattr(
        api_module,
        "api_client",
        api_module.LazyAPIFootballClient(HandshakeFailingClient),
    )

    response = client.get("/api/stats/overview")

    assert response.status_code == 200
    assert response.get_json() == {
        "total_teams": 1,
        "european_leagues": 0,
        "total_active_loans": 1,
        "season_loans": 1,
        "early_terminations": 0,
        "teams_with_loans": 1,
        "total_subscriptions": 0,
        "total_newsletters": 0,
        "current_season": f"{season}-{season + 1}",
    }
    assert construction_attempts == [None]


def test_api_client_initialized_lazily(monkeypatch):
    """The routes module should not hit the football API during import."""
    monkeypatch.delenv("SKIP_API_HANDSHAKE", raising=False)
    monkeypatch.setenv("API_FOOTBALL_KEY", "dummy-key")

    handshake_calls = []

    def fake_handshake(self):
        handshake_calls.append(None)
        return True

    monkeypatch.setattr(
        "src.api_football_client.APIFootballClient.handshake",
        fake_handshake,
        raising=True,
    )

    def fake_get_european_leagues(self, season_start_year: int):
        return {"season": season_start_year}

    monkeypatch.setattr(
        "src.api_football_client.APIFootballClient.get_european_leagues",
        fake_get_european_leagues,
        raising=True,
    )

    try:
        sys.modules.pop("src.routes.api", None)
        api_module = importlib.import_module("src.routes.api")

        assert handshake_calls == []

        response = api_module.api_client.get_european_leagues(2024)

        assert handshake_calls == [None]
        assert response == {"season": 2024}
    finally:
        sys.modules.pop("src.routes.api", None)
