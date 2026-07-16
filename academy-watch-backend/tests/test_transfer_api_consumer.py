"""Focused regressions for transfer consumers in API routes and classifier."""

from datetime import UTC, datetime

import pytest
import src.routes.api as api_routes
import src.routes.teams as team_routes
from src.models.journey import PlayerJourney, PlayerJourneyEntry
from src.models.league import Team, db
from src.models.season_rollup import LeagueSeasonConfig
from src.models.tracked_player import TrackedPlayer
from src.routes.api import _academy_seed_transfer_fallback_eligible, _run_batch_fixture_sync, _seed_single_team
from src.services.transfer_events import record_transfer_events
from src.services.transfer_resolver import resolve_transfer_state as real_resolve_transfer_state
from src.utils.academy_classifier import classify_tracked_player


@pytest.fixture(autouse=True)
def _freeze_batch_clock(monkeypatch):
    monkeypatch.setattr(
        api_routes,
        "_batch_now_utc",
        lambda: datetime(2026, 7, 16, 0, 0, tzinfo=UTC),
    )


def _transfer(transfer_date, transfer_type, out_id, out_name, in_id, in_name):
    return {
        "date": transfer_date,
        "type": transfer_type,
        "teams": {
            "out": {"id": out_id, "name": out_name},
            "in": {"id": in_id, "name": in_name},
        },
    }


def _payload(player_id, transfers):
    return [{"player": {"id": player_id}, "transfers": transfers}]


def _parent_team(team_id=49, name="Chelsea"):
    team = Team(
        team_id=team_id,
        name=name,
        country="England",
        season=2025,
        is_active=True,
    )
    db.session.add(team)
    db.session.flush()
    return team


class _BatchAPI:
    def __init__(self, player_id, transfers, *, profile=None):
        self.player_id = player_id
        self.transfers = transfers
        self.profile = profile
        self.fixture_team_ids = []
        self.fixture_requests = []
        self.transfer_calls = 0
        self.profile_transfer_fallbacks = []

    def get_player_transfers(self, player_id):
        assert player_id == self.player_id
        self.transfer_calls += 1
        return _payload(player_id, self.transfers)

    def get_player_by_id(self, player_id, season, *, allow_transfer_fallback=True):
        assert player_id == self.player_id
        assert season == 2025
        self.profile_transfer_fallbacks.append(allow_transfer_fallback)
        if self.profile is None:
            raise AssertionError("known current club must not trigger profile discovery")
        return self.profile

    def get_fixtures_for_team_cached(self, team_id, season, start, end):
        self.fixture_team_ids.append(team_id)
        self.fixture_requests.append((team_id, season, start, end))
        return []


def _durable_batch_api(player_id, transfers, *, profile=None):
    record_transfer_events(player_id, transfers, db.session)
    db.session.commit()
    return _BatchAPI(player_id, transfers, profile=profile)


class _MultiBatchAPI:
    def __init__(self):
        self.transfer_calls = []
        self.fixture_team_ids = []

    def get_player_transfers(self, player_id):
        self.transfer_calls.append(player_id)
        return _payload(
            player_id,
            [_transfer("2025-07-01", "Transfer", 49, "Chelsea", 900 + player_id, "Resolved Club")],
        )

    def get_player_by_id(self, player_id, season, *, allow_transfer_fallback=True):
        raise AssertionError("known current club must not trigger profile discovery")

    def get_fixtures_for_team_cached(self, team_id, season, start, end):
        self.fixture_team_ids.append(team_id)
        return []


def _known_sold_player(parent, player_id, club_id):
    db.session.add(
        TrackedPlayer(
            player_api_id=player_id,
            player_name=f"Known Player {player_id}",
            team_id=parent.id,
            status="sold",
            current_club_api_id=club_id,
            current_club_name=f"Known Club {club_id}",
            data_source="journey-sync",
            is_active=True,
        )
    )


def test_batch_fee_uses_parent_departure_even_after_later_resale(app, monkeypatch):
    """A known current club must not skip or replace the academy's sale fee."""
    parent = _parent_team()
    player_id = 284492
    db.session.add(
        TrackedPlayer(
            player_api_id=player_id,
            player_name="L. Hall",
            team_id=parent.id,
            status="sold",
            current_club_api_id=66,
            current_club_name="Aston Villa",
            sale_fee="€ 50M",
            data_source="journey-sync",
            is_active=True,
        )
    )
    db.session.commit()

    fake = _durable_batch_api(
        player_id,
        [
            _transfer("2024-07-01", "€ 33M", 49, "Chelsea", 34, "Newcastle"),
            _transfer("2026-07-01", "€ 50M", 34, "Newcastle", 66, "Aston Villa"),
        ],
    )
    monkeypatch.setattr("src.api_football_client.APIFootballClient", lambda: fake)

    _run_batch_fixture_sync({"season": 2025, "delay": 0})

    tracked = TrackedPlayer.query.filter_by(player_api_id=player_id).one()
    assert tracked.sale_fee == "€ 33M"
    assert (tracked.current_club_api_id, tracked.current_club_name) == (66, "Aston Villa")
    assert fake.transfer_calls == 0
    assert fake.fixture_team_ids == [34]
    assert fake.fixture_requests == [(34, 2025, "2025-08-01", "2026-06-30")]


def test_batch_known_rows_do_not_refresh_transfers_by_default(app, monkeypatch):
    parent = _parent_team()
    _known_sold_player(parent, 910001, 101)
    _known_sold_player(parent, 910002, 102)
    db.session.commit()
    fake = _MultiBatchAPI()
    monkeypatch.setattr("src.api_football_client.APIFootballClient", lambda: fake)

    result = _run_batch_fixture_sync({"season": 2025, "delay": 0})

    assert fake.transfer_calls == []
    assert result["transfer_refreshes"] == 0


def test_batch_explicit_transfer_refresh_obeys_run_cap(app, monkeypatch):
    parent = _parent_team()
    _known_sold_player(parent, 910003, 103)
    _known_sold_player(parent, 910004, 104)
    db.session.commit()
    fake = _MultiBatchAPI()
    monkeypatch.setattr("src.api_football_client.APIFootballClient", lambda: fake)

    result = _run_batch_fixture_sync(
        {
            "season": 2025,
            "delay": 0,
            "refresh_transfers": True,
            "transfer_refresh_limit": 1,
        }
    )

    assert len(fake.transfer_calls) == 1
    assert result["transfer_refreshes"] == 1


def test_batch_explicit_refresh_failure_uses_durable_evidence(app, monkeypatch):
    parent = _parent_team()
    player_id = 910012
    _known_sold_player(parent, player_id, 66)
    db.session.commit()
    fake = _durable_batch_api(
        player_id,
        [_transfer("2025-07-01", "Transfer", 49, "Chelsea", 34, "Newcastle")],
    )

    def _fail_refresh(requested_player_id):
        assert requested_player_id == player_id
        fake.transfer_calls += 1
        raise RuntimeError("provider unavailable")

    fake.get_player_transfers = _fail_refresh
    monkeypatch.setattr("src.api_football_client.APIFootballClient", lambda: fake)

    result = _run_batch_fixture_sync(
        {
            "season": 2025,
            "delay": 0,
            "refresh_transfers": True,
            "transfer_refresh_limit": 1,
        }
    )

    tracked = TrackedPlayer.query.filter_by(player_api_id=player_id).one()
    assert fake.transfer_calls == 1
    assert result["transfer_refreshes"] == 1
    assert (tracked.current_club_api_id, tracked.current_club_name) == (34, "Newcastle")
    assert fake.fixture_team_ids == [34]


def test_batch_dry_run_never_refreshes_persisted_transfer_evidence(app, monkeypatch):
    parent = _parent_team()
    _known_sold_player(parent, 910005, 105)
    db.session.commit()
    fake = _MultiBatchAPI()
    monkeypatch.setattr("src.api_football_client.APIFootballClient", lambda: fake)

    result = _run_batch_fixture_sync(
        {
            "season": 2025,
            "delay": 0,
            "dry_run": True,
            "refresh_transfers": True,
            "transfer_refresh_limit": 1,
        }
    )

    assert fake.transfer_calls == []
    assert result["transfer_refreshes"] == 0


def test_batch_season_before_first_event_routes_to_initial_owner(app, monkeypatch):
    parent = _parent_team()
    player_id = 910006
    _known_sold_player(parent, player_id, 66)
    db.session.commit()
    fake = _durable_batch_api(
        player_id,
        [_transfer("2025-07-01", "Transfer", 49, "Chelsea", 66, "Aston Villa")],
    )
    monkeypatch.setattr("src.api_football_client.APIFootballClient", lambda: fake)

    _run_batch_fixture_sync({"season": 2023, "delay": 0})

    tracked = TrackedPlayer.query.filter_by(player_api_id=player_id).one()
    assert (tracked.current_club_api_id, tracked.current_club_name) == (66, "Aston Villa")
    assert fake.fixture_requests == [(49, 2023, "2023-08-01", "2024-06-30")]


def test_batch_current_loan_after_requested_season_routes_to_parent(app, monkeypatch):
    parent = _parent_team()
    player_id = 910007
    db.session.add(
        TrackedPlayer(
            player_api_id=player_id,
            player_name="Future Loanee",
            team_id=parent.id,
            status="on_loan",
            current_club_api_id=44,
            current_club_name="Burnley",
            data_source="journey-sync",
            is_active=True,
        )
    )
    db.session.commit()
    fake = _durable_batch_api(
        player_id,
        [_transfer("2026-07-10", "Loan", 49, "Chelsea", 44, "Burnley")],
    )
    monkeypatch.setattr("src.api_football_client.APIFootballClient", lambda: fake)

    _run_batch_fixture_sync({"season": 2025, "delay": 0})

    assert fake.fixture_team_ids == [49]


def test_batch_present_active_loan_ignores_stale_durable_destination(app, monkeypatch):
    parent = _parent_team()
    player_id = 910013
    db.session.add(
        TrackedPlayer(
            player_api_id=player_id,
            player_name="Current Loanee",
            team_id=parent.id,
            status="on_loan",
            current_club_api_id=44,
            current_club_name="Burnley",
            data_source="journey-sync",
            is_active=True,
        )
    )
    db.session.commit()
    fake = _durable_batch_api(
        player_id,
        [_transfer("2023-07-01", "Transfer", 49, "Chelsea", 34, "Newcastle")],
    )
    monkeypatch.setattr("src.api_football_client.APIFootballClient", lambda: fake)

    _run_batch_fixture_sync({"season": 2025, "delay": 0})

    assert fake.fixture_team_ids == [44]


def test_batch_future_season_does_not_query_an_inverted_fixture_window(app, monkeypatch):
    parent = _parent_team()
    player_id = 910014
    db.session.add(
        TrackedPlayer(
            player_api_id=player_id,
            player_name="Future Season Player",
            team_id=parent.id,
            status="first_team",
            current_club_api_id=parent.team_id,
            current_club_name=parent.name,
            data_source="journey-sync",
            is_active=True,
        )
    )
    db.session.commit()
    fake = _BatchAPI(player_id, [])
    monkeypatch.setattr("src.api_football_client.APIFootballClient", lambda: fake)

    result = _run_batch_fixture_sync({"season": 2026, "delay": 0})

    assert result["total_players"] == 1
    assert fake.fixture_requests == []


def test_batch_calendar_year_entry_controls_routing_and_fixture_window(app, monkeypatch):
    parent = _parent_team()
    player_id = 910010
    journey = PlayerJourney(
        player_api_id=player_id,
        player_name="Calendar Loanee",
        current_club_api_id=2530,
        current_club_name="MLS Borrower",
    )
    db.session.add(journey)
    db.session.flush()
    db.session.add_all(
        [
            PlayerJourneyEntry(
                journey_id=journey.id,
                player_api_id=player_id,
                season=2024,
                club_api_id=2530,
                club_name="MLS Borrower",
                league_api_id=253,
                league_name="Major League Soccer",
                level="First Team",
                entry_type="loan",
                is_international=False,
                appearances=20,
                minutes=1800,
            ),
            LeagueSeasonConfig(
                league_api_id=253,
                season_type="calendar",
                rollover_month=1,
            ),
            TrackedPlayer(
                player_api_id=player_id,
                player_name="Calendar Loanee",
                team_id=parent.id,
                status="on_loan",
                current_club_api_id=2530,
                current_club_name="MLS Borrower",
                journey_id=journey.id,
                data_source="journey-sync",
                is_active=True,
            ),
        ]
    )
    db.session.commit()
    fake = _durable_batch_api(
        player_id,
        [_transfer("2024-08-01", "Loan", 49, "Chelsea", 2530, "MLS Borrower")],
    )
    monkeypatch.setattr("src.api_football_client.APIFootballClient", lambda: fake)

    _run_batch_fixture_sync({"season": 2024, "delay": 0})

    assert fake.fixture_requests == [(2530, 2024, "2024-01-01", "2024-12-31")]


def test_batch_calendar_fallback_uses_final_stored_club_entry(app, monkeypatch):
    parent = _parent_team()
    player_id = 910011
    journey = PlayerJourney(
        player_api_id=player_id,
        player_name="Calendar Fallback",
        current_club_api_id=2530,
        current_club_name="MLS Borrower",
    )
    db.session.add(journey)
    db.session.flush()
    db.session.add_all(
        [
            PlayerJourneyEntry(
                journey_id=journey.id,
                player_api_id=player_id,
                season=2024,
                club_api_id=49,
                club_name="Chelsea",
                league_api_id=39,
                league_name="Premier League",
                level="First Team",
                entry_type="first_team",
                is_international=False,
                appearances=30,
                minutes=2700,
            ),
            PlayerJourneyEntry(
                journey_id=journey.id,
                player_api_id=player_id,
                season=2024,
                club_api_id=2530,
                club_name="MLS Borrower",
                league_api_id=253,
                league_name="Major League Soccer",
                level="First Team",
                entry_type="loan",
                is_international=False,
                appearances=5,
                minutes=300,
                transfer_date="2024-08-01",
            ),
            LeagueSeasonConfig(
                league_api_id=253,
                season_type="calendar",
                rollover_month=1,
            ),
            TrackedPlayer(
                player_api_id=player_id,
                player_name="Calendar Fallback",
                team_id=parent.id,
                status="on_loan",
                current_club_api_id=2530,
                current_club_name="MLS Borrower",
                journey_id=journey.id,
                data_source="journey-sync",
                is_active=True,
            ),
        ]
    )
    db.session.commit()
    fake = _BatchAPI(player_id, [])
    monkeypatch.setattr("src.api_football_client.APIFootballClient", lambda: fake)

    _run_batch_fixture_sync({"season": 2024, "delay": 0})

    assert fake.fixture_requests == [(2530, 2024, "2024-01-01", "2024-12-31")]


@pytest.mark.parametrize("status", ["first_team", "academy"])
def test_batch_current_parent_status_routes_historical_loan_to_borrower(app, monkeypatch, status):
    parent = _parent_team()
    player_id = 910008 if status == "first_team" else 910009
    db.session.add(
        TrackedPlayer(
            player_api_id=player_id,
            player_name=f"Historical {status}",
            team_id=parent.id,
            status=status,
            current_club_api_id=49,
            current_club_name="Chelsea",
            data_source="journey-sync",
            is_active=True,
        )
    )
    db.session.commit()
    fake = _durable_batch_api(
        player_id,
        [
            _transfer("2024-02-01", "Loan", 49, "Chelsea", 34, "Newcastle"),
            _transfer("2024-12-31", "Back from Loan", 34, "Newcastle", 49, "Chelsea"),
        ],
    )
    monkeypatch.setattr("src.api_football_client.APIFootballClient", lambda: fake)

    _run_batch_fixture_sync({"season": 2023, "delay": 0})

    assert fake.fixture_team_ids == [34]


def test_batch_current_club_ignores_later_ambiguous_na(app, monkeypatch):
    """A topology-resolved parent departure survives a later unrelated N/A."""
    parent = _parent_team()
    player_id = 900002
    db.session.add(
        TrackedPlayer(
            player_api_id=player_id,
            player_name="Topology Player",
            team_id=parent.id,
            status="sold",
            current_club_api_id=None,
            current_club_name=None,
            data_source="journey-sync",
            is_active=True,
        )
    )
    db.session.commit()

    fake = _durable_batch_api(
        player_id,
        [
            _transfer("2024-07-01", "N/A", 49, "Chelsea", 34, "Newcastle"),
            _transfer("2025-07-01", "N/A", 777, "Unrelated", 888, "Wrong Club"),
        ],
        profile={"statistics": []},
    )
    monkeypatch.setattr("src.api_football_client.APIFootballClient", lambda: fake)

    _run_batch_fixture_sync({"season": 2025, "delay": 0})

    tracked = TrackedPlayer.query.filter_by(player_api_id=player_id).one()
    assert (tracked.current_club_api_id, tracked.current_club_name) == (34, "Newcastle")
    assert fake.transfer_calls == 0
    assert fake.profile_transfer_fallbacks == [False]
    assert fake.fixture_team_ids == [34]


def test_batch_newer_profile_club_survives_later_ambiguous_na(app, monkeypatch):
    """Ambiguous topology cannot replace newer requested-season statistics."""
    parent = _parent_team()
    player_id = 900002
    db.session.add(
        TrackedPlayer(
            player_api_id=player_id,
            player_name="Topology Player",
            team_id=parent.id,
            status="sold",
            current_club_api_id=None,
            current_club_name=None,
            data_source="journey-sync",
            is_active=True,
        )
    )
    db.session.commit()

    fake = _durable_batch_api(
        player_id,
        [
            _transfer("2024-07-01", "N/A", 49, "Chelsea", 34, "Newcastle"),
            _transfer("2025-07-01", "N/A", 777, "Unrelated", 888, "Current Club"),
        ],
        profile={
            "statistics": [
                {
                    "team": {"id": 888, "name": "Current Club"},
                    "games": {"appearences": 20, "position": "Midfielder"},
                }
            ]
        },
    )
    monkeypatch.setattr("src.api_football_client.APIFootballClient", lambda: fake)

    _run_batch_fixture_sync({"season": 2025, "delay": 0})

    tracked = TrackedPlayer.query.filter_by(player_api_id=player_id).one()
    assert (tracked.current_club_api_id, tracked.current_club_name) == (888, "Current Club")
    assert fake.transfer_calls == 0
    assert fake.profile_transfer_fallbacks == [False]
    assert fake.fixture_team_ids == [888]


def test_batch_historical_run_does_not_rewind_present_club(app, monkeypatch):
    parent = _parent_team()
    player_id = 900013
    db.session.add(
        TrackedPlayer(
            player_api_id=player_id,
            player_name="Historical Backfill",
            team_id=parent.id,
            status="sold",
            current_club_api_id=66,
            current_club_name="Aston Villa",
            data_source="journey-sync",
            is_active=True,
        )
    )
    db.session.commit()
    fake = _durable_batch_api(
        player_id,
        [_transfer("2023-07-01", "Transfer", 49, "Chelsea", 34, "Newcastle")],
    )
    monkeypatch.setattr("src.api_football_client.APIFootballClient", lambda: fake)

    _run_batch_fixture_sync({"season": 2023, "delay": 0})

    tracked = TrackedPlayer.query.filter_by(player_api_id=player_id).one()
    assert (tracked.current_club_api_id, tracked.current_club_name) == (66, "Aston Villa")
    assert fake.fixture_team_ids == [34]


def test_batch_unknown_history_preserves_stored_route_and_current(app, monkeypatch):
    parent = _parent_team()
    player_id = 900014
    db.session.add(
        TrackedPlayer(
            player_api_id=player_id,
            player_name="Ambiguous History",
            team_id=parent.id,
            status="sold",
            current_club_api_id=66,
            current_club_name="Aston Villa",
            data_source="journey-sync",
            is_active=True,
        )
    )
    db.session.commit()
    fake = _durable_batch_api(
        player_id,
        [_transfer("2023-07-01", "N/A", 777, "Unrelated", 888, "Other")],
    )
    monkeypatch.setattr("src.api_football_client.APIFootballClient", lambda: fake)

    _run_batch_fixture_sync({"season": 2023, "delay": 0})

    tracked = TrackedPlayer.query.filter_by(player_api_id=player_id).one()
    assert (tracked.current_club_api_id, tracked.current_club_name) == (66, "Aston Villa")
    assert fake.fixture_team_ids == [66]


@pytest.mark.parametrize("status", ["released", "left"])
def test_batch_does_not_write_sale_fee_for_non_sold_status(app, monkeypatch, status):
    parent = _parent_team()
    player_id = 900015 if status == "released" else 900016
    db.session.add(
        TrackedPlayer(
            player_api_id=player_id,
            player_name=f"Non-sale {status}",
            team_id=parent.id,
            status=status,
            current_club_api_id=34,
            current_club_name="Newcastle",
            sale_fee=None,
            data_source="journey-sync",
            is_active=True,
        )
    )
    db.session.commit()
    fake = _durable_batch_api(
        player_id,
        [_transfer("2024-07-01", "€ 12M", 49, "Chelsea", 34, "Newcastle")],
    )
    monkeypatch.setattr("src.api_football_client.APIFootballClient", lambda: fake)

    _run_batch_fixture_sync({"season": 2025, "delay": 0})

    assert TrackedPlayer.query.filter_by(player_api_id=player_id).one().sale_fee is None


def test_batch_clears_stale_fee_when_parent_sale_has_no_fee(app, monkeypatch):
    parent = _parent_team()
    player_id = 900019
    db.session.add(
        TrackedPlayer(
            player_api_id=player_id,
            player_name="Undisclosed Sale",
            team_id=parent.id,
            status="sold",
            current_club_api_id=34,
            current_club_name="Newcastle",
            sale_fee="€ 50M",
            data_source="journey-sync",
            is_active=True,
        )
    )
    db.session.commit()
    fake = _durable_batch_api(
        player_id,
        [_transfer("2024-07-01", "N/A", 49, "Chelsea", 34, "Newcastle")],
    )
    monkeypatch.setattr("src.api_football_client.APIFootballClient", lambda: fake)

    _run_batch_fixture_sync({"season": 2025, "delay": 0})

    assert TrackedPlayer.query.filter_by(player_api_id=player_id).one().sale_fee is None


def test_batch_refresh_delay_applies_after_profile_failure(app, monkeypatch):
    parent = _parent_team()
    for player_id in (900020, 900021):
        db.session.add(
            TrackedPlayer(
                player_api_id=player_id,
                player_name=f"Profile Failure {player_id}",
                team_id=parent.id,
                status="sold",
                current_club_api_id=None,
                data_source="journey-sync",
                is_active=True,
            )
        )
    db.session.commit()
    fake = _MultiBatchAPI()
    delays = []
    monkeypatch.setattr("src.api_football_client.APIFootballClient", lambda: fake)
    monkeypatch.setattr("time.sleep", delays.append)

    _run_batch_fixture_sync(
        {
            "season": 2025,
            "delay": 0.25,
            "refresh_transfers": True,
            "transfer_refresh_limit": 2,
        }
    )

    assert len(fake.transfer_calls) == 2
    assert delays == [0.25, 0.25]


def test_batch_reconciles_stale_stored_club_before_early_continue(app, monkeypatch):
    """Fresh resolver state must replace a contradictory prior backfill."""
    parent = _parent_team()
    stale_destination = Team(
        team_id=34,
        name="Old Newcastle Row",
        country="England",
        season=2024,
        is_active=False,
    )
    destination = Team(
        team_id=34,
        name="Newcastle",
        country="England",
        season=2025,
        is_active=True,
    )
    db.session.add_all([stale_destination, destination])
    player_id = 900004
    db.session.add(
        TrackedPlayer(
            player_api_id=player_id,
            player_name="Stale Destination",
            team_id=parent.id,
            status="sold",
            current_club_api_id=66,
            current_club_name="Aston Villa",
            current_club_db_id=parent.id,
            sale_fee="Undisclosed",
            data_source="journey-sync",
            is_active=True,
        )
    )
    db.session.commit()

    fake = _durable_batch_api(
        player_id,
        [_transfer("2025-07-01", "Transfer", 49, "Chelsea", 34, "Newcastle")],
    )
    monkeypatch.setattr("src.api_football_client.APIFootballClient", lambda: fake)

    _run_batch_fixture_sync({"season": 2025, "delay": 0})

    tracked = TrackedPlayer.query.filter_by(player_api_id=player_id).one()
    assert (tracked.current_club_api_id, tracked.current_club_name) == (34, "Newcastle")
    assert tracked.current_club_db_id == destination.id
    assert fake.transfer_calls == 0
    assert fake.fixture_team_ids == [34]


def test_batch_indeterminate_historical_loan_preserves_newer_stored_club(app, monkeypatch):
    """An expired open loan is not proof the old borrower is current."""
    parent = _parent_team()
    player_id = 900006
    db.session.add(
        TrackedPlayer(
            player_api_id=player_id,
            player_name="Old Open Loan",
            team_id=parent.id,
            status="sold",
            current_club_api_id=66,
            current_club_name="Aston Villa",
            data_source="journey-sync",
            is_active=True,
        )
    )
    db.session.commit()

    fake = _durable_batch_api(
        player_id,
        [_transfer("2023-07-01", "Loan", 49, "Chelsea", 34, "Newcastle")],
    )
    monkeypatch.setattr("src.api_football_client.APIFootballClient", lambda: fake)

    _run_batch_fixture_sync({"season": 2025, "delay": 0})

    tracked = TrackedPlayer.query.filter_by(player_api_id=player_id).one()
    assert (tracked.current_club_api_id, tracked.current_club_name) == (66, "Aston Villa")
    assert fake.fixture_team_ids == [66]


def test_batch_old_permanent_move_preserves_newer_unrelated_stored_club(app, monkeypatch):
    """An old sale cannot erase later statistics/backfill at a third club."""
    parent = _parent_team()
    player_id = 900010
    db.session.add(
        TrackedPlayer(
            player_api_id=player_id,
            player_name="Later Third Club",
            team_id=parent.id,
            status="sold",
            current_club_api_id=66,
            current_club_name="Aston Villa",
            data_source="journey-sync",
            is_active=True,
        )
    )
    db.session.commit()

    fake = _durable_batch_api(
        player_id,
        [_transfer("2023-07-01", "Transfer", 49, "Chelsea", 34, "Newcastle")],
    )
    monkeypatch.setattr("src.api_football_client.APIFootballClient", lambda: fake)

    _run_batch_fixture_sync({"season": 2025, "delay": 0})

    tracked = TrackedPlayer.query.filter_by(player_api_id=player_id).one()
    assert (tracked.current_club_api_id, tracked.current_club_name) == (
        66,
        "Aston Villa",
    )
    assert fake.fixture_team_ids == [66]


def test_batch_indeterminate_historical_loan_preserves_newer_profile_club(app, monkeypatch):
    """Current-season profile evidence wins over an expired open loan."""
    parent = _parent_team()
    player_id = 900007
    db.session.add(
        TrackedPlayer(
            player_api_id=player_id,
            player_name="Profile Club",
            team_id=parent.id,
            status="sold",
            data_source="journey-sync",
            is_active=True,
        )
    )
    db.session.commit()

    fake = _durable_batch_api(
        player_id,
        [_transfer("2023-07-01", "Loan", 49, "Chelsea", 34, "Newcastle")],
        profile={
            "statistics": [
                {
                    "team": {"id": 66, "name": "Aston Villa"},
                    "games": {"appearences": 12, "position": "Defender"},
                }
            ]
        },
    )
    monkeypatch.setattr("src.api_football_client.APIFootballClient", lambda: fake)

    _run_batch_fixture_sync({"season": 2025, "delay": 0})

    tracked = TrackedPlayer.query.filter_by(player_api_id=player_id).one()
    assert (tracked.current_club_api_id, tracked.current_club_name) == (66, "Aston Villa")
    assert fake.fixture_team_ids == [66]


def test_batch_commits_resolver_fee_before_profile_failure(app, monkeypatch):
    """A later profile error cannot discard an academy sale-fee repair."""
    parent = _parent_team()
    player_id = 900008
    db.session.add(
        TrackedPlayer(
            player_api_id=player_id,
            player_name="Fee Repair",
            team_id=parent.id,
            status="sold",
            sale_fee=None,
            data_source="journey-sync",
            is_active=True,
        )
    )
    db.session.commit()

    fake = _durable_batch_api(
        player_id,
        [_transfer("2024-07-01", "€ 12M", 49, "Chelsea", 34, "Newcastle")],
    )
    monkeypatch.setattr("src.api_football_client.APIFootballClient", lambda: fake)

    _run_batch_fixture_sync({"season": 2025, "delay": 0})

    # Expire ORM state to prove the value survived the independent commit.
    db.session.expire_all()
    tracked = TrackedPlayer.query.filter_by(player_api_id=player_id).one()
    assert tracked.sale_fee == "€ 12M"
    assert (tracked.current_club_api_id, tracked.current_club_name) == (34, "Newcastle")
    assert fake.fixture_team_ids == [34]


def test_academy_network_marks_unfetched_transfers_as_unknown(app, client, monkeypatch):
    parent = _parent_team()
    journey = PlayerJourney(
        player_api_id=900011,
        player_name="Unfetched Loan",
        academy_club_ids=[parent.team_id],
        current_club_api_id=300,
        current_club_name="Hull City",
        current_level="Senior",
    )
    db.session.add(journey)
    db.session.commit()
    observed_transfers = []

    class _JourneyQuery:
        def filter(self, *args):
            return self

        def all(self):
            return [journey]

    def _capture_classifier(*args, **kwargs):
        observed_transfers.append(kwargs.get("transfers"))
        return "on_loan", 300, "Hull City"

    monkeypatch.setattr(team_routes, "classify_tracked_player", _capture_classifier)
    monkeypatch.setattr(PlayerJourney, "query", _JourneyQuery())

    response = client.get(f"/api/teams/{parent.team_id}/academy-network")

    assert response.status_code == 200
    assert observed_transfers == [None]
    assert response.get_json()["all_players"][0]["status"] == "on_loan"


def test_seed_existing_transfer_state_survives_fetch_failure(app, monkeypatch):
    parent = _parent_team()
    destination = Team(
        team_id=777,
        name="Buying Club",
        country="England",
        season=2025,
        is_active=True,
    )
    db.session.add(destination)
    db.session.flush()
    journey = PlayerJourney(
        player_api_id=900012,
        player_name="Known Seed Sale",
        academy_club_ids=[parent.team_id],
        current_club_api_id=parent.team_id,
        current_club_name=parent.name,
        current_level="First Team",
        seasons_synced=[2025],
    )
    db.session.add(journey)
    db.session.flush()
    existing = TrackedPlayer(
        player_api_id=journey.player_api_id,
        player_name=journey.player_name,
        team_id=parent.id,
        status="sold",
        current_club_api_id=777,
        current_club_name="Buying Club",
        current_club_db_id=destination.id,
        sale_fee="€ 20M",
        data_source="journey-sync",
        is_active=True,
    )
    db.session.add(existing)
    db.session.commit()

    class _JourneyQuery:
        def filter(self, *args):
            return self

        def all(self):
            return [journey]

    class _FailedTransferAPI:
        current_season_start_year = 2025

        def get_team_players(self, team_id, season):
            return []

        def get_player_transfers(self, player_id):
            raise RuntimeError("provider unavailable")

    monkeypatch.setattr(PlayerJourney, "query", _JourneyQuery())
    monkeypatch.setattr(api_routes, "APIFootballClient", _FailedTransferAPI)

    _seed_single_team(parent, sync_journeys=False, years=1, season=2025)

    db.session.expire_all()
    persisted = TrackedPlayer.query.filter_by(player_api_id=journey.player_api_id).one()
    assert persisted.status == "sold"
    assert (persisted.current_club_api_id, persisted.current_club_name) == (777, "Buying Club")
    assert persisted.current_club_db_id == destination.id
    assert persisted.sale_fee == "€ 20M"


def test_seed_successful_sale_updates_name_club_fk_and_parent_fee(app, monkeypatch):
    parent = _parent_team()
    stale_destination = Team(
        team_id=34,
        name="Old Newcastle Row",
        country="England",
        season=2024,
        is_active=False,
    )
    destination = Team(
        team_id=34,
        name="Newcastle",
        country="England",
        season=2025,
        is_active=True,
    )
    db.session.add_all([stale_destination, destination])
    journey = PlayerJourney(
        player_api_id=900017,
        player_name="Seed Sale",
        academy_club_ids=[parent.team_id],
        current_club_api_id=parent.team_id,
        current_club_name=parent.name,
        current_level="First Team",
        seasons_synced=[2025],
    )
    db.session.add(journey)
    db.session.flush()
    existing = TrackedPlayer(
        player_api_id=journey.player_api_id,
        player_name=journey.player_name,
        team_id=parent.id,
        status="sold",
        current_club_api_id=34,
        current_club_name="Stale Buyer Name",
        current_club_db_id=destination.id,
        sale_fee="€ 50M",
        data_source="journey-sync",
        is_active=True,
    )
    db.session.add(existing)
    db.session.commit()

    class _JourneyQuery:
        def filter(self, *args):
            return self

        def all(self):
            return [journey]

    class _SuccessfulTransferAPI:
        current_season_start_year = 2025

        def get_team_players(self, team_id, season):
            return []

        def get_player_transfers(self, player_id):
            return _payload(
                player_id,
                [_transfer("2025-07-01", "€ 12M", 49, "Chelsea", 34, "Newcastle")],
            )

    monkeypatch.setattr(PlayerJourney, "query", _JourneyQuery())
    monkeypatch.setattr(api_routes, "APIFootballClient", _SuccessfulTransferAPI)

    _seed_single_team(parent, sync_journeys=False, years=1, season=2025)

    db.session.expire_all()
    persisted = TrackedPlayer.query.filter_by(player_api_id=journey.player_api_id).one()
    assert persisted.status == "sold"
    assert (persisted.current_club_api_id, persisted.current_club_name) == (34, "Newcastle")
    assert persisted.current_club_db_id == destination.id
    assert persisted.sale_fee == "€ 12M"


def test_seed_successful_empty_history_clears_stale_sale_state(app, monkeypatch):
    parent = _parent_team()
    journey = PlayerJourney(
        player_api_id=900018,
        player_name="Seed Return",
        academy_club_ids=[parent.team_id],
        current_club_api_id=parent.team_id,
        current_club_name=parent.name,
        current_level="First Team",
        seasons_synced=[2025],
    )
    db.session.add(journey)
    db.session.flush()
    existing = TrackedPlayer(
        player_api_id=journey.player_api_id,
        player_name=journey.player_name,
        team_id=parent.id,
        status="sold",
        current_club_api_id=777,
        current_club_name="Old Buyer",
        sale_fee="€ 20M",
        data_source="journey-sync",
        is_active=True,
    )
    db.session.add(existing)
    db.session.commit()

    class _JourneyQuery:
        def filter(self, *args):
            return self

        def all(self):
            return [journey]

    class _EmptyTransferAPI:
        current_season_start_year = 2025

        def get_team_players(self, team_id, season):
            return []

        def get_player_transfers(self, player_id):
            return []

    monkeypatch.setattr(PlayerJourney, "query", _JourneyQuery())
    monkeypatch.setattr(api_routes, "APIFootballClient", _EmptyTransferAPI)

    _seed_single_team(parent, sync_journeys=False, years=1, season=2025)

    db.session.expire_all()
    persisted = TrackedPlayer.query.filter_by(player_api_id=journey.player_api_id).one()
    assert persisted.status == "first_team"
    assert (persisted.current_club_api_id, persisted.current_club_name) == (49, "Chelsea")
    assert persisted.current_club_db_id == parent.id
    assert persisted.sale_fee is None


def test_seed_ambiguous_nonempty_history_preserves_existing_transfer_state(app, monkeypatch):
    parent = _parent_team()
    destination = Team(
        team_id=777,
        name="Known Buyer",
        country="England",
        season=2025,
        is_active=True,
    )
    db.session.add(destination)
    db.session.flush()
    journey = PlayerJourney(
        player_api_id=900022,
        player_name="Ambiguous Seed",
        academy_club_ids=[parent.team_id],
        current_club_api_id=parent.team_id,
        current_club_name=parent.name,
        current_level="First Team",
        seasons_synced=[2025],
    )
    db.session.add(journey)
    db.session.flush()
    existing = TrackedPlayer(
        player_api_id=journey.player_api_id,
        player_name=journey.player_name,
        team_id=parent.id,
        status="sold",
        current_club_api_id=777,
        current_club_name="Known Buyer",
        current_club_db_id=destination.id,
        sale_fee="€ 20M",
        data_source="journey-sync",
        is_active=True,
    )
    db.session.add(existing)
    db.session.commit()

    class _JourneyQuery:
        def filter(self, *args):
            return self

        def all(self):
            return [journey]

    class _AmbiguousTransferAPI:
        current_season_start_year = 2025

        def get_team_players(self, team_id, season):
            return []

        def get_player_transfers(self, player_id):
            return _payload(
                player_id,
                [_transfer("2025-07-01", "N/A", 888, "Unrelated", 999, "Other")],
            )

    monkeypatch.setattr(PlayerJourney, "query", _JourneyQuery())
    monkeypatch.setattr(api_routes, "APIFootballClient", _AmbiguousTransferAPI)

    _seed_single_team(parent, sync_journeys=False, years=1, season=2025)

    db.session.expire_all()
    persisted = TrackedPlayer.query.filter_by(player_api_id=journey.player_api_id).one()
    assert persisted.status == "sold"
    assert (persisted.current_club_api_id, persisted.current_club_name) == (777, "Known Buyer")
    assert persisted.current_club_db_id == destination.id
    assert persisted.sale_fee == "€ 20M"


class _SeedTransferAPI:
    def __init__(self, player_id, *, transfers=None, transfer_error=None):
        self.player_id = player_id
        self.transfers = transfers
        self.transfer_error = transfer_error

    def get_player_transfers(self, player_id):
        assert player_id == self.player_id
        if self.transfer_error is not None:
            raise self.transfer_error
        return _payload(player_id, self.transfers or [])


def test_seed_fallback_skips_candidate_when_transfer_fetch_fails():
    player_id = 900005
    fake = _SeedTransferAPI(
        player_id,
        transfer_error=RuntimeError("provider unavailable"),
    )

    assert not _academy_seed_transfer_fallback_eligible(
        fake,
        player_id,
        49,
        "Chelsea",
        as_of="2026-06-30",
    )


def test_seed_fallback_accepts_successful_empty_transfer_history():
    player_id = 900005
    fake = _SeedTransferAPI(player_id, transfers=[])

    assert _academy_seed_transfer_fallback_eligible(
        fake,
        player_id,
        49,
        "Chelsea",
        as_of="2026-06-30",
    )


def test_seed_fallback_does_not_invent_parent_owner_for_ambiguous_na(monkeypatch):
    resolver_kwargs = []

    def _capture_resolver(events, **kwargs):
        resolver_kwargs.append(kwargs)
        return real_resolve_transfer_state(events, **kwargs)

    monkeypatch.setattr(api_routes, "resolve_transfer_state", _capture_resolver)
    player_id = 900005
    fake = _SeedTransferAPI(
        player_id,
        transfers=[
            _transfer(
                "2025-07-01",
                "N/A",
                700,
                "Other Club",
                49,
                "Chelsea",
            )
        ],
    )

    assert not _academy_seed_transfer_fallback_eligible(
        fake,
        player_id,
        49,
        "Chelsea",
        as_of="2026-06-30",
    )
    assert len(resolver_kwargs) == 1
    assert "initial_owner" not in resolver_kwargs[0]


def test_seed_fallback_rejects_external_loan_arrival_into_parent():
    """Borrowing a prospect does not make that prospect an academy product."""
    player_id = 900009
    fake = _SeedTransferAPI(
        player_id,
        transfers=[
            _transfer(
                "2025-07-01",
                "Loan",
                700,
                "Other Club",
                49,
                "Chelsea",
            )
        ],
    )

    assert not _academy_seed_transfer_fallback_eligible(
        fake,
        player_id,
        49,
        "Chelsea",
        as_of="2026-06-30",
    )


def test_classifier_matches_active_borrower_across_reverse_affiliate_id(app):
    """Stats may expose Jong Ajax while the transfer names senior Ajax."""
    status, club_id, club_name = classify_tracked_player(
        current_club_api_id=425,
        current_club_name="Jong Ajax",
        current_level="First Team",
        parent_api_id=165,
        parent_club_name="Borussia Dortmund",
        transfers=[
            _transfer(
                "2025-07-01",
                "Loan",
                165,
                "Borussia Dortmund",
                194,
                "Ajax",
            )
        ],
        latest_season=2025,
        as_of="2026-06-30",
    )

    assert (status, club_id, club_name) == ("on_loan", 425, "Jong Ajax")


def test_classifier_fetch_failure_is_not_a_successful_empty_history(app):
    """Provider failure preserves uncertainty; a real empty response means left."""

    class _FailingAPI:
        def get_player_transfers(self, player_id):
            raise RuntimeError("provider unavailable")

    class _EmptyAPI:
        def get_player_transfers(self, player_id):
            return _payload(player_id, [])

    kwargs = {
        "current_club_api_id": 700,
        "current_club_name": "Other Club",
        "current_level": "First Team",
        "parent_api_id": 165,
        "parent_club_name": "Borussia Dortmund",
        "player_api_id": 900003,
        "latest_season": 2025,
        "as_of": "2026-06-30",
    }

    failed = classify_tracked_player(api_client=_FailingAPI(), transfers=None, **kwargs)
    empty = classify_tracked_player(api_client=_EmptyAPI(), transfers=None, **kwargs)

    assert failed[0] == "on_loan"
    assert empty[0] == "left"


def test_classifier_same_parent_fetch_failure_stays_conservative(app):
    """Unknown transfer evidence must not invent a same-parent departure."""

    class _FailingAPI:
        def get_player_transfers(self, player_id):
            raise RuntimeError("provider unavailable")

    result = classify_tracked_player(
        current_club_api_id=49,
        current_club_name="Chelsea",
        current_level="First Team",
        parent_api_id=49,
        parent_club_name="Chelsea",
        transfers=None,
        player_api_id=284492,
        api_client=_FailingAPI(),
        latest_season=2025,
        config={"inactivity_release_years": 2, "use_squad_check": False},
        as_of="2026-06-30",
    )

    assert result == ("first_team", 49, "Chelsea")


_CLASSIFIER_CONFIG = {"inactivity_release_years": 2, "use_squad_check": False}


def test_classifier_hall_sale_overrides_stale_same_parent_journey(app):
    """Hall-shaped parent stats must not hide the later permanent conversion."""
    result = classify_tracked_player(
        current_club_api_id=49,
        current_club_name="Chelsea",
        current_level="First Team",
        parent_api_id=49,
        parent_club_name="Chelsea",
        transfers=[
            _transfer("2023-08-22", "Loan", 49, "Chelsea", 34, "Newcastle"),
            _transfer("2024-07-01", "€ 33M", 49, "Chelsea", 34, "Newcastle"),
        ],
        latest_season=2025,
        config=_CLASSIFIER_CONFIG,
        as_of="2026-06-30",
    )

    assert result == ("sold", 34, "Newcastle")


def test_classifier_release_overrides_stale_same_parent_journey(app):
    """A definitive parent-to-free-agent event clears stale parent fields."""
    result = classify_tracked_player(
        current_club_api_id=49,
        current_club_name="Chelsea",
        current_level="First Team",
        parent_api_id=49,
        parent_club_name="Chelsea",
        transfers=[
            _transfer("2025-07-01", "Free agent", 49, "Chelsea", None, None),
        ],
        latest_season=2025,
        config=_CLASSIFIER_CONFIG,
        as_of="2026-06-30",
    )

    assert result == ("released", None, None)


def test_classifier_active_loan_overrides_stale_same_parent_journey(app):
    """A fresh resolved parent loan supplies the borrower even before stats move."""
    result = classify_tracked_player(
        current_club_api_id=49,
        current_club_name="Chelsea",
        current_level="First Team",
        parent_api_id=49,
        parent_club_name="Chelsea",
        transfers=[
            _transfer("2026-07-10", "Loan", 49, "Chelsea", 44, "Burnley"),
        ],
        latest_season=2026,
        config=_CLASSIFIER_CONFIG,
        as_of="2026-12-01",
    )

    assert result == ("on_loan", 44, "Burnley")


def test_classifier_name_only_parent_and_destination_can_be_sold(app):
    """Provider IDs are enrichment, not a prerequisite for a named sale."""
    result = classify_tracked_player(
        current_club_api_id=49,
        current_club_name="Chelsea",
        current_level="First Team",
        parent_api_id=49,
        parent_club_name="Chelsea",
        transfers=[
            _transfer(
                "2024-07-01",
                "Transfer",
                None,
                "Chelsea U21",
                None,
                "Newcastle United",
            ),
        ],
        latest_season=2025,
        config=_CLASSIFIER_CONFIG,
        as_of="2026-06-30",
    )

    assert result == ("sold", None, "Newcastle United")


def test_classifier_permanent_buyback_restores_parent_status(app):
    """A later permanent move back to the parent supersedes its old sale."""
    result = classify_tracked_player(
        current_club_api_id=34,
        current_club_name="Newcastle",
        current_level="First Team",
        parent_api_id=49,
        parent_club_name="Chelsea",
        transfers=[
            _transfer("2023-07-01", "Transfer", 49, "Chelsea", 34, "Newcastle"),
            _transfer("2025-07-01", "Transfer", 34, "Newcastle", 49, "Chelsea"),
        ],
        latest_season=2025,
        config=_CLASSIFIER_CONFIG,
        as_of="2026-06-30",
    )

    assert result == ("first_team", 49, "Chelsea")


def test_classifier_older_loan_return_does_not_override_newer_external_stats(app):
    """A return predating the latest stats season cannot erase its current club."""
    result = classify_tracked_player(
        current_club_api_id=34,
        current_club_name="Newcastle",
        current_level="First Team",
        parent_api_id=49,
        parent_club_name="Chelsea",
        transfers=[
            _transfer("2023-07-01", "Loan", 49, "Chelsea", 34, "Newcastle"),
            _transfer("2024-07-01", "Back from Loan", 34, "Newcastle", 49, "Chelsea"),
        ],
        latest_season=2025,
        config=_CLASSIFIER_CONFIG,
        as_of="2026-06-30",
    )

    assert result == ("left", 34, "Newcastle")


def test_classifier_current_season_loan_return_restores_parent_status(app):
    """A return in the latest stats season supersedes stale borrower fields."""
    result = classify_tracked_player(
        current_club_api_id=34,
        current_club_name="Newcastle",
        current_level="First Team",
        parent_api_id=49,
        parent_club_name="Chelsea",
        transfers=[
            _transfer("2024-07-01", "Loan", 49, "Chelsea", 34, "Newcastle"),
            _transfer("2025-07-01", "Back from Loan", 34, "Newcastle", 49, "Chelsea"),
        ],
        latest_season=2025,
        config=_CLASSIFIER_CONFIG,
        as_of="2026-06-30",
    )

    assert result == ("first_team", 49, "Chelsea")
