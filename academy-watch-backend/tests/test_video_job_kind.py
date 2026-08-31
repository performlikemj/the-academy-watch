"""Per-job video pipeline kinds fence workers and analysis submissions."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from src.auth import issue_user_token
from src.models.league import db
from src.models.video import VideoAnalysisJob, VideoCreditLedger, VideoMatch
from src.routes.video import video_bp
from src.services import video_queue

ADMIN_KEY = "video-kind-admin-key"


@pytest.fixture
def video_app(app, monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", ADMIN_KEY)
    monkeypatch.setenv("ADMIN_IP_WHITELIST", "")
    app.register_blueprint(video_bp, url_prefix="/api")
    return app


@pytest.fixture
def video_client(video_app):
    return video_app.test_client()


def _admin_headers():
    token = issue_user_token("video-kind-admin@example.com", role="admin")["token"]
    return {"Authorization": f"Bearer {token}", "X-API-Key": ADMIN_KEY}


def _job(match, pipeline_kind, *, status="queued", age_seconds=0, attempt=1):
    job = VideoAnalysisJob(
        video_match_id=match.id,
        pipeline_kind=pipeline_kind,
        status=status,
        attempt=attempt,
        created_at=datetime.now(UTC) - timedelta(seconds=age_seconds),
    )
    db.session.add(job)
    db.session.commit()
    return job


def test_pinned_claims_refuse_jobs_of_the_other_kind(app):
    match = VideoMatch(status="needs_tagging")
    db.session.add(match)
    db.session.commit()
    cv_job = _job(match, "cv", age_seconds=2)
    qwen_job = _job(match, "qwen_analysis", age_seconds=1)

    assert video_queue.claim_job(qwen_job.id, "cv-worker", "cv") is False
    assert video_queue.claim_job(cv_job.id, "qwen-worker", "qwen_analysis") is False
    assert video_queue.claim_job(cv_job.id, "cv-worker", "cv") is True
    assert video_queue.claim_job(qwen_job.id, "qwen-worker", "qwen_analysis") is True

    db.session.expire_all()
    assert db.session.get(VideoAnalysisJob, cv_job.id).worker_id == "cv-worker"
    assert db.session.get(VideoAnalysisJob, qwen_job.id).worker_id == "qwen-worker"


def test_loop_claims_only_the_workers_kind(app):
    match = VideoMatch(status="needs_tagging")
    db.session.add(match)
    db.session.commit()
    qwen_job = _job(match, "qwen_analysis", age_seconds=2)
    cv_job = _job(match, "cv", age_seconds=1)

    claimed_cv = video_queue.claim_next_job("cv-worker", "cv")
    assert claimed_cv.id == cv_job.id
    assert db.session.get(VideoAnalysisJob, qwen_job.id).status == "queued"

    claimed_qwen = video_queue.claim_next_job("qwen-worker", "qwen_analysis")
    assert claimed_qwen.id == qwen_job.id
    assert claimed_qwen.worker_id == "qwen-worker"


def test_analyze_queues_qwen_job_without_debit(video_client):
    match = VideoMatch(status="needs_tagging", blob_path="matches/analysis.mp4")
    db.session.add(match)
    db.session.commit()

    with patch("src.routes.video.video_queue.enqueue", return_value="fixture") as enqueue:
        response = video_client.post(f"/api/admin/video/matches/{match.id}/analyze", headers=_admin_headers())

    assert response.status_code == 202
    payload = response.get_json()
    assert payload["job"]["pipeline_kind"] == "qwen_analysis"
    assert payload["dispatch"] == "fixture"
    job = VideoAnalysisJob.query.filter_by(video_match_id=match.id).one()
    assert job.status == "queued"
    assert db.session.get(VideoMatch, match.id).status == "needs_tagging"
    assert VideoCreditLedger.query.count() == 0
    enqueue.assert_called_once_with(job.id)


@pytest.mark.parametrize("status", ["uploaded", "queued", "failed", "expired"])
def test_analyze_requires_completed_cv_artifacts(video_client, status):
    match = VideoMatch(status=status)
    db.session.add(match)
    db.session.commit()

    with patch("src.routes.video.video_queue.enqueue") as enqueue:
        response = video_client.post(f"/api/admin/video/matches/{match.id}/analyze", headers=_admin_headers())

    assert response.status_code == 400
    assert "completed CV artifacts required" in response.get_json()["error"]
    assert VideoAnalysisJob.query.count() == 0
    assert VideoCreditLedger.query.count() == 0
    enqueue.assert_not_called()


@pytest.mark.parametrize("job_status", ["queued", "running"])
def test_analyze_rejects_duplicate_active_qwen_job(video_client, job_status):
    match = VideoMatch(status="finalized")
    db.session.add(match)
    db.session.commit()
    existing = _job(match, "qwen_analysis", status=job_status)

    with patch("src.routes.video.video_queue.enqueue") as enqueue:
        response = video_client.post(f"/api/admin/video/matches/{match.id}/analyze", headers=_admin_headers())

    assert response.status_code == 409
    assert VideoAnalysisJob.query.filter_by(video_match_id=match.id).one().id == existing.id
    assert VideoCreditLedger.query.count() == 0
    enqueue.assert_not_called()


def test_requeue_preserves_pipeline_kind_and_cv_lifecycle_status(video_client):
    match = VideoMatch(status="needs_tagging", blob_path="matches/analysis.mp4")
    db.session.add(match)
    db.session.commit()
    failed = _job(match, "qwen_analysis", status="failed", attempt=2)
    failed.pipeline_version = "qwen-analysis-v1"
    db.session.commit()

    verified = {"ok": True, "etag": "etag-analysis", "size_bytes": 2048}
    with (
        patch("src.routes.video.video_storage.verify_expected_blob", return_value=verified),
        patch("src.routes.video.video_queue.enqueue", return_value="fixture"),
    ):
        response = video_client.post(f"/api/admin/video/matches/{match.id}/requeue", headers=_admin_headers())

    assert response.status_code == 202
    jobs = VideoAnalysisJob.query.filter_by(video_match_id=match.id).order_by(VideoAnalysisJob.attempt).all()
    assert [job.pipeline_kind for job in jobs] == ["qwen_analysis", "qwen_analysis"]
    assert jobs[-1].attempt == 3
    assert jobs[-1].pipeline_version == "qwen-analysis-v1"
    assert db.session.get(VideoMatch, match.id).status == "needs_tagging"
    assert VideoCreditLedger.query.count() == 0
