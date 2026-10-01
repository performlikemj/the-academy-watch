"""Flag-independent, bounded preview, consent and job retention. Run daily via the cut worker."""

from datetime import timedelta

import sqlalchemy as sa
from src.models.highlights import (
    HighlightConsentEvent,
    HighlightFootageReview,
    HighlightRenderJob,
    PlayerHighlight,
    now,
)
from src.models.league import db
from src.models.video import VideoMatch
from src.services import highlights

PREVIEW_DAYS = 14
AUDIT_DAYS = 90


def sweep_highlights(*, limit=100):
    if not 1 <= limit <= 500:
        raise ValueError("invalid_limit")
    cutoff, audit = now() - timedelta(days=PREVIEW_DAYS), now() - timedelta(days=AUDIT_DAYS)
    # Select ids first, then lock in the same match -> highlight order as writers.
    due = (
        db.session.query(PlayerHighlight.id, PlayerHighlight.video_match_id)
        .outerjoin(VideoMatch, VideoMatch.id == PlayerHighlight.video_match_id)
        .filter(
            PlayerHighlight.revoked_at.is_(None),
            PlayerHighlight.player_decision != "approve",
            sa.or_(
                PlayerHighlight.created_at < cutoff,
                VideoMatch.status == "expired",
                VideoMatch.expires_at <= now(),
                sa.func.coalesce(VideoMatch.uploaded_at, VideoMatch.created_at) < audit,
            ),
        )
        .order_by(PlayerHighlight.created_at, PlayerHighlight.id)
        .limit(limit)
        .all()
    )
    expired = 0
    for hid, mid in due:
        if mid:
            VideoMatch.query.filter_by(id=mid).with_for_update().first()
        row = PlayerHighlight.query.filter_by(id=hid).populate_existing().with_for_update().first()
        if row and not row.revoked_at and row.player_decision != "approve":
            highlights.revoke(row, None, "request_expired")
            expired += 1
        db.session.commit()
    terminal = (
        PlayerHighlight.query.filter(PlayerHighlight.revoked_at < audit)
        .order_by(PlayerHighlight.revoked_at, PlayerHighlight.id)
        .limit(limit)
        .all()
    )
    for row in terminal:
        if row.video_match_id:
            VideoMatch.query.filter_by(id=row.video_match_id).with_for_update().first()
        # Queues all durable attempt paths even on SQLite (PG cascade trigger is the backstop).
        highlights.discard_preview(row)
        db.session.delete(row)
        db.session.commit()
    events = [
        eid
        for (eid,) in db.session.query(HighlightConsentEvent.id)
        .filter(HighlightConsentEvent.created_at < audit)
        .order_by(HighlightConsentEvent.id)
        .limit(limit)
    ]
    if events:
        HighlightConsentEvent.query.filter(HighlightConsentEvent.id.in_(events)).delete(synchronize_session=False)
    # Keep only source-bound institutional reviews that still have a live clip.
    reviews = [
        mid
        for (mid,) in db.session.query(HighlightFootageReview.video_match_id)
        .filter(
            HighlightFootageReview.reviewed_at < audit,
            ~sa.exists(
                sa.select(PlayerHighlight.id).where(
                    PlayerHighlight.video_match_id == HighlightFootageReview.video_match_id,
                    PlayerHighlight.revoked_at.is_(None),
                )
            ),
        )
        .order_by(HighlightFootageReview.video_match_id)
        .limit(limit)
    ]
    if reviews:
        HighlightFootageReview.query.filter(HighlightFootageReview.video_match_id.in_(reviews)).delete(
            synchronize_session=False
        )
    jobs = (
        HighlightRenderJob.query.filter(
            HighlightRenderJob.status.in_(("succeeded", "cancelled", "failed")),
            ~sa.and_(HighlightRenderJob.kind == "highlight_delete", HighlightRenderJob.status == "failed"),
            sa.func.coalesce(HighlightRenderJob.completed_at, HighlightRenderJob.created_at) < audit,
        )
        .order_by(HighlightRenderJob.created_at, HighlightRenderJob.id)
        .limit(limit)
        .all()
    )
    from src.workers.highlight_worker import queue_cleanup

    for job in jobs:
        # A failed delete remains actionable until storage cleanup succeeds.
        if job.kind == "highlight_delete" and job.status == "failed":
            continue
        if job.kind == "highlight_cut" and job.blob_path:
            live = (
                PlayerHighlight.query.filter_by(output_blob_path=job.blob_path)
                .filter(PlayerHighlight.revoked_at.is_(None))
                .first()
            )
            if not live:
                queue_cleanup(job.blob_path)
        db.session.delete(job)
    db.session.commit()
    return {
        "expired": expired,
        "highlights": len(terminal),
        "events": len(events),
        "reviews": len(reviews),
        "jobs": len(jobs),
    }
