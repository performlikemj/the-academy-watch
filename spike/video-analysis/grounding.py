"""Shared tracked-box grounding primitives for the pipeline and evidence bench."""

from __future__ import annotations

import math
import shutil
import statistics
import subprocess
from pathlib import Path

IOU_THRESHOLD = 0.5
CONTAINMENT_THRESHOLD = 0.8
TRACKING_GAP_MULTIPLIER = 2.0
MIN_INTERPOLATION_GAP_S = 0.25


def scale_box(
    box: list[float] | tuple[float, ...],
    from_size: tuple[int, int],
    to_size: tuple[int, int],
) -> list[float]:
    """Scale one xyxy box independently on the x and y axes."""
    from_width, from_height = from_size
    to_width, to_height = to_size
    if min(from_width, from_height, to_width, to_height) <= 0:
        raise ValueError("box coordinate spaces must have positive dimensions")
    scale_x = to_width / from_width
    scale_y = to_height / from_height
    return [
        float(box[0]) * scale_x,
        float(box[1]) * scale_y,
        float(box[2]) * scale_x,
        float(box[3]) * scale_y,
    ]


def normalized_1000_to_source(
    box: list[float] | tuple[float, ...], frame_size: tuple[int, int]
) -> list[float]:
    """Convert a Qwen normalized-1000 xyxy box to source-video pixels."""
    return scale_box(box, (1000, 1000), frame_size)


def impossible_box_reason(
    box: list[float] | tuple[float, ...], frame_size: tuple[int, int]
) -> str | None:
    """Return why a source-pixel box cannot describe a region in the frame."""
    if len(box) != 4 or not all(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        for value in box
    ):
        return "box must contain four finite numbers"
    source_w, source_h = frame_size
    if source_w <= 0 or source_h <= 0:
        return "frame size must be positive"
    x1, y1, x2, y2 = (float(value) for value in box)
    if x2 <= x1 or y2 <= y1:
        return "box coordinates are not ordered"
    if (x2 - x1) * (y2 - y1) > source_w * source_h:
        return "box area exceeds source frame"
    if x1 < 0 or y1 < 0 or x2 > source_w or y2 > source_h:
        return "box outside frame"
    return None


def tracking_cadence_s(box_track: list[list]) -> float | None:
    """Return the median positive interval between tracked-box samples."""
    timestamps = sorted(float(row[0]) for row in box_track if len(row) >= 5)
    gaps = [
        right - left for left, right in zip(timestamps, timestamps[1:]) if right > left
    ]
    return float(statistics.median(gaps)) if gaps else None


def max_interpolation_gap_s(box_track: list[list]) -> float:
    """Return the largest adjacent sample gap safe to interpolate."""
    cadence = tracking_cadence_s(box_track)
    return max(
        MIN_INTERPOLATION_GAP_S,
        TRACKING_GAP_MULTIPLIER * cadence if cadence is not None else 0.0,
    )


def truth_box_at_time(
    box_track: list[list], timestamp_s: float
) -> tuple[list[float] | None, bool]:
    """Look up truth at a time, interpolating only inside normal track cadence.

    The boolean reports that the timestamp fell inside a disjoint tracking gap.
    """
    if not box_track or not math.isfinite(timestamp_s):
        return None, False
    rows = sorted(
        (row for row in box_track if len(row) >= 5), key=lambda row: float(row[0])
    )
    if not rows:
        return None, False
    if timestamp_s < float(rows[0][0]) or timestamp_s > float(rows[-1][0]):
        return None, False
    interpolation_limit = max_interpolation_gap_s(rows)
    for index, row in enumerate(rows):
        row_t = float(row[0])
        if math.isclose(timestamp_s, row_t, abs_tol=1e-9):
            return [float(value) for value in row[1:5]], False
        if row_t > timestamp_s:
            left = rows[index - 1]
            left_t = float(left[0])
            if row_t - left_t > interpolation_limit:
                return None, True
            fraction = (timestamp_s - left_t) / (row_t - left_t)
            return (
                [
                    float(left[column])
                    + fraction * (float(row[column]) - float(left[column]))
                    for column in range(1, 5)
                ],
                False,
            )
    return [float(value) for value in rows[-1][1:5]], False


def interpolated_box(box_track: list[list], timestamp_s: float) -> list[float] | None:
    """Return tracked truth at a timestamp, or none across gaps/outside the track."""
    box, _in_gap = truth_box_at_time(box_track, timestamp_s)
    return box


def box_matches(
    model_box: list[float], truth_box: list[float]
) -> tuple[bool, float, float]:
    """Return grounded, IoU, and fraction of the model box inside truth."""
    intersection = max(
        0.0, min(model_box[2], truth_box[2]) - max(model_box[0], truth_box[0])
    ) * max(0.0, min(model_box[3], truth_box[3]) - max(model_box[1], truth_box[1]))
    model_area = max(0.0, model_box[2] - model_box[0]) * max(
        0.0, model_box[3] - model_box[1]
    )
    truth_area = max(0.0, truth_box[2] - truth_box[0]) * max(
        0.0, truth_box[3] - truth_box[1]
    )
    union = model_area + truth_area - intersection
    iou = intersection / union if union > 0 else 0.0
    containment = intersection / model_area if model_area > 0 else 0.0
    grounded = iou >= IOU_THRESHOLD or containment >= CONTAINMENT_THRESHOLD
    return grounded, round(iou, 4), round(containment, 4)


def ground_normalized_box(
    model_box: list[float] | tuple[float, ...],
    box_t: float,
    box_track: list[list],
    frame_size: tuple[int, int],
) -> dict:
    """Convert and ground one Qwen box against tracked source-pixel truth."""
    source_box = normalized_1000_to_source(model_box, frame_size)
    malformed_reason = impossible_box_reason(source_box, frame_size)
    truth_box, in_gap = truth_box_at_time(box_track, float(box_t))
    grounded = False
    iou = None
    containment = None
    if malformed_reason is None and truth_box is not None:
        grounded, iou, containment = box_matches(source_box, truth_box)
    return {
        "grounded": grounded,
        "box": source_box,
        "truth_box": truth_box,
        "iou": iou,
        "containment": containment,
        "malformed_reason": malformed_reason,
        "no_truth_at_time": truth_box is None,
        "untracked_gap": in_gap,
    }


def draw_anchor_box(frame: Path, box: list[float], label: str | None = None) -> None:
    """Draw a thin red identity anchor while preserving image dimensions."""
    try:
        from PIL import Image, ImageDraw

        image = Image.open(frame).convert("RGB")
        draw = ImageDraw.Draw(image)
        draw.rectangle(box, outline=(255, 40, 40), width=3)
        if label:
            label_box = draw.textbbox((box[0], box[1]), label)
            draw.rectangle(label_box, fill=(255, 40, 40))
            draw.text((box[0], box[1]), label, fill=(255, 255, 255))
        image.save(frame, quality=94)
        return
    except ImportError:
        pass

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError(
            "Pillow is unavailable and ffmpeg is not on PATH for drawbox fallback"
        )
    output = frame.with_name(f"{frame.stem}-boxed.jpg")
    filters = [
        f"drawbox=x={box[0]:.3f}:y={box[1]:.3f}:"
        f"w={box[2] - box[0]:.3f}:h={box[3] - box[1]:.3f}:color=red:t=3"
    ]
    if label:
        safe_label = label.replace("'", "")
        filters.append(
            f"drawtext=text='{safe_label}':x={box[0]:.3f}:y={box[1]:.3f}:"
            "fontcolor=white:fontsize=22:box=1:boxcolor=red"
        )
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-v",
            "error",
            "-i",
            str(frame),
            "-vf",
            ",".join(filters),
            str(output),
        ],
        check=True,
    )
    output.replace(frame)
