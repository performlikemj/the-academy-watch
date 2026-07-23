"""Strictly test-mode Stripe Connect Express onboarding for grassroots clubs.

F2 never creates payments, Checkout Sessions, transfers, or live-mode objects.
Calls are possible only when an explicit feature flag and an ``sk_test_`` key
are both present. The organization is onboarded as a company, never as the
claimant/coach/parent personally.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from urllib.parse import urljoin

import stripe


class StripeConnectConfigurationError(RuntimeError):
    pass


def _enabled(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def test_connect_configured() -> bool:
    key = (os.getenv("STRIPE_SECRET_KEY") or "").strip()
    return _enabled(os.getenv("STRIPE_CONNECT_TEST_MODE")) and key.startswith("sk_test_")


def _test_key() -> str:
    key = (os.getenv("STRIPE_SECRET_KEY") or "").strip()
    if not _enabled(os.getenv("STRIPE_CONNECT_TEST_MODE")):
        raise StripeConnectConfigurationError("Stripe Connect test mode is disabled")
    if not key.startswith("sk_test_"):
        raise StripeConnectConfigurationError("Stripe Connect requires an sk_test_ key in F2")
    return key


def _onboarding_urls(program_slug: str) -> tuple[str, str]:
    base = (os.getenv("PUBLIC_BASE_URL") or "https://example.com").rstrip("/") + "/"
    refresh_url = os.getenv("STRIPE_CONNECT_REFRESH_URL") or urljoin(base, f"programs/{program_slug}?connect=refresh")
    return_url = os.getenv("STRIPE_CONNECT_RETURN_URL") or urljoin(base, f"programs/{program_slug}?connect=complete")
    if not refresh_url.startswith("https://") or not return_url.startswith("https://"):
        raise StripeConnectConfigurationError("Stripe Connect onboarding URLs must use https")
    return refresh_url, return_url


def create_express_organization_onboarding(program) -> dict:
    """Create one test Express organization account and hosted onboarding link."""
    stripe.api_key = _test_key()
    refresh_url, return_url = _onboarding_urls(program.slug)

    account = stripe.Account.create(
        type="express",
        country="US",
        business_type="company",
        business_profile={
            "name": program.legal_name,
            "product_description": "Grassroots soccer program support",
        },
        capabilities={"transfers": {"requested": True}},
        metadata={"club_program_id": str(program.id), "environment": "test"},
    )
    if bool(account.get("livemode")):
        raise StripeConnectConfigurationError("Live-mode connected accounts are forbidden in F2")

    link = stripe.AccountLink.create(
        account=account["id"],
        refresh_url=refresh_url,
        return_url=return_url,
        type="account_onboarding",
    )
    return {
        **_account_result(account),
        "onboarding_url": link["url"],
        "onboarding_expires_at": datetime.fromtimestamp(link["expires_at"], tz=UTC) if link.get("expires_at") else None,
    }


def retrieve_test_express_account(stripe_account_id: str) -> dict:
    """Refresh readiness from Stripe after hosted test onboarding completes."""
    if not isinstance(stripe_account_id, str) or not stripe_account_id.startswith("acct_"):
        raise StripeConnectConfigurationError("A valid connected account ID is required")
    stripe.api_key = _test_key()
    account = stripe.Account.retrieve(stripe_account_id)
    if account.get("id") != stripe_account_id:
        raise StripeConnectConfigurationError("Stripe returned a different connected account")
    if bool(account.get("livemode")):
        raise StripeConnectConfigurationError("Live-mode connected accounts are forbidden in F2")
    return _account_result(account)


def _account_result(account) -> dict:
    """Normalize the narrow Connect readiness projection stored by F2."""
    return {
        "stripe_account_id": account["id"],
        "livemode": False,
        "account_type": account.get("type") or "express",
        "country": account.get("country") or "US",
        "business_type": account.get("business_type") or "company",
        "details_submitted": bool(account.get("details_submitted")),
        "charges_enabled": bool(account.get("charges_enabled")),
        "payouts_enabled": bool(account.get("payouts_enabled")),
        "transfers_active": (account.get("capabilities") or {}).get("transfers") == "active",
        "requirements_due": _requirements_due(account),
        "disabled_reason": (account.get("requirements") or {}).get("disabled_reason"),
    }


def _requirements_due(account) -> list[str]:
    requirements = account.get("requirements") or {}
    return sorted(
        {
            str(item)
            for key in ("currently_due", "past_due", "pending_verification")
            for item in (requirements.get(key) or [])
        }
    )
