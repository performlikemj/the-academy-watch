"""Pure contract tests for Film Room player-reel aggregation."""

import pytest
from src.services.video_reels import build_reel_payload, merge_windows, reel_confidence


def _window(start, end, tracklet_id=1):
    return {"start_s": start, "end_s": end, "tracklet_id": tracklet_id}


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
    dismissed=False,
):
    return {
        "id": tracklet_id,
        "kind": "chain",
        "pipeline_key": f"T{cluster}#{tracklet_id}",
        "team_cluster": cluster,
        "confidence": confidence,
        "contaminated": contaminated,
        "first_s": first,
        "last_s": last,
        "visible_s": visible,
        "evidence": {
            "member_fragment_ids": members or [],
            **({"member_spans": member_spans} if member_spans is not None else {}),
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


def test_chain_uses_own_span_when_no_member_fragment_resolves():
    payload = build_reel_payload(
        {"our_team_cluster": 0, "capture_meta": {}},
        [_roster()],
        [_chain(11, first=40, last=45, members=[901, "bad"])],
        {902: (1, 2, 1)},
    )

    assert payload["players"][0]["windows"] == [_window(40, 45, 11)]


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

    assert payload["players"][0]["windows"] == [_window(5, 8, 11), _window(20, 25, 11)]


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

    assert payload["players"][0]["windows"] == [_window(20, 24, 11)]


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

    assert payload["players"][0]["windows"] == [_window(7, 9, 11)]


def test_player_total_visible_comes_from_merged_windows_not_chain_span():
    payload = build_reel_payload(
        {"our_team_cluster": 0, "capture_meta": {}},
        [_roster()],
        [_chain(11, first=0, last=100, visible=8, members=[1, 2, 3])],
        {1: (30, 34, 4), 2: (0, 2, 2), 3: (5, 7, 2)},
    )

    player = payload["players"][0]
    assert player["windows"] == [_window(0, 2, 11), _window(5, 7, 11), _window(30, 34, 11)]
    assert player["total_visible_s"] == 8
    assert player["total_visible_s"] != 100


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
