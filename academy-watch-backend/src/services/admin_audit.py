"""Add privileged action history to the caller's transaction; never commit."""

import json
import re

from src.models.league import db
from src.models.p2_foundation import AdminActionEvent
from src.utils.sanitize import sanitize_plain_text


def bounded_meta(meta):
    """Only scalar IDs, booleans and machine codes; no names/bodies/secrets."""
    if meta is None:
        return {}
    if not isinstance(meta, dict) or len(meta) > 16:
        raise ValueError("metadata must be an object with at most 16 fields")
    for key, value in meta.items():
        if not isinstance(key, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,39}", key):
            raise ValueError("invalid metadata key")
        if value is not None and not isinstance(value, (bool, int, str)):
            raise ValueError("metadata values must be scalar IDs, booleans or machine codes")
        if isinstance(value, str) and not re.fullmatch(r"[a-z0-9_-]{1,80}", value):
            raise ValueError("metadata strings must be machine codes; no personal data")
    if len(json.dumps(meta)) > 2048:
        raise ValueError("metadata is too large")
    return dict(meta)


def record_admin_event(actor, action, target_type, target_id, reason, meta=None):
    """actor is an authenticated email or UserAccount; return the added event."""
    email = getattr(actor, "email", actor)
    if not isinstance(email, str) or not email.strip() or len(email) > 254:
        raise ValueError("actor is required")
    if not isinstance(reason, str):
        raise ValueError("reason is required")
    reason = sanitize_plain_text(reason).strip()
    if not reason or len(reason) > 2000:
        raise ValueError("reason must contain 1–2000 characters")
    for value in (action, target_type, str(target_id)):
        if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", value):
            raise ValueError("invalid audit action or target")
    row = AdminActionEvent(
        actor_email=email.strip().lower(),
        action=action,
        target_type=target_type,
        target_id=str(target_id),
        reason=reason,
        event_metadata=bounded_meta(meta),
    )
    db.session.add(row)
    return row
