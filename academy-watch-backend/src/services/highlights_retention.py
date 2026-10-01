"""Flag-independent, bounded preview, consent and job retention. Run daily via the cut worker."""

from datetime import timedelta

import sqlalchemy as sa
from src.models.highlights import (
    HighlightConsentEvent,
    HighlightFootageReview,
    HighlightRenderJob,
    HighlightTakedown,
    PlayerHighlight,
    now,
)
from src.models.league import UserAccount, db
from src.models.showcase import PlayerProfileClaim
from src.models.video import VideoMatch
from src.services import highlights

AUDIT_DAYS = 90


def permanent_key_missing(row):
    claim = db.session.get(PlayerProfileClaim, row.claim_id) if row.claim_id else None
    recipient = db.session.get(UserAccount, row.recipient_user_id) if row.recipient_user_id else None
    return bool(
        not row.recipient_user_id
        or not recipient
        or recipient.is_tombstone
        or not claim
        or claim.status != "approved"
        or claim.relationship_type != "player"
        or claim.user_account_id != row.recipient_user_id
        or (row.player_api_id is not None and claim.player_api_id != row.player_api_id)
        or (row.local_player_id is not None and claim.local_player_id != row.local_player_id)
    )


def sweep_highlights(*, limit=100):
    if not 1 <= limit <= 500:
        raise ValueError("invalid_limit")
    audit = now() - timedelta(days=AUDIT_DAYS)
    # Select ids first, then lock in the same match -> highlight order as writers.
    due = (
        db.session.query(PlayerHighlight.id, PlayerHighlight.video_match_id)
        .outerjoin(VideoMatch, VideoMatch.id == PlayerHighlight.video_match_id)
        .outerjoin(PlayerProfileClaim, PlayerProfileClaim.id == PlayerHighlight.claim_id)
        .outerjoin(UserAccount, UserAccount.id == PlayerHighlight.recipient_user_id)
        .filter(
            PlayerHighlight.revoked_at.is_(None),
            sa.or_(
                UserAccount.id.is_(None),
                UserAccount.is_tombstone.is_(True),
                PlayerProfileClaim.id.is_(None),
                PlayerProfileClaim.status != "approved",
                PlayerProfileClaim.relationship_type != "player",
                PlayerProfileClaim.user_account_id != PlayerHighlight.recipient_user_id,
                sa.and_(
                    PlayerHighlight.player_api_id.is_not(None),
                    PlayerProfileClaim.player_api_id.is_distinct_from(PlayerHighlight.player_api_id),
                ),
                sa.and_(
                    PlayerHighlight.local_player_id.is_not(None),
                    PlayerProfileClaim.local_player_id.is_distinct_from(PlayerHighlight.local_player_id),
                ),
                sa.and_(
                    PlayerHighlight.player_decision != "approve",
                    sa.or_(
                        VideoMatch.id.is_(None),
                        VideoMatch.status == "expired",
                        VideoMatch.expires_at <= now(),
                        sa.and_(
                            VideoMatch.expires_at.is_(None),
                            sa.func.coalesce(VideoMatch.uploaded_at, VideoMatch.created_at) <= audit,
                        ),
                    ),
                ),
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
        if row and not row.revoked_at and permanent_key_missing(row):
            highlights.revoke(row, None, "consent_key_removed")
            expired += 1
        elif row and not row.revoked_at and row.player_decision != "approve":
            match = db.session.get(VideoMatch, mid) if mid else None
            uploaded = (match.uploaded_at or match.created_at) if match else None
            deadline = (match.expires_at or (uploaded + timedelta(days=90) if uploaded else None)) if match else None
            if not match or match.status == "expired" or not deadline or deadline <= now():
                highlights.revoke(row, None, "request_expired", immediate_ready=True)
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
        HighlightConsentEvent.query.filter_by(highlight_id=row.id).delete(synchronize_session=False)
        db.session.delete(row)
        db.session.commit()
    events = [
        eid
        for (eid,) in db.session.query(HighlightConsentEvent.id)
        .join(PlayerHighlight, PlayerHighlight.id == HighlightConsentEvent.highlight_id)
        .filter(
            HighlightConsentEvent.created_at < audit,
            PlayerHighlight.revoked_at < audit,
        )
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
    holds = (
        db.session.query(HighlightTakedown.id, HighlightTakedown.video_match_id)
        .filter(HighlightTakedown.lifted_at < audit)
        .order_by(HighlightTakedown.id)
        .limit(limit)
        .all()
    )
    purged_holds = 0
    for hid, mid in holds:
        VideoMatch.query.filter_by(id=mid).with_for_update().first()
        hold = HighlightTakedown.query.filter_by(id=hid).populate_existing().with_for_update().first()
        if hold and hold.lifted_at and hold.lifted_at < audit:
            db.session.delete(hold)
            purged_holds += 1
        db.session.commit()
    return {
        "expired": expired,
        "highlights": len(terminal),
        "events": len(events),
        "reviews": len(reviews),
        "jobs": len(jobs),
        "takedowns": purged_holds,
    }
