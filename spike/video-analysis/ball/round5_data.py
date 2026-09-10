"""TRAIN-only affine augmentation and immutable-label hard-negative replay."""

from __future__ import annotations
import json
import math
import random
from pathlib import Path


def transform_boxes(boxes, scale, dx, dy, flip=False):
    result = []
    for a, b, c, d in boxes:
        a, c = [(v - 480) * scale + 480 + dx for v in (a, c)]
        b, d = [(v - 270) * scale + 270 + dy for v in (b, d)]
        a, b, c, d = max(0, a), max(0, b), min(960, c), min(540, d)
        if c - a < 1 or d - b < 1:
            continue
        result.append([960 - c, b, 960 - a, d] if flip else [a, b, c, d])
    return result


def is_hard(boxes, scores, click):
    return any(
        score >= 0.3
        and 0 <= box[0] < 960
        and 0 <= box[1] < 540
        and (click is None or math.dist(box[:2], click) > 20)
        for box, score in zip(boxes, scores)
    )


def dataset_class():
    import cv2
    import numpy as np
    import torch
    from torch.utils.data import Dataset

    class Tiles(Dataset):
        def __init__(self, root, augment=True, records=None):
            self.root = Path(root)
            self.records = (
                records
                if records is not None
                else json.loads((self.root / "annotations.json").read_text())
            )
            self.indices = list(range(len(self.records)))
            self.augment = augment

        def __len__(self):
            return len(self.indices)

        def __getitem__(self, index):
            original = self.indices[index]
            record = self.records[original]
            image = cv2.imread(str(self.root / record["file"]))
            if image is None:
                raise ValueError("missing TRAIN image")
            image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            boxes = record["boxes"]
            if self.augment:
                scale = random.uniform(0.8, 1.2)
                dx, dy = random.uniform(-48, 48), random.uniform(-27, 27)
                flip = random.random() < 0.5
                matrix = np.array(
                    [
                        [scale, 0, 480 * (1 - scale) + dx],
                        [0, scale, 270 * (1 - scale) + dy],
                    ],
                    dtype=np.float32,
                )
                # Transform content only; keep the known padding region artificial.
                content = cv2.warpAffine(
                    image[:540], matrix, (960, 540), borderValue=(114, 114, 114)
                )
                image[:540] = content[:, ::-1] if flip else content
                boxes = transform_boxes(boxes, scale, dx, dy, flip)
            image = (
                torch.from_numpy(np.ascontiguousarray(image.transpose(2, 0, 1))).float()
                / 255
            )
            image = (
                image - torch.tensor([0.485, 0.456, 0.406])[:, None, None]
            ) / torch.tensor([0.229, 0.224, 0.225])[:, None, None]
            boxes = torch.tensor(boxes, dtype=torch.float32).reshape(-1, 4) / 960
            boxes = torch.cat(
                ((boxes[:, :2] + boxes[:, 2:]) / 2, boxes[:, 2:] - boxes[:, :2]), 1
            )
            return image, {
                "boxes": boxes,
                "labels": torch.zeros(len(boxes), dtype=torch.int64),
                "image_id": torch.tensor([original]),
                "orig_size": torch.tensor([960, 960]),
                "size": torch.tensor([960, 960]),
            }

    return Tiles
