"""Fixture-driven regressions for the transfer-window cadence job."""

import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest
from src.api_football_client import APICallBudget
from src.jobs import run_transfer_window_heal as cadence
from src.models.league import AdminSetting, League, Team, db
from src.models.tracked_player import TrackedPlayer
from src.models.transfer_event import PlayerTransferEvent
from src.services.transfer_events import record_transfer_events


def _league(league_api_id: int, name: str = "Test League") -> League:
    league = League(
        league_id=league_api_id,
        name=name,
        country="Test Country",
        season=2025,
    )
    db.session.add(league)
    db.session.flush()
    return league


def _team(
    api_team_id: int,
    name: str,
    *,
    season: int = 2025,
    league: League | None = None,
) -> Team:
    team = Team(
        team_id=api_team_id,
        name=name,
        country="Test Country",
        season=season,
        league_id=league.id if league else None,
        is_active=True,
        is_tracked=True,
    )
    db.session.add(team)
    db.session.flush()
    return team


def _tracked(
    player_api_id: int,
    team: Team,
    *,
    status: str = "academy",
    current_club_api_id: int | None = None,
    current_club_name: str | None = None,
) -> TrackedPlayer:
    player = TrackedPlayer(
        player_api_id=player_api_id,
        player_name=f"Player {player_api_id}",
        team_id=team.id,
        status=status,
        current_club_api_id=current_club_api_id,
        current_club_name=current_club_name,
        data_source="test",
        is_active=True,
    )
    db.session.add(player)
    db.session.flush()
    return player


def _transfer(
    transfer_date: str,
    transfer_type: str | None,
    out_id: int | None,
    out_name: str | None,
    in_id: int | None,
    in_name: str | None,
) -> dict:
    return {
        "date": transfer_date,
        "type": transfer_type,
        "teams": {
            "out": {"id": out_id, "name": out_name},
            "in": {"id": in_id, "name": in_name},
        },
    }


def _block(player_api_id: int, *transfers: dict) -> dict:
    return {
        "player": {"id": player_api_id, "name": f"Player {player_api_id}"},
        "transfers": list(transfers),
    }


def _delta_state(*player_api_ids: int) -> dict:
    return {
        "version": 1,
        "players": {
            str(player_api_id): {
                "player_api_id": player_api_id,
                "flagged_at": f"2026-07-{index + 1:02d}T00:00:00+00:00",
                "latest_transfer_date": f"2026-07-{index + 10:02d}",
                "reasons": ["fixture"],
            }
            for index, player_api_id in enumerate(player_api_ids)
        },
    }


class _PersistingTeamClient:
    """Adversarial fetch that persists despite cadence requesting suppression."""

    def __init__(
        self,
        budget: APICallBudget,
        responses: dict[int, list[dict]],
        observed_at: datetime,
    ):
        self.call_budget = budget
        self.responses = responses
        self.observed_at = observed_at
        self.team_calls = []

    def get_team_transfers(
        self,
        team_id: int,
        *,
        force_refresh: bool,
        raise_on_error: bool,
        persist_events: bool,
    ) -> list[dict]:
        assert force_refresh is True
        assert raise_on_error is True
        assert persist_events is False
        self.call_budget.claim("transfers")
        self.team_calls.append(team_id)
        response = deepcopy(self.responses[team_id])
        for block in response:
            record_transfer_events(
                block["player"]["id"],
                block["transfers"],
                db.session,
                observed_at=self.observed_at,
            )
        db.session.commit()
        return response


class _NonPersistingTeamClient:
    """Provider fixture used to prove cadence owns its evidence transaction."""

    def __init__(self, budget: APICallBudget, responses: dict[int, list[dict]]):
        self.call_budget = budget
        self.responses = responses
        self.team_calls = []

    def get_team_transfers(
        self,
        team_id: int,
        *,
        force_refresh: bool,
        raise_on_error: bool,
        persist_events: bool,
    ) -> list[dict]:
        assert force_refresh is True
        assert raise_on_error is True
        assert persist_events is False
        self.call_budget.claim("transfers")
        self.team_calls.append(team_id)
        return deepcopy(self.responses[team_id])


def test_delta_diff_uses_pre_persist_snapshot_and_scan_only_preserves_status(
    app,
    monkeypatch,
):
    league = _league(39, "Premier League")
    current_team = _team(49, "Chelsea", season=2025, league=league)
    historical_team = _team(49, "Chelsea", season=2024, league=league)
    first = _tracked(
        7001,
        current_team,
        status="first_team",
        current_club_api_id=49,
        current_club_name="Chelsea",
    )
    second = _tracked(
        7002,
        historical_team,
        status="on_loan",
        current_club_api_id=44,
        current_club_name="Burnley",
    )
    known = _transfer("2026-07-01", "Loan", 49, "Chelsea", 44, "Burnley")
    record_transfer_events(
        7001,
        [known],
        db.session,
        observed_at=datetime(2026, 7, 1, tzinfo=UTC),
    )
    db.session.commit()

    name_revision = _transfer(
        "2026-07-01",
        "Loan",
        49,
        "Chelsea FC",
        44,
        "Burnley FC",
    )
    type_change = _transfer(
        "2026-07-01",
        "Permanent",
        49,
        "Chelsea",
        44,
        "Burnley",
    )
    new_date = _transfer("2026-07-20", "Loan", 44, "Burnley", 49, "Chelsea")
    second_player_new = _transfer(
        "2026-07-21",
        "Loan",
        49,
        "Chelsea",
        50,
        "Test Club",
    )
    response = [
        _block(7001, name_revision, type_change, new_date),
        _block(7002, second_player_new),
        _block(9999, _transfer("2026-07-22", "Loan", 49, "Chelsea", 60, "Other")),
    ]
    observed_at = datetime(2026, 7, 24, 3, 0, tzinfo=UTC)
    budget = APICallBudget(10)
    client = _PersistingTeamClient(budget, {49: response}, observed_at)
    monkeypatch.setattr(cadence, "_utcnow", lambda: observed_at + timedelta(seconds=1))
    monkeypatch.setattr(cadence, "is_job_paused", lambda _key: False)
    summary = cadence.RunSummary()

    cadence._run_delta(
        client=client,
        budget=budget,
        run_started_at=observed_at - timedelta(seconds=1),
        window=cadence.transfer_window_context(date(2026, 7, 24)),
        dry_run=True,
        summary=summary,
    )

    assert client.team_calls == [49]
    assert budget.spent == 1
    assert summary.teams_scanned == 1
    assert summary.new_transfers_found == 3
    assert summary.flagged_player_ids == {7001, 7002}
    assert PlayerTransferEvent.query.filter_by(player_api_id=7001).count() == 3
    assert PlayerTransferEvent.query.filter_by(player_api_id=7002).count() == 1
    assert PlayerTransferEvent.query.filter_by(player_api_id=9999).count() == 1

    state = cadence._load_setting(cadence.DELTA_QUEUE_SETTING)
    assert set(state["players"]) == {"7001", "7002"}
    assert first.status == "first_team"
    assert first.current_club_api_id == 49
    assert second.status == "on_loan"
    assert second.current_club_api_id == 44


def test_non_dry_delta_persists_new_evidence_and_never_syncs_known_only_player(
    app,
    monkeypatch,
):
    team = _team(49, "Chelsea")
    flagged = _tracked(7004, team, status="first_team")
    scan_only = _tracked(
        7005,
        team,
        status="on_loan",
        current_club_api_id=44,
        current_club_name="Burnley",
    )
    old_flagged_event = _transfer("2026-01-01", "Loan", 49, "Chelsea", 44, "Burnley")
    known_scan_only_event = _transfer(
        "2026-02-01",
        "Loan",
        49,
        "Chelsea",
        45,
        "Known Club",
    )
    record_transfer_events(7004, [old_flagged_event], db.session)
    record_transfer_events(7005, [known_scan_only_event], db.session)
    db.session.commit()
    new_event = _transfer("2026-07-23", "Permanent", 49, "Chelsea", 60, "New Club")

    budget = APICallBudget(5)
    client = _NonPersistingTeamClient(
        budget,
        {
            49: [
                _block(7004, old_flagged_event, new_event),
                _block(7005, known_scan_only_event),
            ]
        },
    )

    class _JourneySpy:
        synced = []

        def __init__(self, api_client):
            assert api_client is client
            self.last_sync_used_transfer_evidence = False

        def sync_player(self, player_api_id, *, force_full, prefetched_transfers):
            assert force_full is True
            identities = {cadence.transfer_event_identity(player_api_id, transfer) for transfer in prefetched_transfers}
            assert cadence.transfer_event_identity(player_api_id, new_event) in identities
            self.synced.append(player_api_id)
            self.last_sync_used_transfer_evidence = True
            return SimpleNamespace(sync_error=None)

    monkeypatch.setattr("src.services.journey_sync.JourneySyncService", _JourneySpy)
    monkeypatch.setattr(cadence, "is_job_paused", lambda _key: False)
    observed_at = datetime(2026, 7, 24, 3, 0, tzinfo=UTC)
    monkeypatch.setattr(cadence, "_utcnow", lambda: observed_at)
    summary = cadence.RunSummary()

    cadence._run_delta(
        client=client,
        budget=budget,
        run_started_at=observed_at,
        window=cadence.transfer_window_context(observed_at.date()),
        dry_run=False,
        summary=summary,
    )

    assert client.team_calls == [49]
    assert _JourneySpy.synced == [7004]
    assert summary.new_transfers_found == 1
    assert summary.resynced_player_ids == {7004}
    assert PlayerTransferEvent.query.filter_by(player_api_id=7004).count() == 2
    assert cadence._load_setting(cadence.DELTA_QUEUE_SETTING)["players"] == {}
    assert flagged.status == "first_team"
    assert scan_only.status == "on_loan"
    assert scan_only.current_club_api_id == 44
    assert scan_only.current_club_name == "Burnley"


def test_delta_never_dequeues_when_expected_new_key_is_not_durable(
    app,
    monkeypatch,
):
    team = _team(49, "Chelsea")
    _tracked(7006, team)
    old_event = _transfer("2026-01-01", "Loan", 49, "Chelsea", 44, "Burnley")
    missing_event = _transfer("2026-07-23", "Permanent", 49, "Chelsea", 60, "New Club")
    record_transfer_events(7006, [old_event], db.session)
    db.session.commit()
    state = _delta_state(7006)
    state["players"]["7006"]["pending_keys"] = [
        cadence._identity_payload(cadence.transfer_event_identity(7006, missing_event))
    ]
    cadence._save_setting(cadence.DELTA_QUEUE_SETTING, state)

    class _MustNotSync:
        def __init__(self, api_client):
            pass

        def sync_player(self, *args, **kwargs):
            raise AssertionError("stale durable evidence cleared a fresh delta flag")

    monkeypatch.setattr("src.services.journey_sync.JourneySyncService", _MustNotSync)
    monkeypatch.setattr(cadence, "is_job_paused", lambda _key: False)
    summary = cadence.RunSummary()

    cadence._process_delta_queue(
        state,
        client=SimpleNamespace(),
        budget=APICallBudget(5),
        deadline_week=False,
        dry_run=False,
        summary=summary,
    )

    assert set(cadence._load_setting(cadence.DELTA_QUEUE_SETTING)["players"]) == {"7006"}
    assert summary.resynced_player_ids == set()


def test_delta_budget_cap_leaves_remainder_and_next_run_resumes(
    app,
    monkeypatch,
):
    team = _team(49, "Chelsea")
    for player_api_id in (7101, 7102):
        _tracked(player_api_id, team)
        record_transfer_events(
            player_api_id,
            [_transfer("2026-07-10", "Loan", 49, "Chelsea", 44, "Burnley")],
            db.session,
        )
    db.session.commit()
    state = _delta_state(7101, 7102)
    cadence._save_setting(cadence.DELTA_QUEUE_SETTING, state)

    class _BudgetedJourneyService:
        synced = []

        def __init__(self, api_client):
            self.api_client = api_client
            self.last_sync_used_transfer_evidence = False

        def sync_player(self, player_api_id, *, force_full, prefetched_transfers):
            assert force_full is True
            assert prefetched_transfers
            self.api_client.call_budget.claim("players/seasons")
            self.synced.append(player_api_id)
            self.last_sync_used_transfer_evidence = True
            return SimpleNamespace(sync_error=None)

    monkeypatch.setattr(
        "src.services.journey_sync.JourneySyncService",
        _BudgetedJourneyService,
    )
    monkeypatch.setattr(cadence, "is_job_paused", lambda _key: False)

    first_budget = APICallBudget(1)
    first_client = SimpleNamespace(call_budget=first_budget)
    first_summary = cadence.RunSummary()
    cadence._process_delta_queue(
        state,
        client=first_client,
        budget=first_budget,
        deadline_week=False,
        dry_run=False,
        summary=first_summary,
    )

    assert first_budget.spent == 1
    assert _BudgetedJourneyService.synced == [7101]
    persisted = cadence._load_setting(cadence.DELTA_QUEUE_SETTING)
    assert set(persisted["players"]) == {"7102"}
    assert first_summary.resynced_player_ids == {7101}

    second_budget = APICallBudget(2)
    second_client = SimpleNamespace(call_budget=second_budget)
    second_summary = cadence.RunSummary()
    cadence._process_delta_queue(
        persisted,
        client=second_client,
        budget=second_budget,
        deadline_week=False,
        dry_run=False,
        summary=second_summary,
    )

    assert second_budget.spent == 1
    assert _BudgetedJourneyService.synced == [7101, 7102]
    assert cadence._load_setting(cadence.DELTA_QUEUE_SETTING)["players"] == {}
    assert second_summary.resynced_player_ids == {7102}


def test_delta_team_scan_cursor_resumes_after_budget_exhaustion(
    app,
    monkeypatch,
):
    first_team = _team(101, "First Team")
    second_team = _team(202, "Second Team")
    _tracked(7111, first_team)
    _tracked(7222, second_team)
    db.session.commit()
    run_at = datetime(2026, 7, 24, 3, 0, tzinfo=UTC)
    monkeypatch.setattr(cadence, "_utcnow", lambda: run_at)
    monkeypatch.setattr(cadence, "is_job_paused", lambda _key: False)

    first_budget = APICallBudget(1)
    first_client = _NonPersistingTeamClient(first_budget, {101: [], 202: []})
    cadence._run_delta(
        client=first_client,
        budget=first_budget,
        run_started_at=run_at,
        window=cadence.transfer_window_context(run_at.date()),
        dry_run=True,
        summary=cadence.RunSummary(),
    )

    assert first_client.team_calls == [101]
    state = cadence._load_setting(cadence.DELTA_QUEUE_SETTING)
    assert state["scan_pending_api_team_ids"] == [202]

    second_budget = APICallBudget(1)
    second_client = _NonPersistingTeamClient(second_budget, {101: [], 202: []})
    cadence._run_delta(
        client=second_client,
        budget=second_budget,
        run_started_at=run_at + timedelta(hours=1),
        window=cadence.transfer_window_context(run_at.date()),
        dry_run=True,
        summary=cadence.RunSummary(),
    )

    assert second_client.team_calls == [202]
    assert cadence._load_setting(cadence.DELTA_QUEUE_SETTING)["scan_pending_api_team_ids"] == []


def test_failed_team_call_keeps_scan_cursor_for_retry(
    app,
    monkeypatch,
):
    team = _team(303, "Retry Team")
    _tracked(7333, team)
    db.session.commit()
    monkeypatch.setattr(cadence, "is_job_paused", lambda _key: False)

    class _FailClosedClient:
        def get_team_transfers(self, team_id, **kwargs):
            assert team_id == 303
            assert kwargs == {
                "force_refresh": True,
                "raise_on_error": True,
                "persist_events": False,
            }
            raise RuntimeError("durable budget checkpoint unavailable")

    summary = cadence.RunSummary()
    cadence._run_delta(
        client=_FailClosedClient(),
        budget=APICallBudget(2),
        run_started_at=datetime(2026, 7, 24, tzinfo=UTC),
        window=cadence.transfer_window_context(date(2026, 7, 24)),
        dry_run=True,
        summary=summary,
    )

    state = cadence._load_setting(cadence.DELTA_QUEUE_SETTING)
    assert state["scan_pending_api_team_ids"] == [303]
    assert summary.teams_scanned == 0
    assert summary.errors == ["team 303: durable budget checkpoint unavailable"]


def test_deadline_week_orders_newest_transfer_first():
    state = {
        "players": {
            "7201": {
                "flagged_at": "2026-07-01T00:00:00+00:00",
                "latest_transfer_date": "2026-08-25",
            },
            "7202": {
                "flagged_at": "2026-07-02T00:00:00+00:00",
                "latest_transfer_date": "2026-08-30",
            },
            "7203": {
                "flagged_at": "2026-06-01T00:00:00+00:00",
                "latest_transfer_date": "2026-08-26",
            },
        }
    }

    assert cadence._ordered_delta_players(state, deadline_week=False) == [
        7203,
        7201,
        7202,
    ]
    assert cadence._ordered_delta_players(state, deadline_week=True) == [
        7202,
        7203,
        7201,
    ]


@pytest.mark.parametrize(
    ("today", "in_window", "deadline_week"),
    [
        (date(2026, 1, 24), True, False),
        (date(2026, 1, 25), True, True),
        (date(2026, 1, 31), True, True),
        (date(2026, 2, 1), True, False),
        (date(2026, 2, 7), True, False),
        (date(2026, 2, 8), False, False),
        (date(2026, 8, 24), True, False),
        (date(2026, 8, 25), True, True),
        (date(2026, 8, 31), True, True),
        (date(2026, 9, 7), True, False),
        (date(2026, 9, 8), False, False),
    ],
)
def test_transfer_window_and_deadline_boundaries(today, in_window, deadline_week):
    context = cadence.transfer_window_context(today)
    assert context.in_window is in_window
    assert context.deadline_week is deadline_week


def test_no_args_dispatches_delta_then_weekday_sweep_inside_and_local_outside():
    assert cadence.planned_modes(
        requested_mode=None,
        today=date(2026, 7, 20),  # Monday
    ) == ["delta", "sweep:mon"]
    assert cadence.planned_modes(
        requested_mode=None,
        today=date(2026, 7, 21),  # Tuesday
    ) == ["delta"]
    assert cadence.planned_modes(
        requested_mode=None,
        today=date(2026, 10, 5),
    ) == ["local"]
    assert cadence.planned_modes(
        requested_mode="delta",
        today=date(2026, 10, 5),
    ) == ["delta"]
    assert cadence.planned_modes(
        requested_mode="sweep",
        today=date(2026, 7, 21),
        sweep_override="all",
    ) == ["sweep:mon", "sweep:wed", "sweep:fri"]
    with pytest.raises(ValueError, match="has no tranche today"):
        cadence.planned_modes(
            requested_mode="sweep",
            today=date(2026, 7, 21),
            sweep_override="",
        )


def test_weekday_tranches_come_from_league_config_with_youth_and_residual_friday(
    app,
    monkeypatch,
):
    monkeypatch.delenv("SUPPORTED_LEAGUE_IDS", raising=False)
    premier_league = _league(39, "Premier League")
    brazil = _league(71, "Brazil Serie A")
    monday = _team(49, "Chelsea", league=premier_league)
    wednesday = _team(131, "Corinthians", league=brazil)
    friday_youth = _team(490, "Chelsea U21", league=premier_league)
    friday_residual = _team(999, "Lower Division Club")
    friday_u20 = _team(501, "Atalanta U20", league=premier_league)
    friday_jong = _team(502, "Jong Ajax", league=premier_league)
    friday_castilla = _team(503, "Real Madrid Castilla", league=premier_league)
    for index, team in enumerate(
        (
            monday,
            wednesday,
            friday_youth,
            friday_residual,
            friday_u20,
            friday_jong,
            friday_castilla,
        ),
        start=7301,
    ):
        _tracked(index, team)
    _tracked(7399, monday, status="sold")
    duplicate_top_five = _team(777, "Seasonal Club", season=2025, league=premier_league)
    duplicate_other = _team(777, "Seasonal Club", season=2024, league=brazil)
    _tracked(7308, duplicate_top_five)
    _tracked(7308, duplicate_other)
    db.session.commit()

    assert cadence.team_sweep_tranche(monday) == "mon"
    assert cadence.team_sweep_tranche(wednesday) == "wed"
    assert cadence.team_sweep_tranche(friday_youth) == "fri"
    assert cadence.team_sweep_tranche(friday_residual) == "fri"
    assert cadence.team_sweep_tranche(friday_u20) == "fri"
    assert cadence.team_sweep_tranche(friday_jong) == "fri"
    assert cadence.team_sweep_tranche(friday_castilla) == "fri"
    assert cadence._sweep_candidates("mon") == [7301, 7308]
    assert cadence._sweep_candidates("wed") == [7302]
    assert cadence._sweep_candidates("fri") == [7303, 7304, 7305, 7306, 7307]
    assert 7399 not in {
        *cadence._sweep_candidates("mon"),
        *cadence._sweep_candidates("wed"),
        *cadence._sweep_candidates("fri"),
    }
    assert cadence._tracked_scan_targets()[0].player_api_ids == frozenset({7301})
    assert cadence.selected_sweep_tranches(date(2026, 7, 20)) == ["mon"]
    assert cadence.selected_sweep_tranches(date(2026, 7, 22)) == ["wed"]
    assert cadence.selected_sweep_tranches(date(2026, 7, 24)) == ["fri"]


def test_sweep_budget_cap_persists_same_week_remainder(
    app,
    monkeypatch,
):
    league = _league(39, "Premier League")
    team = _team(49, "Chelsea", league=league)
    _tracked(7401, team)
    _tracked(7402, team)
    db.session.commit()

    class _BudgetedSweepService:
        synced = []

        def __init__(self, api_client):
            self.api_client = api_client
            self.last_sync_used_transfer_evidence = False

        def sync_player(self, player_api_id, *, force_full, force_transfer_refresh):
            assert force_full is True
            assert force_transfer_refresh is True
            self.api_client.call_budget.claim("players/seasons")
            self.synced.append(player_api_id)
            self.last_sync_used_transfer_evidence = True
            return SimpleNamespace(sync_error=None)

    monkeypatch.setattr(
        "src.services.journey_sync.JourneySyncService",
        _BudgetedSweepService,
    )
    monkeypatch.setattr(cadence, "is_job_paused", lambda _key: False)
    monday = date(2026, 7, 20)

    first_budget = APICallBudget(1)
    first_summary = cadence.RunSummary()
    cadence._run_sweep(
        ["mon"],
        client=SimpleNamespace(call_budget=first_budget),
        budget=first_budget,
        today=monday,
        dry_run=False,
        summary=first_summary,
    )

    assert first_budget.spent == 1
    state = cadence._load_setting(cadence.SWEEP_STATE_SETTING)
    assert state["tranches"]["mon"]["remaining"] == [7402]
    assert state["tranches"]["mon"]["completed_week"] is None

    second_budget = APICallBudget(2)
    second_summary = cadence.RunSummary()
    cadence._run_sweep(
        ["mon"],
        client=SimpleNamespace(call_budget=second_budget),
        budget=second_budget,
        today=monday,
        dry_run=False,
        summary=second_summary,
    )

    state = cadence._load_setting(cadence.SWEEP_STATE_SETTING)
    assert second_budget.spent == 1
    assert _BudgetedSweepService.synced == [7401, 7402]
    assert state["tranches"]["mon"]["remaining"] == []
    assert state["tranches"]["mon"]["completed_week"] == "2026-W30"


def test_old_sweep_backlog_snapshots_current_week_even_when_it_uses_last_call(
    app,
    monkeypatch,
):
    league = _league(39, "Premier League")
    team = _team(49, "Chelsea", league=league)
    for player_api_id in (7411, 7412, 7413):
        _tracked(player_api_id, team)
    db.session.commit()
    cadence._save_setting(
        cadence.SWEEP_STATE_SETTING,
        {
            "version": 1,
            "tranches": {
                "mon": {
                    "started_week": "2026-W30",
                    "completed_week": None,
                    "remaining": [7412],
                }
            },
        },
    )

    class _RolloverSweepService:
        synced = []

        def __init__(self, api_client):
            self.api_client = api_client
            self.last_sync_used_transfer_evidence = False

        def sync_player(self, player_api_id, *, force_full, force_transfer_refresh):
            assert force_full is True
            assert force_transfer_refresh is True
            self.api_client.call_budget.claim("players/seasons")
            self.synced.append(player_api_id)
            self.last_sync_used_transfer_evidence = True
            return SimpleNamespace(sync_error=None)

    monkeypatch.setattr(
        "src.services.journey_sync.JourneySyncService",
        _RolloverSweepService,
    )
    monkeypatch.setattr(cadence, "is_job_paused", lambda _key: False)
    budget = APICallBudget(1)

    cadence._run_sweep(
        ["mon"],
        client=SimpleNamespace(call_budget=budget),
        budget=budget,
        today=date(2026, 7, 27),
        dry_run=False,
        summary=cadence.RunSummary(),
    )

    queue = cadence._load_setting(cadence.SWEEP_STATE_SETTING)["tranches"]["mon"]
    assert budget.spent == 1
    assert _RolloverSweepService.synced == [7412]
    assert queue["started_week"] == "2026-W31"
    assert queue["completed_week"] is None
    assert queue["remaining"] == [7411, 7413]


def _stat(team_id: int, team_name: str, *, youth: bool) -> dict:
    return {
        "team": {"id": team_id, "name": team_name},
        "league": {
            "id": 699 if youth else 39,
            "name": "Premier League 2" if youth else "Premier League",
            "country": "England",
        },
        "games": {
            "appearences": 8,
            "minutes": 600,
            "position": "Midfielder",
        },
        "goals": {"total": 0, "assists": 0},
    }


class _TransfersFedAPI:
    def __init__(self, budget: APICallBudget, player_api_id: int):
        self.call_budget = budget
        self.player_api_id = player_api_id

    def _make_request(self, endpoint, params):
        self.call_budget.claim(endpoint)
        if endpoint == "players/seasons":
            assert params == {"player": self.player_api_id}
            return {"response": [2024, 2026]}
        if endpoint == "players":
            assert params["id"] == self.player_api_id
            season = params["season"]
            statistic = _stat(49, "Chelsea U21", youth=True) if season == 2024 else _stat(44, "Burnley", youth=False)
            return {
                "response": [
                    {
                        "player": {
                            "id": self.player_api_id,
                            "name": "Transfers Fed",
                            "birth": {"date": "2006-01-01", "country": "England"},
                            "nationality": "England",
                        },
                        "statistics": [statistic],
                    }
                ]
            }
        raise AssertionError((endpoint, params))

    def get_player_transfers(self, player_id, **kwargs):
        raise AssertionError("delta sync ignored prefetched durable transfers")


def test_flagged_delta_sync_feeds_transfers_into_status_classification(
    app,
    monkeypatch,
):
    parent = _team(49, "Chelsea")
    _team(44, "Burnley")
    tracked = _tracked(
        7501,
        parent,
        status="first_team",
        current_club_api_id=49,
        current_club_name="Chelsea",
    )
    transfer = _transfer("2026-07-10", "Loan", 49, "Chelsea", 44, "Burnley")
    record_transfer_events(7501, [transfer], db.session)
    db.session.commit()
    state = _delta_state(7501)
    cadence._save_setting(cadence.DELTA_QUEUE_SETTING, state)

    from src.services import journey_sync as journey_module
    from src.utils import academy_classifier

    monkeypatch.setattr(journey_module, "_transfer_as_of", lambda as_of=None: date(2026, 7, 24))
    monkeypatch.setattr(
        journey_module.JourneySyncService,
        "_auto_geocode_clubs",
        lambda self, journey: None,
    )
    classify_calls = []
    real_classify = academy_classifier.classify_tracked_player

    def _spy_classify(*args, **kwargs):
        classify_calls.append(kwargs.get("transfers"))
        return real_classify(*args, **kwargs)

    monkeypatch.setattr(academy_classifier, "classify_tracked_player", _spy_classify)
    monkeypatch.setattr(cadence, "is_job_paused", lambda _key: False)
    budget = APICallBudget(10)
    summary = cadence.RunSummary()

    cadence._process_delta_queue(
        state,
        client=_TransfersFedAPI(budget, 7501),
        budget=budget,
        deadline_week=False,
        dry_run=False,
        summary=summary,
    )

    db.session.refresh(tracked)
    assert budget.spent == 3
    assert summary.resynced_player_ids == {7501}
    assert cadence._load_setting(cadence.DELTA_QUEUE_SETTING)["players"] == {}
    assert classify_calls
    assert classify_calls[-1]
    assert isinstance(classify_calls[-1][0], PlayerTransferEvent)
    assert tracked.status == "on_loan"
    assert tracked.current_club_api_id == 44
    assert tracked.current_club_name == "Burnley"


def test_queue_settings_are_json_and_need_no_schema_change(app):
    cadence._save_setting(cadence.DELTA_QUEUE_SETTING, _delta_state(7601))

    row = AdminSetting.query.filter_by(key=cadence.DELTA_QUEUE_SETTING).one()
    decoded = json.loads(row.value_json)
    assert decoded["version"] == 1
    assert decoded["players"]["7601"]["player_api_id"] == 7601


def test_invalid_sweep_override_fails_closed(monkeypatch):
    monkeypatch.setenv("SWEEP_TRANCHE_OVERRIDE", "tuesday")

    with pytest.raises(ValueError, match=r"mon\|wed\|fri\|all"):
        cadence.selected_sweep_tranches(date(2026, 7, 20))


def test_daily_budget_resumes_across_runs_and_resets_next_utc_day(
    app,
    monkeypatch,
):
    monkeypatch.setenv("TRANSFER_SYNC_DAILY_BUDGET", "2")
    first_day = date(2026, 7, 24)
    first_run = cadence._durable_daily_budget(first_day)

    with ThreadPoolExecutor(max_workers=1) as executor:
        assert executor.submit(first_run.claim, "transfers").result() == 1

    second_run = cadence._durable_daily_budget(first_day)
    assert second_run.spent == 1
    assert second_run.remaining == 1
    assert second_run.claim("players/seasons") == 2
    with pytest.raises(cadence.APICallBudgetExceeded):
        second_run.claim("players")

    next_day = cadence._durable_daily_budget(first_day + timedelta(days=1))
    assert next_day.spent == 0
    assert next_day.remaining == 2


def test_injected_client_is_forced_onto_the_jobs_budget(
    app,
    monkeypatch,
):
    budget = APICallBudget(1)
    client = SimpleNamespace(call_budget=APICallBudget(99))

    def _fake_local_refresh(*, client, budget, dry_run, summary):
        assert client.call_budget is budget
        client.call_budget.claim("transfers")
        summary.modes.append("local")

    monkeypatch.setattr(cadence, "_run_local_refresh", _fake_local_refresh)
    monkeypatch.setattr(cadence, "_queued_player_count", lambda: 0)

    result = cadence._run_locked(
        now=datetime(2026, 10, 5, tzinfo=UTC),
        api_client=client,
        call_budget=budget,
    )

    assert client.call_budget is budget
    assert result["api_calls_spent"] == 1
    assert result["api_calls_spent_this_run"] == 1
    assert result["api_call_budget"] == 1


def test_already_exhausted_run_skips_handshake_and_returns_clean_summary(
    app,
    monkeypatch,
):
    constructed = []

    def _client_factory(*, call_budget, skip_handshake):
        constructed.append((call_budget, skip_handshake))
        return SimpleNamespace(call_budget=call_budget)

    monkeypatch.setattr(cadence, "APIFootballClient", _client_factory)
    monkeypatch.setattr(cadence, "_queued_player_count", lambda: 3)
    budget = APICallBudget(0)

    result = cadence._run_locked(
        mode="delta",
        now=datetime(2026, 7, 24, tzinfo=UTC),
        call_budget=budget,
    )

    assert constructed == [(budget, True)]
    assert result["api_calls_spent"] == 0
    assert result["api_calls_spent_this_run"] == 0
    assert result["api_call_budget"] == 0
    assert result["remainder_queued"] == 3


def test_overlapping_cadence_invocation_fails_closed(
    app,
    monkeypatch,
):
    monkeypatch.setattr(cadence, "is_job_paused", lambda _key: False)
    monkeypatch.setattr(cadence, "has_running_job", lambda _job_type: False)

    with cadence._cadence_run_lock() as acquired:
        assert acquired is True
        assert cadence.run(
            now=datetime(2026, 10, 5, tzinfo=UTC),
            call_budget=APICallBudget(1),
            api_client=SimpleNamespace(call_budget=None),
        ) == {"error": "already_running"}
