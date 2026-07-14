"""Tests for src/utils/fixture_stats_mapper.py — the shared FixturePlayerStats mapping.

The mapper is the single source of truth for turning an API-Football
``statistics[0]`` block into FixturePlayerStats column values. Prod data showed
tackles_interceptions / tackles_blocks / passes_accuracy / dribbles_attempts /
dribbles_past / the penalty set / offsides almost entirely NULL because writers
hand-picked field subsets; these tests pin the full mapping.
"""

from src.utils.fixture_stats_mapper import map_player_stat_block

# Realistic /fixtures/players statistics[0] payload (API-Football v3 shape),
# including the API's "commited" typo in the penalty block.
FULL_STAT_BLOCK = {
    "games": {
        "minutes": 90,
        "number": 22,
        "position": "M",
        "rating": "7.6",
        "captain": True,
        "substitute": False,
    },
    "offsides": 1,
    "shots": {"total": 3, "on": 2},
    "goals": {"total": 1, "conceded": 0, "assists": 1, "saves": None},
    "passes": {"total": 54, "key": 3, "accuracy": 46},
    "tackles": {"total": 4, "blocks": 1, "interceptions": 2},
    "duels": {"total": 15, "won": 9},
    "dribbles": {"attempts": 5, "success": 3, "past": 2},
    "fouls": {"drawn": 2, "committed": 1},
    "cards": {"yellow": 1, "red": 0},
    "penalty": {"won": 1, "commited": 0, "scored": 1, "missed": 0, "saved": None},
}

EXPECTED_FULL = {
    "minutes": 90,
    "position": "M",
    "number": 22,
    "rating": 7.6,
    "captain": True,
    "substitute": False,
    "goals": 1,
    "assists": 1,
    "goals_conceded": 0,
    "saves": None,
    "yellows": 1,
    "reds": 0,
    "shots_total": 3,
    "shots_on": 2,
    "passes_total": 54,
    "passes_key": 3,
    "passes_accuracy": "46%",
    "tackles_total": 4,
    "tackles_blocks": 1,
    "tackles_interceptions": 2,
    "duels_total": 15,
    "duels_won": 9,
    "dribbles_attempts": 5,
    "dribbles_success": 3,
    "dribbles_past": 2,
    "fouls_drawn": 2,
    "fouls_committed": 1,
    "penalty_won": 1,
    "penalty_committed": 0,
    "penalty_scored": 1,
    "penalty_missed": 0,
    "penalty_saved": None,
    "offsides": 1,
}


class TestFullPayload:
    def test_every_column_maps(self):
        assert map_player_stat_block(FULL_STAT_BLOCK) == EXPECTED_FULL

    def test_rating_is_coerced_to_float(self):
        mapped = map_player_stat_block(FULL_STAT_BLOCK)
        assert isinstance(mapped["rating"], float)
        assert mapped["rating"] == 7.6

    def test_penalty_committed_zero_is_kept_not_defaulted(self):
        # 0 is a real value; the "committed" fallback must only fire on None/absent.
        mapped = map_player_stat_block(FULL_STAT_BLOCK)
        assert mapped["penalty_committed"] == 0


class TestModelCoverage:
    def test_mapper_covers_every_stat_column_of_fixture_player_stats(self):
        """The mapper's key set must exactly equal the model's stat columns.

        Identity, formation and raw_json are caller-owned; everything else must
        be produced by the mapper so no writer can silently trim fields again.
        """
        from src.models.weekly import FixturePlayerStats

        caller_owned = {
            "id",
            "fixture_id",
            "player_api_id",
            "team_api_id",
            "formation",
            "grid",
            "formation_position",
            "raw_json",
        }
        stat_columns = {c.name for c in FixturePlayerStats.__table__.columns} - caller_owned
        assert set(map_player_stat_block(FULL_STAT_BLOCK).keys()) == stat_columns


class TestDefaults:
    EXPECTED_DEFAULTS = {
        "minutes": 0,
        "goals": 0,
        "assists": 0,
        "yellows": 0,
        "reds": 0,
        "captain": False,
        "substitute": False,
    }

    def test_empty_block_yields_defaults(self):
        mapped = map_player_stat_block({})
        for key, value in self.EXPECTED_DEFAULTS.items():
            assert mapped[key] == value
        for key in set(mapped) - set(self.EXPECTED_DEFAULTS):
            assert mapped[key] is None, f"{key} should default to None"

    def test_none_block_yields_defaults(self):
        assert map_player_stat_block(None) == map_player_stat_block({})


class TestNullHandling:
    def test_null_values_in_blocks(self):
        """API-Football sends explicit nulls; counting stats coerce to 0."""
        block = {
            "games": {"minutes": None, "rating": None, "position": None, "number": None},
            "goals": {"total": None, "assists": None, "conceded": None, "saves": None},
            "cards": {"yellow": None, "red": None},
            "shots": {"total": None, "on": None},
            "passes": {"total": None, "key": None, "accuracy": None},
            "tackles": {"total": None, "blocks": None, "interceptions": None},
            "duels": {"total": None, "won": None},
            "dribbles": {"attempts": None, "success": None, "past": None},
            "fouls": {"drawn": None, "committed": None},
            "penalty": {"won": None, "commited": None, "scored": None, "missed": None, "saved": None},
            "offsides": None,
        }
        mapped = map_player_stat_block(block)
        assert mapped["minutes"] == 0
        assert mapped["goals"] == 0
        assert mapped["assists"] == 0
        assert mapped["yellows"] == 0
        assert mapped["reds"] == 0
        assert mapped["rating"] is None
        assert mapped["passes_accuracy"] is None
        assert mapped["tackles_interceptions"] is None
        assert mapped["penalty_committed"] is None
        assert mapped["offsides"] is None

    def test_null_nested_blocks_are_guarded(self):
        """Whole sub-blocks can be null (``or {}`` guard) without blowing up."""
        block = {
            "games": None,
            "goals": None,
            "cards": None,
            "shots": None,
            "passes": None,
            "tackles": None,
            "duels": None,
            "dribbles": None,
            "fouls": None,
            "penalty": None,
        }
        mapped = map_player_stat_block(block)
        assert mapped["minutes"] == 0
        assert mapped["shots_total"] is None
        assert mapped["duels_won"] is None


class TestPenaltyCommittedTypo:
    def test_reads_api_typo_commited(self):
        mapped = map_player_stat_block({"penalty": {"commited": 2}})
        assert mapped["penalty_committed"] == 2

    def test_falls_back_to_correct_spelling(self):
        mapped = map_player_stat_block({"penalty": {"committed": 3}})
        assert mapped["penalty_committed"] == 3

    def test_typo_key_wins_when_both_present(self):
        mapped = map_player_stat_block({"penalty": {"commited": 2, "committed": 5}})
        assert mapped["penalty_committed"] == 2


class TestPassesAccuracyCoercion:
    def test_int_accuracy_gets_percent_suffix(self):
        assert map_player_stat_block({"passes": {"accuracy": 68}})["passes_accuracy"] == "68%"

    def test_string_accuracy_kept_as_is(self):
        assert map_player_stat_block({"passes": {"accuracy": "68%"}})["passes_accuracy"] == "68%"
        assert map_player_stat_block({"passes": {"accuracy": "68"}})["passes_accuracy"] == "68"

    def test_missing_accuracy_is_none(self):
        assert map_player_stat_block({"passes": {"total": 10}})["passes_accuracy"] is None


class TestGameFlags:
    def test_substitute_true_passthrough(self):
        assert map_player_stat_block({"games": {"substitute": True}})["substitute"] is True

    def test_captain_true_passthrough(self):
        assert map_player_stat_block({"games": {"captain": True}})["captain"] is True

    def test_missing_flags_default_false(self):
        mapped = map_player_stat_block({"games": {"minutes": 45}})
        assert mapped["captain"] is False
        assert mapped["substitute"] is False
