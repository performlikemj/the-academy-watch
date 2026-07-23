"""D4c flag-gated reads from player-season rollups.

All tests use SQLite and an inert API-Football client. Season values are API
start-years (2025 == 2025-26).
"""

from datetime import UTC, datetime

import pytest
from flask import Flask
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
        season=2025,
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
                    season=2025,
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
                    season=2025,
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
    assert set(provenance) == {
        "primary_source",
        "reconcile_flag",
        "fixtures_minutes",
        "journey_minutes",
        "computed_at",
    }
    assert provenance == {
        "primary_source": total.primary_source,
        "reconcile_flag": total.reconcile_flag,
        "fixtures_minutes": total.fixtures_minutes,
        "journey_minutes": total.journey_minutes,
        "computed_at": total.computed_at.isoformat(),
    }


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


def test_scout_flag_leaves_leaderboards_on_live_phase_query(client, monkeypatch):
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
    top_scorers = response.get_json()["leaderboards"]["top_scorers"]
    assert top_scorers[0]["player_id"] == SECOND_PLAYER
    assert top_scorers[0]["goals"] == 9
    assert "rollup_missing" not in top_scorers[0]


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
    assert row["provenance"] is None
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
        assert not any(rollup_reads_enabled(surface) for surface in ("season_stats", "player_stats", "scout"))


def test_rollup_flag_one_key_is_surface_scoped(monkeypatch):
    from src.utils.feature_flags import rollup_reads_enabled

    monkeypatch.setenv("SEASON_ROLLUP_READS", " player_stats ")
    assert rollup_reads_enabled("player_stats") is True
    assert rollup_reads_enabled("season_stats") is False
    assert rollup_reads_enabled("scout") is False


def test_rollup_flag_all_keys_enable_all_surfaces(monkeypatch):
    from src.utils.feature_flags import rollup_reads_enabled

    monkeypatch.setenv("SEASON_ROLLUP_READS", "season_stats,player_stats,scout,SCOUT")
    assert all(rollup_reads_enabled(surface) for surface in ("season_stats", "player_stats", "scout"))


def test_rollup_flag_ignores_junk_keys(monkeypatch):
    from src.utils.feature_flags import rollup_reads_enabled

    monkeypatch.setenv("SEASON_ROLLUP_READS", "junk,scout,not-a-surface")
    assert rollup_reads_enabled("scout") is True
    assert rollup_reads_enabled("player_stats") is False
    assert rollup_reads_enabled("junk") is False
