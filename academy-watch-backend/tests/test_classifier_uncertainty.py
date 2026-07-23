from types import SimpleNamespace

import pytest
from src.api_football_client import APIFootballClient, TeamPlayersFetchError
from src.utils.academy_classifier import classify_tracked_player
from src.utils.rebuild_runner import _classification_season_context, _classification_season_start

PARENT_ID = 100
OLD_CLUB_ID = 200
LOAN_CLUB_ID = 300
PLAYER_ID = 400
CONFIG = {"inactivity_release_years": None, "use_squad_check": False}


def _loan(transfer_date: str) -> dict:
    return {
        "date": transfer_date,
        "type": "Loan",
        "teams": {
            "out": {"id": PARENT_ID, "name": "Parent FC"},
            "in": {"id": LOAN_CLUB_ID, "name": "Loan FC"},
        },
    }


def _classify_with_loan(transfer_date: str, **kwargs):
    return classify_tracked_player(
        current_club_api_id=OLD_CLUB_ID,
        current_club_name="Prior FC",
        current_level="First Team",
        parent_api_id=PARENT_ID,
        parent_club_name="Parent FC",
        transfers=[_loan(transfer_date)],
        latest_season=2026,
        config=CONFIG,
        **kwargs,
    )


def test_fresh_active_loan_overrides_stale_external_raw_club():
    status, club_id, club_name = _classify_with_loan(
        "2026-07-10",
        as_of="2026-12-01",
    )

    assert (status, club_id, club_name) == ("on_loan", LOAN_CLUB_ID, "Loan FC")


def test_calendar_year_boundary_makes_current_year_loan_fresh():
    stale_under_split_calendar = _classify_with_loan(
        "2026-02-10",
        as_of="2026-12-01",
    )
    calendar_year = _classify_with_loan(
        "2026-02-10",
        as_of="2026-12-01",
        season_start_month=1,
        season_start_day=1,
    )

    assert stale_under_split_calendar[0] == "left"
    assert calendar_year == ("on_loan", LOAN_CLUB_ID, "Loan FC")


def test_expired_historical_loan_does_not_replace_newer_external_stats_club():
    result = classify_tracked_player(
        current_club_api_id=777,
        current_club_name="New Current FC",
        current_level="First Team",
        parent_api_id=PARENT_ID,
        parent_club_name="Parent FC",
        transfers=[_loan("2023-07-10")],
        latest_season=2026,
        config=CONFIG,
        as_of="2026-12-01",
    )

    assert result == ("left", 777, "New Current FC")


def test_hall_permanent_move_replaces_stale_parent_projection():
    transfers = [
        {
            "date": "2023-08-22",
            "type": "Loan",
            "teams": {
                "out": {"id": 49, "name": "Chelsea"},
                "in": {"id": 34, "name": "Newcastle"},
            },
        },
        {
            "date": "2024-06-30",
            "type": "Loan",
            "teams": {
                "out": {"id": 34, "name": "Newcastle"},
                "in": {"id": 49, "name": "Chelsea"},
            },
        },
        {
            "date": "2024-07-01",
            "type": "€ 33M",
            "teams": {
                "out": {"id": 49, "name": "Chelsea"},
                "in": {"id": 34, "name": "Newcastle"},
            },
        },
    ]

    result = classify_tracked_player(
        current_club_api_id=49,
        current_club_name="Chelsea",
        current_level="First Team",
        parent_api_id=49,
        parent_club_name="Chelsea",
        transfers=transfers,
        latest_season=2025,
        config=CONFIG,
        as_of="2026-07-01",
    )

    assert result == ("sold", 34, "Newcastle")


class _TransferClient:
    def __init__(self, result):
        self.result = result

    def get_player_transfers(self, _player_api_id):
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def test_transfer_fetch_failure_preserves_conservative_status():
    result = classify_tracked_player(
        current_club_api_id=LOAN_CLUB_ID,
        current_club_name="Loan FC",
        current_level="First Team",
        parent_api_id=PARENT_ID,
        parent_club_name="Parent FC",
        transfers=None,
        player_api_id=PLAYER_ID,
        api_client=_TransferClient(RuntimeError("provider unavailable")),
        latest_season=2026,
        config=CONFIG,
    )

    assert result == ("on_loan", LOAN_CLUB_ID, "Loan FC")


def test_successful_empty_transfer_fetch_does_not_preserve_stale_loan():
    result = classify_tracked_player(
        current_club_api_id=LOAN_CLUB_ID,
        current_club_name="Loan FC",
        current_level="First Team",
        parent_api_id=PARENT_ID,
        parent_club_name="Parent FC",
        transfers=None,
        player_api_id=PLAYER_ID,
        api_client=_TransferClient([]),
        latest_season=2026,
        config=CONFIG,
    )

    assert result == ("left", LOAN_CLUB_ID, "Loan FC")


@pytest.mark.parametrize(
    "squads",
    [
        {LOAN_CLUB_ID: set()},
        {PARENT_ID: set()},
    ],
)
def test_partial_squad_coverage_preserves_uncertain_status(squads):
    result = classify_tracked_player(
        current_club_api_id=LOAN_CLUB_ID,
        current_club_name="Loan FC",
        current_level="First Team",
        parent_api_id=PARENT_ID,
        parent_club_name="Parent FC",
        transfers=None,
        player_api_id=PLAYER_ID,
        latest_season=2026,
        config={"inactivity_release_years": None, "use_squad_check": True},
        squad_members_by_club=squads,
    )

    assert result == ("on_loan", LOAN_CLUB_ID, "Loan FC")


def test_complete_squad_absence_can_release_player():
    result = classify_tracked_player(
        current_club_api_id=LOAN_CLUB_ID,
        current_club_name="Loan FC",
        current_level="First Team",
        parent_api_id=PARENT_ID,
        parent_club_name="Parent FC",
        transfers=None,
        player_api_id=PLAYER_ID,
        latest_season=2026,
        config={"inactivity_release_years": None, "use_squad_check": True},
        squad_members_by_club={LOAN_CLUB_ID: set(), PARENT_ID: set()},
    )

    assert result == ("released", None, None)


def test_rebuild_uses_league_rollover_month_when_configured():
    config = SimpleNamespace(season_type="calendar", rollover_month=1)

    assert _classification_season_start(71, {71: config}) == (1, 1)
    assert _classification_season_start(71, {}) == (7, 1)


def test_rebuild_calendar_matches_latest_domestic_stats_entry():
    class _EntriesQuery:
        def __init__(self, entries):
            self._entries = entries

        def filter(self, *_criteria):
            return _EntriesQuery([entry for entry in self._entries if not entry.is_international])

        def first(self):
            return self._entries[0] if self._entries else None

    entries = [
        SimpleNamespace(season=2026, league_api_id=999, is_international=True),
        SimpleNamespace(season=2025, league_api_id=71, is_international=False),
        SimpleNamespace(season=2024, league_api_id=39, is_international=False),
    ]
    journey = SimpleNamespace(entries=_EntriesQuery(entries))
    calendar_config = SimpleNamespace(season_type="calendar", rollover_month=1)

    assert _classification_season_context(journey, {71: calendar_config}) == (2025, 1, 1)


def _live_client(request_result):
    client = object.__new__(APIFootballClient)
    client.mode = "direct"
    client.api_key = "test-key"
    client.current_season_start_year = 2026

    if isinstance(request_result, Exception):

        def _raise(*_args, **_kwargs):
            raise request_result

        client._make_request = _raise
    else:
        client._make_request = lambda *_args, **_kwargs: request_result
    return client


def test_live_team_squad_failure_is_not_replaced_with_sample_data():
    client = _live_client(RuntimeError("provider unavailable"))

    with pytest.raises(TeamPlayersFetchError, match="provider unavailable"):
        client.get_team_players(PARENT_ID, season=2026)


def test_successful_empty_team_squad_remains_authoritative_empty():
    client = _live_client(
        {
            "response": [],
            "errors": [],
            "results": 0,
            "paging": {"current": 1, "total": 1},
        }
    )

    assert client.get_team_players(PARENT_ID, season=2026) == []
