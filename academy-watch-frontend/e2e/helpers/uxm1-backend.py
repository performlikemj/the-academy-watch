"""Foreground, local-only Flask/SQLite fixture for UXM1 real API browser checks.

Run with the repository Python environment; no provider or production access.
The real route blueprints and SQL queries serve every /api request.
"""

# ruff: noqa: E402 -- configure offline mode and SQLite types before route imports

import os
import sys
import tempfile
from datetime import UTC, date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "academy-watch-backend"))
os.environ.update(
    SKIP_API_HANDSHAKE="1", API_USE_STUB_DATA="true", TEST_ONLY_MANU="false"
)
os.environ.setdefault("API_FOOTBALL_FROZEN", "true")
os.environ.setdefault("OPENAI_API_KEY", "test-not-a-real-key")

from flask import Flask
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles

compiles(JSONB, "sqlite")(lambda element, compiler, **kw: "JSON")

from src.extensions import limiter
from src.models.follow import PlayerShadow, PlayerShadowStats
from src.models.league import PlayerStatsCache, Team, UserAccount, db
from src.models.player_match_entry import PlayerMatchEntry
from src.models.showcase import LocalPlayer
from src.models.tracked_player import TrackedPlayer
from src.models.weekly import Fixture, FixturePlayerStats
from src.routes.api import api_bp
from src.routes.player_matches import player_matches_bp
from src.routes.players import players_bp
from src.routes.scout import scout_bp
from src.routes.seasons import seasons_bp
from src.routes.showcase import showcase_bp
from src.utils.academy_window import current_stats_season

with tempfile.TemporaryDirectory(prefix="aw_uxm1f2_") as scratch:
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY="local-uxm1-fixture",
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{scratch}/fixture.db",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        RATELIMIT_ENABLED=False,
    )
    db.init_app(app)
    limiter.init_app(app)
    for blueprint in (
        api_bp,
        players_bp,
        scout_bp,
        seasons_bp,
        showcase_bp,
        player_matches_bp,
    ):
        app.register_blueprint(blueprint, url_prefix="/api")
    with app.app_context():
        db.create_all()
        calendar = current_stats_season()
        season = calendar - 1  # fixtures lag the calendar, including an ongoing freeze
        team = Team(
            team_id=33,
            name="UXM1 Academy",
            country="England",
            season=season,
            is_active=True,
        )
        user = UserAccount(
            email="uxm1-fixture@example.test",
            display_name="Fixture Owner",
            display_name_lower="fixture owner",
        )
        local = LocalPlayer(
            id=71,
            display_name="Real Community Adult",
            birth_date=date(2000, 1, 1),
            birth_year=2000,
            api_player_id=-71,
            status="approved",
            position="Centre half",
        )
        db.session.add_all([team, user, local])
        db.session.flush()
        db.session.add(
            TrackedPlayer(
                player_api_id=42,
                player_name="Real Tracked Adult",
                birth_date="2000-01-01",
                age=26,
                position="Midfielder",
                team_id=team.id,
                status="academy",
                is_active=True,
                current_club_api_id=33,
                current_club_name=team.name,
                data_depth="full_stats",
            )
        )
        fixture = Fixture(
            fixture_id_api=900001,
            season=season,
            date_utc=datetime(season, 9, 1, tzinfo=UTC),
            home_team_api_id=33,
            away_team_api_id=99,
            competition_name="Fixture League",
            home_goals=1,
            away_goals=0,
        )
        db.session.add(fixture)
        db.session.flush()
        db.session.add(
            FixturePlayerStats(
                fixture_id=fixture.id,
                player_api_id=42,
                team_api_id=33,
                position="M",
                minutes=90,
                goals=1,
                assists=0,
                rating=7.0,
            )
        )
        # Both sources have totals older than the directory display season.
        # Omitted season must retain the real routes' latest-data fallbacks.
        db.session.add_all(
            [
                PlayerShadow(
                    player_api_id=43,
                    player_name="Real Shadow Adult",
                    birth_date=date(2000, 1, 1),
                    position="Forward",
                    current_club_name=team.name,
                    is_active=True,
                ),
                PlayerShadowStats(
                    player_api_id=43,
                    team_api_id=33,
                    season=season - 1,
                    appearances=15,
                    goals=6,
                    assists=2,
                    minutes=1200,
                ),
                TrackedPlayer(
                    player_api_id=44,
                    player_name="Real Limited Adult",
                    birth_date="2000-01-01",
                    age=26,
                    position="Forward",
                    team_id=team.id,
                    status="on_loan",
                    is_active=True,
                    current_club_api_id=33,
                    current_club_db_id=team.id,
                    current_club_name=team.name,
                    data_depth="events_only",
                ),
                PlayerStatsCache(
                    player_api_id=44,
                    team_api_id=33,
                    season=season - 1,
                    stats_coverage="limited",
                    appearances=30,
                    goals=2,
                    assists=1,
                    minutes_played=2500,
                ),
            ]
        )
        for year, opponent in [
            (season - 1, "Previous Season United"),
            (season, "Display Season City"),
        ]:
            db.session.add(
                PlayerMatchEntry(
                    player_api_id=-71,
                    season=year,
                    match_date=date(year, 9, 1),
                    opponent=opponent,
                    home_away="home",
                    source="self",
                    status="self_reported",
                    reported_by_user_id=user.id,
                    minutes=90,
                    goals=1,
                    assists=0,
                )
            )
        db.session.commit()
    try:
        app.run(host="127.0.0.1", port=5160, use_reloader=False, threaded=True)
    finally:
        with app.app_context():
            db.session.remove()
            db.engine.dispose()
