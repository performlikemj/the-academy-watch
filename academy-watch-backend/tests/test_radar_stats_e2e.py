#!/usr/bin/env python3
"""End-to-end validation of the radar stats service against the real database.

Run with:
    cd academy-watch-backend
    source ../.loan/bin/activate
    python -m pytest tests/test_radar_stats_e2e.py -v -s

Requires a live PostgreSQL database (uses the app's DB config).
Optionally cross-checks against API-Football if API_FOOTBALL_KEY is set.
"""

import os
import sys
import json
import logging
from collections import Counter
from pathlib import Path

import pytest

# Ensure src is importable
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logger = logging.getLogger(__name__)


def _stats_row_to_flat(s):
    """Convert a FixturePlayerStats ORM row to the flat-key dict format
    used by the journalist endpoint and expected by the radar stats service."""
    return {
        'minutes': s.minutes or 0,
        'position': s.position,
        'formation_position': s.formation_position,
        'rating': s.rating,
        'goals': s.goals or 0,
        'assists': s.assists or 0,
        'yellows': s.yellows or 0,
        'reds': s.reds or 0,
        'substitute': s.substitute,
        'shots_total': s.shots_total or 0,
        'shots_on': s.shots_on or 0,
        'passes_total': s.passes_total or 0,
        'passes_key': s.passes_key or 0,
        'passes_accuracy': s.passes_accuracy or 0,
        'tackles_total': s.tackles_total or 0,
        'tackles_blocks': s.tackles_blocks or 0,
        'tackles_interceptions': s.tackles_interceptions or 0,
        'duels_total': s.duels_total or 0,
        'duels_won': s.duels_won or 0,
        'dribbles_attempts': s.dribbles_attempts or 0,
        'dribbles_success': s.dribbles_success or 0,
        'fouls_drawn': s.fouls_drawn or 0,
        'fouls_committed': s.fouls_committed or 0,
        'saves': s.saves or 0,
        'goals_conceded': s.goals_conceded or 0,
    }


# Skip the entire module if no real DB is configured
_HAS_DB = bool(os.environ.get("DB_HOST") or os.environ.get("DATABASE_URL"))


def _get_app():
    """Create the Flask app with the real database connection."""
    from src.main import app
    return app


def _find_test_players(min_fixtures=5):
    """Find players with enough fixture data across different position groups.

    Returns dict of {position_group: (player_api_id, player_name, fixture_count)}.
    """
    from src.models.weekly import FixturePlayerStats
    from src.utils.formation_roles import POSITION_GROUPS
    from sqlalchemy import func

    # Get players with most fixtures that have formation_position data
    rows = (
        FixturePlayerStats.query
        .with_entities(
            FixturePlayerStats.player_api_id,
            FixturePlayerStats.formation_position,
            func.count(FixturePlayerStats.id).label("cnt"),
        )
        .filter(
            FixturePlayerStats.formation_position.isnot(None),
            FixturePlayerStats.minutes > 0,
        )
        .group_by(FixturePlayerStats.player_api_id, FixturePlayerStats.formation_position)
        .having(func.count(FixturePlayerStats.id) >= min_fixtures)
        .order_by(func.count(FixturePlayerStats.id).desc())
        .limit(200)
        .all()
    )

    # Group by player, find primary position
    player_positions: dict = {}
    for row in rows:
        pid = row.player_api_id
        if pid not in player_positions:
            player_positions[pid] = Counter()
        player_positions[pid][row.formation_position] = row.cnt

    # Pick one player per position group
    selected: dict = {}
    for pid, counter in player_positions.items():
        primary_fp = counter.most_common(1)[0][0]
        group = POSITION_GROUPS.get(primary_fp)
        if group and group not in selected:
            total = sum(counter.values())
            if total >= min_fixtures:
                selected[group] = (pid, primary_fp, total)

    return selected


@pytest.fixture(scope="module")
def app_ctx():
    if not _HAS_DB:
        pytest.skip("No database configured (set DB_HOST or DATABASE_URL)")
    app = _get_app()
    with app.app_context():
        yield app


@pytest.fixture(scope="module")
def test_players(app_ctx):
    players = _find_test_players(min_fixtures=3)
    if not players:
        pytest.skip("No players with sufficient fixture data found in DB")
    return players


class TestRadarStatsE2E:
    """End-to-end tests against the real database."""

    def test_per90_math_verification(self, app_ctx, test_players):
        """Verify per-90 computation by hand-checking against raw fixture totals."""
        from src.models.weekly import FixturePlayerStats, Fixture
        from src.services.radar_stats_service import compute_player_per90

        print("\n" + "=" * 80)
        print("PER-90 MATH VERIFICATION")
        print("=" * 80)

        for group, (pid, fp, count) in list(test_players.items())[:3]:
            # Get raw fixtures
            stats_rows = (
                FixturePlayerStats.query
                .filter_by(player_api_id=pid)
                .filter(FixturePlayerStats.minutes > 0)
                .all()
            )

            if not stats_rows:
                continue

            # Build fixture dicts (same format the service expects)
            fixtures_data = []
            raw_total_minutes = 0
            raw_total_goals = 0
            raw_total_assists = 0
            for s in stats_rows:
                fixtures_data.append({"stats": _stats_row_to_flat(s)})
                raw_total_minutes += (s.minutes or 0)
                raw_total_goals += (s.goals or 0)
                raw_total_assists += (s.assists or 0)

            per90 = compute_player_per90(fixtures_data)

            # Hand-compute expected per-90
            if raw_total_minutes > 0:
                expected_goals_p90 = round((raw_total_goals / raw_total_minutes) * 90, 3)
                expected_assists_p90 = round((raw_total_assists / raw_total_minutes) * 90, 3)
            else:
                expected_goals_p90 = 0
                expected_assists_p90 = 0

            print(f"\n--- Player {pid} ({fp} / {group}) ---")
            print(f"  Fixtures: {len(stats_rows)}, Total minutes: {raw_total_minutes}")
            print(f"  Raw goals: {raw_total_goals}, Raw assists: {raw_total_assists}")
            print(f"  Expected goals/90: {expected_goals_p90}, Got: {per90.get('goals', 0)}")
            print(f"  Expected assists/90: {expected_assists_p90}, Got: {per90.get('assists', 0)}")

            assert per90.get("goals", 0) == expected_goals_p90, (
                f"Goals per-90 mismatch for player {pid}: "
                f"expected {expected_goals_p90}, got {per90.get('goals', 0)}"
            )
            assert per90.get("assists", 0) == expected_assists_p90, (
                f"Assists per-90 mismatch for player {pid}"
            )

    def test_position_determination(self, app_ctx, test_players):
        """Validate position determination by printing formation_position breakdown."""
        from src.models.weekly import FixturePlayerStats
        from src.services.radar_stats_service import get_primary_formation_position

        print("\n" + "=" * 80)
        print("POSITION DETERMINATION")
        print("=" * 80)

        for group, (pid, fp, count) in test_players.items():
            stats_rows = (
                FixturePlayerStats.query
                .filter_by(player_api_id=pid)
                .filter(FixturePlayerStats.minutes > 0)
                .all()
            )

            fixtures_data = [{"stats": _stats_row_to_flat(s)} for s in stats_rows]
            primary, fp_count, fp_total = get_primary_formation_position(fixtures_data)

            # Count nulls
            null_count = sum(1 for s in stats_rows if not s.formation_position)
            total = len(stats_rows)
            null_pct = (null_count / total * 100) if total else 0

            print(f"\n--- Player {pid} (expected group: {group}) ---")
            print(f"  Primary position: {primary} ({fp_count} of {fp_total} starts)")
            print(f"  Null formation_position: {null_count}/{total} ({null_pct:.0f}%)")

            # All formation_position values
            fp_counter = Counter(s.formation_position for s in stats_rows if s.formation_position)
            for pos, cnt in fp_counter.most_common():
                print(f"    {pos}: {cnt}")

            if null_pct > 30:
                print(f"  WARNING: >30% null formation_position data for player {pid}")

            assert primary is not None or null_count == total

    def test_full_radar_chart_data(self, app_ctx, test_players):
        """Call get_radar_chart_data and validate the full response."""
        from src.models.weekly import FixturePlayerStats
        from src.services.radar_stats_service import (
            get_radar_chart_data, POSITION_STAT_AXES,
        )

        print("\n" + "=" * 80)
        print("FULL RADAR CHART DATA")
        print("=" * 80)

        for group, (pid, fp, count) in list(test_players.items())[:3]:
            stats_rows = (
                FixturePlayerStats.query
                .filter_by(player_api_id=pid)
                .filter(FixturePlayerStats.minutes > 0)
                .all()
            )
            fixtures_data = [{"stats": _stats_row_to_flat(s)} for s in stats_rows]

            result = get_radar_chart_data(player_id=pid, fixtures_data=fixtures_data)

            print(f"\n--- Player {pid} ({fp}) ---")
            print(f"  Position group: {result['position_group']} ({result['position_group_label']})")
            print(f"  Formation position: {result['formation_position']}")
            print(f"  Position matches: {result['position_matches']}/{result['matches_count']}")
            print(f"  Total minutes: {result['total_minutes']}")
            print(f"  Min minutes met: {result['min_minutes_met']}")
            print(f"  Peers count: {result['peers_count']}")
            print(f"  Stats:")
            for item in result["data"]:
                print(
                    f"    {item['label']:25s}  "
                    f"player={item['player_per90']:6.2f}  "
                    f"pct={item['player_percentile']:3d}  "
                    f"avg={item['position_avg_per90']:6.2f}"
                )

            # Validate structure
            assert result["chart_type"] == "radar"
            assert result["position_group"] in POSITION_STAT_AXES
            assert isinstance(result["data"], list)
            assert len(result["data"]) > 0

            for item in result["data"]:
                assert 0 <= item["player_percentile"] <= 100
                assert item["player_per90"] >= 0
                assert 0 <= item["position_avg_percentile"] <= 100

    def test_percentile_pool_stats(self, app_ctx, test_players):
        """Validate the percentile pool for each position group."""
        from src.services.radar_stats_service import compute_position_percentiles

        print("\n" + "=" * 80)
        print("PERCENTILE POOL STATS")
        print("=" * 80)

        for group in test_players:
            pool = compute_position_percentiles(group)

            print(f"\n--- Position group: {group} ---")
            print(f"  Peers count: {pool['peers_count']}")

            if pool["peers_count"] < 5:
                print(f"  WARNING: Very small pool ({pool['peers_count']} players)")

            for stat, sorted_vals in pool.get("sorted_stats", {}).items():
                if not sorted_vals:
                    continue
                mn = sorted_vals[0]
                mx = sorted_vals[-1]
                median = sorted_vals[len(sorted_vals) // 2]
                avg = pool["averages"].get(stat, 0)
                print(
                    f"    {stat:25s}  "
                    f"min={mn:6.2f}  median={median:6.2f}  "
                    f"max={mx:6.2f}  avg={avg:6.2f}  "
                    f"n={len(sorted_vals)}"
                )

            assert pool["peers_count"] >= 0

    def test_old_vs_new_comparison(self, app_ctx, test_players):
        """Compare old hardcoded-max normalization vs new percentile normalization."""
        from src.models.weekly import FixturePlayerStats
        from src.services.radar_stats_service import (
            get_radar_chart_data, compute_player_per90,
            get_primary_formation_position, formation_position_to_group,
        )
        # Import old normalization functions (still in journalist.py)
        from src.routes.journalist import (
            _get_primary_position, _categorize_position,
            _get_position_max_values, _aggregate_player_stats,
        )

        print("\n" + "=" * 80)
        print("OLD vs NEW NORMALIZATION COMPARISON")
        print("=" * 80)

        for group, (pid, fp, count) in list(test_players.items())[:2]:
            stats_rows = (
                FixturePlayerStats.query
                .filter_by(player_api_id=pid)
                .filter(FixturePlayerStats.minutes > 0)
                .all()
            )
            fixtures_data = [{"stats": _stats_row_to_flat(s)} for s in stats_rows]

            # NEW: percentile-based
            new_result = get_radar_chart_data(player_id=pid, fixtures_data=fixtures_data)

            # OLD: hardcoded max
            old_position = _get_primary_position(fixtures_data)
            old_category = _categorize_position(old_position)
            old_maxes = _get_position_max_values(old_category)
            old_stat_keys = [item["stat"] for item in new_result["data"]]
            old_aggregated = _aggregate_player_stats(fixtures_data, old_stat_keys, average_stats=True)

            print(f"\n--- Player {pid} ({fp} / {group}) ---")
            print(f"  Old position: {old_position} ({old_category})")
            print(f"  New position: {new_result['formation_position']} ({new_result['position_group_label']})")
            print(f"  {'Stat':<25s}  {'Old norm':>8s}  {'New pct':>8s}  {'Per90':>8s}  {'Avg':>8s}")
            print(f"  {'-'*25}  {'-'*8}  {'-'*8}  {'-'*8}  {'-'*8}")

            for item in new_result["data"]:
                stat = item["stat"]
                old_avg = old_aggregated.get(stat, 0)
                old_max = old_maxes.get(stat, 5)
                old_norm = min(100, round((old_avg / max(old_max, 0.1)) * 100, 1))

                print(
                    f"  {item['label']:<25s}  "
                    f"{old_norm:>7.1f}%  "
                    f"{item['player_percentile']:>7d}%  "
                    f"{item['player_per90']:>8.2f}  "
                    f"{item['position_avg_per90']:>8.2f}"
                )


class TestAPIFootballCrossCheck:
    """Cross-check local aggregated stats against API-Football season endpoint.

    Only runs if API_FOOTBALL_KEY is available.
    """

    @pytest.fixture(autouse=True)
    def _skip_without_api_key(self):
        if not os.environ.get("API_FOOTBALL_KEY"):
            pytest.skip("API_FOOTBALL_KEY not set — skipping API cross-check")

    def test_season_stats_match(self, app_ctx, test_players):
        """Compare local fixture aggregates against API-Football /players endpoint."""
        from src.api_football_client import APIFootballClient
        from src.models.weekly import FixturePlayerStats
        from datetime import datetime, timezone

        api_key = os.environ["API_FOOTBALL_KEY"]
        client = APIFootballClient(api_key=api_key)

        now = datetime.now(timezone.utc)
        season = now.year if now.month >= 7 else now.year - 1

        print("\n" + "=" * 80)
        print(f"API-FOOTBALL CROSS-CHECK (season {season})")
        print("=" * 80)

        # Only check 1-2 players to conserve API quota
        for group, (pid, fp, count) in list(test_players.items())[:2]:
            # Local aggregates
            local_rows = (
                FixturePlayerStats.query
                .filter_by(player_api_id=pid)
                .filter(FixturePlayerStats.minutes > 0)
                .all()
            )
            local_goals = sum(r.goals or 0 for r in local_rows)
            local_assists = sum(r.assists or 0 for r in local_rows)
            local_minutes = sum(r.minutes or 0 for r in local_rows)
            local_apps = len(local_rows)

            # API-Football season stats
            try:
                resp = client._make_request("players", {
                    "id": pid,
                    "season": season,
                })
                api_stats = resp.get("response", [])
            except Exception as e:
                print(f"  API call failed for player {pid}: {e}")
                continue

            if not api_stats:
                print(f"  No API data for player {pid}")
                continue

            # Sum across all league entries (player may play in multiple comps)
            api_goals = 0
            api_assists = 0
            api_minutes = 0
            api_apps = 0
            for entry in api_stats:
                for stat_block in entry.get("statistics", []):
                    games = stat_block.get("games", {})
                    goals_block = stat_block.get("goals", {})
                    api_goals += goals_block.get("total", 0) or 0
                    api_assists += goals_block.get("assists", 0) or 0
                    api_minutes += (games.get("minutes", 0) or 0)
                    api_apps += (games.get("appearences", 0) or 0)  # API typo is real

            print(f"\n--- Player {pid} ({fp}) ---")
            print(f"  {'':15s}  {'Local':>8s}  {'API':>8s}  {'Diff':>8s}")
            print(f"  {'Appearances':15s}  {local_apps:>8d}  {api_apps:>8d}  {local_apps - api_apps:>+8d}")
            print(f"  {'Goals':15s}  {local_goals:>8d}  {api_goals:>8d}  {local_goals - api_goals:>+8d}")
            print(f"  {'Assists':15s}  {local_assists:>8d}  {api_assists:>8d}  {local_assists - api_assists:>+8d}")
            print(f"  {'Minutes':15s}  {local_minutes:>8d}  {api_minutes:>8d}  {local_minutes - api_minutes:>+8d}")

            # Allow some slack (international games excluded locally, etc.)
            goals_diff = abs(local_goals - api_goals)
            if goals_diff > 3:
                print(f"  WARNING: Goals differ by {goals_diff}")

            assists_diff = abs(local_assists - api_assists)
            if assists_diff > 3:
                print(f"  WARNING: Assists differ by {assists_diff}")
