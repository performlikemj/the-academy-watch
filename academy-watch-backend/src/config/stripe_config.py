"""Stripe configuration resolved from the environment at call time."""

from __future__ import annotations

import logging
import os
import time

import stripe

logger = logging.getLogger(__name__)

_PRICE_CACHE_SECONDS = 600
_PRICE_FAILURE_CACHE_SECONDS = 60
_price_cache: dict[str, tuple[float, dict]] = {}

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
    "gol": {
        "scope_type": "user",
        "name": "GOL chatbot",
        "purchase_mode": "payment",
        "packs": {
            "gol_starter": {
                "price_env": "STRIPE_PRICE_GOL_STARTER",
                "credits_env": "GOL_STARTER_CREDITS",
                "label": "Starter",
            },
            "gol_topup": {
                "price_env": "STRIPE_PRICE_GOL_TOPUP",
                "credits_env": "GOL_TOPUP_CREDITS",
                "label": "Top up",
            },
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
        if "prices" not in product:
            continue
        prices = {
            price_code: price_id
            for price_code, env_name in product.get("prices", {}).items()
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


def _positive_int_env(name: str) -> int | None:
    try:
        value = int((os.getenv(name) or "").strip())
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def offered_packs() -> dict[str, dict]:
    """Resolve configured GOL credit packs without calling Stripe."""
    packs = {}
    for pack_id, pack in PRODUCT_CATALOG["gol"]["packs"].items():
        price_id = (os.getenv(pack["price_env"]) or "").strip()
        credits = _positive_int_env(pack["credits_env"])
        if price_id and credits is not None:
            packs[pack_id] = {
                "price_id": price_id,
                "credits": credits,
                "label": pack["label"],
            }
    return packs


def _stripe_value(value, key, default=None):
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def price_details(price_id: str) -> dict:
    """Return cached Stripe price amount/currency details."""
    cached = _price_cache.get(price_id)
    now = time.monotonic()
    if cached is not None:
        ttl = _PRICE_CACHE_SECONDS if cached[1] else _PRICE_FAILURE_CACHE_SECONDS
        if now - cached[0] < ttl:
            return cached[1]
    try:
        configure_stripe()
        price = stripe.Price.retrieve(price_id)
        details = {
            "unit_amount": _stripe_value(price, "unit_amount"),
            "currency": str(_stripe_value(price, "currency")).lower(),
        }
        if details["unit_amount"] is None or not _stripe_value(price, "currency"):
            _price_cache[price_id] = (now, {})
            return {}
        _price_cache[price_id] = (now, details)
        return details
    except Exception:
        logger.warning("Stripe price lookup failed for configured price %s", price_id, exc_info=True)
        _price_cache[price_id] = (now, {})
        return {}


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
