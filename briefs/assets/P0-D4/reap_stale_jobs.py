def reap_stale_jobs() -> int:
    """Mark heartbeat-dead running jobs failed — and move their matches out of ``processing`` so the admin UI
    offers Requeue and retention can sweep overdue footage. Returns the job count. Callers decide refund policy
    (admin/auto) — this only flips state so retries can happen."""
    cutoff = datetime.now(UTC) - timedelta(hours=STALE_RUNNING_HOURS)
    stale_jobs = (
        db.session.query(VideoAnalysisJob)
        .filter(VideoAnalysisJob.status == "running", VideoAnalysisJob.heartbeat_at < cutoff)
        .all()
    )
    if not stale_jobs:
        return 0
    reason = f"no heartbeat for {STALE_RUNNING_HOURS}h (stale-fail)"
    match_ids = set()
    for job in stale_jobs:
        job.status = "failed"
        job.error = reason
        match_ids.add(job.video_match_id)
    moved = (
        db.session.query(VideoMatch)
        .filter(VideoMatch.id.in_(match_ids), VideoMatch.status == "processing")
        .update({"status": "failed"}, synchronize_session=False)
    )
    db.session.commit()
    logger.warning("stale-failed %d video job(s); %d match(es) moved processing -> failed", len(stale_jobs), moved)
    return len(stale_jobs)
