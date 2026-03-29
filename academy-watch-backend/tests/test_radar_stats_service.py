"""Unit tests for the radar stats service (per-90 / percentile logic)."""

import pytest
from unittest.mock import patch, MagicMock

from src.services.radar_stats_service import (
    formation_position_to_group,
    get_primary_formation_position,
    compute_player_per90,
    percentile_rank,
    get_radar_chart_data,
    POSITION_STAT_AXES,
    STAT_LABELS,
)
from src.utils.formation_roles import POSITION_GROUPS, POSITION_GROUP_LABELS


# ---------------------------------------------------------------------------
# formation_position_to_group
# ---------------------------------------------------------------------------

class TestFormationPositionToGroup:
    def test_known_positions(self):
        assert formation_position_to_group("LW") == "W"
        assert formation_position_to_group("RW") == "W"
        assert formation_position_to_group("ST") == "ST"
        assert formation_position_to_group("CB") == "CB"
        assert formation_position_to_group("LB") == "FB"
        assert formation_position_to_group("CDM") == "DM"
        assert formation_position_to_group("CAM") == "AM"
        assert formation_position_to_group("CM") == "CM"
        assert formation_position_to_group("GK") == "GK"

    def test_case_insensitive(self):
        assert formation_position_to_group("lw") == "W"
        assert formation_position_to_group("St") == "ST"

    def test_fallback_to_broad_position(self):
        assert formation_position_to_group(None, "F") == "ST"
        assert formation_position_to_group(None, "D") == "CB"
        assert formation_position_to_group(None, "M") == "CM"
        assert formation_position_to_group(None, "G") == "GK"

    def test_none_both(self):
        assert formation_position_to_group(None, None) is None

    def test_unknown_position_with_fallback(self):
        assert formation_position_to_group("UNKNOWN", "F") == "ST"

    def test_unknown_both(self):
        assert formation_position_to_group("UNKNOWN", "X") is None


# ---------------------------------------------------------------------------
# get_primary_formation_position
# ---------------------------------------------------------------------------

class TestGetPrimaryFormationPosition:
    def test_basic_mode(self):
        fixtures = [
            {"stats": {"formation_position": "LW"}},
            {"stats": {"formation_position": "LW"}},
            {"stats": {"formation_position": "ST"}},
        ]
        pos, count, total = get_primary_formation_position(fixtures)
        assert pos == "LW"
        assert count == 2
        assert total == 3

    def test_excludes_nulls(self):
        fixtures = [
            {"stats": {"formation_position": None}},
            {"stats": {"formation_position": "CB"}},
            {"stats": {}},
        ]
        pos, count, total = get_primary_formation_position(fixtures)
        assert pos == "CB"
        assert count == 1
        assert total == 1

    def test_all_nulls(self):
        fixtures = [
            {"stats": {"formation_position": None}},
            {"stats": {}},
        ]
        pos, count, total = get_primary_formation_position(fixtures)
        assert pos is None
        assert count == 0
        assert total == 0

    def test_empty_list(self):
        pos, count, total = get_primary_formation_position([])
        assert pos is None


# ---------------------------------------------------------------------------
# compute_player_per90
# ---------------------------------------------------------------------------

class TestComputePlayerPer90:
    def test_basic_per90(self):
        fixtures = [
            {"stats": {"minutes": 90, "goals": 2, "assists": 1, "rating": 7.5}},
            {"stats": {"minutes": 90, "goals": 1, "assists": 0, "rating": 6.8}},
        ]
        result = compute_player_per90(fixtures)
        # 3 goals in 180 min = 1.5 goals per 90
        assert result["goals"] == 1.5
        # 1 assist in 180 min = 0.5 per 90
        assert result["assists"] == 0.5
        # Rating should be average, not per-90
        assert result["rating"] == round((7.5 + 6.8) / 2, 2)

    def test_partial_minutes(self):
        fixtures = [
            {"stats": {"minutes": 45, "goals": 1, "tackles_total": 3}},
        ]
        result = compute_player_per90(fixtures)
        # 1 goal in 45 min = 2.0 per 90
        assert result["goals"] == 2.0
        # 3 tackles in 45 min = 6.0 per 90
        assert result["tackles_total"] == 6.0

    def test_zero_minutes_skipped(self):
        fixtures = [
            {"stats": {"minutes": 0, "goals": 1}},
            {"stats": {"minutes": 90, "goals": 1}},
        ]
        result = compute_player_per90(fixtures)
        # Only the 90-min fixture counts: 1 goal / 90 min * 90 = 1.0
        assert result["goals"] == 1.0

    def test_none_minutes_skipped(self):
        fixtures = [
            {"stats": {"minutes": None, "goals": 2}},
        ]
        result = compute_player_per90(fixtures)
        assert result == {}

    def test_empty_fixtures(self):
        assert compute_player_per90([]) == {}

    def test_passes_accuracy_string(self):
        fixtures = [
            {"stats": {"minutes": 90, "passes_accuracy": "72%"}},
            {"stats": {"minutes": 90, "passes_accuracy": "80%"}},
        ]
        result = compute_player_per90(fixtures)
        assert result["passes_accuracy"] == 76.0

    def test_rating_not_per90(self):
        """Rating should be averaged, not per-90 normalized."""
        fixtures = [
            {"stats": {"minutes": 45, "rating": 8.0}},
            {"stats": {"minutes": 90, "rating": 6.0}},
        ]
        result = compute_player_per90(fixtures)
        # Simple average of ratings, not weighted by minutes
        assert result["rating"] == 7.0


# ---------------------------------------------------------------------------
# percentile_rank
# ---------------------------------------------------------------------------

class TestPercentileRank:
    def test_middle_value(self):
        sorted_vals = [1.0, 2.0, 3.0, 4.0, 5.0]
        # 3.0 is at index 2 out of 5 = 40th percentile
        assert percentile_rank(3.0, sorted_vals) == 40

    def test_highest_value(self):
        sorted_vals = [1.0, 2.0, 3.0, 4.0, 5.0]
        assert percentile_rank(5.0, sorted_vals) == 80

    def test_above_all(self):
        sorted_vals = [1.0, 2.0, 3.0]
        assert percentile_rank(10.0, sorted_vals) == 100

    def test_below_all(self):
        sorted_vals = [1.0, 2.0, 3.0]
        assert percentile_rank(0.0, sorted_vals) == 0

    def test_empty_list(self):
        assert percentile_rank(5.0, []) == 0

    def test_single_value_equal(self):
        assert percentile_rank(1.0, [1.0]) == 0

    def test_single_value_above(self):
        assert percentile_rank(2.0, [1.0]) == 100


# ---------------------------------------------------------------------------
# get_radar_chart_data (with mocked DB)
# ---------------------------------------------------------------------------

class TestGetRadarChartData:
    @patch("src.services.radar_stats_service.compute_position_percentiles")
    def test_response_shape(self, mock_percentiles):
        mock_percentiles.return_value = {
            "sorted_stats": {
                "goals": [0.0, 0.5, 1.0, 1.5, 2.0],
                "assists": [0.0, 0.3, 0.6, 0.9],
                "shots_on": [0.0, 1.0, 2.0],
                "passes_key": [0.5, 1.0, 1.5],
                "dribbles_success": [0.0, 1.0, 2.0],
                "duels_won": [2.0, 4.0, 6.0],
                "fouls_drawn": [0.5, 1.0, 2.0],
            },
            "averages": {
                "goals": 1.0, "assists": 0.45, "shots_on": 1.0,
                "passes_key": 1.0, "dribbles_success": 1.0,
                "duels_won": 4.0, "fouls_drawn": 1.17,
            },
            "peers_count": 30,
        }

        fixtures = [
            {
                "stats": {
                    "minutes": 90, "goals": 2, "assists": 1,
                    "formation_position": "ST", "position": "F",
                    "shots_on": 3, "passes_key": 1, "dribbles_success": 1,
                    "duels_won": 5, "fouls_drawn": 2,
                }
            },
        ]

        result = get_radar_chart_data(player_id=123, fixtures_data=fixtures)

        assert result["chart_type"] == "radar"
        assert result["position_group"] == "ST"
        assert result["position_group_label"] == "Striker"
        assert result["formation_position"] == "ST"
        assert result["matches_count"] == 1
        assert result["total_minutes"] == 90
        assert result["peers_count"] == 30
        assert isinstance(result["data"], list)
        assert len(result["data"]) == len(POSITION_STAT_AXES["ST"])

        # Check each data item has the right keys
        for item in result["data"]:
            assert "stat" in item
            assert "label" in item
            assert "player_per90" in item
            assert "player_percentile" in item
            assert "position_avg_per90" in item
            assert "position_avg_percentile" in item
            assert 0 <= item["player_percentile"] <= 100

    @patch("src.services.radar_stats_service.compute_position_percentiles")
    def test_position_group_fallback(self, mock_percentiles):
        """When formation_position is all null, falls back to broad position."""
        mock_percentiles.return_value = {
            "sorted_stats": {}, "averages": {}, "peers_count": 0,
        }

        fixtures = [
            {"stats": {"minutes": 90, "position": "D", "formation_position": None}},
        ]

        result = get_radar_chart_data(player_id=456, fixtures_data=fixtures)
        assert result["position_group"] == "CB"
        assert result["formation_position"] is None

    @patch("src.services.radar_stats_service.compute_position_percentiles")
    def test_explicit_stat_keys_override(self, mock_percentiles):
        mock_percentiles.return_value = {
            "sorted_stats": {"goals": [0.0, 1.0], "assists": [0.0, 0.5]},
            "averages": {"goals": 0.5, "assists": 0.25},
            "peers_count": 10,
        }

        fixtures = [
            {"stats": {"minutes": 90, "goals": 1, "assists": 0, "formation_position": "ST", "position": "F"}},
        ]

        result = get_radar_chart_data(
            player_id=789, fixtures_data=fixtures, stat_keys=["goals", "assists"]
        )
        assert len(result["data"]) == 2
        assert result["data"][0]["stat"] == "goals"
        assert result["data"][1]["stat"] == "assists"

    @patch("src.services.radar_stats_service.compute_position_percentiles")
    def test_min_minutes_flag(self, mock_percentiles):
        mock_percentiles.return_value = {
            "sorted_stats": {}, "averages": {}, "peers_count": 0,
        }

        # Player with only 45 minutes — below threshold
        fixtures = [
            {"stats": {"minutes": 45, "formation_position": "LW", "position": "F"}},
        ]
        result = get_radar_chart_data(player_id=100, fixtures_data=fixtures)
        assert result["min_minutes_met"] is False
        assert result["total_minutes"] == 45


# ---------------------------------------------------------------------------
# POSITION_GROUPS coverage
# ---------------------------------------------------------------------------

class TestPositionGroupsCoverage:
    def test_all_groups_have_stat_axes(self):
        for group in POSITION_GROUP_LABELS:
            assert group in POSITION_STAT_AXES, f"Missing stat axes for group {group}"

    def test_all_stat_axes_have_labels(self):
        for group, axes in POSITION_STAT_AXES.items():
            for stat in axes:
                assert stat in STAT_LABELS, f"Missing label for stat {stat} in group {group}"

    def test_all_formation_roles_mapped(self):
        """Every role produced by formation_roles.py should be in POSITION_GROUPS."""
        from src.utils.formation_roles import (
            _DEF_ROLES, _CM_ROLES, _DM_ROLES, _AM_ROLES, _FWD_ROLES,
        )
        all_roles = {"GK"}
        for table in [_DEF_ROLES, _CM_ROLES, _DM_ROLES, _AM_ROLES, _FWD_ROLES]:
            for width_map in table.values():
                all_roles.update(width_map.values())

        for role in all_roles:
            assert role in POSITION_GROUPS, f"Role {role} not mapped in POSITION_GROUPS"
