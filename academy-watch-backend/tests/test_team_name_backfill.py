import importlib


def test_is_placeholder_team_name_detects_numeric_labels():
    api = importlib.import_module("src.utils.team_resolver")

    assert api.is_placeholder_team_name("Team 123") is True
    assert api.is_placeholder_team_name("team 45") is True
    assert api.is_placeholder_team_name("") is True
    assert api.is_placeholder_team_name(None) is True
    assert api.is_placeholder_team_name("Real Madrid") is False


def test_update_team_name_if_missing_uses_api_when_placeholder(monkeypatch):
    api = importlib.import_module("src.utils.team_resolver")

    class DummyTeam:
        def __init__(self):
            self.name = "Team 999"
            self.team_id = 999

    dummy_team = DummyTeam()

    calls = {}

    def fake_resolve_team_name_and_logo(team_id, season):
        calls["team_id"] = team_id
        calls["season"] = season
        return "Brighton Hove Albion", None

    monkeypatch.setattr(api, "resolve_team_name_and_logo", fake_resolve_team_name_and_logo)

    result = api.update_team_name_if_missing(dummy_team, season=2025, dry_run=False)

    assert result["status"] == "updated"
    assert dummy_team.name == "Brighton Hove Albion"
    assert calls == {"team_id": 999, "season": 2025}
