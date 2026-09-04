"""D4c flag-gated reads from player-season rollups.

All tests use SQLite and an inert API-Football client. Season values are API
start-years (2025 == 2025-26).
"""

from datetime import UTC, datetime

import pytest
from flask import Flask
from src.models.funding import ClubProgram, FundingLeague
from src.models.league import Team, db
from src.models.season_rollup import PlayerSeasonCell, PlayerSeasonTotal
from src.models.tracked_player import TrackedPlayer
from src.models.weekly import Fixture, FixturePlayerStats

PLAYER = 840001
SECOND_PLAYER = 840002
PARENT = 33
LOAN = 901
OPPONENT = 999
COMPUTED_AT = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)


class _StubAPIClient:
    def __init__(self, *args, **kwargs):
        pass

    def _fetch_player_team_season_totals_api(self, *args, **kwargs):
        return {"games_played": 0}


@pytest.fixture
def app(monkeypatch):
    monkeypatch.delenv("SEASON_ROLLUP_READS", raising=False)
    monkeypatch.setenv("SKIP_API_HANDSHAKE", "1")
    monkeypatch.setenv("API_USE_STUB_DATA", "true")

    import src.api_football_client as api_football
    from src.routes.players import players_bp
    from src.routes.scout import scout_bp

    monkeypatch.setattr(api_football, "APIFootballClient", _StubAPIClient)

    application = Flask(__name__)
    application.config.update(
        TESTING=True,
        SECRET_KEY="test-secret",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        RATELIMIT_ENABLED=False,
    )
    db.init_app(application)
    application.register_blueprint(players_bp, url_prefix="/api")
    application.register_blueprint(scout_bp, url_prefix="/api")

    ctx = application.app_context()
    ctx.push()
    db.create_all()
    yield application
    db.session.remove()
    db.drop_all()
    ctx.pop()


@pytest.fixture
def client(app):
    return app.test_client()


def _teams():
    parent = Team(
        team_id=PARENT,
        name="Parent FC",
        country="England",
        season=2025,
        logo="parent.png",
        is_active=True,
    )
    loan = Team(
        team_id=LOAN,
        name="Loan FC",
        country="England",
        season=2025,
        logo="loan.png",
        is_active=True,
    )
    db.session.add_all([parent, loan])
    db.session.flush()
    return parent, loan


def _seed_live_player(
    player_api_id=PLAYER,
    *,
    fixture_id=940001,
    minutes=500,
    appearances=1,
    goals=1,
    assists=1,
):
    parent = Team.query.filter_by(team_id=PARENT).first()
    loan = Team.query.filter_by(team_id=LOAN).first()
    if parent is None or loan is None:
        parent, loan = _teams()

    tracked = TrackedPlayer(
        player_api_id=player_api_id,
        player_name=f"Player {player_api_id}",
        position="Midfielder",
        nationality="England",
        age=20,
        team_id=parent.id,
        status="on_loan",
        current_club_api_id=LOAN,
        current_club_name="Loan FC",
        current_club_db_id=loan.id,
        data_depth="full_stats",
        is_active=True,
    )
    db.session.add(tracked)
    db.session.flush()
    base_minutes, extra_minutes = divmod(minutes, appearances)
    for index in range(appearances):
        fixture = Fixture(
            fixture_id_api=fixture_id + index,
            season=2025,
            date_utc=datetime(2025, 9, 1, tzinfo=UTC),
            competition_name="Championship",
            home_team_api_id=LOAN,
            away_team_api_id=OPPONENT,
            home_goals=2,
            away_goals=0,
        )
        db.session.add(fixture)
        db.session.flush()
        db.session.add(
            FixturePlayerStats(
                fixture_id=fixture.id,
                player_api_id=player_api_id,
                team_api_id=LOAN,
                position="M",
                minutes=base_minutes + (index < extra_minutes),
                goals=goals if index == 0 else 0,
                assists=assists if index == 0 else 0,
                yellows=1 if index == 0 else 0,
                reds=0,
                rating=7.0,
                shots_total=9 if index == 0 else 0,
                tackles_total=4 if index == 0 else 0,
            )
        )
    db.session.commit()
    return tracked


def _add_live_match(
    player_api_id=PLAYER,
    *,
    fixture_id=940003,
    minutes=100,
    goals=0,
    assists=0,
    rating=9.0,
):
    fixture = Fixture(
        fixture_id_api=fixture_id,
        season=2025,
        date_utc=datetime(2025, 9, 8, tzinfo=UTC),
        competition_name="Championship",
        home_team_api_id=LOAN,
        away_team_api_id=OPPONENT,
        home_goals=1,
        away_goals=0,
    )
    db.session.add(fixture)
    db.session.flush()
    db.session.add(
        FixturePlayerStats(
            fixture_id=fixture.id,
            player_api_id=player_api_id,
            team_api_id=LOAN,
            position="M",
            minutes=minutes,
            goals=goals,
            assists=assists,
            yellows=0,
            reds=0,
            rating=rating,
        )
    )
    db.session.commit()


def _seed_rollup(
    player_api_id=PLAYER,
    *,
    season=2025,
    minutes=600,
    appearances=8,
    goals=2,
    assists=3,
    fixtures_minutes=500,
    journey_minutes=600,
    avg_rating=7.25,
    primary_source="journey",
    reconcile_flag="cup-gap",
    fixtures_appearances=5,
    journey_appearances=None,
    with_cells=True,
):
    journey_appearances = appearances if journey_appearances is None else journey_appearances
    total = PlayerSeasonTotal(
        player_api_id=player_api_id,
        season=season,
        level_group="senior",
        appearances=appearances,
        goals=goals,
        assists=assists,
        minutes=minutes,
        yellows=2,
        reds=1,
        saves=4,
        goals_conceded=5,
        avg_rating=avg_rating,
        primary_source=primary_source,
        fixtures_minutes=fixtures_minutes,
        journey_minutes=journey_minutes,
        reconcile_flag=reconcile_flag,
        source_breakdown={
            "fixtures": {"minutes": fixtures_minutes},
            "journey": {"minutes": journey_minutes},
        },
        clubs=[
            {
                "id": LOAN,
                "name": "Loan FC",
                "minutes": minutes,
                "appearances": appearances,
                "goals": goals,
                "assists": assists,
                "competition_tiers": ["league", "domestic_cup"],
            }
        ],
        computed_at=COMPUTED_AT,
    )
    db.session.add(total)
    if with_cells:
        db.session.add_all(
            [
                PlayerSeasonCell(
                    player_api_id=player_api_id,
                    season=season,
                    source="fixtures",
                    club_api_id=LOAN,
                    club_name="Loan FC",
                    competition_tier="league",
                    level_group="senior",
                    appearances=fixtures_appearances,
                    goals=goals if primary_source == "fixtures" else 1,
                    assists=assists if primary_source == "fixtures" else 1,
                    minutes=fixtures_minutes,
                    yellows=1,
                    reds=0,
                    saves=4,
                    goals_conceded=5,
                    avg_rating=avg_rating,
                    detail={"shots_total": 9},
                    synced_at=COMPUTED_AT,
                ),
                PlayerSeasonCell(
                    player_api_id=player_api_id,
                    season=season,
                    source="journey",
                    club_api_id=LOAN,
                    club_name="Loan FC",
                    competition_tier="domestic_cup",
                    level_group="senior",
                    appearances=journey_appearances,
                    goals=goals if primary_source == "journey" else goals + 1,
                    assists=assists if primary_source == "journey" else assists + 1,
                    minutes=journey_minutes,
                    yellows=2,
                    reds=1,
                    synced_at=COMPUTED_AT,
                ),
            ]
        )
    db.session.commit()
    return total


def _assert_headline_matches_total(payload, total, *, minutes_key="minutes"):
    assert payload[minutes_key] == total.minutes
    assert payload["appearances"] == total.appearances
    assert payload["goals"] == total.goals
    assert payload["assists"] == total.assists
    assert payload["avg_rating"] == (float(total.avg_rating) if total.avg_rating is not None else None)


def _assert_rollup_provenance(provenance, total):
    expected = {
        "primary_source": total.primary_source,
        "reconcile_flag": total.reconcile_flag,
        "fixtures_minutes": total.fixtures_minutes,
        "journey_minutes": total.journey_minutes,
        "computed_at": total.computed_at.isoformat(),
    }
    assert {key: provenance[key] for key in expected} == expected


# ---------------------------------------------------------------------------
# (a) Flag off: populated rollups are invisible to every surface.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        pytest.param(f"/api/players/{PLAYER}/stats?season=2025", id="player-stats"),
        pytest.param(f"/api/players/{PLAYER}/season-stats?season=2025", id="season-stats"),
        pytest.param("/api/scout/players?season=2025&sort=name", id="scout"),
    ],
)
def test_flag_unset_keeps_live_response_byte_identical(client, monkeypatch, url):
    _seed_live_player()
    monkeypatch.delenv("SEASON_ROLLUP_READS", raising=False)
    live = client.get(url)
    assert live.status_code == 200
    live_data = live.get_json()
    if url.startswith("/api/scout"):
        player = live_data["players"][0]
        assert (player["appearances"], player["minutes_played"], player["goals"], player["assists"]) == (
            1,
            500,
            1,
            1,
        )
        assert "rollup_missing" not in player
    elif "/season-stats" in url:
        assert (live_data["appearances"], live_data["minutes"], live_data["goals"], live_data["assists"]) == (
            1,
            500,
            1,
            1,
        )
        assert live_data["provenance"] == {
            "source": "fixtures",
            "fixtures_minutes": 500,
            "journey_minutes": 0,
            "delta_pct": -100.0,
            "reconcile_flag": "journey-under-sync",
        }
    else:
        assert isinstance(live_data, list)
        assert len(live_data) == 1
        assert (live_data[0]["minutes"], live_data[0]["goals"], live_data[0]["assists"]) == (500, 1, 1)

    _seed_rollup()
    unchanged = client.get(url)
    assert unchanged.status_code == 200
    if url.startswith("/api/scout"):
        unchanged_data = unchanged.get_json()
        live_data["players"][0].pop("provenance", None)
        unchanged_data["players"][0].pop("provenance", None)
        assert unchanged_data == live_data
    else:
        assert unchanged.data == live.data


# ---------------------------------------------------------------------------
# (b) Totals present: one winning source supplies the whole headline.
# ---------------------------------------------------------------------------


def test_season_stats_rollup_uses_total_whole_and_cells_breakdown(client, monkeypatch):
    _seed_live_player()
    total = _seed_rollup()
    monkeypatch.setenv("SEASON_ROLLUP_READS", "season_stats")

    response = client.get(f"/api/players/{PLAYER}/season-stats?season=2025")
    assert response.status_code == 200
    data = response.get_json()
    assert {
        key: data[key]
        for key in ("appearances", "minutes", "goals", "assists", "yellows", "reds", "saves", "goals_conceded")
    } == {
        "appearances": 8,
        "minutes": 600,
        "goals": 2,
        "assists": 3,
        "yellows": 2,
        "reds": 1,
        "saves": 4,
        "goals_conceded": 5,
    }
    assert data["minutes"] != 1100
    assert data["avg_rating"] == 7.25
    assert data["source"] == "season-rollup"
    assert data["clean_sheets"] is None
    _assert_headline_matches_total(data, total)
    _assert_rollup_provenance(data["provenance"], total)
    assert data["source_breakdown"]["fixtures"][0]["stats"]["minutes"] == 500
    assert data["source_breakdown"]["journey"][0]["stats"]["minutes"] == 600


def test_season_stats_rollup_resolves_id_only_club_from_team_table(client, monkeypatch):
    _seed_live_player()
    total = _seed_rollup()
    total.clubs[0].pop("name")
    db.session.commit()
    monkeypatch.setenv("SEASON_ROLLUP_READS", "season_stats")

    response = client.get(f"/api/players/{PLAYER}/season-stats?season=2025")

    assert response.status_code == 200
    assert response.get_json()["clubs"][0] == {
        "team_api_id": LOAN,
        "team_name": "Loan FC",
        "team_logo": "loan.png",
        "window_type": None,
        "is_current": None,
        "appearances": 8,
        "minutes": 600,
        "goals": 2,
        "assists": 3,
        "competition_tiers": ["league", "domestic_cup"],
    }


def test_season_stats_rollup_resolves_negative_id_from_club_program(client, monkeypatch):
    _seed_live_player()
    funding_league = FundingLeague(
        name="Rollup Program League",
        country="England",
        region="North East",
        level="youth_regional",
        age_bands=["U19"],
        gender_program="both",
        season_calendar="aug_may",
        data_tier="self_reported",
        registry_status="approved",
        admission_state="open",
    )
    db.session.add(funding_league)
    db.session.flush()
    program = ClubProgram(
        funding_league_id=funding_league.id,
        name="Community Academy",
        legal_name="Community Academy Association",
        slug="rollup-community-academy",
        country="England",
        region="North East",
        platform_status="approved",
    )
    db.session.add(program)
    db.session.flush()
    db.session.add(
        Team(
            team_id=-program.id,
            name="Wrong API Team",
            country="England",
            season=2025,
            logo="wrong-team.png",
            is_active=True,
        )
    )
    total = _seed_rollup()
    total.clubs = [
        {**total.clubs[0], "id": -program.id, "name": "Stale Program Name"},
        {**total.clubs[0], "id": -987654, "name": "Stored Community Name"},
    ]
    db.session.commit()
    monkeypatch.setenv("SEASON_ROLLUP_READS", "season_stats")

    response = client.get(f"/api/players/{PLAYER}/season-stats?season=2025")

    assert response.status_code == 200
    clubs = response.get_json()["clubs"]
    assert [(club["team_api_id"], club["team_name"]) for club in clubs] == [
        (-program.id, "Community Academy"),
        (-987654, "Stored Community Name"),
    ]
    assert all(club["team_logo"] is None for club in clubs)


def test_season_stats_rollup_keeps_unknown_club_metadata_null(client, monkeypatch):
    _seed_live_player()
    total = _seed_rollup()
    total.clubs = [{**total.clubs[0], "id": team_api_id, "name": "  "} for team_api_id in (987654, -987654, 0)]
    db.session.commit()
    monkeypatch.setenv("SEASON_ROLLUP_READS", "season_stats")

    response = client.get(f"/api/players/{PLAYER}/season-stats?season=2025")

    assert response.status_code == 200
    clubs = response.get_json()["clubs"]
    assert [club["team_api_id"] for club in clubs] == [987654, -987654, 0]
    assert all(club["team_name"] is None for club in clubs)
    assert all(club["team_logo"] is None for club in clubs)


def test_season_stats_fixtures_primary_serves_total_headline_verbatim(client, monkeypatch):
    _seed_live_player(minutes=2941, appearances=39, goals=12, assists=7)
    total = _seed_rollup(
        minutes=2941,
        appearances=39,
        goals=12,
        assists=7,
        fixtures_minutes=2941,
        journey_minutes=2936,
        avg_rating=8.13,
        primary_source="fixtures",
        reconcile_flag="journey-under-sync",
        fixtures_appearances=39,
        journey_appearances=40,
    )

    # Reproduce the live legacy conflict exactly: API/journey has more
    # appearances (40/2936), while fixtures has more minutes (39/2941).
    monkeypatch.setattr(
        _StubAPIClient,
        "_fetch_player_team_season_totals_api",
        lambda *args, **kwargs: {
            "games_played": 40,
            "minutes": 2936,
            "goals": 11,
            "assists": 6,
        },
    )
    monkeypatch.setenv("SEASON_ROLLUP_READS", "season_stats")

    response = client.get(f"/api/players/{PLAYER}/season-stats")
    assert response.status_code == 200
    data = response.get_json()
    _assert_headline_matches_total(data, total)
    assert (data["minutes"], data["appearances"]) == (2941, 39)
    _assert_rollup_provenance(data["provenance"], total)


def test_player_stats_rollup_keeps_matches_and_adds_total_summary(client, monkeypatch):
    _seed_live_player()
    total = _seed_rollup()
    monkeypatch.delenv("SEASON_ROLLUP_READS", raising=False)
    live_matches = client.get(f"/api/players/{PLAYER}/stats?season=2025").get_json()
    monkeypatch.setenv("SEASON_ROLLUP_READS", "player_stats")

    response = client.get(f"/api/players/{PLAYER}/stats?season=2025")
    assert response.status_code == 200
    data = response.get_json()
    assert data["matches"] == live_matches
    assert data["summary"]["minutes"] == 600
    assert data["summary"]["appearances"] == 8
    assert data["summary"]["goals"] == 2
    assert data["summary"]["assists"] == 3
    assert data["summary"]["minutes"] != 1100
    assert data["summary"]["avg_rating"] == 7.25
    assert (data["summary"]["yellows"], data["summary"]["reds"], data["summary"]["saves"]) == (2, 1, 4)
    _assert_headline_matches_total(data["summary"], total)
    _assert_rollup_provenance(data["provenance"], total)
    assert data["source_breakdown"]["fixtures"][0]["stats"]["minutes"] == 500
    assert data["source_breakdown"]["journey"][0]["stats"]["minutes"] == 600


def test_player_stats_fixtures_primary_serves_total_summary_verbatim(client, monkeypatch):
    _seed_live_player(minutes=2936, appearances=40, goals=11, assists=6)
    total = _seed_rollup(
        minutes=2941,
        appearances=39,
        goals=12,
        assists=7,
        fixtures_minutes=2941,
        journey_minutes=2936,
        avg_rating=8.13,
        primary_source="fixtures",
        reconcile_flag="journey-under-sync",
        fixtures_appearances=39,
        journey_appearances=40,
    )
    monkeypatch.setenv("SEASON_ROLLUP_READS", "player_stats")

    response = client.get(f"/api/players/{PLAYER}/stats?season=2025")
    assert response.status_code == 200
    data = response.get_json()
    assert len(data["matches"]) == 40
    _assert_headline_matches_total(data["summary"], total)
    assert (data["summary"]["minutes"], data["summary"]["appearances"]) == (2941, 39)
    _assert_rollup_provenance(data["provenance"], total)


def test_scout_rollup_uses_totals_for_values_and_sorting(client, monkeypatch):
    _seed_live_player(goals=0, minutes=30)
    _seed_live_player(
        SECOND_PLAYER,
        fixture_id=940002,
        goals=9,
        assists=0,
        minutes=900,
    )
    total = _seed_rollup()
    _seed_rollup(
        SECOND_PLAYER,
        minutes=100,
        appearances=2,
        goals=0,
        assists=0,
        fixtures_minutes=90,
        journey_minutes=100,
        with_cells=False,
    )
    monkeypatch.setenv("SEASON_ROLLUP_READS", "scout")

    import src.routes.scout as scout_routes

    def _must_not_run(*args, **kwargs):
        raise AssertionError("live aggregate subquery ran under scout rollup flag")

    monkeypatch.setattr(scout_routes, "_fixture_stats_subquery", _must_not_run)
    monkeypatch.setattr(scout_routes, "_cache_stats_subquery", _must_not_run)

    response = client.get("/api/scout/players?season=2025&sort=goals")
    assert response.status_code == 200
    rows = response.get_json()["players"]
    assert [row["player_id"] for row in rows] == [PLAYER, SECOND_PLAYER]
    first = rows[0]
    assert (first["appearances"], first["minutes_played"], first["goals"], first["assists"]) == (8, 600, 2, 3)
    assert first["avg_rating"] == 7.25
    assert (first["yellows"], first["reds"], first["saves"], first["goals_conceded"]) == (2, 1, 4, 5)
    assert first["rollup_missing"] is False
    assert first["has_detailed_stats"] is False
    assert first["shots_total"] is None
    _assert_headline_matches_total(first, total, minutes_key="minutes_played")
    _assert_rollup_provenance(first["provenance"], total)


def test_scout_fixtures_primary_projects_total_headline_verbatim(client, monkeypatch):
    _seed_live_player(minutes=2936, appearances=40, goals=11, assists=6)
    total = _seed_rollup(
        minutes=2941,
        appearances=39,
        goals=12,
        assists=7,
        fixtures_minutes=2941,
        journey_minutes=2936,
        avg_rating=8.13,
        primary_source="fixtures",
        reconcile_flag="journey-under-sync",
        fixtures_appearances=39,
        journey_appearances=40,
    )
    monkeypatch.setenv("SEASON_ROLLUP_READS", "scout")

    import src.routes.scout as scout_routes

    def _must_not_run(*args, **kwargs):
        raise AssertionError("live aggregate subquery ran under scout rollup flag")

    monkeypatch.setattr(scout_routes, "_fixture_stats_subquery", _must_not_run)
    monkeypatch.setattr(scout_routes, "_cache_stats_subquery", _must_not_run)

    response = client.get("/api/scout/players?season=2025&sort=goals")
    assert response.status_code == 200
    row = response.get_json()["players"][0]
    _assert_headline_matches_total(row, total, minutes_key="minutes_played")
    assert (row["minutes_played"], row["appearances"]) == (2941, 39)
    _assert_rollup_provenance(row["provenance"], total)


def test_scout_flag_routes_supported_leaderboards_to_rollups(client, monkeypatch):
    _seed_live_player(goals=0, minutes=30)
    _seed_live_player(
        SECOND_PLAYER,
        fixture_id=940002,
        goals=9,
        assists=0,
        minutes=900,
    )
    _seed_rollup()
    _seed_rollup(
        SECOND_PLAYER,
        minutes=100,
        appearances=2,
        goals=0,
        assists=0,
        fixtures_minutes=90,
        journey_minutes=100,
        with_cells=False,
    )
    monkeypatch.setenv("SEASON_ROLLUP_READS", "scout")

    response = client.get("/api/scout/leaderboards?limit=2")
    assert response.status_code == 200
    data = response.get_json()
    top_scorers = data["leaderboards"]["top_scorers"]
    assert data["season"] == 2025
    assert top_scorers[0]["player_id"] == PLAYER
    assert top_scorers[0]["goals"] == 2
    assert top_scorers[0]["rollup_missing"] is False
    assert top_scorers[0]["provenance"]["primary_source"] == "journey"


def test_scout_compare_rollup_honors_season_and_carries_provenance(client, monkeypatch):
    _seed_live_player(goals=9, minutes=900)
    total = _seed_rollup()
    monkeypatch.setenv("SEASON_ROLLUP_READS", "scout")

    import src.routes.scout as scout_routes

    def _must_not_mix_fixture_detail(*args, **kwargs):
        raise AssertionError("journey-primary compare must not query fixture detail")

    monkeypatch.setattr(scout_routes, "_compare_fixture_totals", _must_not_mix_fixture_detail)

    response = client.get(f"/api/scout/compare?ids={PLAYER}&season=2025")

    assert response.status_code == 200
    data = response.get_json()
    assert data["season"] == 2025
    compared = data["players"][0]
    assert {
        key: compared["totals"][key]
        for key in (
            "appearances",
            "goals",
            "assists",
            "minutes_played",
            "avg_rating",
            "yellows",
            "reds",
            "saves",
            "goals_conceded",
        )
    } == {
        "appearances": total.appearances,
        "goals": total.goals,
        "assists": total.assists,
        "minutes_played": total.minutes,
        "avg_rating": float(total.avg_rating),
        "yellows": total.yellows,
        "reds": total.reds,
        "saves": total.saves,
        "goals_conceded": total.goals_conceded,
    }
    for key in (
        "shots_total",
        "shots_on",
        "passes_total",
        "key_passes",
        "dribbles_attempts",
        "dribbles_success",
        "tackles",
        "interceptions",
        "duels_total",
        "duels_won",
        "fouls_drawn",
        "penalty_saved",
        "clean_sheets",
    ):
        assert compared["totals"][key] is None
    _assert_rollup_provenance(compared["provenance"], total)


def test_scout_compare_fixtures_primary_enriches_only_rich_fields(client, monkeypatch):
    _seed_live_player(goals=9, assists=8, minutes=90)
    fixture_stats = FixturePlayerStats.query.filter_by(player_api_id=PLAYER).one()
    fixture_stats.position = "G"
    fixture_stats.shots_on = 5
    fixture_stats.passes_total = 42
    fixture_stats.passes_key = 7
    fixture_stats.dribbles_attempts = 8
    fixture_stats.dribbles_success = 6
    fixture_stats.tackles_interceptions = 3
    fixture_stats.duels_total = 11
    fixture_stats.duels_won = 7
    fixture_stats.fouls_drawn = 4
    fixture_stats.saves = 12
    fixture_stats.goals_conceded = 0
    fixture_stats.penalty_saved = 2
    db.session.commit()
    total = _seed_rollup(primary_source="fixtures", minutes=600, appearances=8, goals=2, assists=3)
    monkeypatch.setenv("SEASON_ROLLUP_READS", "scout")

    response = client.get(f"/api/scout/compare?ids={PLAYER}&season=2025")

    assert response.status_code == 200
    compared = response.get_json()["players"][0]
    totals = compared["totals"]
    assert {
        key: totals[key]
        for key in (
            "appearances",
            "goals",
            "assists",
            "minutes_played",
            "avg_rating",
            "yellows",
            "reds",
            "saves",
            "goals_conceded",
        )
    } == {
        "appearances": total.appearances,
        "goals": total.goals,
        "assists": total.assists,
        "minutes_played": total.minutes,
        "avg_rating": float(total.avg_rating),
        "yellows": total.yellows,
        "reds": total.reds,
        "saves": total.saves,
        "goals_conceded": total.goals_conceded,
    }
    assert {
        key: totals[key]
        for key in (
            "shots_total",
            "shots_on",
            "passes_total",
            "key_passes",
            "dribbles_attempts",
            "dribbles_success",
            "tackles",
            "interceptions",
            "duels_total",
            "duels_won",
            "fouls_drawn",
            "penalty_saved",
            "clean_sheets",
        )
    } == {
        "shots_total": 9,
        "shots_on": 5,
        "passes_total": 42,
        "key_passes": 7,
        "dribbles_attempts": 8,
        "dribbles_success": 6,
        "tackles": 4,
        "interceptions": 3,
        "duels_total": 11,
        "duels_won": 7,
        "fouls_drawn": 4,
        "penalty_saved": 2,
        "clean_sheets": 1,
    }
    assert compared["per90"]["key_passes"] == 1.05
    _assert_rollup_provenance(compared["provenance"], total)


def test_scout_compare_no_param_uses_same_discovery_season_as_list(client, monkeypatch):
    _seed_live_player(goals=9, minutes=900)
    total = _seed_rollup()
    monkeypatch.setenv("SEASON_ROLLUP_READS", "scout")

    listed = client.get("/api/scout/players?sort=name")
    compared = client.get(f"/api/scout/compare?ids={PLAYER}")

    assert listed.status_code == compared.status_code == 200
    assert listed.get_json()["players"][0]["goals"] == total.goals
    assert compared.get_json()["season"] == 2025
    assert compared.get_json()["players"][0]["totals"]["goals"] == total.goals


def test_scout_rollup_history_is_flag_gated(client, monkeypatch):
    _seed_live_player()
    total = _seed_rollup(season=2007)

    unflagged = client.get(f"/api/scout/compare?ids={PLAYER}&season=2007")
    monkeypatch.setenv("SEASON_ROLLUP_READS", "scout")
    flagged = client.get(f"/api/scout/compare?ids={PLAYER}&season=2007")
    listed = client.get("/api/scout/players?season=2007&sort=name")

    assert unflagged.status_code == 400
    assert flagged.status_code == listed.status_code == 200
    totals = flagged.get_json()["players"][0]["totals"]
    assert totals["goals"] == total.goals
    assert totals["minutes_played"] == total.minutes
    row = listed.get_json()["players"][0]
    assert row["goals"] == total.goals
    assert row["minutes_played"] == total.minutes


def test_player_rollup_branches_accept_historical_totals(client, monkeypatch):
    _seed_live_player()
    total = _seed_rollup(season=2007)

    monkeypatch.setenv("SEASON_ROLLUP_READS", "season_stats")
    season_stats = client.get(f"/api/players/{PLAYER}/season-stats?season=2007")
    monkeypatch.setenv("SEASON_ROLLUP_READS", "player_stats")
    player_stats = client.get(f"/api/players/{PLAYER}/stats?season=2007")

    assert season_stats.status_code == player_stats.status_code == 200
    assert season_stats.get_json()["goals"] == total.goals
    assert season_stats.get_json()["minutes"] == total.minutes
    assert player_stats.get_json()["summary"]["goals"] == total.goals
    assert player_stats.get_json()["summary"]["minutes"] == total.minutes


def test_scout_rollup_gk_boards_keep_position_clamp(client, monkeypatch):
    goalkeeper = _seed_live_player()
    goalkeeper.position = "Goalkeeper"
    _seed_live_player(SECOND_PLAYER, fixture_id=940002, goals=9, minutes=900)
    _seed_rollup()
    _seed_rollup(
        SECOND_PLAYER,
        minutes=900,
        appearances=10,
        goals=9,
        assists=0,
        fixtures_minutes=900,
        journey_minutes=0,
        with_cells=False,
    )
    db.session.commit()
    monkeypatch.setenv("SEASON_ROLLUP_READS", "scout")

    response = client.get("/api/scout/leaderboards?phase=gk&season=2025")

    assert response.status_code == 200
    for entries in response.get_json()["leaderboards"].values():
        assert all(entry["position"] == "Goalkeeper" for entry in entries)


@pytest.mark.parametrize("path", ["leaderboards", f"compare?ids={PLAYER}&extra=1"])
def test_scout_new_season_params_reject_out_of_range(client, path):
    _seed_live_player()
    separator = "&" if "?" in path else "?"

    response = client.get(f"/api/scout/{path}{separator}season=2024")

    assert response.status_code == 400


# ---------------------------------------------------------------------------
# (c) Missing totals: player reads stay live; bulk Scout never falls back.
# ---------------------------------------------------------------------------


def test_season_stats_missing_total_falls_back_live(client, monkeypatch):
    _seed_live_player()
    monkeypatch.delenv("SEASON_ROLLUP_READS", raising=False)
    live = client.get(f"/api/players/{PLAYER}/season-stats?season=2025").get_json()
    monkeypatch.setenv("SEASON_ROLLUP_READS", "season_stats")

    fallback = client.get(f"/api/players/{PLAYER}/season-stats?season=2025").get_json()
    expected = {**live, "provenance": {"source": "live-fallback"}}
    assert fallback == expected


def test_player_stats_missing_total_falls_back_live(client, monkeypatch):
    _seed_live_player()
    _add_live_match()
    monkeypatch.delenv("SEASON_ROLLUP_READS", raising=False)
    live_matches = client.get(f"/api/players/{PLAYER}/stats?season=2025").get_json()
    monkeypatch.setenv("SEASON_ROLLUP_READS", "player_stats")

    fallback = client.get(f"/api/players/{PLAYER}/stats?season=2025").get_json()
    assert fallback["matches"] == live_matches
    assert fallback["summary"]["appearances"] == 2
    assert fallback["summary"]["minutes"] == 600
    assert fallback["summary"]["goals"] == 1
    assert fallback["summary"]["avg_rating"] == 7.33
    assert fallback["provenance"] == {"source": "live-fallback"}
    assert fallback["source_breakdown"] == {}


def test_scout_missing_total_returns_null_without_live_fallback(client, monkeypatch):
    _seed_live_player()
    db.session.add(
        PlayerSeasonTotal(
            player_api_id=PLAYER,
            season=2025,
            level_group="youth",
            appearances=99,
            goals=99,
            assists=99,
            minutes=9999,
            primary_source="journey",
            fixtures_minutes=0,
            journey_minutes=9999,
            computed_at=COMPUTED_AT,
        )
    )
    db.session.commit()
    monkeypatch.setenv("SEASON_ROLLUP_READS", "scout")

    response = client.get("/api/scout/players?season=2025&sort=goals")
    assert response.status_code == 200
    row = response.get_json()["players"][0]
    assert row["player_id"] == PLAYER
    assert row["rollup_missing"] is True
    assert row["provenance"] == {
        "source_category": "api",
        "source_label": "API-reported",
        "primary_source": None,
    }
    for key in (
        "appearances",
        "minutes_played",
        "goals",
        "assists",
        "avg_rating",
        "goal_contributions",
        "contributions_per90",
        "shots_total",
        "tackles",
        "saves",
    ):
        assert row[key] is None
    assert row["recent_form"], "per-match form remains FPS-driven; only aggregates are cut over"


# ---------------------------------------------------------------------------
# (d) Flag parser: empty/off, scoped keys, all keys, and ignored junk.
# ---------------------------------------------------------------------------


def test_rollup_flag_unset_and_empty_disable_all(monkeypatch):
    from src.utils.feature_flags import rollup_reads_enabled

    for raw in (None, "", " , "):
        if raw is None:
            monkeypatch.delenv("SEASON_ROLLUP_READS", raising=False)
        else:
            monkeypatch.setenv("SEASON_ROLLUP_READS", raw)
        assert not any(rollup_reads_enabled(surface) for surface in ("season_stats", "player_stats", "scout", "teams"))


def test_rollup_flag_one_key_is_surface_scoped(monkeypatch):
    from src.utils.feature_flags import rollup_reads_enabled

    monkeypatch.setenv("SEASON_ROLLUP_READS", " player_stats ")
    assert rollup_reads_enabled("player_stats") is True
    assert rollup_reads_enabled("season_stats") is False
    assert rollup_reads_enabled("scout") is False
    assert rollup_reads_enabled("teams") is False


def test_rollup_flag_all_keys_enable_all_surfaces(monkeypatch):
    from src.utils.feature_flags import rollup_reads_enabled

    monkeypatch.setenv("SEASON_ROLLUP_READS", "season_stats,player_stats,scout,teams,SCOUT")
    assert all(rollup_reads_enabled(surface) for surface in ("season_stats", "player_stats", "scout", "teams"))


def test_rollup_flag_teams_key_is_surface_scoped(monkeypatch):
    from src.utils.feature_flags import rollup_reads_enabled

    monkeypatch.setenv("SEASON_ROLLUP_READS", "teams")
    assert rollup_reads_enabled("teams") is True
    assert rollup_reads_enabled("scout") is False


def test_rollup_flag_ignores_junk_keys(monkeypatch):
    from src.utils.feature_flags import rollup_reads_enabled

    monkeypatch.setenv("SEASON_ROLLUP_READS", "junk,scout,not-a-surface")
    assert rollup_reads_enabled("scout") is True
    assert rollup_reads_enabled("player_stats") is False
    assert rollup_reads_enabled("junk") is False


def test_source_breakdown_labels_reported_competitions_and_local_programs(app):
    funding_league = FundingLeague(
        name="Reported Stats League",
        country="England",
        region="North West",
        level="youth_regional",
        age_bands=["U19"],
        gender_program="both",
        season_calendar="aug_may",
        data_tier="self_reported",
        registry_status="approved",
        admission_state="open",
    )
    db.session.add(funding_league)
    db.session.flush()
    program = ClubProgram(
        funding_league_id=funding_league.id,
        name="Community Academy",
        legal_name="Community Academy Association",
        slug="reported-stats-community-academy",
        country="England",
        region="North West",
        platform_status="approved",
    )
    db.session.add(program)
    db.session.flush()
    db.session.add_all(
        [
            # A colliding negative API-team id must never supply this name.
            Team(
                team_id=-program.id,
                name="Wrong API Team",
                country="England",
                season=2025,
                is_active=True,
            ),
            PlayerSeasonCell(
                player_api_id=PLAYER,
                season=2025,
                source="club",
                club_api_id=-program.id,
                club_name=None,
                competition_tier="opaque-club-key",
                level_group="senior",
                appearances=2,
                minutes=180,
                detail={"competition": "Community Cup"},
                synced_at=COMPUTED_AT,
            ),
            PlayerSeasonCell(
                player_api_id=PLAYER,
                season=2025,
                source="user",
                club_api_id=0,
                club_name=None,
                competition_tier="opaque-user-key",
                level_group="senior",
                appearances=1,
                minutes=90,
                detail={"competition": "Independent League"},
                synced_at=COMPUTED_AT,
            ),
        ]
    )
    db.session.commit()

    from src.routes.players import _rollup_source_breakdown

    breakdown = _rollup_source_breakdown(PLAYER, 2025)
    assert breakdown["club"][0]["club"] == {
        "id": -program.id,
        "name": "Community Academy",
    }
    assert breakdown["club"][0]["competition_tier"] == "Community Cup"
    assert breakdown["user"][0]["competition_tier"] == "Independent League"
