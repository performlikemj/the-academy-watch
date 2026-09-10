"""Three-rule denominators and unchanged primary scores from the saved recount."""

import gzip
import json
from common import HERE


def test_match_only_reproduces_review_counts_and_changes_only_off_pitch():
    e = json.loads(
        gzip.decompress((HERE / "fixtures/round5_scored_output.json.gz").read_bytes())
    )
    review = json.loads((HERE / "fixtures/n21_rule_sensitivity.json").read_text())
    assert e["framing"]["n21_three_rules"] == review
    expected = {
        "yolo-r2-b": [10, 14],
        "rf-b": [15, 27],
        "rf-r5-a": [11, 16],
        "rf-r5-b": [9, 18],
    }
    for r in review["rows"]:
        source = e["models"][r["model"]]["operating_points"][r["train_budget"]]["held"][
            "groups"
        ]
        strict = r["rules"]["as_labelled"]
        match = r["rules"]["match_ball_only"]
        assert strict["top1_hits"] == source["all"]["top1_matched"]
        assert strict["false_boxes"] == source["all"]["no_ball_predictions"]
        assert (strict["visible"], strict["false_exposure_frames"]) == (244, 60)
        assert (match["visible"], match["false_exposure_frames"]) == (238, 66)
        assert match["false_boxes"] == expected[r["model"]][int(r["train_budget"]) - 1]
        assert match["false_boxes"] == strict["false_boxes"] + r["s0_s5_retained_boxes"]
        assert match["top1_hits"] == strict["top1_hits"] - r["s0_s5_hits_removed"]
        assert r["on_ball_recall_unchanged"] == source["on_ball"]["top1_recall"]
    assert review["scorer_class"] == "off_pitch"


def test_any_ball_is_explicitly_provisional_and_preserves_prior_credit_exposure():
    review = json.loads((HERE / "fixtures/n21_rule_sensitivity.json").read_text())
    for r in review["rows"]:
        a = r["rules"]["any_visible_ball"]
        s = r["rules"]["as_labelled"]
        assert (a["visible"], a["false_exposure_frames"]) == (247, 60)
        assert (
            a["false_boxes"]
            == s["false_boxes"] - r["s8_s10_visible_ball_boxes_credited"]
        )
        assert a["top1_hits"] == s["top1_hits"] + r["s8_s10_provisional_top1_hits"]
        assert a["overall_top1_recall"] == a["top1_hits"] / 247
    assert "not MJ-confirmed new clicks" in review["definition"]
    assert "footwear" in review["definition"]
    assert review["reviewer_flagged_spot_distances_px"] == [86, 142, 164, 158, 118, 77]
    assert review["s0_s5_label_sources"] == ["rf_3x3"] + ["rf_2x2"] * 4 + ["manual"]


def test_direction_compares_same_budget_and_rule_and_a_changes_sign():
    review = json.loads((HERE / "fixtures/n21_rule_sensitivity.json").read_text())
    for row in review["rows"]:
        base = next(
            r
            for r in review["rows"]
            if r["model"] == "yolo-r2-b" and r["train_budget"] == row["train_budget"]
        )
        for rule, r in row["rules"].items():
            b = base["rules"][rule]
            assert r["false_delta_vs_yolo"] == r["false_per_10s"] - b["false_per_10s"]
            assert r["recall_delta_pp_vs_yolo"] == 100 * (
                r["overall_top1_recall"] - b["overall_top1_recall"]
            )
    a = next(
        r
        for r in review["rows"]
        if r["model"] == "rf-r5-a" and r["train_budget"] == "2"
    )
    assert [
        a["rules"][k]["direction_vs_yolo"]["false"]
        for k in ("as_labelled", "any_visible_ball", "match_ball_only")
    ] == ["higher", "lower", "higher"]
