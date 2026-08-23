"""Browser footage redirects use a short read SAS capped at the media token's remaining life, and never cache;
the worker SAS is untouched."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from flask import Flask
from src import auth as auth_module
from src.extensions import limiter
from src.models.follow import PlayerShadow  # noqa: F401
from src.models.funding import ClubProgram  # noqa: F401
from src.models.league import db
from src.models.player_suppression import PlayerSuppression  # noqa: F401
from src.models.showcase import LocalPlayer  # noqa: F401
from src.models.tracked_player import TrackedPlayer  # noqa: F401
from src.models.video import VideoMatch
from src.routes import video as video_routes
from src.routes.club import club_bp
from src.routes.player_suppression import player_suppression_bp
from src.routes.showcase import showcase_bp
from src.routes.video import video_bp
from src.services import video_storage


@pytest.fixture
def video_app(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "media-sas-admin-key")
    monkeypatch.setenv("ADMIN_IP_WHITELIST", "")
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SECRET_KEY="media-sas-fixture-secret",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        RATELIMIT_ENABLED=False,
    )
    db.init_app(app)
    limiter.init_app(app)
    app.register_blueprint(showcase_bp, url_prefix="/api")
    app.register_blueprint(player_suppression_bp, url_prefix="/api")
    app.register_blueprint(club_bp, url_prefix="/api")
    app.register_blueprint(video_bp, url_prefix="/api")
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def test_footage_redirect_uses_media_sas_and_no_store(video_app, monkeypatch):
    match = VideoMatch(status="finalized", blob_path="matches/9/raw.mp4")
    db.session.add(match)
    db.session.commit()
    minted = []
    monkeypatch.setattr(video_storage, "is_configured", lambda: True)
    monkeypatch.setattr(
        video_storage,
        "mint_media_read_sas",
        lambda path, *, seconds: minted.append((path, seconds)) or "https://blob.invalid/short?sig=1",
    )
    monkeypatch.setattr(
        video_storage,
        "mint_read_sas",
        lambda *a, **k: pytest.fail("the 6h worker SAS must not serve browsers"),
    )
    monkeypatch.setattr(video_routes, "verify_media_token", lambda token, match_id: True)
    monkeypatch.setattr(video_routes, "media_token_remaining_seconds", lambda token, match_id: 300)

    resp = video_app.test_client().get(f"/api/admin/video/matches/{match.id}/footage?token=ok")

    assert resp.status_code == 302
    assert resp.headers["Location"] == "https://blob.invalid/short?sig=1"
    assert resp.headers["Cache-Control"] == "private, no-store"
    assert resp.headers["Referrer-Policy"] == "no-referrer"
    assert minted == [("matches/9/raw.mp4", 300)]


def test_footage_redirect_refuses_a_token_with_no_life_left(video_app, monkeypatch):
    match = VideoMatch(status="finalized", blob_path="matches/9/raw.mp4")
    db.session.add(match)
    db.session.commit()
    monkeypatch.setattr(video_storage, "is_configured", lambda: True)
    monkeypatch.setattr(video_storage, "mint_media_read_sas", lambda *a, **k: pytest.fail("must not mint"))
    monkeypatch.setattr(video_routes, "verify_media_token", lambda token, match_id: True)
    monkeypatch.setattr(video_routes, "media_token_remaining_seconds", lambda token, match_id: 0)

    resp = video_app.test_client().get(f"/api/admin/video/matches/{match.id}/footage?token=stale")

    assert resp.status_code == 403


def test_media_read_sas_expires_within_thirty_minutes(monkeypatch):
    captured = {}

    def fake_mint(blob_path, permission, expiry):
        captured["expiry"] = expiry
        return "sig=fake"

    monkeypatch.setattr(video_storage, "_mint_sas", fake_mint)
    monkeypatch.setattr(
        video_storage,
        "_service_client",
        lambda: SimpleNamespace(url="https://acct.blob.core.windows.net/"),
    )
    before = datetime.now(UTC)

    url = video_storage.mint_media_read_sas("matches/9/raw.mp4")

    assert url == "https://acct.blob.core.windows.net/video-matches/matches/9/raw.mp4?sig=fake"
    assert captured["expiry"] <= before + timedelta(minutes=30, seconds=5)
    assert captured["expiry"] >= before + timedelta(minutes=29)
    assert video_storage.MEDIA_READ_SAS_MINUTES == 30
    assert video_storage.READ_SAS_HOURS == 6


def test_media_read_sas_is_capped_by_the_remaining_seconds(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        video_storage,
        "_mint_sas",
        lambda blob_path, permission, expiry: captured.setdefault("e", []).append(expiry) or "sig=fake",
    )
    monkeypatch.setattr(
        video_storage, "_service_client", lambda: SimpleNamespace(url="https://acct.blob.core.windows.net/")
    )
    before = datetime.now(UTC)

    video_storage.mint_media_read_sas("matches/9/raw.mp4", seconds=120)
    video_storage.mint_media_read_sas("matches/9/raw.mp4", seconds=10**6)
    video_storage.mint_media_read_sas("matches/9/raw.mp4", seconds=0)

    short, capped, floor = captured["e"]
    assert before + timedelta(seconds=115) <= short <= before + timedelta(seconds=125)
    assert capped <= before + timedelta(minutes=30, seconds=5)
    assert capped >= before + timedelta(minutes=29, seconds=55)
    assert floor <= before + timedelta(seconds=6)


def test_media_token_remaining_seconds_follows_the_token(video_app):
    token = auth_module.mint_media_token(9)["token"]

    assert 1780 <= auth_module.media_token_remaining_seconds(token, 9) <= 1800
    assert auth_module.media_token_remaining_seconds(token, 10) == 0
    assert auth_module.media_token_remaining_seconds("garbage", 9) == 0
    assert auth_module.media_token_remaining_seconds("", 9) == 0
    assert auth_module.media_token_remaining_seconds(token, 9, max_age=0) == 0
