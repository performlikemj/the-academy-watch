"""Environment-backed feature flags shared by backend read surfaces."""

import os

_ROLLUP_READ_SURFACES = frozenset({"season_stats", "player_stats", "scout", "teams"})


def rollup_reads_enabled(surface: str) -> bool:
    """Whether ``surface`` is opted into the season-rollup read path.

    ``SEASON_ROLLUP_READS`` is a comma-separated allow-list. Unknown tokens
    and unknown surface lookups are deliberately inert so a typo can never
    broaden the rollout.
    """
    if surface not in _ROLLUP_READ_SURFACES:
        return False
    enabled = {
        token.strip().lower()
        for token in os.getenv("SEASON_ROLLUP_READS", "").split(",")
        if token.strip().lower() in _ROLLUP_READ_SURFACES
    }
    return surface in enabled


def showcase_trust_min_account_age_days() -> int | None:
    """Return the configured account-age floor for trusted profile edits.

    Missing, blank, malformed, and negative values all disable auto-approval.
    This keeps the trust shortcut fail-closed until an operator deliberately
    configures a non-negative day threshold.
    """
    raw_value = os.getenv("SHOWCASE_TRUST_MIN_ACCOUNT_AGE_DAYS")
    if raw_value is None or not raw_value.strip():
        return None
    try:
        days = int(raw_value)
    except ValueError:
        return None
    return days if days >= 0 else None
