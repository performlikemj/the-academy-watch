"""Pure contract tests for Film Room player-reel aggregation."""

from unittest.mock import patch

import pytest
from flask import Flask
from src.models.league import db
from src.routes.video import update_video_match
from src.services.video_reels import aggregate_votes, build_reel_payload, merge_windows, rank_windows, reel_confidence


def _window(start, end, tracklet_id=1):
    return {"start_s": start, "end_s": end, "tracklet_id": tracklet_id}


def _ranked_window(start, end, tracklet_id, rank):
    return _window(start, end, tracklet_id) | {"rank": rank}


def _chain(
    tracklet_id,
    *,
    roster_entry_id=1,
    cluster=0,
    confidence="high",
    contaminated=False,
    first=0,
    last=10,
    visible=10,
    members=None,
    member_spans=None,
    suggested_number=None,
    votes=None,
    dismissed=False,
):
    return {
        "id": tracklet_id,
        "kind": "chain",
        "pipeline_key": f"T{cluster}#{tracklet_id}",
        "team_cluster": cluster,
        "suggested_number": suggested_number,
        "confidence": confidence,
        "contaminated": contaminated,
        "first_s": first,
        "last_s": last,
        "visible_s": visible,
        "evidence": {
            "member_fragment_ids": members or [],
            **({"member_spans": member_spans} if member_spans is not None else {}),
            **({"votes": votes} if votes is not None else {}),
        },
        "roster_entry_id": roster_entry_id,
        "dismissed": dismissed,
    }


def _roster(roster_id=1, number=8, name="Alex Morgan"):
    return {
        "id": roster_id,
        "player_name": name,
        "jersey_number": number,
        "position": "midfielder",
    }


def test_aggregate_votes_sums_fragments_and_returns_winning_read_count():
    assert aggregate_votes(
        {
            "votes": {
                "101": {"12": 20, "17": 2},
                "102": {"12": 23},
                "103": None,
            }
        }
    ) == (12, 43)


def test_aggregate_votes_skips_malformed_values_and_numbers():
    assert aggregate_votes(
        {
            "votes": {
                "101": {"12": None, "13": "4", "bad": 8},
                "102": {"9": 3, "10": -2, "11": True},
                "103": ["not", "votes"],
            }
        }
    ) == (9, 3)


def test_aggregate_votes_tie_uses_lower_number():
    assert aggregate_votes({"votes": {"101": {"12": 4}, "102": {"7": 4}}}) == (7, 4)


@pytest.mark.parametrize("evidence", [{}, {"votes": None}, {"votes": {}}, None])
def test_aggregate_votes_empty(evidence):
    assert aggregate_votes(evidence) == (None, 0)


def test_same_tracklet_window_merge_uses_strictly_less_than_three_second_gap_and_orders():
    merged = merge_windows(
        [
            _window(20, 22, 1),
            _window(0, 2, 1),
            _window(4.99, 7, 1),
            _window(10, 12, 1),
        ]
    )

    assert merged == [
        _window(0, 7, 1),  # 2.99s gap merges for the same bbox owner
        _window(10, 12, 1),  # exactly 3.0s does not merge
        _window(20, 22, 1),
    ]


def test_different_tracklets_do_not_merge_even_when_gap_is_short():
    merged = merge_windows(
        [
            _window(4, 6, 22),
            _window(0, 2, 11),
        ]
    )

    assert merged == [_window(0, 2, 11), _window(4, 6, 22)]


def test_short_windows_are_dropped_only_after_merging():
    merged = merge_windows(
        [
            _window(0, 0.6),
            _window(0.7, 1.2),
            _window(10, 10.99),
        ]
    )

    assert merged == [_window(0, 1.2)]


def test_rank_windows_uses_contamination_confidence_duration_then_start():
    windows = [
        _window(40, 60, 4),
        _window(30, 34, 3),
        _window(20, 30, 2),
        _window(10, 15, 1),
        _window(0, 30, 5),
    ]
    chains = {
        1: _chain(1, confidence="high"),
        2: _chain(2, confidence="high"),
        3: _chain(3, confidence="high"),
        4: _chain(4, confidence="low"),
        5: _chain(5, confidence="high", contaminated=True),
    }

    assert rank_windows(windows, chains) == [
        _ranked_window(40, 60, 4, 4),
        _ranked_window(30, 34, 3, 3),
        _ranked_window(20, 30, 2, 1),
        _ranked_window(10, 15, 1, 2),
        _ranked_window(0, 30, 5, 5),
    ]


def test_rank_windows_duration_dominates_only_within_same_confidence_class():
    ranked = rank_windows(
        [_window(0, 30, 1), _window(40, 45, 2)],
        {1: _chain(1, confidence="low"), 2: _chain(2, confidence="high")},
    )

    assert ranked == [_ranked_window(0, 30, 1, 2), _ranked_window(40, 45, 2, 1)]


def test_chain_uses_own_span_when_no_member_fragment_resolves():
    payload = build_reel_payload(
        {"our_team_cluster": 0, "capture_meta": {}},
        [_roster()],
        [_chain(11, first=40, last=45, members=[901, "bad"])],
        {902: (1, 2, 1)},
    )

    assert payload["players"][0]["windows"] == [_ranked_window(40, 45, 11, 1)]


def test_chain_uses_persisted_member_spans_without_fragment_map():
    payload = build_reel_payload(
        {"our_team_cluster": 0, "capture_meta": {}},
        [_roster()],
        [
            _chain(
                11,
                first=0,
                last=100,
                members=[901, 902],
                member_spans={"901": [20, 25, 5], "902": [5, 8, 3]},
            )
        ],
    )

    assert payload["players"][0]["windows"] == [
        _ranked_window(5, 8, 11, 2),
        _ranked_window(20, 25, 11, 1),
    ]


def test_malformed_persisted_member_spans_are_skipped():
    payload = build_reel_payload(
        {"our_team_cluster": 0, "capture_meta": {}},
        [_roster()],
        [
            _chain(
                11,
                first=0,
                last=100,
                members=[901, 902, 903, 904],
                member_spans={
                    "901": ["bad", 5, 5],
                    "902": [8, 7, 1],
                    "903": [20, 24, 4],
                    "904": "not-a-span",
                },
            )
        ],
        {901: (30, 35, 5), 902: (40, 45, 5)},
    )

    assert payload["players"][0]["windows"] == [_ranked_window(20, 24, 11, 1)]


def test_chain_member_ids_resolve_through_persisted_fragment_pipeline_keys():
    fragment = {
        **_chain(12, roster_entry_id=None, first=7, last=9, visible=2),
        "kind": "fragment",
        "pipeline_key": "E901",
        "evidence": None,
    }
    payload = build_reel_payload(
        {"our_team_cluster": 0, "capture_meta": {}},
        [_roster()],
        [_chain(11, first=0, last=100, members=["901"]), fragment],
    )

    assert payload["players"][0]["windows"] == [_ranked_window(7, 9, 11, 1)]


def test_player_total_visible_comes_from_merged_windows_not_chain_span():
    payload = build_reel_payload(
        {"our_team_cluster": 0, "capture_meta": {}},
        [_roster()],
        [_chain(11, first=0, last=100, visible=8, members=[1, 2, 3])],
        {1: (30, 34, 4), 2: (0, 2, 2), 3: (5, 7, 2)},
    )

    player = payload["players"][0]
    assert player["windows"] == [
        _ranked_window(0, 2, 11, 2),
        _ranked_window(5, 7, 11, 3),
        _ranked_window(30, 34, 11, 1),
    ]
    assert player["total_visible_s"] == 8
    assert player["total_visible_s"] != 100


def test_player_chains_include_identity_evidence_shape():
    fragment = {
        **_chain(13, suggested_number=99, votes={"1": {"99": 50}}),
        "kind": "fragment",
        "pipeline_key": "E13",
    }
    payload = build_reel_payload(
        {"our_team_cluster": 0, "capture_meta": {}},
        [_roster(number=12)],
        [
            _chain(
                11,
                suggested_number=17,
                votes={"101": {"12": 20, "17": 2}, "102": {"12": 23}},
                confidence="high",
            ),
            _chain(
                12,
                suggested_number=4,
                votes=None,
                confidence="low",
                contaminated=True,
                first=20,
                last=30,
            ),
            fragment,
        ],
    )

    assert payload["players"][0]["chains"] == [
        {
            "tracklet_id": 11,
            "suggested_number": 17,
            "voted_number": 12,
            "vote_total": 43,
            "confidence": "high",
            "contaminated": False,
        },
        {
            "tracklet_id": 12,
            "suggested_number": 4,
            "voted_number": None,
            "vote_total": 0,
            "confidence": "low",
            "contaminated": True,
        },
    ]


@pytest.mark.parametrize(
    ("chain", "expected"),
    [
        (_chain(1, suggested_number=8, votes={"1": {"12": 6}}), True),
        (_chain(1, suggested_number=17, votes={"1": {"8": 6}}), False),
        (_chain(1, suggested_number=12, votes=None), True),
        (_chain(1, suggested_number=None, votes=None), False),
        (_chain(1, suggested_number=None, votes={"1": None}), False),
    ],
)
def test_player_number_mismatch_uses_votes_then_suggestion_and_is_none_safe(chain, expected):
    payload = build_reel_payload(
        {"our_team_cluster": 0, "capture_meta": {}},
        [_roster(number=8)],
        [chain],
    )

    assert payload["players"][0]["number_mismatch"] is expected


@pytest.mark.parametrize(
    ("tracklets", "expected"),
    [
        ([_chain(1), _chain(2)], "high"),
        ([_chain(1, confidence="low"), _chain(2, confidence="low", contaminated=True)], "low"),
        ([_chain(1), _chain(2, confidence="low")], "mixed"),
        ([_chain(1, contaminated=True)], "mixed"),
    ],
)
def test_confidence_high_low_and_mixed(tracklets, expected):
    assert reel_confidence(tracklets) == expected


def test_dismissed_tracklets_are_excluded_from_players_unassigned_and_overview():
    payload = build_reel_payload(
        {"our_team_cluster": 0, "capture_meta": {}},
        [_roster()],
        [
            _chain(1, first=0, last=5, visible=5),
            _chain(2, first=10, last=30, visible=20, dismissed=True),
            _chain(3, roster_entry_id=None, cluster=1, visible=40, dismissed=True),
        ],
    )

    assert payload["players"][0]["tracklet_ids"] == [1]
    assert payload["unassigned"] == {"count": 0, "visible_s": 0}
    assert payload["team_overview"]["clusters"] == [
        {"cluster": 0, "is_ours": True, "players": [1], "total_visible_s": 5.0}
    ]


def test_team_overview_lists_present_clusters_and_maps_our_side():
    payload = build_reel_payload(
        {"our_team_cluster": 1, "capture_meta": {"qwen_analysis": {"match_summary": "Sampled."}}},
        [_roster(1), _roster(2, 10, "Sam Lee")],
        [
            _chain(1, roster_entry_id=1, cluster=1, visible=12),
            _chain(2, roster_entry_id=2, cluster=1, visible=8),
            _chain(3, roster_entry_id=None, cluster=0, visible=30),
        ],
    )

    assert payload["team_overview"] == {
        "clusters": [
            {"cluster": 0, "is_ours": False, "players": [], "total_visible_s": 30.0},
            {"cluster": 1, "is_ours": True, "players": [1, 2], "total_visible_s": 20.0},
        ],
        "qwen_analysis_present": True,
    }


def test_is_ours_is_null_when_match_side_is_unset():
    payload = build_reel_payload(
        {"our_team_cluster": None, "capture_meta": None},
        [_roster()],
        [_chain(1)],
    )

    assert payload["team_overview"]["clusters"][0]["is_ours"] is None
    assert payload["team_overview"]["qwen_analysis_present"] is False


def test_empty_roster_has_no_players_and_counts_unassigned_chains_only():
    payload = build_reel_payload(
        {"our_team_cluster": None, "capture_meta": {}},
        [],
        [
            _chain(1, roster_entry_id=None, visible=12),
            _chain(2, roster_entry_id=None, visible=8),
            {
                **_chain(3, roster_entry_id=None, visible=99),
                "kind": "fragment",
                "pipeline_key": "E3",
            },
        ],
    )

    assert payload["players"] == []
    assert payload["unassigned"] == {"count": 2, "visible_s": 20.0}


@pytest.mark.parametrize("direction", ["left", "right"])
def test_markers_patch_accepts_attack_direction_and_merges_capture_meta(direction):
    app = Flask(__name__)
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:")
    db.init_app(app)
    match = type(
        "Match",
        (),
        {
            "capture_meta": {"camera": "touchline", "qwen_analysis": {"match_summary": "kept"}},
            "status": "uploaded",
            "to_dict": lambda self: {"capture_meta": self.capture_meta},
        },
    )()

    with app.test_request_context(json={"attack_direction_first_half": direction}):
        with patch.object(db.session, "get", return_value=match), patch.object(db.session, "commit"):
            response = update_video_match.__wrapped__(1)

    assert response.json["capture_meta"] == {
        "camera": "touchline",
        "qwen_analysis": {"match_summary": "kept"},
        "attack_direction_first_half": direction,
    }


def test_markers_patch_rejects_unknown_attack_direction_without_committing():
    app = Flask(__name__)
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:")
    db.init_app(app)
    match = type("Match", (), {"capture_meta": {"camera": "touchline"}})()

    with app.test_request_context(json={"attack_direction_first_half": "upfield"}):
        with patch.object(db.session, "get", return_value=match), patch.object(db.session, "commit") as commit:
            response, status = update_video_match.__wrapped__(1)

    assert status == 400
    assert response.json == {"error": "attack_direction_first_half must be left or right"}
    assert match.capture_meta == {"camera": "touchline"}
    commit.assert_not_called()
