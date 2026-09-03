"""Scout Pro entitlement derivation (S3-P1).

Entitlement truth is the `billing_subscriptions` table (D2); `UserAccount.scout_tier`
is only a projection maintained by the billing webhooks. Everything here derives from
`active_subscription` rows plus the grandfather window envs, and NOTHING may break
`/auth/me` or an entitlement route when the environment is missing or malformed.

Dark-shipping contract (D1): with `BILLING_ENABLED` off nothing is gated — the
features come back fully open and `require_scout_entitlement` is a no-op, so every
scout route behaves exactly as it did before S3.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from functools import wraps

from flask import g, jsonify
from src.config.stripe_config import billing_enabled
from src.models.league import UserAccount
from src.services.stripe_billing import active_subscription

# Custom lists a free (non-Pro) account may keep once the billing rail is live.
FREE_LIST_LIMIT = 3

_PRO_FEATURES = {"csv_export": True}
_FREE_FEATURES = {"csv_export": False}


def _utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _as_naive_utc(value: datetime | None) -> datetime | None:
    """Normalise any datetime (naive or aware) to naive UTC for comparisons."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def _parse_utc_env(raw: str | None) -> datetime | None:
    """Parse a grandfather-window env value; None when absent/malformed/timezone-less.

    ISO-8601 with an explicit UTC offset (or trailing `Z`) is required — a timezone-less
    value disables grandfathering per the S3 contracts. Never raises.
    """
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        # Timezone-less values disable grandfathering per the S3 contracts.
        return None
    return _as_naive_utc(parsed)


def _max_follow_lists() -> int:
    """MAX_FOLLOW_LISTS read at call time (tests monkeypatch the scout module attr)."""
    import src.routes.scout as scout_module

    return scout_module.MAX_FOLLOW_LISTS


def _features_for_tier(tier: str) -> dict:
    lists_max = _max_follow_lists() if tier == "pro" else FREE_LIST_LIMIT
    features = dict(_PRO_FEATURES if tier == "pro" else _FREE_FEATURES)
    features["custom_lists_max"] = lists_max
    return features


def _payload(*, tier: str, source: str, subscription_status: str | None = None) -> dict:
    return {
        "billing_enabled": True,
        "tier": tier,
        "source": source,
        "subscription_status": subscription_status,
        "current_period_end": None,
        "cancel_at_period_end": False,
        "grandfathered_until": None,
        "features": _features_for_tier(tier),
    }


def _grandfathered(user, *, now: datetime, launched_at: datetime | None, until: datetime | None) -> bool:
    """Pre-launch accounts stay Pro until GRANDFATHER_UNTIL (D4)."""
    if launched_at is None or until is None or user is None:
        return False
    created_at = _as_naive_utc(getattr(user, "created_at", None))
    if created_at is None or created_at >= launched_at:
        return False
    return now < until


def scout_entitlements(user, *, now: datetime | None = None) -> dict:
    """Derived Scout Pro entitlements for a user account (or None → free defaults)."""
    if not billing_enabled():
        # D1: with the flag off nothing that works today may be gated.
        tier = "free"
        if user is not None:
            tier = getattr(user, "scout_tier", None) or "free"
        return {
            "billing_enabled": False,
            "tier": tier,
            "source": "billing_disabled",
            "subscription_status": None,
            "current_period_end": None,
            "cancel_at_period_end": False,
            "grandfathered_until": None,
            "features": {"csv_export": True, "custom_lists_max": _max_follow_lists()},
        }

    row = active_subscription("user", user.id, "scout_pro") if user is not None else None
    if row is not None:
        payload = _payload(tier="pro", source="subscription", subscription_status=row.status)
        payload["current_period_end"] = row.current_period_end.isoformat() if row.current_period_end else None
        payload["cancel_at_period_end"] = bool(row.cancel_at_period_end)
        return payload

    now_value = _as_naive_utc(now) or _utcnow_naive()
    launched_at = _parse_utc_env(os.getenv("SCOUT_PRO_LAUNCHED_AT"))
    until = _parse_utc_env(os.getenv("SCOUT_PRO_GRANDFATHER_UNTIL"))
    if _grandfathered(user, now=now_value, launched_at=launched_at, until=until):
        payload = _payload(tier="pro", source="grandfather")
        payload["grandfathered_until"] = until.isoformat()
        return payload

    return _payload(tier="free", source="none")


def is_pro(user) -> bool:
    """True when the user holds Scout Pro (subscription or grandfather window)."""
    return scout_entitlements(user)["tier"] == "pro"


def list_limit_for(user) -> int:
    """Custom-list cap for this user (free accounts get FREE_LIST_LIMIT)."""
    return scout_entitlements(user)["features"]["custom_lists_max"]


def _request_user() -> UserAccount | None:
    """The authenticated user inside a require_user_auth-wrapped view."""
    user = getattr(g, "user", None)
    if user is not None:
        return user
    email = getattr(g, "user_email", None)
    if not email:
        return None
    return UserAccount.query.filter_by(email=email).first()


def require_scout_entitlement(feature: str):
    """403 unless the authenticated user holds `feature`; no-op while billing is dark.

    Place INSIDE `@require_user_auth` (auth resolves g.user first), so a free account
    gets the 403 before any rate limiter or business logic runs.
    """

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not scout_entitlements(_request_user())["features"].get(feature, False):
                return jsonify({"error": "scout_pro_required", "feature": feature, "upgrade_path": "/pricing"}), 403
            return view(*args, **kwargs)

        return wrapped

    return decorator


__all__ = ["FREE_LIST_LIMIT", "is_pro", "list_limit_for", "require_scout_entitlement", "scout_entitlements"]
