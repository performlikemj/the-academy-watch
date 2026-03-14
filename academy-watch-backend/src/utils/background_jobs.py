"""Background job utilities for database-backed job tracking.

This module provides a simple job tracking system that works across
gunicorn workers by storing job state in the database.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from src.models.league import db, BackgroundJob

logger = logging.getLogger(__name__)

STALE_JOB_TIMEOUT = timedelta(hours=4)


def create_background_job(job_type: str) -> str:
    """Create a new background job in the database and return its ID.

    Args:
        job_type: Type/category of the job (e.g., 'sync_fixtures', 'seed_loans')

    Returns:
        The UUID string of the created job
    """
    job_id = str(uuid4())
    try:
        job = BackgroundJob(
            id=job_id,
            job_type=job_type,
            status='running',
            progress=0,
            total=0,
            started_at=datetime.now(timezone.utc)
        )
        db.session.add(job)
        db.session.commit()
    except Exception as e:
        logger.error(f'Failed to create background job: {e}')
        db.session.rollback()
    return job_id


def update_job(job_id: str, **kwargs) -> None:
    """Update a background job's status in the database.

    Supported kwargs:
        - progress: int - Current progress count
        - total: int - Total items to process
        - current_player: str - Name of player currently being processed
        - status: str - Job status ('running', 'completed', 'failed')
        - error: str - Error message if job failed
        - results: dict - Results data to store as JSON
        - completed_at: datetime | str - Completion timestamp
    """
    try:
        job = db.session.get(BackgroundJob, job_id)
        if job:
            if 'progress' in kwargs:
                job.progress = kwargs['progress']
            if 'total' in kwargs:
                job.total = kwargs['total']
            if 'current_player' in kwargs:
                job.current_player = kwargs.get('current_player')
            if 'status' in kwargs:
                job.status = kwargs['status']
            if 'error' in kwargs:
                job.error = kwargs.get('error')
            if 'results' in kwargs:
                results = kwargs.get('results')
                if results is not None:
                    job.results_json = json.dumps(results)
            if 'completed_at' in kwargs:
                completed = kwargs.get('completed_at')
                if isinstance(completed, str):
                    job.completed_at = datetime.fromisoformat(completed.replace('Z', '+00:00'))
                else:
                    job.completed_at = completed
            # Always bump updated_at so stale-job detection sees recent activity
            job.updated_at = datetime.now(timezone.utc)
            db.session.commit()
    except Exception as e:
        logger.error(f'Failed to update background job {job_id}: {e}')
        db.session.rollback()


def get_job(job_id: str) -> dict | None:
    """Get a background job's status from the database.

    Auto-fails jobs stuck in 'running' longer than STALE_JOB_TIMEOUT.

    Args:
        job_id: The UUID of the job to retrieve

    Returns:
        Dictionary with job data, or None if not found
    """
    try:
        job = db.session.get(BackgroundJob, job_id)
        if job:
            if job.status == 'running':
                last_active = (job.updated_at or job.started_at or job.created_at)
                elapsed = datetime.now(timezone.utc) - last_active.replace(tzinfo=timezone.utc)
                if elapsed > STALE_JOB_TIMEOUT:
                    logger.warning(
                        f'Job {job_id} stale ({elapsed}), auto-marking failed. '
                        f'Last progress: {job.progress}/{job.total} on {job.current_player}'
                    )
                    job.status = 'failed'
                    job.error = (
                        f'Stale job auto-failed after {elapsed}. '
                        f'Worker likely died at {job.current_player} '
                        f'(progress {job.progress}/{job.total}).'
                    )
                    job.completed_at = datetime.now(timezone.utc)
                    db.session.commit()
            return job.to_dict()
    except Exception as e:
        logger.error(f'Failed to get background job {job_id}: {e}')
        db.session.rollback()
    return None


def cancel_job(job_id: str) -> bool:
    """Cancel a running background job.

    Sets the job status to 'cancelled' so background loops can detect it
    and exit gracefully on their next iteration.

    Returns True if the job was running and is now cancelled.
    """
    try:
        job = db.session.get(BackgroundJob, job_id)
        if job and job.status == 'running':
            job.status = 'cancelled'
            job.error = 'Cancelled by admin'
            job.completed_at = datetime.now(timezone.utc)
            db.session.commit()
            logger.info('Job %s cancelled', job_id)
            return True
        return False
    except Exception as e:
        logger.error('Failed to cancel job %s: %s', job_id, e)
        db.session.rollback()
        return False


def is_job_cancelled(job_id: str) -> bool:
    """Check whether a job has been cancelled.

    Uses a fresh DB read (expunges cached state) so cancellation
    signals are picked up promptly by long-running loops.
    """
    try:
        job = db.session.get(BackgroundJob, job_id)
        if job:
            db.session.refresh(job)
            return job.status == 'cancelled'
    except Exception:
        pass
    return False


# Aliases for backward compatibility with api.py internal naming
_create_background_job = create_background_job
_update_job = update_job
_get_job = get_job
