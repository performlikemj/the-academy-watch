"""Browser footage redirects use a 30-minute read SAS and never cache; the worker SAS is untouched."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from flask import Flask
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
        lambda path: minted.append(path) or "https://blob.invalid/short?sig=1",
    )
    monkeypatch.setattr(
        video_storage,
        "mint_read_sas",
        lambda *a, **k: pytest.fail("the 6h worker SAS must not serve browsers"),
    )
    monkeypatch.setattr(
        video_routes, "verify_media_token", lambda token, match_id: True
    )

    resp = video_app.test_client().get(
        f"/api/admin/video/matches/{match.id}/footage?token=ok"
    )

    assert resp.status_code == 302
    assert resp.headers["Location"] == "https://blob.invalid/short?sig=1"
    assert resp.headers["Cache-Control"] == "private, no-store"
    assert resp.headers["Referrer-Policy"] == "no-referrer"
    assert minted == ["matches/9/raw.mp4"]


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

    assert (
        url
        == "https://acct.blob.core.windows.net/video-matches/matches/9/raw.mp4?sig=fake"
    )
    assert captured["expiry"] <= before + timedelta(minutes=30, seconds=5)
    assert captured["expiry"] >= before + timedelta(minutes=29)
    assert video_storage.MEDIA_READ_SAS_MINUTES == 30
    assert video_storage.READ_SAS_HOURS == 6
