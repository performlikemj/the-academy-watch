"""Scale fitting must not consume held-out geometry or duplicate guesses."""

import copy
import pytest
from scale_targets import fit_scale, target_side


def detection(size, x=10):
    return {
        "xy": [x, 100],
        "box": [0, 0, size, size],
        "size_px": size,
        "confidence": 0.5,
    }


def test_fit_train_only_and_per_click_deduplication():
    labels = {
        ("train", 0): {"visible": True, "x": 10, "y": 100},
        ("train", 0.5): {"visible": True, "x": 10, "y": 200},
        ("held", 0): {"visible": True, "x": 10, "y": 999},
    }
    second = detection(20)
    second["xy"][1] = 200
    held = detection(400)
    held["xy"][1] = 999
    m = {
        "outputs": {
            "rf_2x2": {
                "train": {
                    "frames": [
                        {"t": 0, "detections": [detection(10), detection(40, 20)]},
                        {"t": 0.5, "detections": [second]},
                    ]
                },
                "held": {"frames": [{"t": 0, "detections": [held]}]},
            }
        }
    }
    fit = fit_scale(m, labels, ["train"])
    assert fit["observations"] == 2
    assert fit["slope_px_per_image_y_px"] == pytest.approx(0.1)
    assert fit["r_squared"] == pytest.approx(1)
    altered = copy.deepcopy(labels)
    altered[("held", 0)]["y"] = -10000
    altered_m = copy.deepcopy(m)
    altered_m["outputs"]["rf_2x2"]["held"]["frames"][0]["detections"][0]["size_px"] = (
        9999
    )
    assert fit_scale(altered_m, altered, ["train"]) == fit
    assert target_side({"x": 10, "y": 300}, [], fit) == pytest.approx(30)
    assert target_side({"x": 10, "y": 100}, [detection(40)], fit) == 40
    assert target_side({"x": 10, "y": 1000}, [], fit) == 48
    assert target_side({"x": 10, "y": 0}, [], fit) == 6
