"""Transactional intents and a bounded, at-least-once email dispatcher.

Later lanes register their template in the worker's imported application code.
Each template MUST recheck authoritative entity state and recipient access.
Payloads carry only IDs/booleans/machine codes; render from current state, never
persist email addresses, child names, message bodies, credentials or links.
The worker owns commits. enqueue never commits the caller's transaction.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from src.models.league import UserAccount, db
from src.models.p2_foundation import NotificationOutbox
from src.services.admin_audit import bounded_meta
from src.services.email_service import email_service
from src.services.p2_foundation import foundation_enabled

MAX_ATTEMPTS = 5


@dataclass(frozen=True)
class NotificationTemplate:
    eligible: Callable
    render: Callable  # (row, current_user) -> {subject, html, text}; no child PII


_templates: dict[str, NotificationTemplate] = {}


def register_template(name, *, eligible, render):
    """Register trusted application code, never request-supplied callbacks."""
    _code(name)
    if not callable(eligible) or not callable(render):
        raise ValueError("eligibility and render callbacks are required")
    _templates[name] = NotificationTemplate(eligible, render)


def _code(value, max_length=80):
    if not isinstance(value, str) or len(value) > max_length or not re.fullmatch(r"[a-zA-Z0-9_:-]+", value):
        raise ValueError("outbox identifiers must be opaque IDs or machine codes")
    return value


def enqueue(*, dedupe_key, recipient_user_id, event_type, entity_type, entity_id, template, payload=None):
    """Return existing/new NotificationOutbox in the caller's transaction.

    Dedupe keys are globally unique, opaque event-version/recipient keys. Reuse
    for a different intent is rejected. Disabled rollout produces no intent.
    """
    if not foundation_enabled():
        return None
    payload = bounded_meta(payload)
    if any(not (key.endswith("_id") or key in {"state", "version", "decision"}) for key in payload):
        raise ValueError("notification payload keys must be IDs, state, version or decision")
    values = dict(
        dedupe_key=_code(dedupe_key, 200),
        recipient_user_id=recipient_user_id,
        event_type=_code(event_type),
        entity_type=_code(entity_type),
        entity_id=_code(str(entity_id)),
        template=_code(template),
        payload=bounded_meta(payload),
    )
    if isinstance(recipient_user_id, bool) or not isinstance(recipient_user_id, int) or recipient_user_id <= 0:
        raise ValueError("recipient_user_id must be a positive account ID")
    row = NotificationOutbox.query.filter_by(dedupe_key=dedupe_key).first()
    if row is None:
        try:
            with db.session.begin_nested():
                row = NotificationOutbox(**values)
                db.session.add(row)
                db.session.flush()
        except IntegrityError:
            row = NotificationOutbox.query.filter_by(dedupe_key=dedupe_key).first()
            if row is None:
                raise
    if any(getattr(row, key) != value for key, value in values.items()):
        raise ValueError("dedupe key already belongs to another intent")
    return row


def dispatch_due(*, limit=100, now=None, send=None):
    """Worker-only: lock/revalidate/send/commit one row at a time.

    PostgreSQL SKIP LOCKED prevents concurrent workers sending the same intent.
    Locks stay held across the provider call (and account erasure waits on the
    recipient lock). A crash after send before commit can duplicate delivery.
    Unknown templates cancel; eligibility false cancels; exceptions retry.
    No provider exception/body is stored because it may contain personal data.
    """
    summary = dict(sent=0, retry=0, cancelled=0, failed=0, disabled=not foundation_enabled())
    if summary["disabled"]:
        return summary
    if isinstance(limit, bool) or not isinstance(limit, int) or not 0 <= limit <= 1000:
        raise ValueError("limit must be between 0 and 1000")
    now = now or datetime.now(UTC)
    send = send or email_service.send_email
    for _ in range(limit):
        try:
            candidate = db.session.execute(
                sa.select(NotificationOutbox.id, NotificationOutbox.recipient_user_id)
                .where(
                    NotificationOutbox.status.in_(("pending", "retry")),
                    NotificationOutbox.next_attempt_at <= now,
                )
                .order_by(NotificationOutbox.next_attempt_at, NotificationOutbox.id)
                .limit(1)
            ).first()
            if candidate is None:
                db.session.rollback()
                break
            user = db.session.execute(
                sa.select(UserAccount)
                .where(UserAccount.id == candidate.recipient_user_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            ).scalar_one_or_none()
            # Match account erasure order: recipient first, then intent.
            row = db.session.execute(
                sa.select(NotificationOutbox)
                .where(
                    NotificationOutbox.id == candidate.id,
                    NotificationOutbox.status.in_(("pending", "retry")),
                    NotificationOutbox.next_attempt_at <= now,
                )
                .with_for_update(skip_locked=True)
                .execution_options(populate_existing=True)
            ).scalar_one_or_none()
            if row is None:
                db.session.rollback()
                continue
            handler = _templates.get(row.template)
            if user is None or user.is_tombstone or not user.email or handler is None:
                row.status, row.last_error = "cancelled", "recipient_or_template_unavailable"
            else:
                row.attempts += 1
                try:
                    if not handler.eligible(row, user):
                        row.status, row.last_error = "cancelled", "ineligible"
                    else:
                        message = handler.render(row, user)
                        if set(message) != {"subject", "html", "text"} or not all(
                            isinstance(v, str) for v in message.values()
                        ):
                            raise ValueError("invalid template output")
                        result = send(to=user.email, **message, max_retries=0)
                        if not result.success:
                            raise RuntimeError("provider failed")
                        row.status, row.sent_at, row.last_error = "sent", now, None
                        row.provider = (result.provider or "")[:40]
                        row.provider_message_id = (result.message_id or "")[:254]
                except Exception:
                    row.status = "failed" if row.attempts >= MAX_ATTEMPTS else "retry"
                    row.last_error = "delivery_failed"
                    row.next_attempt_at = now + timedelta(seconds=min(60 * 2 ** (row.attempts - 1), 3600))
            summary[row.status] += 1
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
    return summary
