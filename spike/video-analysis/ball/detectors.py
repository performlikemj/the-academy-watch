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
    def __init__(self, grid, size, resolution=None, device="mps"):
        import supervision as sv

        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from run_spike import load_detector, detect_batch, keep_classes

        self.model = load_detector("medium", device, resolution)
        self.device = str(self.model.model.device)
        if self.device != device:
            raise RuntimeError(f"RF-DETR requested {device}, loaded on {self.device}")
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
    def __init__(self, checkout, weights, device="mps", grid=1):
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
        self.grid = grid

    def heatmaps(self, stack):
        """Return all three sigmoid channels per tile for parity and last-frame reads."""
        import torch
        import cv2

        height, width = stack[-1].shape[:2]
        results = []
        for x1, y1, x2, y2 in tile_bounds(width, height, self.grid):
            tensors = []
            scale = 512 / (x2 - x1)
            pad = 144 - (y2 - y1) * scale / 2
            affine = np.array([[scale, 0, 0], [0, scale, pad]], dtype=np.float32)
            for image in stack:
                data = (
                    cv2.warpAffine(
                        image[y1:y2, x1:x2], affine, (512, 288), flags=cv2.INTER_LINEAR
                    ).astype(np.float32)
                    / 255
                )
                data = (
                    data - np.array([0.485, 0.456, 0.406], dtype=np.float32)
                ) / np.array([0.229, 0.224, 0.225], dtype=np.float32)
                tensors.append(data.transpose(2, 0, 1))
            tensor = torch.from_numpy(np.concatenate(tensors)[None]).to(self.device)
            with torch.inference_mode():
                heatmaps = self.model(tensor)[0][0].sigmoid().cpu().numpy()
            results.append(((x1, y1, scale, pad), heatmaps))
        return results

    def __call__(self, stack, source_size):
        import cv2

        height, width = stack[-1].shape[:2]
        selected: list[dict[str, Any]] = []
        for (x1, y1, scale, pad), heatmaps in self.heatmaps(stack):
            heatmap = heatmaps[2]
            count, labels = cv2.connectedComponents((heatmap > 0.5).astype(np.uint8))
            blobs: list[dict[str, Any]] = []
            for label in range(1, count):
                ys, xs = np.where(labels == label)
                weights = heatmap[ys, xs]
                x = (
                    (float(np.average(xs, weights=weights)) / scale + x1)
                    * source_size[0]
                    / width
                )
                y = (
                    ((float(np.average(ys, weights=weights)) - pad) / scale + y1)
                    * source_size[1]
                    / height
                )
                if not (0 <= x < source_size[0] and 0 <= y < source_size[1]):
                    continue
                blobs.append(
                    {
                        "xy": [x, y],
                        "confidence": float(weights.max()),
                        "box": None,
                        "size_px": None,
                        "heatmap_mass": float(weights.sum()),
                    }
                )
            if blobs:
                selected.append(max(blobs, key=lambda d: d["heatmap_mass"]))
        return merge_points(selected)


def tile_bounds(width, height, grid):
    """Non-overlapping WASB tiles; 1080p 2x2 is four 960x540 inputs."""
    if grid not in (1, 2):
        raise ValueError("WASB supports full or 2x2")
    return [
        (
            col * width // grid,
            row * height // grid,
            (col + 1) * width // grid,
            (row + 1) * height // grid,
        )
        for row in range(grid)
        for col in range(grid)
    ]


def merge_points(points, radius=40.0):
    """Suppress duplicate tile peaks by source-pixel distance; no invented boxes."""
    result: list[dict[str, Any]] = []
    for point in sorted(points, key=lambda d: (-d["heatmap_mass"], tuple(d["xy"]))):
        if all(math.dist(point["xy"], existing["xy"]) > radius for existing in result):
            result.append(point)
    return result
