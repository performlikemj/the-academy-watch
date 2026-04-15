"""Unit tests for the radar stats service (per-90 / league comparison logic)."""

from unittest.mock import patch

from src.services.radar_stats_service import (
    POSITION_STAT_AXES,
    STAT_LABELS,
    _extract_player_per90_from_api,
    compute_player_per90,
    formation_position_to_group,
    get_primary_formation_position,
    get_radar_chart_data,
)
from src.utils.formation_roles import POSITION_GROUP_LABELS, POSITION_GROUPS

# ---------------------------------------------------------------------------
# formation_position_to_group
# ---------------------------------------------------------------------------


class TestFormationPositionToGroup:
    def test_known_positions(self):
        assert formation_position_to_group("LW") == "W"
        assert formation_position_to_group("ST") == "ST"
        assert formation_position_to_group("CB") == "CB"
        assert formation_position_to_group("LB") == "FB"
        assert formation_position_to_group("CDM") == "DM"
        assert formation_position_to_group("CAM") == "AM"
        assert formation_position_to_group("CM") == "CM"
        assert formation_position_to_group("GK") == "GK"

    def test_case_insensitive(self):
        assert formation_position_to_group("lw") == "W"

    def test_fallback_to_broad_position(self):
        assert formation_position_to_group(None, "F") == "ST"
        assert formation_position_to_group(None, "D") == "CB"
        assert formation_position_to_group(None, "M") == "CM"
        assert formation_position_to_group(None, "G") == "GK"

    def test_none_both(self):
        assert formation_position_to_group(None, None) is None


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
        ]
        pos, count, total = get_primary_formation_position(fixtures)
        assert pos == "CB"
        assert count == 1

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
        assert result["goals"] == 1.5
        assert result["assists"] == 0.5
        assert result["rating"] == round((7.5 + 6.8) / 2, 2)

    def test_zero_minutes_skipped(self):
        fixtures = [
            {"stats": {"minutes": 0, "goals": 1}},
            {"stats": {"minutes": 90, "goals": 1}},
        ]
        result = compute_player_per90(fixtures)
        assert result["goals"] == 1.0

    def test_empty_fixtures(self):
        assert compute_player_per90([]) == {}

    def test_passes_accuracy_string(self):
        fixtures = [
            {"stats": {"minutes": 90, "passes_accuracy": "72%"}},
            {"stats": {"minutes": 90, "passes_accuracy": "80%"}},
        ]
        result = compute_player_per90(fixtures)
        assert result["passes_accuracy"] == 76.0


# ---------------------------------------------------------------------------
# _extract_player_per90_from_api
# ---------------------------------------------------------------------------


class TestExtractPlayerPer90FromApi:
    def test_basic_extraction(self):
        stat_block = {
            "games": {"minutes": 900, "position": "Defender", "appearences": 10},
            "goals": {"total": 2, "assists": 3, "saves": None, "conceded": 0},
            "passes": {"total": 500, "key": 10, "accuracy": None},
            "tackles": {"total": 30, "blocks": 5, "interceptions": 15},
            "duels": {"total": 100, "won": 55},
            "dribbles": {"attempts": 10, "success": 5, "past": None},
            "fouls": {"drawn": 8, "committed": 12},
            "shots": {"total": 5, "on": 2},
        }
        result = _extract_player_per90_from_api(stat_block)
        assert result is not None
        assert result["goals"] == round((2 / 900) * 90, 3)
        assert result["tackles_total"] == round((30 / 900) * 90, 3)
        assert result["duels_won"] == round((55 / 900) * 90, 3)

    def test_below_min_minutes(self):
        stat_block = {
            "games": {"minutes": 100, "position": "Defender"},
            "goals": {"total": 1},
        }
        result = _extract_player_per90_from_api(stat_block)
        assert result is None

    def test_null_stats_treated_as_zero(self):
        stat_block = {
            "games": {"minutes": 900, "position": "Attacker"},
            "goals": {"total": None, "assists": None, "saves": None, "conceded": None},
            "passes": {"total": None, "key": None},
            "tackles": {"total": None, "blocks": None, "interceptions": None},
            "duels": {"total": None, "won": None},
            "dribbles": {"attempts": None, "success": None},
            "fouls": {"drawn": None, "committed": None},
            "shots": {"total": None, "on": None},
        }
        result = _extract_player_per90_from_api(stat_block)
        assert result is not None
        assert result["goals"] == 0.0


# ---------------------------------------------------------------------------
# get_radar_chart_data (with mocked dependencies)
# ---------------------------------------------------------------------------


class TestGetRadarChartData:
    @patch("src.services.radar_stats_service.resolve_player_league")
    @patch("src.services.radar_stats_service.fetch_league_position_averages")
    def test_response_shape_with_league(self, mock_fetch, mock_resolve):
        mock_resolve.return_value = (40, "Championship")
        mock_fetch.return_value = {
            "Defender": {
                "averages": {
                    "tackles_total": 2.0,
                    "tackles_interceptions": 1.0,
                    "passes_key": 0.5,
                    "dribbles_success": 0.8,
                    "duels_won": 4.0,
                    "passes_total": 40.0,
                    "tackles_blocks": 0.5,
                },
                "maximums": {
                    "tackles_total": 5.0,
                    "tackles_interceptions": 3.0,
                    "passes_key": 2.0,
                    "dribbles_success": 2.5,
                    "duels_won": 9.0,
                    "passes_total": 70.0,
                    "tackles_blocks": 2.0,
                },
                "player_count": 85,
            },
        }

        fixtures = [
            {
                "stats": {
                    "minutes": 90,
                    "tackles_total": 3,
                    "tackles_interceptions": 2,
                    "passes_key": 1,
                    "dribbles_success": 1,
                    "duels_won": 5,
                    "passes_total": 50,
                    "tackles_blocks": 1,
                    "formation_position": "LB",
                    "position": "D",
                }
            },
        ]

        result = get_radar_chart_data(player_id=123, fixtures_data=fixtures)

        assert result["chart_type"] == "radar"
        assert result["position_group"] == "FB"
        assert result["league_name"] == "Championship"
        assert result["league_peers"] == 85
        assert len(result["data"]) == len(POSITION_STAT_AXES["FB"])

        for item in result["data"]:
            assert "player_per90" in item
            assert "player_normalized" in item
            assert "league_avg_per90" in item
            assert "league_avg_normalized" in item
            assert 0 <= item["player_normalized"] <= 100

    @patch("src.services.radar_stats_service.resolve_player_league")
    @patch("src.services.radar_stats_service.fetch_league_position_averages")
    def test_no_league_data_graceful(self, mock_fetch, mock_resolve):
        mock_resolve.return_value = None
        fixtures = [
            {"stats": {"minutes": 90, "position": "D", "formation_position": "CB"}},
        ]
        result = get_radar_chart_data(player_id=456, fixtures_data=fixtures)
        assert result["league_name"] is None
        assert result["league_peers"] == 0
        # Should still have data items
        assert len(result["data"]) > 0


# ---------------------------------------------------------------------------
# Coverage checks
# ---------------------------------------------------------------------------


class TestPositionGroupsCoverage:
    def test_all_groups_have_stat_axes(self):
        for group in POSITION_GROUP_LABELS:
            assert group in POSITION_STAT_AXES

    def test_all_stat_axes_have_labels(self):
        for group, axes in POSITION_STAT_AXES.items():
            for stat in axes:
                assert stat in STAT_LABELS

    def test_all_formation_roles_mapped(self):
        from src.utils.formation_roles import (
            _AM_ROLES,
            _CM_ROLES,
            _DEF_ROLES,
            _DM_ROLES,
            _FWD_ROLES,
        )

        all_roles = {"GK"}
        for table in [_DEF_ROLES, _CM_ROLES, _DM_ROLES, _AM_ROLES, _FWD_ROLES]:
            for width_map in table.values():
                all_roles.update(width_map.values())
        for role in all_roles:
            assert role in POSITION_GROUPS
