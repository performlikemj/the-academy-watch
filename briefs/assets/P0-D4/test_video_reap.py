"""reap_stale_jobs moves heartbeat-dead jobs AND their matches out of processing, so Requeue and retention can act."""

from datetime import UTC, datetime, timedelta

import pytest
from flask import Flask
from src.extensions import limiter
from src.models.follow import PlayerShadow  # noqa: F401
from src.models.funding import ClubProgram  # noqa: F401
from src.models.league import db
from src.models.player_suppression import PlayerSuppression  # noqa: F401
from src.models.showcase import LocalPlayer  # noqa: F401
from src.models.tracked_player import TrackedPlayer  # noqa: F401
from src.models.video import VideoAnalysisJob, VideoMatch
from src.routes.club import club_bp
from src.routes.player_suppression import player_suppression_bp
from src.routes.showcase import showcase_bp
from src.routes.video import video_bp
from src.services import video_queue


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


def _job(match, *, status="running", hours_ago=0.0):
    job = VideoAnalysisJob(
        video_match_id=match.id, status=status, heartbeat_at=datetime.now(UTC) - timedelta(hours=hours_ago)
    )
    db.session.add(job)
    db.session.commit()
    return job


def test_reap_fails_stale_jobs_and_moves_their_matches_out_of_processing(video_app):
    stale_match = VideoMatch(status="processing", blob_path="matches/1.mp4")
    live_match = VideoMatch(status="processing", blob_path="matches/2.mp4")
    done_match = VideoMatch(status="finalized", blob_path="matches/3.mp4")
    db.session.add_all([stale_match, live_match, done_match])
    db.session.commit()
    stale = _job(stale_match, hours_ago=video_queue.STALE_RUNNING_HOURS + 1)
    live = _job(live_match, hours_ago=0.1)
    old_but_finalized = _job(done_match, hours_ago=video_queue.STALE_RUNNING_HOURS + 1)

    assert video_queue.reap_stale_jobs() == 2

    db.session.expire_all()
    assert db.session.get(VideoAnalysisJob, stale.id).status == "failed"
    assert "stale-fail" in db.session.get(VideoAnalysisJob, stale.id).error
    assert db.session.get(VideoMatch, stale_match.id).status == "failed"
    assert db.session.get(VideoAnalysisJob, live.id).status == "running"
    assert db.session.get(VideoMatch, live_match.id).status == "processing"
    assert db.session.get(VideoAnalysisJob, old_but_finalized.id).status == "failed"
    assert db.session.get(VideoMatch, done_match.id).status == "finalized"


def test_reap_with_nothing_stale_returns_zero_and_touches_nothing(video_app):
    match = VideoMatch(status="processing", blob_path="matches/1.mp4")
    db.session.add(match)
    db.session.commit()
    _job(match, hours_ago=0.1)

    assert video_queue.reap_stale_jobs() == 0
    db.session.expire_all()
    assert db.session.get(VideoMatch, match.id).status == "processing"
