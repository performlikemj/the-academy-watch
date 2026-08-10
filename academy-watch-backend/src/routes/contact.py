"""Feature-gated scout-to-player contact requests, threads, and outcomes."""

from __future__ import annotations

import logging

from flask import Blueprint, abort, g, jsonify, request
from sqlalchemy import and_, func, or_
from sqlalchemy.exc import IntegrityError
from src.auth import _ensure_user_account, _safe_error_payload, require_api_key, require_user_auth
from src.extensions import limiter
from src.models.contact import ContactAuditEvent, ContactMessage, ContactOutcome, ContactRequest
from src.models.journey import PlayerJourney
from src.models.league import Player, UserAccount, db
from src.models.showcase import PlayerProfileClaim
from src.models.trust import ScoutVerification
from src.services.club_registry import (
    active_manager_program_ids,
    active_program_manager_user_ids,
    is_active_program_manager,
    program_is_operational,
)
from src.services.contact import (
    APPROACH_RULES_WARNING,
    ROUTING_CLUB_INCLUDED,
    ROUTING_CLUB_NOTIFIED,
    ROUTING_DIRECT,
    add_audit_event,
    clean_plain_text,
    contact_rail_enabled,
    decline_cooldown_cutoff,
    decline_cooldown_days,
    expire_if_due,
    has_status_contradiction,
    load_club_consent_token,
    messaging_is_open,
    parse_occurred_at,
    platform_contract_belief,
    request_can_expire,
    request_expires_at,
    require_contact_rail,
    resolve_club_courtesy_target,
    routing_mode_for_claim,
    send_club_consent_notice,
    send_club_courtesy_notice,
    utcnow,
)
from src.services.player_suppression import is_player_suppressed, without_active_suppression
from src.services.trust import is_verified_scout
from src.services.user_blocks import (
    block_related_user_ids,
    user_has_block_relationship_with_any,
    users_have_block_relationship,
)

logger = logging.getLogger(__name__)
contact_bp = Blueprint("contact", __name__)

ACTIVE_REQUEST_STATUSES = {"pending", "accepted"}
OUTCOME_STAGES = {"contacted", "trial_scheduled", "trial_completed", "signed", "no_fit"}

MAX_REQUEST_MESSAGE_LENGTH = 2000
MAX_THREAD_MESSAGE_LENGTH = 2000
MAX_OUTCOME_NOTES_LENGTH = 2000
MAX_CLUB_CONSENT_NOTE_LENGTH = 1000
MAX_PAGE_SIZE = 200
MAX_ADMIN_PAGE_SIZE = 100

CONTACT_REQUEST_STATUSES = {"pending", "accepted", "declined", "withdrawn", "expired"}
CONTACT_ROUTING_MODES = {ROUTING_DIRECT, ROUTING_CLUB_INCLUDED, ROUTING_CLUB_NOTIFIED}

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


def _player_not_claimable():
    """Return the shared neutral response for unavailable contact targets."""
    return jsonify({"error": "Player is not available for contact", "code": "player_not_claimable"}), 403


def _contact_request_payload(contact_request: ContactRequest) -> dict:
    """Serialize blockable participants only for authenticated contact APIs."""
    return contact_request.to_dict(include_user_ids=True)


def _contact_message_payload(message: ContactMessage) -> dict:
    """Expose a thread sender's block target without changing account exports."""
    return message.to_dict(include_user_ids=True)


def _invalid_consent_link():
    return jsonify({"error": "Consent link is invalid or no longer available", "code": "invalid_consent_link"}), 404


def _pagination() -> tuple[int, int]:
    limit = request.args.get("limit", 50, type=int)
    offset = request.args.get("offset", 0, type=int)
    limit = min(MAX_PAGE_SIZE, max(1, limit if limit is not None else 50))
    offset = max(0, offset if offset is not None else 0)
    return limit, offset


def _admin_pagination() -> tuple[int, int]:
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 25, type=int)
    page = max(1, page if page is not None else 1)
    per_page = min(MAX_ADMIN_PAGE_SIZE, max(1, per_page if per_page is not None else 25))
    return page, per_page


def _contact_admin_query():
    """Build the oversight query with constant-query activity aggregates."""
    message_stats = (
        db.session.query(
            ContactMessage.contact_request_id.label("request_id"),
            func.count(ContactMessage.id).label("message_count"),
            func.max(ContactMessage.created_at).label("last_message_at"),
        )
        .group_by(ContactMessage.contact_request_id)
        .subquery()
    )
    audit_stats = (
        db.session.query(
            ContactAuditEvent.contact_request_id.label("request_id"),
            func.max(ContactAuditEvent.created_at).label("last_audit_at"),
        )
        .group_by(ContactAuditEvent.contact_request_id)
        .subquery()
    )
    return (
        db.session.query(
            ContactRequest,
            func.coalesce(message_stats.c.message_count, 0).label("message_count"),
            message_stats.c.last_message_at,
            audit_stats.c.last_audit_at,
            Player.name.label("stored_player_name"),
            PlayerJourney.player_name.label("journey_player_name"),
        )
        .outerjoin(message_stats, message_stats.c.request_id == ContactRequest.id)
        .outerjoin(audit_stats, audit_stats.c.request_id == ContactRequest.id)
        .outerjoin(Player, Player.player_id == ContactRequest.player_api_id)
        .outerjoin(PlayerJourney, PlayerJourney.player_api_id == ContactRequest.player_api_id)
    )


def _created_metadata_by_request(request_ids: list[str]) -> dict[str, dict]:
    if not request_ids:
        return {}
    rows = (
        ContactAuditEvent.query.filter(
            ContactAuditEvent.contact_request_id.in_(request_ids),
            ContactAuditEvent.event_type == "created",
        )
        .order_by(ContactAuditEvent.id.asc())
        .all()
    )
    metadata_by_request: dict[str, dict] = {}
    for event in rows:
        metadata_by_request.setdefault(event.contact_request_id, event.event_metadata)
    return metadata_by_request


def _verification_by_scout(scout_user_ids: list[int]) -> dict[int, ScoutVerification]:
    if not scout_user_ids:
        return {}
    rows = (
        ScoutVerification.query.filter(ScoutVerification.user_account_id.in_(scout_user_ids))
        .order_by(
            ScoutVerification.user_account_id.asc(),
            ScoutVerification.submitted_at.desc(),
            ScoutVerification.id.desc(),
        )
        .all()
    )
    verification_by_scout: dict[int, ScoutVerification] = {}
    for verification in rows:
        verification_by_scout.setdefault(verification.user_account_id, verification)
    return verification_by_scout


def _admin_contact_request_payload(row, verification, created_metadata: dict | None) -> dict:
    contact_request = row.ContactRequest
    activity_candidates = [
        value for value in (contact_request.created_at, row.last_message_at, row.last_audit_at) if value is not None
    ]
    return {
        "id": contact_request.id,
        "created_at": contact_request.created_at.isoformat() if contact_request.created_at else None,
        "last_activity": max(activity_candidates).isoformat() if activity_candidates else None,
        "status": contact_request.status,
        "routing_mode": contact_request.routing_mode,
        "club_consent_status": contact_request.club_consent_status,
        "scout": {
            "account_id": contact_request.scout_user_id,
            "name": verification.full_name if verification else None,
            "organization": verification.organization if verification else None,
        },
        "player_api_id": contact_request.player_api_id,
        "player_name": row.stored_player_name or row.journey_player_name or f"Player {contact_request.player_api_id}",
        "message_count": int(row.message_count or 0),
        "status_contradiction": contact_request.status_contradiction_at_creation(created_metadata=created_metadata),
    }


def _target_claim(player_api_id: int, *, for_update: bool = False) -> PlayerProfileClaim | None:
    # FC-B1 permits multiple approved claimants. The newest approved self-claim
    # is the deterministic introduction target and remains pinned by claim_id.
    query = PlayerProfileClaim.query.filter_by(
        player_api_id=player_api_id,
        relationship_type="player",
        status="approved",
    ).filter(without_active_suppression(PlayerProfileClaim.player_api_id))
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


def _is_club_manager(
    contact_request: ContactRequest,
    user: UserAccount,
    *,
    for_update: bool = False,
) -> bool:
    return bool(
        contact_request.routing_mode == ROUTING_CLUB_INCLUDED
        and contact_request.club_program_id is not None
        and is_active_program_manager(user.id, contact_request.club_program_id)
        and program_is_operational(contact_request.club_program_id, for_update=for_update)
    )


def _participant_role(
    contact_request: ContactRequest,
    user: UserAccount,
    *,
    club_for_update: bool = False,
) -> str | None:
    """Resolve a stable role, with deterministic overlap precedence."""
    if contact_request.scout_user_id == user.id:
        return "scout"
    if _is_claim_owner(contact_request, user):
        return "player"
    if _is_club_manager(contact_request, user, for_update=club_for_update):
        return "club"
    return None


def _is_participant(
    contact_request: ContactRequest,
    user: UserAccount,
    *,
    club_for_update: bool = False,
) -> bool:
    return _participant_role(contact_request, user, club_for_update=club_for_update) is not None


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


def _participant_request(request_id: str, user: UserAccount, *, club_for_update: bool = False):
    contact_request = db.session.get(ContactRequest, request_id)
    if contact_request is None or not _is_participant(
        contact_request,
        user,
        club_for_update=club_for_update,
    ):
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

        if is_player_suppressed(player_api_id):
            return _player_not_claimable()

        claim = _target_claim(player_api_id)
        if claim is None:
            return _player_not_claimable()
        if users_have_block_relationship(
            first_user_id=claim.user_account_id,
            second_user_id=user.id,
        ):
            return _player_not_claimable()

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
            return _player_not_claimable()
        if users_have_block_relationship(
            first_user_id=claim.user_account_id,
            second_user_id=user.id,
        ):
            db.session.rollback()
            return _player_not_claimable()

        platform_belief, platform_pathway_status = platform_contract_belief(player_api_id)
        routing_mode = routing_mode_for_claim(claim, platform_belief=platform_belief)
        status_contradiction = has_status_contradiction(
            player_api_id,
            claim.contract_status,
            platform_belief=platform_belief,
        )
        permission_attestation = payload.get("permission_attestation") is True
        if routing_mode == ROUTING_CLUB_NOTIFIED and not permission_attestation:
            db.session.rollback()
            return jsonify({"error": APPROACH_RULES_WARNING, "code": "attestation_required"}), 400

        active = matching.filter(_active_request_filter()).first()
        if active is not None:
            active_payload = _contact_request_payload(active)
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
        # Serialize emergency hide/suspend updates against both persistence and
        # consent dispatch so inclusion cannot escape through a stale decision.
        if routing_mode == ROUTING_CLUB_INCLUDED and not program_is_operational(
            claim.club_program_id,
            for_update=True,
        ):
            routing_mode = ROUTING_CLUB_NOTIFIED
            if not permission_attestation:
                db.session.rollback()
                return jsonify({"error": APPROACH_RULES_WARNING, "code": "attestation_required"}), 400
        club_program_id = claim.club_program_id if routing_mode != "direct" else None
        courtesy_target = None
        if routing_mode == ROUTING_CLUB_NOTIFIED and club_program_id is not None:
            courtesy_target = resolve_club_courtesy_target(
                program_id=club_program_id,
                club_name=claim.current_club_name,
                player_api_id=player_api_id,
                for_update=True,
            )
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
                    "status_contradiction": status_contradiction,
                    "platform_contract_belief": platform_belief,
                    "platform_pathway_status": platform_pathway_status,
                },
                created_at=now,
            )
            if status_contradiction:
                logger.warning(
                    "contact_status_contradiction",
                    extra={
                        "contact_request_id": contact_request.id,
                        "player_api_id": player_api_id,
                        "claim_id": claim.id,
                        "claim_contract_status": claim.contract_status,
                        "platform_contract_belief": platform_belief,
                        "platform_pathway_status": platform_pathway_status,
                        "routing_mode": routing_mode,
                    },
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
                        "contact_request": _contact_request_payload(active),
                    }
                ), 409
            raise
        notice_metadata = None
        if routing_mode == ROUTING_CLUB_NOTIFIED and (club_program_id is None or courtesy_target is not None):
            try:
                notice_metadata = send_club_courtesy_notice(contact_request, target=courtesy_target)
            except Exception:
                db.session.rollback()
                notice_metadata = None
                logger.exception("Club notice dispatch failed for request %s", contact_request.id)
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
        elif routing_mode == ROUTING_CLUB_INCLUDED:
            try:
                send_club_consent_notice(contact_request)
            except Exception:
                db.session.rollback()
                logger.exception("Club consent dispatch failed for request %s", contact_request.id)
        if routing_mode in {ROUTING_DIRECT, ROUTING_CLUB_NOTIFIED}:
            try:
                from src.services.admin_notify_service import notify_contact_request

                notify_contact_request(
                    contact_request.id,
                    contact_request.player_api_id,
                    routing_mode=routing_mode,
                    status_contradiction=status_contradiction,
                    club_program_id=(
                        notice_metadata["club_program_id"]
                        if notice_metadata is not None
                        else contact_request.club_program_id
                    ),
                    club_notice_sent=notice_metadata is not None if routing_mode == ROUTING_CLUB_NOTIFIED else None,
                )
            except Exception:
                logger.exception("Failed to queue admin notice for contact request %s", contact_request.id)
        return jsonify({"contact_request": _contact_request_payload(contact_request)}), 201
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        logger.exception("Failed to create contact request")
        return jsonify(_safe_error_payload(exc, "Failed to create contact request")), 500


@contact_bp.route("/admin/contact/requests", methods=["GET"])
@require_api_key
def admin_list_contact_requests():
    """List contact requests for Trust Desk oversight, even while the rail is dark."""
    try:
        query = _contact_admin_query()

        status = request.args.get("status")
        if status is not None:
            status = status.strip().lower()
            if status not in CONTACT_REQUEST_STATUSES:
                return jsonify({"error": f"status must be one of {sorted(CONTACT_REQUEST_STATUSES)}"}), 400
            query = query.filter(ContactRequest.status == status)

        routing_mode = request.args.get("routing_mode")
        if routing_mode is not None:
            routing_mode = routing_mode.strip().lower()
            if routing_mode not in CONTACT_ROUTING_MODES:
                return jsonify({"error": f"routing_mode must be one of {sorted(CONTACT_ROUTING_MODES)}"}), 400
            query = query.filter(ContactRequest.routing_mode == routing_mode)

        contradiction = request.args.get("contradiction")
        if contradiction is not None:
            contradiction = contradiction.strip().lower()
            if contradiction not in {"true", "false"}:
                return jsonify({"error": "contradiction must be true or false"}), 400
            contradiction_exists = (
                db.session.query(ContactAuditEvent.id)
                .filter(
                    ContactAuditEvent.contact_request_id == ContactRequest.id,
                    ContactAuditEvent.event_type == "created",
                    ContactAuditEvent.event_metadata["status_contradiction"].as_boolean().is_(True),
                )
                .exists()
            )
            query = query.filter(contradiction_exists if contradiction == "true" else ~contradiction_exists)

        page, per_page = _admin_pagination()
        total = query.count()
        rows = (
            query.order_by(ContactRequest.created_at.desc(), ContactRequest.id.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )
        request_ids = [row.ContactRequest.id for row in rows]
        metadata_by_request = _created_metadata_by_request(request_ids)
        verification_by_scout = _verification_by_scout([row.ContactRequest.scout_user_id for row in rows])
        requests_payload = [
            _admin_contact_request_payload(
                row,
                verification_by_scout.get(row.ContactRequest.scout_user_id),
                metadata_by_request.get(row.ContactRequest.id),
            )
            for row in rows
        ]
        return jsonify(
            {
                "requests": requests_payload,
                "total": total,
                "page": page,
                "pages": (total + per_page - 1) // per_page,
            }
        )
    except Exception as exc:
        db.session.rollback()
        logger.exception("Failed to list contact requests for admin oversight")
        return jsonify(_safe_error_payload(exc, "Failed to list admin contact requests")), 500


@contact_bp.route("/admin/contact/requests/<string:request_id>", methods=["GET"])
@require_api_key
def admin_get_contact_request(request_id: str):
    """Return one contact request with participant data and its full audit trail."""
    try:
        row = _contact_admin_query().filter(ContactRequest.id == request_id).one_or_none()
        if row is None:
            return jsonify({"error": "contact request not found"}), 404

        contact_request = row.ContactRequest
        created_metadata = _created_metadata_by_request([contact_request.id]).get(contact_request.id)
        verification = _verification_by_scout([contact_request.scout_user_id]).get(contact_request.scout_user_id)
        payload = _contact_request_payload(contact_request)
        payload.update(_admin_contact_request_payload(row, verification, created_metadata))
        payload["audit_events"] = [
            {
                "event_type": event.event_type,
                "created_at": event.created_at.isoformat() if event.created_at else None,
                "metadata": event.event_metadata,
            }
            for event in contact_request.audit_events.order_by(None)
            .order_by(ContactAuditEvent.created_at.asc(), ContactAuditEvent.id.asc())
            .all()
        ]
        return jsonify({"request": payload})
    except Exception as exc:
        db.session.rollback()
        logger.exception("Failed to load contact request %s for admin oversight", request_id)
        return jsonify(_safe_error_payload(exc, "Failed to load admin contact request")), 500


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
        related_user_ids = block_related_user_ids(user_id=user.id)
        related_claim_ids = None
        if related_user_ids:
            related_claim_ids = db.session.query(PlayerProfileClaim.id).filter(
                PlayerProfileClaim.user_account_id.in_(related_user_ids)
            )
        if box == "sent":
            query = ContactRequest.query.filter(ContactRequest.scout_user_id == user.id)
            if related_claim_ids is not None:
                query = query.filter(
                    or_(
                        ContactRequest.claim_id.is_(None),
                        ContactRequest.claim_id.notin_(related_claim_ids),
                    )
                )
        elif box == "inbox":
            claim_ids = db.session.query(PlayerProfileClaim.id).filter_by(
                user_account_id=user.id,
                relationship_type="player",
                status="approved",
            )
            query = ContactRequest.query.filter(ContactRequest.claim_id.in_(claim_ids))
            if related_user_ids:
                query = query.filter(ContactRequest.scout_user_id.notin_(related_user_ids))
        elif box == "club":
            program_ids = [
                program_id
                for program_id in sorted(active_manager_program_ids(user.id))
                if program_is_operational(program_id, for_update=True)
            ]
            query = ContactRequest.query.filter(
                ContactRequest.routing_mode == ROUTING_CLUB_INCLUDED,
                ContactRequest.club_program_id.in_(program_ids),
            )
            if related_user_ids:
                query = query.filter(ContactRequest.scout_user_id.notin_(related_user_ids))
            if related_claim_ids is not None:
                query = query.filter(
                    or_(
                        ContactRequest.claim_id.is_(None),
                        ContactRequest.claim_id.notin_(related_claim_ids),
                    )
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
                "requests": [_contact_request_payload(row) for row in rows],
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
        return jsonify({"contact_request": _contact_request_payload(contact_request)})
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


def _apply_club_consent(
    contact_request: ContactRequest,
    action: str,
    *,
    actor_user_id: int | None,
    note: str | None,
) -> None:
    now = utcnow()
    contact_request.club_consent_status = "granted" if action == "grant" else "declined"
    contact_request.club_consent_at = now
    contact_request.club_consent_by_user_id = actor_user_id
    contact_request.club_consent_note = note
    if action == "decline":
        contact_request.status = "declined"
        contact_request.responded_at = now
    event_type = "club_consent_granted" if action == "grant" else "club_consent_declined"
    add_audit_event(
        contact_request,
        event_type,
        actor_user_id=actor_user_id,
        metadata={"note": note} if note else {},
        created_at=now,
    )


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
            or not _is_club_manager(contact_request, user, for_update=True)
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

        _apply_club_consent(
            contact_request,
            action,
            actor_user_id=user.id,
            note=note,
        )
        db.session.commit()
        return jsonify({"contact_request": _contact_request_payload(contact_request)})
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        logger.exception("Failed to set club consent for request %s", request_id)
        return jsonify(_safe_error_payload(exc, "Failed to set club consent")), 500


def _public_consent_summary(contact_request: ContactRequest, action: str) -> dict:
    from src.models.trust import ScoutVerification
    from src.services.club_registry import get_club_program

    verification = (
        ScoutVerification.query.filter_by(user_account_id=contact_request.scout_user_id, status="approved")
        .order_by(ScoutVerification.submitted_at.desc(), ScoutVerification.id.desc())
        .first()
    )
    program = get_club_program(contact_request.club_program_id)
    return {
        "action": action,
        "contact_request_id": contact_request.id,
        "player_reference": f"player profile {contact_request.player_api_id}",
        "program_name": program.get("name") if program else None,
        "scout": {
            "name": verification.full_name
            if verification
            else (contact_request.scout.display_name if contact_request.scout else None),
            "organization": verification.organization if verification else None,
        },
        "confirmation_required": True,
    }


@contact_bp.route("/contact/club-consent/<string:token>", methods=["GET", "POST"])
@require_contact_rail
def public_club_consent(token: str):
    """Inspect or execute one signed, state-bound club consent capability."""
    payload = load_club_consent_token(token)
    if payload is None:
        return _invalid_consent_link()
    try:
        query = ContactRequest.query.filter_by(id=payload["contact_request_id"])
        if request.method == "POST":
            query = query.populate_existing().with_for_update()
        contact_request = query.first()
        if (
            contact_request is None
            or contact_request.routing_mode != ROUTING_CLUB_INCLUDED
            or not program_is_operational(
                contact_request.club_program_id,
                for_update=True,
            )
            or contact_request.status not in ACTIVE_REQUEST_STATUSES
            or contact_request.club_consent_status != "pending"
        ):
            db.session.rollback()
            return _invalid_consent_link()
        if request_can_expire(contact_request) and contact_request.expires_at <= utcnow():
            expire_if_due(contact_request)
            db.session.commit()
            return _invalid_consent_link()
        if request.method == "GET":
            return jsonify({"decision": _public_consent_summary(contact_request, payload["action"])})

        _apply_club_consent(
            contact_request,
            payload["action"],
            actor_user_id=None,
            note=None,
        )
        db.session.commit()
        return jsonify(
            {
                "decision": "granted" if payload["action"] == "grant" else "declined",
                "contact_request_id": contact_request.id,
            }
        )
    except Exception:
        db.session.rollback()
        logger.exception("Failed to process public club consent link")
        return _invalid_consent_link()


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
        return jsonify({"contact_request": _contact_request_payload(contact_request)})
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
        contact_request, error = _participant_request(request_id, user, club_for_update=True)
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
                "messages": [_contact_message_payload(row) for row in rows],
                "contact_request": _contact_request_payload(contact_request),
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
        contact_request, error = _participant_request(request_id, user, club_for_update=True)
        if error:
            return error
        if not messaging_is_open(contact_request):
            return _messaging_gate_error(contact_request, sending=True)
        sender_role = _participant_role(contact_request, user, club_for_update=True)
        if sender_role == "player" and _lock_claim_owner(contact_request, user) is None:
            db.session.rollback()
            return jsonify({"error": "contact request not found"}), 404
        if sender_role == "club" and not _is_club_manager(contact_request, user, for_update=True):
            db.session.rollback()
            return jsonify({"error": "contact request not found"}), 404
        if sender_role is None:
            db.session.rollback()
            return jsonify({"error": "contact request not found"}), 404

        player_user_id = contact_request.claim.user_account_id if contact_request.claim is not None else None
        counterpart_user_ids = [contact_request.scout_user_id, player_user_id]
        if contact_request.routing_mode == ROUTING_CLUB_INCLUDED and program_is_operational(
            contact_request.club_program_id,
            for_update=True,
        ):
            counterpart_user_ids.extend(active_program_manager_user_ids(contact_request.club_program_id))
        if user_has_block_relationship_with_any(
            user_id=user.id,
            counterpart_user_ids=counterpart_user_ids,
        ):
            db.session.rollback()
            return jsonify(
                {
                    "error": "Messaging is unavailable for this contact request",
                    "code": "messaging_unavailable",
                }
            ), 403

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
        return jsonify({"message": _contact_message_payload(message)}), 201
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
        contact_request, error = _participant_request(request_id, user, club_for_update=True)
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
        return jsonify(
            {
                "outcome": outcome.to_dict(),
                "contact_request": _contact_request_payload(contact_request),
            }
        ), 201
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        logger.exception("Failed to report outcome for contact request %s", request_id)
        return jsonify(_safe_error_payload(exc, "Failed to report contact outcome")), 500


__all__ = ["contact_bp"]
