"""Stripe configuration resolved from the environment at call time."""

from __future__ import annotations

import os

import stripe

PRODUCT_CATALOG = {
    "scout_pro": {
        "scope_type": "user",
        "name": "Scout Pro",
        "prices": {
            "monthly": "STRIPE_PRICE_SCOUT_PRO_MONTHLY",
            "yearly": "STRIPE_PRICE_SCOUT_PRO_YEARLY",
        },
    },
    "club_bundle": {
        "scope_type": "club_program",
        "name": "Club bundle",
        "prices": {
            "monthly": "STRIPE_PRICE_CLUB_BUNDLE_MONTHLY",
            "yearly": "STRIPE_PRICE_CLUB_BUNDLE_YEARLY",
        },
    },
}


def _platform_fee_percent() -> int:
    try:
        return int(os.getenv("STRIPE_PLATFORM_FEE_PERCENT", "10"))
    except (TypeError, ValueError):
        return 10


def billing_enabled() -> bool:
    return os.getenv("BILLING_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def offered_products() -> dict[str, dict]:
    products = {}
    for code, product in PRODUCT_CATALOG.items():
        prices = {
            price_code: price_id
            for price_code, env_name in product["prices"].items()
            if (price_id := (os.getenv(env_name) or "").strip())
        }
        if prices:
            products[code] = {
                "scope_type": product["scope_type"],
                "name": product["name"],
                "prices": prices,
            }
    return products


def resolve_price(product_code: str, price_code: str) -> str | None:
    product = offered_products().get(product_code)
    return product["prices"].get(price_code) if product else None


def product_for_price_id(stripe_price_id: str) -> tuple[str, str] | None:
    for product_code, product in offered_products().items():
        for price_code, price_id in product["prices"].items():
            if price_id == stripe_price_id:
                return product_code, price_code
    return None


def configure_stripe() -> None:
    stripe.api_key = (os.getenv("STRIPE_SECRET_KEY") or "").strip() or None


def get_stripe_keys() -> dict:
    """Return legacy configuration fields without caching credentials."""
    return {
        "secret_key": os.getenv("STRIPE_SECRET_KEY"),
        "publishable_key": os.getenv("STRIPE_PUBLISHABLE_KEY"),
        "webhook_secret": os.getenv("STRIPE_WEBHOOK_SECRET"),
        "platform_fee_percent": _platform_fee_percent(),
    }


def calculate_platform_fee(amount_cents: int) -> int:
    return int(amount_cents * _platform_fee_percent() / 100)


def validate_stripe_config() -> tuple[bool, str | None]:
    keys = get_stripe_keys()
    if not keys["secret_key"]:
        return False, "STRIPE_SECRET_KEY not configured"
    if not keys["publishable_key"]:
        return False, "STRIPE_PUBLISHABLE_KEY not configured"
    if not keys["webhook_secret"]:
        return False, "STRIPE_WEBHOOK_SECRET not configured (required for webhook verification)"

    configure_stripe()
    try:
        stripe.Account.retrieve()
        return True, None
    except stripe.error.AuthenticationError:
        return False, "Invalid Stripe API key"
    except Exception as exc:
        return False, f"Error validating Stripe configuration: {exc}"
