"""Raw-footage retention (ToS: raw match video is deleted 90 days after upload; derived data is kept).

``VideoMatch.expires_at`` is stamped at upload-complete (routes/video.py, routes/club.py). This module
is the only thing that ENFORCES it: delete the blob, then flip the match to ``expired``. It never touches
tracklets, reports, or jobs.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, exists, func, or_
from src.models.league import db
from src.models.video import VideoAnalysisJob, VideoMatch
from src.services import video_storage

logger = logging.getLogger(__name__)

# Only footage no pipeline still needs may go: queued/preflight/processing rows are in flight and wait for the
# next run, and created rows have no blob yet.
EXPIRABLE_STATUSES = ("uploaded", "needs_tagging", "finalized", "failed")
# A row that never reached upload-complete keeps status "created" and no expires_at, yet its blob may exist (the
# browser uploaded straight to Azure and vanished). Those are swept by age instead — mirrors the routes' 90-day policy.
ABANDONED_UPLOAD_DAYS = 90
# A write SAS minted for an upload lives this long. No grant may be issued that would outlive the retention deadline,
# and the sweep waits one grant-lifetime past the deadline — so a live grant can never recreate a swept blob.
UPLOAD_GRANT_GRACE = timedelta(minutes=video_storage.UPLOAD_SAS_MINUTES)


def _utcnow_naive() -> datetime:
    # Columns are naive UTC (the routes store datetime.now(UTC) into a tz-less DateTime).
    return datetime.now(UTC).replace(tzinfo=None)


def _abandoned_before(now: datetime) -> datetime:
    return now - timedelta(days=ABANDONED_UPLOAD_DAYS)


def retention_deadline(match: VideoMatch) -> datetime | None:
    """When this match's raw footage is due: the stamped deadline, or (never-completed uploads) created_at + policy."""
    if match.expires_at is not None:
        return match.expires_at
    if match.status == "created" and match.created_at is not None:
        return match.created_at + timedelta(days=ABANDONED_UPLOAD_DAYS)
    return None


def retention_window_closed(match: VideoMatch, now: datetime | None = None) -> bool:
    """True once the retention deadline has passed: upload-complete must not re-stamp or re-verify such a match."""
    now = now or _utcnow_naive()
    deadline = retention_deadline(match)
    return deadline is not None and deadline <= now


def can_issue_upload_grant(match: VideoMatch, now: datetime | None = None) -> bool:
    """False when a write SAS minted now would still be usable at (or after) the retention deadline."""
    now = now or _utcnow_naive()
    deadline = retention_deadline(match)
    return deadline is None or deadline - UPLOAD_GRANT_GRACE > now


def _still_eligible(match: VideoMatch, now: datetime) -> bool:
    """The in-loop re-check: the same rule as due_matches(), evaluated on a freshly re-read row."""
    if not match.blob_path:
        return False
    active_job = (
        db.session.query(VideoAnalysisJob.id)
        .filter(
            VideoAnalysisJob.video_match_id == match.id,
            VideoAnalysisJob.status.in_(("queued", "running")),
        )
        .first()
    )
    if active_job is not None:
        return False
    cutoff = now - UPLOAD_GRANT_GRACE
    if match.status in EXPIRABLE_STATUSES:
        return match.expires_at is not None and match.expires_at <= cutoff
    if match.status == "created":
        return match.created_at is not None and match.created_at <= _abandoned_before(cutoff)
    return False


def due_matches(now: datetime | None = None) -> list[VideoMatch]:
    """Matches whose raw footage is past retention and still present, oldest deadline first — plus abandoned
    uploads (status created, blob path set, older than ABANDONED_UPLOAD_DAYS)."""
    now = now or _utcnow_naive()
    cutoff = now - UPLOAD_GRANT_GRACE  # one grant-lifetime past the deadline: every issued write SAS is dead by then
    active_job = exists().where(
        VideoAnalysisJob.video_match_id == VideoMatch.id,
        VideoAnalysisJob.status.in_(("queued", "running")),
    )
    return (
        VideoMatch.query.filter(
            VideoMatch.blob_path.isnot(None),
            ~active_job,
            or_(
                and_(
                    VideoMatch.expires_at.isnot(None),
                    VideoMatch.expires_at <= cutoff,
                    VideoMatch.status.in_(EXPIRABLE_STATUSES),
                ),
                and_(
                    VideoMatch.status == "created",
                    VideoMatch.created_at.isnot(None),
                    VideoMatch.created_at <= _abandoned_before(cutoff),
                ),
            ),
        )
        .order_by(func.coalesce(VideoMatch.expires_at, VideoMatch.created_at).asc(), VideoMatch.id.asc())
        .all()
    )


def expire_raw_footage(now: datetime | None = None, *, dry_run: bool = False) -> dict:
    """Delete due raw footage and mark those matches expired. Returns counts; a failed delete — or storage
    not being configured at all — is counted as failed, a row that stopped being eligible in the meantime is
    counted as skipped; either way the row stays untouched for the next run and nothing is raised."""
    now = now or _utcnow_naive()
    due = due_matches(now)
    if dry_run:
        return {"due": len(due), "expired": 0, "failed": 0, "skipped": 0, "dry_run": True}
    expired = 0
    failed = 0
    skipped = 0
    for match in due:
        if not video_storage.is_configured():
            # No storage client here: the blob cannot be deleted, so the row must keep pointing at it for a
            # configured run. Forgetting the path would strand the footage in Azure forever.
            failed += 1
            continue
        # Re-read the row under lock right before acting, then check active jobs while holding the same match lock.
        # /process and /analyze take the match lock before creating a job, so they cannot race a delete past this
        # point; if they won the lock first, _still_eligible sees their queued/running job and skips the match.
        db.session.refresh(match, with_for_update=True)
        if not _still_eligible(match, now):
            db.session.rollback()
            skipped += 1
            continue
        if not video_storage.delete_blob(match.blob_path):
            db.session.rollback()
            failed += 1
            continue
        match.status = "expired"
        match.blob_path = None
        match.blob_etag = None
        db.session.commit()
        expired += 1
        logger.info("raw footage expired for video match %s", match.id)
    return {"due": len(due), "expired": expired, "failed": failed, "skipped": skipped, "dry_run": False}
