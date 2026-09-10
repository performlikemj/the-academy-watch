"""Leakage, independent size availability, proxy boundaries and TRAIN-only selection."""

import sys
from types import ModuleType

import pytest

from round2_analysis import bucket, error_summary, gate, independent_sizes
from train_loss_trainer import train_loss_value, trainer_class


def test_train_loss_validator_never_invokes_image_validation(monkeypatch):
    module = ModuleType("ultralytics.models.yolo.detect.train")

    class ForbiddenValidator:
        best_fitness = None
        tloss = {"box": 1.0, "cls": 2.0, "dfl": 1.0}

        def validate(self):
            raise AssertionError("held-out image validation must not happen")

        def final_eval(self):
            raise AssertionError("final held-out validation must not happen")

    module.DetectionTrainer = ForbiddenValidator
    monkeypatch.setitem(sys.modules, "ultralytics.models.yolo.detect.train", module)
    trainer = trainer_class()()
    metrics, fitness = trainer.validate()
    assert metrics == {"train/selection_loss": 4.0}
    assert fitness == pytest.approx(0.2)
    assert trainer.best_fitness == fitness
    trainer.tloss = {"box": 2, "cls": 2, "dfl": 1}
    assert trainer.validate()[1] < trainer.best_fitness
    assert trainer.final_eval() is None
    for bad in ([float("nan")], [float("inf")], [-1]):
        with pytest.raises(ValueError):
            train_loss_value(bad)


def test_projection_retains_unknowns_and_unsupported_bins():
    records = [
        {
            "hit": True,
            "size": 5,
            "size_bucket": "0",
            "image_y": "0",
            "motion": "unknown",
            "player_overlap": "inside",
        },
        {
            "hit": False,
            "size": 12,
            "size_bucket": "2",
            "image_y": "1",
            "motion": "1",
            "player_overlap": "outside",
        },
        {
            "hit": False,
            "size": None,
            "size_bucket": "unknown",
            "image_y": "2",
            "motion": "2",
            "player_overlap": "outside",
        },
    ]
    result = error_summary(records)
    assert result["misses"] == 2
    projection = result["double_size_projection"]
    assert projection["supported_frames"] == 1  # 5px maps to measured 10–16px bin
    assert projection["unchanged_unknown_or_unsupported"] == 2
    assert projection["projected_recall"] == 0  # never promise improvement
    assert projection["observed_recall"] == pytest.approx(1 / 3)
    for rows in result["buckets"].values():
        assert sum(r["visible"] for r in rows.values()) == 3
        assert sum(r["misses"] for r in rows.values()) == 2
    assert bucket(6, [6, 10, 16, 24]) == 1
    assert bucket(24, [6, 10, 16, 24]) == 4


def test_independent_size_cannot_use_trained_pseudo_boxes():
    def output(size, location=(0, 0)):
        return {
            "c": {
                "frames": [
                    {
                        "t": 0,
                        "detections": [
                            {
                                "xy": list(location),
                                "box": [0, 0, size, size],
                                "size_px": size,
                                "confidence": 0.1,
                            }
                        ],
                    }
                ]
            }
        }

    m = {
        "outputs": {
            "rf_full": output(4),
            "rf_2x2": output(8),
            "rf_3x3": output(100, (100, 100)),
            "tinyball-r2-a": output(18),
        }
    }
    labels = {
        ("c", 0): {"visible": True, "x": 0, "y": 0},
        ("c", 1): {"visible": True, "x": 0, "y": 0},
    }
    assert independent_sizes(m, labels) == {("c", 0): 6}


def test_real_gate_requires_both_measured_conditions():
    def verdict(recall, false):
        return gate(
            {"on_ball": {"top1_recall": recall}, "all": {"false_per_10s": false}}
        )

    assert verdict(0.8, 1) == "PASS"
    assert verdict(0.79999, 0) == "FAIL"
    assert verdict(1, 1.00001) == "FAIL"
    assert verdict(1, None) == "UNMEASURABLE"


def test_train_only_dataset_never_decodes_held_out(monkeypatch, tmp_path):
    from types import SimpleNamespace
    import numpy as np
    import train_tiny_ball as training

    monkeypatch.setitem(
        sys.modules,
        "cv2",
        SimpleNamespace(
            COLOR_RGB2BGR=1,
            IMWRITE_JPEG_QUALITY=1,
            cvtColor=lambda a, _: a,
            imwrite=lambda *args: True,
        ),
    )

    def sample(clip):
        assert clip["clip_id"] == "train", "held-out pixels reached fitting"
        yield {"t": 0, "sample_index": 0}, [np.zeros((1080, 1920, 3), dtype=np.uint8)]

    monkeypatch.setattr(training, "samples", sample)
    clips = [{"clip_id": cid, "source_size": [1920, 1080]} for cid in ("train", "held")]
    m = {
        "outputs": {
            "rf_2x2": {
                cid: {"frames": [{"t": 0, "detections": []}]}
                for cid in ("train", "held")
            }
        }
    }
    labels = {
        (cid, 0): {"visible": True, "x": 100, "y": 100} for cid in ("train", "held")
    }
    split = {
        "train": ["train"],
        "held_out": ["held"],
        "smoke_resubstitution_only": False,
    }
    result = training.prepare_dataset(
        m, clips, labels, tmp_path, split, train_only=True
    )
    assert result["counts"] == {
        "train": 4,
        "val": 0,
        "positive_tiles": 1,
        "negative_tiles": 3,
    }
    assert "val: images/train" in (tmp_path / "dataset.yaml").read_text()
    assert not (tmp_path / "images/val").exists()


def test_frozen_round2_selection_and_paired_denominators():
    import gzip
    import json
    from common import HERE

    evidence = json.loads(
        gzip.decompress((HERE / "fixtures/round2_measurements.json.gz").read_bytes())
    )
    selection = evidence["selection"]
    assert set(selection["fits"]) == set("abcd")
    assert selection["evaluation_started"] is False
    assert selection["selected"] == min(
        selection["fits"], key=lambda k: selection["fits"][k]["best_train_loss"]
    )
    parent = min("abc", key=lambda k: selection["fits"][k]["best_train_loss"])
    assert selection["fits"]["d"]["initial_weights"].endswith(
        f"mj-r2-{parent}/weights.pt"
    )
    assert selection["fits"]["c"]["training_s"] <= 25 * 60
    assert len(evidence["results"]) == 11
    for row in evidence["results"]:
        for scope, visible, no_ball in (("all", 875, 182), ("held", 244, 60)):
            groups = row[scope]["groups"]
            assert groups["all"]["visible"] == visible
            assert groups["all"]["no_ball_frames"] == no_ball
            assert row[scope]["gate"] == gate(groups)
            assert groups["all"]["false_per_10s"] == pytest.approx(
                groups["all"]["false_per_frame"] * 20
            )
    raw = json.dumps(evidence)
    assert '"x":' not in raw and '"y":' not in raw and '"hit":' not in raw


def test_frozen_error_buckets_partition_selected_on_ball_labels():
    import gzip
    import json
    from common import HERE

    evidence = json.loads(
        gzip.decompress((HERE / "fixtures/round2_measurements.json.gz").read_bytes())
    )
    selected = next(
        r for r in evidence["results"] if r["candidate"] == evidence["selected_model"]
    )
    for scope in ("all", "held"):
        error = evidence["errors"][scope]
        score = selected[scope]["groups"]["on_ball"]
        assert error["visible"] == score["visible"]
        assert error["misses"] == score["visible"] - score["matched"]
        for buckets in error["buckets"].values():
            assert sum(r["visible"] for r in buckets.values()) == error["visible"]
            assert sum(r["misses"] for r in buckets.values()) == error["misses"]
        projection = error["double_size_projection"]
        assert projection["observed_recall"] == score["recall"]
        assert (
            projection["supported_frames"]
            + projection["unchanged_unknown_or_unsupported"]
            == score["visible"]
        )
