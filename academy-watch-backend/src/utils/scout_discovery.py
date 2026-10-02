"""Dynamic switch shared by all community scout discovery reads."""

import os


def local_players_enabled() -> bool:
    """Whether approved locals join discovery/query-resolved Scout surfaces.

    This gates global search, browse, leaderboards, compare, export, and query follows. Direct
    watchlist adds and player-follow selectors accept approved adult locals
    regardless of this flag. Read dynamically so an operator can roll the
    union back without a process restart; the safe default remains off.
    """

    return os.getenv("SCOUT_INCLUDE_LOCAL_PLAYERS", "").strip().lower() in {"1", "true", "yes", "on"}
