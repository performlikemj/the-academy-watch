"""Raw-footage retention (ToS: raw match video is deleted 90 days after upload; derived data is kept).

``VideoMatch.expires_at`` is stamped at upload-complete (routes/video.py, routes/club.py). This module
is the only thing that ENFORCES it: delete the blob, then flip the match to ``expired``. It never touches
tracklets, reports, or jobs.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, func, or_
from src.models.league import db
from src.models.video import VideoMatch
from src.services import video_storage

logger = logging.getLogger(__name__)

# Only footage no pipeline still needs may go: queued/preflight/processing rows are in flight and wait for the
# next run, and created rows have no blob yet.
EXPIRABLE_STATUSES = ("uploaded", "needs_tagging", "finalized", "failed")
# A row that never reached upload-complete keeps status "created" and no expires_at, yet its blob may exist (the
# browser uploaded straight to Azure and vanished). Those are swept by age instead — mirrors the routes' 90-day policy.
ABANDONED_UPLOAD_DAYS = 90


def _utcnow_naive() -> datetime:
    # Columns are naive UTC (the routes store datetime.now(UTC) into a tz-less DateTime).
    return datetime.now(UTC).replace(tzinfo=None)


def _abandoned_before(now: datetime) -> datetime:
    return now - timedelta(days=ABANDONED_UPLOAD_DAYS)


def _still_eligible(match: VideoMatch, now: datetime) -> bool:
    """The in-loop re-check: the same rule as due_matches(), evaluated on a freshly re-read row."""
    if not match.blob_path:
        return False
    if match.status in EXPIRABLE_STATUSES:
        return match.expires_at is not None and match.expires_at <= now
    if match.status == "created":
        return match.created_at is not None and match.created_at <= _abandoned_before(now)
    return False


def due_matches(now: datetime | None = None) -> list[VideoMatch]:
    """Matches whose raw footage is past retention and still present, oldest deadline first — plus abandoned
    uploads (status created, blob path set, older than ABANDONED_UPLOAD_DAYS)."""
    now = now or _utcnow_naive()
    return (
        VideoMatch.query.filter(
            VideoMatch.blob_path.isnot(None),
            or_(
                and_(
                    VideoMatch.expires_at.isnot(None),
                    VideoMatch.expires_at <= now,
                    VideoMatch.status.in_(EXPIRABLE_STATUSES),
                ),
                and_(
                    VideoMatch.status == "created",
                    VideoMatch.created_at.isnot(None),
                    VideoMatch.created_at <= _abandoned_before(now),
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
        # Re-read the row under lock right before acting: a /process call may have claimed the match
        # (uploaded -> queued) after due_matches() ran, and deleting its input would strand a queued job.
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
