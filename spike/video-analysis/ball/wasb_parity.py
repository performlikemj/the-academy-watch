"""Five deterministic samples, all four tiles and all three heatmap channels."""

from __future__ import annotations
import numpy as np
from fractions import Fraction
from common import samples, probe, sample_indices


def plan_parity(clips, count=5):
    """Plan distinct samples before loading a model, balanced across available clips.

    Spread up to five selected clips across the provided order. Allocate samples
    equally, then spread within each clip, excluding a replicated left boundary
    whenever a non-boundary frame is available.
    """
    if not clips or count < 1:
        raise ValueError("parity needs available clips and a positive sample count")
    n = min(len(clips), count)
    selected = (
        [clips[round(i * (len(clips) - 1) / (n - 1))] for i in range(n)]
        if n > 1
        else [clips[0]]
    )
    schedules = []
    for clip in selected:
        rate = float(Fraction(probe(clip["video"])["avg_frame_rate"]))
        start, end = clip["window"]["start_s"], clip["window"]["end_s"]
        offset = 0 if clip["native_source"] else start
        _, _, indices = sample_indices(start, end, rate, 2.0, offset)
        schedules.append(
            list(range(1, len(indices)))
            if len(indices) > 1
            else list(range(len(indices)))
        )
    if sum(map(len, schedules)) < count:
        raise ValueError(
            f"parity needs {count} distinct available frames; selected clips have too few"
        )
    quotas = [0] * n
    while sum(quotas) < count:
        for i, schedule in enumerate(schedules):
            if quotas[i] < len(schedule) and sum(quotas) < count:
                quotas[i] += 1
    plan = []
    for clip, schedule, quota in zip(selected, schedules, quotas):
        for i in range(quota):
            index = (
                round(i * (len(schedule) - 1) / (quota - 1))
                if quota > 1
                else (len(schedule) - 1) // 2
            )
            plan.append({"clip": clip["clip_id"], "sample_index": schedule[index]})
    return plan


def check_parity(model, clips, plan=None):
    import torch

    plan = plan_parity(clips) if plan is None else plan
    by_clip = {clip["clip_id"]: clip for clip in clips}
    rows = []
    original_device = model.device
    try:
        for item in plan:
            clip = by_clip[item["clip"]]
            iterator = samples(clip)
            try:
                for _ in range(item["sample_index"] + 1):
                    frame, stack = next(iterator)
            finally:
                iterator.close()
            model.model.to("mps")
            model.device = "mps"
            mps = model.heatmaps(stack)
            torch.mps.synchronize()
            model.model.to("cpu")
            model.device = "cpu"
            cpu = model.heatmaps(stack)
            diffs = [float(np.max(np.abs(a[1] - b[1]))) for a, b in zip(mps, cpu)]
            rows.append(
                {
                    "clip": clip["clip_id"],
                    "t": frame["t"],
                    "sample_index": item["sample_index"],
                    "tile_max_abs_heatmap_diff": diffs,
                    "max_abs_heatmap_diff": max(diffs),
                }
            )
    finally:
        model.model.to(original_device)
        model.device = original_device
    maximum = max(r["max_abs_heatmap_diff"] for r in rows)
    return {
        "frames": rows,
        "max_abs_heatmap_diff": maximum,
        "channels": "all three sigmoid heatmaps per tile",
        "tolerance": 1e-4,
        "within_tolerance": maximum <= 1e-4,
        "scope": "WASB 2x2 FP32, same state dict and inputs; parity does not validate ball accuracy",
    }
