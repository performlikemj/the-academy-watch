"""Trust prerequisites for scout verification and user content reports."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from flask import Blueprint, g, jsonify, request
from sqlalchemy.exc import IntegrityError
from src.auth import _ensure_user_account, _safe_error_payload, require_api_key, require_user_auth
from src.extensions import limiter
from src.models.league import UserAccount, db
from src.models.trust import ContentReport, ScoutVerification
from src.utils.sanitize import is_safe_https_url, sanitize_comment_body, sanitize_plain_text

logger = logging.getLogger(__name__)
trust_bp = Blueprint("trust", __name__)

VERIFICATION_STATUSES = {"pending", "approved", "rejected", "revoked"}
ACTIVE_VERIFICATION_STATUSES = {"pending", "approved"}
REPORT_SUBJECT_TYPES = {
    "player_profile",
    "showcase_content",
    "club_program",
    "contact_message",
    "other",
}
REPORT_STATUSES = {"open", "reviewing", "resolved", "dismissed"}
REPORT_RESOLUTION_STATUSES = {"resolved", "dismissed"}

MAX_FULL_NAME_LENGTH = 200
MAX_ORGANIZATION_LENGTH = 200
MAX_ROLE_TITLE_LENGTH = 120
MAX_STATEMENT_LENGTH = 2000
MAX_REVIEW_NOTES_LENGTH = 2000
MAX_REVOCATION_REASON_LENGTH = 1000
MAX_EVIDENCE_URL_LENGTH = 500
MAX_EVIDENCE_URLS = 10

MAX_SUBJECT_ID_LENGTH = 200
MAX_REASON_CODE_LENGTH = 80
MAX_REPORT_DETAILS_LENGTH = 2000
MAX_RESOLUTION_NOTES_LENGTH = 2000
MAX_ADMIN_PAGE_SIZE = 200

VERIFICATION_RATE_LIMIT = "3 per hour"
REPORT_RATE_LIMIT_PER_MINUTE = "10 per minute"
REPORT_RATE_LIMIT_PER_HOUR = "30 per hour"


def _clean_text(value, field: str, *, max_len: int, required: bool = True) -> str | None:
    """Validate and bleach-clean a short plain-text value."""
    if value is None:
        if required:
            raise ValueError(f"{field} is required")
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    cleaned = sanitize_plain_text(value).strip()
    if not cleaned:
        if required:
            raise ValueError(f"{field} is required")
        return None
    if len(cleaned) > max_len:
        raise ValueError(f"{field} must be at most {max_len} characters")
    return cleaned


def _clean_body(value, field: str, *, max_len: int, required: bool = True) -> str | None:
    """Validate and bleach-clean a bounded free-text value."""
    if value is None:
        if required:
            raise ValueError(f"{field} is required")
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    cleaned = sanitize_comment_body(value).strip()
    if not cleaned:
        if required:
            raise ValueError(f"{field} is required")
        return None
    if len(cleaned) > max_len:
        raise ValueError(f"{field} must be at most {max_len} characters")
    return cleaned


def _enum(value, field: str, allowed: set[str]) -> str:
    cleaned = _clean_text(value, field, max_len=80)
    normalized = cleaned.lower()
    if normalized not in allowed:
        raise ValueError(f"{field} must be one of {sorted(allowed)}")
    return normalized


def _evidence_urls(value) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError("evidence_urls must be a non-empty list")
    if len(value) > MAX_EVIDENCE_URLS:
        raise ValueError(f"evidence_urls must contain at most {MAX_EVIDENCE_URLS} URLs")

    urls: list[str] = []
    for item in value:
        cleaned = _clean_text(item, "evidence_urls item", max_len=MAX_EVIDENCE_URL_LENGTH)
        if not is_safe_https_url(cleaned):
            raise ValueError("evidence_urls entries must be absolute https URLs")
        if cleaned not in urls:
            urls.append(cleaned)
    return urls


def _user_rate_limit_key() -> str:
    # The ingress proxy makes request.remote_addr a shared bucket in production;
    # authenticated trust actions must be limited per account instead.
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


def _active_verification(user_id: int) -> ScoutVerification | None:
    return (
        ScoutVerification.query.filter(
            ScoutVerification.user_account_id == user_id,
            ScoutVerification.status.in_(ACTIVE_VERIFICATION_STATUSES),
        )
        .order_by(ScoutVerification.submitted_at.desc(), ScoutVerification.id.desc())
        .first()
    )


def _admin_actor() -> str:
    return (getattr(g, "user_email", None) or "admin")[:200]


def _pagination() -> tuple[int, int]:
    limit = request.args.get("limit", 50, type=int)
    offset = request.args.get("offset", 0, type=int)
    limit = min(MAX_ADMIN_PAGE_SIZE, max(1, limit if limit is not None else 50))
    offset = max(0, offset if offset is not None else 0)
    return limit, offset


def _json_object() -> dict:
    payload = request.get_json(silent=True)
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValueError("JSON body must be an object")
    return payload


# ---------------------------------------------------------------------------
# Scout verification
# ---------------------------------------------------------------------------


@trust_bp.route("/scout/verification", methods=["POST"])
@require_user_auth
@limiter.limit(VERIFICATION_RATE_LIMIT, key_func=_user_rate_limit_key)
def submit_scout_verification():
    """Submit a scout verification application for admin review."""
    try:
        user = _current_user_account()
        if user is None:
            return jsonify({"error": "auth context missing email"}), 401

        active = _active_verification(user.id)
        if active is not None:
            return jsonify(
                {"error": "an active scout verification already exists", "verification": active.to_dict()}
            ), 409

        payload = _json_object()
        verification = ScoutVerification(
            user_account_id=user.id,
            full_name=_clean_text(payload.get("full_name"), "full_name", max_len=MAX_FULL_NAME_LENGTH),
            organization=_clean_text(payload.get("organization"), "organization", max_len=MAX_ORGANIZATION_LENGTH),
            role_title=_clean_text(payload.get("role_title"), "role_title", max_len=MAX_ROLE_TITLE_LENGTH),
            statement=_clean_body(payload.get("statement"), "statement", max_len=MAX_STATEMENT_LENGTH),
            evidence_urls=_evidence_urls(payload.get("evidence_urls")),
            status="pending",
        )
        db.session.add(verification)
        try:
            db.session.commit()
        except IntegrityError:
            # The partial unique index is authoritative if simultaneous requests
            # both pass the application-level active-row check.
            db.session.rollback()
            active = _active_verification(user.id)
            if active is not None:
                return jsonify(
                    {"error": "an active scout verification already exists", "verification": active.to_dict()}
                ), 409
            raise
        return jsonify({"verification": verification.to_dict()}), 201
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        logger.exception("Failed to submit scout verification")
        return jsonify(_safe_error_payload(exc, "Failed to submit scout verification")), 500


@trust_bp.route("/scout/verification", methods=["GET"])
@require_user_auth
def get_scout_verification():
    """Return the caller's latest scout verification, including inactive history."""
    try:
        user = _current_user_account()
        if user is None:
            return jsonify({"error": "auth context missing email"}), 401
        verification = (
            ScoutVerification.query.filter_by(user_account_id=user.id)
            .order_by(ScoutVerification.submitted_at.desc(), ScoutVerification.id.desc())
            .first()
        )
        return jsonify({"verification": verification.to_dict() if verification else None})
    except Exception as exc:
        logger.exception("Failed to load scout verification")
        return jsonify(_safe_error_payload(exc, "Failed to load scout verification")), 500


@trust_bp.route("/admin/scout-verifications", methods=["GET"])
@require_api_key
def admin_list_scout_verifications():
    """List verification applications, defaulting to the pending queue."""
    try:
        status = (request.args.get("status") or "pending").strip().lower()
        query = ScoutVerification.query
        if status != "all":
            if status not in VERIFICATION_STATUSES:
                return jsonify({"error": f"status must be one of {sorted(VERIFICATION_STATUSES)} or all"}), 400
            query = query.filter(ScoutVerification.status == status)

        limit, offset = _pagination()
        total = query.count()
        rows = (
            query.order_by(ScoutVerification.submitted_at.asc(), ScoutVerification.id.asc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return jsonify(
            {
                "verifications": [row.admin_dict() for row in rows],
                "total": total,
                "limit": limit,
                "offset": offset,
            }
        )
    except Exception as exc:
        logger.exception("Failed to list scout verifications")
        return jsonify(_safe_error_payload(exc, "Failed to list scout verifications")), 500


def _review_scout_verification(verification_id: int, action: str):
    try:
        verification = db.session.get(ScoutVerification, verification_id)
        if verification is None:
            return jsonify({"error": "scout verification not found"}), 404

        payload = _json_object()
        now = datetime.now(UTC)
        if action == "approve":
            if verification.status != "pending":
                return jsonify({"error": f"cannot approve a {verification.status} verification"}), 409
            verification.status = "approved"
            verification.review_notes = _clean_body(
                payload.get("review_notes", payload.get("notes", payload.get("reason"))),
                "review_notes",
                max_len=MAX_REVIEW_NOTES_LENGTH,
            )
        elif action == "reject":
            if verification.status != "pending":
                return jsonify({"error": f"cannot reject a {verification.status} verification"}), 409
            verification.status = "rejected"
            verification.review_notes = _clean_body(
                payload.get("review_notes", payload.get("notes", payload.get("reason"))),
                "review_notes",
                max_len=MAX_REVIEW_NOTES_LENGTH,
            )
        elif action == "revoke":
            if verification.status != "approved":
                return jsonify({"error": f"cannot revoke a {verification.status} verification"}), 409
            verification.status = "revoked"
            verification.revocation_reason = _clean_body(
                payload.get("revocation_reason", payload.get("reason")),
                "revocation_reason",
                max_len=MAX_REVOCATION_REASON_LENGTH,
            )
        else:  # pragma: no cover - routes below pass constants only
            raise ValueError("unsupported verification action")

        verification.reviewed_by = _admin_actor()
        verification.reviewed_at = now
        db.session.commit()
        return jsonify({"verification": verification.admin_dict()})
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        logger.exception("Failed to %s scout verification %s", action, verification_id)
        return jsonify(_safe_error_payload(exc, f"Failed to {action} scout verification")), 500


@trust_bp.route("/admin/scout-verifications/<int:verification_id>/approve", methods=["POST"])
@require_api_key
def admin_approve_scout_verification(verification_id: int):
    return _review_scout_verification(verification_id, "approve")


@trust_bp.route("/admin/scout-verifications/<int:verification_id>/reject", methods=["POST"])
@require_api_key
def admin_reject_scout_verification(verification_id: int):
    return _review_scout_verification(verification_id, "reject")


@trust_bp.route("/admin/scout-verifications/<int:verification_id>/revoke", methods=["POST"])
@require_api_key
def admin_revoke_scout_verification(verification_id: int):
    return _review_scout_verification(verification_id, "revoke")


# ---------------------------------------------------------------------------
# Content reports
# ---------------------------------------------------------------------------


@trust_bp.route("/reports", methods=["POST"])
@require_user_auth
@limiter.limit(REPORT_RATE_LIMIT_PER_MINUTE, key_func=_user_rate_limit_key)
@limiter.limit(REPORT_RATE_LIMIT_PER_HOUR, key_func=_user_rate_limit_key)
def submit_content_report():
    """Submit a bounded, sanitized report for admin moderation."""
    try:
        user = _current_user_account()
        if user is None:
            return jsonify({"error": "auth context missing email"}), 401
        payload = _json_object()
        report = ContentReport(
            reporter_user_id=user.id,
            subject_type=_enum(payload.get("subject_type"), "subject_type", REPORT_SUBJECT_TYPES),
            subject_id=_clean_text(payload.get("subject_id"), "subject_id", max_len=MAX_SUBJECT_ID_LENGTH),
            reason_code=_clean_text(payload.get("reason_code"), "reason_code", max_len=MAX_REASON_CODE_LENGTH).lower(),
            details=_clean_body(payload.get("details"), "details", max_len=MAX_REPORT_DETAILS_LENGTH, required=False),
            status="open",
        )
        db.session.add(report)
        db.session.commit()
        return jsonify({"report": report.to_dict()}), 201
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        logger.exception("Failed to submit content report")
        return jsonify(_safe_error_payload(exc, "Failed to submit content report")), 500


@trust_bp.route("/admin/reports", methods=["GET"])
@require_api_key
def admin_list_content_reports():
    """List content reports, defaulting to the open moderation queue."""
    try:
        status = (request.args.get("status") or "open").strip().lower()
        query = ContentReport.query
        if status != "all":
            if status not in REPORT_STATUSES:
                return jsonify({"error": f"status must be one of {sorted(REPORT_STATUSES)} or all"}), 400
            query = query.filter(ContentReport.status == status)

        limit, offset = _pagination()
        total = query.count()
        rows = query.order_by(ContentReport.created_at.asc(), ContentReport.id.asc()).offset(offset).limit(limit).all()
        return jsonify(
            {
                "reports": [row.admin_dict() for row in rows],
                "total": total,
                "limit": limit,
                "offset": offset,
            }
        )
    except Exception as exc:
        logger.exception("Failed to list content reports")
        return jsonify(_safe_error_payload(exc, "Failed to list content reports")), 500


@trust_bp.route("/admin/reports/<int:report_id>/resolve", methods=["POST"])
@require_api_key
def admin_resolve_content_report(report_id: int):
    """Resolve or dismiss a content report with a bounded admin note."""
    try:
        report = db.session.get(ContentReport, report_id)
        if report is None:
            return jsonify({"error": "content report not found"}), 404
        if report.status in REPORT_RESOLUTION_STATUSES:
            return jsonify({"error": f"content report is already {report.status}"}), 409

        payload = _json_object()
        status = _enum(payload.get("status"), "status", REPORT_RESOLUTION_STATUSES)
        resolution_notes = _clean_body(
            payload.get("resolution_notes"),
            "resolution_notes",
            max_len=MAX_RESOLUTION_NOTES_LENGTH,
        )
        report.status = status
        report.resolution_notes = resolution_notes
        report.resolved_at = datetime.now(UTC)
        db.session.commit()
        return jsonify({"report": report.admin_dict()})
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        logger.exception("Failed to resolve content report %s", report_id)
        return jsonify(_safe_error_payload(exc, "Failed to resolve content report")), 500


__all__ = ["trust_bp"]
