"""One frozen-corpus RF-DETR pass per final checkpoint, after both fits finish."""

from __future__ import annotations

from output_guard import guard_outputs
import json
import time
from pathlib import Path

from common import (
    DEFAULT_MANIFEST,
    DEFAULT_SOURCE,
    HERE,
    dump,
    load_dataset,
    samples,
    sha256,
)
from compare_ball import load_measurements
from detectors import merge_tiles, tile_bounds
from human_loop import write_jsonl
from rfdetr_data import restore_box, square_pad


def predict_all(model, clips, out, frozen_set_id, fit):
    import numpy as np
    import torch

    model.predict([np.full((960, 960, 3), 114, dtype=np.uint8)] * 4, threshold=0.1)
    torch.mps.synchronize()
    outputs, suggestions = {}, []
    for clip in clips:
        torch.mps.synchronize()
        start, rows = time.perf_counter(), []
        bounds = tile_bounds(1920, 1080, 2)
        for sample, stack in samples(clip):
            tiles = [square_pad(stack[-1][b:d, a:c]) for a, b, c, d in bounds]
            predictions = model.predict(tiles, threshold=0.1)
            if len(predictions) != len(bounds):
                raise RuntimeError("RF-DETR must return one prediction per tile")
            ds = []
            for prediction, tile in zip(predictions, bounds):
                for box, confidence, category in zip(
                    prediction.xyxy, prediction.confidence, prediction.class_id
                ):
                    if category != 0:
                        continue
                    restored = restore_box(box, tile)
                    if restored is None:
                        continue
                    a, b, c, d = restored
                    ds.append(
                        {
                            "box": restored,
                            "xy": [(a + c) / 2, (b + d) / 2],
                            "confidence": float(confidence),
                            "size_px": min(c - a, d - b),
                        }
                    )
            ds = merge_tiles(ds)
            rows.append({**sample, "detections": ds})
            if ds:
                top = max(ds, key=lambda d: d["confidence"])
                suggestions.append(
                    {
                        "clip": clip["clip_id"],
                        "t": sample["t"],
                        "x": top["xy"][0],
                        "y": top["xy"][1],
                        "score": top["confidence"],
                        "source": f"model:{out.name}",
                    }
                )
        torch.mps.synchronize()
        wall = time.perf_counter() - start
        outputs[clip["clip_id"]] = {
            "clip": clip["clip_id"],
            "duration_s": clip["duration_s"],
            "wall_s": wall,
            "frames": rows,
        }
        print(
            f"RF predict {out.name} {clip['clip_id']}: {len(rows)} frames {wall:.2f}s",
            flush=True,
        )
    dump(
        out / "detections.json",
        {
            "schema_version": 1,
            "frozen_set_id": frozen_set_id,
            "source_sha256": sha256(clips[0]["video"]),
            "candidate": out.name,
            "synthetic_smoke": False,
            "threshold": 0.1,
            "source_size": [1920, 1080],
            "training_split": fit["split"],
            "training_labels_sha256": fit["labels_sha256"],
            "weights_sha256": fit["weights_sha256"],
            "licence": "Apache-2.0",
            "outputs": outputs,
        },
    )
    write_jsonl(out / "suggestions.jsonl", suggestions)


def main():
    guard_outputs(HERE / "fixtures/round4_execution.json")
    import cv2
    import torch
    from rfdetr import RFDETRNano

    cv2.setNumThreads(1)
    torch.set_num_threads(8)
    root = Path.home() / "models/tinyball"
    fits = {
        c: json.loads((root / f"mj-r4-rf-{c}/fit_summary.json").read_text())
        for c in "ab"
    }
    state_path = root / "round4-fit-state.json"
    dump(state_path, {"fits": fits, "evaluation_started": False})
    marker = root / "round4-evaluation-start.json"
    if marker.exists():
        raise ValueError("Evaluation already started; preserve saved passes")
    protocol = HERE / "fixtures/round4_execution.json"
    protocol_data = json.loads(protocol.read_text())
    for name, digest in protocol_data["training_code_sha256"].items():
        if sha256(HERE / name) != digest:
            raise ValueError("training code changed after protocol freezing")
    protocol_data["status"] = (
        "Both fits complete; first saved inference passes starting"
    )
    protocol_data["fit_state_sha256"] = sha256(state_path)
    dump(protocol, protocol_data)
    dump(
        marker,
        {
            "fit_state_sha256": sha256(state_path),
            "protocol_sha256": sha256(protocol),
            "protocol_snapshot": protocol_data,
        },
    )
    m = load_measurements()
    _, clips = load_dataset(DEFAULT_MANIFEST, DEFAULT_SOURCE)
    for c, fit in fits.items():
        out = root / f"mj-r4-rf-{c}"
        if (
            sha256(out / "weights.pt") != fit["weights_sha256"]
            or (out / "detections.json").exists()
        ):
            raise ValueError("changed checkpoint or existing pass")
        model = RFDETRNano(
            pretrain_weights=str(out / "weights.pt"),
            resolution=fit["resolution"],
            num_classes=1,
            device="mps",
        )
        predict_all(model, clips, out, m["frozen_set_id"], fit)
        del model
        torch.mps.empty_cache()


if __name__ == "__main__":
    main()
