"""RF scale/padding, train-only supervision, stopping and selection regressions."""

from __future__ import annotations

import json
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from rfdetr_data import prepare, restore_box, scale_side, square_pad, target_boxes
from review_round4 import beats_bar, select_rf
from train_tiny_ball_rfdetr import TrainStop, export_final


def test_affine_floor_restores_distant_targets_without_overriding_near_targets():
    fit = {"intercept_px": -12.42, "slope_px_per_image_y_px": 0.04821}
    assert scale_side({"y": 100}, fit, 18.68) == 18.68
    assert scale_side({"y": 900}, fit, 18.68) == pytest.approx(30.969)
    assert scale_side({"y": 2000}, fit, 18.68) == 48
    for floor in (float("nan"), 0, 49):
        with pytest.raises(ValueError):
            scale_side({"y": 100}, fit, floor)


def test_square_padding_preserves_pixels_and_inverse_does_not_promote_padding():
    image = np.arange(540 * 960 * 3, dtype=np.uint8).reshape(540, 960, 3)
    padded = square_pad(image)
    assert padded.shape == (960, 960, 3)
    np.testing.assert_array_equal(padded[:540], image)
    assert np.all(padded[540:] == 114)
    # Lower-right native crop; no guessed independent x/y resize factors.
    bounds = (960, 540, 1920, 1080)
    assert restore_box([10, 20, 30, 40], bounds) == [970, 560, 990, 580]
    assert restore_box([10, 600, 30, 620], bounds) is None
    assert restore_box([10, 530, 30, 544], bounds) == [970, 1070, 990, 1080]
    assert restore_box([10, 540, 30, 560], bounds) is None
    assert restore_box([10, 20, 10, 40], bounds) is None


def test_seam_click_belongs_to_one_tile_and_pseudo_is_opt_in():
    label = {"visible": True, "x": 960, "y": 540}
    bounds = [
        (0, 0, 960, 540),
        (960, 0, 1920, 540),
        (0, 540, 960, 1080),
        (960, 540, 1920, 1080),
    ]
    boxes = [target_boxes(label, b, 20) for b in bounds]
    assert boxes == [[], [], [], [[0, 0, 10, 10]]]
    assert target_boxes({"visible": False}, bounds[0], 20) == []
    teacher = [{"xy": [975, 555], "box": [973, 553, 977, 557], "confidence": 0.9}]
    label = {"visible": True, "x": 968, "y": 548}
    assert len(target_boxes(label, bounds[3], 20, teacher)) == 1
    assert len(target_boxes(label, bounds[3], 20, teacher, True)) == 2


def test_prepare_never_decodes_held_out_or_calls_unlabelled_negative(
    monkeypatch, tmp_path
):
    import rfdetr_data

    labels = {
        ("train", 0): {"visible": True, "x": 100, "y": 100},
        ("train", 1): {"visible": True, "x": 1000, "y": 900},
        ("train", 2): {"visible": False},
        ("held", 0): {"visible": True, "x": 100, "y": 999999},
    }

    def detection(x, y, size):
        return {
            "xy": [x, y],
            "box": [x - size / 2, y - size / 2, x + size / 2, y + size / 2],
            "size_px": size,
            "confidence": 0.9,
        }

    m = {
        "outputs": {
            "rf_2x2": {
                "train": {
                    "frames": [
                        {"t": 0, "detections": [detection(100, 100, 10)]},
                        {"t": 1, "detections": [detection(1000, 900, 30)]},
                        {"t": 2, "detections": []},
                    ]
                },
                "held": {"frames": []},
            }
        }
    }

    def samples(clip):
        assert clip["clip_id"] == "train", "held-out decoded during training"
        image = np.zeros((1080, 1920, 3), dtype=np.uint8)
        for i in range(4):  # Fourth frame unlabelled: contributes nothing.
            yield {"t": i, "sample_index": i}, [image]

    monkeypatch.setattr(rfdetr_data, "samples", samples)
    monkeypatch.setitem(
        sys.modules,
        "cv2",
        SimpleNamespace(
            COLOR_RGB2BGR=1,
            IMWRITE_JPEG_QUALITY=2,
            cvtColor=lambda im, _: im,
            imwrite=lambda *args: True,
        ),
    )
    d = prepare(
        m,
        [{"clip_id": "train"}, {"clip_id": "held"}],
        labels,
        tmp_path / "data",
        {"train": ["train"], "held_out": ["held"]},
        18.68,
    )
    assert d["counts"] == {
        "train": 12,
        "val": 0,
        "positive_tiles": 2,
        "negative_tiles": 10,
    }
    assert d["box_recipe"]["slope_px_per_image_y_px"] == 0.025
    assert d["box_recipe"]["fit_clips"] == ["train"]
    assert d["target_distribution"]["at_floor"] == 1
    assert all(
        r["clip"] == "train"
        for r in json.loads((tmp_path / "data/annotations.json").read_text())
    )


def test_patience_sees_only_train_loss_and_final_export_ignores_prior_best(monkeypatch):
    stop = TrainStop(2)
    assert not stop.epoch(4)
    assert not stop.epoch(3)
    assert not stop.epoch(3.01)
    assert stop.epoch(3.02)
    with pytest.raises(ValueError):
        stop.epoch(float("nan"))

    class Value:
        def detach(self):
            return self

        def cpu(self):
            return 99  # Final state, even when its train loss is worse.

    saved = []
    monkeypatch.setitem(
        sys.modules,
        "torch",
        SimpleNamespace(save=lambda data, path: saved.append(data)),
    )
    monkeypatch.setitem(
        sys.modules,
        "rfdetr._namespace",
        SimpleNamespace(_namespace_from_configs=lambda *args: SimpleNamespace()),
    )
    export_final(
        SimpleNamespace(state_dict=lambda: {"last": Value()}), None, None, "unused", 7
    )
    assert saved[0]["model"] == {"last": 99}
    assert saved[0]["final_optimizer_step"] == 7
    assert saved[0]["licence"] == "Apache-2.0"


def test_rf_selection_excludes_yolo_and_improvement_requires_no_false_increase():
    def row(name, recall, false):
        return {
            "candidate": name,
            "held": {
                "groups": {
                    "on_ball": {"top1_recall": recall},
                    "all": {"false_per_10s": false},
                }
            },
        }

    bar = row("tinyball-r2-b", 0.68, 1.67)
    a = row("tinyball-r4-rf-a", 0.7, 1.8)
    b = row("tinyball-r4-rf-b", 0.75, 2.1)
    assert select_rf([bar, a, b]) == a["candidate"]
    assert not beats_bar(a, bar)
    assert not beats_bar(b, bar)
    assert select_rf([bar, b]) is None
    assert beats_bar(row("tinyball-r4-rf-b", 0.69, 1.67), bar)
    assert not beats_bar(row("tinyball-r4-rf-b", 0.68, 1), bar)


def test_rf_saved_pass_pads_each_tile_filters_background_and_rejects_padding(
    monkeypatch, tmp_path
):
    import evaluate_round4

    calls = []

    class Model:
        def predict(self, tiles, threshold):
            assert len(tiles) == 4 and threshold == 0.1
            assert all(t.shape == (960, 960, 3) for t in tiles)
            calls.append(tiles)
            prediction = SimpleNamespace(
                xyxy=np.array(
                    [[10, 20, 30, 40], [10, 600, 30, 620], [100, 100, 110, 110]]
                ),
                confidence=np.array([0.9, 0.8, 0.7]),
                class_id=np.array([0, 0, 1]),
            )
            return [prediction] * 4

    monkeypatch.setitem(
        sys.modules,
        "torch",
        SimpleNamespace(mps=SimpleNamespace(synchronize=lambda: None)),
    )
    image = np.zeros((1080, 1920, 3), dtype=np.uint8)
    monkeypatch.setattr(
        evaluate_round4,
        "samples",
        lambda c: iter([({"t": 0.0, "sample_index": 0, "frame_index": 0}, [image])]),
    )
    monkeypatch.setattr(evaluate_round4, "sha256", lambda path: "source")
    fit = {
        "split": {"train": ["c"], "held_out": []},
        "labels_sha256": "labels",
        "weights_sha256": "weights",
    }
    evaluate_round4.predict_all(
        Model(),
        [{"clip_id": "c", "video": "unused", "duration_s": 0.5}],
        tmp_path,
        "frozen",
        fit,
    )
    saved = json.loads((tmp_path / "detections.json").read_text())
    ds = saved["outputs"]["c"]["frames"][0]["detections"]
    assert len(calls) == 2  # one warmup, one measured pass
    assert len(ds) == 4  # one true-class content box per tile
    assert sorted(d["xy"] for d in ds) == [[20, 30], [20, 570], [980, 30], [980, 570]]
    assert saved["licence"] == "Apache-2.0"
    assert saved["training_split"] == fit["split"]
    suggestion = json.loads((tmp_path / "suggestions.jsonl").read_text())
    assert suggestion["source"] == f"model:{tmp_path.name}"


def test_saved_error_buckets_keep_oracle_and_highest_confidence_distinct(monkeypatch):
    import review_round4

    monkeypatch.setattr(review_round4, "clip_class", lambda c: "on_ball")
    records = [
        {
            "clip": "c",
            "hit": True,
            "size": 8,
            "size_bucket": "1",
            "image_y": "0",
            "motion": "unknown",
            "player_overlap": "outside",
        }
    ]
    monkeypatch.setattr(review_round4, "error_records", lambda *args: records)
    m = {"clips": [{"clip_id": "c"}]}
    labels = {("c", 0): {"visible": True, "x": 10, "y": 10}}
    outputs = {
        "c": {
            "frames": [
                {
                    "t": 0,
                    "detections": [
                        {"xy": [10, 10], "confidence": 0.2},
                        {"xy": [100, 100], "confidence": 0.9},
                    ],
                }
            ]
        }
    }
    result = review_round4.errors_top1(m, labels, outputs, {}, {"held_out": ["c"]})
    for scope in ("all", "held"):
        assert result["oracle"][scope]["misses"] == 0
        assert result["top1"][scope]["misses"] == 1
        assert result["top1"][scope]["buckets"]["size_bucket"]["1"]["misses"] == 1
