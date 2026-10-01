"""Two-key highlights: every read and byte request rechecks current eligibility."""

import hashlib
import json
import math
import os
import re
from functools import wraps

import sqlalchemy as sa
from flask import abort
from src.models.funding import ClubProgram, ClubRosterMember, ClubSquad
from src.models.highlights import (
    HighlightConsentEvent,
    HighlightFootageReview,
    HighlightRenderJob,
    PlayerHighlight,
    now,
)
from src.models.league import db
from src.models.showcase import LocalPlayer, PlayerProfileClaim
from src.models.video import VideoMatch, VideoPlayerReport, VideoRosterEntry, VideoTracklet
from src.services.account_standing import is_account_active
from src.services.admin_audit import record_admin_event
from src.services.club_directory import is_listed
from src.services.club_publication_hold import club_publication_held, subject_publication_held
from src.services.public_adult import is_public_adult
from src.services.public_player_subject import resolve_public_adult_subject

MAX_CLIPS_PER_MATCH = 100
MAX_CLIP_SECONDS = 60


def enabled():
    return os.getenv("HIGHLIGHTS_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}


def gated(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not enabled():
            abort(404)
        return fn(*args, **kwargs)

    return wrapped


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def member_subject(member):
    if member is None:
        return None
    if member.player_api_id is not None:
        return member.player_api_id
    local = db.session.get(LocalPlayer, member.local_player_id)
    return local.api_player_id if local and local.api_player_id is not None else None


def own_claim(claim, signed_id, user_id=None):
    if claim is None or claim.status != "approved" or claim.relationship_type != "player":
        return False
    if user_id is not None and claim.user_account_id != user_id:
        return False
    if not is_account_active(claim.user_account_id):
        return False
    if claim.local_player_id is not None:
        local = db.session.get(LocalPlayer, claim.local_player_id)
        return bool(local and local.api_player_id == signed_id and local.merged_into_local_player_id is None)
    return claim.player_api_id == signed_id


def claim_for_subject(signed_id):
    claims = (
        PlayerProfileClaim.query.outerjoin(LocalPlayer, LocalPlayer.id == PlayerProfileClaim.local_player_id)
        .filter(
            PlayerProfileClaim.status == "approved",
            PlayerProfileClaim.relationship_type == "player",
            sa.or_(PlayerProfileClaim.player_api_id == signed_id, LocalPlayer.api_player_id == signed_id),
        )
        .order_by(PlayerProfileClaim.id)
        .all()
    )
    claims = [claim for claim in claims if own_claim(claim, signed_id)]
    # Ambiguous ownership is reviewed rather than silently selecting somebody's second key.
    return claims[0] if len(claims) == 1 else None


def adult_recording(match, *, frozen_etag=None):
    """Fail closed without a source-bound human review of EVERY visible person."""
    etag = frozen_etag or (match.blob_etag if match else None)
    if not match or not etag or not match.scoped_snapshot or match.scoped_ready_etag != etag:
        return False
    review = db.session.get(HighlightFootageReview, match.id)
    if not (
        review
        and review.classification == "adult_only"
        and review.source_etag == etag
        and review.source_snapshot == match.scoped_snapshot
        and review.reviewer_user_id
        and is_account_active(review.reviewer_user_id)
    ):
        return False
    squad = db.session.get(ClubSquad, match.squad_id) if match.squad_id else None
    label = getattr(squad, "name", "") or ""
    if squad and squad.age_limit is not None and squad.age_limit <= 18:
        return False
    if re.search(r"\b(?:u|under[ -]?)(?:1[0-8]|[5-9])\b", label, re.I):
        return False
    entries = VideoRosterEntry.query.filter_by(video_match_id=match.id).all()
    if not entries:
        return False
    for entry in entries:
        member = db.session.get(ClubRosterMember, entry.club_roster_member_id) if entry.club_roster_member_id else None
        pid = member_subject(member)
        if not member or member.program_id != match.club_program_id or pid is None or not is_public_adult(pid):
            return False
    return True


def source_fingerprint(match, entry, tracklet, *, frozen_etag=None):
    review = db.session.get(HighlightFootageReview, match.id)
    members = []
    for roster in VideoRosterEntry.query.filter_by(video_match_id=match.id).order_by(VideoRosterEntry.id):
        member = (
            db.session.get(ClubRosterMember, roster.club_roster_member_id) if roster.club_roster_member_id else None
        )
        members.append([roster.id, roster.club_roster_member_id, roster.jersey_number, member_subject(member)])
    return digest(
        {
            "match": [
                match.id,
                match.club_program_id,
                match.squad_id,
                frozen_etag or match.blob_etag,
                match.scoped_snapshot,
                match.scoped_ready_etag,
                match.duration_s,
                match.finalized_at,
            ],
            "roster": members,
            "entry": entry.id,
            "track": [
                tracklet.id,
                tracklet.roster_entry_id,
                tracklet.tag_source,
                tracklet.review_action,
                tracklet.reviewed_at,
                tracklet.contaminated,
                tracklet.dismissed,
                tracklet.first_s,
                tracklet.last_s,
                tracklet.evidence,
            ],
            "review": [review.classification, review.reviewed_at, review.source_etag, review.source_snapshot]
            if review
            else None,
        }
    )


def reviewed_window(match, entry, tracklet_id, start_s, end_s):
    """Client selects a window; its time range and identity are resolved by the server."""
    from src.routes.video import _reel_payload

    track = db.session.get(VideoTracklet, tracklet_id)
    report = VideoPlayerReport.query.filter_by(video_match_id=match.id, roster_entry_id=entry.id).first()
    if not (
        match.status == "finalized"
        and track
        and track.video_match_id == match.id
        and track.roster_entry_id == entry.id
        and track.reviewed_at
        and track.review_action in {"confirmed", "reassigned"}
        and not track.contaminated
        and not track.dismissed
        and report
        and report.identity_confidence == "human_confirmed"
        and report.club_program_id_at_finalize == match.club_program_id
        and report.club_roster_member_id_at_finalize == entry.club_roster_member_id
    ):
        return None
    if any(
        isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
        for value in (start_s, end_s)
    ):
        return None
    if not 0 <= start_s < end_s <= (match.duration_s or 0) or end_s - start_s > MAX_CLIP_SECONDS:
        return None
    if end_s - start_s >= (match.duration_s or 0):  # a short recording still cannot become a full-match public URL
        return None
    reel = _reel_payload(match, [entry])
    player = next((row for row in reel["players"] if row["roster_entry_id"] == entry.id), None)
    if not player or player["number_mismatch"]:
        return None
    window = next(
        (
            window
            for window in player["windows"]
            if window["tracklet_id"] == track.id and window["start_s"] == start_s and window["end_s"] == end_s
        ),
        None,
    )
    return (track, window) if window else None


def current_source(row):
    match = db.session.get(VideoMatch, row.video_match_id) if row.video_match_id else None
    entry = db.session.get(VideoRosterEntry, row.roster_entry_id) if row.roster_entry_id else None
    track = db.session.get(VideoTracklet, row.tracklet_id) if row.tracklet_id else None
    if not match or not entry or not track or entry.video_match_id != match.id:
        return False
    member = db.session.get(ClubRosterMember, entry.club_roster_member_id) if entry.club_roster_member_id else None
    expired = match.status == "expired" and match.blob_path is None and match.blob_etag is None
    if expired and row.render_status != "ready":
        return False  # a missing source cannot create a new cut
    frozen_etag = row.source_etag if expired else None
    return bool(
        match.club_program_id == row.program_id
        and member_subject(member) == row.signed_id
        and match.status in {"finalized", "expired"}
        and track.roster_entry_id == entry.id
        and source_fingerprint(match, entry, track, frozen_etag=frozen_etag) == row.source_fingerprint
        and adult_recording(match, frozen_etag=frozen_etag)
    )


def eligible(row):
    program = db.session.get(ClubProgram, row.program_id)
    claim = db.session.get(PlayerProfileClaim, row.claim_id) if row.claim_id else None
    return bool(
        enabled()
        and not row.revoked_at
        and row.club_picked_at
        and program
        and is_listed(program)
        and not club_publication_held(row.program_id)
        and not subject_publication_held(row.signed_id)
        and is_public_adult(row.signed_id)
        and resolve_public_adult_subject(row.signed_id)
        and own_claim(claim, row.signed_id, row.recipient_user_id)
        and current_source(row)
    )


def public(row):
    return bool(
        eligible(row)
        and row.player_decision == "approve"
        and row.decision_user_id == row.recipient_user_id
        and row.approved_source_version == row.source_version
        and row.render_status == "ready"
        and row.render_source_version == row.source_version
        and row.output_blob_path
        and row.output_etag
    )


def event(row, actor_id, action):
    db.session.add(
        HighlightConsentEvent(
            highlight_id=row.id,
            actor_user_id=actor_id,
            action=action,
            version=row.version,
            source_version=row.source_version,
        )
    )


def notify(row):
    # Notification failure must never prevent revocation or consent writes.
    from sqlalchemy.exc import SQLAlchemyError
    from src.services.notification_outbox import enqueue

    try:
        with db.session.begin_nested():
            enqueue(
                dedupe_key=f"highlight:{row.id}:{row.version}:{row.recipient_user_id}",
                recipient_user_id=row.recipient_user_id,
                event_type="highlight_request",
                entity_type="user_account",
                entity_id=row.recipient_user_id,
                template="highlight_request",
                payload={"highlight_id": row.id, "version": row.version},
            )
    except SQLAlchemyError:
        pass  # Savepoint preserves the publication/consent transaction.


def queue_cut(row):
    live = (
        HighlightRenderJob.query.filter_by(highlight_id=row.id, source_version=row.source_version)
        .filter(HighlightRenderJob.kind == "highlight_cut", HighlightRenderJob.status.in_(("queued", "running")))
        .first()
    )
    if not live:
        db.session.add(HighlightRenderJob(highlight_id=row.id, source_version=row.source_version, kind="highlight_cut"))
        row.render_status = "queued"


def pick(match, data, actor):
    # Program+match lock serializes picks/caps and source editing on this match.
    db.session.refresh(match, with_for_update=True)
    if not adult_recording(match) or club_publication_held(match.club_program_id):
        raise ValueError("adult_recording_review_required")
    entry_id = data.get("roster_entry_id")
    tracklet_id = data.get("tracklet_id")
    if type(entry_id) is not int or type(tracklet_id) is not int:
        raise ValueError("reviewed_window_required")
    entry = VideoRosterEntry.query.filter_by(id=entry_id, video_match_id=match.id).first()
    if not entry:
        raise ValueError("reviewed_window_required")
    selected = reviewed_window(match, entry, tracklet_id, data.get("start_s"), data.get("end_s"))
    if selected is None:
        raise ValueError("reviewed_window_required")
    track, window = selected
    member = db.session.get(ClubRosterMember, entry.club_roster_member_id)
    pid = member_subject(member)
    claim = claim_for_subject(pid)
    if not claim or not is_public_adult(pid) or not resolve_public_adult_subject(pid):
        raise ValueError("adult_self_claim_required")
    if (pid > 0 and report_subject(match, entry) != pid) or (pid < 0 and report_subject(match, entry) != pid):
        raise ValueError("reviewed_identity_required")
    title = data.get("title", "Match moment")
    if not isinstance(title, str) or not title.strip() or len(title) > 160 or any(ord(c) < 32 for c in title):
        raise ValueError("invalid_title")
    fingerprint = source_fingerprint(match, entry, track)
    key = digest([match.id, entry.id, track.id, window, fingerprint, title.strip(), claim.id])
    existing = PlayerHighlight.query.filter_by(pick_key=key).first()
    while existing and existing.revoked_at:
        # A new club pick after removal is a fresh request with no inherited consent.
        key = digest([key, existing.id, existing.version])
        existing = PlayerHighlight.query.filter_by(pick_key=key).first()
    if existing:
        return existing, False
    if PlayerHighlight.query.filter_by(video_match_id=match.id).count() >= MAX_CLIPS_PER_MATCH:
        raise ValueError("highlight_limit_reached")
    row = PlayerHighlight(
        program_id=match.club_program_id,
        video_match_id=match.id,
        roster_entry_id=entry.id,
        tracklet_id=track.id,
        player_api_id=pid if pid > 0 else None,
        local_player_id=-pid if pid < 0 else None,
        claim_id=claim.id,
        recipient_user_id=claim.user_account_id,
        picker_user_id=actor.id,
        source_etag=match.blob_etag,
        source_snapshot=match.scoped_snapshot,
        source_fingerprint=fingerprint,
        pick_key=key,
        start_s=window["start_s"],
        end_s=window["end_s"],
        title=title.strip(),
    )
    db.session.add(row)
    db.session.flush()
    event(row, actor.id, "club_pick")
    record_admin_event(
        actor,
        "highlight_pick",
        "player_highlight",
        row.id,
        "Club selected reviewed window",
        meta={"program_id": row.program_id, "match_id": match.id},
    )
    queue_cut(row)
    notify(row)
    return row, True


def report_subject(match, entry):
    report = VideoPlayerReport.query.filter_by(video_match_id=match.id, roster_entry_id=entry.id).first()
    return (
        (
            report.club_player_api_id_at_finalize
            if report.club_player_api_id_at_finalize is not None
            else -report.club_local_player_id_at_finalize
            if report.club_local_player_id_at_finalize
            else None
        )
        if report
        else None
    )


def revoke(row, actor_id, reason):
    if row.revoked_at:
        return
    from src.workers.highlight_worker import queue_cleanup

    paths = {job.blob_path for job in HighlightRenderJob.query.filter_by(highlight_id=row.id) if job.blob_path}
    if row.output_blob_path:
        paths.add(row.output_blob_path)
    for path in paths:
        queue_cleanup(path)
    row.revoked_at = now()
    row.revoke_reason = reason
    row.player_decision = "private"
    row.approved_source_version = None
    row.version += 1
    HighlightRenderJob.query.filter_by(highlight_id=row.id).filter(
        HighlightRenderJob.status.in_(("queued", "running"))
    ).update({"status": "cancelled", "lease_token": None}, synchronize_session=False)
    event(row, actor_id, reason)


def decide(row, actor, decision, version):
    if type(version) is not int or version != row.version:
        raise ValueError("version_conflict")
    if decision not in {"approve", "private"}:
        raise ValueError("invalid_decision")
    if row.recipient_user_id != actor.id or not own_claim(
        db.session.get(PlayerProfileClaim, row.claim_id), row.signed_id, actor.id
    ):
        raise ValueError("adult_self_claim_required")
    if decision == "approve" and not eligible(row):
        raise ValueError("highlight_unavailable")
    row.player_decision = decision
    row.decision_at = now()
    row.decision_user_id = actor.id
    row.approved_source_version = row.source_version if decision == "approve" else None
    row.version += 1
    event(row, actor.id, decision)
    if decision == "approve" and row.render_status == "failed":
        queue_cut(row)


def dto(row, *, private=False):
    is_public = public(row)
    if row.revoked_at:
        label = "Taken back" if row.revoke_reason == "player_revoke" else "Removed · private"
    elif is_public:
        label = "Public on your page"
    elif row.render_status == "failed":
        label = "Clip not made · still private"
    elif row.player_decision == "approve":
        label = "Approved · preparing clip" if eligible(row) else "Unavailable · still private"
    elif row.player_decision == "private":
        label = "Kept private"
    else:
        label = "Waiting for you"
    program = db.session.get(ClubProgram, row.program_id)
    out = {
        "id": row.id,
        "title": row.title,
        "duration_s": round(row.end_s - row.start_s, 2),
        "program_id": row.program_id,
        "club_name": program.name if program else None,
        "player_id": row.signed_id,
        "clip_url": f"/api/highlights/{row.id}/clip" if is_public else None,
    }
    if private:
        out.update(
            version=row.version,
            player_decision=row.player_decision,
            render_status=row.render_status,
            status_label=label,
            can_approve=eligible(row),
            revoked=bool(row.revoked_at),
            preview_url=f"/api/me/highlight-requests/{row.id}/preview"
            if row.render_status == "ready" and eligible(row)
            else None,
            start_s=row.start_s,
            end_s=row.end_s,
            roster_entry_id=row.roster_entry_id,
            tracklet_id=row.tracklet_id,
        )
    return out


def register_notifications():
    from src.services.notification_outbox import register_template

    def notification_eligible(intent, user):
        row = db.session.get(PlayerHighlight, (intent.payload or {}).get("highlight_id"))
        return bool(
            row
            and row.recipient_user_id == user.id
            and row.version == (intent.payload or {}).get("version")
            and row.player_decision == "pending"
            and eligible(row)
        )

    register_template(
        "highlight_request",
        eligible=notification_eligible,
        render=notification_render,
    )


def candidates(match):
    if not adult_recording(match):
        return []
    from src.routes.video import _reel_payload

    out = []
    for player in _reel_payload(match)["players"]:
        entry = db.session.get(VideoRosterEntry, player["roster_entry_id"])
        member = db.session.get(ClubRosterMember, entry.club_roster_member_id) if entry.club_roster_member_id else None
        pid = member_subject(member)
        if not pid or not is_public_adult(pid) or not claim_for_subject(pid) or report_subject(match, entry) != pid:
            continue
        for window in player["windows"]:
            if len(out) >= 100:
                return out
            if reviewed_window(match, entry, window["tracklet_id"], window["start_s"], window["end_s"]):
                out.append(
                    {"roster_entry_id": entry.id, "player_name": player["player_name"], "player_id": pid, **window}
                )
    return out


def notification_render(intent, user):
    from html import escape

    link = os.getenv("PUBLIC_BASE_URL", "https://theacademywatch.com").rstrip("/") + "/highlight-approvals"
    return {
        "subject": "A highlight is waiting for your decision",
        "html": f'<p>Sign in to Academy Watch to review a highlight request.</p><p><a href="{escape(link, quote=True)}">Review highlights</a></p>',
        "text": f"Sign in to Academy Watch to review a highlight request. {link}",
    }
