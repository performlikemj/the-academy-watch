"""Bounded highlight-only retention, separately enabled at go-live with MJ's go."""

import json
import os
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
from src.models.showcase import LocalPlayer, PlayerProfileClaim
from src.models.video import VideoMatch
from src.services import highlights

AUDIT_DAYS = 90
COUNT_KEYS = ("expired", "highlights", "events", "reviews", "jobs", "takedowns")


def retention_enabled():
    return os.getenv("HIGHLIGHT_RETENTION_SWEEP_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}


def log_disabled():
    print("highlight retention/deletion disabled: HIGHLIGHT_RETENTION_SWEEP_ENABLED is OFF (dry-run; no changes)")


def preview_paths(row):
    paths = {job.blob_path for job in HighlightRenderJob.query.filter_by(highlight_id=row.id) if job.blob_path}
    if row.output_blob_path:
        paths.add(row.output_blob_path)
    return paths


def permanent_key_missing(row):
    claim = db.session.get(PlayerProfileClaim, row.claim_id, populate_existing=True) if row.claim_id else None
    recipient = (
        db.session.get(UserAccount, row.recipient_user_id, populate_existing=True) if row.recipient_user_id else None
    )
    if claim and claim.local_player_id is not None:
        db.session.get(LocalPlayer, claim.local_player_id, populate_existing=True)
    return bool(
        not row.recipient_user_id
        or not recipient
        or recipient.is_tombstone
        or not claim
        or claim.status != "approved"
        or claim.relationship_type != "player"
        or claim.user_account_id != row.recipient_user_id
        or not highlights.claim_subject_matches(claim, row.signed_id)
    )


def sweep_highlights(*, limit=100, dry_run=False):
    if not 1 <= limit <= 500:
        raise ValueError("invalid_limit")
    if not retention_enabled() and not dry_run:
        log_disabled()
        return dict.fromkeys(COUNT_KEYS, 0)
    plan = {"revoke": [], "delete_rows": {}, "queue_cleanup": set()}
    audit = now() - timedelta(days=AUDIT_DAYS)
    # Select ids first, then lock in the same match -> highlight order as writers.
    signed_id = sa.func.coalesce(PlayerHighlight.player_api_id, -PlayerHighlight.local_player_id)
    subject_matches = sa.case(
        (
            PlayerProfileClaim.local_player_id.is_not(None),
            sa.and_(
                LocalPlayer.api_player_id == signed_id,
                LocalPlayer.merged_into_local_player_id.is_(None),
            ),
        ),
        else_=PlayerProfileClaim.player_api_id == signed_id,
    )
    due = (
        db.session.query(PlayerHighlight.id, PlayerHighlight.video_match_id)
        .outerjoin(VideoMatch, VideoMatch.id == PlayerHighlight.video_match_id)
        .outerjoin(PlayerProfileClaim, PlayerProfileClaim.id == PlayerHighlight.claim_id)
        .outerjoin(LocalPlayer, LocalPlayer.id == PlayerProfileClaim.local_player_id)
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
                subject_matches.is_not(True),
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
        if mid and not dry_run:
            VideoMatch.query.filter_by(id=mid).with_for_update().first()
        query = PlayerHighlight.query.filter_by(id=hid).populate_existing()
        row = query.first() if dry_run else query.with_for_update().first()
        if row and not row.revoked_at and permanent_key_missing(row):
            if dry_run:
                plan["revoke"].append(row.id)
                plan["queue_cleanup"].update(preview_paths(row))
            else:
                highlights.revoke(row, None, "consent_key_removed")
            expired += 1
        elif row and not row.revoked_at and row.player_decision != "approve":
            match = db.session.get(VideoMatch, mid) if mid else None
            uploaded = (match.uploaded_at or match.created_at) if match else None
            deadline = (match.expires_at or (uploaded + timedelta(days=90) if uploaded else None)) if match else None
            if not match or match.status == "expired" or not deadline or deadline <= now():
                if dry_run:
                    plan["revoke"].append(row.id)
                    plan["queue_cleanup"].update(preview_paths(row))
                else:
                    highlights.revoke(row, None, "request_expired", immediate_ready=True)
                expired += 1
        if not dry_run:
            db.session.commit()
    terminal = (
        PlayerHighlight.query.filter(PlayerHighlight.revoked_at < audit)
        .order_by(PlayerHighlight.revoked_at, PlayerHighlight.id)
        .limit(limit)
        .all()
    )
    for row in terminal:
        if dry_run:
            plan["queue_cleanup"].update(preview_paths(row))
            continue
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
    if events and not dry_run:
        HighlightConsentEvent.query.filter(HighlightConsentEvent.id.in_(events)).delete(synchronize_session=False)
    # Dry-run must account for the revocations it proposed without mutating rows.
    live_review_clip = sa.select(PlayerHighlight.id).where(
        PlayerHighlight.video_match_id == HighlightFootageReview.video_match_id,
        PlayerHighlight.revoked_at.is_(None),
    )
    if dry_run:
        live_review_clip = live_review_clip.where(PlayerHighlight.id.notin_(plan["revoke"]))
    # Keep only source-bound institutional reviews that still have a live clip.
    reviews = [
        mid
        for (mid,) in db.session.query(HighlightFootageReview.video_match_id)
        .filter(
            HighlightFootageReview.reviewed_at < audit,
            ~sa.exists(live_review_clip),
        )
        .order_by(HighlightFootageReview.video_match_id)
        .limit(limit)
    ]
    if reviews and not dry_run:
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
            live_query = PlayerHighlight.query.filter_by(output_blob_path=job.blob_path).filter(
                PlayerHighlight.revoked_at.is_(None)
            )
            if dry_run:
                live_query = live_query.filter(PlayerHighlight.id.notin_(plan["revoke"]))
            live = live_query.first()
            if not live:
                if dry_run:
                    plan["queue_cleanup"].add(job.blob_path)
                else:
                    queue_cleanup(job.blob_path)
        if not dry_run:
            db.session.delete(job)
    if not dry_run:
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
        if dry_run:
            purged_holds += 1
            continue
        VideoMatch.query.filter_by(id=mid).with_for_update().first()
        hold = HighlightTakedown.query.filter_by(id=hid).populate_existing().with_for_update().first()
        if hold and hold.lifted_at and hold.lifted_at < audit:
            db.session.delete(hold)
            purged_holds += 1
        db.session.commit()
    result = {
        "expired": expired,
        "highlights": len(terminal),
        "events": len(events),
        "reviews": len(reviews),
        "jobs": len(jobs),
        "takedowns": purged_holds,
    }
    if dry_run:
        from src.services.highlights_storage import is_output_path

        plan["delete_rows"] = {
            "player_highlights": [row.id for row in terminal],
            "highlight_consent_events": sorted(
                set(events)
                | {
                    event.id
                    for event in HighlightConsentEvent.query.filter(
                        HighlightConsentEvent.highlight_id.in_([row.id for row in terminal])
                    )
                }
            ),
            "highlight_footage_reviews": reviews,
            "highlight_render_jobs": [job.id for job in jobs],
            "highlight_takedowns": [hid for hid, _ in holds],
        }
        plan["queue_cleanup"] = sorted(path for path in plan["queue_cleanup"] if is_output_path(path))
        print(json.dumps({"dry_run": True, "would": plan}))
    return result
