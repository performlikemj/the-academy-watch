"""Consumer-level regressions for chronological transfer state.

These tests deliberately enter through ``JourneySyncService.sync_player`` with
an in-memory database and an API client that cannot perform I/O.  The pure
resolver has its own exhaustive unit suite; this module pins the values written
by its three consumers: journey entries, academy-relative tracked status/fee,
and journey-level current club/status/owner.
"""

from copy import deepcopy

import pytest
from src.models.journey import PlayerJourney, PlayerJourneyEntry
from src.models.league import Team, db
from src.models.season_rollup import PlayerSeasonCell, PlayerSeasonTotal
from src.models.tracked_player import TrackedPlayer
from src.services.journey_sync import JourneySyncService


@pytest.fixture(autouse=True)
def _freeze_transfer_resolution_date(monkeypatch):
    monkeypatch.setattr(
        "src.services.journey_sync._transfer_as_of",
        lambda as_of=None: as_of or "2026-07-16",
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


def _stat(team_id, team_name, appearances, minutes, *, youth=False):
    return {
        "team": {"id": team_id, "name": team_name},
        "league": {
            "id": 699 if youth else 39,
            "name": "Premier League 2" if youth else "Premier League",
            "country": "Test Country",
        },
        "games": {
            "appearences": appearances,
            "minutes": minutes,
            "position": "Midfielder",
        },
        "goals": {"total": 0, "assists": 0},
    }


class _FakeAPI:
    """The only API surface the real sync may use; every other call fails."""

    def __init__(self, player_id, player_name, seasons, transfers):
        self.player_id = player_id
        self.player_name = player_name
        self.seasons = seasons
        self.transfers = transfers
        self.player_seasons_requested = []

    def _make_request(self, endpoint, params):
        if endpoint == "players/seasons":
            assert params == {"player": self.player_id}
            return {"response": sorted(self.seasons)}
        if endpoint == "players":
            assert params["id"] == self.player_id
            season = params["season"]
            self.player_seasons_requested.append(season)
            return {
                "response": [
                    {
                        "player": {
                            "id": self.player_id,
                            "name": self.player_name,
                            "birth": {"date": "2004-01-01", "country": "Test Country"},
                            "nationality": "Test Country",
                        },
                        "statistics": deepcopy(self.seasons[season]),
                    }
                ]
            }
        raise AssertionError(f"unexpected endpoint: {endpoint} {params}")

    def get_player_transfers(self, player_id):
        assert player_id == self.player_id
        return [
            {
                "player": {"id": player_id, "name": self.player_name},
                "transfers": deepcopy(self.transfers),
            }
        ]


class _FailingTransferAPI(_FakeAPI):
    def get_player_transfers(self, player_id):
        assert player_id == self.player_id
        raise RuntimeError("provider transfer endpoint unavailable")


def _seed_transfer_teams(transfers):
    clubs = {}
    for event in transfers:
        for direction in ("out", "in"):
            club = event["teams"][direction]
            clubs[club["id"]] = club["name"]

    for club_id, club_name in clubs.items():
        if Team.query.filter_by(team_id=club_id, season=2025).first() is None:
            db.session.add(
                Team(
                    team_id=club_id,
                    name=club_name,
                    country="Test Country",
                    season=2025,
                    is_active=True,
                )
            )
    db.session.commit()


def _sync(player_id, player_name, parent_id, seasons, transfers):
    _seed_transfer_teams(transfers)
    service = JourneySyncService(_FakeAPI(player_id, player_name, seasons, transfers))
    # Geocoding is unrelated to transfer consumers and must never escape the
    # hermetic test boundary.
    service._auto_geocode_clubs = lambda journey: None
    journey = service.sync_player(player_id, force_full=True)
    assert journey is not None
    assert journey.sync_error is None

    parent = Team.query.filter_by(team_id=parent_id, season=2025).one()
    entries = PlayerJourneyEntry.query.filter_by(journey_id=journey.id).all()
    tracked = TrackedPlayer.query.filter_by(player_api_id=player_id, team_id=parent.id).one_or_none()
    assert tracked is not None, {
        "academy_club_ids": journey.academy_club_ids,
        "entries": [
            (
                entry.season,
                entry.club_api_id,
                entry.club_name,
                entry.entry_type,
                entry.is_youth,
            )
            for entry in entries
        ],
        "tracked_rows": [
            (row.team.team_id, row.status, row.is_active)
            for row in TrackedPlayer.query.filter_by(player_api_id=player_id).all()
        ],
    }
    return journey, tracked, entries


def _entry(entries, season, club_id):
    matches = [entry for entry in entries if entry.season == season and entry.club_api_id == club_id]
    assert len(matches) == 1
    return matches[0]


HALL_TRANSFERS = [
    _transfer("2024-07-01", "€ 33M", 49, "Chelsea", 34, "Newcastle"),
    _transfer("2023-08-22", "Loan", 49, "Chelsea", 34, "Newcastle"),
]


def test_hall_full_sync_canary_replaces_the_loan_on_the_july_first_conversion(app):
    """Hall's exact transfer payload repairs all three persisted consumers."""
    seasons = {
        2022: [_stat(49, "Chelsea U21", 6, 500, youth=True)],
        2023: [_stat(34, "Newcastle", 24, 1009)],
        2024: [_stat(34, "Newcastle", 34, 2660)],
        2025: [_stat(34, "Newcastle", 45, 3263)],
    }
    _seed_transfer_teams(HALL_TRANSFERS)
    chelsea = Team.query.filter_by(team_id=49, season=2025).one()
    newcastle = Team.query.filter_by(team_id=34, season=2025).one()
    db.session.add_all(
        [
            TrackedPlayer(
                id=21704,
                player_api_id=284492,
                player_name="L. Hall",
                team_id=chelsea.id,
                status="on_loan",
                current_club_api_id=34,
                current_club_name="Newcastle",
                data_source="journey-sync",
                last_academy_season=2022,
                is_active=True,
            ),
            TrackedPlayer(
                id=21705,
                player_api_id=284492,
                player_name="L. Hall",
                team_id=newcastle.id,
                status="first_team",
                current_club_api_id=34,
                current_club_name="Newcastle",
                data_source="owning-club",
                is_active=True,
            ),
        ]
    )
    db.session.commit()

    journey, tracked, entries = _sync(284492, "L. Hall", 49, seasons, HALL_TRANSFERS)
    buying_club_row = TrackedPlayer.query.filter_by(id=21705).one()
    loan_entry = _entry(entries, 2023, 34)
    newcastle_entries = [_entry(entries, season, 34) for season in (2024, 2025)]

    assert tracked.id == 21704
    assert tracked.is_active is True
    assert tracked.status == "sold"
    assert tracked.current_club_api_id == 34
    assert tracked.current_club_name == "Newcastle"
    assert tracked.sale_fee == "€ 33M"
    assert buying_club_row.is_active is False

    assert [entry.entry_type for entry in newcastle_entries] == ["first_team", "first_team"]
    assert [entry.transfer_date for entry in newcastle_entries] == ["2024-07-01", "2024-07-01"]
    assert [entry.transfer_fee for entry in newcastle_entries] == ["€ 33M", "€ 33M"]
    assert (loan_entry.entry_type, loan_entry.transfer_date, loan_entry.transfer_fee) == (
        "loan",
        "2023-08-22",
        None,
    )
    assert journey.current_club_api_id == 34
    assert journey.current_club_name == "Newcastle"
    assert journey.current_status is None
    assert journey.current_owner_api_id is None
    assert journey.current_owner_name is None
    assert journey.total_loan_apps == 24

    for season, appearances, minutes in (
        (2023, 24, 1009),
        (2024, 34, 2660),
        (2025, 45, 3263),
    ):
        cell = PlayerSeasonCell.query.filter_by(
            player_api_id=284492,
            season=season,
            source="journey",
            club_api_id=34,
        ).one()
        total = PlayerSeasonTotal.query.filter_by(
            player_api_id=284492,
            season=season,
            level_group="senior",
        ).one()
        assert (cell.appearances, cell.minutes) == (appearances, minutes)
        assert (total.appearances, total.minutes, total.primary_source) == (
            appearances,
            minutes,
            "journey",
        )


def test_hall_incremental_sync_converges_with_full_sync_and_repairs_older_history(app):
    """A current-season refresh also repairs an older stale Hall loan row."""
    seasons = {
        2022: [_stat(49, "Chelsea U21", 6, 500, youth=True)],
        2023: [_stat(34, "Newcastle", 24, 1009)],
        2024: [_stat(34, "Newcastle", 34, 2660)],
        2025: [_stat(34, "Newcastle", 45, 3263)],
    }
    player_id = 284493
    journey, tracked, _entries = _sync(
        player_id,
        "L. Hall Incremental",
        49,
        seasons,
        HALL_TRANSFERS,
    )

    def persisted_state():
        entries = PlayerJourneyEntry.query.filter_by(journey_id=journey.id).all()
        return {
            "tracked": (
                tracked.status,
                tracked.current_club_api_id,
                tracked.current_club_name,
                tracked.sale_fee,
                tracked.is_active,
            ),
            "journey": (
                journey.current_club_api_id,
                journey.current_club_name,
                journey.current_status,
                journey.current_owner_api_id,
                journey.current_owner_name,
                journey.total_loan_apps,
            ),
            "entries": {
                season: (
                    _entry(entries, season, 34).entry_type,
                    _entry(entries, season, 34).transfer_date,
                    _entry(entries, season, 34).transfer_fee,
                )
                for season in (2023, 2024, 2025)
            },
            "rollups": {
                season: (
                    PlayerSeasonTotal.query.filter_by(
                        player_api_id=player_id,
                        season=season,
                        level_group="senior",
                    )
                    .one()
                    .appearances,
                    PlayerSeasonTotal.query.filter_by(
                        player_api_id=player_id,
                        season=season,
                        level_group="senior",
                    )
                    .one()
                    .minutes,
                )
                for season in (2023, 2024, 2025)
            },
        }

    full_state = persisted_state()
    assert full_state["entries"] == {
        2023: ("loan", "2023-08-22", None),
        2024: ("first_team", "2024-07-01", "€ 33M"),
        2025: ("first_team", "2024-07-01", "€ 33M"),
    }

    stale_entry = PlayerJourneyEntry.query.filter_by(
        journey_id=journey.id,
        season=2024,
        club_api_id=34,
    ).one()
    stale_entry.entry_type = "loan"
    stale_entry.transfer_date = "2023-08-22"
    stale_entry.transfer_fee = None
    tracked.status = "on_loan"
    tracked.sale_fee = None
    journey.current_status = "on_loan"
    journey.current_owner_api_id = 49
    journey.current_owner_name = "Chelsea"
    journey.total_loan_apps = 58
    stale_total = PlayerSeasonTotal.query.filter_by(
        player_api_id=player_id,
        season=2024,
        level_group="senior",
    ).one()
    stale_total.appearances = -1
    stale_total.minutes = -1
    db.session.commit()

    incremental_api = _FakeAPI(player_id, "L. Hall Incremental", seasons, HALL_TRANSFERS)
    service = JourneySyncService(incremental_api)
    service._auto_geocode_clubs = lambda synced_journey: None
    synced = service.sync_player(player_id, force_full=False)

    assert synced is not None
    assert synced.sync_error is None
    # In 2026 only 2025 is re-fetched, while all persisted seasons are still
    # reclassified against the single chronological resolution.
    assert incremental_api.player_seasons_requested == [2025]
    assert persisted_state() == full_state


def test_transfer_fetch_failure_preserves_existing_tracked_transfer_state(app, caplog):
    seasons = {
        2023: [_stat(49, "Chelsea U21", 6, 500, youth=True)],
        2025: [_stat(34, "Newcastle", 45, 3263)],
    }
    _seed_transfer_teams(HALL_TRANSFERS)
    chelsea = Team.query.filter_by(team_id=49, season=2025).one()
    journey = PlayerJourney(
        player_api_id=884492,
        player_name="Transfer Fetch Canary",
        current_club_api_id=34,
        current_club_name="Newcastle",
        current_level="First Team",
        academy_club_ids=[49],
        academy_last_seasons={"49": 2023},
        seasons_synced=[2023, 2025],
    )
    db.session.add(journey)
    db.session.flush()
    tracked = TrackedPlayer(
        player_api_id=884492,
        player_name="Transfer Fetch Canary",
        team_id=chelsea.id,
        journey_id=journey.id,
        status="sold",
        current_club_api_id=34,
        current_club_name="Newcastle",
        sale_fee="€ 33M",
        data_source="journey-sync",
        last_academy_season=2023,
        is_active=True,
    )
    db.session.add(tracked)
    db.session.commit()

    service = JourneySyncService(_FailingTransferAPI(884492, "Transfer Fetch Canary", seasons, []))
    service._auto_geocode_clubs = lambda synced_journey: None
    synced = service.sync_player(884492, force_full=True)
    db.session.refresh(tracked)

    assert synced is not None
    assert synced.sync_error is None
    assert synced.last_synced_at is not None
    assert "Failed to get transfers for player 884492" in caplog.text
    assert tracked.is_active is True
    assert tracked.status == "sold"
    assert tracked.sale_fee == "€ 33M"
    assert tracked.current_club_api_id == 34
    assert tracked.current_club_name == "Newcastle"


def test_fresh_active_loan_populates_borrower_and_current_owner(app):
    transfers = [
        _transfer("2026-07-10", "Loan", 49, "Chelsea", 44, "Burnley"),
    ]
    seasons = {
        2024: [_stat(49, "Chelsea U21", 6, 500, youth=True)],
        2026: [_stat(44, "Burnley", 2, 140)],
    }

    journey, tracked, entries = _sync(
        884495,
        "Active Loan Canary",
        49,
        seasons,
        transfers,
    )
    borrower = _entry(entries, 2026, 44)

    assert tracked.status == "on_loan"
    assert tracked.current_club_api_id == 44
    assert tracked.current_club_name == "Burnley"
    assert tracked.sale_fee is None
    assert (borrower.entry_type, borrower.transfer_date, borrower.transfer_fee) == (
        "loan",
        "2026-07-10",
        None,
    )
    assert journey.current_club_api_id == 44
    assert journey.current_club_name == "Burnley"
    assert journey.current_status == "on_loan"
    assert journey.current_owner_api_id == 49
    assert journey.current_owner_name == "Chelsea"


def test_mills_reverse_na_return_clears_status_owner_and_moves_home(app):
    transfers = [
        _transfer("2024-01-08", "N/A", 1338, "Oxford United", 7193, "Everton U21"),
        _transfer("2023-07-27", "Loan", 45, "Everton", 1338, "Oxford United"),
    ]
    seasons = {
        2022: [_stat(45, "Everton U21", 6, 500, youth=True)],
        2023: [_stat(1338, "Oxford United", 10, 800)],
        2025: [_stat(45, "Everton U21", 6, 500, youth=True)],
    }

    journey, tracked, entries = _sync(284187, "S. Mills", 45, seasons, transfers)
    oxford = _entry(entries, 2023, 1338)

    assert tracked.status == "academy"
    assert tracked.sale_fee is None
    assert (oxford.entry_type, oxford.transfer_date, oxford.transfer_fee) == (
        "loan",
        "2023-07-27",
        None,
    )
    # The resolver preserves the provider's raw affiliate id while matching it
    # to Everton's owning organisation for academy-relative classification.
    assert journey.current_club_api_id == 7193
    assert journey.current_club_name == "Everton U21"
    assert journey.current_status is None
    assert journey.current_owner_api_id is None
    assert journey.current_owner_name is None


def test_saadi_same_day_return_then_free_transfer_becomes_permanent(app):
    transfers = [
        _transfer("2024-09-09", "Loan", 67, "Blackburn", 3412, "Ethnikos Achna"),
        _transfer("2025-07-01", "Free Transfer", 67, "Blackburn", 3412, "Ethnikos Achna"),
        _transfer("2025-07-01", "Back from Loan", 3412, "Ethnikos Achna", 67, "Blackburn"),
    ]
    seasons = {
        2023: [_stat(67, "Blackburn U21", 6, 500, youth=True)],
        2024: [_stat(3412, "Ethnikos Achna", 20, 1400)],
        2025: [_stat(3412, "Ethnikos Achna", 24, 1800)],
    }

    journey, tracked, entries = _sync(298095, "J. Saadi", 67, seasons, transfers)
    loan_season = _entry(entries, 2024, 3412)
    permanent_season = _entry(entries, 2025, 3412)

    assert tracked.status == "sold"
    assert tracked.sale_fee == "Free Transfer"
    assert (loan_season.entry_type, loan_season.transfer_date, loan_season.transfer_fee) == (
        "loan",
        "2024-09-09",
        None,
    )
    assert (
        permanent_season.entry_type,
        permanent_season.transfer_date,
        permanent_season.transfer_fee,
    ) == ("first_team", "2025-07-01", "Free Transfer")
    assert (journey.current_club_api_id, journey.current_club_name) == (3412, "Ethnikos Achna")
    assert journey.current_status is None
    assert journey.current_owner_api_id is None
    assert journey.current_owner_name is None


def test_zuccon_reloan_uses_the_new_episode_without_claiming_it_is_current_forever(app):
    transfers = [
        _transfer("2024-08-23", "Loan", 499, "Atalanta", 863, "Juve Stabia"),
        _transfer("2025-09-01", "Loan", 22104, "Atalanta II", 863, "Juve Stabia"),
        _transfer("2025-08-31", "Loan", 499, "Atalanta", 863, "Juve Stabia"),
    ]
    seasons = {
        2023: [_stat(499, "Atalanta U21", 6, 500, youth=True)],
        2024: [_stat(863, "Juve Stabia", 18, 1200)],
        2025: [_stat(863, "Juve Stabia", 22, 1600)],
    }

    journey, tracked, entries = _sync(336639, "F. Zuccon", 499, seasons, transfers)
    first_loan = _entry(entries, 2024, 863)
    reloan = _entry(entries, 2025, 863)

    assert tracked.status == "left"
    assert tracked.sale_fee is None
    assert (first_loan.entry_type, first_loan.transfer_date, first_loan.transfer_fee) == (
        "loan",
        "2024-08-23",
        None,
    )
    assert (reloan.entry_type, reloan.transfer_date, reloan.transfer_fee) == (
        "loan",
        "2025-08-31",
        None,
    )
    assert (journey.current_club_api_id, journey.current_club_name) == (863, "Juve Stabia")
    assert journey.current_status is None
    assert journey.current_owner_api_id is None
    assert journey.current_owner_name is None


def test_aseko_affiliate_return_clears_hannover_as_current_loan(app):
    transfers = [
        _transfer("2025-07-01", "N/A", 166, "Hannover 96", 4674, "Bayern München II"),
        _transfer("2025-02-03", "Loan", 4674, "Bayern München II", 166, "Hannover 96"),
        _transfer("2026-06-29", "Return from loan", 166, "Hannover 96", 157, "Bayern München"),
    ]
    seasons = {
        2023: [_stat(157, "Bayern München U21", 6, 500, youth=True)],
        2024: [_stat(166, "Hannover 96", 11, 850)],
    }

    journey, tracked, entries = _sync(342171, "N. Aséko Nkili", 157, seasons, transfers)
    hannover = _entry(entries, 2024, 166)

    assert tracked.status == "first_team"
    assert tracked.sale_fee is None
    assert (hannover.entry_type, hannover.transfer_date, hannover.transfer_fee) == (
        "loan",
        "2025-02-03",
        None,
    )
    assert (journey.current_club_api_id, journey.current_club_name) == (157, "Bayern München")
    assert journey.current_status is None
    assert journey.current_owner_api_id is None
    assert journey.current_owner_name is None


def test_knauff_and_asllani_conversions_preserve_historical_loans_and_clear_current_owners(app, monkeypatch):
    # Keep the older academy evidence in scope so this regression exercises
    # transfer conversion, not the independently tested academy-window gate.
    monkeypatch.setenv("ACADEMY_WINDOW_YEARS", "5")
    knauff_transfers = [
        _transfer(
            "2023-07-01",
            "€ 5M",
            165,
            "Borussia Dortmund",
            169,
            "Eintracht Frankfurt",
        ),
        _transfer(
            "2022-01-20",
            "Loan",
            165,
            "Borussia Dortmund",
            169,
            "Eintracht Frankfurt",
        ),
    ]
    knauff_seasons = {
        2021: [_stat(165, "Borussia Dortmund U21", 6, 500, youth=True)],
        2022: [_stat(169, "Eintracht Frankfurt", 25, 1800)],
        2023: [_stat(169, "Eintracht Frankfurt", 30, 2200)],
    }
    knauff_journey, knauff, knauff_entries = _sync(
        161922,
        "A. Knauff",
        165,
        knauff_seasons,
        knauff_transfers,
    )

    assert (knauff.status, knauff.sale_fee) == ("sold", "€ 5M")
    assert (
        _entry(knauff_entries, 2022, 169).entry_type,
        _entry(knauff_entries, 2022, 169).transfer_date,
        _entry(knauff_entries, 2022, 169).transfer_fee,
    ) == ("loan", "2022-01-20", None)
    assert (
        _entry(knauff_entries, 2023, 169).entry_type,
        _entry(knauff_entries, 2023, 169).transfer_date,
        _entry(knauff_entries, 2023, 169).transfer_fee,
    ) == ("first_team", "2023-07-01", "€ 5M")
    assert (knauff_journey.current_club_api_id, knauff_journey.current_club_name) == (
        169,
        "Eintracht Frankfurt",
    )
    assert knauff_journey.current_status is None
    assert knauff_journey.current_owner_api_id is None
    assert knauff_journey.current_owner_name is None

    asllani_transfers = [
        _transfer("2023-07-01", "€ 10M", 511, "Empoli", 505, "Inter"),
        _transfer("2022-07-01", "Loan", 511, "Empoli", 505, "Inter"),
        _transfer("2025-08-25", "Loan", 505, "Inter", 503, "Torino"),
        _transfer("2026-01-29", "Return from loan", 503, "Torino", 505, "Inter"),
        _transfer("2026-01-29", "Loan", 505, "Inter", 549, "Beşiktaş"),
        _transfer("2026-06-29", "Return from loan", 549, "Beşiktaş", 505, "Inter"),
    ]
    asllani_seasons = {
        2021: [_stat(511, "Empoli U21", 6, 500, youth=True)],
        2022: [_stat(505, "Inter", 20, 1400)],
        2023: [_stat(505, "Inter", 28, 1900)],
        2025: [
            _stat(503, "Torino", 12, 800),
            _stat(549, "Beşiktaş", 9, 600),
        ],
    }
    asllani_journey, asllani, asllani_entries = _sync(
        275776,
        "K. Asllani",
        511,
        asllani_seasons,
        asllani_transfers,
    )

    inter_loan = _entry(asllani_entries, 2022, 505)
    inter_permanent = _entry(asllani_entries, 2023, 505)
    torino = _entry(asllani_entries, 2025, 503)
    besiktas = _entry(asllani_entries, 2025, 549)
    assert (asllani.status, asllani.sale_fee) == ("sold", "€ 10M")
    assert (inter_loan.entry_type, inter_loan.transfer_date, inter_loan.transfer_fee) == (
        "loan",
        "2022-07-01",
        None,
    )
    assert (
        inter_permanent.entry_type,
        inter_permanent.transfer_date,
        inter_permanent.transfer_fee,
    ) == ("first_team", "2023-07-01", "€ 10M")
    assert (torino.entry_type, torino.transfer_date, torino.transfer_fee) == (
        "loan",
        "2025-08-25",
        None,
    )
    assert (besiktas.entry_type, besiktas.transfer_date, besiktas.transfer_fee) == (
        "loan",
        "2026-01-29",
        None,
    )
    assert (asllani_journey.current_club_api_id, asllani_journey.current_club_name) == (505, "Inter")
    assert asllani_journey.current_status is None
    assert asllani_journey.current_owner_api_id is None
    assert asllani_journey.current_owner_name is None
