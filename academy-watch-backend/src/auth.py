"""Authentication decorators and utilities.

This module contains shared authentication code used across blueprints:
- require_api_key: Admin endpoint protection (dual-factor: Bearer token + API key)
- require_user_auth: User endpoint protection (Bearer token)
- Token issuance and validation
- Display name helpers
- Client IP resolution
"""

import logging
import os
import re
import time
from datetime import datetime, timezone
from functools import wraps
from uuid import uuid4

from flask import Blueprint, current_app, g, jsonify, make_response, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from src.models.league import db, UserAccount
from src.utils.sanitize import sanitize_plain_text

logger = logging.getLogger(__name__)

# Blueprint for any shared auth utilities that need to be registered
auth_utilities_bp = Blueprint('auth_utilities', __name__)


# ---------------------------------------------------------------------------
# Admin email list
# ---------------------------------------------------------------------------

def _admin_email_list() -> list[str]:
    """Return list of admin emails from environment, deduplicated and ordered."""
    raw = os.getenv('ADMIN_EMAILS') or ''
    emails = [item.strip() for item in raw.split(',') if item.strip()]
    if not emails:
        return []
    # Preserve order while removing duplicates
    return list(dict.fromkeys(emails))


# ---------------------------------------------------------------------------
# IP whitelist configuration
# ---------------------------------------------------------------------------

def _get_allowed_admin_ips() -> list[str]:
    """Parse IP whitelist from environment."""
    return [ip.strip() for ip in os.getenv('ADMIN_IP_WHITELIST', '').split(',') if ip.strip()]


# Module-level cache (evaluated once at import time in production,
# but function allows re-evaluation in tests)
ALLOWED_ADMIN_IPS = _get_allowed_admin_ips()


def get_client_ip() -> str:
    """Get the real client IP, handling proxies and load balancers."""
    # Check X-Forwarded-For header (from load balancers, proxies)
    forwarded_for = request.headers.get('X-Forwarded-For')
    if forwarded_for:
        # Take the first IP in the chain (original client)
        return forwarded_for.split(',')[0].strip()

    # Check X-Real-IP header (nginx proxy)
    real_ip = request.headers.get('X-Real-IP')
    if real_ip:
        return real_ip.strip()

    # Fall back to direct connection IP
    return request.remote_addr or ''


# ---------------------------------------------------------------------------
# Token serializer
# ---------------------------------------------------------------------------

def _user_serializer() -> URLSafeTimedSerializer:
    """Get a URL-safe timed serializer for user tokens."""
    secret = current_app.config.get('SECRET_KEY') or os.getenv('SECRET_KEY')
    is_prod = os.getenv("FLASK_ENV", "").lower() in ("prod", "production", "stage", "staging")

    # Fail fast in production if SECRET_KEY is missing or default
    if is_prod and (not secret or secret == 'change-me'):
        raise RuntimeError("SECRET_KEY must be properly configured in production")

    return URLSafeTimedSerializer(secret_key=secret or 'change-me', salt='user-auth')


def issue_user_token(email: str, ttl_seconds: int = 60 * 60 * 24 * 30, role: str = 'user') -> dict:
    """Issue a signed JWT-like token for user authentication.

    Args:
        email: User's email address
        ttl_seconds: Token lifetime in seconds (default 30 days)
        role: Token role ('user' or 'admin')

    Returns:
        Dict with 'token' and 'expires_in' keys
    """
    s = _user_serializer()
    # Embed ts in payload for debugging; URLSafeTimedSerializer enforces max_age on loads
    payload = {'email': email, 'role': role, 'iat': int(time.time())}
    token = s.dumps(payload)
    logger.info("Issued auth token payload for %s with role=%s", email, role)
    return {
        'token': token,
        'expires_in': ttl_seconds
    }


# ---------------------------------------------------------------------------
# Auth decorators
# ---------------------------------------------------------------------------

def require_api_key(f):
    """Decorator to require API key for admin endpoints with optional IP whitelisting.

    Implements dual-factor authentication:
    1. Valid admin Bearer token (role='admin')
    2. Correct X-API-Key header matching ADMIN_API_KEY env var

    Also optionally checks IP against ADMIN_IP_WHITELIST if configured.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.method == 'OPTIONS':
            return make_response('', 204)

        client_ip = get_client_ip()
        auth_header = request.headers.get('Authorization') or ''
        api_key_header = request.headers.get('X-API-Key') or request.headers.get('X-Admin-Key') or ''
        logger.debug(
            "Admin auth attempt ip=%s endpoint=%s auth_present=%s key_present=%s",
            client_ip,
            request.endpoint,
            bool(auth_header),
            bool(api_key_header),
        )

        # Check IP whitelist if configured
        allowed_ips = _get_allowed_admin_ips()
        if allowed_ips and client_ip not in allowed_ips:
            logger.warning(f"Admin access denied for IP {client_ip} (not in whitelist)")
            return jsonify({
                'error': 'Access denied from this IP address',
                'message': 'Your IP is not authorized for admin operations'
            }), 403

        # Get the API key from environment
        required_api_key = os.getenv('ADMIN_API_KEY')
        if required_api_key:
            required_api_key = required_api_key.strip()

        if not required_api_key:
            logger.warning("ADMIN_API_KEY not configured in environment")
            return jsonify({
                'error': 'API authentication not configured',
                'message': 'Contact administrator'
            }), 500

        # Require admin Bearer token
        token_data = None
        if auth_header.startswith('Bearer '):
            token = auth_header.split(' ', 1)[1]
            try:
                data = _user_serializer().loads(token, max_age=60 * 60 * 24 * 30)
                if (data or {}).get('role') == 'admin':
                    token_data = data
                    g.user_email = (data or {}).get('email')
            except Exception as _e:
                logger.warning(f"Bearer admin token failed for {client_ip}: {_e}")

        if not token_data:
            logger.warning(
                "Admin token missing or invalid ip=%s endpoint=%s auth_sample=%s",
                client_ip,
                request.endpoint,
                auth_header[:32],
            )
            return jsonify({'error': 'Admin login required', 'message': 'Provide a valid admin Bearer token'}), 401

        # Require API key as a second factor
        provided_key = request.headers.get('X-API-Key') or request.headers.get('X-Admin-Key')
        provided_key = (provided_key or '').strip()

        def _mask_admin_key(value: str | None) -> str:
            if not value:
                return '(none)'
            trimmed = value.strip()
            if len(trimmed) <= 6:
                return trimmed
            return f"{trimmed[:3]}...{trimmed[-3:]}"

        masked_key = _mask_admin_key(provided_key)

        if not provided_key:
            logger.warning(
                "Admin API key missing ip=%s user=%s endpoint=%s auth_sample=%s",
                client_ip,
                getattr(g, 'user_email', None),
                request.endpoint,
                auth_header[:32],
            )
            return jsonify({'error': 'Admin API key required', 'message': 'Send X-API-Key in the request headers'}), 401

        if provided_key != required_api_key:
            logger.warning(
                "Invalid admin credential ip=%s user=%s endpoint=%s key=%s",
                client_ip,
                getattr(g, 'user_email', None),
                request.endpoint,
                masked_key,
            )
            return jsonify({'error': 'Invalid admin credential', 'message': 'Access denied'}), 403

        logger.info(
            "Admin dual auth granted ip=%s user=%s endpoint=%s key=%s",
            client_ip,
            getattr(g, 'user_email', None),
            request.endpoint,
            masked_key,
        )
        return f(*args, **kwargs)

    return decorated_function


def require_curator_auth(f):
    """Decorator to require curator authentication (dual-factor).

    Implements:
    1. Valid Bearer token (sets g.user)
    2. User must have is_curator=True
    3. Correct X-Curator-Key header matching CURATOR_API_KEY from config
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.method == 'OPTIONS':
            return make_response('', 204)

        # Step 1: Validate Bearer token
        auth = request.headers.get('Authorization', '')
        if auth.startswith('Bearer '):
            token = auth.split(' ', 1)[1]
        else:
            return jsonify({'error': 'missing auth token'}), 401

        s = _user_serializer()
        try:
            data = s.loads(token, max_age=60 * 60 * 24 * 30)
            email = data.get('email')
            g.user_email = email
            if email:
                user = UserAccount.query.filter_by(email=email).first()
                if user:
                    g.user = user
                    g.user_id = user.id
                else:
                    return jsonify({'error': 'user not found'}), 401
            else:
                return jsonify({'error': 'invalid token payload'}), 401
        except SignatureExpired:
            return jsonify({'error': 'auth token expired'}), 401
        except BadSignature:
            return jsonify({'error': 'invalid auth token'}), 401

        # Step 2: Check curator role
        if not getattr(g.user, 'is_curator', False):
            logger.warning("Curator access denied for user %s (not a curator)", g.user_email)
            return jsonify({'error': 'Curator access required'}), 403

        # Step 3: Validate X-Curator-Key
        required_key = current_app.config.get('CURATOR_API_KEY')
        if not required_key:
            logger.warning("CURATOR_API_KEY not configured")
            return jsonify({'error': 'Curator authentication not configured'}), 500

        provided_key = (request.headers.get('X-Curator-Key') or '').strip()
        if not provided_key:
            return jsonify({'error': 'X-Curator-Key header required'}), 401

        if provided_key != required_key:
            logger.warning("Invalid curator key from user %s", g.user_email)
            return jsonify({'error': 'Invalid curator credential'}), 403

        logger.info("Curator auth granted for user %s", g.user_email)
        return f(*args, **kwargs)

    return decorated


def require_user_auth(f):
    """Decorator to require user authentication via Bearer token.

    Sets g.user_email, g.user, and g.user_id on successful authentication.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get('Authorization', '')
        if auth.startswith('Bearer '):
            token = auth.split(' ', 1)[1]
        else:
            token = None
        if not token:
            return jsonify({'error': 'missing auth token'}), 401
        s = _user_serializer()
        try:
            # Accept tokens up to 30 days old by default
            data = s.loads(token, max_age=60 * 60 * 24 * 30)
            email = data.get('email')
            g.user_email = email
            if email:
                user = UserAccount.query.filter_by(email=email).first()
                if user:
                    g.user = user
                    g.user_id = user.id
        except SignatureExpired:
            return jsonify({'error': 'auth token expired'}), 401
        except BadSignature:
            return jsonify({'error': 'invalid auth token'}), 401
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# Helper to get authorized email from request context
# ---------------------------------------------------------------------------

def _get_authorized_email() -> str | None:
    """Resolve the authenticated email from the current request, if present.

    Checks g.user_email first, then attempts to decode Bearer token.
    """
    email = getattr(g, 'user_email', None)
    if email:
        return email

    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header.split(' ', 1)[1].strip()
        if token:
            serializer = _user_serializer()
            try:
                data = serializer.loads(token, max_age=60 * 60 * 24 * 30)
                resolved = (data or {}).get('email')
                if resolved:
                    g.user_email = resolved
                    return resolved
            except (SignatureExpired, BadSignature):
                return None
            except Exception:
                logger.exception('Failed to decode auth token while resolving email')
                return None
    return None


# ---------------------------------------------------------------------------
# Display name helpers
# ---------------------------------------------------------------------------

def _base_display_name_from_email(email: str) -> str:
    """Extract a base display name from email local part."""
    local = (email or '').split('@')[0]
    cleaned = re.sub(r'[^a-zA-Z0-9]+', '', local)
    if not cleaned:
        cleaned = 'loaner'
    return cleaned[:16] or 'loaner'


def _make_display_name_unique(candidate: str) -> str:
    """Ensure display name is unique by appending numeric suffix if needed."""
    base = candidate[:28] or 'loaner'
    suffix = 1
    name = candidate
    while UserAccount.query.filter_by(display_name_lower=name.lower()).first():
        suffix += 1
        trim_base = base[: max(1, 30 - len(str(suffix)))]
        name = f"{trim_base}{suffix}"
    return name


def _generate_default_display_name(email: str) -> str:
    """Generate a unique default display name from email."""
    base = _base_display_name_from_email(email)
    candidate = base
    if len(candidate) < 3:
        candidate = f"{candidate}fan"
    candidate = candidate.title()
    return _make_display_name_unique(candidate)


def _normalize_display_name(value: str) -> str:
    """Sanitize and normalize a display name input."""
    cleaned = sanitize_plain_text(value or '')
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    cleaned = re.sub(r'[^A-Za-z0-9 ._\-]', '', cleaned)
    return cleaned[:40]


# ---------------------------------------------------------------------------
# User account management
# ---------------------------------------------------------------------------

def _ensure_user_account(email: str) -> UserAccount:
    """Get or create a UserAccount for the given email.

    If the user exists, updates last_login_at.
    If not, creates a new user with a generated display name.
    """
    now = datetime.now(timezone.utc)
    user = UserAccount.query.filter_by(email=email).first()
    if user:
        user.last_login_at = now
        if not user.display_name:
            display_name = _generate_default_display_name(email)
            user.display_name = display_name
            user.display_name_lower = display_name.lower()
            user.display_name_confirmed = False
        if not user.last_display_name_change_at:
            user.last_display_name_change_at = now
        return user
    display_name = _generate_default_display_name(email)
    user = UserAccount(
        email=email,
        display_name=display_name,
        display_name_lower=display_name.lower(),
        display_name_confirmed=False,
        created_at=now,
        updated_at=now,
        last_login_at=now,
        last_display_name_change_at=now,
    )
    db.session.add(user)
    db.session.flush()
    return user


# ---------------------------------------------------------------------------
# Error handling helpers
# ---------------------------------------------------------------------------

def _is_production() -> bool:
    """Check if running in production environment."""
    env = (os.getenv('ENV') or os.getenv('FLASK_ENV') or os.getenv('APP_ENV') or '').strip().lower()
    return env in ('prod', 'production')


def _safe_error_payload(exc: Exception, fallback_message: str, include_detail: bool = False) -> dict[str, str]:
    """Return a sanitized error payload, hiding internal details in production."""
    payload = {'error': fallback_message}
    if include_detail or not _is_production():
        payload['detail'] = str(exc)
    else:
        reference = uuid4().hex[:8]
        payload['reference'] = reference
        logger.error('Error reference=%s: %s', reference, exc, exc_info=True)
    return payload
