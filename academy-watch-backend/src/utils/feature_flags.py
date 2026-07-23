"""Environment-backed feature flags shared by backend read surfaces."""

import os

_ROLLUP_READ_SURFACES = frozenset({"season_stats", "player_stats", "scout"})


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
