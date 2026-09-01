import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from grounding import (  # noqa: E402
    ground_normalized_box,
    impossible_box_reason,
    truth_box_at_time,
)


def test_normalized_box_is_converted_and_grounded_by_iou():
    result = ground_normalized_box(
        [100, 200, 300, 400],
        10.0,
        [[10.0, 192, 216, 576, 432]],
        (1920, 1080),
    )

    assert result["box"] == [192, 216, 576, 432]
    assert result["grounded"] is True
    assert result["iou"] == 1.0


def test_containment_can_ground_a_smaller_model_box():
    result = ground_normalized_box(
        [150, 150, 200, 200],
        10.0,
        [[10.0, 100, 100, 300, 300]],
        (1000, 1000),
    )

    assert result["iou"] < 0.5
    assert result["containment"] == 1.0
    assert result["grounded"] is True


def test_truth_lookup_never_interpolates_across_tracking_gap():
    track = [
        [10.0, 0, 0, 10, 10],
        [10.1, 0, 0, 10, 10],
        [10.2, 0, 0, 10, 10],
        [13.2, 20, 20, 30, 30],
        [13.3, 20, 20, 30, 30],
    ]

    box, in_gap = truth_box_at_time(track, 11.0)

    assert box is None
    assert in_gap is True


@pytest.mark.parametrize(
    ("box", "reason"),
    [
        ([-1, 0, 10, 10], "box outside frame"),
        ([0, 0, 101, 101], "box area exceeds source frame"),
        ([10, 10, 5, 20], "box coordinates are not ordered"),
    ],
)
def test_impossible_boxes_are_malformed(box, reason):
    assert impossible_box_reason(box, (100, 100)) == reason

