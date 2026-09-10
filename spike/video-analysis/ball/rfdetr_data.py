"""Native, square-padded point supervision shared by RF-DETR fitting/inference.

No Ultralytics imports. Private image/annotation datasets stay outside git.
"""

from __future__ import annotations

import math
import statistics

from common import dump, samples
from detectors import merge_tiles, tile_bounds
from scale_targets import fit_scale


def scale_side(label, fit, floor):
    if not math.isfinite(floor) or not 6 <= floor <= 48:
        raise ValueError("scale floor must be in [6,48] native px")
    return min(
        48.0,
        max(floor, fit["intercept_px"] + fit["slope_px_per_image_y_px"] * label["y"]),
    )


def target_boxes(label, bounds, side, teacher=(), pseudo=False):
    x0, y0, x1, y1 = bounds
    if not label["visible"] or not (x0 <= label["x"] < x1 and y0 <= label["y"] < y1):
        return []
    x, y = label["x"], label["y"]
    ds = [
        {
            "box": [x - side / 2, y - side / 2, x + side / 2, y + side / 2],
            "confidence": 1.0,
        }
    ]
    if pseudo:
        ds += [
            d
            for d in teacher
            if d["confidence"] >= 0.1 and math.dist(d["xy"], [x, y]) <= 20
        ]
    result = []
    for d in merge_tiles(ds):
        a, b, c, e = d["box"]
        a, b, c, e = max(a, x0), max(b, y0), min(c, x1), min(e, y1)
        if a < c and b < e:
            # Top-left tile placement; padding is exclusively below/right.
            result.append([a - x0, b - y0, c - x0, e - y0])
    return result


def square_pad(image):
    import numpy as np

    h, w = image.shape[:2]
    padded = np.full((max(h, w), max(h, w), 3), 114, dtype=np.uint8)
    padded[:h, :w] = image
    return padded


def restore_box(box, bounds):
    """RF predict returns coordinates in the original padded 960-square image."""
    x0, y0, x1, y1 = bounds
    a, b, c, d = map(float, box)
    # Never project a prediction whose centre lies in artificial padding into play.
    if not (0 <= (a + c) / 2 < x1 - x0 and 0 <= (b + d) / 2 < y1 - y0):
        return None
    a, b, c, d = max(0.0, a), max(0.0, b), min(x1 - x0, c), min(y1 - y0, d)
    if a >= c or b >= d:
        return None
    return [a + x0, b + y0, c + x0, d + y0]


def prepare(measurements, clips, labels, out, split, floor, pseudo=False):
    import cv2

    out.mkdir(parents=True, exist_ok=False)
    fit = fit_scale(measurements, labels, split["train"])
    fit.update(
        mode="train_affine_with_minimum",
        clip_px=[floor, 48],
        definition="OLS nearest TRAIN RF 2x2 matched short side versus native image y. Every visible TRAIN label receives clamp(affine(y), floor, 48), including labels with a matched box. No held-out observations or direct matched-size overrides.",
    )
    records, sides = [], []
    for clip in clips:
        cid = clip["clip_id"]
        if cid not in split["train"]:
            continue
        saved = {
            r["t"]: r["detections"]
            for r in measurements["outputs"]["rf_2x2"][cid]["frames"]
        }
        for sample, stack in samples(clip):
            label = labels.get((cid, sample["t"]))
            if label is None:
                continue
            side = scale_side(label, fit, floor) if label["visible"] else 0
            if label["visible"]:
                sides.append(side)
            for i, bounds in enumerate(tile_bounds(1920, 1080, 2)):
                x0, y0, x1, y1 = bounds
                filename = f"{cid}-{sample['sample_index']:05d}-{i}.jpg"
                padded = square_pad(stack[-1][y0:y1, x0:x1])
                if not cv2.imwrite(
                    str(out / filename),
                    cv2.cvtColor(padded, cv2.COLOR_RGB2BGR),
                    [cv2.IMWRITE_JPEG_QUALITY, 98],
                ):
                    raise RuntimeError("dataset image write failed")
                records.append(
                    {
                        "file": filename,
                        "clip": cid,
                        "boxes": target_boxes(
                            label, bounds, side, saved[sample["t"]], pseudo
                        ),
                    }
                )
        print(f"prepared TRAIN {cid}", flush=True)
    dump(out / "annotations.json", records)
    return {
        "split": split,
        "counts": {
            "train": len(records),
            "val": 0,
            "positive_tiles": sum(bool(r["boxes"]) for r in records),
            "negative_tiles": sum(not r["boxes"] for r in records),
        },
        "box_recipe": fit,
        "pseudo": pseudo,
        "target_distribution": {
            "count": len(sides),
            "median_px": statistics.median(sides),
            "min_px": min(sides),
            "max_px": max(sides),
            "at_floor": sum(s == floor for s in sides),
            "ge24": sum(s >= 24 for s in sides),
        },
        "tiling": "Native non-overlapping 2x2 960x540 crops, pad bottom 420px with RGB114 to 960x960, then uniform square resize. No anisotropic squash.",
        "negative_policy": "Only human-labelled TRAIN frames: non-click tiles are negative; all four tiles negative when no ball visible. Unlabelled and held-out frames never enter training. Pseudo boxes opt-in only.",
    }


def dataset_class():
    import json
    import random
    import torch
    from PIL import Image
    from torch.utils.data import Dataset
    from torchvision.transforms import functional as F

    class Tiles(Dataset):
        def __init__(self, root, resolution):
            self.root, self.resolution = root, resolution
            self.records = json.loads((root / "annotations.json").read_text())

        def __len__(self):
            return len(self.records)

        def __getitem__(self, index):
            record = self.records[index]
            with Image.open(self.root / record["file"]) as source:
                image = F.resize(
                    source.convert("RGB"), [self.resolution, self.resolution]
                )
            boxes = (
                torch.tensor(record["boxes"], dtype=torch.float32).reshape(-1, 4) / 960
            )
            if random.random() < 0.5:
                image = F.hflip(image)
                boxes[:, [0, 2]] = 1 - boxes[:, [2, 0]]
            image = F.normalize(
                F.to_tensor(image), [0.485, 0.456, 0.406], [0.229, 0.224, 0.225]
            )
            # RF criterion consumes normalized cx/cy/w/h boxes and zero-based labels.
            boxes = torch.cat(
                ((boxes[:, :2] + boxes[:, 2:]) / 2, boxes[:, 2:] - boxes[:, :2]), dim=1
            )
            return image, {
                "boxes": boxes,
                "labels": torch.zeros(len(boxes), dtype=torch.int64),
                "image_id": torch.tensor([index]),
                "orig_size": torch.tensor([960, 960]),
                "size": torch.tensor([self.resolution, self.resolution]),
            }

    return Tiles
