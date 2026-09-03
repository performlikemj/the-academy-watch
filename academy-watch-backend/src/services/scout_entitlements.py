"""Derived Scout Pro entitlements and feature gates."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from functools import wraps

from flask import g, jsonify
from src.config.stripe_config import billing_enabled
from src.models.follow import FollowList
from src.services.stripe_billing import active_subscription

FREE_LIST_LIMIT = 3


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


def scout_entitlements(user, *, now=None) -> dict:
    """Return the user's effective tier and feature limits."""
    import src.routes.scout as scout_module

    max_follow_lists = scout_module.MAX_FOLLOW_LISTS
    enabled = billing_enabled()
    if not enabled:
        tier = user.scout_tier or "free"
        return {
            "billing_enabled": False,
            "tier": tier,
            "source": "billing_disabled",
            "subscription_status": None,
            "current_period_end": None,
            "cancel_at_period_end": False,
            "grandfathered_until": None,
            "features": {"csv_export": True, "custom_lists_max": max_follow_lists},
        }

    subscription = active_subscription("user", user.id, "scout_pro")
    if subscription is not None:
        period_end = (
            _naive_utc(subscription.current_period_end).isoformat() if subscription.current_period_end else None
        )
        return {
            "billing_enabled": True,
            "tier": "pro",
            "source": "subscription",
            "subscription_status": subscription.status,
            "current_period_end": period_end,
            "cancel_at_period_end": bool(subscription.cancel_at_period_end),
            "grandfathered_until": None,
            "features": {"csv_export": True, "custom_lists_max": max_follow_lists},
        }

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
    if grandfathered:
        return {
            "billing_enabled": True,
            "tier": "pro",
            "source": "grandfather",
            "subscription_status": None,
            "current_period_end": None,
            "cancel_at_period_end": False,
            "grandfathered_until": grandfather_until.isoformat(),
            "features": {"csv_export": True, "custom_lists_max": max_follow_lists},
        }

    return {
        "billing_enabled": True,
        "tier": "free",
        "source": "none",
        "subscription_status": None,
        "current_period_end": None,
        "cancel_at_period_end": False,
        "grandfathered_until": None,
        "features": {"csv_export": False, "custom_lists_max": FREE_LIST_LIMIT},
    }


def is_pro(user) -> bool:
    return scout_entitlements(user)["tier"] == "pro"


def list_limit_for(user) -> int:
    return scout_entitlements(user)["features"]["custom_lists_max"]


def list_is_within_entitlement(user, follow_list) -> bool:
    """Whether mutations inside this list are included in the user's tier."""
    entitlements = scout_entitlements(user)
    if not entitlements["billing_enabled"] or entitlements["tier"] == "pro" or follow_list.is_default:
        return True

    rank = FollowList.query.filter(
        FollowList.user_account_id == user.id,
        FollowList.is_default.is_(False),
        FollowList.id < follow_list.id,
    ).count()
    return rank < entitlements["features"]["custom_lists_max"]


def require_scout_entitlement(feature: str):
    """Reject authenticated users who lack a Scout Pro feature."""

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            entitlements = scout_entitlements(g.user)
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
    "FREE_LIST_LIMIT",
    "is_pro",
    "list_is_within_entitlement",
    "list_limit_for",
    "require_scout_entitlement",
    "scout_entitlements",
]
