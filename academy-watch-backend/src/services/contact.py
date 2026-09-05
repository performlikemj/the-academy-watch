"""Shared policy helpers for the feature-gated contact rail."""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta
from email.utils import parseaddr
from functools import wraps
from html import escape

from flask import abort, current_app
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import object_session
from src.models.contact import ContactAuditEvent, ContactRequest
from src.models.league import db
from src.services.club_registry import (
    active_program_manager_contacts,
    find_club_notice_target,
    get_club_program,
    program_has_active_manager,
    program_is_operational,
)
from src.utils.player_status import player_facing_status
from src.utils.sanitize import sanitize_plain_text

logger = logging.getLogger(__name__)

CONTACT_REQUEST_EXPIRY_ENV = "CONTACT_REQUEST_EXPIRY_DAYS"
CONTACT_DECLINE_COOLDOWN_ENV = "CONTACT_DECLINE_COOLDOWN_DAYS"

DEFAULT_REQUEST_EXPIRY_DAYS = 14
DEFAULT_DECLINE_COOLDOWN_DAYS = 30
MAX_POLICY_DAYS = 365
CLUB_CONSENT_TOKEN_MAX_AGE_SECONDS = 14 * 24 * 60 * 60
CLUB_CONSENT_TOKEN_SALT = "contact-club-consent"

CONTRACT_STATUSES = {"free_agent", "contracted", "unknown"}
CONTRACTED_PATHWAY_STATUSES = {"academy", "on_loan", "first_team", "sold", "left"}
FREE_AGENT_PATHWAY_STATUSES = {"released"}

ROUTING_DIRECT = "direct"
ROUTING_CLUB_INCLUDED = "club_included"
ROUTING_CLUB_NOTIFIED = "club_notified"

APPROACH_RULES_WARNING = (
    "Football approach rules may prohibit contacting a contracted player without their club's consent. "
    "Confirm that you already have the current club's permission before continuing."
)


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


def platform_contract_belief(player_api_id: int) -> tuple[str, str | None]:
    """Project the persisted player-facing status into the contract axis.

    The shared player-facing helper supplies the already-persisted journey /
    tracked-player status. This function does not run the classifier or infer
    from club names; it only projects that existing vocabulary onto the
    contract axis.
    """
    if player_api_id is None or player_api_id <= 0:
        return "unknown", None
    pathway_status = player_facing_status(player_api_id)

    normalized = (pathway_status or "").strip().lower()
    if normalized in FREE_AGENT_PATHWAY_STATUSES:
        return "free_agent", pathway_status
    if normalized in CONTRACTED_PATHWAY_STATUSES:
        return "contracted", pathway_status
    return "unknown", pathway_status


def has_status_contradiction(
    player_api_id: int,
    contract_status: str | None,
    *,
    platform_belief: str | None = None,
) -> bool:
    if platform_belief is None:
        platform_belief, _ = platform_contract_belief(player_api_id)
    return (
        contract_status in {"free_agent", "contracted"}
        and platform_belief in {"free_agent", "contracted"}
        and contract_status != platform_belief
    )


def effective_contract_status(contract_status: str | None) -> str:
    """Unknown and legacy-null attestations take the conservative club path."""
    return "free_agent" if contract_status == "free_agent" else "contracted"


def routing_mode_for_claim(claim, *, platform_belief: str | None = None) -> str:
    player_api_id = getattr(claim, "player_api_id", None)
    if getattr(claim, "local_player_id", None) is not None:
        from src.models.club_invitation import accepted_relationship, claim_matches
        from src.models.showcase import LocalPlayer
        from src.services.public_player_subject import resolve_public_adult_subject

        session = object_session(claim) or db.session
        local = session.get(LocalPlayer, claim.local_player_id)
        signed_id = local.api_player_id if local else None
        if (
            not signed_id
            or signed_id >= 0
            or not resolve_public_adult_subject(signed_id)
            or not claim_matches(session, claim, signed_id)
        ):
            return ROUTING_CLUB_NOTIFIED
        if claim.contract_status == "free_agent":
            return ROUTING_DIRECT
        return (
            ROUTING_CLUB_INCLUDED
            if accepted_relationship(session, claim, claim.club_program_id)
            else ROUTING_CLUB_NOTIFIED
        )
    if platform_belief is None:
        platform_belief, _ = platform_contract_belief(player_api_id)
    claim_status = getattr(claim, "contract_status", None)
    if platform_belief == "free_agent" and claim_status == "free_agent":
        return ROUTING_DIRECT
    if platform_belief == "unknown" and effective_contract_status(claim_status) == "free_agent":
        return ROUTING_DIRECT
    program_id = getattr(claim, "club_program_id", None)
    if program_id is not None and program_has_active_manager(program_id) and program_is_operational(program_id):
        return ROUTING_CLUB_INCLUDED
    return ROUTING_CLUB_NOTIFIED


def messaging_is_open(contact_request: ContactRequest) -> bool:
    session = object_session(contact_request)
    if session is not None:
        # Same row lock as relationship withdrawal; callers retain commit ownership.
        session.refresh(contact_request, with_for_update=True)
    if contact_request.status != "accepted":
        return False
    return contact_request.routing_mode != ROUTING_CLUB_INCLUDED or contact_request.club_consent_status == "granted"


def request_can_expire(contact_request: ContactRequest) -> bool:
    return contact_request.status == "pending" or (
        contact_request.status == "accepted"
        and contact_request.routing_mode == ROUTING_CLUB_INCLUDED
        and contact_request.club_consent_status == "pending"
    )


def _stored_email(value) -> str | None:
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not candidate or len(candidate) > 254 or "\n" in candidate or "\r" in candidate:
        return None
    _, parsed = parseaddr(candidate)
    return candidate if parsed == candidate and "@" in parsed else None


def _club_consent_serializer() -> URLSafeTimedSerializer:
    secret = current_app.config.get("SECRET_KEY") or os.getenv("SECRET_KEY") or "change-me"
    return URLSafeTimedSerializer(secret_key=secret, salt=CLUB_CONSENT_TOKEN_SALT)


def issue_club_consent_token(contact_request_id: str, action: str) -> str:
    if action not in {"grant", "decline"}:
        raise ValueError("action must be grant or decline")
    return _club_consent_serializer().dumps(
        {"contact_request_id": contact_request_id, "action": action},
    )


def load_club_consent_token(token: str) -> dict | None:
    try:
        payload = _club_consent_serializer().loads(token, max_age=CLUB_CONSENT_TOKEN_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(payload, dict):
        return None
    request_id = payload.get("contact_request_id")
    action = payload.get("action")
    if not isinstance(request_id, str) or action not in {"grant", "decline"}:
        return None
    return {"contact_request_id": request_id, "action": action}


def club_consent_action_links(contact_request_id: str) -> dict[str, str]:
    base = (os.getenv("PUBLIC_BASE_URL") or "https://theacademywatch.com").strip().rstrip("/")
    path = "/contact/club-consent/"
    return {
        action: f"{base}{path}{issue_club_consent_token(contact_request_id, action)}" for action in ("grant", "decline")
    }


def resolve_club_courtesy_target(
    *,
    program_id: int | None,
    club_name: str | None,
    player_api_id: int | None,
    for_update: bool = False,
) -> dict | None:
    """Resolve and optionally lock the exact/discovered courtesy target."""
    return find_club_notice_target(
        program_id=program_id,
        club_name=club_name,
        player_api_id=player_api_id,
        for_update=for_update,
    )


def send_club_courtesy_notice(
    contact_request: ContactRequest,
    *,
    target: dict | None = None,
) -> dict | None:
    """Best-effort courtesy notice using only a registry-row contact email.

    Delivery is deliberately outside request creation's transaction.  The
    caller appends ``club_notice_sent`` only when this returns success metadata.
    """
    claim = contact_request.claim
    # Never trust the pre-commit target supplied by older callers. Registry
    # contact data and the persisted current-club identity are refreshed here.
    target = resolve_club_courtesy_target(
        program_id=contact_request.club_program_id,
        club_name=getattr(claim, "current_club_name", None),
        player_api_id=contact_request.player_api_id,
    )
    if target is None:
        return None
    recipient = _stored_email(target.get("contact_email"))
    if recipient is None:
        return None

    club_name = sanitize_plain_text(str(target.get("name") or "Current club")).strip()[:180] or "Current club"
    player_reference = f"player profile {contact_request.player_api_id}"
    subject = f"Courtesy notice: approach request for {player_reference}"
    text = (
        f"Hello {club_name},\n\n"
        "A verified scout has requested an introduction to a player associated with your club/program "
        f"through The Academy Watch ({player_reference}). This neutral notice does not expose the private message.\n\n"
        "The Academy Watch"
    )
    html = (
        f"<p>Hello {escape(club_name)},</p>"
        "<p>A verified scout has requested an introduction to a player associated with your club/program "
        f"through The Academy Watch ({escape(player_reference)}).</p>"
        "<p>This neutral notice does not expose the private message.</p>"
        "<p>The Academy Watch</p>"
    )

    # Refresh recipient validity at the provider boundary. The final
    # operational check stays last so only the irreducible check->HTTP gap
    # remains.
    target = resolve_club_courtesy_target(
        program_id=contact_request.club_program_id,
        club_name=getattr(claim, "current_club_name", None),
        player_api_id=contact_request.player_api_id,
    )
    if target is None:
        return None
    recipient = _stored_email(target.get("contact_email"))
    delivery_program_id = target.get("id")
    if recipient is None:
        return None
    try:
        from src.services.email_service import email_service

        if not program_is_operational(delivery_program_id):
            return None
        result = email_service.send_email(
            to=recipient,
            subject=subject,
            html=html,
            text=text,
            tags=["club-contact-notice"],
            use_fallback=False,
            max_retries=0,
        )
    except Exception:
        logger.exception("Club courtesy notice failed for contact request %s", contact_request.id)
        return None
    if not getattr(result, "success", False):
        logger.warning("Club courtesy notice was not delivered for contact request %s", contact_request.id)
        return None
    return {
        "club_program_id": int(target["id"]),
        "provider": getattr(result, "provider", None),
        "message_id": getattr(result, "message_id", None),
    }


def _manager_recipient_snapshot(contacts: list[dict]) -> tuple[tuple[int, str], ...]:
    return tuple(
        sorted(
            (int(row["user_account_id"]), email)
            for row in contacts
            if row.get("user_account_id") is not None and (email := _stored_email(row.get("email")))
        )
    )


def send_club_consent_notice(contact_request: ContactRequest) -> bool:
    """Best-effort delivery of signed consent actions to active managers."""
    contacts = active_program_manager_contacts(contact_request.club_program_id)
    captured_recipients = _manager_recipient_snapshot(contacts)
    if not captured_recipients:
        logger.warning("No active manager email for contact request %s", contact_request.id)
        return False
    recipients = [email for _, email in captured_recipients]

    program = get_club_program(contact_request.club_program_id)
    program_name = sanitize_plain_text(str((program or {}).get("name") or "your program")).strip()[:180]
    from src.models.trust import ScoutVerification

    verification = (
        ScoutVerification.query.filter_by(user_account_id=contact_request.scout_user_id, status="approved")
        .order_by(ScoutVerification.submitted_at.desc(), ScoutVerification.id.desc())
        .first()
    )
    scout_name = sanitize_plain_text(
        str(
            getattr(verification, "full_name", None)
            or getattr(contact_request.scout, "display_name", None)
            or "Verified scout"
        )
    )
    organization = sanitize_plain_text(str(getattr(verification, "organization", None) or "")).strip() or None

    links = club_consent_action_links(contact_request.id)
    identity = f"{scout_name} ({organization})" if organization else scout_name
    subject = f"Club consent requested for player profile {contact_request.player_api_id}"
    text = (
        f"Hello {program_name},\n\n"
        f"{identity}, a verified scout, requested an introduction to player profile "
        f"{contact_request.player_api_id}. Messaging remains closed unless both the player and club consent.\n\n"
        f"Grant: {links['grant']}\nDecline: {links['decline']}\n\n"
        "These signed links expire after 14 days and stop working after either choice or request resolution.\n"
    )
    html = (
        f"<p>Hello {escape(program_name)},</p>"
        f"<p>{escape(identity)}, a verified scout, requested an introduction to player profile "
        f"{contact_request.player_api_id}. Messaging remains closed unless both the player and club consent.</p>"
        f'<p><a href="{escape(links["grant"])}">Review and grant</a> &nbsp; '
        f'<a href="{escape(links["decline"])}">Review and decline</a></p>'
        "<p>These signed links expire after 14 days and stop working after either choice or request resolution.</p>"
    )
    try:
        from src.services.email_service import email_service

        current_recipients = _manager_recipient_snapshot(
            active_program_manager_contacts(contact_request.club_program_id)
        )
        if current_recipients != captured_recipients or not program_is_operational(contact_request.club_program_id):
            return False
        result = email_service.send_email(
            to=recipients,
            subject=subject,
            html=html,
            text=text,
            tags=["club-consent-request"],
            use_fallback=False,
            max_retries=0,
        )
    except Exception:
        logger.exception("Club consent notice failed for contact request %s", contact_request.id)
        return False
    if not getattr(result, "success", False):
        logger.warning("Club consent notice was not delivered for contact request %s", contact_request.id)
        return False
    return True


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
    """Expire a request still waiting for either required acceptance gate."""
    checked_at = now or utcnow()
    if (
        not request_can_expire(contact_request)
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
    "APPROACH_RULES_WARNING",
    "CONTRACT_STATUSES",
    "CLUB_CONSENT_TOKEN_MAX_AGE_SECONDS",
    "ROUTING_CLUB_INCLUDED",
    "ROUTING_CLUB_NOTIFIED",
    "ROUTING_DIRECT",
    "add_audit_event",
    "clean_plain_text",
    "contact_rail_enabled",
    "club_consent_action_links",
    "decline_cooldown_cutoff",
    "decline_cooldown_days",
    "expire_if_due",
    "effective_contract_status",
    "has_status_contradiction",
    "issue_club_consent_token",
    "load_club_consent_token",
    "messaging_is_open",
    "parse_occurred_at",
    "platform_contract_belief",
    "request_can_expire",
    "request_expires_at",
    "request_expiry_days",
    "require_contact_rail",
    "resolve_club_courtesy_target",
    "routing_mode_for_claim",
    "send_club_courtesy_notice",
    "send_club_consent_notice",
    "utcnow",
]
