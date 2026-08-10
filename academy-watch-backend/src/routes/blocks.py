"""Authenticated lifecycle routes for persistent user-level blocks."""

import logging

from flask import Blueprint, g, jsonify, request
from sqlalchemy.exc import IntegrityError, ProgrammingError
from src.auth import _safe_error_payload, require_user_auth
from src.extensions import limiter
from src.models.league import UserAccount, db
from src.models.user_block import UserBlock
from src.services.club_registry import active_manager_program_ids, program_is_operational
from src.services.user_blocks import (
    is_user_blocks_undefined_table_error,
    log_user_blocks_table_unavailable_once,
)

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


def _blocks_unavailable():
    return jsonify({"error": "Blocking is temporarily unavailable", "code": "blocks_unavailable"}), 503


@blocks_bp.route("/blocks", methods=["POST"])
@require_user_auth
@limiter.limit(BLOCK_MUTATION_RATE_LIMIT, key_func=_user_rate_limit_key)
def create_user_block():
    """Idempotently block a target without disclosing account existence."""
    try:
        blocked_user_id = _blocked_user_id(request.get_json(silent=True))
        if blocked_user_id == g.user.id:
            return jsonify({"error": "you cannot block yourself"}), 400

        existing = UserBlock.query.filter_by(
            blocker_user_id=g.user.id,
            blocked_user_id=blocked_user_id,
        ).first()
        if existing is not None:
            return "", 204

        blocked_user = db.session.get(UserAccount, blocked_user_id)
        if blocked_user is None or blocked_user.is_tombstone:
            return "", 204

        block = UserBlock(
            blocker_user_id=g.user.id,
            blocked_user_id=blocked_user_id,
        )
        db.session.add(block)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            # A concurrent duplicate or target deletion is indistinguishable
            # from the already-satisfied neutral contract.
            return "", 204
        return "", 204
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400
    except ProgrammingError as exc:
        db.session.rollback()
        if is_user_blocks_undefined_table_error(exc):
            log_user_blocks_table_unavailable_once()
            return _blocks_unavailable()
        logger.exception("Failed to create user block")
        return jsonify(_safe_error_payload(exc, "Failed to block user")), 500
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
        managed_program_ids = sorted(active_manager_program_ids(g.user.id))
        if any(not program_is_operational(program_id, for_update=True) for program_id in managed_program_ids):
            return jsonify({"blocks": []})
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
        if is_user_blocks_undefined_table_error(exc):
            log_user_blocks_table_unavailable_once()
            return _blocks_unavailable()
        logger.exception("Failed to list user blocks")
        return jsonify(_safe_error_payload(exc, "Failed to list blocked users")), 500


@blocks_bp.route("/blocks/<int:blocked_user_id>", methods=["DELETE"])
@require_user_auth
@limiter.limit(BLOCK_MUTATION_RATE_LIMIT, key_func=_user_rate_limit_key)
def delete_user_block(blocked_user_id: int):
    """Remove one caller-owned block; repeated requests are idempotent."""
    try:
        UserBlock.query.filter_by(
            blocker_user_id=g.user.id,
            blocked_user_id=blocked_user_id,
        ).delete(synchronize_session=False)
        db.session.commit()
        return "", 204
    except Exception as exc:
        db.session.rollback()
        if is_user_blocks_undefined_table_error(exc):
            log_user_blocks_table_unavailable_once()
            return _blocks_unavailable()
        logger.exception("Failed to delete user block")
        return jsonify(_safe_error_payload(exc, "Failed to unblock user")), 500


__all__ = ["blocks_bp"]
