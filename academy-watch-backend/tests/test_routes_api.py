import importlib
import sys


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
