"""Fresh low-confidence passes; YOLO remains a bench-only comparison adapter."""

from __future__ import annotations
import argparse
import json
from pathlib import Path
from common import DEFAULT_MANIFEST, DEFAULT_SOURCE, load_dataset, sha256
from compare_ball import load_measurements

import time

from common import (
    HERE,
    dump,
    samples,
)
from detectors import merge_tiles, tile_bounds
from human_loop import write_jsonl
from rfdetr_data import restore_box, square_pad


class YoloAdapter:
    def __init__(self, weights):
        from ultralytics import YOLO

        self.model = YOLO(weights)

    def predict(self, tiles, threshold):
        from types import SimpleNamespace

        # RF inputs are padded; YOLO receives the original native rectangular crop.
        outputs = self.model.predict(
            [tile[:540, :, ::-1].copy() for tile in tiles],
            imgsz=960,
            device="mps",
            conf=threshold,
            iou=0.5,
            verbose=False,
        )
        return [
            SimpleNamespace(
                xyxy=p.boxes.xyxy.cpu().numpy(),
                confidence=p.boxes.conf.cpu().numpy(),
                class_id=p.boxes.cls.cpu().numpy(),
            )
            for p in outputs
        ]


def load_model(weights, kind, optimize=False, half=False):
    if kind == "yolo":
        return YoloAdapter(str(weights))
    from rfdetr import RFDETRNano
    import torch

    model = RFDETRNano(
        pretrain_weights=str(weights), resolution=960, num_classes=1, device="mps"
    )
    if optimize:
        model.optimize_for_inference(
            batch_size=4, dtype=torch.float16 if half else torch.float32
        )
    return model


def predict_all(model, clips, out, frozen_set_id, fit):
    import numpy as np
    import torch

    model.predict([np.full((960, 960, 3), 114, dtype=np.uint8)] * 4, threshold=0.01)
    torch.mps.synchronize()
    outputs, suggestions = {}, []
    for clip in clips:
        torch.mps.synchronize()
        start, rows = time.perf_counter(), []
        bounds = tile_bounds(1920, 1080, 2)
        for sample, stack in samples(clip):
            tiles = [square_pad(stack[-1][b:d, a:c]) for a, b, c, d in bounds]
            predictions = model.predict(tiles, threshold=0.01)
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
            "threshold": 0.01,
            "source_size": [1920, 1080],
            "training_split": fit["split"],
            "training_labels_sha256": fit["labels_sha256"],
            "weights_sha256": fit["weights_sha256"],
            "licence": fit.get("licence", "AGPL-3.0 bench-only"),
            "outputs": outputs,
        },
    )
    write_jsonl(out / "suggestions.jsonl", suggestions)


def evaluation_marker(root):
    """No new held-out pass before both final checkpoints exist and validate."""
    from datetime import datetime, timezone

    summaries = {}
    for letter in "ab":
        directory = root / f"mj-r5-rf-{letter}"
        fit_path = directory / "fit_summary.json"
        fit = json.loads(fit_path.read_text())
        if fit["weights_sha256"] != sha256(directory / "weights.pt"):
            raise ValueError("final checkpoint changed before evaluation")
        summaries[letter] = sha256(fit_path)
    protocol_path = HERE / "fixtures/round5_execution.json"
    marker_path = root / "round5-evaluation-start.json"
    digest = sha256(protocol_path)
    if marker_path.exists():
        marker = json.loads(marker_path.read_text())
        if (
            marker["fit_summaries_sha256"] != summaries
            or marker["protocol_sha256"] != digest
        ):
            raise ValueError("fit or protocol changed between saved passes")
    else:
        dump(
            marker_path,
            {
                "utc": datetime.now(timezone.utc).isoformat(),
                "fit_summaries_sha256": summaries,
                "protocol_sha256": digest,
                "protocol_snapshot": json.loads(protocol_path.read_text()),
                "definition": "Both final checkpoint hashes validated before the first new held-out inference; all intermediate results remain diagnostic.",
            },
        )


def main():
    import cv2
    import torch

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--kind", choices=["rf", "yolo"], default="rf")
    a = p.parse_args()
    if a.model.parent.name in {"mj-r5-rf-a", "mj-r5-rf-b"}:
        evaluation_marker(a.model.parent.parent)
    if a.out.exists():
        raise ValueError("preserve existing passes")
    a.out.mkdir(parents=True)
    cv2.setNumThreads(1)
    torch.set_num_threads(8)
    fit = json.loads((a.model.parent / "fit_summary.json").read_text())
    fit["weights_sha256"] = sha256(a.model)
    if "labels_sha256" not in fit:
        fit["labels_sha256"] = sha256(Path.home() / "codex-runs/ball-human-truth.jsonl")
    if "split" not in fit:
        fit["split"] = json.loads(
            (HERE / "fixtures/round2_execution.json").read_text()
        )["split"]
    _, clips = load_dataset(DEFAULT_MANIFEST, DEFAULT_SOURCE)
    predict_all(
        load_model(a.model, a.kind),
        clips,
        a.out,
        load_measurements()["frozen_set_id"],
        fit,
    )


if __name__ == "__main__":
    main()
