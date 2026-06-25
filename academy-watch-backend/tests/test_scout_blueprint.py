"""Tests for scout blueprint endpoints in src/routes/scout.py."""

import os
from datetime import datetime

import pytest
from flask import Flask
from src.models.journey import PlayerJourney
from src.models.league import League, PlayerStatsCache, Team, db
from src.models.tracked_player import TrackedPlayer
from src.models.weekly import Fixture, FixturePlayerStats


@pytest.fixture
def scout_app():
    """Create a minimal Flask app with scout blueprint registered."""
    os.environ.setdefault("SKIP_API_HANDSHAKE", "1")
    os.environ.setdefault("API_USE_STUB_DATA", "true")

    from src.routes.scout import scout_bp

    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret-key",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        RATELIMIT_ENABLED=False,
    )

    db.init_app(app)
    app.register_blueprint(scout_bp, url_prefix="/api")

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def scout_client(scout_app):
    return scout_app.test_client()


@pytest.fixture
def seeded_players(scout_app):
    """Seed parent club, loan clubs, tracked players, and stats."""
    with scout_app.app_context():
        league = League(
            league_id=39, name="Premier League", country="England", season=2025, is_european_top_league=True
        )
        db.session.add(league)
        db.session.flush()

        parent = Team(
            team_id=33, name="Manchester United", country="England", season=2025, league_id=league.id, is_active=True
        )
        loan_club = Team(
            team_id=901, name="Loan FC", country="Brazil", season=2025, league_id=league.id, is_active=True
        )
        db.session.add_all([parent, loan_club])
        db.session.flush()

        journey = PlayerJourney(
            player_api_id=1001,
            player_name="Alfie Striker",
            total_first_team_apps=5,
            total_youth_apps=40,
            total_loan_apps=20,
            total_goals=30,
            total_assists=11,
            first_team_debut_season=2024,
            first_team_debut_club="Manchester United",
        )
        db.session.add(journey)
        db.session.flush()

        striker = TrackedPlayer(
            player_api_id=1001,
            player_name="Alfie Striker",
            position="Attacker",
            nationality="England",
            age=19,
            team_id=parent.id,
            status="on_loan",
            current_club_api_id=901,
            current_club_name="Loan FC",
            current_club_db_id=loan_club.id,
            data_depth="full_stats",
            journey_id=journey.id,
            is_active=True,
        )
        midfielder = TrackedPlayer(
            player_api_id=1002,
            player_name="Billy Passer",
            position="Midfielder",
            nationality="Brazil",
            age=21,
            team_id=parent.id,
            status="on_loan",
            current_club_api_id=901,
            current_club_name="Loan FC",
            current_club_db_id=loan_club.id,
            data_depth="full_stats",
            is_active=True,
        )
        # Limited-coverage player: stats only in PlayerStatsCache
        keeper = TrackedPlayer(
            player_api_id=1003,
            player_name="Charlie Gloves",
            position="Goalkeeper",
            nationality="Japan",
            age=18,
            team_id=parent.id,
            status="on_loan",
            current_club_api_id=902,
            current_club_name="Far FC",
            data_depth="events_only",
            is_active=True,
        )
        # Duplicate row for striker under an owning-club source — must be deduped away
        striker_dupe = TrackedPlayer(
            player_api_id=1001,
            player_name="Alfie Striker",
            position="Attacker",
            nationality="England",
            age=19,
            team_id=loan_club.id,
            status="on_loan",
            current_club_api_id=901,
            current_club_name="Loan FC",
            data_source="owning-club",
            data_depth="full_stats",
            is_active=True,
        )
        # Inactive player — must never appear
        ghost = TrackedPlayer(
            player_api_id=1004,
            player_name="Danny Ghost",
            position="Defender",
            age=20,
            team_id=parent.id,
            status="released",
            is_active=False,
        )
        db.session.add_all([striker, midfielder, keeper, striker_dupe, ghost])

        # Fixtures + per-match stats for striker (2 games) and midfielder (1 game)
        fixtures = []
        for i in range(2):
            fixture = Fixture(
                fixture_id_api=5000 + i,
                season=2025,
                home_team_api_id=901,
                away_team_api_id=950 + i,
                date_utc=datetime(2025, 9, 1 + 7 * i),
            )
            fixtures.append(fixture)
        db.session.add_all(fixtures)
        db.session.flush()

        db.session.add_all(
            [
                FixturePlayerStats(
                    fixture_id=fixtures[0].id,
                    player_api_id=1001,
                    team_api_id=901,
                    minutes=90,
                    goals=2,
                    assists=1,
                    rating=8.2,
                    shots_total=5,
                    shots_on=3,
                    passes_key=2,
                    dribbles_success=4,
                    tackles_total=1,
                    duels_won=6,
                ),
                FixturePlayerStats(
                    fixture_id=fixtures[1].id,
                    player_api_id=1001,
                    team_api_id=901,
                    minutes=80,
                    goals=1,
                    assists=0,
                    rating=7.0,
                    shots_total=2,
                    shots_on=1,
                    passes_key=1,
                    dribbles_success=2,
                    tackles_total=0,
                    duels_won=3,
                ),
                FixturePlayerStats(
                    fixture_id=fixtures[0].id,
                    player_api_id=1002,
                    team_api_id=901,
                    minutes=90,
                    goals=0,
                    assists=2,
                    rating=7.5,
                    passes_total=70,
                    passes_key=4,
                    tackles_total=3,
                ),
            ]
        )

        # Cache stats for limited-coverage keeper (two seasons; latest must win)
        db.session.add_all(
            [
                PlayerStatsCache(
                    player_api_id=1003,
                    team_api_id=902,
                    season=2024,
                    appearances=10,
                    goals=0,
                    assists=0,
                    minutes_played=900,
                    saves=30,
                ),
                PlayerStatsCache(
                    player_api_id=1003,
                    team_api_id=902,
                    season=2025,
                    appearances=12,
                    goals=0,
                    assists=1,
                    minutes_played=1080,
                    saves=41,
                ),
            ]
        )
        db.session.commit()


class TestScoutPlayers:
    def test_browse_returns_deduped_players_with_stats(self, scout_client, seeded_players):
        resp = scout_client.get("/api/scout/players")
        assert resp.status_code == 200
        data = resp.get_json()
        ids = [p["player_id"] for p in data["players"]]
        assert ids.count(1001) == 1  # owning-club duplicate removed
        assert 1004 not in ids  # inactive excluded
        assert data["total"] == 3

        striker = next(p for p in data["players"] if p["player_id"] == 1001)
        assert striker["goals"] == 3
        assert striker["assists"] == 1
        assert striker["minutes_played"] == 170
        assert striker["appearances"] == 2
        assert striker["avg_rating"] == pytest.approx(7.6)
        # Preferred row is the academy-origin one (parent = Manchester United)
        assert striker["primary_team_name"] == "Manchester United"

    def test_cache_fallback_uses_latest_season(self, scout_client, seeded_players):
        resp = scout_client.get("/api/scout/players?position=Goalkeeper")
        data = resp.get_json()
        assert data["total"] == 1
        keeper = data["players"][0]
        assert keeper["player_id"] == 1003
        assert keeper["appearances"] == 12
        assert keeper["minutes_played"] == 1080

    def test_sort_by_goals(self, scout_client, seeded_players):
        resp = scout_client.get("/api/scout/players?sort=goals")
        data = resp.get_json()
        assert data["players"][0]["player_id"] == 1001

    def test_sort_by_assists_puts_midfielder_first(self, scout_client, seeded_players):
        resp = scout_client.get("/api/scout/players?sort=assists")
        data = resp.get_json()
        assert data["players"][0]["player_id"] == 1002

    def test_filter_by_age(self, scout_client, seeded_players):
        resp = scout_client.get("/api/scout/players?max_age=19")
        data = resp.get_json()
        ids = {p["player_id"] for p in data["players"]}
        assert ids == {1001, 1003}

    def test_filter_by_nationality(self, scout_client, seeded_players):
        resp = scout_client.get("/api/scout/players?nationality=brazil")
        data = resp.get_json()
        assert [p["player_id"] for p in data["players"]] == [1002]

    def test_search_by_name(self, scout_client, seeded_players):
        resp = scout_client.get("/api/scout/players?search=gloves")
        data = resp.get_json()
        assert [p["player_id"] for p in data["players"]] == [1003]

    def test_min_minutes_filter(self, scout_client, seeded_players):
        resp = scout_client.get("/api/scout/players?min_minutes=200")
        data = resp.get_json()
        assert [p["player_id"] for p in data["players"]] == [1003]

    def test_per90_sort_applies_minutes_floor(self, scout_client, seeded_players):
        resp = scout_client.get("/api/scout/players?sort=per90")
        data = resp.get_json()
        # Only the keeper has >= 270 minutes
        assert [p["player_id"] for p in data["players"]] == [1003]

    def test_pagination(self, scout_client, seeded_players):
        resp = scout_client.get("/api/scout/players?per_page=2&page=2&sort=name")
        data = resp.get_json()
        assert data["total"] == 3
        assert data["total_pages"] == 2
        assert len(data["players"]) == 1

    def test_invalid_position_rejected(self, scout_client, seeded_players):
        resp = scout_client.get("/api/scout/players?position=Striker")
        assert resp.status_code == 400

    def test_invalid_status_rejected(self, scout_client, seeded_players):
        resp = scout_client.get("/api/scout/players?status=banana")
        assert resp.status_code == 400

    def test_invalid_sort_rejected(self, scout_client, seeded_players):
        resp = scout_client.get("/api/scout/players?sort=banana")
        assert resp.status_code == 400

    def test_status_filter(self, scout_client, seeded_players):
        resp = scout_client.get("/api/scout/players?status=on_loan")
        data = resp.get_json()
        assert data["total"] == 3
        resp = scout_client.get("/api/scout/players?status=first_team")
        assert resp.get_json()["total"] == 0


class TestScoutLeaderboards:
    def test_leaderboards_shape_and_order(self, scout_client, seeded_players):
        resp = scout_client.get("/api/scout/leaderboards?limit=5")
        assert resp.status_code == 200
        boards = resp.get_json()["leaderboards"]
        assert set(boards.keys()) == {"top_scorers", "top_assists", "most_minutes", "best_per90"}
        assert boards["top_scorers"][0]["player_id"] == 1001
        assert boards["top_assists"][0]["player_id"] == 1002
        assert boards["most_minutes"][0]["player_id"] == 1003
        # per-90 board enforces the minutes floor
        assert [p["player_id"] for p in boards["best_per90"]] == [1003]

    def test_leaderboards_respect_filters(self, scout_client, seeded_players):
        resp = scout_client.get("/api/scout/leaderboards?position=Midfielder")
        boards = resp.get_json()["leaderboards"]
        assert [p["player_id"] for p in boards["top_assists"]] == [1002]
        assert boards["top_scorers"][0]["player_id"] == 1002


class TestScoutCompare:
    def test_compare_two_players(self, scout_client, seeded_players):
        resp = scout_client.get("/api/scout/compare?ids=1001,1002")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["players"]) == 2
        striker = next(p for p in data["players"] if p["profile"]["player_id"] == 1001)
        assert striker["totals"]["goals"] == 3
        assert striker["totals"]["shots_total"] == 7
        assert striker["totals"]["key_passes"] == 3
        assert striker["per90"]["goals"] == pytest.approx(1.59, abs=0.01)
        assert striker["career"]["youth_apps"] == 40
        # Dedup: profile comes from academy-origin row
        assert striker["profile"]["primary_team_name"] == "Manchester United"

    def test_compare_limited_coverage_fallback(self, scout_client, seeded_players):
        resp = scout_client.get("/api/scout/compare?ids=1003")
        data = resp.get_json()
        keeper = data["players"][0]
        assert keeper["totals"]["appearances"] == 12
        assert keeper["totals"]["saves"] == 41

    def test_compare_missing_and_invalid(self, scout_client, seeded_players):
        resp = scout_client.get("/api/scout/compare?ids=1001,99999")
        data = resp.get_json()
        assert data["missing_ids"] == [99999]

        assert scout_client.get("/api/scout/compare").status_code == 400
        assert scout_client.get("/api/scout/compare?ids=a,b").status_code == 400
        assert scout_client.get("/api/scout/compare?ids=1,2,3,4,5").status_code == 400


class TestRecentForm:
    def test_browse_includes_recent_form_newest_first(self, scout_client, seeded_players):
        resp = scout_client.get("/api/scout/players?position=Attacker")
        striker = resp.get_json()["players"][0]
        form = striker["recent_form"]
        assert len(form) == 2
        # Newest match (Sep 8: 80 mins, 1 goal) first
        assert form[0]["minutes"] == 80
        assert form[0]["goals"] == 1
        assert form[1]["minutes"] == 90
        assert form[1]["goals"] == 2
        assert form[0]["date"] > form[1]["date"]

    def test_player_without_fixture_stats_gets_empty_form(self, scout_client, seeded_players):
        resp = scout_client.get("/api/scout/players?position=Goalkeeper")
        keeper = resp.get_json()["players"][0]
        assert keeper["recent_form"] == []


class _FakeApiClient:
    current_season_start_year = 2025

    def get_player_injuries(self, player_id, season=None):
        if player_id != 1001:
            return []
        return [
            {
                "player": {"id": 1001, "type": "Missing Fixture", "reason": "Knee Injury"},
                "fixture": {"id": 7001, "date": "2025-10-04T14:00:00+00:00"},
                "team": {"id": 901, "name": "Loan FC", "logo": "https://example.com/loanfc.png"},
                "league": {"name": "Premier League"},
            },
            {
                "player": {"id": 1001, "type": "Missing Fixture", "reason": "Knee Injury"},
                "fixture": {"id": 7002, "date": "2025-10-11T14:00:00+00:00"},
                "team": {"id": 901, "name": "Loan FC", "logo": "https://example.com/loanfc.png"},
                "league": {"name": "Premier League"},
            },
        ]


class TestCompareAvailability:
    def test_compare_with_availability(self, scout_client, seeded_players, monkeypatch):
        import src.routes.scout as scout_module

        monkeypatch.setattr(scout_module, "_get_api_client", lambda: _FakeApiClient())
        resp = scout_client.get("/api/scout/compare?ids=1001,1002&include_availability=true")
        data = resp.get_json()
        striker = next(p for p in data["players"] if p["profile"]["player_id"] == 1001)
        midfielder = next(p for p in data["players"] if p["profile"]["player_id"] == 1002)
        assert striker["availability"] == {"total_absences": 2, "last_reason": "Knee Injury"}
        assert midfielder["availability"] == {"total_absences": 0, "last_reason": None}

    def test_compare_without_flag_omits_availability(self, scout_client, seeded_players):
        resp = scout_client.get("/api/scout/compare?ids=1001")
        assert resp.get_json()["players"][0]["availability"] is None


class TestPlayerAvailabilityEndpoint:
    @pytest.fixture
    def availability_client(self, monkeypatch):
        from flask import Flask
        from src.routes import players as players_module

        monkeypatch.setattr(players_module, "_get_api_client", lambda: _FakeApiClient())
        app = Flask(__name__)
        app.config.update(TESTING=True)
        app.register_blueprint(players_module.players_bp, url_prefix="/api")
        return app.test_client()

    def test_availability_normalizes_and_summarizes(self, availability_client):
        resp = availability_client.get("/api/players/1001/availability")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["season"] == 2025
        assert data["summary"]["total_absences"] == 2
        assert data["summary"]["by_reason"] == {"Knee Injury": 2}
        # Sorted newest first
        assert data["absences"][0]["fixture_id"] == 7002
        assert data["absences"][0]["reason"] == "Knee Injury"
        assert data["absences"][0]["team_name"] == "Loan FC"

    def test_availability_empty_for_unknown_player(self, availability_client):
        resp = availability_client.get("/api/players/9999/availability")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["absences"] == []
        assert data["summary"]["total_absences"] == 0
        assert data["summary"]["last_absence"] is None


@pytest.fixture
def current_situation_seeded(scout_app):
    """A Rijkhoff-like player: a Borussia Dortmund academy product, 'sold'
    relative to Dortmund, but ACTUALLY on loan at Almere City FROM Ajax.
    journey.current_status holds that player-level truth."""
    with scout_app.app_context():
        league = League(league_id=78, name="Bundesliga", country="Germany", season=2025)
        db.session.add(league)
        db.session.flush()
        dortmund = Team(
            team_id=165, name="Borussia Dortmund", country="Germany", season=2025, league_id=league.id, is_active=True
        )
        almere = Team(
            team_id=910, name="Almere City FC", country="Netherlands", season=2025, league_id=league.id, is_active=True
        )
        db.session.add_all([dortmund, almere])
        db.session.flush()

        journey = PlayerJourney(
            player_api_id=2001,
            player_name="Julian Rijkhoff",
            current_club_api_id=910,
            current_club_name="Almere City FC",
            current_status="on_loan",
            current_owner_api_id=194,
            current_owner_name="Ajax",
        )
        db.session.add(journey)
        db.session.flush()

        rijkhoff = TrackedPlayer(
            player_api_id=2001,
            player_name="Julian Rijkhoff",
            position="Midfielder",
            nationality="Netherlands",
            age=20,
            team_id=dortmund.id,
            status="sold",  # academy-relative: Dortmund sold him
            current_club_api_id=910,
            current_club_name="Almere City FC",
            current_club_db_id=almere.id,
            data_depth="full_stats",
            journey_id=journey.id,
            is_active=True,
        )
        db.session.add(rijkhoff)
        db.session.commit()


class TestCurrentSituationOverride:
    def test_browse_reflects_actual_current_situation(self, scout_client, current_situation_seeded):
        resp = scout_client.get("/api/scout/players?search=Rijkhoff")
        data = resp.get_json()
        assert len(data["players"]) == 1
        player = data["players"][0]
        # Academy-relative status was 'sold'; actual situation is an active loan
        assert player["status"] == "on_loan"
        # CLUB column reads current club + OWNING club (Ajax), not academy
        assert player["loan_team_name"] == "Almere City FC"
        assert player["primary_team_name"] == "Borussia Dortmund"
        assert player["owner_team_name"] == "Ajax"
        assert player["owner_team_id"] == 194

    def test_status_filter_tracks_current_situation(self, scout_client, current_situation_seeded):
        # Filtering by the actual current status surfaces him…
        on_loan = scout_client.get("/api/scout/players?status=on_loan").get_json()
        assert [p["player_id"] for p in on_loan["players"]] == [2001]
        # …and the academy-relative 'sold' does not, so the filter never
        # disagrees with the status the row displays.
        sold = scout_client.get("/api/scout/players?status=sold").get_json()
        assert sold["total"] == 0

    def test_compare_reflects_actual_current_situation(self, scout_client, current_situation_seeded):
        resp = scout_client.get("/api/scout/compare?ids=2001")
        profile = resp.get_json()["players"][0]["profile"]
        assert profile["status"] == "on_loan"
        assert profile["owner_team_name"] == "Ajax"


class TestSupportedLeaguesConfig:
    def test_default_supported_leagues_global(self):
        from src.utils.supported_leagues import get_supported_leagues

        leagues = get_supported_leagues()
        regions = {info["region"] for info in leagues.values()}
        assert {"Europe", "South America", "North America", "Asia"} <= regions
        assert 39 in leagues and 71 in leagues and 253 in leagues

    def test_supported_league_ids_env_override(self, monkeypatch):
        from src.utils.supported_leagues import get_supported_leagues

        monkeypatch.setenv("SUPPORTED_LEAGUE_IDS", "39, 71")
        assert set(get_supported_leagues().keys()) == {39, 71}

    def test_crawl_league_ids_default_top5(self, monkeypatch):
        from src.utils.supported_leagues import get_crawl_league_ids

        monkeypatch.delenv("CRAWL_LEAGUE_IDS", raising=False)
        assert get_crawl_league_ids() == [39, 140, 135, 78, 61]

    def test_crawl_league_ids_env_override(self, monkeypatch):
        from src.utils.supported_leagues import get_crawl_league_ids

        monkeypatch.setenv("CRAWL_LEAGUE_IDS", "39,71,253")
        assert get_crawl_league_ids() == [39, 71, 253]


@pytest.fixture
def age_seeded(scout_app):
    """Players exercising birth_date-derived ages and owning-club exclusion."""
    from datetime import date

    with scout_app.app_context():
        league = League(league_id=39, name="Premier League", country="England", season=2025)
        db.session.add(league)
        db.session.flush()
        parent = Team(
            team_id=33, name="Manchester United", country="England", season=2025, league_id=league.id, is_active=True
        )
        db.session.add(parent)
        db.session.flush()

        year = date.today().year
        # Jan-1 birthdays make derived age exactly (year - birth_year)
        teen = TrackedPlayer(
            player_api_id=3001,
            player_name="Teen Talent",
            age=None,  # journey-sync rows never set age — only birth_date
            birth_date=f"{year - 17}-01-01",
            team_id=parent.id,
            status="academy",
            is_active=True,
        )
        stale = TrackedPlayer(
            player_api_id=3002,
            player_name="Stale Snapshot",
            age=17,  # stored snapshot from years ago…
            birth_date=f"{year - 24}-01-01",  # …but he is 24 now
            team_id=parent.id,
            status="first_team",
            current_club_api_id=33,
            is_active=True,
        )
        senior_signing = TrackedPlayer(
            player_api_id=3003,
            player_name="Big Money Signing",
            age=None,
            birth_date=f"{year - 24}-01-01",
            team_id=parent.id,
            status="first_team",
            current_club_api_id=33,
            data_source="owning-club",  # deprecated — must never surface
            is_active=True,
        )
        db.session.add_all([teen, stale, senior_signing])

        # Give the owning-club row stats so it would top boards if leaked
        fixture = Fixture(
            fixture_id_api=7000,
            season=2025,
            home_team_api_id=33,
            away_team_api_id=999,
            date_utc=datetime(2025, 10, 1),
        )
        db.session.add(fixture)
        db.session.flush()
        db.session.add(
            FixturePlayerStats(
                fixture_id=fixture.id,
                player_api_id=3003,
                team_api_id=33,
                minutes=90,
                goals=3,
                assists=2,
                rating=9.1,
            )
        )
        db.session.commit()


class TestAgeDerivationAndOwningClubExclusion:
    def test_age_filter_derives_from_birth_date_when_age_is_null(self, scout_client, age_seeded):
        resp = scout_client.get("/api/scout/players?max_age=18")
        data = resp.get_json()
        assert [p["player_id"] for p in data["players"]] == [3001]

    def test_birth_date_beats_stale_stored_age(self, scout_client, age_seeded):
        # Stored age says 17, birth_date says 24 — birth_date wins.
        resp = scout_client.get("/api/scout/players?max_age=18")
        ids = {p["player_id"] for p in resp.get_json()["players"]}
        assert 3002 not in ids

        resp = scout_client.get("/api/scout/players?min_age=20&max_age=30")
        ids = {p["player_id"] for p in resp.get_json()["players"]}
        assert 3002 in ids

    def test_payload_age_is_derived_from_birth_date(self, scout_client, age_seeded):
        resp = scout_client.get("/api/scout/players?search=Teen")
        players = resp.get_json()["players"]
        assert players and players[0]["age"] == 17

    def test_owning_club_rows_never_surface_in_browse(self, scout_client, age_seeded):
        resp = scout_client.get("/api/scout/players")
        ids = {p["player_id"] for p in resp.get_json()["players"]}
        assert 3003 not in ids
        assert ids == {3001, 3002}

    def test_owning_club_rows_never_surface_in_leaderboards(self, scout_client, age_seeded):
        resp = scout_client.get("/api/scout/leaderboards")
        boards = resp.get_json()["leaderboards"]
        all_ids = {p["player_id"] for entries in boards.values() for p in entries}
        assert 3003 not in all_ids

    def test_owning_club_rows_excluded_from_compare(self, scout_client, age_seeded):
        resp = scout_client.get("/api/scout/compare?ids=3003")
        data = resp.get_json()
        assert data["players"] == []
        assert data["missing_ids"] == [3003]
