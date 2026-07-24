"""Hermetic request-budget and journey propagation regressions."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
import requests
from src import api_football_client as api_module
from src.api_football_client import (
    APICallBudget,
    APICallBudgetExceeded,
    APIFootballClient,
)
from src.models.api_cache import APICache
from src.models.journey import PlayerJourney
from src.services.journey_sync import JourneySyncService


class _Response:
    status_code = 200
    text = '{"response": []}'

    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _direct_client(budget: APICallBudget) -> APIFootballClient:
    client = APIFootballClient.__new__(APIFootballClient)
    client.mode = "direct"
    client.use_stub = False
    client.api_key = "test-key"
    client.base_url = "https://example.test"
    client.headers = {"x-apisports-key": "test-key"}
    client.call_budget = budget
    client._transfer_cache = {}
    client._transfer_cache_ttl = timedelta(hours=24)
    return client


def test_db_cache_hit_does_not_consume_call_budget(app, monkeypatch):
    params = {"team": 49}
    cached = {"results": 1, "response": [{"player": {"id": 1}, "transfers": []}]}
    APICache.set_cached("transfers", params, cached, ttl_seconds=3600)
    budget = APICallBudget(1)
    client = _direct_client(budget)

    monkeypatch.setattr(
        api_module.requests,
        "get",
        lambda *args, **kwargs: pytest.fail("cache hit attempted live HTTP"),
    )

    assert client._make_request("transfers", params) == cached
    assert budget.spent == 0
    assert budget.remaining == 1
    assert budget.exhausted is False


def test_live_failure_still_consumes_call_budget(app, monkeypatch):
    budget = APICallBudget(1)
    client = _direct_client(budget)

    def fail_request(*args, **kwargs):
        raise requests.exceptions.Timeout("provider timeout")

    monkeypatch.setattr(api_module.requests, "get", fail_request)

    with pytest.raises(RuntimeError, match="API request failed"):
        client._make_request("status")

    assert budget.spent == 1
    assert budget.remaining == 0
    assert budget.exhausted is True


def test_call_budget_hard_caps_live_requests(app, monkeypatch):
    budget = APICallBudget(2)
    client = _direct_client(budget)
    http_calls = []

    def successful_request(*args, **kwargs):
        http_calls.append((args, kwargs))
        return _Response({"results": 0, "response": []})

    monkeypatch.setattr(api_module.requests, "get", successful_request)

    client._make_request("status")
    client._make_request("status")
    with pytest.raises(APICallBudgetExceeded, match=r"2/2"):
        client._make_request("status")

    assert len(http_calls) == 2
    assert budget.spent == 2
    assert budget.exhausted is True


def test_call_budget_can_resume_already_exhausted_above_current_limit():
    budget = APICallBudget(2, initial_spent=3)

    assert budget.limit == 2
    assert budget.spent == 3
    assert budget.remaining == 0
    assert budget.exhausted is True
    with pytest.raises(APICallBudgetExceeded, match=r"3/2"):
        budget.claim("transfers")


def test_claim_callback_failure_prevents_count_and_live_request(app, monkeypatch):
    persisted = []
    http_calls = []

    def fail_persistence(next_spent):
        persisted.append(next_spent)
        raise RuntimeError("checkpoint unavailable")

    budget = APICallBudget(2, on_claim=fail_persistence)
    client = _direct_client(budget)
    monkeypatch.setattr(
        api_module.requests,
        "get",
        lambda *args, **kwargs: http_calls.append((args, kwargs)),
    )

    with pytest.raises(RuntimeError, match="Failed to reserve API-Football call budget"):
        client._make_request("status")

    assert persisted == [1]
    assert budget.spent == 0
    assert budget.remaining == 2
    assert http_calls == []


def test_non_runtime_claim_callback_failure_is_fail_closed(app, monkeypatch):
    http_calls = []

    def fail_persistence(_next_spent):
        raise ValueError("database checkpoint rejected")

    budget = APICallBudget(2, on_claim=fail_persistence)
    client = _direct_client(budget)
    monkeypatch.setattr(
        api_module.requests,
        "get",
        lambda *args, **kwargs: http_calls.append((args, kwargs)),
    )

    with pytest.raises(RuntimeError, match="Failed to reserve API-Football call budget"):
        client._make_request("status")

    assert budget.spent == 0
    assert http_calls == []


def test_claim_callback_succeeds_before_count_advances():
    observed = []
    budget = None

    def persist(next_spent):
        observed.append((next_spent, budget._spent))

    budget = APICallBudget(2, initial_spent=1, on_claim=persist)

    assert budget.claim("transfers") == 2
    assert observed == [(2, 1)]
    assert budget.spent == 2
    assert budget.remaining == 0


def test_call_budget_claim_is_thread_safe():
    budget = APICallBudget(3)

    def claim_once(_):
        try:
            budget.claim("transfers")
            return True
        except APICallBudgetExceeded:
            return False

    with ThreadPoolExecutor(max_workers=10) as executor:
        claims = list(executor.map(claim_once, range(20)))

    assert claims.count(True) == 3
    assert claims.count(False) == 17
    assert budget.spent == 3


def test_force_refresh_bypasses_db_cache_and_consumes_budget(app, monkeypatch):
    params = {"team": 49}
    cached = {"results": 0, "response": []}
    fresh = {
        "results": 1,
        "response": [{"player": {"id": 123}, "transfers": []}],
    }
    APICache.set_cached("transfers", params, cached, ttl_seconds=3600)
    budget = APICallBudget(1)
    client = _direct_client(budget)
    monkeypatch.setattr(api_module, "_record_transfer_payload", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        api_module.requests,
        "get",
        lambda *args, **kwargs: _Response(fresh),
    )

    assert client.get_team_transfers(49, force_refresh=False, raise_on_error=True) == []
    assert budget.spent == 0
    assert client.get_team_transfers(49, force_refresh=True, raise_on_error=True) == fresh["response"]
    assert budget.spent == 1


def test_team_transfer_scan_can_defer_evidence_to_its_own_transaction(
    app,
    monkeypatch,
):
    fresh = {
        "results": 1,
        "response": [{"player": {"id": 123}, "transfers": []}],
    }
    persisted = []
    budget = APICallBudget(1)
    client = _direct_client(budget)
    monkeypatch.setattr(
        api_module,
        "_record_transfer_payload",
        lambda *args, **kwargs: persisted.append((args, kwargs)),
    )
    monkeypatch.setattr(
        api_module.requests,
        "get",
        lambda *args, **kwargs: _Response(fresh),
    )

    assert (
        client.get_team_transfers(
            49,
            force_refresh=True,
            raise_on_error=True,
            persist_events=False,
        )
        == fresh["response"]
    )
    assert budget.spent == 1
    assert persisted == []


class _JourneyBudgetAPI:
    def __init__(self, stage):
        self.stage = stage

    def _make_request(self, endpoint, params):
        if endpoint == "players/seasons":
            if self.stage == "seasons":
                raise APICallBudgetExceeded("seasons cap")
            return {"response": [2025]}
        if endpoint == "players":
            if self.stage == "season_data":
                raise APICallBudgetExceeded("season data cap")
            raise AssertionError((endpoint, params))
        raise AssertionError((endpoint, params))

    def get_player_transfers(self, player_id):
        if self.stage == "transfers":
            raise APICallBudgetExceeded("transfers cap")
        return []


@pytest.mark.parametrize("stage", ["seasons", "transfers", "season_data"])
def test_journey_sync_rolls_back_and_propagates_budget_sentinel(app, stage):
    service = JourneySyncService(api_client=_JourneyBudgetAPI(stage))

    with pytest.raises(APICallBudgetExceeded):
        service.sync_player(7001, force_full=True)

    assert service.last_sync_used_transfer_evidence is False
    assert PlayerJourney.query.filter_by(player_api_id=7001).count() == 0


class _PrefetchedJourneyAPI:
    def _make_request(self, endpoint, params):
        if endpoint == "players/seasons":
            return {"response": [2025]}
        if endpoint == "players":
            return {
                "response": [
                    {
                        "player": {
                            "id": 7002,
                            "name": "Budget Player",
                            "birth": {"date": "2000-01-01", "country": "Test"},
                            "nationality": "Test",
                        },
                        "statistics": [
                            {
                                "team": {"id": 100, "name": "Test Club"},
                                "league": {"id": 200, "name": "Test League", "country": "Test"},
                                "games": {
                                    "appearences": 10,
                                    "minutes": 900,
                                    "position": "Midfielder",
                                },
                                "goals": {"total": 1, "assists": 2},
                            }
                        ],
                    }
                ]
            }
        raise AssertionError((endpoint, params))

    def get_player_transfers(self, player_id):
        raise AssertionError("prefetched transfer evidence was ignored")


def test_prefetched_transfer_evidence_marks_completed_sync_as_fed(app):
    service = JourneySyncService(api_client=_PrefetchedJourneyAPI())
    service._auto_geocode_clubs = lambda journey: None

    journey = service.sync_player(
        7002,
        force_full=True,
        prefetched_transfers=[],
    )

    assert journey is not None
    assert journey.sync_error is None
    assert service.last_sync_used_transfer_evidence is True
