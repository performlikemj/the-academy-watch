"""Route-level contract tests for synthetic negative player identities.

The tests deliberately install clients that explode on any API-Football use.
Approved adult locals must remain DB-only, while minor and unknown negative
identities share the same neutral 404 across every signed public player route.
"""

from __future__ import annotations

from datetime import date

import pytest
from flask import Flask
from src.auth import _ensure_user_account
from src.extensions import limiter
from src.models.follow import PlayerShadow
from src.models.league import db
from src.models.showcase import LocalPlayer, PlayerShowcaseProfile
from src.services.player_shadow_service import is_external_player_id


@pytest.fixture
def negative_app(monkeypatch):
    monkeypatch.setenv("SKIP_API_HANDSHAKE", "1")
    monkeypatch.setenv("API_USE_STUB_DATA", "true")
    monkeypatch.setenv("SCOUT_INCLUDE_LOCAL_PLAYERS", "true")

    from src.routes.api import api_bp
    from src.routes.journey import journey_bp
    from src.routes.players import players_bp
    from src.routes.scout import scout_bp
    from src.routes.showcase import showcase_bp

    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SECRET_KEY="negative-player-test",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        RATELIMIT_ENABLED=False,
    )
    db.init_app(app)
    limiter.init_app(app)
    app.register_blueprint(journey_bp, url_prefix="/api")
    app.register_blueprint(players_bp, url_prefix="/api")
    app.register_blueprint(scout_bp, url_prefix="/api")
    app.register_blueprint(showcase_bp, url_prefix="/api")
    app.register_blueprint(api_bp, url_prefix="/api")

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(negative_app):
    return negative_app.test_client()


@pytest.fixture
def api_call_counter(monkeypatch):
    calls = []

    class ExplodingClient:
        current_season_start_year = 2025

        def __init__(self, *args, **kwargs):
            calls.append(("construct", args, kwargs))
            raise AssertionError("negative player route constructed an API-Football client")

    class ExplodingLazyClient:
        current_season_start_year = 2025

        def __getattr__(self, name):
            calls.append((name, (), {}))
            raise AssertionError(f"negative player route called API-Football.{name}")

    import src.api_football_client as client_module
    from src.routes import api as api_module
    from src.routes import players as players_module
    from src.services import player_shadow_service

    monkeypatch.setattr(client_module, "APIFootballClient", ExplodingClient)
    monkeypatch.setattr(api_module, "api_client", ExplodingLazyClient())
    monkeypatch.setattr(players_module, "_get_api_client", lambda: ExplodingLazyClient())
    monkeypatch.setattr(player_shadow_service, "_get_api_client", lambda: ExplodingLazyClient())
    return calls


def _seed_local(*, name: str, birth_date: date) -> int:
    creator = _ensure_user_account(f"{name.lower().replace(' ', '-')}@example.com")
    db.session.flush()
    local_player = LocalPlayer(
        display_name=name,
        normalized_name="set-by-validator",
        birth_date=birth_date,
        position="Midfielder",
        country="England",
        club_name="Community FC",
        status="approved",
        created_by_user_id=creator.id,
    )
    db.session.add(local_player)
    db.session.flush()
    signed_id = -local_player.id
    local_player.api_player_id = signed_id
    db.session.add(
        PlayerShadow(
            player_api_id=signed_id,
            player_name=name,
            position=local_player.position,
            nationality=local_player.country,
            birth_date=birth_date,
            current_club_name=local_player.club_name,
            requested_by_user_id=creator.id,
            is_active=True,
        )
    )
    db.session.add(
        PlayerShowcaseProfile(
            local_player_id=local_player.id,
            bio="Local academy prospect",
            positions="Midfielder",
            status="approved",
            updated_by_user_id=creator.id,
        )
    )
    db.session.commit()
    return signed_id


@pytest.fixture
def local_subjects(negative_app):
    return {
        "adult": _seed_local(name="Adult Local", birth_date=date(2000, 1, 1)),
        "minor": _seed_local(name="Minor Local", birth_date=date(2012, 1, 1)),
    }


def _player_paths(player_api_id: int) -> list[str]:
    return [
        f"/api/players/{player_api_id}/profile",
        f"/api/players/{player_api_id}/stats",
        f"/api/players/{player_api_id}/season-stats",
        f"/api/players/{player_api_id}/availability",
        f"/api/players/{player_api_id}/journey?sync=true",
        f"/api/players/{player_api_id}/journey/map?sync=true",
        f"/api/players/{player_api_id}/showcase",
    ]


def test_external_player_guard_is_strictly_positive():
    assert is_external_player_id(1) is True
    assert is_external_player_id(0) is False
    assert is_external_player_id(-1) is False


def test_approved_adult_negative_routes_are_db_only(client, local_subjects, api_call_counter):
    player_api_id = local_subjects["adult"]

    responses = {path: client.get(path) for path in _player_paths(player_api_id)}

    assert {path: response.status_code for path, response in responses.items()} == {path: 200 for path in responses}
    profile = responses[f"/api/players/{player_api_id}/profile"].get_json()
    assert profile["player_id"] == player_api_id
    assert profile["name"] == "Adult Local"
    assert profile["local_player_id"] == -player_api_id
    assert responses[f"/api/players/{player_api_id}/availability"].get_json()["reason"] == "local_player"
    assert responses[f"/api/players/{player_api_id}/journey?sync=true"].get_json()["source"] == "local_player"
    assert responses[f"/api/players/{player_api_id}/journey/map?sync=true"].get_json()["source"] == "local-player"
    assert api_call_counter == []


@pytest.mark.parametrize("subject_key", ["minor", "unknown"])
def test_minor_and_unknown_negative_routes_are_neutral_404(
    client,
    local_subjects,
    api_call_counter,
    subject_key,
):
    player_api_id = local_subjects["minor"] if subject_key == "minor" else -999_999

    responses = [client.get(path) for path in _player_paths(player_api_id)]

    assert all(response.status_code == 404 for response in responses)
    assert all(response.get_json() == {"error": "Player not found"} for response in responses)
    assert api_call_counter == []


def test_local_scout_browse_uses_synthetic_id_and_self_provenance(client, local_subjects):
    response = client.get("/api/scout/players?source=self&per_page=100")

    assert response.status_code == 200
    rows = response.get_json()["players"]
    local_row = next(row for row in rows if row["player_id"] == local_subjects["adult"])
    assert local_row["provenance"] == {
        "source_category": "self",
        "source_label": "Self-reported",
        "primary_source": None,
    }
    assert all(row["player_id"] != local_subjects["minor"] for row in rows)
