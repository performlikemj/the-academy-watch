"""Per-90 percentile radar chart service.

Computes per-90-minute stats for a player and ranks them against peers
who most frequently play the same positional role (derived from
FixturePlayerStats.formation_position).
"""

import logging
import time
from bisect import bisect_left
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func

from src.models.league import db
from src.models.weekly import Fixture, FixturePlayerStats
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

# Stats that are NOT per-90 normalized (they are already rates/averages)
_RAW_AVERAGE_STATS = {"rating", "passes_accuracy"}

# Stats where lower is better (invert percentile: 100 - pct)
_INVERTED_STATS = {"goals_conceded", "fouls_committed"}

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

# Minimum minutes for inclusion in percentile pool
MIN_MINUTES_POOL = 200
# Minimum minutes for the charted player before we show a warning
MIN_MINUTES_PLAYER = 200

# ---------------------------------------------------------------------------
# In-memory cache for position percentile pools
# ---------------------------------------------------------------------------
_percentile_cache: Dict[Tuple[str, int], Tuple[float, dict]] = {}
_CACHE_TTL = 6 * 3600  # 6 hours


def _cache_get(key: Tuple[str, int]) -> Optional[dict]:
    entry = _percentile_cache.get(key)
    if entry and (time.time() - entry[0]) < _CACHE_TTL:
        return entry[1]
    return None


def _cache_set(key: Tuple[str, int], data: dict) -> None:
    _percentile_cache[key] = (time.time(), data)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def formation_position_to_group(
    formation_position: Optional[str],
    fallback_position: Optional[str] = None,
) -> Optional[str]:
    """Map a formation_position label (e.g. 'LW') to a position group key (e.g. 'W').

    Falls back to broad position code (G/D/M/F) if formation_position is missing.
    Returns None if nothing can be resolved.
    """
    if formation_position:
        group = POSITION_GROUPS.get(formation_position.upper())
        if group:
            return group
    if fallback_position:
        return POSITION_BROAD_TO_GROUP.get(fallback_position.upper())
    return None


def get_primary_formation_position(fixtures_data: List[dict]) -> Tuple[Optional[str], int, int]:
    """Determine a player's most-played formation_position from fixture data.

    Args:
        fixtures_data: List of fixture dicts, each with a 'stats' sub-dict
                       containing 'formation_position' and optionally 'substitute'.

    Returns:
        (most_common_position, count_at_that_position, total_starts_with_position_data)
    """
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
    """Compute per-90-minute stats for a single player from their fixture data.

    For stats in _RAW_AVERAGE_STATS (rating, passes_accuracy), returns the
    simple average instead of per-90 normalization.

    Returns dict of {stat_key: per90_value}.
    """
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

        # Accumulate countable stats
        for key in STAT_LABELS:
            if key in _RAW_AVERAGE_STATS:
                continue
            val = stats.get(key)
            if val is None:
                continue
            totals[key] = totals.get(key, 0) + (val if isinstance(val, (int, float)) else 0)

        # Collect rating values for averaging
        r = stats.get("rating")
        if r is not None and isinstance(r, (int, float)) and r > 0:
            rating_values.append(r)

        # Collect pass accuracy (may be string like "68%")
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

    # Raw averages
    if rating_values:
        result["rating"] = round(sum(rating_values) / len(rating_values), 2)
    if accuracy_values:
        result["passes_accuracy"] = round(sum(accuracy_values) / len(accuracy_values), 1)

    return result


def percentile_rank(value: float, sorted_values: List[float]) -> int:
    """Return the percentile rank (0-100) of value within sorted_values.

    Uses bisect_left for O(log n) lookup.
    Returns 0 if sorted_values is empty.
    """
    n = len(sorted_values)
    if n == 0:
        return 0
    idx = bisect_left(sorted_values, value)
    return round((idx / n) * 100)


def compute_position_percentiles(
    position_group: str,
    season: Optional[int] = None,
) -> Dict[str, Any]:
    """Compute per-90 stats for all players in a position group and return
    sorted arrays for each stat (used for percentile lookups).

    Uses an in-memory cache with 6-hour TTL.

    Returns:
        {
            'sorted_stats': {stat_key: sorted_list_of_per90_values},
            'averages': {stat_key: mean_per90_value},
            'peers_count': int,
        }
    """
    from datetime import datetime, timezone

    if season is None:
        now = datetime.now(timezone.utc)
        season = now.year if now.month >= 7 else now.year - 1

    cache_key = (position_group, season)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    # Find all formation_position labels that belong to this group
    group_positions = [fp for fp, g in POSITION_GROUPS.items() if g == position_group]
    if not group_positions:
        return {"sorted_stats": {}, "averages": {}, "peers_count": 0}

    # Query: get per-player aggregates for the season
    # Join FixturePlayerStats with Fixture to filter by season
    rows = (
        db.session.query(
            FixturePlayerStats.player_api_id,
            func.sum(FixturePlayerStats.minutes).label("total_minutes"),
            func.sum(FixturePlayerStats.goals).label("total_goals"),
            func.sum(FixturePlayerStats.assists).label("total_assists"),
            func.sum(FixturePlayerStats.shots_total).label("total_shots_total"),
            func.sum(FixturePlayerStats.shots_on).label("total_shots_on"),
            func.sum(FixturePlayerStats.passes_total).label("total_passes_total"),
            func.sum(FixturePlayerStats.passes_key).label("total_passes_key"),
            func.sum(FixturePlayerStats.tackles_total).label("total_tackles_total"),
            func.sum(FixturePlayerStats.tackles_blocks).label("total_tackles_blocks"),
            func.sum(FixturePlayerStats.tackles_interceptions).label("total_tackles_interceptions"),
            func.sum(FixturePlayerStats.duels_total).label("total_duels_total"),
            func.sum(FixturePlayerStats.duels_won).label("total_duels_won"),
            func.sum(FixturePlayerStats.dribbles_success).label("total_dribbles_success"),
            func.sum(FixturePlayerStats.dribbles_attempts).label("total_dribbles_attempts"),
            func.sum(FixturePlayerStats.fouls_drawn).label("total_fouls_drawn"),
            func.sum(FixturePlayerStats.fouls_committed).label("total_fouls_committed"),
            func.sum(FixturePlayerStats.saves).label("total_saves"),
            func.sum(FixturePlayerStats.goals_conceded).label("total_goals_conceded"),
            func.sum(FixturePlayerStats.yellows).label("total_yellows"),
            func.sum(FixturePlayerStats.reds).label("total_reds"),
            func.avg(FixturePlayerStats.rating).label("avg_rating"),
            func.count(FixturePlayerStats.id).label("appearances"),
        )
        .join(Fixture, FixturePlayerStats.fixture_id == Fixture.id)
        .filter(
            Fixture.season == season,
            FixturePlayerStats.formation_position.in_(group_positions),
            FixturePlayerStats.minutes > 0,
        )
        .group_by(FixturePlayerStats.player_api_id)
        .having(func.sum(FixturePlayerStats.minutes) >= MIN_MINUTES_POOL)
        .all()
    )

    if not rows:
        result = {"sorted_stats": {}, "averages": {}, "peers_count": 0}
        _cache_set(cache_key, result)
        return result

    # Now we need to filter to players whose MOST COMMON formation_position
    # is in this group. The query above includes all appearances at group positions,
    # but a player might mostly play elsewhere.
    # For efficiency, we do a second pass: for each player in our result set,
    # check their most common position.
    player_ids = [r.player_api_id for r in rows]

    # Get formation_position counts per player (only for this season)
    fp_counts = (
        db.session.query(
            FixturePlayerStats.player_api_id,
            FixturePlayerStats.formation_position,
            func.count(FixturePlayerStats.id).label("cnt"),
        )
        .join(Fixture, FixturePlayerStats.fixture_id == Fixture.id)
        .filter(
            Fixture.season == season,
            FixturePlayerStats.player_api_id.in_(player_ids),
            FixturePlayerStats.formation_position.isnot(None),
            FixturePlayerStats.minutes > 0,
        )
        .group_by(FixturePlayerStats.player_api_id, FixturePlayerStats.formation_position)
        .all()
    )

    # Find each player's primary position
    player_fp_counts: Dict[int, Counter] = {}
    for row in fp_counts:
        if row.player_api_id not in player_fp_counts:
            player_fp_counts[row.player_api_id] = Counter()
        player_fp_counts[row.player_api_id][row.formation_position] = row.cnt

    valid_player_ids = set()
    for pid, counter in player_fp_counts.items():
        primary_fp = counter.most_common(1)[0][0]
        primary_group = POSITION_GROUPS.get(primary_fp)
        if primary_group == position_group:
            valid_player_ids.add(pid)

    # Filter rows to only valid players
    valid_rows = [r for r in rows if r.player_api_id in valid_player_ids]

    if not valid_rows:
        result = {"sorted_stats": {}, "averages": {}, "peers_count": 0}
        _cache_set(cache_key, result)
        return result

    # Compute per-90 for each valid player
    stat_columns = {
        "goals": "total_goals",
        "assists": "total_assists",
        "shots_total": "total_shots_total",
        "shots_on": "total_shots_on",
        "passes_total": "total_passes_total",
        "passes_key": "total_passes_key",
        "tackles_total": "total_tackles_total",
        "tackles_blocks": "total_tackles_blocks",
        "tackles_interceptions": "total_tackles_interceptions",
        "duels_total": "total_duels_total",
        "duels_won": "total_duels_won",
        "dribbles_success": "total_dribbles_success",
        "dribbles_attempts": "total_dribbles_attempts",
        "fouls_drawn": "total_fouls_drawn",
        "fouls_committed": "total_fouls_committed",
        "saves": "total_saves",
        "goals_conceded": "total_goals_conceded",
        "yellows": "total_yellows",
        "reds": "total_reds",
    }

    all_per90: Dict[str, List[float]] = {k: [] for k in stat_columns}
    all_per90["rating"] = []

    for r in valid_rows:
        mins = r.total_minutes or 0
        if mins <= 0:
            continue
        for stat_key, col_name in stat_columns.items():
            val = getattr(r, col_name, None) or 0
            p90 = round((val / mins) * 90, 3)
            all_per90[stat_key].append(p90)
        # Rating is a raw average
        if r.avg_rating and r.avg_rating > 0:
            all_per90["rating"].append(round(r.avg_rating, 2))

    # Sort each stat array and compute averages
    sorted_stats: Dict[str, List[float]] = {}
    averages: Dict[str, float] = {}
    for stat_key, values in all_per90.items():
        if not values:
            continue
        sorted_stats[stat_key] = sorted(values)
        averages[stat_key] = round(sum(values) / len(values), 3)

    result = {
        "sorted_stats": sorted_stats,
        "averages": averages,
        "peers_count": len(valid_rows),
    }
    _cache_set(cache_key, result)
    return result


def get_radar_chart_data(
    player_id: int,
    fixtures_data: List[dict],
    stat_keys: Optional[List[str]] = None,
    season: Optional[int] = None,
) -> Dict[str, Any]:
    """Build the full radar chart response for a player.

    Args:
        player_id: The player's API ID.
        fixtures_data: List of fixture dicts with 'stats' sub-dict.
        stat_keys: Explicit stat axes to use. If None, auto-selects by position.
        season: Season year for percentile pool. Defaults to current.

    Returns:
        Dict matching the new radar chart API response shape.
    """
    # Determine primary position
    primary_fp, fp_count, fp_total = get_primary_formation_position(fixtures_data)

    # Get broad position fallback
    broad_positions: Counter = Counter()
    for f in fixtures_data:
        pos = f.get("stats", {}).get("position")
        if pos:
            broad_positions[pos] += 1
    fallback_pos = broad_positions.most_common(1)[0][0] if broad_positions else None

    position_group = formation_position_to_group(primary_fp, fallback_pos)
    if not position_group:
        position_group = "CM"  # ultimate fallback

    # Auto-select stat axes if not provided
    if not stat_keys:
        stat_keys = POSITION_STAT_AXES.get(position_group, POSITION_STAT_AXES["CM"])

    # Compute player per-90 stats
    player_per90 = compute_player_per90(fixtures_data)

    # Compute total minutes
    total_minutes = sum(
        (f.get("stats", {}).get("minutes") or 0) for f in fixtures_data
    )

    # Get position percentile pool
    pool = compute_position_percentiles(position_group, season)

    # Build data array
    data_items = []
    for stat_key in stat_keys:
        p90_val = player_per90.get(stat_key, 0.0)
        sorted_vals = pool.get("sorted_stats", {}).get(stat_key, [])
        avg_val = pool.get("averages", {}).get(stat_key, 0.0)

        pct = percentile_rank(p90_val, sorted_vals)
        avg_pct = percentile_rank(avg_val, sorted_vals)

        # Invert for "lower is better" stats
        if stat_key in _INVERTED_STATS:
            pct = 100 - pct
            avg_pct = 100 - avg_pct

        label = STAT_LABELS.get(stat_key, stat_key.replace("_", " ").title())
        if stat_key not in _RAW_AVERAGE_STATS:
            label += " Per 90"

        data_items.append({
            "stat": stat_key,
            "label": label,
            "player_per90": round(p90_val, 2),
            "player_percentile": pct,
            "position_avg_per90": round(avg_val, 2),
            "position_avg_percentile": avg_pct,
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
        "peers_count": pool.get("peers_count", 0),
        "data": data_items,
    }
