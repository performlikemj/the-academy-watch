"""API-Football transfer payload persistence wiring regressions."""

import threading
from datetime import timedelta

import sqlalchemy.orm
from src import api_football_client as api_module
from src.api_football_client import APIFootballClient


def _block(player_id=123):
    transfer = {
        "date": "2024-07-01",
        "type": "Free Transfer",
        "teams": {
            "out": {"id": 49, "name": "Chelsea"},
            "in": {"id": 34, "name": "Newcastle"},
        },
    }
    return {"player": {"id": player_id, "name": "Player"}, "transfers": [transfer]}


def test_team_and_profile_transfer_paths_use_payload_adapter(monkeypatch):
    calls = []
    monkeypatch.setattr(
        api_module,
        "_record_transfer_payload",
        lambda blocks, **kwargs: calls.append((blocks, kwargs)),
    )

    blocks = [_block()]
    client = APIFootballClient.__new__(APIFootballClient)
    client.mode = "direct"
    client.current_season_start_year = 2025
    client._player_profile_cache = {}

    client._make_request = lambda endpoint, params: {"response": blocks}
    assert client.get_team_transfers(49) is blocks
    assert calls == [(blocks, {})]

    calls.clear()

    def profile_request(endpoint, params):
        if endpoint in {"players", "players/seasons"}:
            return {"response": []}
        assert endpoint == "transfers"
        return {"response": blocks}

    client._make_request = profile_request
    profile = client.get_player_by_id(123, season=2025)

    assert profile["player"]["name"] == "Player"
    assert calls == [(blocks, {"fallback_player_api_id": 123})]


def test_player_transfer_path_records_live_and_memory_cached_payloads(monkeypatch):
    calls = []
    monkeypatch.setattr(
        api_module,
        "_record_transfer_payload",
        lambda blocks, **kwargs: calls.append((blocks, kwargs)),
    )

    blocks = [_block()]
    client = APIFootballClient.__new__(APIFootballClient)
    client.mode = "direct"
    client.api_key = "test-key"
    client._transfer_cache = {}
    client._transfer_cache_ttl = timedelta(hours=24)
    client._make_request = lambda endpoint, params: {"response": blocks}

    assert client.get_player_transfers(123) is blocks
    assert calls == [(blocks, {"fallback_player_api_id": 123})]

    # Re-observing the same response through the in-process API cache is
    # intentional: the natural-key upsert keeps one row and advances last_seen.
    calls.clear()
    assert client.get_player_transfers(123) is blocks
    assert calls == [(blocks, {"fallback_player_api_id": 123})]


def test_stub_and_sample_fallbacks_are_never_persisted(monkeypatch):
    calls = []
    monkeypatch.setattr(
        api_module,
        "_record_transfer_payload",
        lambda blocks, **kwargs: calls.append((blocks, kwargs)),
    )

    sample = [_block()]
    client = APIFootballClient.__new__(APIFootballClient)
    client.mode = "stub"
    client.api_key = None
    client._transfer_cache = {}
    client._transfer_cache_ttl = timedelta(hours=24)
    client._get_sample_transfers = lambda **kwargs: sample

    assert client.get_player_transfers(123) is sample
    assert calls == []

    # Direct mode also returns sample data when no API key exists, and after a
    # failed live request. Neither fallback is provider evidence.
    client.mode = "direct"
    assert client.get_player_transfers(123) is sample
    assert calls == []

    client.api_key = "test-key"
    client._make_request = lambda endpoint, params: (_ for _ in ()).throw(RuntimeError("fetch failed"))
    assert client.get_player_transfers(123) is sample
    assert calls == []


def test_batch_player_fetch_persists_only_on_context_owning_thread(app, monkeypatch):
    from src.services import transfer_events as transfer_events_module

    main_thread_id = threading.get_ident()
    recorder_calls = []

    class FakeSession:
        def __init__(self):
            self.commits = 0
            self.rollbacks = 0
            self.closed = False

        def commit(self):
            self.commits += 1

        def rollback(self):
            self.rollbacks += 1

        def close(self):
            self.closed = True

    sessions = []

    def make_session(*, bind):
        assert bind is not None
        session = FakeSession()
        sessions.append(session)
        return session

    def record(player_api_id, transfers, session, *, observed_at=None):
        recorder_calls.append((threading.get_ident(), player_api_id, transfers, session, observed_at))
        return len(transfers)

    monkeypatch.setattr(sqlalchemy.orm, "Session", make_session)
    monkeypatch.setattr(transfer_events_module, "record_transfer_events", record)

    blocks = [_block()]
    client = APIFootballClient.__new__(APIFootballClient)
    client.mode = "direct"
    client.api_key = "test-key"
    client._transfer_cache = {}
    client._transfer_cache_ttl = timedelta(hours=24)
    client._make_request = lambda endpoint, params: {"response": blocks}

    result = client.batch_get_player_transfers([123], max_workers=1, rate_limit_delay=0)

    assert result[123] is blocks
    assert len(recorder_calls) == 1
    thread_id, player_api_id, transfers, session, observed_at = recorder_calls[0]
    assert thread_id == main_thread_id
    assert player_api_id == 123
    assert transfers is blocks[0]["transfers"]
    assert observed_at is not None
    assert session is sessions[0]
    assert sessions[0].commits == 1
    assert sessions[0].rollbacks == 0
    assert sessions[0].closed is True


def test_transfer_persistence_failure_is_non_fatal(app, monkeypatch):
    from src.services import transfer_events as transfer_events_module

    class FailingSession:
        def __init__(self):
            self.rolled_back = False
            self.closed = False

        def commit(self):
            raise RuntimeError("player_transfer_events is not deployed")

        def rollback(self):
            self.rolled_back = True

        def close(self):
            self.closed = True

    session = FailingSession()
    monkeypatch.setattr(sqlalchemy.orm, "Session", lambda *, bind: session)
    monkeypatch.setattr(transfer_events_module, "record_transfer_events", lambda *args, **kwargs: 1)

    api_module._record_transfer_payload([_block()])

    assert session.rolled_back is True
    assert session.closed is True


def test_transfer_persistence_cleanup_failures_are_non_fatal(app, monkeypatch):
    from src.services import transfer_events as transfer_events_module

    class BrokenCleanupSession:
        def commit(self):
            raise RuntimeError("write failed")

        def rollback(self):
            raise RuntimeError("rollback failed")

        def close(self):
            raise RuntimeError("close failed")

    monkeypatch.setattr(sqlalchemy.orm, "Session", lambda *, bind: BrokenCleanupSession())
    monkeypatch.setattr(transfer_events_module, "record_transfer_events", lambda *args, **kwargs: 1)

    api_module._record_transfer_payload([_block()])
