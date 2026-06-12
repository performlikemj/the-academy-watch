"""Window gate on GOL on-demand player creation (gol_player_lookup)."""

import os

import pytest
from flask import Flask
from src.models.journey import PlayerJourney
from src.models.league import League, Team, db
from src.models.tracked_player import TrackedPlayer
from src.utils.academy_window import academy_window_start, current_academy_season


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("SKIP_API_HANDSHAKE", "1")
    monkeypatch.setenv("API_USE_STUB_DATA", "true")

    flask_app = Flask(__name__)
    flask_app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret-key",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(flask_app)
    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def lookup(app):
    os.environ.setdefault("API_USE_STUB_DATA", "true")
    from src.services.gol_player_lookup import GolPlayerLookup

    return GolPlayerLookup(app)


def _seed_team(api_id=100, name="Feyenoord"):
    league = League(league_id=39, name="Premier League", country="England", season=2025)
    db.session.add(league)
    db.session.flush()
    team = Team(team_id=api_id, name=name, country="England", season=2025, league_id=league.id, is_active=True)
    db.session.add(team)
    db.session.flush()
    return team


def _journey(player_api_id, *, last_seasons=None, birth_date=None):
    journey = PlayerJourney(
        player_api_id=player_api_id,
        player_name=f"GOL Player {player_api_id}",
        academy_club_ids=[100],
        academy_last_seasons=last_seasons or {},
        birth_date=birth_date,
        current_club_api_id=999,
        current_club_name="Elsewhere FC",
        current_level="First Team",
    )
    db.session.add(journey)
    db.session.flush()
    return journey


def _player_block(name="GOL Player", birth_date=None, age=None):
    return {
        "player": {
            "id": 1,
            "name": name,
            "photo": None,
            "nationality": "England",
            "age": age,
            "position": "Attacker",
            "birth": {"date": birth_date},
        },
        "statistics": [],
    }


class TestGolWindowGate:
    def test_out_of_window_player_not_created(self, app, lookup, monkeypatch):
        team = _seed_team()
        old = academy_window_start() - 1
        journey = _journey(500, last_seasons={"100": old}, birth_date="2001-09-26")
        db.session.commit()
        monkeypatch.setattr(
            "src.services.gol_player_lookup.classify_tracked_player",
            lambda **kwargs: ("first_team", 999, "Elsewhere FC"),
        )

        tracked = lookup._upsert_tracked_player(
            player_id=500, player_block=_player_block(birth_date="2001-09-26", age=24), journey=journey, team=team
        )

        assert tracked is None
        assert TrackedPlayer.query.filter_by(player_api_id=500).first() is None

    def test_in_window_player_created_with_evidence(self, app, lookup, monkeypatch):
        team = _seed_team()
        recent = current_academy_season() - 1
        journey = _journey(501, last_seasons={"100": recent}, birth_date="2006-01-01")
        db.session.commit()
        monkeypatch.setattr(
            "src.services.gol_player_lookup.classify_tracked_player",
            lambda **kwargs: ("first_team", 100, "Feyenoord"),
        )

        tracked = lookup._upsert_tracked_player(
            player_id=501, player_block=_player_block(birth_date="2006-01-01", age=20), journey=journey, team=team
        )

        assert tracked is not None
        assert tracked.is_active is True
        assert tracked.last_academy_season == recent

    def test_existing_row_refreshed_not_gated(self, app, lookup):
        team = _seed_team()
        old = academy_window_start() - 1
        journey = _journey(502, last_seasons={"100": old})
        existing = TrackedPlayer(
            player_api_id=502,
            player_name="GOL Player 502",
            team_id=team.id,
            status="sold",
            data_source="api-football",
            is_active=False,
        )
        db.session.add(existing)
        db.session.commit()

        tracked = lookup._upsert_tracked_player(
            player_id=502, player_block=_player_block(birth_date="2001-01-01", age=25), journey=journey, team=team
        )

        # Existing rows are refreshed (liveness governed by repair endpoints),
        # never force-created or force-deleted by GOL.
        assert tracked is not None
        assert tracked.id == existing.id
        assert tracked.is_active is False
        assert tracked.last_academy_season == old
