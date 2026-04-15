"""Auth blueprint for authentication endpoints.

This blueprint handles:
- Login code request and verification
- User profile retrieval
- Display name management
- Auth status (admin only)
"""

import json
import logging
import os
import re
import secrets
import string
import uuid
from datetime import UTC, datetime, timedelta

from flask import Blueprint, g, jsonify, render_template, request
from src.auth import (
    ALLOWED_ADMIN_IPS,
    _ensure_user_account,
    _is_production,
    _normalize_display_name,
    _safe_error_payload,
    _user_serializer,
    get_client_ip,
    issue_user_token,
    require_api_key,
    require_user_auth,
)
from src.extensions import limiter
from src.models.league import (
    EmailToken,
    UserAccount,
    _as_utc,
    db,
)
from src.services.email_service import email_service

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _generate_otp_code(length: int = 11) -> str:
    """Generate a cryptographically-strong login code.

    Uses upper/lowercase letters, digits, and safe special symbols.
    """
    alphabet = string.ascii_letters + string.digits + "!@#$%^*-_"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _create_email_token(email: str, purpose: str, metadata: dict | None = None, ttl_minutes: int = 60) -> EmailToken:
    """Create an email token for verification purposes."""
    token = str(uuid.uuid4())
    expires_at = datetime.now(UTC) + timedelta(minutes=ttl_minutes)
    row = EmailToken(
        token=token, email=email, purpose=purpose, expires_at=expires_at, metadata_json=json.dumps(metadata or {})
    )
    db.session.add(row)
    db.session.flush()
    logger.info(
        "Created email token id=%s purpose=%s email=%s expires_at=%s",
        row.id,
        purpose,
        email,
        expires_at.isoformat(),
    )
    return row


def _send_login_code(email: str, code: str):
    """Send login code via email service (Mailgun/SMTP).

    In development, also prints the code to terminal for testing.
    """
    expires_minutes = 5
    subject = "Your Login Code"

    html_body = render_template(
        "login_code_email.html",
        email=email,
        code=code,
        expires_in=expires_minutes,
    )
    text_body = (
        f"Your The Academy Watch login code is {code}. "
        f"It expires in {expires_minutes} minutes. "
        "If you did not request it, you can ignore this email."
    )

    # Send via email service if configured
    if email_service.is_configured():
        try:
            result = email_service.send_email(
                to=email,
                subject=subject,
                html=html_body,
                text=text_body,
                tags=["login_code"],
            )
            if result.success:
                logger.info("Login code sent to %s via %s", email, result.provider)
            else:
                logger.warning("Failed to send login code to %s: %s", email, result.error)
        except Exception:
            logger.exception("Failed to send login code to %s", email)

    # In development, also print to terminal for testing
    if not _is_production():
        msg = f"[DEV] Login code for {email}: {code} (expires in 5 minutes)"
        try:
            print(msg)
        except Exception:
            pass
        logger.info(msg)


def _user_rate_limit_key() -> str | None:
    """Rate limit key based on user email or IP."""
    return getattr(g, "user_email", None) or (request.remote_addr or "anon")


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------


@auth_bp.route("/auth/request-code", methods=["POST"])
@limiter.limit("5 per minute", error_message="Too many login code requests. Please wait and try again.")
def request_login_code():
    """Request a login code to be sent to the provided email."""
    email = None
    try:
        data = request.get_json() or {}
        email = (data.get("email") or "").strip().lower()
        if not email:
            logger.warning("Login code request missing email from %s", get_client_ip())
            return jsonify({"error": "email is required"}), 400
        client_ip = get_client_ip()
        logger.info("Login code requested for %s from %s", email, client_ip)
        code = _generate_otp_code(11)
        # 5 minutes TTL
        tok = _create_email_token(email=email, purpose="login", metadata={"kind": "otp"}, ttl_minutes=5)
        # Overwrite token string with numeric code so user types digits
        tok.token = code
        db.session.add(tok)
        db.session.commit()

        # Deliver or print locally depending on environment
        _send_login_code(email, code)
        logger.info("Login code issued for %s from %s (token_id=%s)", email, client_ip, tok.id)
        return jsonify({"message": "Login code sent"})
    except Exception as e:
        logger.exception("Failed to issue login code for email=%s", email)
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify(_safe_error_payload(e, "An unexpected error occurred. Please try again later.")), 500


@auth_bp.route("/auth/verify-code", methods=["POST"])
@limiter.limit("10 per minute", error_message="Too many verification attempts. Please wait a moment and try again.")
def verify_login_code():
    """Verify a login code and issue an auth token."""
    email = None
    try:
        data = request.get_json() or {}
        email = (data.get("email") or "").strip().lower()
        code = (data.get("code") or "").strip()
        if not email or not code:
            logger.warning(
                "Verify-login missing fields email_present=%s code_present=%s from %s",
                bool(email),
                bool(code),
                get_client_ip(),
            )
            return jsonify({"error": "email and code are required"}), 400
        client_ip = get_client_ip()
        logger.info("Verifying login code for %s from %s", email, client_ip)
        row = EmailToken.query.filter_by(email=email, token=code, purpose="login").first()
        if not row or not row.is_valid():
            logger.warning("Invalid/expired login code for %s from %s", email, client_ip)
            return jsonify({"error": "invalid or expired code"}), 400
        # Mark used and issue an auth token
        row.used_at = datetime.now(UTC)
        is_new_user = not UserAccount.query.filter_by(email=email).first()
        user = _ensure_user_account(email)
        if user:
            user.last_login_at = datetime.now(UTC)
        db.session.commit()
        if is_new_user:
            from src.services.admin_notify_service import notify_new_user

            notify_new_user(email, user.display_name if user else None)
        # Determine role by env allowlist
        allowed = [x.strip().lower() for x in (os.getenv("ADMIN_EMAILS") or "").split(",") if x.strip()]
        role = "admin" if email in allowed else "user"
        logger.info("Login verified for %s from %s role=%s", email, client_ip, role)
        out = issue_user_token(email, role=role)
        return jsonify(
            {
                "message": "Logged in",
                "role": role,
                "display_name": user.display_name if user else None,
                "display_name_confirmed": bool(user.display_name_confirmed) if user else False,
                **out,
            }
        )
    except Exception as e:
        logger.exception("Failed to verify login code for email=%s", email)
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify(_safe_error_payload(e, "Unable to verify login code right now. Please try again later.")), 500


@auth_bp.route("/auth/me", methods=["GET"])
@require_user_auth
def auth_me():
    """Get current authenticated user's profile."""
    try:
        auth = request.headers.get("Authorization", "")
        token = auth.split(" ", 1)[1] if auth.startswith("Bearer ") else None
        role = "user"
        if token:
            try:
                data = _user_serializer().loads(token, max_age=60 * 60 * 24 * 30)
                role = (data or {}).get("role") or "user"
            except Exception:
                pass
        email = getattr(g, "user_email", None)
        user = UserAccount.query.filter_by(email=email).first() if email else None
        return jsonify(
            {
                "email": email,
                "role": role,
                "user_id": user.id if user else None,
                "display_name": user.display_name if user else None,
                "display_name_confirmed": bool(user.display_name_confirmed) if user else False,
                "is_journalist": bool(user.is_journalist) if user else False,
                "is_curator": bool(user.is_curator) if user else False,
            }
        )
    except Exception as e:
        return jsonify(_safe_error_payload(e, "An unexpected error occurred. Please try again later.")), 500


@auth_bp.route("/auth/display-name", methods=["POST"])
@require_user_auth
@limiter.limit("3 per minute", key_func=_user_rate_limit_key)
def update_display_name():
    """Update the authenticated user's display name."""
    try:
        payload = request.get_json() or {}
        raw = (payload.get("display_name") or "").strip()
        normalized = _normalize_display_name(raw)
        if not normalized or len(normalized) < 3:
            return jsonify({"error": "Display name must be at least 3 characters"}), 400
        if not re.match(r"^[A-Za-z0-9]", normalized):
            return jsonify({"error": "Display name must start with a letter or number"}), 400
        email = getattr(g, "user_email", None)
        if not email:
            return jsonify({"error": "auth context missing email"}), 401
        user = UserAccount.query.filter_by(email=email).first()
        if not user:
            user = _ensure_user_account(email)
        lower = normalized.lower()
        now = datetime.now(UTC)
        cooldown = timedelta(hours=24)
        if user.display_name_lower != lower:
            last_change = (
                _as_utc(user.last_display_name_change_at) or _as_utc(user.updated_at) or _as_utc(user.created_at)
            )
            enforce_cooldown = bool(user.display_name_confirmed)
            if enforce_cooldown and last_change and (now - last_change) < cooldown:
                remaining = cooldown - (now - last_change)
                hours = int(remaining.total_seconds() // 3600)
                minutes = int((remaining.total_seconds() % 3600) // 60)
                return jsonify(
                    {
                        "error": "Display name recently updated. Try again later.",
                        "retry_after_seconds": int(remaining.total_seconds()),
                        "retry_after_human": f"{hours}h {minutes}m",
                    }
                ), 429
            conflict = UserAccount.query.filter(
                UserAccount.display_name_lower == lower, UserAccount.id != user.id
            ).first()
            if conflict:
                return jsonify({"error": "Display name already in use"}), 409
            user.display_name = normalized
            user.display_name_lower = lower
            user.display_name_confirmed = True
            user.last_display_name_change_at = now
            user.updated_at = now
        else:
            if not user.display_name_confirmed:
                user.display_name_confirmed = True
        db.session.commit()
        return jsonify(
            {
                "message": "Display name updated",
                "display_name": user.display_name,
                "display_name_confirmed": bool(user.display_name_confirmed),
            }
        )
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify(_safe_error_payload(e, "An unexpected error occurred. Please try again later.")), 500


@auth_bp.route("/auth/status", methods=["GET"])
@require_api_key
def auth_status():
    """Get API authentication status and instructions. Requires admin authentication."""
    api_key_configured = bool(os.getenv("ADMIN_API_KEY"))
    ip_whitelist_configured = bool(ALLOWED_ADMIN_IPS)
    client_ip = get_client_ip()

    return jsonify(
        {
            "api_key_configured": api_key_configured,
            "ip_whitelist_configured": ip_whitelist_configured,
            "client_ip": client_ip,
            "ip_whitelisted": not ip_whitelist_configured or client_ip in ALLOWED_ADMIN_IPS,
            "message": "API key authentication is configured"
            if api_key_configured
            else "API key authentication not configured",
            "security_status": {
                "api_key": "configured" if api_key_configured else "missing",
                "ip_whitelist": f"{len(ALLOWED_ADMIN_IPS)} IPs allowed" if ip_whitelist_configured else "disabled",
                "production_ready": api_key_configured,
            },
            "secured_endpoints": [
                "POST /api/players",
                "POST /api/loans",
                "POST /api/loans/bulk-upload",
                "PUT /api/loans/<id>/performance",
                "POST /api/loans/<id>/terminate",
                "POST /api/sync-leagues",
                "POST /api/sync-teams",
                "POST /api/sync-loans",
                "POST /api/detect-loan-candidates",
                "GET /api/loan-candidates/review",
            ],
        }
    )
