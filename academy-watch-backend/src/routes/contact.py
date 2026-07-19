"""Feature-gated scout-to-player contact requests, threads, and outcomes."""

from __future__ import annotations

import logging

from flask import Blueprint, abort, g, jsonify, request
from sqlalchemy import and_, func, or_
from sqlalchemy.exc import IntegrityError
from src.auth import _ensure_user_account, _safe_error_payload, require_user_auth
from src.extensions import limiter
from src.models.contact import ContactMessage, ContactOutcome, ContactRequest
from src.models.league import UserAccount, db
from src.models.showcase import PlayerProfileClaim
from src.models.trust import ScoutVerification
from src.services.club_registry import (
    active_manager_program_ids,
    is_active_program_manager,
)
from src.services.contact import (
    APPROACH_RULES_WARNING,
    ROUTING_CLUB_INCLUDED,
    ROUTING_CLUB_NOTIFIED,
    add_audit_event,
    clean_plain_text,
    contact_rail_enabled,
    decline_cooldown_cutoff,
    decline_cooldown_days,
    expire_if_due,
    messaging_is_open,
    parse_occurred_at,
    request_can_expire,
    request_expires_at,
    require_contact_rail,
    routing_mode_for_claim,
    send_club_courtesy_notice,
    utcnow,
)
from src.services.trust import is_verified_scout

logger = logging.getLogger(__name__)
contact_bp = Blueprint("contact", __name__)

ACTIVE_REQUEST_STATUSES = {"pending", "accepted"}
OUTCOME_STAGES = {"contacted", "trial_scheduled", "trial_completed", "signed", "no_fit"}

MAX_REQUEST_MESSAGE_LENGTH = 2000
MAX_THREAD_MESSAGE_LENGTH = 2000
MAX_OUTCOME_NOTES_LENGTH = 2000
MAX_CLUB_CONSENT_NOTE_LENGTH = 1000
MAX_PAGE_SIZE = 200

REQUEST_RATE_LIMIT = "10 per day"
MESSAGE_RATE_LIMIT = "60 per hour"


@contact_bp.before_app_request
def _hide_contact_rail_paths_when_disabled():
    """Hide even automatic OPTIONS and wrong-method probes while flag-off."""
    path = request.path.rstrip("/")
    is_contact_path = path.startswith("/api/contact/")
    if is_contact_path and not contact_rail_enabled():
        abort(404)


def _user_rate_limit_key() -> str:
    return getattr(g, "user_email", None) or request.remote_addr or "anon"


def _current_user_account() -> UserAccount | None:
    user = getattr(g, "user", None)
    if user is not None:
        return user
    email = getattr(g, "user_email", None)
    if not email:
        return None
    user = UserAccount.query.filter_by(email=email).first()
    if user is None:
        user = _ensure_user_account(email)
        db.session.commit()
    return user


def _json_object() -> dict:
    payload = request.get_json(silent=True)
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValueError("JSON body must be an object")
    return payload


def _positive_player_id(value) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("player_api_id must be a positive integer")
    return value


def _pagination() -> tuple[int, int]:
    limit = request.args.get("limit", 50, type=int)
    offset = request.args.get("offset", 0, type=int)
    limit = min(MAX_PAGE_SIZE, max(1, limit if limit is not None else 50))
    offset = max(0, offset if offset is not None else 0)
    return limit, offset


def _target_claim(player_api_id: int, *, for_update: bool = False) -> PlayerProfileClaim | None:
    # FC-B1 permits multiple approved claimants. The newest approved self-claim
    # is the deterministic introduction target and remains pinned by claim_id.
    query = PlayerProfileClaim.query.filter_by(
        player_api_id=player_api_id,
        relationship_type="player",
        status="approved",
    )
    query = query.order_by(PlayerProfileClaim.reviewed_at.desc(), PlayerProfileClaim.id.desc())
    if for_update:
        query = query.populate_existing().with_for_update()
    return query.first()


def _lock_verified_scout(user: UserAccount) -> ScoutVerification | None:
    return (
        ScoutVerification.query.filter_by(user_account_id=user.id, status="approved")
        .order_by(ScoutVerification.submitted_at.desc(), ScoutVerification.id.desc())
        .populate_existing()
        .with_for_update()
        .first()
    )


def _lock_claim_owner(contact_request: ContactRequest, user: UserAccount) -> PlayerProfileClaim | None:
    return (
        PlayerProfileClaim.query.filter_by(
            id=contact_request.claim_id,
            user_account_id=user.id,
            relationship_type="player",
            status="approved",
        )
        .populate_existing()
        .with_for_update()
        .first()
    )


def _is_claim_owner(contact_request: ContactRequest, user: UserAccount) -> bool:
    claim = contact_request.claim
    return bool(
        claim is not None
        and claim.user_account_id == user.id
        and claim.status == "approved"
        and claim.relationship_type == "player"
    )


def _is_club_manager(contact_request: ContactRequest, user: UserAccount) -> bool:
    return bool(
        contact_request.routing_mode == ROUTING_CLUB_INCLUDED
        and contact_request.club_program_id is not None
        and is_active_program_manager(user.id, contact_request.club_program_id)
    )


def _participant_role(contact_request: ContactRequest, user: UserAccount) -> str | None:
    """Resolve a stable role, with deterministic overlap precedence."""
    if contact_request.scout_user_id == user.id:
        return "scout"
    if _is_claim_owner(contact_request, user):
        return "player"
    if _is_club_manager(contact_request, user):
        return "club"
    return None


def _is_participant(contact_request: ContactRequest, user: UserAccount) -> bool:
    return _participant_role(contact_request, user) is not None


def _active_request_filter():
    return ContactRequest.status.in_(ACTIVE_REQUEST_STATUSES)


def _messaging_gate_error(contact_request: ContactRequest, *, sending: bool):
    if contact_request.routing_mode == ROUTING_CLUB_INCLUDED and contact_request.club_consent_status == "declined":
        return jsonify({"error": "club consent was declined", "code": "club_consent_declined"}), 409
    if contact_request.status != "accepted":
        error = (
            "messages can be sent only for accepted requests"
            if sending
            else "messages are available only for accepted requests"
        )
        return jsonify({"error": error}), 409
    if contact_request.routing_mode == ROUTING_CLUB_INCLUDED:
        if contact_request.club_consent_status != "granted":
            return jsonify({"error": "club consent is required before messaging", "code": "club_consent_required"}), 409
    return None


def _expire_authorized_request(contact_request: ContactRequest) -> bool:
    if not expire_if_due(contact_request):
        return False
    db.session.commit()
    return True


def _participant_request(request_id: str, user: UserAccount):
    contact_request = db.session.get(ContactRequest, request_id)
    if contact_request is None or not _is_participant(contact_request, user):
        return None, (jsonify({"error": "contact request not found"}), 404)
    if (
        request_can_expire(contact_request)
        and contact_request.expires_at is not None
        and contact_request.expires_at <= utcnow()
    ):
        contact_request = ContactRequest.query.filter_by(id=request_id).populate_existing().with_for_update().first()
        _expire_authorized_request(contact_request)
    return contact_request, None


def _expire_visible_rows(query) -> None:
    due = (
        query.filter(
            or_(
                ContactRequest.status == "pending",
                and_(
                    ContactRequest.status == "accepted",
                    ContactRequest.routing_mode == ROUTING_CLUB_INCLUDED,
                    ContactRequest.club_consent_status == "pending",
                ),
            ),
            ContactRequest.expires_at <= utcnow(),
        )
        .order_by(ContactRequest.id.asc())
        .populate_existing()
        .with_for_update()
        .all()
    )
    changed = False
    checked_at = utcnow()
    for row in due:
        changed = expire_if_due(row, now=checked_at) or changed
    if changed:
        db.session.commit()


@contact_bp.route("/contact/requests", methods=["POST"])
@require_contact_rail
@require_user_auth
@limiter.limit(REQUEST_RATE_LIMIT, key_func=_user_rate_limit_key)
def create_contact_request():
    """Create an introduction from a verified scout to an approved player claimant."""
    try:
        user = _current_user_account()
        if user is None:
            return jsonify({"error": "auth context missing email"}), 401
        if not is_verified_scout(user):
            return jsonify({"error": "Scout verification is required", "code": "scout_not_verified"}), 403

        payload = _json_object()
        player_api_id = _positive_player_id(payload.get("player_api_id"))
        message = clean_plain_text(
            payload.get("message"),
            "message",
            max_len=MAX_REQUEST_MESSAGE_LENGTH,
        )

        claim = _target_claim(player_api_id)
        if claim is None:
            return jsonify({"error": "Player is not available for contact", "code": "player_not_claimable"}), 403

        # An unread expired request must not keep the partial unique guard live.
        matching = ContactRequest.query.filter_by(scout_user_id=user.id, player_api_id=player_api_id)
        _expire_visible_rows(matching)

        # Revalidate and lock both trust prerequisites through the insert
        # commit so concurrent admin revocation cannot win after our checks.
        if _lock_verified_scout(user) is None:
            db.session.rollback()
            return jsonify({"error": "Scout verification is required", "code": "scout_not_verified"}), 403
        claim = _target_claim(player_api_id, for_update=True)
        if claim is None:
            db.session.rollback()
            return jsonify({"error": "Player is not available for contact", "code": "player_not_claimable"}), 403

        routing_mode = routing_mode_for_claim(claim)
        permission_attestation = payload.get("permission_attestation") is True
        if routing_mode == ROUTING_CLUB_NOTIFIED and not permission_attestation:
            db.session.rollback()
            return jsonify({"error": APPROACH_RULES_WARNING, "code": "attestation_required"}), 400

        active = matching.filter(_active_request_filter()).first()
        if active is not None:
            active_payload = active.to_dict()
            db.session.rollback()
            return jsonify(
                {
                    "error": "An active contact request already exists for this player",
                    "code": "active_request_exists",
                    "contact_request": active_payload,
                }
            ), 409

        cooldown_cutoff = decline_cooldown_cutoff()
        declined = (
            matching.filter(
                ContactRequest.status == "declined",
                func.coalesce(ContactRequest.responded_at, ContactRequest.created_at) >= cooldown_cutoff,
            )
            .order_by(ContactRequest.responded_at.desc(), ContactRequest.created_at.desc())
            .first()
        )
        if declined is not None:
            db.session.rollback()
            return jsonify(
                {
                    "error": "A recent request was declined; please wait before contacting this player again",
                    "code": "decline_cooldown_active",
                    "cooldown_days": decline_cooldown_days(),
                }
            ), 409

        now = utcnow()
        club_program_id = claim.club_program_id if routing_mode != "direct" else None
        contact_request = ContactRequest(
            scout_user_id=user.id,
            player_api_id=player_api_id,
            claim_id=claim.id,
            message=message,
            status="pending",
            routing_mode=routing_mode,
            club_program_id=club_program_id,
            club_consent_status="pending" if routing_mode == ROUTING_CLUB_INCLUDED else None,
            permission_attestation=permission_attestation if routing_mode == ROUTING_CLUB_NOTIFIED else False,
            permission_attested_at=now if routing_mode == ROUTING_CLUB_NOTIFIED else None,
            created_at=now,
            expires_at=request_expires_at(now=now),
        )
        db.session.add(contact_request)
        try:
            db.session.flush()
            add_audit_event(
                contact_request,
                "created",
                actor_user_id=user.id,
                metadata={
                    "player_api_id": player_api_id,
                    "claim_id": claim.id,
                    "routing_mode": routing_mode,
                    "club_program_id": club_program_id,
                },
                created_at=now,
            )
            if routing_mode == ROUTING_CLUB_NOTIFIED:
                add_audit_event(
                    contact_request,
                    "scout_permission_attested",
                    actor_user_id=user.id,
                    metadata={
                        "club_program_id": club_program_id,
                        "warning": "approach_rules_permission",
                    },
                    created_at=now,
                )
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            active = (
                ContactRequest.query.filter_by(scout_user_id=user.id, player_api_id=player_api_id)
                .filter(_active_request_filter())
                .first()
            )
            if active is not None:
                return jsonify(
                    {
                        "error": "An active contact request already exists for this player",
                        "code": "active_request_exists",
                        "contact_request": active.to_dict(),
                    }
                ), 409
            raise
        if routing_mode == ROUTING_CLUB_NOTIFIED:
            notice_metadata = send_club_courtesy_notice(contact_request)
            if notice_metadata is not None:
                try:
                    add_audit_event(
                        contact_request,
                        "club_notice_sent",
                        actor_user_id=None,
                        metadata=notice_metadata,
                    )
                    db.session.commit()
                except Exception:
                    db.session.rollback()
                    logger.exception("Failed to record club notice audit for request %s", contact_request.id)
        return jsonify({"contact_request": contact_request.to_dict()}), 201
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        logger.exception("Failed to create contact request")
        return jsonify(_safe_error_payload(exc, "Failed to create contact request")), 500


@contact_bp.route("/contact/requests", methods=["GET"])
@require_contact_rail
@require_user_auth
def list_contact_requests():
    """List the caller's sent requests or approved player-claim inbox."""
    try:
        user = _current_user_account()
        if user is None:
            return jsonify({"error": "auth context missing email"}), 401
        box = (request.args.get("box") or "sent").strip().lower()
        if box == "sent":
            query = ContactRequest.query.filter(ContactRequest.scout_user_id == user.id)
        elif box == "inbox":
            claim_ids = db.session.query(PlayerProfileClaim.id).filter_by(
                user_account_id=user.id,
                relationship_type="player",
                status="approved",
            )
            query = ContactRequest.query.filter(ContactRequest.claim_id.in_(claim_ids))
        elif box == "club":
            program_ids = active_manager_program_ids(user.id)
            query = ContactRequest.query.filter(
                ContactRequest.routing_mode == ROUTING_CLUB_INCLUDED,
                ContactRequest.club_program_id.in_(program_ids),
            )
        else:
            return jsonify({"error": "box must be sent, inbox, or club"}), 400

        _expire_visible_rows(query)
        limit, offset = _pagination()
        total = query.count()
        rows = (
            query.order_by(ContactRequest.created_at.desc(), ContactRequest.id.desc()).offset(offset).limit(limit).all()
        )
        return jsonify(
            {
                "requests": [row.to_dict() for row in rows],
                "box": box,
                "total": total,
                "limit": limit,
                "offset": offset,
            }
        )
    except Exception as exc:
        db.session.rollback()
        logger.exception("Failed to list contact requests")
        return jsonify(_safe_error_payload(exc, "Failed to list contact requests")), 500


def _respond_to_request(request_id: str, action: str):
    try:
        user = _current_user_account()
        if user is None:
            return jsonify({"error": "auth context missing email"}), 401
        contact_request = ContactRequest.query.filter_by(id=request_id).populate_existing().with_for_update().first()
        if contact_request is None:
            return jsonify({"error": "contact request not found"}), 404
        if _lock_claim_owner(contact_request, user) is None:
            db.session.rollback()
            return jsonify({"error": "Only the player claim owner can respond"}), 403
        if _expire_authorized_request(contact_request):
            return jsonify({"error": "contact request has expired", "code": "request_expired"}), 409
        if contact_request.routing_mode == ROUTING_CLUB_INCLUDED and contact_request.club_consent_status == "declined":
            db.session.rollback()
            return jsonify({"error": "club consent was declined", "code": "club_consent_declined"}), 409
        if contact_request.status != "pending":
            db.session.rollback()
            return jsonify({"error": f"cannot {action} a {contact_request.status} request"}), 409

        now = utcnow()
        contact_request.status = "accepted" if action == "accept" else "declined"
        contact_request.responded_at = now
        event_type = "accepted" if action == "accept" else "declined"
        add_audit_event(contact_request, event_type, actor_user_id=user.id, created_at=now)
        db.session.commit()
        return jsonify({"contact_request": contact_request.to_dict()})
    except Exception as exc:
        db.session.rollback()
        logger.exception("Failed to %s contact request %s", action, request_id)
        return jsonify(_safe_error_payload(exc, f"Failed to {action} contact request")), 500


@contact_bp.route("/contact/requests/<string:request_id>/accept", methods=["POST"])
@require_contact_rail
@require_user_auth
def accept_contact_request(request_id: str):
    return _respond_to_request(request_id, "accept")


@contact_bp.route("/contact/requests/<string:request_id>/decline", methods=["POST"])
@require_contact_rail
@require_user_auth
def decline_contact_request(request_id: str):
    return _respond_to_request(request_id, "decline")


@contact_bp.route("/contact/requests/<string:request_id>/club-consent", methods=["POST"])
@require_contact_rail
@require_user_auth
def set_club_consent(request_id: str):
    try:
        user = _current_user_account()
        if user is None:
            return jsonify({"error": "auth context missing email"}), 401
        contact_request = ContactRequest.query.filter_by(id=request_id).populate_existing().with_for_update().first()
        if (
            contact_request is None
            or contact_request.routing_mode != ROUTING_CLUB_INCLUDED
            or not _is_club_manager(contact_request, user)
        ):
            db.session.rollback()
            return jsonify({"error": "contact request not found"}), 404
        if _expire_authorized_request(contact_request):
            return jsonify({"error": "contact request has expired", "code": "request_expired"}), 409
        if contact_request.status not in ACTIVE_REQUEST_STATUSES:
            db.session.rollback()
            return jsonify({"error": f"club consent cannot change a {contact_request.status} request"}), 409
        if contact_request.club_consent_status != "pending":
            db.session.rollback()
            return jsonify({"error": "club consent has already been decided"}), 409

        payload = _json_object()
        action = payload.get("action")
        if not isinstance(action, str) or action.strip().lower() not in {"grant", "decline"}:
            raise ValueError("action must be grant or decline")
        action = action.strip().lower()
        note = clean_plain_text(
            payload.get("note"),
            "note",
            max_len=MAX_CLUB_CONSENT_NOTE_LENGTH,
            required=False,
        )

        now = utcnow()
        contact_request.club_consent_status = "granted" if action == "grant" else "declined"
        contact_request.club_consent_at = now
        contact_request.club_consent_by_user_id = user.id
        contact_request.club_consent_note = note
        if action == "decline":
            contact_request.status = "declined"
            contact_request.responded_at = now
        event_type = "club_consent_granted" if action == "grant" else "club_consent_declined"
        add_audit_event(
            contact_request,
            event_type,
            actor_user_id=user.id,
            metadata={"note": note} if note else {},
            created_at=now,
        )
        db.session.commit()
        return jsonify({"contact_request": contact_request.to_dict()})
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        logger.exception("Failed to set club consent for request %s", request_id)
        return jsonify(_safe_error_payload(exc, "Failed to set club consent")), 500


@contact_bp.route("/contact/requests/<string:request_id>/withdraw", methods=["POST"])
@require_contact_rail
@require_user_auth
def withdraw_contact_request(request_id: str):
    try:
        user = _current_user_account()
        if user is None:
            return jsonify({"error": "auth context missing email"}), 401
        contact_request = ContactRequest.query.filter_by(id=request_id).populate_existing().with_for_update().first()
        if contact_request is None:
            return jsonify({"error": "contact request not found"}), 404
        if contact_request.scout_user_id != user.id:
            return jsonify({"error": "Only the initiating scout can withdraw this request"}), 403
        if _expire_authorized_request(contact_request):
            return jsonify({"error": "contact request has expired", "code": "request_expired"}), 409
        if contact_request.status != "pending":
            return jsonify({"error": f"cannot withdraw a {contact_request.status} request"}), 409

        now = utcnow()
        contact_request.status = "withdrawn"
        add_audit_event(contact_request, "withdrawn", actor_user_id=user.id, created_at=now)
        db.session.commit()
        return jsonify({"contact_request": contact_request.to_dict()})
    except Exception as exc:
        db.session.rollback()
        logger.exception("Failed to withdraw contact request %s", request_id)
        return jsonify(_safe_error_payload(exc, "Failed to withdraw contact request")), 500


@contact_bp.route("/contact/requests/<string:request_id>/messages", methods=["GET"])
@require_contact_rail
@require_user_auth
def list_contact_messages(request_id: str):
    try:
        user = _current_user_account()
        if user is None:
            return jsonify({"error": "auth context missing email"}), 401
        contact_request, error = _participant_request(request_id, user)
        if error:
            return error
        if not messaging_is_open(contact_request):
            return _messaging_gate_error(contact_request, sending=False)

        limit, offset = _pagination()
        query = ContactMessage.query.filter_by(contact_request_id=contact_request.id)
        total = query.count()
        rows = (
            query.order_by(ContactMessage.created_at.asc(), ContactMessage.id.asc()).offset(offset).limit(limit).all()
        )
        return jsonify(
            {
                "messages": [row.to_dict() for row in rows],
                "contact_request": contact_request.to_dict(),
                "total": total,
                "limit": limit,
                "offset": offset,
            }
        )
    except Exception as exc:
        db.session.rollback()
        logger.exception("Failed to list messages for contact request %s", request_id)
        return jsonify(_safe_error_payload(exc, "Failed to list contact messages")), 500


@contact_bp.route("/contact/requests/<string:request_id>/messages", methods=["POST"])
@require_contact_rail
@require_user_auth
@limiter.limit(MESSAGE_RATE_LIMIT, key_func=_user_rate_limit_key)
def create_contact_message(request_id: str):
    try:
        user = _current_user_account()
        if user is None:
            return jsonify({"error": "auth context missing email"}), 401
        contact_request, error = _participant_request(request_id, user)
        if error:
            return error
        if not messaging_is_open(contact_request):
            return _messaging_gate_error(contact_request, sending=True)
        sender_role = _participant_role(contact_request, user)
        if sender_role == "player" and _lock_claim_owner(contact_request, user) is None:
            db.session.rollback()
            return jsonify({"error": "contact request not found"}), 404
        if sender_role == "club" and not _is_club_manager(contact_request, user):
            db.session.rollback()
            return jsonify({"error": "contact request not found"}), 404
        if sender_role is None:
            db.session.rollback()
            return jsonify({"error": "contact request not found"}), 404

        payload = _json_object()
        body = clean_plain_text(payload.get("body"), "body", max_len=MAX_THREAD_MESSAGE_LENGTH)
        now = utcnow()
        message = ContactMessage(
            contact_request_id=contact_request.id,
            sender_user_id=user.id,
            sender_role=sender_role,
            body=body,
            created_at=now,
        )
        db.session.add(message)
        db.session.flush()
        add_audit_event(
            contact_request,
            "message_sent",
            actor_user_id=user.id,
            metadata={"message_id": message.id},
            created_at=now,
        )
        db.session.commit()
        return jsonify({"message": message.to_dict()}), 201
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        logger.exception("Failed to send message for contact request %s", request_id)
        return jsonify(_safe_error_payload(exc, "Failed to send contact message")), 500


@contact_bp.route("/contact/requests/<string:request_id>/outcome", methods=["POST"])
@require_contact_rail
@require_user_auth
def report_contact_outcome(request_id: str):
    try:
        user = _current_user_account()
        if user is None:
            return jsonify({"error": "auth context missing email"}), 401
        contact_request, error = _participant_request(request_id, user)
        if error:
            return error
        if contact_request.scout_user_id != user.id and _lock_claim_owner(contact_request, user) is None:
            db.session.rollback()
            return jsonify({"error": "contact request not found"}), 404

        payload = _json_object()
        stage = clean_plain_text(payload.get("stage"), "stage", max_len=30).lower()
        if stage not in OUTCOME_STAGES:
            raise ValueError(f"stage must be one of {sorted(OUTCOME_STAGES)}")
        notes = clean_plain_text(
            payload.get("notes"),
            "notes",
            max_len=MAX_OUTCOME_NOTES_LENGTH,
            required=False,
        )
        occurred_at = parse_occurred_at(payload.get("occurred_at"))
        now = utcnow()
        outcome = ContactOutcome(
            contact_request_id=contact_request.id,
            stage=stage,
            reported_by_user_id=user.id,
            notes=notes,
            occurred_at=occurred_at,
            created_at=now,
        )
        db.session.add(outcome)
        db.session.flush()
        add_audit_event(
            contact_request,
            "outcome_reported",
            actor_user_id=user.id,
            metadata={"outcome_id": outcome.id, "stage": stage},
            created_at=now,
        )
        db.session.commit()
        return jsonify({"outcome": outcome.to_dict(), "contact_request": contact_request.to_dict()}), 201
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        logger.exception("Failed to report outcome for contact request %s", request_id)
        return jsonify(_safe_error_payload(exc, "Failed to report contact outcome")), 500


__all__ = ["contact_bp"]
