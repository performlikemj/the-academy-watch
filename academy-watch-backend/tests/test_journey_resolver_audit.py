"""Audit regressions for journey consumers of durable transfer state."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

from src.models.journey import LEVEL_PRIORITY, PlayerJourney, PlayerJourneyEntry
from src.models.league import Team, db
from src.models.season_rollup import LeagueSeasonConfig, PlayerSeasonCell, PlayerSeasonTotal
from src.models.tracked_player import TrackedPlayer
from src.services.journey_sync import JourneySyncService
from src.services.transfer_events import record_transfer_events
from src.services.transfer_resolver import resolve_transfer_state


def _transfer(transfer_date, transfer_type, out_id, out_name, in_id, in_name):
    return {
        "date": transfer_date,
        "type": transfer_type,
        "teams": {
            "out": {"id": out_id, "name": out_name},
            "in": {"id": in_id, "name": in_name},
        },
    }


def _entry(
    *,
    season,
    club_api_id,
    club_name,
    level="First Team",
    entry_type="first_team",
    transfer_date=None,
    appearances=1,
):
    return SimpleNamespace(
        season=season,
        club_api_id=club_api_id,
        club_name=club_name,
        club_logo=None,
        league_api_id=39,
        league_name="Test League",
        level=level,
        entry_type=entry_type,
        is_youth=level != "First Team",
        is_international=False,
        appearances=appearances,
        goals=0,
        assists=0,
        minutes=90 if appearances else 0,
        sort_priority=LEVEL_PRIORITY.get(level, 0),
        transfer_date=transfer_date,
        transfer_fee=None,
        stats_synced_at=datetime(2026, 6, 24, tzinfo=UTC),
    )


class _SingleSeasonAPI:
    def __init__(self, player_id, stat, *, transfer_error=False):
        self.player_id = player_id
        self.stat = stat
        self.transfer_error = transfer_error

    def _make_request(self, endpoint, params):
        if endpoint == "players/seasons":
            return {"response": [2025]}
        if endpoint == "players":
            return {
                "response": [
                    {
                        "player": {
                            "id": self.player_id,
                            "name": "Audit Player",
                            "birth": {"date": "2000-01-01", "country": "Test"},
                            "nationality": "Test",
                        },
                        "statistics": [self.stat],
                    }
                ]
            }
        raise AssertionError((endpoint, params))

    def get_player_transfers(self, player_id):
        assert player_id == self.player_id
        if self.transfer_error:
            raise RuntimeError("transfer provider unavailable")
        return []


def _stat(team_id, league_id, *, minutes=900):
    return {
        "team": {"id": team_id, "name": "Stable Club Name"},
        "league": {"id": league_id, "name": "Stable League Name", "country": "Test"},
        "games": {"appearences": 10, "minutes": minutes, "position": "Midfielder"},
        "goals": {"total": 1, "assists": 2},
    }


def test_set_current_status_without_transfer_evidence_does_not_guess_from_entries(app):
    service = JourneySyncService(api_client=Mock())
    journey = SimpleNamespace(
        player_api_id=7001,
        current_club_api_id=20,
        current_club_name="Borrower",
        current_status=None,
        current_owner_api_id=None,
        current_owner_name=None,
    )
    entries = [
        _entry(season=2025, club_api_id=20, club_name="Borrower", entry_type="loan"),
        _entry(season=2024, club_api_id=10, club_name="Owner"),
    ]

    applied = service._set_current_status(journey, entries)

    assert applied is False
    assert journey.current_status is None
    assert journey.current_owner_api_id is None
    assert journey.current_owner_name is None


def test_durable_transfer_rows_resolve_current_status_without_provider_io(app):
    service = JourneySyncService(api_client=Mock())
    owner = Team(team_id=10, name="Owner", country="Test", season=2025, is_active=True)
    db.session.add(owner)
    journey = PlayerJourney(
        player_api_id=7002,
        origin_club_api_id=10,
        origin_club_name="Owner",
        current_club_api_id=20,
        current_club_name="Borrower",
    )
    db.session.add(journey)
    db.session.flush()
    entry = PlayerJourneyEntry(
        journey_id=journey.id,
        season=2025,
        club_api_id=20,
        club_name="Borrower",
        level="First Team",
        entry_type="loan",
        is_international=False,
        appearances=1,
    )
    db.session.add(entry)
    record_transfer_events(
        journey.player_api_id,
        [_transfer("2025-08-01", "Loan", 10, "Owner", 20, "Borrower")],
        db.session,
    )
    db.session.commit()

    resolution = service._resolve_durable_transfer_state(
        journey,
        [entry],
        as_of="2026-06-30",
    )
    applied = service._set_current_status(
        journey,
        [entry],
        transfer_resolution=resolution,
    )

    assert resolution is not None
    assert applied is True
    assert journey.current_status == "on_loan"
    assert journey.current_owner_api_id == 10
    assert journey.current_owner_name == "Owner"


def test_calendar_year_borrower_controls_european_parent_loan_boundary(app):
    service = JourneySyncService(database_only=True)
    db.session.add(LeagueSeasonConfig(league_api_id=253, season_type="calendar", rollover_month=1))
    journey = PlayerJourney(
        player_api_id=7008,
        origin_club_api_id=49,
        origin_club_name="European Parent",
        current_club_api_id=2530,
        current_club_name="MLS Borrower",
    )
    db.session.add(journey)
    db.session.flush()
    entry = PlayerJourneyEntry(
        journey_id=journey.id,
        season=2024,
        club_api_id=2530,
        club_name="MLS Borrower",
        league_api_id=253,
        league_name="Major League Soccer",
        level="First Team",
        entry_type="first_team",
        is_international=False,
        appearances=10,
    )
    db.session.add(entry)
    record_transfer_events(
        journey.player_api_id,
        [_transfer("2024-02-01", "Loan", 49, "European Parent", 2530, "MLS Borrower")],
        db.session,
    )
    db.session.commit()

    resolution = service._resolve_durable_transfer_state(journey, [entry], as_of="2024-12-31")
    service._apply_loan_classification([entry], resolution)

    assert resolution is not None
    assert resolution.season_start_month == 1
    assert resolution.on_loan is True
    assert entry.entry_type == "loan"
    assert entry.transfer_date == "2024-02-01"


def test_current_status_matches_name_only_clubs_from_resolver():
    service = JourneySyncService(api_client=Mock())
    journey = SimpleNamespace(
        player_api_id=7006,
        current_club_api_id=999,
        current_club_name="Stale Club",
        current_level="First Team",
        current_status=None,
        current_owner_api_id=None,
        current_owner_name=None,
    )
    resolution = resolve_transfer_state(
        [_transfer("2026-07-02", "Loan", None, "Owner", None, "Borrower U21")],
        as_of="2026-07-16",
    )

    applied = service.apply_resolved_current_state(journey, [], resolution)

    assert applied is True
    assert journey.current_club_api_id is None
    assert journey.current_club_name == "Borrower U21"
    assert journey.current_level == "U21"
    assert journey.current_status == "on_loan"
    assert journey.current_owner_api_id is None
    assert journey.current_owner_name == "Owner"


def test_resolved_release_clears_stale_current_club_status_owner_and_level():
    service = JourneySyncService(api_client=Mock())
    journey = SimpleNamespace(
        player_api_id=7007,
        current_club_api_id=20,
        current_club_name="Stale Borrower",
        current_level="First Team",
        current_status="on_loan",
        current_owner_api_id=10,
        current_owner_name="Stale Owner",
    )
    resolution = resolve_transfer_state(
        [_transfer("2026-07-02", "Released", 10, "Owner", None, None)],
        as_of="2026-07-16",
        initial_owner={"id": 10, "name": "Owner"},
    )

    applied = service.apply_resolved_current_state(journey, [], resolution)

    assert applied is True
    assert journey.current_club_api_id is None
    assert journey.current_club_name is None
    assert journey.current_level is None
    assert journey.current_status is None
    assert journey.current_owner_api_id is None
    assert journey.current_owner_name is None


def test_admin_status_backfill_uses_durable_evidence_and_skips_missing_evidence(app):
    from src.routes.journey import admin_backfill_current_status

    today = datetime.now(UTC).date().isoformat()
    db.session.add(Team(team_id=30, name="Durable Owner", country="Test", season=2025, is_active=True))
    evidenced = PlayerJourney(
        player_api_id=7003,
        origin_club_api_id=30,
        origin_club_name="Durable Owner",
        current_club_api_id=31,
        current_club_name="Current Borrower",
    )
    missing = PlayerJourney(
        player_api_id=7004,
        current_club_api_id=41,
        current_club_name="Historical Borrower",
        current_status="on_loan",
        current_owner_api_id=40,
        current_owner_name="Unproven Owner",
    )
    db.session.add_all([evidenced, missing])
    db.session.flush()
    db.session.add_all(
        [
            PlayerJourneyEntry(
                journey_id=evidenced.id,
                season=2026,
                club_api_id=31,
                club_name="Current Borrower",
                level="First Team",
                entry_type="loan",
                is_international=False,
                appearances=1,
            ),
            PlayerJourneyEntry(
                journey_id=missing.id,
                season=2025,
                club_api_id=41,
                club_name="Historical Borrower",
                level="First Team",
                entry_type="loan",
                is_international=False,
                appearances=1,
            ),
        ]
    )
    record_transfer_events(
        evidenced.player_api_id,
        [_transfer(today, "Loan", 30, "Durable Owner", 31, "Current Borrower")],
        db.session,
    )
    db.session.commit()

    with app.test_request_context(json={"dry_run": False, "limit": 200, "cursor": 0}):
        response = admin_backfill_current_status.__wrapped__()

    payload = response.get_json()
    db.session.expire_all()
    evidenced = PlayerJourney.query.filter_by(player_api_id=7003).one()
    missing = PlayerJourney.query.filter_by(player_api_id=7004).one()

    assert payload["journeys_processed"] == 2
    assert payload["evidence_resolved"] == 1
    assert payload["skipped_no_transfer_evidence"] == 1
    assert payload["on_loan_set"] == 1
    assert evidenced.current_status == "on_loan"
    assert evidenced.current_owner_api_id == 30
    assert missing.current_status == "on_loan"
    assert missing.current_owner_api_id == 40
    assert missing.current_owner_name == "Unproven Owner"


def test_newer_season_stats_without_transfer_date_beat_historical_transfer_state(app):
    service = JourneySyncService(api_client=Mock())
    fresh_stats = _entry(
        season=2025,
        club_api_id=1349,
        club_name="Oldham",
        transfer_date=None,
        appearances=16,
    )
    historical = _entry(
        season=2023,
        club_api_id=19746,
        club_name="Nottingham Forest U21",
        level="U21",
        entry_type="development",
        transfer_date="2024-01-02",
    )
    transfers = [
        _transfer("2023-08-01", "Loan", 65, "Nottingham Forest", 1943, "Cheltenham"),
        _transfer("2024-01-02", "N/A", 1943, "Cheltenham", 19746, "Nottingham Forest U21"),
    ]
    journey = MagicMock(id=7005, player_api_id=7005)

    with (
        patch("src.services.journey_sync.PlayerJourneyEntry") as entry_model,
        patch.object(service, "_compute_academy_club_ids"),
    ):
        entry_model.query.filter_by.return_value.all.return_value = [fresh_stats, historical]
        service._update_journey_aggregates(journey, transfers=transfers, as_of="2026-06-30")

    assert journey.current_club_api_id == 1349
    assert journey.current_club_name == "Oldham"


def test_midseason_permanent_conversion_replaces_loan_classification():
    service = JourneySyncService(api_client=Mock())
    entry = _entry(
        season=2023,
        club_api_id=20,
        club_name="Borrower",
        entry_type="first_team",
    )
    transfers = [
        _transfer("2023-08-01", "Loan", 10, "Owner", 20, "Borrower"),
        _transfer("2024-01-15", "€ 5M", 10, "Owner", 20, "Borrower"),
    ]
    resolution = resolve_transfer_state(transfers, as_of="2024-06-30")

    service._apply_loan_classification([entry], resolution)
    service._apply_permanent_transfer_dates([entry], resolution)

    assert entry.entry_type == "first_team"
    assert entry.transfer_date == "2024-01-15"
    assert entry.transfer_fee == "€ 5M"


def test_failed_transfer_fetch_preserves_metadata_across_club_and_league_id_remaps(app):
    player_id = 7010
    journey = PlayerJourney(
        player_api_id=player_id,
        player_name="Audit Player",
        current_club_api_id=100,
        current_club_name="Stable Club Name",
        current_level="First Team",
        current_status="on_loan",
        current_owner_api_id=10,
        current_owner_name="Owner",
        seasons_synced=[2025],
    )
    db.session.add(journey)
    db.session.flush()
    db.session.add(
        PlayerJourneyEntry(
            journey_id=journey.id,
            player_api_id=player_id,
            season=2025,
            club_api_id=100,
            club_name="Stable Club Name",
            league_api_id=200,
            league_name="Stable League Name",
            level="First Team",
            entry_type="loan",
            is_international=False,
            appearances=4,
            minutes=360,
            transfer_date="2025-08-01",
            transfer_fee="Loan fee",
        )
    )
    db.session.commit()

    service = JourneySyncService(_SingleSeasonAPI(player_id, _stat(101, 201), transfer_error=True))
    service._auto_geocode_clubs = lambda synced_journey: None
    synced = service.sync_player(player_id, force_full=True)

    assert synced is not None
    entry = PlayerJourneyEntry.query.filter_by(player_api_id=player_id, season=2025).one()
    assert (entry.club_api_id, entry.league_api_id) == (101, 201)
    assert (entry.entry_type, entry.transfer_date, entry.transfer_fee) == (
        "loan",
        "2025-08-01",
        "Loan fee",
    )
    assert synced.current_status == "on_loan"
    assert synced.current_owner_api_id == 10


def test_sync_commits_journey_when_affected_rollup_refresh_fails(app, monkeypatch):
    player_id = 7011
    journey = PlayerJourney(player_api_id=player_id, player_name="Before", seasons_synced=[2025])
    db.session.add(journey)
    db.session.flush()
    db.session.add(
        PlayerJourneyEntry(
            journey_id=journey.id,
            player_api_id=player_id,
            season=2025,
            club_api_id=100,
            club_name="Old Club",
            league_api_id=200,
            league_name="Old League",
            level="First Team",
            entry_type="first_team",
            is_international=False,
            appearances=1,
            minutes=90,
        )
    )
    db.session.commit()

    def fail_rollup(*args, **kwargs):
        raise RuntimeError("simulated rollup failure")

    monkeypatch.setattr("src.services.journey_sync.refresh_season_rollup", fail_rollup)
    service = JourneySyncService(_SingleSeasonAPI(player_id, _stat(101, 201, minutes=900)))
    service._auto_geocode_clubs = lambda synced_journey: None

    assert service.sync_player(player_id, force_full=True) is not None

    db.session.expire_all()
    persisted = PlayerJourney.query.filter_by(player_api_id=player_id).one()
    entry = PlayerJourneyEntry.query.filter_by(player_api_id=player_id, season=2025).one()
    assert persisted.player_name == "Audit Player"
    assert persisted.last_synced_at is not None
    assert persisted.sync_error is None
    assert (entry.club_api_id, entry.club_name, entry.minutes) == (
        101,
        "Stable Club Name",
        900,
    )
    assert PlayerSeasonCell.query.filter_by(player_api_id=player_id).count() == 0
    assert PlayerSeasonTotal.query.filter_by(player_api_id=player_id).count() == 0


def test_database_repair_surfaces_rollup_failure_and_rolls_back(app, monkeypatch):
    from src.routes.journey import admin_recompute_academy

    journey = PlayerJourney(
        player_api_id=7012,
        player_name="Repair Rollback",
        total_first_team_apps=999,
    )
    db.session.add(journey)
    db.session.flush()
    db.session.add(
        PlayerJourneyEntry(
            journey_id=journey.id,
            player_api_id=journey.player_api_id,
            season=2025,
            club_api_id=100,
            club_name="Stable Club Name",
            league_api_id=200,
            league_name="Stable League Name",
            level="First Team",
            entry_type="first_team",
            is_international=False,
            appearances=10,
            minutes=900,
        )
    )
    record_transfer_events(
        journey.player_api_id,
        [_transfer("2025-07-01", "Transfer", 99, "Previous Club", 100, "Stable Club Name")],
        db.session,
    )
    db.session.commit()

    def fail_rollup(*args, **kwargs):
        raise RuntimeError("repair rollup failed")

    monkeypatch.setattr("src.services.season_rollup_service.refresh_player", fail_rollup)
    with app.test_request_context(json={"dry_run": False, "limit": 100, "cursor": 0}):
        response = admin_recompute_academy.__wrapped__()

    payload = response.get_json()
    db.session.expire_all()
    persisted = PlayerJourney.query.filter_by(player_api_id=7012).one()

    assert payload["journeys_processed"] == 0
    assert payload["errors"] == 1
    assert payload["durable_reclassified"] == 0
    assert payload["rollup_seasons_refreshed"] == 0
    assert payload["error_examples"] == [{"journey_id": journey.id, "error": "repair rollup failed"}]
    assert persisted.total_first_team_apps == 999


def test_hall_incremental_state_durable_repair_converges_with_rollups_and_is_idempotent(app, monkeypatch):
    from src.routes.journey import admin_recompute_academy

    transfers = [
        _transfer("2024-07-01", "€ 33M", 49, "Chelsea", 34, "Newcastle"),
        _transfer("2023-08-22", "Loan", 49, "Chelsea", 34, "Newcastle"),
    ]
    chelsea = Team(team_id=49, name="Chelsea", country="England", season=2025, is_active=True)
    newcastle = Team(team_id=34, name="Newcastle", country="England", season=2025, is_active=True)
    db.session.add_all([chelsea, newcastle])
    db.session.flush()
    journey = PlayerJourney(
        player_api_id=7013,
        player_name="L. Hall",
        birth_date="2004-01-01",
        origin_club_api_id=49,
        origin_club_name="Chelsea",
        current_club_api_id=34,
        current_club_name="Newcastle",
        current_level="First Team",
        current_status="on_loan",
        current_owner_api_id=49,
        current_owner_name="Chelsea",
        academy_club_ids=[49],
        academy_last_seasons={"49": 2022},
        seasons_synced=[2022, 2023, 2024, 2025],
        total_loan_apps=103,
    )
    db.session.add(journey)
    db.session.flush()

    def stored_entry(season, club_id, club_name, apps, minutes, *, youth=False):
        return PlayerJourneyEntry(
            journey_id=journey.id,
            player_api_id=journey.player_api_id,
            season=season,
            club_api_id=club_id,
            club_name=club_name,
            league_api_id=699 if youth else 39,
            league_name="Premier League 2" if youth else "Premier League",
            league_country="England",
            level="U21" if youth else "First Team",
            entry_type="academy" if youth else "loan",
            is_youth=youth,
            is_international=False,
            appearances=apps,
            minutes=minutes,
            goals=0,
            assists=0,
            sort_priority=LEVEL_PRIORITY["U21" if youth else "First Team"],
            transfer_date=None if youth else "2023-08-22",
        )

    db.session.add_all(
        [
            stored_entry(2022, 49, "Chelsea U21", 6, 500, youth=True),
            stored_entry(2023, 34, "Newcastle", 24, 1009),
            stored_entry(2024, 34, "Newcastle", 34, 2660),
            stored_entry(2025, 34, "Newcastle", 45, 3263),
            TrackedPlayer(
                player_api_id=journey.player_api_id,
                player_name="L. Hall",
                team_id=chelsea.id,
                journey_id=journey.id,
                status="on_loan",
                current_club_api_id=34,
                current_club_name="Newcastle",
                data_source="journey-sync",
                last_academy_season=2022,
                is_active=True,
            ),
            TrackedPlayer(
                player_api_id=journey.player_api_id,
                player_name="L. Hall",
                team_id=newcastle.id,
                journey_id=journey.id,
                status="first_team",
                current_club_api_id=34,
                current_club_name="Newcastle",
                data_source="owning-club",
                is_active=True,
            ),
        ]
    )
    record_transfer_events(journey.player_api_id, transfers, db.session)
    db.session.commit()

    # A DB-only repair must never instantiate or handshake an API client.
    monkeypatch.setattr(
        "src.services.journey_sync.APIFootballClient",
        lambda: (_ for _ in ()).throw(AssertionError("database repair attempted API setup")),
    )

    def run_repair():
        with app.test_request_context(json={"dry_run": False, "limit": 100, "cursor": 0}):
            return admin_recompute_academy.__wrapped__().get_json()

    first_payload = run_repair()
    db.session.expire_all()

    repaired = PlayerJourney.query.filter_by(player_api_id=journey.player_api_id).one()
    entries = PlayerJourneyEntry.query.filter_by(journey_id=repaired.id).order_by(PlayerJourneyEntry.season).all()
    academy_row = TrackedPlayer.query.filter_by(player_api_id=repaired.player_api_id, team_id=chelsea.id).one()
    buyer_row = TrackedPlayer.query.filter_by(player_api_id=repaired.player_api_id, team_id=newcastle.id).one()
    entry_state = [(e.season, e.entry_type, e.transfer_date, e.transfer_fee) for e in entries]

    assert first_payload["errors"] == 0
    assert first_payload["durable_reclassified"] == 1
    assert first_payload["rollup_seasons_refreshed"] == 4
    assert entry_state == [
        (2022, "academy", None, None),
        (2023, "loan", "2023-08-22", None),
        (2024, "first_team", "2024-07-01", "€ 33M"),
        (2025, "first_team", "2024-07-01", "€ 33M"),
    ]
    assert (academy_row.status, academy_row.sale_fee, academy_row.is_active) == ("sold", "€ 33M", True)
    assert buyer_row.is_active is False
    assert (
        repaired.current_club_api_id,
        repaired.current_club_name,
        repaired.current_status,
        repaired.current_owner_api_id,
        repaired.current_owner_name,
        repaired.total_loan_apps,
    ) == (34, "Newcastle", None, None, None, 24)

    for season, appearances, minutes in (
        (2023, 24, 1009),
        (2024, 34, 2660),
        (2025, 45, 3263),
    ):
        cell = PlayerSeasonCell.query.filter_by(
            player_api_id=repaired.player_api_id,
            season=season,
            source="journey",
            club_api_id=34,
        ).one()
        total = PlayerSeasonTotal.query.filter_by(
            player_api_id=repaired.player_api_id,
            season=season,
            level_group="senior",
        ).one()
        assert (cell.appearances, cell.minutes) == (appearances, minutes)
        assert (total.appearances, total.minutes, total.primary_source) == (
            appearances,
            minutes,
            "journey",
        )

    first_snapshot = (
        entry_state,
        academy_row.status,
        academy_row.sale_fee,
        buyer_row.is_active,
        repaired.total_loan_apps,
        [(row.season, row.source, row.club_api_id, row.minutes) for row in PlayerSeasonCell.query.all()],
        [(row.season, row.level_group, row.minutes) for row in PlayerSeasonTotal.query.all()],
    )
    second_payload = run_repair()
    db.session.expire_all()
    second_snapshot = (
        [
            (e.season, e.entry_type, e.transfer_date, e.transfer_fee)
            for e in PlayerJourneyEntry.query.filter_by(journey_id=repaired.id)
            .order_by(PlayerJourneyEntry.season)
            .all()
        ],
        TrackedPlayer.query.filter_by(player_api_id=repaired.player_api_id, team_id=chelsea.id).one().status,
        TrackedPlayer.query.filter_by(player_api_id=repaired.player_api_id, team_id=chelsea.id).one().sale_fee,
        TrackedPlayer.query.filter_by(player_api_id=repaired.player_api_id, team_id=newcastle.id).one().is_active,
        PlayerJourney.query.filter_by(player_api_id=repaired.player_api_id).one().total_loan_apps,
        [(row.season, row.source, row.club_api_id, row.minutes) for row in PlayerSeasonCell.query.all()],
        [(row.season, row.level_group, row.minutes) for row in PlayerSeasonTotal.query.all()],
    )
    assert second_payload["errors"] == 0
    assert first_snapshot == second_snapshot
