"""Radar chart service — per-90 stats compared against league-wide position averages.

Computes per-90-minute stats for a player and compares them against the
average for all players at the same broad position in the same league,
using API-Football's /players endpoint for league-wide season data.
"""

import logging
import os
import time
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

from src.models.league import db
from src.utils.formation_roles import (
    POSITION_BROAD_TO_GROUP,
    POSITION_GROUP_LABELS,
    POSITION_GROUPS,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Position-specific stat axes (ordered list of stat keys per group)
# ---------------------------------------------------------------------------

POSITION_STAT_AXES: Dict[str, List[str]] = {
    "ST": [
        "goals", "assists", "shots_on", "passes_key",
        "dribbles_success", "duels_won", "fouls_drawn",
    ],
    "W": [
        "dribbles_success", "passes_key", "assists", "goals",
        "shots_on", "duels_won", "tackles_total",
    ],
    "AM": [
        "passes_key", "assists", "dribbles_success", "goals",
        "shots_total", "passes_total", "duels_won",
    ],
    "CM": [
        "passes_total", "passes_key", "tackles_total",
        "tackles_interceptions", "duels_won", "assists", "dribbles_success",
    ],
    "DM": [
        "tackles_total", "tackles_interceptions", "tackles_blocks",
        "duels_won", "passes_total", "passes_key", "fouls_committed",
    ],
    "FB": [
        "tackles_total", "tackles_interceptions", "passes_key",
        "dribbles_success", "duels_won", "passes_total", "tackles_blocks",
    ],
    "CB": [
        "tackles_total", "tackles_interceptions", "tackles_blocks",
        "duels_won", "passes_total", "passes_key", "fouls_committed",
    ],
    "GK": [
        "saves", "goals_conceded", "passes_total", "passes_key",
    ],
}

# Stats where lower is better (invert: higher normalized = fewer conceded/fouls)
_INVERTED_STATS = {"goals_conceded", "fouls_committed"}

# Stats that are NOT per-90 normalized (already rates/averages)
_RAW_AVERAGE_STATS = {"rating", "passes_accuracy"}

# Human-readable labels
STAT_LABELS: Dict[str, str] = {
    "goals": "Goals",
    "assists": "Assists",
    "shots_total": "Shots",
    "shots_on": "Shots on Target",
    "passes_total": "Passes",
    "passes_key": "Key Passes",
    "passes_accuracy": "Pass Accuracy %",
    "tackles_total": "Tackles",
    "tackles_blocks": "Blocks",
    "tackles_interceptions": "Interceptions",
    "duels_total": "Duels",
    "duels_won": "Duels Won",
    "dribbles_attempts": "Dribble Attempts",
    "dribbles_success": "Dribbles",
    "fouls_drawn": "Fouls Drawn",
    "fouls_committed": "Fouls Committed",
    "saves": "Saves",
    "goals_conceded": "Goals Conceded",
    "yellows": "Yellow Cards",
    "reds": "Red Cards",
    "rating": "Rating",
}

# Minimum minutes for a league player to be included in averages
MIN_MINUTES_LEAGUE = 400
# Minimum minutes for the charted player before we show a warning
MIN_MINUTES_PLAYER = 200
# Minimum league peers to show the comparison overlay
MIN_PEERS_FOR_OVERLAY = 10

# Map our granular position groups to API-Football broad positions
_GROUP_TO_BROAD_POSITION = {
    "GK": "Goalkeeper",
    "CB": "Defender",
    "FB": "Defender",
    "DM": "Midfielder",
    "CM": "Midfielder",
    "AM": "Midfielder",
    "W": "Attacker",
    "ST": "Attacker",
}

# ---------------------------------------------------------------------------
# In-memory cache for league position averages
# ---------------------------------------------------------------------------
_league_cache: Dict[Tuple[int, int], Tuple[float, dict]] = {}
_LEAGUE_CACHE_TTL = 24 * 3600  # 24 hours (API response cached 7 days anyway)


def _cache_get(key: Tuple) -> Optional[dict]:
    entry = _league_cache.get(key)
    if entry and (time.time() - entry[0]) < _LEAGUE_CACHE_TTL:
        return entry[1]
    return None


def _cache_set(key: Tuple, data: dict) -> None:
    _league_cache[key] = (time.time(), data)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def formation_position_to_group(
    formation_position: Optional[str],
    fallback_position: Optional[str] = None,
) -> Optional[str]:
    """Map a formation_position label (e.g. 'LW') to a position group key (e.g. 'W')."""
    if formation_position:
        group = POSITION_GROUPS.get(formation_position.upper())
        if group:
            return group
    if fallback_position:
        return POSITION_BROAD_TO_GROUP.get(fallback_position.upper())
    return None


def get_primary_formation_position(fixtures_data: List[dict]) -> Tuple[Optional[str], int, int]:
    """Determine a player's most-played formation_position from fixture data."""
    counter: Counter = Counter()
    for f in fixtures_data:
        stats = f.get("stats", {})
        fp = stats.get("formation_position")
        if fp:
            counter[fp] = counter.get(fp, 0) + 1

    if not counter:
        return None, 0, 0

    most_common = counter.most_common(1)[0]
    return most_common[0], most_common[1], sum(counter.values())


def compute_player_per90(fixtures_data: List[dict]) -> Dict[str, float]:
    """Compute per-90-minute stats for a single player from their fixture data."""
    total_minutes = 0
    totals: Dict[str, float] = {}
    rating_values: List[float] = []
    accuracy_values: List[float] = []

    for f in fixtures_data:
        stats = f.get("stats", {})
        minutes = stats.get("minutes") or 0
        if minutes <= 0:
            continue

        total_minutes += minutes

        for key in STAT_LABELS:
            if key in _RAW_AVERAGE_STATS:
                continue
            val = stats.get(key)
            if val is None:
                continue
            totals[key] = totals.get(key, 0) + (val if isinstance(val, (int, float)) else 0)

        r = stats.get("rating")
        if r is not None and isinstance(r, (int, float)) and r > 0:
            rating_values.append(r)

        pa = stats.get("passes_accuracy")
        if pa is not None:
            try:
                pa_float = float(str(pa).replace("%", ""))
                accuracy_values.append(pa_float)
            except (ValueError, TypeError):
                pass

    if total_minutes <= 0:
        return {}

    result: Dict[str, float] = {}
    for key, total in totals.items():
        result[key] = round((total / total_minutes) * 90, 3)

    if rating_values:
        result["rating"] = round(sum(rating_values) / len(rating_values), 2)
    if accuracy_values:
        result["passes_accuracy"] = round(sum(accuracy_values) / len(accuracy_values), 1)

    return result


# ---------------------------------------------------------------------------
# League-wide position averages from API-Football
# ---------------------------------------------------------------------------

def _extract_player_per90_from_api(stat_block: dict) -> Optional[Dict[str, float]]:
    """Extract per-90 stats from a single API-Football player statistics block.

    Returns None if the player doesn't meet the minimum minutes threshold.
    """
    games = stat_block.get("games", {})
    minutes = games.get("minutes") or 0
    if minutes < MIN_MINUTES_LEAGUE:
        return None

    goals = stat_block.get("goals", {})
    passes = stat_block.get("passes", {})
    tackles = stat_block.get("tackles", {})
    duels = stat_block.get("duels", {})
    dribbles = stat_block.get("dribbles", {})
    fouls = stat_block.get("fouls", {})
    shots = stat_block.get("shots", {})

    def _p90(val):
        """Convert a season total to per-90."""
        v = val if isinstance(val, (int, float)) else 0
        return round((v / minutes) * 90, 3)

    return {
        "goals": _p90(goals.get("total")),
        "assists": _p90(goals.get("assists")),
        "saves": _p90(goals.get("saves")),
        "goals_conceded": _p90(goals.get("conceded")),
        "shots_total": _p90(shots.get("total")),
        "shots_on": _p90(shots.get("on")),
        "passes_total": _p90(passes.get("total")),
        "passes_key": _p90(passes.get("key")),
        "tackles_total": _p90(tackles.get("total")),
        "tackles_blocks": _p90(tackles.get("blocks")),
        "tackles_interceptions": _p90(tackles.get("interceptions")),
        "duels_total": _p90(duels.get("total")),
        "duels_won": _p90(duels.get("won")),
        "dribbles_success": _p90(dribbles.get("success")),
        "dribbles_attempts": _p90(dribbles.get("attempts")),
        "fouls_drawn": _p90(fouls.get("drawn")),
        "fouls_committed": _p90(fouls.get("committed")),
    }


def fetch_league_position_averages(
    league_api_id: int,
    season: int,
) -> Dict[str, Dict[str, Any]]:
    """Fetch per-90 averages for all positions in a league from API-Football.

    Returns:
        {
            "Defender": {
                "averages": {stat_key: avg_per90, ...},
                "maximums": {stat_key: max_per90, ...},
                "player_count": int,
            },
            "Midfielder": { ... },
            ...
        }
    """
    cache_key = (league_api_id, season)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    from src.api_football_client import APIFootballClient

    api_key = os.getenv("API_FOOTBALL_KEY")
    if not api_key:
        logger.warning("API_FOOTBALL_KEY not set — cannot fetch league averages")
        return {}

    client = APIFootballClient(api_key=api_key)

    # Collect per-90 stats grouped by broad position
    position_stats: Dict[str, List[Dict[str, float]]] = {
        "Goalkeeper": [],
        "Defender": [],
        "Midfielder": [],
        "Attacker": [],
    }

    page = 1
    while True:
        try:
            resp = client._make_request("players", {
                "league": league_api_id,
                "season": season,
                "page": page,
            })
        except Exception as e:
            logger.error(f"API error fetching league {league_api_id} page {page}: {e}")
            break

        players_data = resp.get("response", [])
        if not players_data:
            break

        for player_row in players_data:
            for stat_block in player_row.get("statistics", []):
                pos = (stat_block.get("games", {}).get("position") or "").strip()
                if pos not in position_stats:
                    continue

                per90 = _extract_player_per90_from_api(stat_block)
                if per90:
                    position_stats[pos].append(per90)

        paging = resp.get("paging", {})
        if page >= paging.get("total", 1):
            break
        page += 1

    # Aggregate: compute mean and max per stat per position
    result: Dict[str, Dict[str, Any]] = {}
    for pos, players in position_stats.items():
        if not players:
            result[pos] = {"averages": {}, "maximums": {}, "player_count": 0}
            continue

        all_stats = players[0].keys()
        averages: Dict[str, float] = {}
        maximums: Dict[str, float] = {}

        for stat in all_stats:
            values = [p[stat] for p in players if p.get(stat) is not None]
            if values:
                averages[stat] = round(sum(values) / len(values), 3)
                maximums[stat] = round(max(values), 3)

        result[pos] = {
            "averages": averages,
            "maximums": maximums,
            "player_count": len(players),
        }

    _cache_set(cache_key, result)
    logger.info(
        f"League {league_api_id} season {season}: "
        + ", ".join(f"{p}={d['player_count']}" for p, d in result.items())
    )
    return result


def _league_from_fixture_dicts(fixtures_data: List[dict]) -> Optional[Tuple[int, str]]:
    """Extract league from in-memory fixture dicts (most recent first).

    Uses league_id/league_name fields added by _get_season_stats.
    """
    for f in reversed(fixtures_data):  # most recent last in list
        lid = f.get("league_id")
        lname = f.get("league_name")
        if lid and lname:
            return int(lid), lname
    return None


def _league_from_fixtures(player_api_id: int) -> Optional[Tuple[int, str]]:
    """Extract league from the player's most recent fixture raw_json."""
    import json
    from src.models.weekly import Fixture, FixturePlayerStats

    row = (
        db.session.query(Fixture.raw_json)
        .join(FixturePlayerStats, FixturePlayerStats.fixture_id == Fixture.id)
        .filter(
            FixturePlayerStats.player_api_id == player_api_id,
            Fixture.raw_json.isnot(None),
        )
        .order_by(Fixture.date_utc.desc())
        .first()
    )
    if not row or not row.raw_json:
        return None
    try:
        data = json.loads(row.raw_json)
        league = data.get("league") or {}
        league_id = league.get("id")
        league_name = league.get("name")
        if league_id and league_name:
            return int(league_id), league_name
    except (json.JSONDecodeError, ValueError, TypeError):
        pass
    return None


def resolve_player_league(player_api_id: int) -> Optional[Tuple[int, str]]:
    """Resolve a player's league from their tracked club.

    Returns (league_api_id, league_name) or None.

    Priority (intentionally current-club first for ALL statuses, not just
    on_loan): the league we compare a player against in the radar must be the
    league he is *currently* playing in. A loanee at Barrow → League Two. A
    first-team breakthrough at Forest → Premier League. Falling back to fixture
    raw_json or parent-club lookups can mis-attribute a player's stats to the
    wrong league (e.g. a Barrow loanee with stale Forest U21 fixtures showing
    "Premier League Avg" in his radar), so we drop to those fallbacks only if
    the current club itself has no league row.
    """
    from src.models.league import Team, League
    from src.models.tracked_player import TrackedPlayer

    def _league_from_team(team: "Team") -> Optional[Tuple[int, str]]:
        if not team or not team.league_id:
            return None
        league = League.query.filter_by(id=team.league_id).first()
        if not league:
            return None
        return league.league_id, league.name

    tp = (
        TrackedPlayer.query
        .filter_by(player_api_id=player_api_id, is_active=True)
        .first()
    )
    if tp:
        # 1. Current club via DB id (canonical relationship)
        if tp.current_club_db_id:
            team = Team.query.filter_by(id=tp.current_club_db_id).first()
            result = _league_from_team(team)
            if result:
                return result

        # 2. Current club via API id (fallback when current_club_db_id wasn't
        #    populated by the classifier — common for older records)
        if tp.current_club_api_id:
            team = Team.query.filter_by(team_id=tp.current_club_api_id).first()
            result = _league_from_team(team)
            if result:
                return result

        # 3. Most recent fixture's raw_json league
        result = _league_from_fixtures(player_api_id)
        if result:
            return result

        # 4. Last resort: parent academy club
        team = Team.query.filter_by(id=tp.team_id).first()
        result = _league_from_team(team)
        if result:
            return result

    return None


# ---------------------------------------------------------------------------
# Main radar chart builder
# ---------------------------------------------------------------------------

def get_radar_chart_data(
    player_id: int,
    fixtures_data: List[dict],
    stat_keys: Optional[List[str]] = None,
    season: Optional[int] = None,
) -> Dict[str, Any]:
    """Build the full radar chart response for a player.

    Compares the player's per-90 stats against the league-wide position
    average. Both values are normalized to 0-100 where 100 = the best
    performer at that position in the league.
    """
    from datetime import datetime, timezone

    if season is None:
        now = datetime.now(timezone.utc)
        season = now.year if now.month >= 7 else now.year - 1

    # Determine primary position
    primary_fp, fp_count, fp_total = get_primary_formation_position(fixtures_data)

    broad_positions: Counter = Counter()
    for f in fixtures_data:
        pos = f.get("stats", {}).get("position")
        if pos:
            broad_positions[pos] += 1
    fallback_pos = broad_positions.most_common(1)[0][0] if broad_positions else None

    position_group = formation_position_to_group(primary_fp, fallback_pos)
    if not position_group:
        position_group = "CM"

    # Auto-select stat axes
    if not stat_keys:
        stat_keys = POSITION_STAT_AXES.get(position_group, POSITION_STAT_AXES["CM"])

    # Compute player per-90
    player_per90 = compute_player_per90(fixtures_data)
    total_minutes = sum(
        (f.get("stats", {}).get("minutes") or 0) for f in fixtures_data
    )

    # Resolve league: prefer the canonical current-club league from DB so the
    # comparison is always against the player's actual league, even when
    # fixture data is sparse or mis-attributed. Fixture-dict league is a
    # sanity-check fallback only.
    league_info = resolve_player_league(player_id) or _league_from_fixture_dicts(fixtures_data)
    league_name = None
    league_peers = 0
    league_avg: Dict[str, float] = {}
    league_max: Dict[str, float] = {}

    if league_info:
        league_api_id, league_name = league_info
        broad_pos = _GROUP_TO_BROAD_POSITION.get(position_group, "Midfielder")
        league_data = fetch_league_position_averages(league_api_id, season)
        pos_data = league_data.get(broad_pos, {})
        league_avg = pos_data.get("averages", {})
        league_max = pos_data.get("maximums", {})
        league_peers = pos_data.get("player_count", 0)

    has_league_data = league_peers >= MIN_PEERS_FOR_OVERLAY

    # When no league data exists, self-normalize so the radar still shows
    # the shape of the player's stats rather than a dot in the center.
    if not has_league_data:
        player_max_val = max(
            (player_per90.get(k, 0.0) for k in stat_keys), default=0.0
        )
    else:
        player_max_val = 0.0  # unused when league data exists

    # Build data array
    data_items = []
    for stat_key in stat_keys:
        p90_val = player_per90.get(stat_key, 0.0)
        avg_val = league_avg.get(stat_key, 0.0)
        max_val = league_max.get(stat_key, 0.0)

        # For inverted stats, flip: higher normalized = fewer conceded/fouls
        if stat_key in _INVERTED_STATS and max_val > 0:
            player_norm = max(0, round((1 - p90_val / max_val) * 100))
            avg_norm = max(0, round((1 - avg_val / max_val) * 100))
        elif max_val > 0:
            player_norm = min(100, round((p90_val / max_val) * 100))
            avg_norm = min(100, round((avg_val / max_val) * 100))
        elif player_max_val > 0:
            # No league data — self-normalize against player's own best stat
            player_norm = min(100, round((p90_val / player_max_val) * 100))
            avg_norm = 0
        else:
            player_norm = 0
            avg_norm = 0

        label = STAT_LABELS.get(stat_key, stat_key.replace("_", " ").title())
        if stat_key not in _RAW_AVERAGE_STATS:
            label += " Per 90"

        data_items.append({
            "stat": stat_key,
            "label": label,
            "player_per90": round(p90_val, 2),
            "player_normalized": player_norm,
            "league_avg_per90": round(avg_val, 2),
            "league_avg_normalized": avg_norm if has_league_data else None,
        })

    return {
        "chart_type": "radar",
        "position_group": position_group,
        "position_group_label": POSITION_GROUP_LABELS.get(position_group, position_group),
        "formation_position": primary_fp,
        "position_matches": fp_count,
        "matches_count": len(fixtures_data),
        "total_minutes": total_minutes,
        "min_minutes_met": total_minutes >= MIN_MINUTES_PLAYER,
        "league_name": league_name,
        "league_peers": league_peers,
        "data": data_items,
    }
