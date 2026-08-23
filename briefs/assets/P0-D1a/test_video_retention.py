"""Raw-footage retention: due rows lose their blob and flip to expired; nothing else is touched."""

from datetime import datetime

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
from src.routes.club import club_bp
from src.routes.player_suppression import player_suppression_bp
from src.routes.showcase import showcase_bp
from src.routes.video import video_bp
from src.services import video_retention, video_storage

PAST = datetime(2026, 1, 1, 12, 0, 0)
FUTURE = datetime(2030, 1, 1, 12, 0, 0)
NOW = datetime(2026, 8, 23, 12, 0, 0)


@pytest.fixture
def video_app(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "retention-admin-key")
    monkeypatch.setenv("ADMIN_IP_WHITELIST", "")
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SECRET_KEY="retention-fixture-secret",
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


def _match(*, status, expires_at, blob_path="matches/x.mp4"):
    row = VideoMatch(status=status, expires_at=expires_at, blob_path=blob_path, blob_etag="etag")
    db.session.add(row)
    db.session.commit()
    return row


def test_due_matches_selects_only_past_expirable_rows_with_blobs(video_app):
    due_finalized = _match(status="finalized", expires_at=PAST)
    due_failed = _match(status="failed", expires_at=PAST)
    _match(status="processing", expires_at=PAST)
    _match(status="queued", expires_at=PAST)
    _match(status="finalized", expires_at=FUTURE)
    _match(status="finalized", expires_at=None)
    _match(status="finalized", expires_at=PAST, blob_path=None)
    _match(status="expired", expires_at=PAST, blob_path=None)

    assert [m.id for m in video_retention.due_matches(NOW)] == [due_finalized.id, due_failed.id]


def test_expire_deletes_blob_then_flips_row(video_app, monkeypatch):
    row = _match(status="finalized", expires_at=PAST, blob_path="matches/7/raw.mp4")
    deleted = []
    monkeypatch.setattr(video_storage, "is_configured", lambda: True)
    monkeypatch.setattr(video_storage, "delete_blob", lambda path: deleted.append(path) or True)

    result = video_retention.expire_raw_footage(NOW)

    assert result == {"due": 1, "expired": 1, "failed": 0, "dry_run": False}
    assert deleted == ["matches/7/raw.mp4"]
    fresh = db.session.get(VideoMatch, row.id)
    assert fresh.status == "expired"
    assert fresh.blob_path is None
    assert fresh.blob_etag is None


def test_failed_delete_keeps_row_for_next_run(video_app, monkeypatch):
    row = _match(status="finalized", expires_at=PAST)
    monkeypatch.setattr(video_storage, "is_configured", lambda: True)
    monkeypatch.setattr(video_storage, "delete_blob", lambda path: False)

    result = video_retention.expire_raw_footage(NOW)

    assert result == {"due": 1, "expired": 0, "failed": 1, "dry_run": False}
    fresh = db.session.get(VideoMatch, row.id)
    assert fresh.status == "finalized"
    assert fresh.blob_path == "matches/x.mp4"


def test_dry_run_counts_and_changes_nothing(video_app, monkeypatch):
    row = _match(status="finalized", expires_at=PAST)
    monkeypatch.setattr(video_storage, "is_configured", lambda: True)

    def explode(path):
        raise AssertionError("dry run must not delete")

    monkeypatch.setattr(video_storage, "delete_blob", explode)
    assert video_retention.expire_raw_footage(NOW, dry_run=True) == {"due": 1, "expired": 0, "failed": 0, "dry_run": True}
    assert db.session.get(VideoMatch, row.id).status == "finalized"


def test_unconfigured_storage_still_flips_row(video_app, monkeypatch):
    row = _match(status="uploaded", expires_at=PAST)
    monkeypatch.setattr(video_storage, "is_configured", lambda: False)
    assert video_retention.expire_raw_footage(NOW)["expired"] == 1
    assert db.session.get(VideoMatch, row.id).status == "expired"


def test_delete_blob_treats_404_as_gone(monkeypatch):
    class Gone(Exception):
        status_code = 404

    class FakeBlob:
        def delete_blob(self):
            raise Gone("already deleted")

    class FakeClient:
        def get_blob_client(self, container, path):
            return FakeBlob()

    monkeypatch.setattr(video_storage, "_service_client", lambda: FakeClient())
    assert video_storage.delete_blob("matches/gone.mp4") is True

    class Boom(Exception):
        status_code = 500

    class BoomBlob:
        def delete_blob(self):
            raise Boom("network")

    class BoomClient:
        def get_blob_client(self, container, path):
            return BoomBlob()

    monkeypatch.setattr(video_storage, "_service_client", lambda: BoomClient())
    assert video_storage.delete_blob("matches/stuck.mp4") is False
