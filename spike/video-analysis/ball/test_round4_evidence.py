"""Executed RF-DETR provenance, paired denominators and aggregate fixture checks."""

from __future__ import annotations

import gzip
import hashlib
import json
import math

import pytest

from common import HERE, sha256
from review_round4 import beats_bar, select_rf
from round2_analysis import gate


def evidence():
    return json.loads(
        gzip.decompress((HERE / "fixtures/round4_scored_output.json.gz").read_bytes())
    )


def test_rf_two_fits_use_train_geometry_and_final_checkpoints():
    e = evidence()
    p = json.loads((HERE / "fixtures/round4_execution.json").read_text())
    assert set(e["fits"]) == {"a", "b"}
    assert e["evaluation_start"]["fit_state_sha256"] == e["fit_state_sha256"]
    snapshot = (
        json.dumps(e["evaluation_start"]["protocol_snapshot"], indent=2, sort_keys=True)
        + "\n"
    ).encode()
    assert (
        hashlib.sha256(snapshot).hexdigest() == e["evaluation_start"]["protocol_sha256"]
    )
    for name, digest in p["training_code_sha256"].items():
        assert sha256(HERE / name) == digest
    # During run a only the broken upstream tag URL was corrected, no training code.
    original = (
        (HERE / "train_tiny_ball_rfdetr.py")
        .read_bytes()
        .replace(b"blob/develop/LICENSE", b"blob/v1.7.1/LICENSE")
    )
    assert (
        hashlib.sha256(original).hexdigest()
        == p["run_a_code_sha256_at_start"]["train_tiny_ball_rfdetr.py"]
    )
    assert p["run_a_code_sha256_at_start"]["rfdetr_data.py"] == sha256(
        HERE / "rfdetr_data.py"
    )
    for c, fit in e["fits"].items():
        assert fit["model"] == "RFDETRNano"
        assert fit["licence"] == "Apache-2.0" and fit["device"] == "mps"
        assert fit["versions"]["rfdetr"] == "1.7.1"
        assert fit["resolution"] == (640 if c == "a" else 960)
        assert fit["batch"] == 8 and fit["gradient_accumulation"] == 1
        assert fit["seed"] == 42 and fit["patience"] == 6
        assert fit["training_s"] < 1800 and fit["budget_minutes"] == 29
        assert fit["checkpoint_selection"].startswith("FINAL optimizer step")
        assert not fit["train_config"]["use_ema"]
        assert fit["images_seen"] == sum(r["images"] for r in fit["history"])
        assert fit["optimizer_steps"] == sum(
            math.ceil(r["images"] / 8) for r in fit["history"]
        )
        assert fit["epochs_complete"] == sum(r["complete"] for r in fit["history"])
        d = e["datasets"][c]
        assert d["counts"] == {
            "train": 3012,
            "val": 0,
            "positive_tiles": 631,
            "negative_tiles": 2381,
        }
        assert not d["pseudo"]
        scale = d["box_recipe"]
        assert scale["mode"] == "train_affine_with_minimum"
        assert scale["clip_px"] == [18.680435180664062, 48]
        assert scale["observations"] == 545
        assert scale["r_squared"] == pytest.approx(0.49435065660963573)
        assert set(scale["fit_clips"]) == set(p["split"]["train"])
        assert not set(scale["fit_clips"]) & set(p["split"]["held_out"])
        assert d["target_distribution"]["at_floor"] == 592
        assert d["target_distribution"]["ge24"] == 23
        assert d["labels_sha256"] == fit["labels_sha256"] == e["labels_sha256"]
        saved = e["saved_passes"][f"tinyball-r4-rf-{c}"]
        assert saved["frames"] == 1105
        assert saved["weights_sha256"] == fit["weights_sha256"]
    assert e["fits"]["b"]["initial_weights_sha256"] == e["fits"]["a"]["weights_sha256"]


def test_rf_paired_headlines_buckets_controls_and_selection_are_honest():
    e = evidence()
    assert len(e["results"]) == 5
    assert e["current_best_licence_clean"] == select_rf(e["results"])
    bar = next(r for r in e["results"] if r["candidate"] == "tinyball-r2-b")
    assert bar["held"]["groups"]["on_ball"]["top1_recall"] == pytest.approx(83 / 122)
    assert bar["held"]["groups"]["on_ball"]["manual_top1_recall"] == 0.44
    assert bar["held"]["groups"]["all"]["false_per_10s"] == pytest.approx(5 / 3)
    expected = [
        r["candidate"]
        for r in e["results"]
        if r["candidate"].startswith("tinyball-r4-rf-") and beats_bar(r, bar)
    ]
    assert e["improvements_over_r2_b"] == expected
    old = json.loads(
        gzip.decompress((HERE / "fixtures/round3_scored_output.json.gz").read_bytes())
    )
    for r in e["results"]:
        if not r["candidate"].startswith("tinyball-r4-rf-"):
            assert r == next(
                v for v in old["results"] if v["candidate"] == r["candidate"]
            )
        for scope in ("all", "held"):
            g = r[scope]["groups"]
            assert g["all"]["visible"] == (875 if scope == "all" else 244)
            assert g["on_ball"]["visible"] == (422 if scope == "all" else 122)
            assert g["all"]["no_ball_frames"] == (182 if scope == "all" else 60)
            assert g["on_ball"]["top1_recall"] <= g["on_ball"]["oracle_recall"]
            assert r[scope]["gate"] == gate(g)
            for rule, key in (("top1", "top1_matched"), ("oracle", "matched")):
                errors = e["errors"][r["candidate"]][rule][scope]
                assert errors["visible"] - errors["misses"] == g["on_ball"][key]
                for buckets in errors["buckets"].values():
                    assert (
                        sum(b["matched"] for b in buckets.values()) == g["on_ball"][key]
                    )
            path = e["path_sensitivity"][r["candidate"]][scope]
            assert path["strict_false_per_10s"] == g["all"]["false_per_10s"]
            assert (
                0 <= path["path_credited_false_per_10s"] <= path["strict_false_per_10s"]
            )
            t = r[scope]["tracks"]["groups"]["all"]
            if t["track_points_on_visible_frames"]:
                assert (
                    t["wrong_per_track_point"]
                    == t["wrong_object_frames"] / t["track_points_on_visible_frames"]
                )
                assert (
                    t["track_precision"]
                    == t["covered"] / t["track_points_on_visible_frames"]
                )
    assert e["controls"]["seed"] == 20260911 and e["controls"]["repeats"] == 100
    for scope in ("all", "held"):
        for method in ("shuffled_within_clip", "uniform_random"):
            assert set(e["controls"]["results"][scope][method]) == {
                "tinyball-r4-rf-a",
                "tinyball-r4-rf-b",
            }
    raw = json.dumps(e)
    assert all(k not in raw for k in ('"x":', '"y":', '"xy":', '"hit":'))
