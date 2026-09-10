"""Fair-protocol aggregate provenance and cross-table denominator invariants."""

from __future__ import annotations
import gzip
import hashlib
import json
import math
from common import HERE, sha256
from benchmark_activity import busy


def evidence():
    return json.loads(
        gzip.decompress((HERE / "fixtures/round5_scored_output.json.gz").read_bytes())
    )


def test_fresh_baselines_reproduce_fixed_confidence_review_and_calibration():
    e = evidence()
    expected = {"yolo-r2-b": (83, 5, 81, 86), "rf-b": (91, 14, 91, 92)}
    for name, (fixed_hits, fixed_false, op1_hits, op2_hits) in expected.items():
        row = e["models"][name]
        fixed = row["fixed_0.1_not_comparable"]["held"]["groups"]
        assert fixed["on_ball"]["top1_matched"] == fixed_hits
        assert fixed["all"]["no_ball_predictions"] == fixed_false
        assert (
            row["operating_points"]["1"]["held"]["groups"]["on_ball"]["top1_matched"]
            == op1_hits
        )
        assert (
            row["operating_points"]["2"]["held"]["groups"]["on_ball"]["top1_matched"]
            == op2_hits
        )
    mc = e["models"]["rf-b"]["fixed_0.1_mcnemar"]
    assert (mc["wins"], mc["losses"], mc["n"]) == (16, 8, 122)


def test_each_operating_point_uses_train_budget_and_consistent_cohorts():
    e = evidence()
    for row in e["models"].values():
        assert row["saved_pass_provenance"]["threshold"] == 0.01
        for key, op in row["operating_points"].items():
            assert op["train_no_ball"] == 122
            assert op["allowed_false_boxes"] == int(key) * 6
            assert op["achieved_false_boxes"] <= op["allowed_false_boxes"]
            assert op["achieved_false_per_10s"] <= float(key)
            for scope, vis, no_ball, on in (
                ("train", 631, 122, 300),
                ("held", 244, 60, 122),
            ):
                r = op[scope]
                g = r["groups"]
                assert (
                    g["all"]["visible"],
                    g["all"]["no_ball_frames"],
                    g["on_ball"]["visible"],
                ) == (vis, no_ball, on)
                assert sum(b["visible"] for b in r["size_buckets"].values()) == on
                assert (
                    sum(b["hits"] for b in r["size_buckets"].values())
                    == g["on_ball"]["top1_matched"]
                )
                assert (
                    sum(c["no_ball_predictions"] for c in r["per_clip"])
                    == g["all"]["no_ball_predictions"]
                )
                assert (
                    r["path_sensitivity"]["credits"] <= g["all"]["no_ball_predictions"]
                )
            mc = op["mcnemar_vs_yolo"]
            assert (
                sum(mc[k] for k in ("wins", "losses", "both_hit", "both_miss")) == 122
            )
            curve = [
                r
                for r in row["held_curve_diagnostic_only"]
                if r["threshold"] >= op["threshold"]
            ]
            point = curve[-1]
            assert point["top1_hits"] == op["held"]["groups"]["on_ball"]["top1_matched"]
            assert (
                point["false_boxes"]
                == op["held"]["groups"]["all"]["no_ball_predictions"]
            )


def test_final_checkpoints_and_train_only_replay_provenance():
    e = evidence()
    p = e["protocol"]
    assert len(e["fits"]) == 2
    snapshot = (
        json.dumps(
            e["fit_protocol_at_completion"]["snapshot"], indent=2, sort_keys=True
        )
        + "\n"
    ).encode()
    assert (
        hashlib.sha256(snapshot).hexdigest()
        == e["fit_protocol_at_completion"]["sha256"]
    )
    for name, digest in p["training_code_sha256"].items():
        assert sha256(HERE / name) == digest
    original_a = (
        (HERE / "train_round5.py")
        .read_bytes()
        .replace(
            b"        # The reset COCO ball head is not a trained checkpoint: defer mining.\n",
            b"        _, hard = audit_train(True)\n",
        )
    )
    assert (
        hashlib.sha256(original_a).hexdigest()
        == p["fit_a_training_code_at_launch"]["train_round5.py"]
    )
    for name, fit in e["fits"].items():
        assert fit["licence"] == "Apache-2.0" and fit["versions"]["rfdetr"] == "1.7.1"
        assert fit["checkpoint_selection"] == "FINAL"
        assert (
            e["models"][name]["saved_pass_provenance"]["weights_sha256"]
            == fit["weights_sha256"]
        )
        assert fit["protocol_sha256"] == e["fit_protocol_at_completion"]["sha256"]
        assert fit["images_seen"] == sum(r["views"] for r in fit["history"])
        assert fit["optimizer_steps"] == sum(
            math.ceil(r["views"] / 8) for r in fit["history"]
        )
        assert fit["epochs_complete"] == sum(r["complete"] for r in fit["history"])
        assert fit["split"] == p["split"]
        assert fit["replay"] == (name == "rf-r5-b")
        assert all(
            0 <= r["negative_tiles"] <= r["hard_tiles"] <= 3012
            for r in fit["replay_refreshes"]
        )
        assert e["datasets"][name]["counts"] == {
            "train": 3012,
            "val": 0,
            "positive_tiles": 631,
            "negative_tiles": 2381,
        }
    assert e["kit"]["model"] != "yolo-r2-b"
    assert e["kit"]["confirmed_seed_labels"] == 1057 and e["kit"]["unlabelled"] == 48
    assert e["kit"]["build_version"] == 8
    raw = json.dumps(e)
    assert '"x":' not in raw and '"y":' not in raw


def test_throughput_has_three_interleaved_repeats_and_correct_projection():
    e = evidence()
    t = e["throughput"]
    assert len(t["models"]) == 3
    assert 0 <= t["total_quiet_wait_s"] <= t["quiet_wait_cap_s"] == 900
    for row in t["models"].values():
        assert len(row["repeats"]) == len(row["native_repeats"]) == 3
        assert (
            row["native_median_fps"]
            == sorted(r["fps"] for r in row["native_repeats"])[1]
        )
        assert all(r["frames"] == 192 for r in row["native_repeats"])
        for repeat in row["repeats"] + row["native_repeats"]:
            if repeat["timing_status"].startswith("quiet"):
                assert repeat["busy_polls"] == 0
                assert not busy(repeat["activity_before"], preflight=True)
                assert repeat["maximum_foreign_client_cpu_percent"] < 2
            else:
                assert repeat["timing_status"] == "contended (steady background load)"
            assert repeat["activity_polls_during"] > 0
            samples = repeat["background_caveat_samples"]
            assert len(samples) == repeat["activity_polls_during"]
            assert all(s["mediaanalysisd_cpu_percent"] >= 0 for s in samples)
            assert all(0 <= s["agx_gpu_utilisation_percent"] <= 100 for s in samples)
        assert row["median_fps"] == sorted(r["fps"] for r in row["repeats"])[1]
        assert row["match_2fps_minutes"] == 10800 / row["median_fps"] / 60
        assert (
            row["match_native_minutes"]
            == 5400 * t["native_fps"] / row["native_median_fps"] / 60
        )


def test_selection_uses_final_counts_including_exact_ceiling():
    from review_round5 import select_rf

    e = evidence()
    assert select_rf(e["models"]) == e["best_rf_final_selected"] == "rf-r5-a"
    audit = e["selection_audit"]
    assert audit["rule_unchanged"]
    for name, hits, false in (("rf-b", 91, 9), ("rf-r5-a", 76, 6), ("rf-r5-b", 75, 4)):
        row = audit["rows"][name]
        assert (row["on_ball_hits"], row["false_boxes"]) == (hits, false)
        assert row["no_ball_frames"] == 60
        assert row["false_per_10s"] == 20 * false / 60
        scored = e["models"][name]["operating_points"]["1"]["held"]["groups"]
        assert scored["on_ball"]["top1_matched"] == hits
        assert scored["all"]["no_ball_predictions"] == false
    assert e["kit"]["model"] == audit["selected"]
