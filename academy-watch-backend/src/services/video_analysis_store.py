"""Fenced persistence for analysis-only Film Room jobs."""

from datetime import UTC, datetime

from sqlalchemy import update
from src.models.league import db
from src.models.video import VideoMatch


def complete_job_with_analysis(job_id: str, analysis: dict, gpu_seconds: float | None = None) -> dict:
    """Persist Qwen analysis and mark a running job succeeded, fenced against reap/requeue.

    The analysis write and final running-to-succeeded compare-and-swap commit atomically;
    a failed CAS rolls back the analysis so fenced results are discarded.
    Analysis-only jobs produce no tracklets, so this deliberately leaves ``match.status``
    unchanged; the CV/tagging lifecycle statuses remain honest.
    """
    from src.models.video import VideoAnalysisJob  # local import avoids cycles
    from src.services.video_queue import JobFenced  # local import avoids cycles

    if not isinstance(analysis, dict):
        raise ValueError("analysis must be a dict")
    job = db.session.get(VideoAnalysisJob, job_id, with_for_update=True)
    if job is None:
        raise ValueError(f"job {job_id} not found")
    if job.status != "running":
        db.session.rollback()
        raise JobFenced(f"job {job_id} is no longer running (status={job.status}); results discarded")
    job.heartbeat_at = datetime.now(UTC)
    job.stage = "persist"
    db.session.commit()

    match = db.session.get(VideoMatch, job.video_match_id)
    capture_meta = dict(match.capture_meta) if isinstance(match.capture_meta, dict) else {}
    capture_meta["qwen_analysis"] = analysis
    match.capture_meta = capture_meta

    done = db.session.execute(
        update(VideoAnalysisJob)
        .where(VideoAnalysisJob.id == job_id, VideoAnalysisJob.status == "running")
        .values(
            status="succeeded",
            stage="persist",
            progress=100,
            gpu_seconds=gpu_seconds,
            pipeline_version="qwen-analysis-v1",
            completed_at=datetime.now(UTC),
        )
        .execution_options(synchronize_session=False)
    ).rowcount
    if done != 1:
        db.session.rollback()
        raise JobFenced(f"job {job_id} was moved during persistence; not marked succeeded")
    db.session.commit()
    return analysis
