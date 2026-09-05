"""Immutable private revisions and shared participant policy; never commits."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import timedelta
from uuid import uuid4

import bleach
import sqlalchemy as sa
from src.models.club_invitation import (
    ClubInvitation,
    InvitationError,
    canonical_uuid,
    effective_relationship,
    lock_context,
    strict_manager,
    utcnow,
)
from src.models.league import UserAccount, db


class PlayerFeedback(db.Model):
    __tablename__ = "player_feedback"
    __table_args__ = (
        sa.UniqueConstraint("thread_id", "revision", name="uq_player_feedback_revision"),
        sa.UniqueConstraint("program_id", "client_request_id", name="uq_player_feedback_request"),
        sa.CheckConstraint("revision >= 1", name="ck_player_feedback_revision"),
        sa.CheckConstraint(
            "player_api_id <> 0 AND player_api_id BETWEEN -2147483647 AND 2147483647", name="ck_player_feedback_subject"
        ),
        sa.Index("ix_player_feedback_recipient", "recipient_user_id", "published_at", "id"),
        sa.Index("ix_player_feedback_invitation", "invitation_id", "thread_id", "revision"),
    )
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid4()))
    thread_id = db.Column(db.String(36), nullable=False)
    revision = db.Column(db.Integer, nullable=False)
    program_id = db.Column(db.Integer, db.ForeignKey("club_programs.id"), nullable=False)
    invitation_id = db.Column(db.String(36), db.ForeignKey("club_invitations.id"), nullable=False)
    claim_id = db.Column(db.Integer, db.ForeignKey("player_profile_claims.id"), nullable=False)
    recipient_user_id = db.Column(db.Integer, db.ForeignKey("user_accounts.id"), nullable=False)
    player_api_id = db.Column(db.Integer, nullable=False)
    author_user_id = db.Column(db.Integer, db.ForeignKey("user_accounts.id", ondelete="SET NULL"))
    video_match_id = db.Column(db.Integer, db.ForeignKey("video_matches.id", ondelete="SET NULL"))
    title = db.Column(db.String(140), nullable=False)
    body = db.Column(db.Text, nullable=False)
    observation_refs = db.Column(db.JSON, nullable=False, default=list, server_default=sa.text("'[]'"))
    client_request_id = db.Column(db.String(36), nullable=False)
    request_hash = db.Column(db.String(64), nullable=False)
    published_at = db.Column(db.DateTime(), nullable=False, default=utcnow)
    acknowledged_at = db.Column(db.DateTime())
    withdrawn_at = db.Column(db.DateTime())
    audit_expires_at = db.Column(db.DateTime())


class FeedbackError(Exception):
    def __init__(self, code="invalid_request", status=400, *, current_revision=None, closure=False):
        self.code, self.status = code, status
        self.current_revision, self.closure = current_revision, closure
        super().__init__(code)


def uuid(value):
    try:
        return canonical_uuid(value)
    except InvitationError:
        raise FeedbackError() from None


def integer(value, *, signed=False):
    if isinstance(value, bool) or not isinstance(value, int) or not 0 < (abs(value) if signed else value) <= 2147483647:
        raise FeedbackError()
    return value


def plain_text(value, maximum):
    if not isinstance(value, str) or not 1 <= len(value) <= maximum or "\x00" in value:
        raise FeedbackError()
    value = bleach.clean(value, tags=[], attributes={}, strip=True).strip()
    if not value or len(value) > maximum:
        raise FeedbackError()
    return value


def authored_payload(payload, *, correction=False):
    required = {"client_request_id", "title", "body", "expected_revision" if correction else "invitation_id"}
    if (
        not isinstance(payload, dict)
        or not required <= set(payload)
        or set(payload) - required - {"video_match_id", "observation_refs"}
    ):
        raise FeedbackError()
    result = {
        "client_request_id": uuid(payload["client_request_id"]),
        "title": plain_text(payload["title"], 140),
        "body": plain_text(payload["body"], 4000),
        "video_match_id": integer(payload["video_match_id"]) if payload.get("video_match_id") is not None else None,
    }
    key = "expected_revision" if correction else "invitation_id"
    result[key] = integer(payload[key]) if correction else uuid(payload[key])
    refs = payload.get("observation_refs", [])
    if not isinstance(refs, list) or len(refs) > 10:
        raise FeedbackError()
    result["observation_refs"] = []
    for ref in refs:
        if not isinstance(ref, dict) or set(ref) != {"label", "timestamp_s"}:
            raise FeedbackError()
        timestamp = ref["timestamp_s"]
        if isinstance(timestamp, int) and not isinstance(timestamp, bool):
            try:
                timestamp = float(timestamp)
            except OverflowError:
                raise FeedbackError() from None
        if timestamp is not None and (
            isinstance(timestamp, bool)
            or not isinstance(timestamp, (int, float))
            or not math.isfinite(timestamp)
            or timestamp < 0
        ):
            raise FeedbackError()
        result["observation_refs"].append(
            {"label": plain_text(ref["label"], 160), "timestamp_s": float(timestamp) if timestamp is not None else None}
        )
    return result


def relationship_matches(session, row):
    invitation = session.get(ClubInvitation, row.invitation_id)
    return bool(
        invitation
        and invitation.program_id == row.program_id
        and invitation.player_api_id == row.player_api_id
        and invitation.recipient_user_id == row.recipient_user_id
        and effective_relationship(session, invitation, claim_id=row.claim_id)
    )


def observe_closure(session, row, *, now=None):
    """Once closed, a thread is audit-only even if eligibility later returns."""
    if row.withdrawn_at is None and row.audit_expires_at is None and relationship_matches(session, row):
        return False
    deadline = row.audit_expires_at or ((row.withdrawn_at or now or utcnow()) + timedelta(days=30))
    session.query(PlayerFeedback).filter_by(thread_id=row.thread_id).filter(
        PlayerFeedback.audit_expires_at.is_(None)
    ).update({PlayerFeedback.audit_expires_at: deadline}, synchronize_session="fetch")
    return True


def player_can_read(session, row, user_id):
    return bool(
        row
        and row.recipient_user_id == user_id
        and row.withdrawn_at is None
        and row.audit_expires_at is None
        and relationship_matches(session, row)
    )


def locked_invitation(session, invitation, actor_id):
    """Account -> claimant -> program/grants -> invitation -> thread order."""
    lock_context(
        session,
        claim_id=invitation.claim_id,
        program_id=invitation.program_id,
        account_ids=[actor_id, invitation.recipient_user_id, invitation.created_by_user_id],
    )
    from src.models.funding import ClubProgramClaim, ClubProgramManager

    grants = (
        session.query(ClubProgramManager)
        .filter_by(program_id=invitation.program_id)
        .order_by(ClubProgramManager.id)
        .populate_existing()
        .with_for_update()
        .all()
    )
    source_ids = [grant.source_claim_id for grant in grants if grant.source_claim_id is not None]
    session.query(ClubProgramClaim).filter(ClubProgramClaim.id.in_(source_ids)).order_by(
        ClubProgramClaim.id
    ).populate_existing().with_for_update().all()
    return session.query(ClubInvitation).filter_by(id=invitation.id).populate_existing().with_for_update().one_or_none()


def lock_thread(session, row, actor_id):
    invitation = session.get(ClubInvitation, row.invitation_id)
    if not invitation or not locked_invitation(session, invitation, actor_id):
        raise FeedbackError("feedback_not_found", 404)
    return (
        session.query(PlayerFeedback)
        .filter_by(thread_id=row.thread_id)
        .order_by(PlayerFeedback.revision)
        .populate_existing()
        .with_for_update()
        .all()
    )


def feedback_dict(session, row, *, manager=False, summary=False):
    from src.models.funding import ClubProgram

    program = session.get(ClubProgram, row.program_id)
    author = session.get(UserAccount, row.author_user_id) if row.author_user_id else None
    latest = session.query(sa.func.max(PlayerFeedback.revision)).filter_by(thread_id=row.thread_id).scalar()

    def stamp(value):
        return value.isoformat() + "Z" if value else None

    result = {
        "id": row.id,
        "thread_id": row.thread_id,
        "revision": row.revision,
        "program": {"id": row.program_id, "name": program.name if program else "Unavailable club"},
        "player_api_id": row.player_api_id,
        "title": row.title,
        "author": {"display_name": author.display_name if author and not author.is_tombstone else "Former club staff"},
        "published_at": stamp(row.published_at),
        "acknowledged_at": stamp(row.acknowledged_at),
        "can_acknowledge": not manager
        and row.revision == latest
        and row.acknowledged_at is None
        and row.withdrawn_at is None
        and row.audit_expires_at is None,
    }
    if not summary:
        result.update(body=row.body, observation_refs=row.observation_refs)
    if manager:
        result.update(
            invitation_id=row.invitation_id,
            claim_id=row.claim_id,
            recipient_user_id=row.recipient_user_id,
            withdrawn_at=stamp(row.withdrawn_at),
        )
    return result


def validate_reference(session, invitation, match_id):
    from src.models.video import VideoMatch, VideoPlayerReport

    if match_id is None:
        return
    match = (
        session.query(VideoMatch)
        .filter_by(id=match_id, club_program_id=invitation.program_id, status="finalized")
        .with_for_update()
        .first()
    )
    reports = session.query(VideoPlayerReport).filter_by(
        video_match_id=match_id, club_program_id_at_finalize=invitation.program_id
    )
    reports = (
        reports.filter_by(club_player_api_id_at_finalize=invitation.player_api_id)
        if invitation.player_api_id > 0
        else reports.filter_by(club_local_player_id_at_finalize=-invitation.player_api_id)
    )
    if not match or not reports.first():
        raise FeedbackError("feedback_reference_unavailable", 409)


def publish(session, invitation, author_id, data, *, rows=None):
    if not strict_manager(session, invitation.program_id, author_id):
        raise FeedbackError("Club manager access denied", 403)
    if not effective_relationship(session, invitation):
        raise FeedbackError("club_relationship_required", 409)
    latest = rows[-1] if rows else None
    identity = {**data, "thread_id": latest.thread_id if latest else None}
    digest = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    replay = (
        session.query(PlayerFeedback)
        .filter_by(program_id=invitation.program_id, client_request_id=data["client_request_id"])
        .first()
    )
    if replay and replay.request_hash != digest:
        raise FeedbackError("client_request_id_reused", 409)
    if latest and (latest.withdrawn_at or latest.audit_expires_at):
        raise FeedbackError("feedback_withdrawn", 409)
    if replay:
        if observe_closure(session, replay):
            raise FeedbackError("feedback_withdrawn", 409, closure=True)
        return replay, 200
    if latest and data["expected_revision"] != latest.revision:
        raise FeedbackError("feedback_revision_conflict", 409, current_revision=latest.revision)
    validate_reference(session, invitation, data["video_match_id"])
    row = PlayerFeedback(
        thread_id=latest.thread_id if latest else str(uuid4()),
        revision=latest.revision + 1 if latest else 1,
        program_id=invitation.program_id,
        invitation_id=invitation.id,
        claim_id=invitation.claim_id,
        recipient_user_id=invitation.recipient_user_id,
        player_api_id=invitation.player_api_id,
        author_user_id=author_id,
        request_hash=digest,
        **{key: data[key] for key in ("title", "body", "video_match_id", "observation_refs", "client_request_id")},
    )
    session.add(row)
    session.flush()
    return row, 201
