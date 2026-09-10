"""Adversarial regression controls: top-1, scope, sparse tracks and fixture hygiene."""

from __future__ import annotations
import gzip
import json
import random
import pytest
from common import HERE
from human_score import score_rows, score_track
from matching_controls import control_labels
from review_round3 import select_current
from round2_analysis import gate


def fixture(name):
    return json.loads(gzip.decompress((HERE / "fixtures" / name).read_bytes()))


def test_top1_is_confidence_ranked_not_nearest_and_manual_has_own_denominator():
    rows = [
        {
            "clip": "c",
            "t": 0,
            "detections": [
                {"xy": [0, 0], "confidence": 0.2},
                {"xy": [100, 100], "confidence": 0.9},
            ],
        },
        {"clip": "c", "t": 0.5, "detections": [{"xy": [20, 0], "confidence": 0.8}]},
        {"clip": "c", "t": 1, "detections": [{"xy": [0, 0], "confidence": 0.8}]},
    ]
    labels = {
        ("c", 0): {"visible": True, "x": 0, "y": 0, "source_accepted": True},
        ("c", 0.5): {"visible": True, "x": 0, "y": 0},
        ("c", 1): {"visible": False},
    }
    scored = score_rows(rows, labels)
    assert scored["oracle_recall"] == 1
    assert scored["top1_recall"] == 0.5
    assert scored["manual_top1_recall"] == 1
    assert scored["manual_visible"] == 1
    assert scored["boxes_per_visible_frame"] == 1.5
    assert scored["boxes_per_frame"] == pytest.approx(4 / 3)
    assert scored["top1_precision"] == pytest.approx(1 / 3)
    assert gate({"on_ball": scored, "all": {"false_per_10s": 0}}) == "FAIL"


def test_reviewer_round1_numbers_and_honest_held_out_scope():
    data = fixture("human_measurements.json.gz")
    expected = {
        "rf_full": (57.58, 43.36, 4.73),
        "rf_2x2": (83.18, 67.77, 7.80),
        "rf_3x3": (87.20, 74.17, 10.81),
        "wasb": (3.55, 3.55, 0.28),
        "wasb_2x2": (18.25, 11.37, 1.33),
        "tinyball-r1-960": (77.73, 77.49, 0.83),
    }
    for r in data["results"]:
        if r["candidate"] not in expected:
            continue
        on = r["groups"]["on_ball"]
        oracle, top, boxes = expected[r["candidate"]]
        assert on["oracle_recall"] * 100 == pytest.approx(oracle, abs=0.005)
        assert on["top1_recall"] * 100 == pytest.approx(top, abs=0.005)
        assert on["boxes_per_visible_frame"] == pytest.approx(boxes, abs=0.005)
    trained = next(r for r in data["results"] if r["candidate"] == "tinyball-r1-960")
    on = trained["held_out_groups"]["on_ball"]
    assert trained["headline_scope"] == "held-out only"
    assert on["top1_recall"] == pytest.approx(71 / 122)
    assert on["oracle_recall"] == pytest.approx(72 / 122)
    assert on["precision"] == pytest.approx(72 / 86)
    assert trained["held_out"]["no_ball_frames"] == 144


def test_track_precision_uses_emitted_points_and_coverage_penalises_silence():
    rows = [
        {"clip": "c", "t": i / 2, "detections": [{"xy": [100, 100], "confidence": 0.9}]}
        for i in range(3)
    ]
    labels = {
        ("c", i / 2): {"visible": True, "x": 100 if i < 2 else 900, "y": 100}
        for i in range(3)
    }
    scored = score_track(rows, labels, 1.5)
    assert scored["track_precision"] == pytest.approx(2 / 3)
    assert scored["wrong_per_track_point"] == pytest.approx(1 / 3)
    silent = score_track([{**r, "detections": []} for r in rows], labels, 1.5)
    assert silent["coverage"] == 0
    assert silent["track_precision"] is None
    assert silent["wrong_per_track_point"] is None
    expected = {
        "rf_2x2": (491, 874),
        "rf_3x3": (557, 875),
        "wasb": (311, 354),
        "tinyball-r1-960": (58, 576),
    }
    for row in fixture("human_measurements.json.gz")["results"]:
        if row["candidate"] in expected:
            wrong, points = expected[row["candidate"]]
            t = row["tracks"]["groups"]["all"]
            assert (t["wrong_object_frames"], t["track_points_on_visible_frames"]) == (
                wrong,
                points,
            )
            assert t["wrong_per_track_point"] == pytest.approx(wrong / points)
            assert t["track_precision"] == pytest.approx(t["covered"] / points)


def test_controls_preserve_clip_membership_counts_and_original_labels():
    labels = {("a", i): {"visible": True, "x": i + 1, "y": i + 2} for i in range(10)}
    labels[("b", 0)] = {"visible": True, "x": 500, "y": 600}
    labels[("a", 20)] = {"visible": False}
    raw = json.dumps(list(labels.values()), sort_keys=True)
    shuffled = control_labels(
        labels,
        "shuffled_within_clip",
        random.Random(42),
        {"a": (1920, 1080), "b": (1920, 1080)},
    )
    assert sorted(
        (r["x"], r["y"]) for (c, _), r in shuffled.items() if c == "a" and r["visible"]
    ) == [(i + 1, i + 2) for i in range(10)]
    assert shuffled[("b", 0)] == labels[("b", 0)]
    assert shuffled[("a", 20)] == labels[("a", 20)]
    assert shuffled != labels
    randomised = control_labels(
        labels,
        "uniform_random",
        random.Random(42),
        {"a": (1920, 1080), "b": (1920, 1080)},
    )
    assert all(
        0 <= r["x"] <= 1920 and 0 <= r["y"] <= 1080
        for r in randomised.values()
        if r["visible"]
    )
    assert json.dumps(list(labels.values()), sort_keys=True) == raw


def test_permanent_controls_are_a_floor_not_alternate_truth():
    evidence = fixture("round3_scored_output.json.gz")
    controls = evidence["controls"]
    assert controls["seed"] == 20260911 and controls["repeats"] == 100
    for scope in ("all", "held"):
        for row in evidence["results"]:
            on = row[scope]["groups"]["on_ball"]
            for method in ("shuffled_within_clip", "uniform_random"):
                floor = controls["results"][scope][method][row["candidate"]]["on_ball"]
                assert floor["top1_recall"]["mean"] < on["top1_recall"]
                assert floor["oracle_recall"]["mean"] < on["oracle_recall"]
                assert floor["oracle_recall"]["mean"] < (
                    0.15 if method == "shuffled_within_clip" else 0.02
                )
    sensitivity = evidence["path_sensitivity_r1_original_split"]
    assert sensitivity["all"]["credits"] == 2
    assert sensitivity["held"]["credits"] == 1
    assert sensitivity["all"]["path_credited_false_per_10s"] == pytest.approx(
        20 * 20 / 182
    )
    assert sensitivity["all"]["path_credited_false_per_10s"] > 1
    raw = json.dumps(evidence)
    assert all(key not in raw for key in ('"x":', '"y":', '"xy":', '"hit":'))


def test_current_best_rule_is_held_out_top1_with_false_ceiling():
    def row(name, top, oracle, false):
        return {
            "candidate": name,
            "held": {
                "groups": {
                    "on_ball": {"top1_recall": top, "oracle_recall": oracle},
                    "all": {"false_per_10s": false},
                }
            },
        }

    rows = [
        row("tinyball-r2-a", 0.9, 0.95, 2.01),
        row("tinyball-r2-b", 0.7, 0.8, 2),
        row("tinyball-r3-a", 0.69, 0.99, 1),
    ]
    assert select_current(rows) == "tinyball-r2-b"
    assert select_current(rows[:1]) is None
    assert select_current([row("tinyball-r3-b", 0.7, 0.7, 1), *rows]) == "tinyball-r3-b"


def test_two_scale_fits_preserve_recipe_and_never_fit_held_out_geometry():
    from common import sha256

    evidence = fixture("round3_scored_output.json.gz")
    protocol = json.loads((HERE / "fixtures/round3_execution.json").read_text())
    old = fixture("round2_measurements.json.gz")["selection"]["fits"]
    assert set(evidence["fits"]) == {"a", "b"}
    assert len(evidence["results"]) == 13
    assert evidence["current_best"] == select_current(evidence["results"])
    assert (
        evidence["evaluation_start"]["fit_state_sha256"] == evidence["fit_state_sha256"]
    )
    for name, digest in protocol["training_code_sha256"].items():
        assert sha256(HERE / name) == digest
    for letter, fit in evidence["fits"].items():
        assert fit["device"] == "mps"
        for key in (
            "initial_weights_sha256",
            "model_input_px",
            "epochs_requested",
            "fit_budget_minutes",
            "batch",
            "patience",
            "labels_sha256",
            "source_sha256",
            "split",
        ):
            assert fit[key] == old[letter][key]
        assert fit["best_train_loss"] == min(fit["train_loss_history"])
        dataset = evidence["datasets"][letter]
        assert dataset["counts"] == {
            "train": 3012,
            "val": 0,
            "positive_tiles": 631,
            "negative_tiles": 2381,
        }
        scale = dataset["box_recipe"]
        assert scale["clip_px"] == [6, 48]
        assert set(scale["fit_clips"]) == set(protocol["split"]["train"])
        assert not set(scale["fit_clips"]) & set(protocol["split"]["held_out"])
        assert scale["observations"] == 545 and scale["fallback_labels"] == 86
        assert scale["r_squared"] == pytest.approx(0.49435065660963573)
        saved = evidence["saved_passes"][f"tinyball-r3-{letter}"]
        assert saved["frames"] == 1105
        assert saved["weights_sha256"] == fit["weights_sha256"]
    for row in evidence["results"]:
        for scope in ("all", "held"):
            assert row[scope]["gate"] == gate(row[scope]["groups"])
        if row["candidate"] not in evidence["errors"]:
            continue
        for rule, metric in (("oracle", "matched"), ("top1", "top1_matched")):
            for scope in ("all", "held"):
                summary = evidence["errors"][row["candidate"]][rule][scope]
                group = row[scope]["groups"]["on_ball"]
                assert summary["visible"] - summary["misses"] == group[metric]
                for buckets in summary["buckets"].values():
                    assert (
                        sum(v["visible"] for v in buckets.values())
                        == summary["visible"]
                    )
                    assert (
                        sum(v["misses"] for v in buckets.values()) == summary["misses"]
                    )
