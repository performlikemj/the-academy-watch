"""Five deterministic samples, all four tiles and all three heatmap channels."""

from __future__ import annotations
import numpy as np
from common import samples


def check_parity(model, clips):
    import torch

    selected = [clips[i] for i in (1, 3, 10, 12, 15)]
    rows = []
    for clip in selected:
        # First non-boundary 2 fps sample includes genuine consecutive frames.
        iterator = samples(clip)
        next(iterator)
        frame, stack = next(iterator)
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
                "tile_max_abs_heatmap_diff": diffs,
                "max_abs_heatmap_diff": max(diffs),
            }
        )
    model.model.to("mps")
    model.device = "mps"
    maximum = max(r["max_abs_heatmap_diff"] for r in rows)
    return {
        "frames": rows,
        "max_abs_heatmap_diff": maximum,
        "channels": "all three sigmoid heatmaps per tile",
        "tolerance": 1e-4,
        "within_tolerance": maximum <= 1e-4,
        "scope": "WASB 2x2 FP32, same state dict and inputs; parity does not validate ball accuracy",
    }
