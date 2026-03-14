from src.services.youth_competition_resolver import (
    get_default_youth_league_map,
    resolve_team_name,
    resolve_youth_leagues,
    resolve_youth_team_for_parent,
)


class _MockAPIClient:
    def __init__(self, responses=None, teams=None, team_data=None):
        self.responses = responses or {}
        self.teams = teams or {}
        self.team_data = team_data or {}

    def _make_request(self, endpoint, params=None):
        key = (endpoint, tuple(sorted((params or {}).items())))
        return self.responses.get(key, {"response": []})

    def get_league_teams(self, league_id, season):
        return self.teams.get((league_id, season), [])

    def get_team_by_id(self, team_id):
        return self.team_data.get(team_id, {})


def _req_key(endpoint, params):
    return endpoint, tuple(sorted(params.items()))


def test_default_youth_league_map_uses_current_ids():
    league_map = get_default_youth_league_map()
    assert league_map[702] == "Premier League 2 Division One"
    assert league_map[695] == "U18 Premier League - North"
    assert league_map[696] == "U18 Premier League - South"
    assert league_map[987] == "U18 Premier League - Championship"
    assert league_map[1068] == "FA Youth Cup"
    assert league_map[14] == "UEFA Youth League"


def test_resolve_youth_leagues_falls_back_without_client():
    resolved = resolve_youth_leagues(api_client=None)
    ids = [entry["league_id"] for entry in resolved]
    assert 702 in ids
    assert 695 in ids
    assert 696 in ids
    assert 1068 in ids
    assert 14 in ids
    assert all(entry["source"] == "static_fallback" for entry in resolved)


def test_resolve_youth_leagues_prefers_dynamic_match():
    api = _MockAPIClient(
        responses={
            _req_key("leagues", {"search": "Premier League 2"}): {
                "response": [
                    {
                        "league": {"id": 9999, "name": "Premier League 2 Division One", "type": "League"},
                        "country": {"name": "England"},
                    }
                ]
            }
        }
    )

    resolved = resolve_youth_leagues(api_client=api)
    pl2 = next(r for r in resolved if r["key"] == "pl2_div1")
    assert pl2["league_id"] == 9999
    assert pl2["source"] == "dynamic"


def test_resolve_youth_team_for_parent_matches_youth_variant():
    api = _MockAPIClient(
        teams={
            (702, 2024): [
                {"team": {"id": 7198, "name": "Manchester United U21"}},
                {"team": {"id": 7202, "name": "Tottenham Hotspur U21"}},
            ]
        }
    )
    cache = {}

    team_id, team_name = resolve_youth_team_for_parent(
        api_client=api,
        league_id=702,
        season=2024,
        parent_team_name="Manchester United",
        teams_cache=cache,
    )
    assert team_id == 7198
    assert team_name == "Manchester United U21"

    spurs_id, spurs_name = resolve_youth_team_for_parent(
        api_client=api,
        league_id=702,
        season=2024,
        parent_team_name="Tottenham",
        teams_cache=cache,
    )
    assert spurs_id == 7202
    assert spurs_name == "Tottenham Hotspur U21"


def test_resolve_team_name_uses_api_then_fallback():
    api = _MockAPIClient(
        team_data={
            33: {"team": {"id": 33, "name": "Manchester United"}},
        }
    )
    assert resolve_team_name(api, 33) == "Manchester United"
    assert resolve_team_name(api, 47, fallback_name="Tottenham") == "Tottenham"
