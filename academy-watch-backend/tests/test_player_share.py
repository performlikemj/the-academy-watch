"""Tests for the player share / OG-unfurl endpoint (GET /players/<id>/share).

Covers the three cases called out in the deliverable: a known player renders
200 with escaped meta, an unknown player 404s, and og:image is omitted when
the player has no photo. Fixture style mirrors tests/test_showcase.py.
"""

import pytest
from flask import Flask
from src.models.follow import PlayerShadow  # noqa: F401 - registers player_shadows for db.create_all()
from src.models.league import Player, db
from src.models.weekly import Fixture, FixturePlayerStats  # noqa: F401 - registers fixture tables

FRONTEND_URL = "https://example.com"


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("SKIP_API_HANDSHAKE", "1")
    monkeypatch.setenv("API_USE_STUB_DATA", "true")
    monkeypatch.setenv("FRONTEND_URL", FRONTEND_URL)

    from src.routes.players import players_bp

    flask_app = Flask(__name__)
    flask_app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret-key",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        RATELIMIT_ENABLED=False,
    )

    db.init_app(flask_app)
    flask_app.register_blueprint(players_bp, url_prefix="/api")

    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def _make_player(player_id=7001, **overrides):
    defaults = dict(
        player_id=player_id,
        name="Kobbie Mainoo",
        nationality="England",
        age=20,
        position="Midfielder",
        photo_url=f"https://media.api-sports.io/football/players/{player_id}.png",
    )
    defaults.update(overrides)
    player = Player(**defaults)
    db.session.add(player)
    db.session.commit()
    return player


class TestPlayerSharePage:
    def test_known_player_returns_200_with_escaped_meta(self, client, app):
        with app.app_context():
            _make_player(
                player_id=7001,
                name="O'Brien & <Test>",
            )

        res = client.get("/api/players/7001/share")
        assert res.status_code == 200
        assert res.mimetype == "text/html"

        html = res.get_data(as_text=True)

        # Raw unescaped name must never appear in the markup.
        assert "O'Brien & <Test>" not in html
        assert "<Test>" not in html

        # HTML-escaped form is present in the title / og:title.
        assert "O&#39;Brien &amp; &lt;Test&gt;" in html
        assert '<meta property="og:title" content="O&#39;Brien &amp; &lt;Test&gt; — Player Profile' in html

        # Canonical / redirect target points at the SPA, built from FRONTEND_URL.
        canonical = f"{FRONTEND_URL}/players/7001"
        assert f'<link rel="canonical" href="{canonical}">' in html
        assert f'<meta http-equiv="refresh" content="0;url={canonical}">' in html
        assert canonical in html  # present in the JS fallback + plain link too

    def test_unknown_player_returns_404(self, client):
        res = client.get("/api/players/999999/share")
        assert res.status_code == 404

    def test_og_image_omitted_when_no_photo(self, client, app):
        with app.app_context():
            _make_player(player_id=7002, name="No Photo Player", photo_url=None)

        res = client.get("/api/players/7002/share")
        assert res.status_code == 200
        html = res.get_data(as_text=True)

        assert "og:image" not in html
        assert 'name="twitter:card" content="summary"' in html
        assert 'content="summary_large_image"' not in html

    def test_og_image_present_when_photo_available(self, client, app):
        with app.app_context():
            _make_player(player_id=7003, name="Has Photo Player")

        res = client.get("/api/players/7003/share")
        assert res.status_code == 200
        html = res.get_data(as_text=True)

        assert '<meta property="og:image" content="https://media.api-sports.io/football/players/7003.png">' in html
        assert 'name="twitter:card" content="summary_large_image"' in html
