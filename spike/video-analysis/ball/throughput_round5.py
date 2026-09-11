"""One idle MPS session: interleaved decode + four-tile batches, three repeats."""

from __future__ import annotations
from output_guard import guard_outputs
import argparse
from contextlib import closing
from itertools import islice
import gc
import json
import math
import statistics
import time
from pathlib import Path
from common import (
    DEFAULT_MANIFEST,
    DEFAULT_SOURCE,
    HERE,
    dump,
    load_dataset,
    probe,
    samples,
)
from detectors import tile_bounds, merge_tiles
from rfdetr_data import square_pad, restore_box
from round5_inference import load_model
from checkpoint_provenance import validate_model
from benchmark_activity import ACTIVE_GENERATORS, Activity, busy


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--new", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    guard_outputs(a.out, inputs=[a.new], parser=p)
    root = Path.home() / "models/tinyball"
    definitions = [
        ("yolo-r2-b", root / "mj-r2-b/weights.pt", "yolo"),
        ("rf-b", root / "mj-r4-rf-b/weights.pt", "rf"),
        (a.new.parent.name, a.new, "rf"),
    ]
    # Preflight every checkpoint before loading any model, outside timed calls.
    for _, weights, _ in definitions:
        validate_model(weights)
    import cv2
    import numpy as np
    import torch

    activity = Activity()
    idle_before = activity.wait_idle()
    cv2.setNumThreads(1)
    torch.set_num_threads(8)
    _, clips = load_dataset(DEFAULT_MANIFEST, DEFAULT_SOURCE)
    split = json.loads((HERE / "fixtures/round5_execution.json").read_text())["split"]
    selected = [
        c
        for c in clips
        if c["clip_id"] in split["train"]
        and any(
            tag in c["clip_id"]
            for tag in ("n04-t3006-243433", "n12-t1411-237107", "n15-t3010-164698")
        )
    ]
    assert len(selected) == 3
    models = {}
    modes = {}
    errors = {}
    dummy = [np.full((960, 960, 3), 114, dtype=np.uint8)] * 4
    # No timed call includes model loading, JIT tracing or warmup.
    for name, weights, kind in definitions:
        if kind == "yolo":
            model = load_model(weights, kind)
            modes[name] = "Ultralytics FP32 raw 960x540, imgsz960, batch4"
        else:
            for half in (True, False):
                try:
                    model = load_model(weights, kind, optimize=True, half=half)
                    with torch.no_grad():
                        raw = model.model.inference_model(
                            torch.ones(
                                (4, 3, 960, 960),
                                device="mps",
                                dtype=torch.float16 if half else torch.float32,
                            )
                        )
                    tensors = raw.values() if isinstance(raw, dict) else raw
                    if any(not torch.isfinite(t).all().item() for t in tensors):
                        raise RuntimeError("nonfinite raw optimized output")
                    pred = model.predict(dummy, threshold=0.01)
                    if len(pred) != 4 or any(
                        not np.isfinite(r.xyxy).all()
                        or not np.isfinite(r.confidence).all()
                        for r in pred
                    ):
                        raise RuntimeError("nonfinite optimized output")
                    modes[name] = "optimize_for_inference JIT batch4 " + (
                        "FP16" if half else "FP32"
                    )
                    break
                except Exception as exc:
                    errors.setdefault(name, []).append(
                        f"{'FP16' if half else 'FP32'}: {type(exc).__name__}: {exc}"
                    )
                    if not half:
                        raise
                    gc.collect()
                    torch.mps.empty_cache()
        model.predict(dummy, threshold=0.01)
        torch.mps.synchronize()
        models[name] = model
    # TRAIN-only precision probe; do not silently pair FP16 speed with assumed FP32 accuracy.
    evidence = json.loads((root / "round5-evidence.json").read_text())
    parity = {}
    for name, weights, kind in definitions:
        if kind != "rf":
            continue
        key = "rf-b" if name == "rf-b" else "rf-r5-" + a.new.parent.name[-1]
        reference = (
            root
            / (
                "r5-rfb-low"
                if name == "rf-b"
                else f"r5-rf-{a.new.parent.name[-1]}-final-low"
            )
            / "detections.json"
        )
        saved = json.loads(reference.read_text())["outputs"]
        threshold = evidence["models"][key]["operating_points"]["1"]["threshold"]
        n = presence_changes = 0
        distances, score_deltas = [], []
        for clip in selected:
            by_time = {r["t"]: r for r in saved[clip["clip_id"]]["frames"]}
            for sample, stack in samples(clip):
                if sample["sample_index"] >= 5:
                    break
                bounds = tile_bounds(1920, 1080, 2)
                tiles = [square_pad(stack[-1][b:d, aa:c]) for aa, b, c, d in bounds]
                predictions = models[name].predict(tiles, threshold=0.01)
                ds = []
                for prediction, tile in zip(predictions, bounds):
                    for box, score, category in zip(
                        prediction.xyxy, prediction.confidence, prediction.class_id
                    ):
                        restored = restore_box(box, tile)
                        if category == 0 and restored is not None:
                            aa, b, c, d = restored
                            ds.append(
                                {
                                    "box": restored,
                                    "xy": [(aa + c) / 2, (b + d) / 2],
                                    "confidence": float(score),
                                    "size_px": min(c - aa, d - b),
                                }
                            )
                ds = merge_tiles(ds)
                old = max(
                    (
                        d
                        for d in by_time[sample["t"]]["detections"]
                        if d["confidence"] >= threshold
                    ),
                    key=lambda d: d["confidence"],
                    default=None,
                )
                new = max(
                    (d for d in ds if d["confidence"] >= threshold),
                    key=lambda d: d["confidence"],
                    default=None,
                )
                presence_changes += bool(old) != bool(new)
                if old and new:
                    distances.append(math.dist(old["xy"], new["xy"]))
                    score_deltas.append(abs(old["confidence"] - new["confidence"]))
                n += 1
        parity[name] = {
            "train_frames": n,
            "threshold": threshold,
            "top1_presence_changes": presence_changes,
            "maximum_top1_centre_delta_px": max(distances, default=None),
            "maximum_top1_score_delta": max(score_deltas, default=None),
            "note": "15 TRAIN frames, not full optimized-accuracy validation; primary metrics remain eager FP32.",
        }
    source = probe(DEFAULT_SOURCE)
    num, den = map(int, source["avg_frame_rate"].split("/"))
    native = num / den
    measurements = {
        mode: {name: [] for name, _, _ in definitions} for mode in ("sampled", "native")
    }
    for repeat in range(3):
        for sampling, rate in (("sampled", 2.0), ("native", native)):
            for name, _, kind in definitions:
                activity_before = activity.wait_idle()
                model = models[name]
                n = boxes = 0
                torch.mps.synchronize()
                start = time.perf_counter()
                for clip in selected:
                    with closing(samples(clip, fps=rate)) as stream:
                        frames = islice(stream, 64) if sampling == "native" else stream
                        for _, stack in frames:
                            tiles = [
                                square_pad(stack[-1][y0:y1, x0:x1])
                                if kind == "rf"
                                else stack[-1][y0:y1, x0:x1]
                                for x0, y0, x1, y1 in tile_bounds(1920, 1080, 2)
                            ]
                            predictions = model.predict(tiles, threshold=0.01)
                            n += 1
                            boxes += sum(len(r.confidence) for r in predictions)
                torch.mps.synchronize()
                wall = time.perf_counter() - start
                after = activity.after(start + wall)
                during = [v for v in activity.samples if start <= v["t"] <= after["t"]]
                if not activity.thread.is_alive():
                    raise RuntimeError("activity monitor failed during timing")
                contended = any(busy(v) for v in during) or activity_before[
                    "timing_status"
                ].startswith("contended")
                measurements[sampling][name].append(
                    {
                        "repeat": repeat + 1,
                        "frames": n,
                        "wall_s": wall,
                        "fps": n / wall,
                        "tile_predictions": boxes,
                        "activity_before": activity_before,
                        "activity_polls_during": len(during),
                        "busy_polls": sum(busy(v) for v in during),
                        "timing_status": "contended (steady background load)"
                        if contended
                        else activity_before["timing_status"],
                        "background_caveat_samples": [
                            {
                                "elapsed_s": v["t"] - start,
                                "mediaanalysisd_cpu_percent": sum(
                                    p["cpu_percent"]
                                    for p in v["clients"]
                                    if p["name"] == "mediaanalysisd"
                                ),
                                "agx_gpu_utilisation_percent": v["gpu_percent"],
                                "blocking_activity": busy(v),
                            }
                            for v in during
                        ],
                        "maximum_foreign_client_cpu_percent": max(
                            (
                                p["cpu_percent"]
                                for sample in during
                                for p in sample["clients"]
                                if p["name"] in ACTIVE_GENERATORS
                            ),
                            default=0,
                        ),
                        "maximum_background_media_cpu_percent": max(
                            (
                                p["cpu_percent"]
                                for sample in during
                                for p in sample["clients"]
                                if p["name"] not in ACTIVE_GENERATORS
                            ),
                            default=0,
                        ),
                    }
                )
                print(name, sampling, repeat + 1, n / wall, flush=True)
    activity.close()
    summary = {
        name: {
            "median_fps": statistics.median(r["fps"] for r in rows),
            "native_median_fps": statistics.median(
                r["fps"] for r in measurements["native"][name]
            ),
            "mode": modes[name],
            "repeats": rows,
            "native_repeats": measurements["native"][name],
        }
        for name, rows in measurements["sampled"].items()
    }
    for r in summary.values():
        r["match_2fps_minutes"] = 10800 / r["median_fps"] / 60
        r["match_native_minutes"] = 5400 * native / r["native_median_fps"] / 60
    dump(
        a.out,
        {
            "models": summary,
            "errors": errors,
            "idle_preflight": idle_before,
            "total_quiet_wait_s": activity.waited_s,
            "quiet_wait_cap_s": 900,
            "timing_status": "contended (steady background load)"
            if any(
                r["timing_status"].startswith("contended")
                for modes_rows in measurements.values()
                for rows in modes_rows.values()
                for r in rows
            )
            else "quiet known clients (steady background load)",
            "contention_observation": json.loads(
                (root / "round5-resource-observation.json").read_text()
            )
            if (root / "round5-resource-observation.json").exists()
            else {"limitation": "No prior resource observation recorded for this run."},
            "optimized_train_parity": parity,
            "native_fps": native,
            "hardware": "Apple M4 Max, 128 GiB unified memory; torch CPU threads8, OpenCV threads1",
            "clips": [c["clip_id"] for c in selected],
            "protocol": "3 interleaved repeats per model per sampling mode after bench training/inference stopped. Before each repeat require three quiet one-second observations: GPU utilization <=10%, empty ComfyUI queue, and Ollama workers below2% CPU. Poll active llama-server/Ollama, bench training/inference and ComfyUI during timing. The total quiet wait across all repeats is capped at 15 minutes; after exhaustion repeats proceed and are labelled contended (steady background load). Activity starting during a repeat also labels that repeat contended. Every repeat records mediaanalysisd CPU percent and ioreg AGXAccelerator GPU utilization samples. macOS media-analysis CPU load is recorded separately: sustained roughly two-core housekeeping was observed with0% GPU utilization, so it is not treated as active GPU work. These are observed desktop conditions, not an otherwise-idle-CPU laboratory. This detects known competing work, not every possible GPU client. Sampled mode covers all 2fps samples of the three TRAIN clips; native mode covers the first 64 consecutive native frames of each (192 frames/repeat). Warmup/compile excluded; source decode (including skipped frames), RGB conversion, cropping/padding, four-tile batched inference and prediction materialization included. Merge/JSON writing excluded consistently. Accuracy passes use eager FP32 separately; these optimized throughput measurements do not substitute for scored outputs.",
            "projection": "Separate linear projections from measured 2fps-pipeline and native-pipeline throughput; native does not inherit skipped-frame decode cost. These are not actual 90-minute match runs. Native bursts include three seeks per192 frames, a conservative overhead versus continuous match decoding; long-run thermal behaviour is unmeasured.",
            "old_yolo_discrepancy": "UNCONFIRMED: historical 11.51 vs 50.9–51.0 FPS were separate sessions. Current controlled session resolves present throughput, not their historical cause.",
        },
    )


if __name__ == "__main__":
    main()
