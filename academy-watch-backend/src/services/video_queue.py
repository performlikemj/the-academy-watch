"""
Job dispatch + claim for video analysis (Phase A).

The DATABASE is the source of truth for job state; the queue is only a wake-up
signal. Workers claim work with a conditional UPDATE (queued -> running), so a
duplicate or replayed message is a harmless no-op, and a worker polling the DB
directly (no Service Bus configured — concierge mode) behaves identically.

Service Bus (when VIDEO_SERVICE_BUS_CONNECTION is set) gives us peek-lock
delivery + DLQ for production scale; its absence must never block a job, which
is also the outbox property: any 'queued' row with no message gets picked up by
the next DB poll.
"""

import logging
import os
from datetime import UTC, datetime, timedelta

from src.models.league import db
from src.models.video import VideoAnalysisJob

logger = logging.getLogger(__name__)

QUEUE_NAME = os.getenv("VIDEO_JOBS_QUEUE", "video-jobs")
STALE_RUNNING_HOURS = 6  # reaper: running with no heartbeat for this long => failed
MAX_ATTEMPTS = 3


def enqueue(job_id: str) -> str:
    """Signal that a queued job exists. Returns the dispatch mode used.
    DB row must already be committed (status='queued') BEFORE calling this —
    a lost signal then degrades to DB polling instead of losing the job."""
    conn = os.getenv("VIDEO_SERVICE_BUS_CONNECTION")
    if not conn:
        return "db-poll"
    try:
        from azure.servicebus import ServiceBusClient, ServiceBusMessage

        with ServiceBusClient.from_connection_string(conn) as client:
            with client.get_queue_sender(QUEUE_NAME) as sender:
                sender.send_messages(ServiceBusMessage(job_id))
        return "service-bus"
    except Exception as e:
        logger.warning("service bus enqueue failed for job %s (DB poll covers it): %s", job_id, e)
        return "db-poll"


def claim_job(job_id: str, worker_id: str) -> bool:
    """Atomically claim a specific job. False means someone else owns it."""
    claimed = (
        db.session.query(VideoAnalysisJob)
        .filter(VideoAnalysisJob.id == job_id, VideoAnalysisJob.status == "queued")
        .update(
            {
                "status": "running",
                "worker_id": worker_id,
                "started_at": datetime.now(UTC),
                "heartbeat_at": datetime.now(UTC),
            },
            synchronize_session=False,
        )
    )
    db.session.commit()
    return bool(claimed)


def claim_next_job(worker_id: str) -> "VideoAnalysisJob | None":
    """DB-poll path: claim the oldest queued job. Safe under concurrency via
    row-level locking (skip_locked keeps idle workers from queueing on the row)."""
    job = (
        db.session.query(VideoAnalysisJob)
        .filter(VideoAnalysisJob.status == "queued")
        .order_by(VideoAnalysisJob.created_at)
        .with_for_update(skip_locked=True)
        .first()
    )
    if job is None:
        db.session.commit()
        return None
    job.status = "running"
    job.worker_id = worker_id
    job.started_at = datetime.now(UTC)
    job.heartbeat_at = datetime.now(UTC)
    db.session.commit()
    return job


def heartbeat(job_id: str, stage: str | None = None, progress: int | None = None) -> None:
    values: dict = {"heartbeat_at": datetime.now(UTC)}
    if stage is not None:
        values["stage"] = stage
    if progress is not None:
        values["progress"] = progress
    db.session.query(VideoAnalysisJob).filter(VideoAnalysisJob.id == job_id).update(values, synchronize_session=False)
    db.session.commit()


def reap_stale_jobs() -> int:
    """Mark heartbeat-dead running jobs failed. Returns count. Callers decide
    refund policy (admin/auto) — this only flips state so retries can happen."""
    cutoff = datetime.now(UTC) - timedelta(hours=STALE_RUNNING_HOURS)
    stale = (
        db.session.query(VideoAnalysisJob)
        .filter(
            VideoAnalysisJob.status == "running",
            VideoAnalysisJob.heartbeat_at < cutoff,
        )
        .update(
            {"status": "failed", "error": f"no heartbeat for {STALE_RUNNING_HOURS}h (stale-fail)"},
            synchronize_session=False,
        )
    )
    db.session.commit()
    if stale:
        logger.warning("stale-failed %d video job(s)", stale)
    return int(stale)
