def reap_stale_jobs() -> int:
    """Mark heartbeat-dead running jobs failed — and move their matches out of ``processing`` so the admin UI
    offers Requeue and retention can sweep overdue footage. Returns the job count. Callers decide refund policy
    (admin/auto) — this only flips state so retries can happen."""
    cutoff = datetime.now(UTC) - timedelta(hours=STALE_RUNNING_HOURS)
    reason = f"no heartbeat for {STALE_RUNNING_HOURS}h (stale-fail)"
    # Compare-and-swap: only rows that are STILL running with an old heartbeat at update time flip, so a worker
    # that resumed in the meantime keeps its job; RETURNING tells us exactly which matches to move.
    reaped = db.session.execute(
        update(VideoAnalysisJob)
        .where(VideoAnalysisJob.status == "running", VideoAnalysisJob.heartbeat_at < cutoff)
        .values(status="failed", error=reason)
        .returning(VideoAnalysisJob.video_match_id)
        .execution_options(synchronize_session=False)
    ).all()
    if not reaped:
        db.session.commit()
        return 0
    match_ids = {row[0] for row in reaped}
    moved = (
        db.session.query(VideoMatch)
        .filter(VideoMatch.id.in_(match_ids), VideoMatch.status == "processing")
        .update({"status": "failed"}, synchronize_session=False)
    )
    db.session.commit()
    logger.warning("stale-failed %d video job(s); %d match(es) moved processing -> failed", len(reaped), moved)
    return len(reaped)
