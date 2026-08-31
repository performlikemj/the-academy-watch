"""Fenced persistence tests for analysis-only Film Room jobs."""

from datetime import UTC, datetime

import pytest
from src.models.follow import PlayerShadow  # noqa: F401
from src.models.funding import ClubProgram  # noqa: F401
from src.models.league import db
from src.models.player_suppression import PlayerSuppression  # noqa: F401
from src.models.showcase import LocalPlayer  # noqa: F401
from src.models.tracked_player import TrackedPlayer  # noqa: F401
from src.models.video import VideoAnalysisJob, VideoMatch
from src.services.video_analysis_store import complete_job_with_analysis
from src.services.video_queue import JobFenced


def _match_and_job(*, status="running", capture_meta=None, match_status="processing"):
    match = VideoMatch(status=match_status, capture_meta=capture_meta)
    db.session.add(match)
    db.session.commit()
    job = VideoAnalysisJob(video_match_id=match.id, status=status, heartbeat_at=datetime.now(UTC))
    db.session.add(job)
    db.session.commit()
    return match, job


def test_running_job_succeeds_and_stamps_pipeline_version(app):
    match, job = _match_and_job(match_status="queued")
    analysis = {"schema_version": "qwen-analysis-v1", "match_summary": "Blue and red kits are visible."}

    result = complete_job_with_analysis(job.id, analysis, gpu_seconds=12.5)

    assert result == analysis
    db.session.expire_all()
    saved_job = db.session.get(VideoAnalysisJob, job.id)
    assert saved_job.status == "succeeded"
    assert saved_job.progress == 100
    assert saved_job.gpu_seconds == 12.5
    assert saved_job.pipeline_version == "qwen-analysis-v1"
    assert db.session.get(VideoMatch, match.id).status == "queued"


@pytest.mark.parametrize("status", ["failed", "cancelled"])
def test_completion_is_fenced_after_reap_or_cancel(app, status):
    match, job = _match_and_job(status=status)

    with pytest.raises(JobFenced):
        complete_job_with_analysis(job.id, {"schema_version": "qwen-analysis-v1"}, gpu_seconds=1.0)

    db.session.expire_all()
    assert db.session.get(VideoAnalysisJob, job.id).status == status
    assert db.session.get(VideoMatch, match.id).capture_meta is None


def test_capture_meta_merge_preserves_existing_local_keys(app):
    local = {"video": "/private/tmp/match.mp4", "frames": "/private/tmp/frames"}
    match, job = _match_and_job(capture_meta={"local": local, "camera": "high-wide"})
    analysis = {"schema_version": "qwen-analysis-v1", "match_summary": "Sampled observations."}

    complete_job_with_analysis(job.id, analysis)

    db.session.expire_all()
    saved = db.session.get(VideoMatch, match.id)
    assert saved.capture_meta["local"] == local
    assert saved.capture_meta["camera"] == "high-wide"
    assert saved.capture_meta["qwen_analysis"] == analysis
    assert saved.status == "processing"


def test_mid_persistence_fence_rolls_back_analysis(app, monkeypatch):
    match, job = _match_and_job(capture_meta={"local": {"video": "/private/tmp/match.mp4"}})
    original_get = db.session.get
    fenced = False

    def get_with_cancel(model, ident, **kwargs):
        nonlocal fenced
        if model is VideoMatch and not fenced:
            fenced = True
            moved_job = original_get(VideoAnalysisJob, job.id)
            moved_job.status = "cancelled"
            db.session.commit()
        return original_get(model, ident, **kwargs)

    monkeypatch.setattr(db.session, "get", get_with_cancel)

    with pytest.raises(JobFenced):
        complete_job_with_analysis(
            job.id,
            {"schema_version": "qwen-analysis-v1", "match_summary": "Discarded result."},
        )

    db.session.expire_all()
    saved_match = original_get(VideoMatch, match.id)
    saved_job = original_get(VideoAnalysisJob, job.id)
    assert saved_job.status == "cancelled"
    assert "qwen_analysis" not in saved_match.capture_meta
