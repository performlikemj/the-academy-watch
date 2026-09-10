"""Guard TRAIN-only calibration, geometry and replay eligibility."""

import math
import pytest
from fair_protocol import mcnemar, threshold_for_budget
from round5_data import is_hard, transform_boxes
from train_round5 import Plateau


def test_train_threshold_ties_and_held_out_independence():
    labels = {("train", 0): {"visible": False}, ("held", 0): {"visible": False}}
    outputs = {
        "train": {
            "frames": [
                {
                    "t": 0,
                    "detections": [
                        {"confidence": 0.5},
                        {"confidence": 0.5},
                        {"confidence": 0.2},
                    ],
                }
            ]
        },
        "held": {"frames": [{"t": 0, "detections": [{"confidence": 0.99}]}]},
    }
    op = threshold_for_budget(outputs, labels, ["train"], 20)
    assert op["threshold"] == math.nextafter(0.5, math.inf)
    assert op["achieved_false_boxes"] == 0  # cannot split a tied score
    outputs["held"]["frames"][0]["detections"] *= 100
    assert threshold_for_budget(outputs, labels, ["train"], 20) == op


def test_native_zoom_translation_and_flip_preserve_box_geometry():
    assert transform_boxes([[470, 260, 490, 280]], 1.2, 10, 20) == [
        [478, 278, 502, 302]
    ]
    assert transform_boxes([[470, 260, 490, 280]], 1.2, 10, 20, True) == [
        [458, 278, 482, 302]
    ]
    assert transform_boxes([[1, 1, 2, 2]], 1.2, -48, -27) == []


def test_replay_preserves_click_distance_and_ignores_padding():
    assert not is_hard([[100, 100, 20, 20]], [0.9], [100, 100])
    assert not is_hard([[120, 100, 20, 20]], [0.9], [100, 100])
    assert is_hard([[121, 100, 20, 20]], [0.3], [100, 100])
    assert not is_hard([[10, 600, 20, 20]], [0.9], None)
    assert not is_hard([[10, 10, 20, 20]], [0.299], None)
    assert is_hard([[10, 10, 20, 20]], [0.3], None)


def test_train_plateau_relative_improvement_and_invalid_loss():
    p = Plateau()
    assert not p.update(10)
    assert not p.update(9.95)
    assert not p.update(9.8)
    assert not p.update(9.79)
    assert not p.update(9.78)
    assert p.update(9.77)
    with pytest.raises(ValueError):
        p.update(math.nan)


def test_exact_mcnemar_reviewer_discordances():
    candidate = {i: i < 16 for i in range(24)}
    baseline = {i: i >= 16 for i in range(24)}
    r = mcnemar(candidate, baseline)
    assert (r["wins"], r["losses"]) == (16, 8)
    assert r["exact_two_sided_p"] == pytest.approx(0.15158963203430176)


def test_rf_final_selection_uses_declared_false_constraint_and_excludes_yolo():
    from review_round5 import select_rf

    def row(recall, false):
        return {
            "operating_points": {
                "1": {
                    "held": {
                        "groups": {
                            "on_ball": {"top1_recall": recall},
                            "all": {"false_per_10s": false},
                        }
                    }
                }
            }
        }

    rows = {
        "yolo-r2-b": row(1, 0),
        "rf-b": row(0.75, 3),
        "rf-r5-a": row(0.70, 1.5),
        "rf-r5-b": row(0.72, 2),
    }
    assert select_rf(rows) == "rf-r5-b"
    rows["rf-r5-b"] = row(0.90, 4)
    assert select_rf(rows) == "rf-r5-a"
    rows["rf-r5-a"] = row(0.70, 3.5)
    assert select_rf(rows) == "rf-b"  # explicitly unqualified fallback
    assert select_rf(rows, only_new=True) == "rf-r5-a"


def test_new_evaluation_requires_both_final_fits_and_rejects_changed_weights(tmp_path):
    import json
    from common import sha256
    from round5_inference import evaluation_marker

    for letter in "ab":
        directory = tmp_path / f"mj-r5-rf-{letter}"
        directory.mkdir()
        (directory / "weights.pt").write_bytes(b"test checkpoint, not model data")
    first = tmp_path / "mj-r5-rf-a"
    (first / "fit_summary.json").write_text(
        json.dumps({"weights_sha256": sha256(first / "weights.pt")})
    )
    with pytest.raises(FileNotFoundError):
        evaluation_marker(tmp_path)
    assert not (tmp_path / "round5-evaluation-start.json").exists()
    second = tmp_path / "mj-r5-rf-b"
    (second / "fit_summary.json").write_text(
        json.dumps({"weights_sha256": sha256(second / "weights.pt")})
    )
    evaluation_marker(tmp_path)
    original = (tmp_path / "round5-evaluation-start.json").read_bytes()
    evaluation_marker(tmp_path)
    assert (tmp_path / "round5-evaluation-start.json").read_bytes() == original
    (second / "weights.pt").write_bytes(b"changed")
    with pytest.raises(ValueError, match="checkpoint changed"):
        evaluation_marker(tmp_path)


def test_benchmark_excludes_foreign_activity_but_allows_its_own_gpu_use():
    from benchmark_activity import busy

    sample = {
        "comfy": {"queue_running": 0, "queue_pending": 0},
        "clients": [],
        "new_clients": [],
        "gpu_percent": 0,
    }
    assert not busy(sample, preflight=True)
    assert busy({**sample, "gpu_percent": 89}, preflight=True)
    assert not busy({**sample, "gpu_percent": 89})
    assert busy({**sample, "clients": [{"name": "llama-server", "cpu_percent": 2}]})
    assert busy({**sample, "new_clients": [123]})
    assert busy({**sample, "comfy": {"queue_running": 1}})


def test_benchmark_wait_is_bounded_and_media_is_nonblocking(monkeypatch):
    from types import SimpleNamespace
    import benchmark_activity as mod

    sample = {
        "comfy": {},
        "clients": [
            {"name": "mediaanalysisd", "cpu_percent": 250},
            {"name": "PhotosReliveWidget", "cpu_percent": 100},
        ],
        "new_clients": [],
        "gpu_percent": 0,
    }
    assert not mod.busy(sample, preflight=True)
    assert mod.busy(
        {**sample, "bench_jobs": [{"pid": 123, "script": "train_round5.py"}]}
    )
    assert mod.busy({**sample, "clients": [{"name": "ollama", "cpu_percent": 50}]})
    assert mod.bench_job(
        123, ["python", "spike/video-analysis/ball/round5_inference.py"]
    )
    assert mod.bench_job(123, ["python", "spike/video-analysis/bench/run_bench.py"])
    assert mod.bench_job(123, ["python", "spike/video-analysis/ball/run_round4.py"])
    assert mod.bench_job(
        123, ["python", "run_bench.py"], "/tmp/spike/video-analysis/bench"
    )
    assert mod.bench_job(123, ["python", "unrelated.py"]) is None
    activity = object.__new__(mod.Activity)
    activity.max_wait_s = 900
    activity.waited_s = 899
    activity.thread = SimpleNamespace(is_alive=lambda: True)
    activity.samples = [{**sample, "comfy": {"queue_running": 1}}] * 3
    clock = [100.0]
    monkeypatch.setattr(mod.time, "perf_counter", lambda: clock[0])
    monkeypatch.setattr(
        mod.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds)
    )
    assert activity.wait_idle()["timing_status"] == "contended (steady background load)"
    assert activity.waited_s == 900
    assert activity.wait_idle()["quiet_wait_total_s"] == 900
    assert clock[0] == 101
