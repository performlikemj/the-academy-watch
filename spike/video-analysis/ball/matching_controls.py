"""Fixed-seed negative controls; aggregate sanity floors, never alternate truth."""

from __future__ import annotations
import random
import statistics
from typing import Any
from human_score import score_rows
from metrics import clip_class

SEED = 20260911
REPEATS = 100


def control_labels(labels, method, rng, dimensions):
    """Preserve visible timestamps and counts; corrupt centres only within scope."""
    altered = {k: dict(v) for k, v in labels.items()}
    for cid in sorted({k[0] for k in labels}):
        keys = sorted(k for k, v in labels.items() if k[0] == cid and v["visible"])
        points = [(labels[k]["x"], labels[k]["y"]) for k in keys]
        if method == "shuffled_within_clip":
            rng.shuffle(points)  # Ordinary permutation, including chance fixed points.
        elif method == "uniform_random":
            w, h = dimensions[cid]
            points = [(rng.uniform(0, w), rng.uniform(0, h)) for _ in keys]
        else:
            raise ValueError(method)
        for key, (x, y) in zip(keys, points):
            altered[key].update(x=x, y=y)
    return altered


def controls(measurements, labels, candidates, split, repeats=REPEATS):
    groups = {c["clip_id"]: clip_class(c) for c in measurements["clips"]}
    dimensions = {cid: (1920, 1080) for cid in groups}
    result = {
        "seed": SEED,
        "repeats": repeats,
        "definition": "Corrupt visible human centres only; keep detections/confidences/timestamps/no-ball labels fixed. Ordinary within-clip permutation (fixed points allowed) or independent uniform native 1920x1080 centres. Same seeded draws for every candidate. Report mean/min/max across 100 repeats; oracle over N boxes and top-1 separately. No tracks or model inference. Reviewer gave ranges without a seed; these newly specified controls may differ.",
        "results": {},
    }
    for scope in ("all", "held"):
        selected = {
            k: v
            for k, v in labels.items()
            if scope == "all" or k[0] in split["held_out"]
        }
        for method in ("shuffled_within_clip", "uniform_random"):
            rng = random.Random(SEED)
            values: dict[str, Any] = {
                name: {
                    g: {m: [] for m in ("top1_recall", "oracle_recall")}
                    for g in ("all", "on_ball")
                }
                for name in candidates
            }
            grouped_rows = {
                name: {
                    g: [
                        {
                            **r,
                            "clip": cid,
                            "detections": [
                                d for d in r["detections"] if d["confidence"] >= 0.1
                            ],
                        }
                        for cid, o in outputs.items()
                        if g == "all" or groups[cid] == g
                        for r in o["frames"]
                    ]
                    for g in ("all", "on_ball")
                }
                for name, outputs in candidates.items()
            }
            for _ in range(repeats):
                corrupted = control_labels(selected, method, rng, dimensions)
                for name, rows_by_group in grouped_rows.items():
                    for group, rows in rows_by_group.items():
                        scored = score_rows(rows, corrupted)
                        for metric in ("top1_recall", "oracle_recall"):
                            values[name][group][metric].append(scored[metric])
            result["results"].setdefault(scope, {})[method] = {
                name: {
                    g: {
                        metric: {
                            "mean": statistics.mean(v),
                            "min": min(v),
                            "max": max(v),
                        }
                        for metric, v in scores.items()
                    }
                    for g, scores in bygroup.items()
                }
                for name, bygroup in values.items()
            }
    return result
