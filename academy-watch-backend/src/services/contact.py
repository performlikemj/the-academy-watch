"""Shared policy helpers for the feature-gated contact rail."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from functools import wraps

from flask import abort
from src.models.contact import ContactAuditEvent, ContactRequest
from src.models.league import db
from src.utils.sanitize import sanitize_plain_text

CONTACT_REQUEST_EXPIRY_ENV = "CONTACT_REQUEST_EXPIRY_DAYS"
CONTACT_DECLINE_COOLDOWN_ENV = "CONTACT_DECLINE_COOLDOWN_DAYS"

DEFAULT_REQUEST_EXPIRY_DAYS = 14
DEFAULT_DECLINE_COOLDOWN_DAYS = 30
MAX_POLICY_DAYS = 365


def utcnow() -> datetime:
    """Naive UTC matching the repository's timestamp-without-time-zone columns."""
    return datetime.now(UTC).replace(tzinfo=None)


def _env_days(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw.strip())
    except (TypeError, ValueError):
        return default
    return min(MAX_POLICY_DAYS, max(1, value))


def request_expiry_days() -> int:
    return _env_days(CONTACT_REQUEST_EXPIRY_ENV, DEFAULT_REQUEST_EXPIRY_DAYS)


def decline_cooldown_days() -> int:
    return _env_days(CONTACT_DECLINE_COOLDOWN_ENV, DEFAULT_DECLINE_COOLDOWN_DAYS)


def request_expires_at(*, now: datetime | None = None) -> datetime:
    return (now or utcnow()) + timedelta(days=request_expiry_days())


def decline_cooldown_cutoff(*, now: datetime | None = None) -> datetime:
    return (now or utcnow()) - timedelta(days=decline_cooldown_days())


def contact_rail_enabled() -> bool:
    return os.getenv("CONTACT_RAIL_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def require_contact_rail(view):
    """Hide a user-facing route completely while the rollout flag is off."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        if not contact_rail_enabled():
            abort(404)
        return view(*args, **kwargs)

    return wrapped


def clean_plain_text(value, field: str, *, max_len: int, required: bool = True) -> str | None:
    """Validate bounded, sanitized plain text without silently truncating it."""
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


def parse_occurred_at(value) -> datetime:
    """Parse an optional ISO-8601 timestamp and normalize it to naive UTC."""
    if value is None:
        return utcnow()
    if not isinstance(value, str):
        raise ValueError("occurred_at must be an ISO-8601 string")
    raw = value.strip()
    if not raw:
        raise ValueError("occurred_at must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("occurred_at must be an ISO-8601 string") from exc
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


def add_audit_event(
    contact_request: ContactRequest,
    event_type: str,
    *,
    actor_user_id: int | None,
    metadata: dict | None = None,
    created_at: datetime | None = None,
) -> ContactAuditEvent:
    """Append one audit event to the current transaction."""
    event = ContactAuditEvent(
        contact_request_id=contact_request.id,
        actor_user_id=actor_user_id,
        event_type=event_type,
        event_metadata=dict(metadata or {}),
        created_at=created_at or utcnow(),
    )
    db.session.add(event)
    return event


def expire_if_due(contact_request: ContactRequest, *, now: datetime | None = None) -> bool:
    """Lazily expire one pending request and append its system audit event."""
    checked_at = now or utcnow()
    if (
        contact_request.status != "pending"
        or contact_request.expires_at is None
        or contact_request.expires_at > checked_at
    ):
        return False
    contact_request.status = "expired"
    add_audit_event(
        contact_request,
        "expired",
        actor_user_id=None,
        metadata={"expired_at": checked_at.isoformat()},
        created_at=checked_at,
    )
    return True


__all__ = [
    "add_audit_event",
    "clean_plain_text",
    "contact_rail_enabled",
    "decline_cooldown_cutoff",
    "decline_cooldown_days",
    "expire_if_due",
    "parse_occurred_at",
    "request_expires_at",
    "request_expiry_days",
    "require_contact_rail",
    "utcnow",
]
