"""Training-only apparent-size supervision; no held-out geometry enters the fit."""

from __future__ import annotations

import math
import statistics


def matched_size(label, detections):
    candidates = [
        d
        for d in detections
        if d["confidence"] >= 0.1
        and d.get("box") is not None
        and d.get("size_px") is not None
        and math.isfinite(d["size_px"])
        and d["size_px"] > 0
        and math.dist(d["xy"], [label["x"], label["y"]]) <= 20
    ]
    nearest = min(
        candidates,
        key=lambda d: math.dist(d["xy"], [label["x"], label["y"]]),
        default=None,
    )
    return nearest["size_px"] if nearest else None


def fit_scale(measurements, labels, train_clips):
    observations = []
    visible = 0
    for cid in train_clips:
        for row in measurements["outputs"]["rf_2x2"][cid]["frames"]:
            label = labels.get((cid, row["t"]))
            if not label or not label["visible"]:
                continue
            visible += 1
            size = matched_size(label, row["detections"])
            if size is not None:
                observations.append((label["y"], size))
    if len(observations) < 2:
        raise ValueError("scale fit needs at least two training-only matched sizes")
    mean_y = statistics.mean(y for y, _ in observations)
    mean_size = statistics.mean(s for _, s in observations)
    sxx = sum((y - mean_y) ** 2 for y, _ in observations)
    slope = (
        sum((y - mean_y) * (s - mean_size) for y, s in observations) / sxx
        if sxx
        else 0.0
    )
    intercept = mean_size - slope * mean_y
    residual = sum((s - intercept - slope * y) ** 2 for y, s in observations)
    total = sum((s - mean_size) ** 2 for _, s in observations)
    return {
        "mode": "matched_size_with_train_affine_fallback",
        "intercept_px": intercept,
        "slope_px_per_image_y_px": slope,
        "r_squared": 1 - residual / total if total else None,
        "observations": len(observations),
        "visible_train_labels": visible,
        "fallback_labels": visible - len(observations),
        "clip_px": [6, 48],
        "fit_clips": sorted(train_clips),
        "observed_short_side_px": {
            "min": min(s for _, s in observations),
            "median": statistics.median(s for _, s in observations),
            "max": max(s for _, s in observations),
        },
        "definition": "One nearest saved RF 2x2 box per visible TRAIN click within inclusive 20 native px at confidence >=0.1. OLS short side = intercept + slope * native image y; R-squared before clipping. Per-label target uses its matched short side when present, otherwise the fitted value; all sides clipped to [6,48] native px. No fixed doubling. Held-out labels/boxes never enter fitting or targets. Detector extents are estimates, not human-drawn boundaries; image y is an imperfect perspective proxy.",
    }


def target_side(label, detections, fit):
    size = matched_size(label, detections)
    if size is None:
        size = fit["intercept_px"] + fit["slope_px_per_image_y_px"] * label["y"]
    return min(48.0, max(6.0, size))
