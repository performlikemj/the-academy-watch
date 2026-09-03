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
    _review_account_config,
    _review_login_matches,
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
    Team,
    UserAccount,
    _as_utc,
    db,
)
from src.models.showcase import PlayerProfileClaim
from src.models.tracked_player import TrackedPlayer
from src.models.trust import ScoutVerification
from src.services.account_roles import derive_account_role
from src.services.email_service import email_service
from src.services.scout_entitlements import scout_entitlements
from src.services.trust import is_verified_scout

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__)

DEMO_PLAYER_API_ID = 2_147_160_001
DEMO_TEAM_API_ID = 2_147_160_000
DEMO_TEAM_SEASON = 2026
DEMO_PLAYER_NAME = "Demo Player (App Review)"
DEMO_PLAYER_BIRTH_DATE = "2000-01-01"


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
        submitted_code = data.get("code") or ""
        code = submitted_code.strip()
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
        # Static review credentials require a byte-exact submitted code. Keep
        # the existing whitespace-tolerant normalization for one-time codes.
        is_review_login = _review_login_matches(email, submitted_code)
        if not is_review_login:
            row = EmailToken.query.filter_by(email=email, token=code, purpose="login").first()
            if not row or not row.is_valid():
                logger.warning("Invalid/expired login code for %s from %s", email, client_ip)
                return jsonify({"error": "invalid or expired code"}), 400
            # Mark one-time email codes used. The env-gated review code is
            # intentionally reusable until operators revoke either env var.
            row.used_at = datetime.now(UTC)
        is_new_user = not UserAccount.query.filter_by(email=email).first()
        user = _ensure_user_account(email)
        if user:
            user.last_login_at = datetime.now(UTC)
        db.session.commit()
        if is_review_login:
            logger.warning(
                "audit_event=review_login_used email=%s user_id=%s ip=%s",
                email,
                user.id if user else None,
                client_ip,
            )
        if is_new_user:
            from src.services.admin_notify_service import notify_new_user

            notify_new_user(email, user.display_name if user else None)
        # Determine role by env allowlist
        allowed = [x.strip().lower() for x in (os.getenv("ADMIN_EMAILS") or "").split(",") if x.strip()]
        # A reusable App Review credential must never mint an elevated bearer,
        # even if deployment allowlists accidentally overlap.
        role = "user" if is_review_login else ("admin" if email in allowed else "user")
        logger.info("Login verified for %s from %s role=%s", email, client_ip, role)
        out = issue_user_token(email, role=role)
        return jsonify(
            {
                "message": "Logged in",
                "role": role,
                "account_role": derive_account_role(user),
                "is_verified_scout": is_verified_scout(user),
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


@auth_bp.route("/admin/review-accounts/seed", methods=["POST"])
@require_api_key
def seed_review_accounts():
    """Idempotently provision synthetic scout and player App Review states."""
    try:
        scout_config = _review_account_config("scout")
        player_config = _review_account_config("player")
        if scout_config is None or player_config is None:
            return jsonify({"error": "Both scout and player review accounts must be configured"}), 503

        actor = getattr(g, "user_email", None) or "admin"
        now = datetime.now(UTC)
        result = {"created": [], "found": []}

        def _record(resource: str, created: bool) -> None:
            result["created" if created else "found"].append(resource)

        scout = UserAccount.query.filter_by(email=scout_config["email"]).first()
        scout_created = scout is None
        scout = _ensure_user_account(scout_config["email"])
        _record("scout_account", scout_created)

        verification = (
            ScoutVerification.query.filter_by(user_account_id=scout.id, status="approved")
            .order_by(ScoutVerification.id.asc())
            .first()
        )
        if verification is None:
            verification = (
                ScoutVerification.query.filter_by(user_account_id=scout.id, status="pending")
                .order_by(ScoutVerification.id.asc())
                .first()
            )
        if verification is None:
            verification = (
                ScoutVerification.query.filter_by(user_account_id=scout.id)
                .order_by(ScoutVerification.id.desc())
                .first()
            )
        verification_created = verification is None
        if verification is None:
            verification = ScoutVerification(
                user_account_id=scout.id,
                full_name="App Review Scout",
                organization="The Academy Watch Demo",
                role_title="Scout",
                statement="Synthetic App Review account for demonstrating verified scout access.",
                evidence_urls=[],
            )
            db.session.add(verification)
        verification.status = "approved"
        verification.reviewed_at = now
        verification.reviewed_by = actor
        verification.review_notes = "Synthetic App Review seed; no real-person verification evidence."
        verification.revocation_reason = None
        _record("scout_verification", verification_created)

        player_account = UserAccount.query.filter_by(email=player_config["email"]).first()
        player_account_created = player_account is None
        player_account = _ensure_user_account(player_config["email"])
        _record("player_account", player_account_created)

        team = Team.query.filter_by(team_id=DEMO_TEAM_API_ID, season=DEMO_TEAM_SEASON).first()
        team_created = team is None
        if team is None:
            team = Team(
                team_id=DEMO_TEAM_API_ID,
                name="App Review Demo Academy",
                country="Demo",
                season=DEMO_TEAM_SEASON,
                is_active=True,
                is_tracked=False,
                newsletters_active=False,
            )
            db.session.add(team)
            db.session.flush()
        elif team.name != "App Review Demo Academy" or team.country != "Demo":
            db.session.rollback()
            return jsonify({"error": "Reserved App Review demo team identifier is already in use"}), 409
        _record("demo_team", team_created)

        tracked_rows = TrackedPlayer.query.filter_by(player_api_id=DEMO_PLAYER_API_ID).all()
        if any(row.data_source != "demo" for row in tracked_rows):
            db.session.rollback()
            return jsonify({"error": "Reserved App Review demo player identifier is already in use"}), 409
        tracked = next((row for row in tracked_rows if row.team_id == team.id), None)
        tracked_created = tracked is None
        if tracked is None:
            tracked = TrackedPlayer(player_api_id=DEMO_PLAYER_API_ID, team_id=team.id)
            db.session.add(tracked)
        tracked.player_name = DEMO_PLAYER_NAME
        tracked.birth_date = DEMO_PLAYER_BIRTH_DATE
        tracked.age = None
        tracked.position = "Midfielder"
        tracked.nationality = "Demo"
        tracked.status = "first_team"
        tracked.data_source = "demo"
        tracked.data_depth = "profile_only"
        tracked.is_active = True
        tracked.notes = "Synthetic App Review fixture; never replace with real-person data."
        _record("demo_player", tracked_created)

        claim = PlayerProfileClaim.query.filter_by(
            player_api_id=DEMO_PLAYER_API_ID,
            user_account_id=player_account.id,
        ).first()
        claim_created = claim is None
        if claim is None:
            claim = PlayerProfileClaim(
                player_api_id=DEMO_PLAYER_API_ID,
                user_account_id=player_account.id,
                relationship_type="player",
            )
            db.session.add(claim)
        claim.relationship_type = "player"
        claim.status = "approved"
        claim.contract_status = "free_agent"
        claim.current_club_name = None
        claim.club_program_id = None
        claim.status_contradiction = False
        claim.verification_status = "unverified"
        claim.verification_method = None
        claim.verification_note = "Synthetic App Review seed; not a real-person identity claim."
        claim.reviewed_at = now
        claim.reviewed_by = actor
        _record("player_claim", claim_created)

        db.session.commit()
        return jsonify(
            {
                **result,
                "scout": {"email": scout.email, "verification_status": verification.status},
                "player": {
                    "email": player_account.email,
                    "claim_status": claim.status,
                    "player_api_id": DEMO_PLAYER_API_ID,
                },
                "demo_player": {
                    "name": tracked.player_name,
                    "data_source": tracked.data_source,
                    "birth_date": tracked.birth_date,
                },
            }
        )
    except Exception as exc:
        db.session.rollback()
        logger.exception("Failed to seed App Review accounts")
        return jsonify(_safe_error_payload(exc, "Failed to seed App Review accounts")), 500


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
        entitlements = scout_entitlements(user, role=role)
        return jsonify(
            {
                "email": email,
                "role": role,
                "account_role": derive_account_role(user),
                "user_id": user.id if user else None,
                "display_name": user.display_name if user else None,
                "display_name_confirmed": bool(user.display_name_confirmed) if user else False,
                "is_journalist": bool(user.is_journalist) if user else False,
                "is_curator": bool(user.is_curator) if user else False,
                "is_verified_scout": is_verified_scout(user),
                "scout_tier": entitlements["tier"],
                "scout_pro": {
                    "enabled": entitlements["billing_enabled"],
                    "tier": entitlements["tier"],
                    "features": entitlements["features"],
                },
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
