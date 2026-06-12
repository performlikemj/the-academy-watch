"""Supported league configuration — single source of truth for the
platform's league footprint.

Two tiers:

- SUPPORTED_LEAGUES: every league the platform knows about. Drives league/team
  metadata sync, /api/leagues, and team browsing. Cheap to expand (one or two
  API calls per league, cached). Override with SUPPORTED_LEAGUE_IDS env var
  (comma-separated API-Football league IDs) to constrain.

- Crawl leagues: the subset actively crawled for fixtures, player stats, and
  loan detection. These sweeps are expensive (paginated per-league player
  crawls), so expanding them is an explicit env change (CRAWL_LEAGUE_IDS),
  never a side effect of widening the supported map.

League IDs are API-Football IDs.
"""

import logging
import os

logger = logging.getLogger(__name__)

REGION_EUROPE = "Europe"
REGION_SOUTH_AMERICA = "South America"
REGION_NORTH_AMERICA = "North America"
REGION_ASIA = "Asia"

SUPPORTED_LEAGUES: dict[int, dict[str, str | int]] = {
    # Europe — top five
    39: {"name": "Premier League", "country": "England", "region": REGION_EUROPE, "tier": 1},
    140: {"name": "La Liga", "country": "Spain", "region": REGION_EUROPE, "tier": 1},
    135: {"name": "Serie A", "country": "Italy", "region": REGION_EUROPE, "tier": 1},
    78: {"name": "Bundesliga", "country": "Germany", "region": REGION_EUROPE, "tier": 1},
    61: {"name": "Ligue 1", "country": "France", "region": REGION_EUROPE, "tier": 1},
    # Europe — key development leagues (heavy loan/academy traffic)
    88: {"name": "Eredivisie", "country": "Netherlands", "region": REGION_EUROPE, "tier": 1},
    94: {"name": "Primeira Liga", "country": "Portugal", "region": REGION_EUROPE, "tier": 1},
    144: {"name": "Jupiler Pro League", "country": "Belgium", "region": REGION_EUROPE, "tier": 1},
    40: {"name": "Championship", "country": "England", "region": REGION_EUROPE, "tier": 2},
    203: {"name": "Süper Lig", "country": "Turkey", "region": REGION_EUROPE, "tier": 1},
    # South America — primary talent pipelines
    71: {"name": "Serie A", "country": "Brazil", "region": REGION_SOUTH_AMERICA, "tier": 1},
    128: {"name": "Liga Profesional Argentina", "country": "Argentina", "region": REGION_SOUTH_AMERICA, "tier": 1},
    # North America
    253: {"name": "Major League Soccer", "country": "USA", "region": REGION_NORTH_AMERICA, "tier": 1},
    262: {"name": "Liga MX", "country": "Mexico", "region": REGION_NORTH_AMERICA, "tier": 1},
    # Asia
    98: {"name": "J1 League", "country": "Japan", "region": REGION_ASIA, "tier": 1},
    307: {"name": "Pro League", "country": "Saudi Arabia", "region": REGION_ASIA, "tier": 1},
}

# The original European top-five — the historical crawl footprint. Fixture and
# loan-detection sweeps stay on this set unless CRAWL_LEAGUE_IDS widens them.
DEFAULT_CRAWL_LEAGUE_IDS: tuple[int, ...] = (39, 140, 135, 78, 61)


def _parse_league_ids(raw: str) -> list[int]:
    ids = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.append(int(part))
        except ValueError:
            logger.warning("Ignoring invalid league id %r in league env config", part)
    return ids


def get_supported_leagues() -> dict[int, dict[str, str | int]]:
    """Return the supported league map, optionally constrained by
    SUPPORTED_LEAGUE_IDS (comma-separated API-Football league IDs)."""
    raw = os.getenv("SUPPORTED_LEAGUE_IDS", "").strip()
    if not raw:
        return dict(SUPPORTED_LEAGUES)
    ids = _parse_league_ids(raw)
    selected = {lid: SUPPORTED_LEAGUES[lid] for lid in ids if lid in SUPPORTED_LEAGUES}
    unknown = [lid for lid in ids if lid not in SUPPORTED_LEAGUES]
    if unknown:
        logger.warning("SUPPORTED_LEAGUE_IDS contains unknown league ids %s — ignored", unknown)
    return selected or dict(SUPPORTED_LEAGUES)


def get_crawl_league_ids() -> list[int]:
    """Return league IDs eligible for expensive fixture/loan-detection crawls.

    Defaults to the European top-five. Override with CRAWL_LEAGUE_IDS.
    """
    raw = os.getenv("CRAWL_LEAGUE_IDS", "").strip()
    if not raw:
        return list(DEFAULT_CRAWL_LEAGUE_IDS)
    ids = _parse_league_ids(raw)
    return ids or list(DEFAULT_CRAWL_LEAGUE_IDS)


def get_league_region(league_id: int | None) -> str | None:
    info = SUPPORTED_LEAGUES.get(league_id or 0)
    return info["region"] if info else None
