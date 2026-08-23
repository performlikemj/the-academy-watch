def _move_orphaned_matches_to_failed(match_ids: set) -> int:
    """Matches whose job just failed and that have no other queued/running job go to ``failed`` — the status the
    admin UI offers Requeue for and retention may sweep. Matches are ``queued`` for the whole worker run (nothing
    flips them to processing), so both are handled; a match with a newer live job is left alone."""
    if not match_ids:
        return 0
    other_active = exists().where(
        and_(VideoAnalysisJob.video_match_id == VideoMatch.id, VideoAnalysisJob.status.in_(("queued", "running")))
    )
    return (
        db.session.query(VideoMatch)
        .filter(VideoMatch.id.in_(match_ids), VideoMatch.status.in_(("queued", "processing")), ~other_active)
        .update({"status": "failed"}, synchronize_session=False)
    )


def reap_stale_jobs() -> int:
    """Mark heartbeat-dead running jobs failed — and move their matches out of queued/processing so the admin UI
    offers Requeue and retention can sweep overdue footage. Returns the job count. Callers decide refund policy
    (admin/auto) — this only flips state so retries can happen."""
    cutoff = datetime.now(UTC) - timedelta(hours=STALE_RUNNING_HOURS)
    reason = f"no heartbeat for {STALE_RUNNING_HOURS}h (stale-fail)"
    # Compare-and-swap: only rows that are STILL running with an old heartbeat at update time flip, so a worker
    # that resumed in the meantime keeps its job; RETURNING tells us exactly which matches to consider.
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
    moved = _move_orphaned_matches_to_failed({row[0] for row in reaped})
    db.session.commit()
    logger.warning("stale-failed %d video job(s); %d match(es) moved to failed", len(reaped), moved)
    return len(reaped)


def fail_running_job(job_id: str, *, error: str, gpu_seconds: float | None = None) -> bool:
    """Worker failure path as a compare-and-swap: fail the job only while it is still RUNNING (otherwise a reaper
    or a requeue owns it and nothing may be overwritten), then move its match to failed if no other job is live."""
    failed = db.session.execute(
        update(VideoAnalysisJob)
        .where(VideoAnalysisJob.id == job_id, VideoAnalysisJob.status == "running")
        .values(status="failed", error=error[:2000], gpu_seconds=gpu_seconds, completed_at=datetime.now(UTC))
        .returning(VideoAnalysisJob.video_match_id)
        .execution_options(synchronize_session=False)
    ).all()
    if not failed:
        db.session.commit()
        return False
    _move_orphaned_matches_to_failed({row[0] for row in failed})
    db.session.commit()
    return True
