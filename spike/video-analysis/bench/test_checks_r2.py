"""Saved 8B distributions, note corrections, sampling confound and regeneration."""

import copy
import json
from pathlib import Path

import pytest

from checks_score import score_run, threshold_results
from checks_truth import derive_truth
from compare_checks import main
from test_checks import FIXTURES, comparison_fixture, raw, read

SAVED = json.loads(
    (Path(__file__).parent / "fixtures/checks_8b_answers.json").read_text()
)


def saved_truths():
    return {
        f["truth"]["clip_id"]: {
            **f["truth"],
            "window": SAVED["windows"][f["truth"]["clip_id"]],
        }
        for f in FIXTURES
    }


@pytest.mark.parametrize("run", list(SAVED["runs"]))
def test_real_8b_priors_and_touch_sampling(run):
    m = score_run(SAVED["runs"][run], saved_truths())["overall"]
    q = m["questions"]["player_touches_ball"]
    assert q["answer_distribution"] == {"no": 20}
    assert q["modal_answer_share"] == 1 and q["modal_answer"] == "no"
    assert q["accuracy"] == q["majority_baseline_accuracy"] == 9 / 15
    assert q["accuracy_minus_baseline"] == 0 and not q["information"]
    assert m["touch_yes_count"] == 0 and m["touch_truth_positive_count"] == 6
    assert m["touch_recall_raw"] == 0 and m["touch_recall"] is None
    assert "mean frame spacing exceeds" in m["touch_recall_reason"]
    assert threshold_results(m)["gate2"]["status"] == "WITHHELD"
    assert m["gates"]["off_pitch_player_on_pitch"]["truth_no_count"] == 7
    assert m["gates"]["off_pitch_play_in_progress"]["truth_no_count"] == 7
    assert m["gates"]["off_pitch"]["truth_no_count"] == 14
    if run.endswith("dense"):
        for name in ("player_on_pitch", "player_running"):
            assert m["questions"][name]["answer_distribution"] == {"yes": 20}
        assert m["questions"]["kit_color_seen"]["answer_distribution"] == {"red": 20}
        assert m["questions"]["ball_near_player"]["answer_distribution"]["no"] == 18
        assert m["questions"]["player_on_pitch"]["accuracy"] == 12 / 19
        assert (
            m["questions"]["player_on_pitch"]["majority_baseline_accuracy"] == 12 / 19
        )
        assert m["questions"]["player_running"]["accuracy"] == 4 / 13
        assert m["questions"]["player_running"]["majority_baseline_accuracy"] == 9 / 13
    expected_signal = (
        {"play_in_progress"} if run.endswith("dense") else {"ball_near_player"}
    )
    assert {q for q, v in m["questions"].items() if v["information"]} == expected_signal


def moment_read(cid, answer):
    return {**raw(cid, answer=answer), "sent_frames": [{"t": i / 4} for i in range(8)]}


def test_touch_gate_requires_recall_and_passes_with_measurable_signal():
    truths = saved_truths()
    truths = {
        cid: {**t, "window": {"start_s": 0, "end_s": 2}} for cid, t in truths.items()
    }
    positives = [
        cid
        for cid, t in truths.items()
        if derive_truth(t)["expected"]["player_touches_ball"] == "yes"
    ]
    rows = [moment_read(cid, "yes" if cid in positives[:3] else "no") for cid in truths]
    m = score_run(rows, truths)["overall"]
    assert (
        m["touch_recall"] == 0.5 and threshold_results(m)["gate2"]["status"] == "PASS"
    )
    rows = [moment_read(cid, "no") for cid in truths]
    m = score_run(rows, truths)["overall"]
    assert m["off_pitch_idle_touch_false_yes_rate"] == 0
    assert m["touch_recall"] == 0 and threshold_results(m)["gate2"]["status"] == "FAIL"
    assert threshold_results(m, complete=False)["gate2"]["status"] == "WITHHELD"


@pytest.mark.parametrize("duration,measurable", [(1, True), (1.001, False)])
def test_sampling_boundary_and_context_pairs(duration, measurable):
    t = {
        "human_note": "passes",
        "kit_color": "red",
        "window": {"start_s": 0, "end_s": duration},
    }
    row = {**raw("a", answer="yes"), "sent_frames": [{"t": 0}, {"t": duration}]}
    m = score_run([row], {"a": t})["overall"]
    paired = copy.deepcopy(row)
    paired["sent_frames"] *= 2
    assert score_run([paired], {"a": t})["overall"] == m
    assert (m["touch_recall"] is not None) == measurable
    assert m["frames_per_second_of_window"] == {
        "mean": 2 / duration,
        "min": 2 / duration,
    }


def test_missing_sampling_and_failed_touch_remain_visible():
    t = {
        "human_note": "passes",
        "kit_color": "red",
        "window": {"start_s": 0, "end_s": 2},
    }
    rows = [moment_read("a", "yes"), {**moment_read("b", "yes"), "error": "failed"}]
    m = score_run(rows, {"a": t, "b": t})["overall"]
    assert m["touch_yes_count"] == 1 and m["touch_truth_positive_count"] == 2
    assert m["touch_recall"] == 0.5
    rows[0]["sent_frames"] = []
    m = score_run(rows, {"a": t, "b": t})["overall"]
    assert m["touch_recall"] is None and "missing" in m["touch_recall_reason"]


def test_information_and_modal_tie_do_not_depend_on_order():
    truths = {
        str(i): {"human_note": "on sideline" if i < 5 else "passes", "kit_color": "red"}
        for i in range(10)
    }
    rows = [raw(cid, answer="no" if int(cid) < 5 else "yes") for cid in truths]
    m = score_run(rows, truths)["overall"]["questions"]["player_on_pitch"]
    assert m["majority_baseline_accuracy"] == 0.5 and m["accuracy"] == 1
    assert (
        m["information"]
        and m["modal_answer"] == "no"
        and m["modal_answer_share"] == 0.5
    )
    assert (
        score_run(list(reversed(rows)), truths)["overall"]["questions"][
            "player_on_pitch"
        ]
        == m
    )
    for row in rows[:4]:
        row["checks_raw"] = json.dumps(read(answer="yes"))
    m = score_run(rows, truths)["overall"]["questions"]["player_on_pitch"]
    assert m["modal_answer_share"] == 0.9 and not m["information"]


@pytest.mark.parametrize(
    "note,question,expected",
    [
        ("walking off field in warmup suit. misses header", "ball_near_player", "yes"),
        ("walking off field. missed a header", "ball_near_player", "yes"),
        ("multiple challenges for the ball", "player_running", None),
        ("wins challenge and passes", "player_running", None),
        ("receives ball in midfield", "player_running", None),
        ("a bit of running. waits for throw-in", "play_in_progress", None),
        ("waits for throw-in", "play_in_progress", "no"),
    ],
)
def test_corrections_are_rules_not_clip_overrides(note, question, expected):
    assert (
        derive_truth({"clip_id": "arbitrary", "human_note": note})["expected"][question]
        == expected
    )


def test_execution_cli_regenerates_identical_json_and_markdown(tmp_path):
    manifest, runs, _ = comparison_fixture(tmp_path)
    execution = tmp_path / "execution.json"
    execution.write_text(
        json.dumps(
            {"round": "r2", "prompt_history": {"verbatim_diff": "- old\n+ final"}}
        )
    )
    output = tmp_path / "comparison.json"
    md = tmp_path / "comparison.md"
    args = [
        "--reports-root",
        str(tmp_path),
        "--manifest",
        str(manifest),
        "--runs",
        *[f"{k}={v}" for k, v in runs.items()],
        "--execution",
        str(execution),
        "--out-json",
        str(output),
        "--out-md",
        str(md),
    ]
    assert main(args) == 0
    first = output.read_bytes(), md.read_bytes()
    assert main(args) == 0 and first == (output.read_bytes(), md.read_bytes())
    assert json.loads(output.read_text())["execution"] == json.loads(
        execution.read_text()
    )


def test_comparison_keeps_full_touch_denominator_after_a_failed_read(tmp_path):
    from compare_checks import compare

    manifest, runs, ids = comparison_fixture(tmp_path)
    cid = ids[2]  # The only true-touch clip in this smaller comparison fixture.
    path = tmp_path / "dense" / "claims" / f"{cid}.json"
    row = json.loads(path.read_text())
    row["error"] = "saved request failure"
    path.write_text(json.dumps(row))
    result = compare(tmp_path, runs, manifest)
    assert result["comparison_metadata"]["shared_scored_clips"] == 3
    for metrics in result["comparison_metadata"]["paired_overall"].values():
        assert metrics["touch_truth_positive_count"] == 1

    paired = result["comparison_metadata"]["paired_overall"]
    assert paired["dense"]["questions"]["player_on_pitch"]["answer_count"] == 3
    assert paired["prod30"]["questions"]["player_on_pitch"]["answer_count"] == 4
