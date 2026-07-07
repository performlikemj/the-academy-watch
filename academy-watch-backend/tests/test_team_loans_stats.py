"""Regression tests for GET /teams/<id>/loans roster stat attribution.

Covers the fix that makes the team roster read limited-coverage players'
(``data_depth`` events_only / profile_only) stats from ``PlayerStatsCache`` —
the same source the season-scoped profile (``compute_stats``) and Scout Desk
(``_cache_stats_subquery``) use. Before the fix these players rendered
0 apps / 0 mins on the roster while the profile and Scout showed their real
cache totals — a contradiction one click apart.
"""

import os
from datetime import datetime

import pytest
from flask import Flask
from src.models.league import League, PlayerStatsCache, Team, db
from src.models.tracked_player import TrackedPlayer
from src.models.weekly import Fixture, FixturePlayerStats


@pytest.fixture
def teams_app():
    os.environ.setdefault("SKIP_API_HANDSHAKE", "1")
    os.environ.setdefault("API_USE_STUB_DATA", "true")

    from src.routes.teams import teams_bp

    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret-key",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        RATELIMIT_ENABLED=False,
    )
    db.init_app(app)
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
