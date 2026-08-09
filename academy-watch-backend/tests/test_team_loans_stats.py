"""Regression tests for GET /teams/<id>/loans roster stat attribution.

Covers the fix that makes the team roster read limited-coverage players'
(``data_depth`` events_only / profile_only) stats from ``PlayerStatsCache`` —
the same source the season-scoped profile (``compute_stats``) and Scout Desk
(``_cache_stats_subquery``) use. Before the fix these players rendered
0 apps / 0 mins on the roster while the profile and Scout showed their real
cache totals — a contradiction one click apart.
"""

import os
from datetime import UTC, datetime

import pytest
from flask import Flask
from src.models.league import League, PlayerStatsCache, Team, db
from src.models.season_rollup import PlayerSeasonTotal
from src.models.tracked_player import TrackedPlayer
from src.models.weekly import Fixture, FixturePlayerStats


@pytest.fixture
def teams_app(monkeypatch):
    os.environ.setdefault("SKIP_API_HANDSHAKE", "1")
    os.environ.setdefault("API_USE_STUB_DATA", "true")

    from src.routes.api import api_bp
    from src.routes.teams import teams_bp

    monkeypatch.delenv("SEASON_ROLLUP_READS", raising=False)

    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret-key",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        RATELIMIT_ENABLED=False,
    )
    db.init_app(app)
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(teams_bp, url_prefix="/api")

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def teams_client(teams_app):
    return teams_app.test_client()


@pytest.fixture
def roster_seeded(teams_app):
    """One full-coverage loanee (fixtures) + one limited-coverage loanee (cache)."""
    with teams_app.app_context():
        league = League(
            league_id=39, name="Premier League", country="England", season=2025, is_european_top_league=True
        )
        db.session.add(league)
        db.session.flush()

        parent = Team(
            team_id=33, name="Manchester United", country="England", season=2025, league_id=league.id, is_active=True
        )
        db.session.add(parent)
        db.session.flush()

        full = TrackedPlayer(
            player_api_id=1001,
            player_name="Freddie Fixtures",
            position="Attacker",
            team_id=parent.id,
            status="on_loan",
            current_club_api_id=901,
            current_club_name="Loan FC",
            data_depth="full_stats",
            is_active=True,
        )
        limited = TrackedPlayer(
            player_api_id=1003,
            player_name="Charlie Gloves",
            position="Goalkeeper",
            team_id=parent.id,
            status="on_loan",
            current_club_api_id=902,
            current_club_name="Far FC",
            data_depth="events_only",
            is_active=True,
        )
        db.session.add_all([full, limited])

        fixtures = []
        for i in range(2):
            fixtures.append(
                Fixture(
                    fixture_id_api=5000 + i,
                    season=2025,
                    home_team_api_id=901,
                    away_team_api_id=950 + i,
                    date_utc=datetime(2025, 9, 1 + 7 * i),
                )
            )
        db.session.add_all(fixtures)
        db.session.flush()
        db.session.add_all(
            [
                FixturePlayerStats(
                    fixture_id=fixtures[0].id, player_api_id=1001, team_api_id=901, minutes=90, goals=2, assists=1
                ),
                FixturePlayerStats(
                    fixture_id=fixtures[1].id, player_api_id=1001, team_api_id=901, minutes=80, goals=1, assists=0
                ),
            ]
        )

        prior_fixture = Fixture(
            fixture_id_api=4999,
            season=2024,
            home_team_api_id=901,
            away_team_api_id=949,
            date_utc=datetime(2024, 9, 1),
        )
        db.session.add(prior_fixture)
        db.session.flush()
        db.session.add(
            FixturePlayerStats(
                fixture_id=prior_fixture.id,
                player_api_id=1001,
                team_api_id=901,
                minutes=90,
                goals=9,
                assists=4,
            )
        )

        # Limited-coverage keeper: two cached seasons, the latest must win.
        db.session.add_all(
            [
                PlayerStatsCache(
                    player_api_id=1003, team_api_id=902, season=2024, appearances=10, minutes_played=900, saves=30
                ),
                PlayerStatsCache(
                    player_api_id=1003,
                    team_api_id=902,
                    season=2025,
                    appearances=12,
                    assists=1,
                    minutes_played=1080,
                    saves=41,
                ),
            ]
        )
        computed_at = datetime(2026, 8, 1, tzinfo=UTC)
        db.session.add_all(
            [
                PlayerSeasonTotal(
                    player_api_id=1001,
                    season=2025,
                    level_group="senior",
                    appearances=8,
                    goals=7,
                    assists=6,
                    minutes=700,
                    yellows=2,
                    reds=0,
                    primary_source="journey",
                    fixtures_minutes=170,
                    journey_minutes=700,
                    reconcile_flag="cup-gap",
                    clubs=[{"id": 901, "name": "Loan FC", "appearances": 8, "minutes": 700}],
                    computed_at=computed_at,
                ),
                PlayerSeasonTotal(
                    player_api_id=1003,
                    season=2025,
                    level_group="senior",
                    appearances=14,
                    goals=0,
                    assists=2,
                    minutes=1260,
                    saves=50,
                    primary_source="fixtures",
                    fixtures_minutes=1260,
                    journey_minutes=1200,
                    reconcile_flag="journey-under-sync",
                    clubs=[{"id": 902, "name": "Far FC", "appearances": 14, "minutes": 1260}],
                    computed_at=computed_at,
                ),
            ]
        )
        db.session.commit()
        return parent.id


def _by_id(rows, player_id):
    return next(r for r in rows if r["player_id"] == player_id)


class TestTeamRosterStatAttribution:
    def test_full_coverage_player_reads_fixture_totals(self, teams_client, roster_seeded):
        rows = teams_client.get(f"/api/teams/{roster_seeded}/loans").get_json()
        full = _by_id(rows, 1001)
        assert full["appearances"] == 2
        assert full["minutes_played"] == 170
        assert full["goals"] == 3
        assert full["assists"] == 1

    def test_limited_coverage_player_reads_cache_latest_season(self, teams_client, roster_seeded):
        # Regression: previously 0/0 because the roster only read FixturePlayerStats.
        rows = teams_client.get(f"/api/teams/{roster_seeded}/loans").get_json()
        keeper = _by_id(rows, 1003)
        assert keeper["appearances"] == 12
        assert keeper["minutes_played"] == 1080
        assert keeper["assists"] == 1
        assert keeper["saves"] == 41

    def test_explicit_season_is_honestly_scoped_with_flag_off(self, teams_client, roster_seeded):
        response = teams_client.get(f"/api/teams/{roster_seeded}/loans?season=2024")

        assert response.status_code == 200
        data = response.get_json()
        assert data["season"] == 2024
        full = _by_id(data["loans"], 1001)
        keeper = _by_id(data["loans"], 1003)
        assert (full["appearances"], full["minutes_played"], full["goals"]) == (1, 90, 9)
        assert (keeper["appearances"], keeper["minutes_played"], keeper["saves"]) == (10, 900, 30)

    def test_slug_and_squad_are_honestly_scoped_with_flag_off(self, teams_client, roster_seeded):
        slug = teams_client.get(f"/api/teams/{roster_seeded}/loans/season/2024").get_json()
        squad = teams_client.get(f"/api/teams/{roster_seeded}/players?season=2024").get_json()

        assert slug["season"] == squad["season"] == 2024
        assert _by_id(slug["loans"], 1001)["goals"] == 9
        assert _by_id(squad["players"], 1001)["goals"] == 9

    def test_squad_no_param_keeps_legacy_shape_and_all_time_stats(self, teams_client, roster_seeded):
        data = teams_client.get(f"/api/teams/{roster_seeded}/players").get_json()

        assert set(data) == {"team", "players", "total"}
        full = _by_id(data["players"], 1001)
        assert (full["appearances"], full["minutes_played"], full["goals"]) == (3, 260, 12)

    def test_rollup_flag_uses_totals_and_provenance(self, teams_client, roster_seeded, monkeypatch):
        monkeypatch.setenv("SEASON_ROLLUP_READS", "teams")

        data = teams_client.get(f"/api/teams/{roster_seeded}/loans?season=2025").get_json()

        assert data["season"] == 2025
        full = _by_id(data["loans"], 1001)
        assert (full["appearances"], full["minutes_played"], full["goals"], full["assists"]) == (8, 700, 7, 6)
        assert full["provenance"] == {
            "primary_source": "journey",
            "reconcile_flag": "cup-gap",
            "fixtures_minutes": 170,
            "journey_minutes": 700,
            "computed_at": "2026-08-01T00:00:00",
        }

    def test_season_slug_and_squad_scope_stats(self, teams_client, roster_seeded, monkeypatch):
        monkeypatch.setenv("SEASON_ROLLUP_READS", "teams")

        slug = teams_client.get(f"/api/teams/{roster_seeded}/loans/season/2025").get_json()
        squad = teams_client.get(f"/api/teams/{roster_seeded}/players?season=2025").get_json()

        assert slug["season"] == squad["season"] == 2025
        assert _by_id(slug["loans"], 1001)["minutes_played"] == 700
        assert _by_id(squad["players"], 1001)["minutes_played"] == 700
        assert _by_id(squad["players"], 1001)["provenance"]["primary_source"] == "journey"

    def test_rollup_team_routes_accept_historical_totals(self, teams_client, roster_seeded, monkeypatch):
        db.session.add(
            PlayerSeasonTotal(
                player_api_id=1001,
                season=2007,
                level_group="senior",
                appearances=4,
                goals=3,
                assists=2,
                minutes=360,
                primary_source="journey",
                fixtures_minutes=0,
                journey_minutes=360,
                clubs=[{"id": 901, "name": "Loan FC", "appearances": 4, "minutes": 360}],
                computed_at=datetime(2026, 8, 1, tzinfo=UTC),
            )
        )
        db.session.commit()
        monkeypatch.setenv("SEASON_ROLLUP_READS", "teams")

        loans = teams_client.get(f"/api/teams/{roster_seeded}/loans?season=2007")
        slug = teams_client.get(f"/api/teams/{roster_seeded}/loans/season/2007")
        squad = teams_client.get(f"/api/teams/{roster_seeded}/players?season=2007")

        assert loans.status_code == slug.status_code == squad.status_code == 200
        for rows in (loans.get_json()["loans"], slug.get_json()["loans"], squad.get_json()["players"]):
            historical = _by_id(rows, 1001)
            assert (historical["goals"], historical["minutes_played"]) == (3, 360)

    @pytest.mark.parametrize(
        "path",
        [
            "/loans?season=2023",
            "/loans/season/2023",
            "/players?season=2023",
        ],
    )
    def test_team_season_reads_reject_out_of_range(self, teams_client, roster_seeded, path):
        response = teams_client.get(f"/api/teams/{roster_seeded}{path}")

        assert response.status_code == 400
