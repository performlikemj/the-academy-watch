"""Derived Scout Pro entitlements and feature gates."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from functools import wraps

from flask import g, jsonify, request
from src.config.stripe_config import billing_enabled
from src.services.stripe_billing import active_subscription


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def _environment_datetime(name: str) -> datetime | None:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return None
    try:
        value = datetime.fromisoformat(raw[:-1] + "+00:00" if raw.endswith(("Z", "z")) else raw)
        if value.tzinfo is None or value.utcoffset() is None:
            return None
        return _naive_utc(value)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def decoded_bearer_role() -> str:
    """Return the signed role from the current request's Bearer token."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return "user"
    try:
        from src.auth import USER_TOKEN_TTL_SECONDS, _user_serializer

        token_data = _user_serializer().loads(auth_header.split(" ", 1)[1], max_age=USER_TOKEN_TTL_SECONDS)
        if not isinstance(token_data, dict):
            return "user"
        role = token_data.get("role")
    except Exception:
        return "user"
    return role if isinstance(role, str) and role else "user"


def scout_entitlements(user, *, now=None, role="user") -> dict:
    """Return the user's effective tier and feature access."""
    enabled = billing_enabled()
    if not enabled:
        tier = user.scout_tier or "free"
        entitlements = {
            "billing_enabled": False,
            "tier": tier,
            "source": "billing_disabled",
            "subscription_status": None,
            "current_period_end": None,
            "cancel_at_period_end": False,
            "grandfathered_until": None,
            "features": {"gol_chat": True},
        }
    elif (subscription := active_subscription("user", user.id, "scout_pro")) is not None:
        period_end = (
            _naive_utc(subscription.current_period_end).isoformat() if subscription.current_period_end else None
        )
        entitlements = {
            "billing_enabled": True,
            "tier": "pro",
            "source": "subscription",
            "subscription_status": subscription.status,
            "current_period_end": period_end,
            "cancel_at_period_end": bool(subscription.cancel_at_period_end),
            "grandfathered_until": None,
            "features": {"gol_chat": True},
        }
    else:
        launched_at = _environment_datetime("SCOUT_PRO_LAUNCHED_AT")
        grandfather_until = _environment_datetime("SCOUT_PRO_GRANDFATHER_UNTIL")
        current_time = _naive_utc(now or datetime.now(UTC))
        created_at = _naive_utc(user.created_at) if user.created_at is not None else None
        grandfathered = (
            launched_at is not None
            and grandfather_until is not None
            and created_at is not None
            and created_at < launched_at
            and current_time < grandfather_until
        )
        entitlements = {
            "billing_enabled": True,
            "tier": "pro" if grandfathered else "free",
            "source": "grandfather" if grandfathered else "none",
            "subscription_status": None,
            "current_period_end": None,
            "cancel_at_period_end": False,
            "grandfathered_until": grandfather_until.isoformat() if grandfathered else None,
            "features": {"gol_chat": grandfathered},
        }

    if role == "admin":
        entitlements["features"]["gol_chat"] = True
    return entitlements


def is_pro(user) -> bool:
    return scout_entitlements(user)["tier"] == "pro"


def require_scout_entitlement(feature: str):
    """Reject authenticated users who lack a Scout Pro feature."""

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            role = decoded_bearer_role()
            if role == "admin":
                return view(*args, **kwargs)

            entitlements = scout_entitlements(g.user, role=role)
            if not entitlements["features"].get(feature, False):
                return (
                    jsonify(
                        {
                            "error": "scout_pro_required",
                            "feature": feature,
                            "upgrade_path": "/pricing",
                        }
                    ),
                    403,
                )
            return view(*args, **kwargs)

        return wrapped

    return decorator


__all__ = [
    "decoded_bearer_role",
    "is_pro",
    "require_scout_entitlement",
    "scout_entitlements",
]
