"""Review invariants: unchanged scores, denominator sensitivity and numeric drift."""

from copy import deepcopy
import gzip
import json
from common import HERE
from compare_ball import load_measurements, same_retracking
from round5_framing import HEADLINE


def evidence():
    return json.loads(
        gzip.decompress((HERE / "fixtures/round5_scored_output.json.gz").read_bytes())
    )


def test_matched_false_budgets_use_integer_counts_and_show_crossovers():
    e = evidence()
    expected = {
        3: [69, 74, 63, 68],
        4: [72, 76, 74, 78],
        5: [83, 78, 74, 81],
        6: [86, 79, 79, 87],
        9: [86, 91, 89, 93],
    }
    names = ["yolo-r2-b", "rf-b", "rf-r5-a", "rf-r5-b"]
    for row in e["framing"]["matched_false_rate_diagnostic_only"]:
        count = row["false_boxes_budget"]
        for name in names:
            assert row["hits"][name] == max(
                p["top1_hits"]
                for p in e["models"][name]["held_curve_diagnostic_only"]
                if p["false_boxes"] <= count
            )
        if count in expected:
            assert [row["hits"][n] for n in names] == expected[count]
        assert row["hits"]["rf-r5-b"] >= row["hits"]["rf-r5-a"]
    assert e["framing"]["headline"] == HEADLINE


def test_on_ball_and_strict_false_denominators_are_distinct():
    e = evidence()
    for name, budget, count in [
        ("rf-r5-a", "1", 5),
        ("rf-r5-b", "1", 3),
        ("rf-r5-a", "2", 6),
        ("rf-r5-b", "2", 7),
    ]:
        g = e["models"][name]["operating_points"][budget]["held"]["groups"]
        assert g["on_ball"]["no_ball_frames"] == 46
        assert g["on_ball"]["no_ball_predictions"] == count
        assert g["on_ball"]["false_per_10s"] == count * 20 / 46
        assert g["all"]["no_ball_frames"] == 60
    assert "DO reproduce" in e["selection_audit"]["preview_discrepancy"]


def test_n21_sensitivity_leaves_strict_scores_and_selection_unchanged():
    e = evidence()
    expected = {
        ("yolo-r2-b", "1"): (5, 0),
        ("yolo-r2-b", "2"): (9, 0),
        ("rf-b", "1"): (9, 2),
        ("rf-b", "2"): (20, 3),
        ("rf-r5-a", "1"): (6, 1),
        ("rf-r5-a", "2"): (10, 2),
        ("rf-r5-b", "1"): (4, 1),
        ("rf-r5-b", "2"): (12, 2),
    }
    for r in e["framing"]["n21_sensitivity"]:
        false, credit = expected[r["model"], r["train_budget"]]
        assert (r["strict_false_boxes"], r["n21_visible_ball_boxes"]) == (false, credit)
        assert r["without_visible_ball_boxes_per_10s"] == (false - credit) * 20 / 60
    assert e["best_rf_final_selected"] == e["kit"]["model"] == "rf-r5-a"
    from review_round5 import select_rf

    counterfactual = deepcopy(e["models"])
    counterfactual["rf-r5-a"]["operating_points"]["1"]["held"]["groups"]["all"][
        "false_per_10s"
    ] = 7 * 20 / 60
    assert select_rf(counterfactual) == "rf-r5-b"


def test_timing_summary_flags_four_slowest_repeats_and_has_no_process_samples():
    e = evidence()
    flagged = []
    for name, row in e["throughput"]["models"].items():
        for key in ("repeats", "native_repeats"):
            values = row[key]
            assert row[key + "_fps_range"] == [
                min(r["fps"] for r in values),
                max(r["fps"] for r in values),
            ]
            for r in values:
                if r["media_cpu_ge30"]:
                    assert r["fps"] == min(v["fps"] for v in values)
                    flagged.append((name, key, r["repeat"]))
    assert len(flagged) == 4

    def check(v):
        if isinstance(v, dict):
            assert (
                not {
                    "pid",
                    "pids",
                    "resident_ollama_bytes",
                    "background_caveat_samples",
                    "activity_before",
                }
                & v.keys()
            )
            for item in v.values():
                check(item)
        elif isinstance(v, list):
            for item in v:
                check(item)

    check(e)


def test_epoch_two_budget_two_is_censored_and_only_first_decay_ran():
    e = evidence()
    for letter, count in [("a", 9), ("b", 10)]:
        row = e["learning_curve"][f"rf-r5-{letter} / epoch-2"]["operating_points"]["2"]
        assert row["threshold"] == 0.01
        assert row["achieved_false_boxes"] == count
        assert row["achieved_false_per_10s"] < 2
        assert e["fits"][f"rf-r5-{letter}"]["epochs_complete"] == 3
        assert not e["fits"][f"rf-r5-{letter}"]["history"][-1]["complete"]


def test_retracking_roundoff_tolerance_never_hides_track_or_count_changes():
    saved = load_measurements()["retracking"]
    current = deepcopy(saved)
    current["rf_full"]["groups"]["on_ball"]["continuity"] += 1e-16
    assert same_retracking(current, saved)
    current["rf_full"]["groups"]["on_ball"]["continuity"] += 1e-7
    assert not same_retracking(current, saved)
    current = deepcopy(saved)
    current["rf_full"]["groups"]["on_ball"]["fragments"] += 1
    assert not same_retracking(current, saved)
    current = deepcopy(saved)
    current["rf_full"]["per_clip"][0]["continuity"] += 1e-16
    assert not same_retracking(current, saved)
