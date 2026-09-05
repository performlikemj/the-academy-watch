"""Participant-only private feedback; no media or analysis projection."""

import logging
import math
import time
from functools import wraps

import sqlalchemy as sa
from flask import Blueprint, g, jsonify, request
from sqlalchemy.exc import IntegrityError
from src.auth import require_api_key, require_user_auth
from src.extensions import limiter
from src.models.club_invitation import (
    ClubInvitation,
    effective_relationship,
    relationships_enabled,
    strict_manager,
    utcnow,
)
from src.models.league import db
from src.models.player_feedback import (
    FeedbackError,
    PlayerFeedback,
    authored_payload,
    feedback_dict,
    integer,
    lock_thread,
    locked_invitation,
    observe_closure,
    player_can_read,
    publish,
    relationship_matches,
    uuid,
)
from src.services.club_registry import require_club_manager
from src.services.public_player_subject import resolve_public_adult_subject, user_owns_subject
from werkzeug.exceptions import HTTPException

feedback_bp = Blueprint("feedback", __name__)
logger = logging.getLogger(__name__)


@feedback_bp.after_request
def private_response(response):
    response.headers["Cache-Control"] = "private, no-store"
    return response


def rate_rejected(limit):
    response = jsonify(error="rate_limit_exceeded")
    response.status_code = 429
    response.headers["Retry-After"] = str(max(1, math.ceil(limit.reset_at - time.time())))
    return private_response(response)


def limited(value):
    return limiter.limit(value, key_func=lambda: str(getattr(g, "user_id", "admin")), on_breach=rate_rejected)


def transaction(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        try:
            try:
                result = view(*args, **kwargs)
            except FeedbackError as error:
                payload = {"error": error.code}
                if error.current_revision is not None:
                    payload["current_revision"] = error.current_revision
                result = jsonify(payload), error.status
                if not error.closure:
                    db.session.rollback()
                    return result
            db.session.commit()
            return result
        except HTTPException:
            db.session.rollback()
            raise
        except Exception as error:
            db.session.rollback()
            code = getattr(getattr(error, "orig", None), "sqlstate", None)
            if isinstance(error, IntegrityError) or code in {"40001", "40P01"}:
                return jsonify(error="retry_conflict"), 409
            logger.error("Feedback operation failed (%s)", type(error).__name__)
            return jsonify(error="feedback_operation_failed"), 500

    return wrapped


def authority(*, manager=False):
    def decorate(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not relationships_enabled():
                raise FeedbackError("feedback_not_found", 404)
            program_id = kwargs.get("program_id")
            if manager and not strict_manager(db.session, program_id, g.user_id):
                raise FeedbackError("Club manager access denied", 403)
            row_id = kwargs.get("revision_id")
            thread_id = kwargs.get("thread_id")
            if row_id or thread_id:
                query = (
                    PlayerFeedback.query.filter_by(id=uuid(row_id))
                    if row_id
                    else PlayerFeedback.query.filter_by(thread_id=uuid(thread_id))
                )
                query = (
                    query.filter_by(program_id=program_id) if manager else query.filter_by(recipient_user_id=g.user_id)
                )
                row = query.order_by(PlayerFeedback.revision).first()
                if not row:
                    raise FeedbackError("feedback_not_found", 404)
                g.feedback_rows = lock_thread(db.session, row, g.user_id)
                g.feedback = next(item for item in g.feedback_rows if item.id == row.id)
                if manager:
                    if not strict_manager(db.session, program_id, g.user_id):
                        raise FeedbackError("Club manager access denied", 403)
                    # Withdrawal remains possible after relationship closure.
                    if not request.path.endswith("/withdraw") and observe_closure(db.session, g.feedback):
                        raise FeedbackError("feedback_withdrawn", 409, closure=True)
                else:
                    observe_closure(db.session, g.feedback)
                    if not player_can_read(db.session, g.feedback, g.user_id):
                        raise FeedbackError("feedback_not_found", 404, closure=True)
            elif manager and request.method == "POST":
                g.feedback_data = authored_payload(request.get_json(silent=True))
                invitation = ClubInvitation.query.filter_by(
                    id=g.feedback_data["invitation_id"], program_id=program_id
                ).first()
                if not invitation:
                    raise FeedbackError("feedback_not_found", 404)
                g.feedback_invitation = locked_invitation(db.session, invitation, g.user_id)
                if not g.feedback_invitation:
                    raise FeedbackError("club_relationship_required", 409)
                if not strict_manager(db.session, program_id, g.user_id):
                    raise FeedbackError("Club manager access denied", 403)
                if not effective_relationship(db.session, g.feedback_invitation):
                    for row in PlayerFeedback.query.filter_by(invitation_id=g.feedback_invitation.id).all():
                        observe_closure(db.session, row)
                    raise FeedbackError("club_relationship_required", 409, closure=True)
            else:
                allowed = {"limit", "before", "invitation_id" if manager else "player_api_id"}
                if set(request.args) - allowed or any(len(request.args.getlist(k)) != 1 for k in request.args):
                    raise FeedbackError()
                try:
                    g.feedback_limit = int(request.args.get("limit", "20"))
                    if not 1 <= g.feedback_limit <= 100:
                        raise ValueError()
                    if manager:
                        g.feedback_invitation_id = uuid(request.args.get("invitation_id"))
                        if not ClubInvitation.query.filter_by(
                            id=g.feedback_invitation_id, program_id=program_id
                        ).first():
                            raise FeedbackError("feedback_not_found", 404)
                    else:
                        g.feedback_subject = integer(int(request.args.get("player_api_id", "")), signed=True)
                except ValueError:
                    raise FeedbackError() from None
                if not manager and (
                    not resolve_public_adult_subject(g.feedback_subject)
                    or not user_owns_subject(g.user_id, g.feedback_subject)
                ):
                    # Observe previously delivered records without returning them.
                    for row in PlayerFeedback.query.filter_by(
                        recipient_user_id=g.user_id, player_api_id=g.feedback_subject
                    ).all():
                        observe_closure(db.session, row)
                    raise FeedbackError("feedback_not_found", 404, closure=True)
            return view(*args, **kwargs)

        return wrapped

    return decorate


@feedback_bp.post("/club/<int:program_id>/player-feedback")
@require_club_manager()
@transaction
@authority(manager=True)
@limited("30 per hour")
def create_feedback(program_id):
    row, status = publish(db.session, g.feedback_invitation, g.user_id, g.feedback_data)
    return jsonify(feedback=feedback_dict(db.session, row, manager=True)), status


@feedback_bp.post("/club/<int:program_id>/player-feedback/<thread_id>/revisions")
@require_club_manager()
@transaction
@authority(manager=True)
@limited("30 per hour")
def revise_feedback(program_id, thread_id):
    data = authored_payload(request.get_json(silent=True), correction=True)
    invitation = db.session.get(ClubInvitation, g.feedback.invitation_id)
    row, status = publish(db.session, invitation, g.user_id, data, rows=g.feedback_rows)
    return jsonify(feedback=feedback_dict(db.session, row, manager=True)), status


@feedback_bp.post("/club/<int:program_id>/player-feedback/<thread_id>/withdraw")
@require_club_manager()
@transaction
@authority(manager=True)
@limited("30 per hour")
def withdraw_feedback(program_id, thread_id):
    from datetime import timedelta

    data = request.get_json(silent=True)
    if not isinstance(data, dict) or set(data) != {"expected_revision"}:
        raise FeedbackError()
    expected = integer(data["expected_revision"])
    latest = g.feedback_rows[-1]
    if latest.revision != expected:
        raise FeedbackError("feedback_revision_conflict", 409, current_revision=latest.revision)
    now = utcnow()
    for row in g.feedback_rows:
        row.withdrawn_at = row.withdrawn_at or now
        row.audit_expires_at = row.audit_expires_at or now + timedelta(days=30)
    return jsonify(
        feedback={
            "thread_id": latest.thread_id,
            "revision": latest.revision,
            "withdrawn_at": latest.withdrawn_at.isoformat() + "Z",
        }
    )


def list_feedback(*, manager=False):
    query = (
        PlayerFeedback.query.filter_by(
            program_id=request.view_args["program_id"], invitation_id=g.feedback_invitation_id
        )
        if manager
        else PlayerFeedback.query.filter_by(recipient_user_id=g.user_id, player_api_id=g.feedback_subject)
    )
    newer = sa.orm.aliased(PlayerFeedback)
    query = query.filter(
        ~sa.exists().where(newer.thread_id == PlayerFeedback.thread_id, newer.revision > PlayerFeedback.revision)
    )
    before = request.args.get("before")
    if before:
        cursor = query.filter(PlayerFeedback.id == uuid(before)).first()
        if not cursor:
            raise FeedbackError("feedback_not_found", 404)
        query = query.filter(
            sa.or_(
                PlayerFeedback.published_at < cursor.published_at,
                sa.and_(PlayerFeedback.published_at == cursor.published_at, PlayerFeedback.id < cursor.id),
            )
        )
    # Bound scanning even when the entire page has lost eligibility.
    candidates = (
        query.order_by(PlayerFeedback.published_at.desc(), PlayerFeedback.id.desc()).limit(g.feedback_limit + 1).all()
    )
    result = []
    for candidate in candidates[: g.feedback_limit]:
        rows = lock_thread(db.session, candidate, g.user_id)
        if manager and not strict_manager(db.session, candidate.program_id, g.user_id):
            raise FeedbackError("Club manager access denied", 403)
        row = next(item for item in rows if item.id == candidate.id)
        if row.revision != rows[-1].revision:
            continue
        closed = observe_closure(db.session, row)
        if closed:
            if manager:
                result.append(
                    {
                        "id": row.id,
                        "thread_id": row.thread_id,
                        "revision": row.revision,
                        "withdrawn_at": row.withdrawn_at.isoformat() + "Z" if row.withdrawn_at else None,
                        "unavailable": True,
                    }
                )
            continue
        item = feedback_dict(db.session, row, manager=manager, summary=True)
        if manager:
            item["revision_history"] = [
                {
                    "id": r.id,
                    "revision": r.revision,
                    "published_at": r.published_at.isoformat() + "Z",
                    "acknowledged_at": r.acknowledged_at.isoformat() + "Z" if r.acknowledged_at else None,
                }
                for r in rows
            ]
        result.append(item)
    return jsonify(
        feedback=result, next_before=candidates[g.feedback_limit - 1].id if len(candidates) > g.feedback_limit else None
    )


@feedback_bp.get("/club/<int:program_id>/player-feedback")
@require_club_manager()
@transaction
@authority(manager=True)
@limited("60 per minute")
def manager_feedback(program_id):
    return list_feedback(manager=True)


@feedback_bp.get("/me/player-feedback")
@require_user_auth
@transaction
@authority()
@limited("60 per minute")
def player_feedback():
    return list_feedback()


@feedback_bp.get("/me/player-feedback/<revision_id>")
@require_user_auth
@transaction
@authority()
@limited("60 per minute")
def feedback_detail(revision_id):
    return jsonify(feedback=feedback_dict(db.session, g.feedback))


@feedback_bp.post("/me/player-feedback/<revision_id>/acknowledge")
@require_user_auth
@transaction
@authority()
@limited("30 per hour")
def acknowledge_feedback(revision_id):
    if request.get_json(silent=True) != {}:
        raise FeedbackError()
    row = g.feedback
    if row.acknowledged_at is None:
        if row.revision != g.feedback_rows[-1].revision:
            raise FeedbackError("feedback_revision_conflict", 409, current_revision=g.feedback_rows[-1].revision)
        PlayerFeedback.query.filter_by(id=row.id, acknowledged_at=None).update(
            {PlayerFeedback.acknowledged_at: utcnow()}, synchronize_session="fetch"
        )
    return jsonify(feedback=feedback_dict(db.session, row))


@feedback_bp.post("/admin/player-feedback/purge")
@require_api_key
@transaction
@limited("1 per hour")
def purge_feedback():
    from datetime import timedelta

    data = request.get_json(silent=True)
    if (
        not isinstance(data, dict)
        or "dry_run" not in data
        or set(data) - {"dry_run", "before"}
        or not isinstance(data["dry_run"], bool)
    ):
        raise FeedbackError()
    query = PlayerFeedback.query
    if data.get("before") is not None:
        query = query.filter(PlayerFeedback.id > uuid(data["before"]))
    candidates = query.order_by(PlayerFeedback.id).limit(501).all()
    counts = {"scanned": 0, "closed": 0, "expired": 0, "deleted": 0}
    now = utcnow()
    for candidate in candidates[:500]:
        invitation = db.session.get(ClubInvitation, candidate.invitation_id)
        if invitation is None:
            continue
        locked_invitation(db.session, invitation, getattr(g, "user_id", None))
        # Lock only this batch's revision; do not materialize an unbounded thread.
        row = PlayerFeedback.query.filter_by(id=candidate.id).populate_existing().with_for_update().first()
        if row is None:
            continue
        counts["scanned"] += 1
        closed = bool(row.withdrawn_at or row.audit_expires_at or not relationship_matches(db.session, row))
        if not closed:
            continue
        if row.audit_expires_at is None:
            counts["closed"] += 1
        if not data["dry_run"]:
            observe_closure(db.session, row, now=now)
        deadline = row.audit_expires_at or (row.withdrawn_at or now) + timedelta(days=30)
        if deadline <= now:
            counts["expired"] += 1
            if not data["dry_run"]:
                db.session.delete(row)
                counts["deleted"] += 1
    return jsonify(**counts, next_before=candidates[499].id if len(candidates) > 500 else None, dry_run=data["dry_run"])
