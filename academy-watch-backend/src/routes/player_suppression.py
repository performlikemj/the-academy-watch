"""Public player takedown intake and admin suppression lifecycle."""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime

from flask import Blueprint, g, jsonify, request
from sqlalchemy.exc import IntegrityError
from src.auth import _safe_error_payload, require_api_key
from src.extensions import limiter
from src.models.follow import PlayerShadow
from src.models.league import db
from src.models.player_suppression import PlayerSuppression
from src.utils.sanitize import sanitize_plain_text

logger = logging.getLogger(__name__)
player_suppression_bp = Blueprint("player_suppression", __name__)

REQUESTER_ROLES = {"player", "guardian", "club", "other"}
SUPPRESSION_STATUSES = {"requested", "active", "lifted", "rejected"}
ROLE_REASON_CODES = {
    "player": "player_request",
    "guardian": "guardian_request",
    "club": "admin_other",
    "other": "admin_other",
}

MAX_CONTACT_LENGTH = 254
MAX_STATEMENT_LENGTH = 2000
MAX_NOTES_LENGTH = 2000
MAX_ADMIN_PAGE_SIZE = 200
INTAKE_RATE_LIMIT_PER_MINUTE = "5 per minute"
INTAKE_RATE_LIMIT_PER_HOUR = "20 per hour"
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
ACKNOWLEDGMENT = {"message": "Your takedown request has been received and will be reviewed."}


def _json_object() -> dict:
    payload = request.get_json(silent=True)
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValueError("JSON body must be an object")
    return payload


def _clean_required(value, field: str, *, max_len: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    cleaned = sanitize_plain_text(value).strip()
    if not cleaned:
        raise ValueError(f"{field} is required")
    if len(cleaned) > max_len:
        raise ValueError(f"{field} must be at most {max_len} characters")
    return cleaned


def _contact_email(value) -> str:
    email = _clean_required(value, "contact_email", max_len=MAX_CONTACT_LENGTH).lower()
    if not EMAIL_PATTERN.fullmatch(email):
        raise ValueError("contact_email must be a valid email address")
    return email


def _neutral_acknowledgment():
    return jsonify(ACKNOWLEDGMENT), 202


@player_suppression_bp.route("/players/<int:player_api_id>/takedown-request", methods=["POST"])
@limiter.limit(INTAKE_RATE_LIMIT_PER_MINUTE)
@limiter.limit(INTAKE_RATE_LIMIT_PER_HOUR)
def submit_takedown_request(player_api_id: int):
    """Accept a request without checking or revealing player existence."""

    try:
        payload = _json_object()
        requester_role = _clean_required(payload.get("requester_role"), "requester_role", max_len=20).lower()
        if requester_role not in REQUESTER_ROLES:
            raise ValueError(f"requester_role must be one of {sorted(REQUESTER_ROLES)}")
        contact = _contact_email(payload.get("contact_email"))
        statement = _clean_required(payload.get("statement"), "statement", max_len=MAX_STATEMENT_LENGTH)
        now = datetime.now(UTC)

        suppression = (
            PlayerSuppression.query.filter(
                PlayerSuppression.player_api_id == player_api_id,
                PlayerSuppression.status.in_(("requested", "active")),
            )
            .order_by(PlayerSuppression.created_at.desc(), PlayerSuppression.id.desc())
            .populate_existing()
            .with_for_update()
            .first()
        )
        if suppression is None:
            suppression = PlayerSuppression(
                player_api_id=player_api_id,
                reason_code=ROLE_REASON_CODES[requester_role],
                requester_role=requester_role,
                requester_contact=contact,
                request_statement=statement,
                status="requested",
                created_at=now,
                updated_at=now,
            )
            db.session.add(suppression)
        elif suppression.status == "requested":
            # Attach the latest sanitized request details to the one open
            # lifecycle. Once active, public duplicates are acknowledged but
            # cannot overwrite the evidence behind an admin decision.
            suppression.requester_role = requester_role
            suppression.requester_contact = contact
            suppression.request_statement = statement
            suppression.updated_at = now
            suppression.reason_code = ROLE_REASON_CODES[requester_role]
        try:
            db.session.commit()
        except IntegrityError:
            # Simultaneous neutral submissions may race the partial unique
            # index.  The winning row is sufficient; both callers get the same
            # no-oracle acknowledgment.
            db.session.rollback()
        return _neutral_acknowledgment()
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        logger.exception("Failed to record player takedown request")
        return jsonify(_safe_error_payload(exc, "Failed to submit takedown request")), 500


def _admin_actor() -> str:
    return (getattr(g, "user_email", None) or "admin")[:200]


def _pagination() -> tuple[int, int]:
    limit = request.args.get("limit", 50, type=int)
    offset = request.args.get("offset", 0, type=int)
    return min(MAX_ADMIN_PAGE_SIZE, max(1, limit or 50)), max(0, offset or 0)


@player_suppression_bp.route("/admin/suppressions", methods=["GET"])
@require_api_key
def admin_list_suppressions():
    """List the moderation queue, defaulting to requested rows."""

    try:
        status = (request.args.get("status") or "requested").strip().lower()
        query = PlayerSuppression.query
        if status != "all":
            if status not in SUPPRESSION_STATUSES:
                return jsonify({"error": f"status must be one of {sorted(SUPPRESSION_STATUSES)} or all"}), 400
            query = query.filter(PlayerSuppression.status == status)
        limit, offset = _pagination()
        total = query.count()
        rows = (
            query.order_by(PlayerSuppression.created_at.asc(), PlayerSuppression.id.asc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return jsonify(
            {
                "suppressions": [row.admin_dict() for row in rows],
                "total": total,
                "limit": limit,
                "offset": offset,
            }
        )
    except Exception as exc:
        db.session.rollback()
        logger.exception("Failed to load suppression queue")
        return jsonify(_safe_error_payload(exc, "Failed to load suppressions")), 500


def _decision_notes() -> str:
    payload = _json_object()
    return _clean_required(payload.get("notes"), "notes", max_len=MAX_NOTES_LENGTH)


def _decide_suppression(suppression_id: int, action: str):
    transitions = {
        "activate": ({"requested", "active"}, "active"),
        "reject": ({"requested", "rejected"}, "rejected"),
        "lift": ({"active", "lifted"}, "lifted"),
    }
    try:
        notes = _decision_notes()
        suppression = PlayerSuppression.query.filter_by(id=suppression_id).populate_existing().with_for_update().first()
        if suppression is None:
            return jsonify({"error": "suppression not found"}), 404
        allowed, target = transitions[action]
        if suppression.status not in allowed:
            return jsonify({"error": f"cannot {action} a {suppression.status} suppression"}), 409

        suppression.status = target
        suppression.notes = notes
        suppression.decided_at = datetime.now(UTC)
        suppression.decided_by = _admin_actor()
        suppression.updated_at = suppression.decided_at

        if action == "activate":
            PlayerShadow.query.filter_by(player_api_id=suppression.player_api_id).update(
                {PlayerShadow.is_active: False},
                synchronize_session=False,
            )
        elif action == "lift":
            # Activation only soft-deactivates the shadow; lifting restores it
            # so existing follows work again without deleting/re-minting data.
            PlayerShadow.query.filter_by(player_api_id=suppression.player_api_id).update(
                {PlayerShadow.is_active: True},
                synchronize_session=False,
            )

        db.session.commit()
        return jsonify({"suppression": suppression.admin_dict()})
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        logger.exception("Failed to %s suppression %s", action, suppression_id)
        return jsonify(_safe_error_payload(exc, f"Failed to {action} suppression")), 500


@player_suppression_bp.route("/admin/suppressions/<int:suppression_id>/activate", methods=["POST"])
@require_api_key
def admin_activate_suppression(suppression_id: int):
    return _decide_suppression(suppression_id, "activate")


@player_suppression_bp.route("/admin/suppressions/<int:suppression_id>/reject", methods=["POST"])
@require_api_key
def admin_reject_suppression(suppression_id: int):
    return _decide_suppression(suppression_id, "reject")


@player_suppression_bp.route("/admin/suppressions/<int:suppression_id>/lift", methods=["POST"])
@require_api_key
def admin_lift_suppression(suppression_id: int):
    return _decide_suppression(suppression_id, "lift")


__all__ = ["player_suppression_bp"]
