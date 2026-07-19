"""Authenticated data-subject export and immediate account deletion routes."""

import logging

from flask import Blueprint, g, jsonify, request
from src.auth import _safe_error_payload, require_user_auth
from src.extensions import limiter
from src.models.league import db
from src.services.account import AccountDeletionUnavailable, build_account_export, delete_account

logger = logging.getLogger(__name__)

account_bp = Blueprint("account", __name__)


def _user_rate_limit_key() -> str:
    return str(getattr(g, "user_id", None) or getattr(g, "user_email", None) or request.remote_addr or "anon")


@account_bp.route("/account/export", methods=["GET"])
@require_user_auth
@limiter.limit("3 per hour", key_func=_user_rate_limit_key)
def export_account_data():
    """Return one portable JSON document containing the caller's DSR data."""
    try:
        return jsonify(build_account_export(g.user))
    except Exception as exc:
        db.session.rollback()
        logger.exception("Failed to export account data")
        return jsonify(_safe_error_payload(exc, "Failed to export account data")), 500


@account_bp.route("/account/delete", methods=["POST"])
@require_user_auth
@limiter.limit("5 per hour", key_func=_user_rate_limit_key)
def delete_current_account():
    """Immediately and irreversibly delete the authenticated account."""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or payload.get("confirm") != "DELETE":
        return jsonify({"error": 'confirm must exactly equal "DELETE"'}), 400

    try:
        event = delete_account(g.user)
        db.session.commit()
        return jsonify(
            {
                "deleted": True,
                "deletion_event_id": event.id,
                "completed_at": event.completed_at.isoformat(),
                "counts": event.counts,
            }
        )
    except AccountDeletionUnavailable:
        db.session.rollback()
        return jsonify({"error": "account not found"}), 401
    except Exception as exc:
        db.session.rollback()
        logger.exception("Failed to delete account")
        return jsonify(_safe_error_payload(exc, "Failed to delete account")), 500


__all__ = ["account_bp"]
