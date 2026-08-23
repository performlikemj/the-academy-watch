"""Fencing: a reaped/cancelled job cannot be heartbeaten, completed, or failed-over by a zombie worker."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from flask import Flask
from sqlalchemy import update
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
from src.services import video_identity, video_queue
from src.workers.vision_worker import process_job


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


def _match_and_job(*, job_status="running"):
    match = VideoMatch(status="processing", blob_path="matches/1.mp4")
    db.session.add(match)
    db.session.commit()
    job = VideoAnalysisJob(
        video_match_id=match.id, status=job_status, heartbeat_at=datetime.now(UTC) - timedelta(hours=1)
    )
    db.session.add(job)
    db.session.commit()
    return match, job


def test_heartbeat_touches_only_a_running_job(video_app):
    _, running = _match_and_job(job_status="running")
    _, reaped = _match_and_job(job_status="failed")
    before = reaped.heartbeat_at

    assert video_queue.heartbeat(running.id, stage="detect", progress=5) is True
    assert video_queue.heartbeat(reaped.id, stage="detect", progress=5) is False

    db.session.expire_all()
    assert db.session.get(VideoAnalysisJob, running.id).stage == "detect"
    assert db.session.get(VideoAnalysisJob, reaped.id).heartbeat_at == before
    assert db.session.get(VideoAnalysisJob, reaped.id).stage != "detect"


def test_completion_refuses_a_job_that_is_no_longer_running(video_app, monkeypatch):
    match, reaped = _match_and_job(job_status="failed")
    monkeypatch.setattr(
        video_identity, "persist_artifacts", lambda *a, **k: pytest.fail("must not persist for a fenced job")
    )

    with pytest.raises(video_queue.JobFenced):
        video_identity.complete_job_with_artifacts(reaped.id, {"fragments": [], "votes": []})

    db.session.expire_all()
    assert db.session.get(VideoAnalysisJob, reaped.id).status == "failed"
    assert db.session.get(VideoMatch, match.id).status == "processing"


def test_worker_stops_and_writes_nothing_when_fenced_at_first_heartbeat():
    app = Flask(__name__)
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:", SQLALCHEMY_TRACK_MODIFICATIONS=False)
    db.init_app(app)
    job = SimpleNamespace(video_match_id=1, status="failed", error="stale-fail", gpu_seconds=None, completed_at=None)
    match = SimpleNamespace(blob_path="matches/1/video.mp4", blob_etag=None, status="queued")

    def fake_get(model, _identifier):
        return job if model is VideoAnalysisJob else match

    with app.app_context():
        with (
            patch.object(db.session, "get", side_effect=fake_get),
            patch.object(db.session, "rollback") as rollback,
            patch.object(db.session, "commit") as commit,
            patch("src.services.video_queue.heartbeat", return_value=False),
            patch("src.services.video_storage.verify_expected_blob", side_effect=AssertionError("must not verify")),
        ):
            assert process_job(app, "job-1") is False

    assert job.status == "failed"
    assert match.status == "queued"
    rollback.assert_called_once()
    commit.assert_not_called()


def test_completion_marks_a_running_job_succeeded_after_persisting(video_app, monkeypatch):
    match, running = _match_and_job(job_status="running")
    persisted = []
    monkeypatch.setattr(video_identity, "persist_artifacts", lambda m, a: persisted.append(m.id) or {"tracklets": 0})

    result = video_identity.complete_job_with_artifacts(running.id, {"fragments": [], "votes": []}, gpu_seconds=2.5)

    assert result == {"tracklets": 0}
    assert persisted == [match.id]
    db.session.expire_all()
    job = db.session.get(VideoAnalysisJob, running.id)
    assert job.status == "succeeded"
    assert job.progress == 100
    assert job.gpu_seconds == 2.5


def test_completion_is_fenced_if_the_job_is_moved_during_persistence(video_app, monkeypatch):
    match, running = _match_and_job(job_status="running")

    def cancel_underneath(m, artifacts):
        # An admin cancels while artifacts are being written (another transaction).
        db.session.execute(update(VideoAnalysisJob).where(VideoAnalysisJob.id == running.id).values(status="cancelled"))
        db.session.commit()
        return {"tracklets": 0}

    monkeypatch.setattr(video_identity, "persist_artifacts", cancel_underneath)

    with pytest.raises(video_queue.JobFenced):
        video_identity.complete_job_with_artifacts(running.id, {"fragments": [], "votes": []})

    db.session.expire_all()
    assert db.session.get(VideoAnalysisJob, running.id).status == "cancelled"
