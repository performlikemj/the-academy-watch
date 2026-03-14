import importlib


def test_is_placeholder_team_name_detects_numeric_labels():
    api = importlib.import_module('src.routes.api')

    assert api._is_placeholder_team_name('Team 123') is True
    assert api._is_placeholder_team_name('team 45') is True
    assert api._is_placeholder_team_name('') is True
    assert api._is_placeholder_team_name(None) is True
    assert api._is_placeholder_team_name('Real Madrid') is False


def test_update_team_name_if_missing_uses_api_when_placeholder(monkeypatch):
    api = importlib.import_module('src.routes.api')

    class DummyTeam:
        def __init__(self):
            self.name = 'Team 999'
            self.team_id = 999

    dummy_team = DummyTeam()

    calls = {}

    def fake_get_team_by_id(team_id, season):
        calls['team_id'] = team_id
        calls['season'] = season
        return {'team': {'name': 'Brighton Hove Albion'}}

    monkeypatch.setattr(api.api_client, 'get_team_by_id', fake_get_team_by_id)

    result = api._update_team_name_if_missing(dummy_team, season=2025, dry_run=False)

    assert result['status'] == 'updated'
    assert dummy_team.name == 'Brighton Hove Albion'
    assert calls == {'team_id': 999, 'season': 2025}

