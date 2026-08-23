def complete_job_with_artifacts(job_id: str, artifacts: dict, gpu_seconds: float | None = None) -> dict:
    """Worker entry point: mark the job succeeded and persist its artifacts — fenced against reap/requeue.

    The job row is taken FOR UPDATE and must still be ``running``; its heartbeat is re-armed under that lock, so the
    reaper (which only takes STALE heartbeats) cannot fire during the seconds of persistence, and a requeue needs a
    failed/cancelled job. The final ``succeeded`` write is a compare-and-swap on ``running``: if anyone moved the job
    meanwhile (an explicit cancel), the job is NOT marked succeeded and ``JobFenced`` is raised.
    """
    from src.models.video import VideoAnalysisJob  # local import avoids cycles
    from src.services.video_queue import JobFenced  # local import avoids cycles

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
    result = persist_artifacts(match, artifacts)
    done = db.session.execute(
        update(VideoAnalysisJob)
        .where(VideoAnalysisJob.id == job_id, VideoAnalysisJob.status == "running")
        .values(
            status="succeeded", stage="persist", progress=100, gpu_seconds=gpu_seconds, completed_at=datetime.now(UTC)
        )
        .execution_options(synchronize_session=False)
    ).rowcount
    db.session.commit()
    if done != 1:
        raise JobFenced(f"job {job_id} was moved during persistence; not marked succeeded")
    return result
