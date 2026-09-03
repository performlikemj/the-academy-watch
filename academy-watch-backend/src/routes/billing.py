"""Dark-shipped Stripe billing HTTP routes."""

from __future__ import annotations

import logging
import time

import stripe
from flask import Blueprint, abort, g, jsonify, request
from src.auth import require_api_key, require_user_auth
from src.config.stripe_config import billing_enabled, configure_stripe, offered_products
from src.extensions import limiter
from src.models.billing import BillingCustomer
from src.models.league import db
from src.services.stripe_billing import (
    BillingError,
    admin_summary,
    create_checkout,
    create_portal_session,
    handle_webhook,
    require_billing_rail,
    subscription_payload,
    subscriptions_for_user,
)

logger = logging.getLogger(__name__)
billing_bp = Blueprint("billing", __name__)

_PRICE_CACHE_SECONDS = 600
_price_cache: dict[str, tuple[float, dict]] = {}


@billing_bp.before_app_request
def _hide_billing_rail_paths_when_disabled():
    """Hide automatic OPTIONS and wrong-method probes while flag-off."""
    path = request.path.rstrip("/")
    is_billing_path = path == "/api/billing" or path.startswith("/api/billing/")
    is_admin_billing_path = path == "/api/admin/billing" or path.startswith("/api/admin/billing/")
    if (is_billing_path or is_admin_billing_path) and not billing_enabled():
        abort(404)


def _user_rate_limit_key() -> str:
    return str(getattr(g, "user_id", None) or getattr(g, "user_email", None) or request.remote_addr or "anon")


def _stripe_value(value, key, default=None):
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _price_details(price_id: str) -> dict:
    cached = _price_cache.get(price_id)
    now = time.monotonic()
    if cached is not None and now - cached[0] < _PRICE_CACHE_SECONDS:
        return cached[1]
    try:
        configure_stripe()
        price = stripe.Price.retrieve(price_id)
        details = {
            "unit_amount": _stripe_value(price, "unit_amount"),
            "currency": str(_stripe_value(price, "currency")).lower(),
        }
        if details["unit_amount"] is None or not _stripe_value(price, "currency"):
            return {}
        _price_cache[price_id] = (now, details)
        return details
    except Exception:
        logger.warning("Stripe price lookup failed for configured price %s", price_id, exc_info=True)
        return {}


@billing_bp.route("/billing/stripe/webhook", methods=["POST"])
@require_billing_rail
def stripe_webhook():
    return handle_webhook(request.get_data(), request.headers.get("Stripe-Signature"))


@billing_bp.route("/billing/config", methods=["GET"])
@require_billing_rail
def billing_config():
    products = []
    for code, product in offered_products().items():
        prices = []
        for price_code, price_id in product["prices"].items():
            price = {
                "price_code": price_code,
                "interval": "month" if price_code == "monthly" else "year",
            }
            price.update(_price_details(price_id))
            prices.append(price)
        products.append(
            {
                "code": code,
                "name": product["name"],
                "scope_type": product["scope_type"],
                "prices": prices,
            }
        )
    response = jsonify({"enabled": True, "products": products})
    response.headers["Cache-Control"] = "no-store"
    return response


@billing_bp.route("/billing/me", methods=["GET"])
@require_billing_rail
@require_user_auth
def billing_me():
    rows = subscriptions_for_user(g.user)
    return jsonify(
        {
            "enabled": True,
            "has_billing_account": BillingCustomer.query.filter_by(user_account_id=g.user.id).first() is not None,
            "subscriptions": [subscription_payload(row) for row in rows],
        }
    )


@billing_bp.route("/billing/checkout", methods=["POST"])
@require_billing_rail
@require_user_auth
@limiter.limit("10 per minute", key_func=_user_rate_limit_key)
def billing_checkout():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "invalid_json"}), 400
    try:
        result = create_checkout(
            g.user,
            product_code=payload.get("product_code"),
            price_code=payload.get("price_code"),
            client_key=payload.get("client_key"),
        )
        db.session.commit()
        return jsonify(result)
    except BillingError as exc:
        db.session.rollback()
        return jsonify({"error": exc.code}), exc.status
    except Exception:
        db.session.rollback()
        logger.exception("Stripe checkout creation failed")
        return jsonify({"error": "checkout_failed"}), 500


@billing_bp.route("/billing/portal", methods=["POST"])
@require_billing_rail
@require_user_auth
@limiter.limit("10 per minute", key_func=_user_rate_limit_key)
def billing_portal():
    try:
        return jsonify({"portal_url": create_portal_session(g.user)})
    except BillingError as exc:
        db.session.rollback()
        return jsonify({"error": exc.code}), exc.status
    except Exception:
        db.session.rollback()
        logger.exception("Stripe billing portal creation failed")
        return jsonify({"error": "portal_failed"}), 500


@billing_bp.route("/admin/billing/summary", methods=["GET"])
@require_billing_rail
@require_api_key
def billing_admin_summary():
    return jsonify(admin_summary())


__all__ = ["billing_bp"]
