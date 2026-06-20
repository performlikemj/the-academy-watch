"""Regression: GET /players/<id>/stats must include per-match rows at the club
where a player CURRENTLY plays (loan destination OR the club that bought them),
not only the parent academy club.

Bug history: the team filter in get_public_player_stats added the current club to
the query only when status == "on_loan". Once moved players were reclassified
"sold"/"released" they fell through to the parent-only branch, so the query
filtered out every fixture at their real club and the player page rendered
"No match data available for this player yet." — even though the rows exist in
FixturePlayerStats (the aggregate season-stats endpoint, which derives its club
list straight from FixturePlayerStats, kept showing the appearances).
"""

import os
from datetime import UTC, datetime

import pytest
from flask import Flask
from src.models.league import Team, db
from src.models.tracked_player import TrackedPlayer
from src.models.weekly import Fixture, FixturePlayerStats


class _StubAPIClient:
    """No-network stand-in. Returns a non-empty dict so api_totals_failed is
    False, and games_played=0 so the freshness-sync branch never fires."""

    def __init__(self, *args, **kwargs):
        pass

    def _fetch_player_team_season_totals_api(self, *args, **kwargs):
        return {"games_played": 0}


@pytest.fixture
def app(monkeypatch):
    os.environ.setdefault("SKIP_API_HANDSHAKE", "1")
    os.environ.setdefault("API_USE_STUB_DATA", "true")

    import src.api_football_client as apifc

    monkeypatch.setattr(apifc, "APIFootballClient", _StubAPIClient)

    from src.routes.players import players_bp

    application = Flask(__name__)
    application.config.update(
        TESTING=True,
        SECRET_KEY="test",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        RATELIMIT_ENABLED=False,
    )
    db.init_app(application)
    application.register_blueprint(players_bp, url_prefix="/api")
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


def _seed(status, *, parent_api=33, buyer_api=50, player_api=999001):
    """Seed a tracked player at a parent club who now plays for buyer_api, with a
    single FixturePlayerStats row recorded against buyer_api."""
    parent = Team(team_id=parent_api, name="Parent FC", country="England", season=2025, logo="p.png")
    buyer = Team(team_id=buyer_api, name="Buyer FC", country="England", season=2025, logo="b.png")
    db.session.add_all([parent, buyer])
    db.session.commit()

    tp = TrackedPlayer(
        player_api_id=player_api,
        player_name="Moved Player",
        team_id=parent.id,
        status=status,
        current_club_api_id=buyer_api,
        current_club_name="Buyer FC",
        current_club_db_id=buyer.id,
        is_active=True,
    )
    db.session.add(tp)
    fx = Fixture(
        fixture_id_api=910001,
        season=2025,
        date_utc=datetime(2025, 9, 1, tzinfo=UTC),
        competition_name="Championship",
        home_team_api_id=buyer_api,
        away_team_api_id=77,
        home_goals=1,
        away_goals=0,
    )
    db.session.add(fx)
    db.session.commit()
    db.session.add(FixturePlayerStats(fixture_id=fx.id, player_api_id=player_api, team_api_id=buyer_api))
    db.session.commit()
    return player_api


@pytest.mark.parametrize("status", ["sold", "released", "first_team", "on_loan"])
def test_stats_includes_current_club_regardless_of_status(app, status):
    """Match data for the player's CURRENT club is returned for every status —
    not just on_loan (the original behaviour, which dropped sold/released)."""
    with app.app_context():
        player_api = _seed(status)

    res = app.test_client().get(f"/api/players/{player_api}/stats")
    assert res.status_code == 200
    data = res.get_json()
    assert isinstance(data, list)
    assert len(data) == 1, f"status={status}: expected the buyer-club fixture, got {data}"
    assert data[0]["loan_team_name"] == "Buyer FC"
    assert data[0]["competition"] == "Championship"
