"""Truth scoring boundaries, no-ball denominators, track identity, frozen evidence."""

import json
from pathlib import Path

import pytest

from human_score import score_rows, score_track
from train_tiny_ball import split_clips
from compare_ball import load_measurements
from human_loop import frame_catalog


def test_truth_matching_and_no_ball_exposure():
    rows = [
        {
            "clip": "c",
            "t": 0,
            "detections": [{"xy": [20, 0]}, {"xy": [20, 0]}, {"xy": [20.001, 0]}],
        },
        {"clip": "c", "t": 0.5, "detections": [{"xy": [0, 0]}, {"xy": [0, 0]}]},
        {"clip": "c", "t": 1, "detections": [{"xy": [0, 0]}] * 100},
    ]
    labels = {
        ("c", 0): {"visible": True, "x": 0, "y": 0},
        ("c", 0.5): {"visible": False},
    }
    result = score_rows(rows, labels)
    assert result["recall"] == 1
    assert (
        result["precision"] == 0.2
    )  # one match; duplicates and no-ball predictions false
    assert result["no_ball_frames"] == 1
    assert result["false_per_frame"] == 2
    assert result["false_per_10s"] == 40
    assert result["matched_box_short_side_px"]["n"] == 0
    assert result["error_px"]["median"] == 20
    assert score_rows(rows, {("c", 0): labels[("c", 0)]})["false_per_frame"] is None


def test_track_runs_do_not_bridge_unknown_labels_or_fragments():
    rows = [
        {"clip": "c", "t": i / 2, "detections": [{"xy": [100, 100], "confidence": 0.9}]}
        for i in range(7)
    ]
    labels = {("c", i / 2): {"visible": True, "x": 100, "y": 100} for i in (0, 1, 3, 4)}
    labels.update({("c", i / 2): {"visible": True, "x": 900, "y": 900} for i in (5, 6)})
    result = score_track(rows, labels, 3.5)
    assert result["coverage"] == pytest.approx(4 / 6)
    assert result["longest_correct_s"] == 1
    assert result["wrong_object_frames"] == 2
    assert result["wrong_object_episodes"] == 1
    assert result["wrong_per_visible"] == pytest.approx(2 / 6)


def test_all_twenty_labelled_clips_reserve_sixteen():
    m = load_measurements()
    labels = {(f["clip"], f["t"]): {} for f in frame_catalog(m)}
    split = split_clips(m, labels)
    assert len(split["train"]) == 4
    assert len(split["held_out"]) == 16
    assert len(set(split["train"]) & set(split["held_out"])) == 0
    on = {f["clip"] for f in frame_catalog(m) if f["class"] == "on_ball"}
    assert len(on & set(split["held_out"])) == 2


def test_human_ledger_regenerates_without_private_labels(tmp_path):
    from build_human_report import generate, PREFIX

    data = generate(tmp_path / "ledger")
    for suffix in (".json", ".md"):
        assert (tmp_path / "ledger").with_suffix(
            suffix
        ).read_bytes() == PREFIX.with_suffix(suffix).read_bytes()
    assert data["labels"]["rows"] == 1057
    assert data["labels"]["no_ball"] == 182
    assert data["labels"]["coverage"]["on_ball"]["covered"] == 506
    assert data["labels"]["extra"] == 452
    assert len(data["results"]) == 7
    assert data["execution"]["held_out_experiments"] == 2
    assert data["execution"]["selected_model"] == "tinyball-r1-960"
    rf = next(r for r in data["results"] if r["candidate"] == "rf_3x3")
    assert rf["groups"]["on_ball"]["matched"] == 368
    assert rf["gate"] == "FAIL"
    assert rf["missing_label_bounds"]["no_ball_false_per_10s_lower_bound"] > 150
    assert rf["missing_label_bounds"]["failure_unavoidable_on_full_frozen_schedule"]
    raw = json.dumps(data)
    assert '"x":' not in raw and '"y":' not in raw
    assert not list(Path(__file__).parent.rglob("*.pt"))


def test_variant_resolution_reaches_warmup_and_saved_pass(monkeypatch, tmp_path):
    import sys
    from types import SimpleNamespace
    import numpy as np
    import train_tiny_ball as training

    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace())
    monkeypatch.setitem(
        sys.modules,
        "cv2",
        SimpleNamespace(COLOR_RGB2BGR=1, cvtColor=lambda image, _: image),
    )
    sample = {"t": 0.0, "sample_index": 0, "frame_index": 0}
    monkeypatch.setattr(
        training,
        "samples",
        lambda _: [(sample, [np.zeros((1080, 1920, 3), dtype=np.uint8)])],
    )
    source = tmp_path / "source"
    source.write_bytes(b"fake source for plumbing test")
    calls = []
    empty = SimpleNamespace(cpu=lambda: SimpleNamespace(tolist=lambda: []))

    def predict(tiles, **kwargs):
        calls.append(kwargs["imgsz"])
        return [
            SimpleNamespace(boxes=SimpleNamespace(xyxy=empty, conf=empty))
            for _ in tiles
        ]

    clip = {
        "clip_id": "c",
        "source_size": [1920, 1080],
        "duration_s": 0.5,
        "video": str(source),
    }
    outputs, suggestions = training.predict_all(
        SimpleNamespace(predict=predict),
        [clip],
        tmp_path,
        "test",
        "cpu",
        "frozen",
        True,
        960,
    )
    assert calls == [960, 960]
    assert suggestions == 0
    assert outputs["c"]["frames"][0]["detections"] == []
