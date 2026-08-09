"""W1a public season-directory contract."""

from datetime import UTC, datetime

import pytest
from flask import Flask
from src.models.league import db
from src.models.season_rollup import PlayerSeasonTotal
from src.routes.seasons import seasons_bp


@pytest.fixture
def seasons_app(monkeypatch):
    monkeypatch.setenv("SKIP_API_HANDSHAKE", "1")
    application = Flask(__name__)
    application.config.update(
        TESTING=True,
        SECRET_KEY="test-secret",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(application)
    application.register_blueprint(seasons_bp, url_prefix="/api")
    context = application.app_context()
    context.push()
    db.create_all()
    yield application
    db.session.remove()
    db.drop_all()
    context.pop()


def _total(season: int, player: int) -> PlayerSeasonTotal:
    return PlayerSeasonTotal(
        player_api_id=player,
        season=season,
        level_group="senior",
        appearances=1,
        minutes=90,
        primary_source="fixtures",
        fixtures_minutes=90,
        journey_minutes=0,
        computed_at=datetime(2026, 8, 1, tzinfo=UTC),
    )


def test_seasons_shape_order_coverage_and_current_inclusion(seasons_app, monkeypatch):
    import src.routes.seasons as seasons_routes

    monkeypatch.setattr(seasons_routes, "current_stats_season", lambda: 2026)
    monkeypatch.setattr(seasons_routes, "season_bounds", lambda _session: (2007, 2027))
    db.session.add_all(
        [
            _total(2007, 1),
            _total(2025, 1),
            _total(2025, 2),  # DISTINCT season, not one picker row per player
            _total(2027, 1),
            _total(2030, 1),  # outside season_bounds, excluded
        ]
    )
    db.session.commit()

    response = seasons_app.test_client().get("/api/seasons")

    assert response.status_code == 200
    assert response.get_json() == {
        "current_season": 2026,
        "bounds": {"min": 2007, "max": 2027},
        "seasons": [
            {"season": 2027, "label": "2027/28", "has_rollup": True, "is_current": False},
            {"season": 2026, "label": "2026/27", "has_rollup": False, "is_current": True},
            {"season": 2025, "label": "2025/26", "has_rollup": True, "is_current": False},
            {"season": 2007, "label": "2007/08", "has_rollup": True, "is_current": False},
        ],
    }


def test_seasons_includes_current_when_no_rollups_exist(seasons_app, monkeypatch):
    import src.routes.seasons as seasons_routes

    monkeypatch.setattr(seasons_routes, "current_stats_season", lambda: 2026)
    monkeypatch.setattr(seasons_routes, "season_bounds", lambda _session: (2025, 2027))
    data = seasons_app.test_client().get("/api/seasons").get_json()

    assert data["bounds"] == {"min": 2025, "max": 2027}
    assert data["seasons"] == [{"season": 2026, "label": "2026/27", "has_rollup": False, "is_current": True}]
