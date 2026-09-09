"""RF-DETR wrappers use the production loader/filter and InferenceSlicer."""

from __future__ import annotations
import importlib.util
import math
import sys
from pathlib import Path
from typing import Any
import numpy as np


def merge_tiles(detections, iou_threshold=0.5):
    """Stable class-agnostic NMS of source-coordinate ball boxes."""
    ordered = sorted(detections, key=lambda d: (-d["confidence"], tuple(d["box"])))
    result: list[dict[str, Any]] = []
    for candidate in ordered:
        a = candidate["box"]
        keep = True
        for existing in result:
            b = existing["box"]
            intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(
                0, min(a[3], b[3]) - max(a[1], b[1])
            )
            union = (
                (a[2] - a[0]) * (a[3] - a[1])
                + (b[2] - b[0]) * (b[3] - b[1])
                - intersection
            )
            if union > 0 and intersection / union > iou_threshold:
                keep = False
                break
        if keep:
            result.append(candidate)
    return result


class RFDetector:
    def __init__(self, grid, size):
        import supervision as sv

        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from run_spike import load_detector, detect_batch, keep_classes

        self.model = load_detector("medium", "mps", None)
        self.device = str(self.model.model.device)
        if self.device != "mps":
            raise RuntimeError(f"RF-DETR unexpectedly fell back to {self.device}")
        self.resolution = self.model.model.resolution
        self.predict_batch = detect_batch
        self.keep = keep_classes
        self.slicer = None
        if grid > 1:
            # Exactly grid origins per axis with 100 source-pixel overlaps.
            tile = tuple(math.ceil((n + (grid - 1) * 100) / grid) for n in size)
            self.slicer = sv.InferenceSlicer(
                callback=self.callback,
                slice_wh=tile,
                overlap_wh=(100, 100),
                overlap_filter=sv.OverlapFilter.NON_MAX_SUPPRESSION,
                iou_threshold=0.5,
                thread_workers=1,
            )

    def callback(self, image):
        return self.keep(
            self.predict_batch(self.model, [image], 0.1)[0], {"sports ball"}, {37}
        )

    def __call__(self, stack, source_size):
        image = stack[-1]
        det = self.slicer(image) if self.slicer else self.callback(image)
        sx, sy = source_size[0] / image.shape[1], source_size[1] / image.shape[0]
        rows = []
        for box, confidence in zip(det.xyxy, det.confidence):
            x1, y1, x2, y2 = [float(v) for v in box * [sx, sy, sx, sy]]
            rows.append(
                {
                    "box": [x1, y1, x2, y2],
                    "xy": [(x1 + x2) / 2, (y1 + y2) / 2],
                    "confidence": float(confidence),
                    "size_px": min(x2 - x1, y2 - y1),
                }
            )
        return merge_tiles(rows)


class WASBDetector:
    def __init__(self, checkout, weights, device="mps"):
        import torch
        from omegaconf import OmegaConf

        source = Path(checkout) / "src"
        spec = importlib.util.spec_from_file_location(
            "wasb_hrnet", source / "models/hrnet.py"
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("cannot load WASB HRNet source")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        config = OmegaConf.load(source / "configs/model/wasb.yaml")
        self.model = module.HRNet(config)
        checkpoint = torch.load(weights, map_location="cpu", weights_only=True)
        self.model.load_state_dict(checkpoint["model_state_dict"], strict=True)
        self.model.to(device).eval()
        self.device = device
        self.resolution = [512, 288]

    def __call__(self, stack, source_size):
        import torch
        import cv2

        tensors = []
        for image in stack:
            height, width = image.shape[:2]
            affine = np.array(
                [[512 / width, 0, 0], [0, 512 / width, 144 - height * 256 / width]],
                dtype=np.float32,
            )
            data = (
                cv2.warpAffine(
                    image, affine, (512, 288), flags=cv2.INTER_LINEAR
                ).astype(np.float32)
                / 255
            )
            data = (
                data - np.array([0.485, 0.456, 0.406], dtype=np.float32)
            ) / np.array([0.229, 0.224, 0.225], dtype=np.float32)
            tensors.append(data.transpose(2, 0, 1))
        tensor = torch.from_numpy(np.concatenate(tensors)[None]).to(self.device)
        with torch.inference_mode():
            # Last output heatmap corresponds to the last of 3 native frames.
            heatmap = self.model(tensor)[0][0, 2].sigmoid().cpu().numpy()
        _, binary = cv2.threshold(heatmap, 0.5, 1, cv2.THRESH_BINARY)
        count, labels = cv2.connectedComponents(binary.astype(np.uint8))
        blobs: list[dict[str, Any]] = []
        for label in range(1, count):
            ys, xs = np.where(labels == label)
            weights = heatmap[ys, xs]
            x = float(np.average(xs, weights=weights)) * source_size[0] / 512
            y = float(np.average(ys, weights=weights)) * source_size[1] / 288
            blobs.append(
                {
                    "xy": [x, y],
                    "confidence": float(weights.max()),
                    "box": None,
                    "size_px": None,
                    "heatmap_mass": float(weights.sum()),
                }
            )
        # Upstream intra-frame peak uses heatmap-weighted blob mass.
        return [max(blobs, key=lambda d: d["heatmap_mass"])] if blobs else []
