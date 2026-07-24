"""Authenticated lifecycle routes for persistent user-level blocks."""

import logging

from flask import Blueprint, g, jsonify, request
from sqlalchemy.exc import IntegrityError
from src.auth import _safe_error_payload, require_user_auth
from src.extensions import limiter
from src.models.league import UserAccount, db
from src.models.user_block import UserBlock

logger = logging.getLogger(__name__)

blocks_bp = Blueprint("blocks", __name__)

BLOCK_MUTATION_RATE_LIMIT = "30 per minute"
BLOCK_LIST_RATE_LIMIT = "60 per minute"


def _user_rate_limit_key() -> str:
    return str(getattr(g, "user_id", None) or getattr(g, "user_email", None) or request.remote_addr or "anon")


def _block_payload(block: UserBlock, blocked_user: UserAccount | None = None) -> dict:
    target = blocked_user or db.session.get(UserAccount, block.blocked_user_id)
    return {
        "blocked_user_id": block.blocked_user_id,
        "display_name": target.display_name if target and not target.is_tombstone else None,
        "created_at": block.created_at.isoformat() if block.created_at else None,
    }


def _blocked_user_id(payload) -> int:
    if not isinstance(payload, dict):
        raise ValueError("JSON body must be an object")
    value = payload.get("blocked_user_id")
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("blocked_user_id must be a positive integer")
    return value


@blocks_bp.route("/blocks", methods=["POST"])
@require_user_auth
@limiter.limit(BLOCK_MUTATION_RATE_LIMIT, key_func=_user_rate_limit_key)
def create_user_block():
    """Block one existing user; repeated requests are idempotent."""
    try:
        blocked_user_id = _blocked_user_id(request.get_json(silent=True))
        if blocked_user_id == g.user.id:
            return jsonify({"error": "you cannot block yourself"}), 400

        blocked_user = db.session.get(UserAccount, blocked_user_id)
        if blocked_user is None or blocked_user.is_tombstone:
            return jsonify({"error": "user not found"}), 404

        existing = UserBlock.query.filter_by(
            blocker_user_id=g.user.id,
            blocked_user_id=blocked_user_id,
        ).first()
        if existing is not None:
            return jsonify({"block": _block_payload(existing, blocked_user)}), 200

        block = UserBlock(
            blocker_user_id=g.user.id,
            blocked_user_id=blocked_user_id,
        )
        db.session.add(block)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            existing = UserBlock.query.filter_by(
                blocker_user_id=g.user.id,
                blocked_user_id=blocked_user_id,
            ).first()
            if existing is None:
                raise
            return jsonify({"block": _block_payload(existing, blocked_user)}), 200
        return jsonify({"block": _block_payload(block, blocked_user)}), 201
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        logger.exception("Failed to create user block")
        return jsonify(_safe_error_payload(exc, "Failed to block user")), 500


@blocks_bp.route("/blocks", methods=["GET"])
@require_user_auth
@limiter.limit(BLOCK_LIST_RATE_LIMIT, key_func=_user_rate_limit_key)
def list_user_blocks():
    """List only blocks created by the authenticated caller."""
    try:
        rows = (
            db.session.query(UserBlock, UserAccount)
            .join(UserAccount, UserAccount.id == UserBlock.blocked_user_id)
            .filter(
                UserBlock.blocker_user_id == g.user.id,
                UserAccount.is_tombstone.is_(False),
            )
            .order_by(UserBlock.created_at.desc(), UserBlock.id.desc())
            .all()
        )
        return jsonify({"blocks": [_block_payload(block, target) for block, target in rows]})
    except Exception as exc:
        db.session.rollback()
        logger.exception("Failed to list user blocks")
        return jsonify(_safe_error_payload(exc, "Failed to list blocked users")), 500


@blocks_bp.route("/blocks/<int:blocked_user_id>", methods=["DELETE"])
@require_user_auth
@limiter.limit(BLOCK_MUTATION_RATE_LIMIT, key_func=_user_rate_limit_key)
def delete_user_block(blocked_user_id: int):
    """Remove one caller-owned block; repeated requests are idempotent."""
    try:
        removed = UserBlock.query.filter_by(
            blocker_user_id=g.user.id,
            blocked_user_id=blocked_user_id,
        ).delete(synchronize_session=False)
        db.session.commit()
        return jsonify({"removed": bool(removed)})
    except Exception as exc:
        db.session.rollback()
        logger.exception("Failed to delete user block")
        return jsonify(_safe_error_payload(exc, "Failed to unblock user")), 500


__all__ = ["blocks_bp"]
