"""Transactional intents and a bounded, at-least-once email dispatcher.

Later lanes register their template in the worker's imported application code.
Each template MUST recheck authoritative entity state and recipient access.
Payloads carry only integer/UUID IDs, versions and declared enum codes; render from current state, never
persist email addresses, child names, message bodies, credentials or links.
The worker owns commits. enqueue never commits the caller's transaction.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from src.models.league import UserAccount, db
from src.models.p2_foundation import NotificationOutbox
from src.services.admin_audit import bounded_meta
from src.services.email_service import email_service
from src.services.p2_foundation import foundation_enabled

MAX_ATTEMPTS = 5
LEASE_SECONDS = 300


@dataclass(frozen=True)
class NotificationTemplate:
    eligible: Callable
    render: Callable  # (row, current_user) -> {subject, html, text}; no child PII
    payload_enums: dict
    defer: Callable | None = None


_templates: dict[str, NotificationTemplate] = {}


def register_template(name, *, eligible, render, payload_enums=None, defer=None):
    """Register trusted application code, never request-supplied callbacks."""
    _code(name)
    if not callable(eligible) or not callable(render) or (defer is not None and not callable(defer)):
        raise ValueError("eligibility and render callbacks are required")
    enums = payload_enums or {}
    if not isinstance(enums, dict) or any(key not in {"state", "decision", "version"} for key in enums):
        raise ValueError("payload enum keys must be state, decision or version")
    normalized = {}
    for key, values in enums.items():
        if not isinstance(values, (set, frozenset, list, tuple)) or not values:
            raise ValueError("payload enums must be nonempty collections")
        for value in values:
            if not isinstance(value, str):
                raise ValueError("payload enums must contain machine code strings")
            bounded_meta({key: value})
        normalized[key] = frozenset(values)
    _templates[name] = NotificationTemplate(eligible, render, normalized, defer)


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
    payload = _validate_payload(template, payload)
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


def _validate_payload(template, payload):
    payload = bounded_meta(payload)
    handler = _templates.get(template)
    for key, value in payload.items():
        if key.endswith("_id"):
            if isinstance(value, bool) or not isinstance(value, (int, str)):
                raise ValueError("payload IDs must be integers or UUIDs")
            if isinstance(value, str):
                try:
                    if str(UUID(value)) != value.lower():
                        raise ValueError()
                except ValueError:
                    raise ValueError("payload IDs must be integers or UUIDs") from None
        elif key not in {"state", "version", "decision"}:
            raise ValueError("notification payload keys must be IDs, state, version or decision")
        elif isinstance(value, str):
            if handler is None or value not in handler.payload_enums.get(key, ()):
                raise ValueError("payload strings require a registered template enum")
        elif isinstance(value, bool) or not isinstance(value, int) or key != "version":
            raise ValueError("non-ID payloads must be an integer version or a registered enum")
    return payload


def _referenced_account_unavailable(row):
    if row.entity_type != "user_account":
        return False
    try:
        account_id = int(row.entity_id)
    except ValueError:
        return True
    account = db.session.get(UserAccount, account_id, populate_existing=True)
    return account is None or account.is_tombstone


def _claim(now):
    due = sa.or_(
        sa.and_(NotificationOutbox.status.in_(("pending", "retry")), NotificationOutbox.next_attempt_at <= now),
        sa.and_(NotificationOutbox.status == "sending", NotificationOutbox.lease_expires_at <= now),
    )
    row = db.session.execute(
        sa.select(NotificationOutbox)
        .where(due)
        .order_by(NotificationOutbox.next_attempt_at, NotificationOutbox.id)
        .limit(1)
        .with_for_update(skip_locked=True)
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if row is None:
        db.session.rollback()
        return None
    if row.attempts >= MAX_ATTEMPTS:
        row.status, row.last_error = "failed", "lease_expired"
        row.lease_token = row.lease_expires_at = None
        db.session.commit()
        return (None, None)
    row.attempts += 1
    row.status, row.lease_token = "sending", str(uuid4())
    row.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
    claim = (row.id, row.lease_token)
    db.session.commit()
    return claim


def _prepare(row_id, token):
    """SQL callbacks run inside a savepoint; no locks/transaction escape to send."""
    try:
        with db.session.begin_nested():
            row = db.session.get(NotificationOutbox, row_id, populate_existing=True)
            if row is None or row.status != "sending" or row.lease_token != token:
                return None, "cancelled", "lease_lost"
            user = db.session.get(UserAccount, row.recipient_user_id, populate_existing=True)
            if user is None or user.is_tombstone or not user.email or _referenced_account_unavailable(row):
                return None, "cancelled", "recipient_or_subject_unavailable"
            handler = _templates.get(row.template)
            if handler is None:
                return None, "retry", "template_unavailable"
            _validate_payload(row.template, row.payload)
            if not handler.eligible(row, user):
                if handler.defer is not None and handler.defer(row, user):
                    return None, "deferred", "temporarily_unavailable"
                return None, "cancelled", "ineligible"
            message = handler.render(row, user)
            if set(message) != {"subject", "html", "text"} or not all(isinstance(v, str) for v in message.values()):
                raise ValueError("invalid template output")
            return dict(to=user.email, **message, max_retries=0), None, None
    except Exception:
        return None, "retry", "delivery_failed"
    finally:
        # Close callback reads and any locks requested by trusted template code.
        db.session.rollback()


def _finalize(row_id, token, status, error, now, result=None):
    row = db.session.execute(
        sa.select(NotificationOutbox)
        .where(
            NotificationOutbox.id == row_id,
            NotificationOutbox.status == "sending",
            NotificationOutbox.lease_token == token,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if row is None:
        db.session.rollback()
        return None  # erased intent or a newer worker owns its reclaimed lease
    user = db.session.get(UserAccount, row.recipient_user_id, populate_existing=True)
    if user is None or user.is_tombstone or _referenced_account_unavailable(row):
        status, error = "cancelled", "recipient_or_subject_unavailable"
    deferred = status == "deferred"
    if deferred:
        # A publication pause consumes no delivery attempt, even across many worker runs.
        row.attempts = max(0, row.attempts - 1)
        status = "retry"
        row.next_attempt_at = now + timedelta(seconds=LEASE_SECONDS)
    elif status == "retry":
        status = "failed" if row.attempts >= MAX_ATTEMPTS else "retry"
        row.next_attempt_at = now + timedelta(seconds=min(60 * 2 ** (row.attempts - 1), 3600))
    row.status, row.last_error = status, error
    row.lease_token = row.lease_expires_at = None
    if status == "sent":
        row.sent_at = now
        row.provider = (result.provider or "")[:40]
        row.provider_message_id = (result.message_id or "")[:254]
    db.session.commit()
    return "deferred" if deferred and status == "retry" else status


def dispatch_due(*, limit=100, now=None, send=None):
    """Claim/commit → prepare → send without DB locks → finalize/recheck.

    Sending leases expire after five minutes; a reclaimed lease has a new token
    so late workers cannot overwrite it. At-least-once: a crash/lease expiry
    after provider success before finalize can duplicate delivery. Erasure may
    race an already-started provider call; finalization never resurrects data.
    Unknown templates retry, false eligibility cancels unless trusted defer code
    confirms a temporary pause; deferral preserves attempts. Per-row errors continue.
    Database infrastructure failure in claiming/finalizing leaves a recoverable
    lease; a template's SQL error cannot abort the batch or reset its attempt.
    """
    summary = dict(sent=0, retry=0, deferred=0, cancelled=0, failed=0, errors=0, disabled=not foundation_enabled())
    if summary["disabled"]:
        return summary
    if isinstance(limit, bool) or not isinstance(limit, int) or not 0 <= limit <= 1000:
        raise ValueError("limit must be between 0 and 1000")
    send = send or email_service.send_email
    for _ in range(limit):
        run_now = now or datetime.now(UTC)
        try:
            claim = _claim(run_now)
        except Exception:
            db.session.rollback()
            summary["errors"] += 1
            continue
        if claim is None:
            break
        row_id, token = claim
        if row_id is None:
            summary["failed"] += 1
            continue
        message, status, error = _prepare(row_id, token)
        result = None
        if message is not None:
            try:
                result = send(**message)
                if not result.success:
                    raise RuntimeError("provider failed")
                status, error = "sent", None
            except Exception:
                status, error = "retry", "delivery_failed"
            finally:
                db.session.rollback()  # finalize in a fresh transaction even if send touched SQL
        try:
            finalized = _finalize(row_id, token, status, error, run_now, result)
            if finalized is not None:
                summary[finalized] += 1
        except Exception:
            db.session.rollback()
            # Persisting fails only for this row; its committed lease recovers.
            summary["errors"] += 1
            continue
    return summary
