def heartbeat(job_id: str, stage: str | None = None, progress: int | None = None) -> bool:
    """Touch a RUNNING job. Returns False when the job is no longer running (reaped/cancelled/finished) — the
    worker must then stop: it has been fenced out and another actor owns the job/match."""
    values: dict = {"heartbeat_at": datetime.now(UTC)}
    if stage is not None:
        values["stage"] = stage
    if progress is not None:
        values["progress"] = progress
    touched = (
        db.session.query(VideoAnalysisJob)
        .filter(VideoAnalysisJob.id == job_id, VideoAnalysisJob.status == "running")
        .update(values, synchronize_session=False)
    )
    db.session.commit()
    return touched == 1
