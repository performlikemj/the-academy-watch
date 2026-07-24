"""P5 regression coverage for scout-data attribution.

The fixtures in this module are deliberately database-only. They pin the four
remaining contracts from the scout-data-attribution remediation:

* a returned loanee keeps whole-season stats and a post-loan ``first_team`` status;
* the transfer-heal orphan sweep reaches the real journey-sync reactivation path;
* the July academy clock and August stats clock roll independently, with the
  display season falling back until new-season fixtures exist;
* the zero-at-tracked-club quality gauge is deterministic on seeded fixtures.
"""

from datetime import UTC, date, datetime

FIXTURE_SEASON = 2025
PARENT_API_ID = 3301
LOAN_API_ID = 7701
OPPONENT_API_ID = 9901
RETURNED_PLAYER_ID = 303010
ORPHAN_PLAYER_ID = 303011


def _team(api_id: int, name: str, *, season: int = FIXTURE_SEASON):
    from src.models.league import Team, db

    team = Team(
        team_id=api_id,
        name=name,
        country="England",
        season=season,
        logo=f"{api_id}.png",
        is_active=True,
    )
    db.session.add(team)
    db.session.flush()
    return team


def _fixture_appearance(
    player_api_id: int,
    team_api_id: int,
    *,
    fixture_api_id: int,
    season: int = FIXTURE_SEASON,
    minutes: int,
    goals: int = 0,
    played_on: datetime | None = None,
):
    from src.models.league import db
    from src.models.weekly import Fixture, FixturePlayerStats

    fixture = Fixture(
        fixture_id_api=fixture_api_id,
        season=season,
        date_utc=played_on or datetime(season, 9, 1, tzinfo=UTC),
        competition_name="Regression League",
        home_team_api_id=team_api_id,
        away_team_api_id=OPPONENT_API_ID,
        home_goals=goals,
        away_goals=0,
    )
    db.session.add(fixture)
    db.session.flush()
    db.session.add(
        FixturePlayerStats(
            fixture_id=fixture.id,
            player_api_id=player_api_id,
            team_api_id=team_api_id,
            minutes=minutes,
            goals=goals,
            assists=0,
            position="M",
            rating=7.0,
        )
    )


def _seed_returned_loanee():
    """Persist the final state after a loan spell has closed.

    The journey and tracked row both point back to the parent. Most of the
    season's minutes remain at the loan club, with a small parent cameo after
    return. A current-club-only regression therefore reports a plausible but
    wrong 10 minutes instead of the correct cross-club 100.
    """
    from src.models.journey import PlayerJourney, PlayerJourneyEntry
    from src.models.league import db
    from src.models.tracked_player import TrackedPlayer

    parent = _team(PARENT_API_ID, "Parent FC")
    loan = _team(LOAN_API_ID, "Loan FC")
    _team(OPPONENT_API_ID, "Opponent FC")

    journey = PlayerJourney(
        player_api_id=RETURNED_PLAYER_ID,
        player_name="Returned Loanee",
        birth_date="2004-05-10",
        origin_club_api_id=parent.team_id,
        origin_club_name=parent.name,
        current_club_api_id=parent.team_id,
        current_club_name=parent.name,
        current_level="First Team",
        current_status=None,
        current_owner_api_id=None,
        current_owner_name=None,
        academy_club_ids=[parent.team_id],
        academy_last_seasons={str(parent.team_id): FIXTURE_SEASON},
    )
    db.session.add(journey)
    db.session.flush()
    db.session.add_all(
        [
            PlayerJourneyEntry(
                journey_id=journey.id,
                player_api_id=RETURNED_PLAYER_ID,
                season=FIXTURE_SEASON,
                club_api_id=loan.team_id,
                club_name=loan.name,
                league_api_id=2,
                league_name="Championship",
                level="First Team",
                entry_type="loan",
                is_youth=False,
                is_international=False,
                appearances=1,
                minutes=90,
                transfer_date=f"{FIXTURE_SEASON}-08-15",
            ),
            PlayerJourneyEntry(
                journey_id=journey.id,
                player_api_id=RETURNED_PLAYER_ID,
                season=FIXTURE_SEASON,
                club_api_id=parent.team_id,
                club_name=parent.name,
                league_api_id=39,
                league_name="Premier League",
                level="First Team",
                entry_type="first_team",
                is_youth=False,
                is_international=False,
                appearances=1,
                minutes=10,
                transfer_date=f"{FIXTURE_SEASON + 1}-01-31",
            ),
        ]
    )

    tracked = TrackedPlayer(
        player_api_id=RETURNED_PLAYER_ID,
        player_name=journey.player_name,
        position="Midfielder",
        team_id=parent.id,
        status="first_team",
        current_level="First Team",
        current_club_api_id=parent.team_id,
        current_club_name=parent.name,
        current_club_db_id=parent.id,
        data_source="journey-sync",
        data_depth="full_stats",
        journey_id=journey.id,
        last_academy_season=FIXTURE_SEASON,
        is_active=True,
    )
    db.session.add(tracked)
    _fixture_appearance(
        RETURNED_PLAYER_ID,
        loan.team_id,
        fixture_api_id=81001,
        minutes=90,
        goals=1,
        played_on=datetime(2025, 10, 4, tzinfo=UTC),
    )
    _fixture_appearance(
        RETURNED_PLAYER_ID,
        parent.team_id,
        fixture_api_id=81002,
        minutes=10,
        played_on=datetime(2026, 2, 7, tzinfo=UTC),
    )
    db.session.commit()
    return tracked


def test_returned_loanee_keeps_cross_club_stats_and_post_loan_status(app):
    from src.models.tracked_player import TrackedPlayer
    from src.routes.scout import _base_scout_query, _row_to_dict

    tracked = _seed_returned_loanee()

    assert tracked.current_club_api_id == PARENT_API_ID
    assert tracked.journey.current_status is None
    assert tracked.status == "first_team"
    assert tracked.compute_stats() == {
        "appearances": 2,
        "goals": 1,
        "assists": 0,
        "minutes_played": 100,
        "saves": 0,
        "yellows": 0,
        "reds": 0,
        "stats_coverage": "full",
    }

    query, columns = _base_scout_query(allow_rollup=False)
    row = query.filter(
        TrackedPlayer.player_api_id == RETURNED_PLAYER_ID,
        columns["effective_status"] == "first_team",
        columns["minutes_played"] == 100,
    ).one()
    payload = _row_to_dict(row)

    assert payload["appearances"] == 2
    assert payload["minutes_played"] == 100
    assert payload["goals"] == 1
    assert payload["status"] == "first_team"
    assert payload["pathway_status"] == "first_team"
    assert payload["primary_team_api_id"] == PARENT_API_ID
    assert payload["loan_team_api_id"] == PARENT_API_ID


class _JourneyFixtureAPI:
    """Strict fixture client for a real ``JourneySyncService.sync_player`` call."""

    def __init__(self, player_api_id: int, parent_api_id: int, season: int):
        self.player_api_id = player_api_id
        self.parent_api_id = parent_api_id
        self.season = season
        self.calls: list[tuple[str, object]] = []

    def _make_request(self, endpoint, params):
        self.calls.append((endpoint, dict(params)))
        if endpoint == "players/seasons":
            assert params == {"player": self.player_api_id}
            return {"response": [self.season]}
        if endpoint == "players":
            assert params == {"id": self.player_api_id, "season": self.season}
            return {
                "response": [
                    {
                        "player": {
                            "id": self.player_api_id,
                            "name": "Reactivated Academy Player",
                            "photo": None,
                            "birth": {"date": "2006-02-03", "country": "England"},
                            "nationality": "England",
                        },
                        "statistics": [
                            {
                                "team": {
                                    "id": self.parent_api_id,
                                    "name": "Origin FC U21",
                                    "logo": None,
                                },
                                "league": {
                                    "id": 699,
                                    "name": "Premier League 2",
                                    "country": "England",
                                    "logo": None,
                                },
                                "games": {
                                    "appearences": 5,
                                    "lineups": 5,
                                    "minutes": 450,
                                    "position": "Midfielder",
                                    "rating": "7.1",
                                },
                                "goals": {"total": 0, "assists": 1},
                            }
                        ],
                    }
                ]
            }
        raise AssertionError(f"Unexpected journey fixture endpoint: {endpoint}")

    def get_player_transfers(self, player_api_id):
        self.calls.append(("transfers", player_api_id))
        assert player_api_id == self.player_api_id
        return []


class _HealFixtureAPI:
    """Strict fixture client for transfer-heal prefetches."""

    def __init__(self, player_api_id: int, parent_api_id: int):
        self.player_api_id = player_api_id
        self.parent_api_id = parent_api_id
        self.calls: list[tuple[str, object]] = []

    def batch_get_player_transfers(self, player_api_ids):
        ids = list(player_api_ids)
        self.calls.append(("batch_transfers", ids))
        assert ids == [self.player_api_id]
        return {self.player_api_id: []}

    def get_team_players(self, club_id, season=None):
        self.calls.append(("squad", (club_id, season)))
        assert club_id == self.parent_api_id
        return [{"player": {"id": self.player_api_id}}]


def test_reactivation_sweep_leaves_no_in_window_academy_orphan(app, monkeypatch):
    import src.services.transfer_heal_service as transfer_heal
    from src.models.journey import PlayerJourney
    from src.models.league import db
    from src.models.tracked_player import TrackedPlayer
    from src.services.journey_sync import JourneySyncService
    from src.utils.academy_window import current_academy_season

    recent = current_academy_season()
    parent = _team(PARENT_API_ID, "Origin FC", season=recent)
    journey = PlayerJourney(
        player_api_id=ORPHAN_PLAYER_ID,
        player_name="Orphaned Academy Player",
        birth_date="2006-02-03",
        current_club_api_id=parent.team_id,
        current_club_name=parent.name,
        current_level="First Team",
        academy_club_ids=[parent.team_id],
        academy_last_seasons={str(parent.team_id): recent},
    )
    db.session.add(journey)
    db.session.flush()
    orphan = TrackedPlayer(
        player_api_id=ORPHAN_PLAYER_ID,
        player_name=journey.player_name,
        team_id=parent.id,
        status="first_team",
        current_level="First Team",
        current_club_api_id=parent.team_id,
        current_club_name=parent.name,
        current_club_db_id=parent.id,
        data_source="owning-club",
        data_depth="full_stats",
        journey_id=journey.id,
        last_academy_season=None,
        pinned_parent=False,
        is_active=False,
    )
    db.session.add(orphan)
    db.session.commit()
    original_journey_id = journey.id

    journey_api = _JourneyFixtureAPI(ORPHAN_PLAYER_ID, PARENT_API_ID, recent)
    heal_api = _HealFixtureAPI(ORPHAN_PLAYER_ID, PARENT_API_ID)

    def fixture_sync_service():
        service = JourneySyncService(api_client=journey_api)
        service._auto_geocode_clubs = lambda synced_journey: None
        return service

    monkeypatch.setattr(transfer_heal, "JourneySyncService", fixture_sync_service)
    monkeypatch.setattr(transfer_heal, "APIFootballClient", lambda: heal_api)

    result = transfer_heal.refresh_and_heal(
        resync_journeys=True,
        dry_run=False,
        cascade_fixtures=False,
        orphan_budget=1,
    )

    db.session.expire_all()
    rows = TrackedPlayer.query.filter_by(
        player_api_id=ORPHAN_PLAYER_ID,
        team_id=parent.id,
    ).all()

    assert result["orphans_requeued"] == 1
    assert result["journeys_resynced"] == 1
    assert len(rows) == 1
    assert TrackedPlayer.query.filter_by(player_api_id=ORPHAN_PLAYER_ID, is_active=False).count() == 0
    assert rows[0].is_active is True
    assert rows[0].data_source == "journey-sync"
    assert rows[0].status == "academy"
    assert rows[0].last_academy_season == recent
    assert rows[0].journey_id == original_journey_id
    assert journey_api.calls == [
        ("players/seasons", {"player": ORPHAN_PLAYER_ID}),
        ("transfers", ORPHAN_PLAYER_ID),
        ("players", {"id": ORPHAN_PLAYER_ID, "season": recent}),
    ]
    assert heal_api.calls == [
        ("batch_transfers", [ORPHAN_PLAYER_ID]),
        ("squad", (PARENT_API_ID, None)),
    ]


class _FrozenDate(date):
    frozen_today = date(2026, 7, 31)

    @classmethod
    def today(cls):
        return cls.frozen_today


def test_august_rollover_keeps_shared_stats_and_academy_clocks_distinct(app, monkeypatch):
    import src.utils.academy_window as academy_window
    from src.models.league import db
    from src.models.weekly import Fixture

    monkeypatch.setenv("ACADEMY_WINDOW_YEARS", "4")
    monkeypatch.setattr(academy_window, "date", _FrozenDate)
    db.session.add(
        Fixture(
            fixture_id_api=82001,
            season=2025,
            date_utc=datetime(2025, 9, 1, tzinfo=UTC),
            home_team_api_id=PARENT_API_ID,
            away_team_api_id=LOAN_API_ID,
        )
    )
    db.session.commit()

    expectations = [
        # day, stats clock, academy clock, academy-window start, display season
        (date(2026, 6, 30), 2025, 2025, 2021, 2025),
        (date(2026, 7, 1), 2025, 2026, 2022, 2025),
        (date(2026, 7, 31), 2025, 2026, 2022, 2025),
        (date(2026, 8, 1), 2026, 2026, 2022, 2025),
    ]
    for frozen_day, stats_season, academy_season, window_start, display_season in expectations:
        _FrozenDate.frozen_today = frozen_day
        assert academy_window.current_stats_season() == stats_season
        assert academy_window.current_academy_season() == academy_season
        assert academy_window.academy_window_start() == window_start
        assert academy_window.stats_season_with_data(db.session) == display_season

    db.session.add(
        Fixture(
            fixture_id_api=82002,
            season=2026,
            date_utc=datetime(2026, 8, 20, tzinfo=UTC),
            home_team_api_id=PARENT_API_ID,
            away_team_api_id=LOAN_API_ID,
        )
    )
    db.session.commit()
    assert academy_window.stats_season_with_data(db.session) == 2026


def _zero_at_tracked_club_count(db_session, *, today: date) -> int:
    """Fixture-only data-quality gauge from the P5 ledger.

    Count distinct active players who have positive minutes in the resolved
    display season and zero minutes at their tracked current club. A missing
    ``current_club_api_id`` is an attribution gap and therefore has zero
    current-club minutes, matching the ledger's reference gauge.

    ``TrackedPlayer.team_id`` is the academy parent's database key; the
    comparable provider IDs are ``current_club_api_id`` and
    ``FixturePlayerStats.team_api_id``.
    """
    from sqlalchemy import case, func
    from src.models.tracked_player import TrackedPlayer
    from src.models.weekly import Fixture, FixturePlayerStats
    from src.utils.academy_window import stats_season_with_data

    season = stats_season_with_data(db_session, today)
    minutes = func.coalesce(FixturePlayerStats.minutes, 0)
    at_tracked_club = func.coalesce(
        func.sum(case((FixturePlayerStats.team_api_id == TrackedPlayer.current_club_api_id, minutes), else_=0)),
        0,
    )
    season_minutes = func.coalesce(func.sum(minutes), 0)
    rows = (
        db_session.query(TrackedPlayer.player_api_id)
        .join(
            FixturePlayerStats,
            FixturePlayerStats.player_api_id == TrackedPlayer.player_api_id,
        )
        .join(Fixture, Fixture.id == FixturePlayerStats.fixture_id)
        .filter(
            TrackedPlayer.is_active.is_(True),
            Fixture.season == season,
        )
        .group_by(
            TrackedPlayer.player_api_id,
            TrackedPlayer.current_club_api_id,
        )
        .having(at_tracked_club == 0, season_minutes > 0)
        .distinct()
        .all()
    )
    return len(rows)


def _quality_gauge_player(player_api_id: int, parent, *, current_club_api_id, is_active=True):
    from src.models.league import db
    from src.models.tracked_player import TrackedPlayer

    tracked = TrackedPlayer(
        player_api_id=player_api_id,
        player_name=f"Gauge Player {player_api_id}",
        team_id=parent.id,
        status="first_team",
        current_club_api_id=current_club_api_id,
        data_source="journey-sync",
        data_depth="full_stats",
        is_active=is_active,
    )
    db.session.add(tracked)
    return tracked


def test_zero_at_tracked_club_gauge_counts_only_seeded_current_season_mismatches(app):
    from src.models.league import db

    parent = _team(PARENT_API_ID, "Gauge Parent FC")
    _team(LOAN_API_ID, "Gauge Loan FC")
    _team(OPPONENT_API_ID, "Gauge Opponent FC")
    gauge_day = date(2026, 8, 1)

    # Active returnee: all current display-season minutes are elsewhere.
    _quality_gauge_player(501, parent, current_club_api_id=PARENT_API_ID)
    _fixture_appearance(501, LOAN_API_ID, fixture_api_id=85001, minutes=90)
    db.session.commit()
    assert _zero_at_tracked_club_count(db.session, today=gauge_day) == 1

    # Healthy attribution: minutes are at the stated current club.
    _quality_gauge_player(502, parent, current_club_api_id=LOAN_API_ID)
    _fixture_appearance(502, LOAN_API_ID, fixture_api_id=85002, minutes=90)
    db.session.commit()
    assert _zero_at_tracked_club_count(db.session, today=gauge_day) == 1

    # Inactive rows do not contribute to the operational gauge.
    _quality_gauge_player(503, parent, current_club_api_id=PARENT_API_ID, is_active=False)
    _fixture_appearance(503, LOAN_API_ID, fixture_api_id=85003, minutes=90)
    db.session.commit()
    assert _zero_at_tracked_club_count(db.session, today=gauge_day) == 1

    # Any positive current-club minutes make this a multi-club season, not a zero-at-club mismatch.
    _quality_gauge_player(504, parent, current_club_api_id=PARENT_API_ID)
    _fixture_appearance(504, PARENT_API_ID, fixture_api_id=85004, minutes=10)
    _fixture_appearance(504, LOAN_API_ID, fixture_api_id=85005, minutes=80)
    db.session.commit()
    assert _zero_at_tracked_club_count(db.session, today=gauge_day) == 1

    # Missing current-club attribution is also zero-at-club when season minutes exist.
    _quality_gauge_player(505, parent, current_club_api_id=None)
    _fixture_appearance(505, LOAN_API_ID, fixture_api_id=85006, minutes=90)
    db.session.commit()
    assert _zero_at_tracked_club_count(db.session, today=gauge_day) == 2

    # A mismatch outside the resolved display season is ignored.
    _quality_gauge_player(506, parent, current_club_api_id=PARENT_API_ID)
    _fixture_appearance(
        506,
        LOAN_API_ID,
        fixture_api_id=85007,
        season=FIXTURE_SEASON - 1,
        minutes=90,
    )
    db.session.commit()
    assert _zero_at_tracked_club_count(db.session, today=gauge_day) == 2
