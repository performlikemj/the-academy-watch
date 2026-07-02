#!/usr/bin/env python3
"""Phase 0 spike: time every pipeline stage on real footage, extrapolate to a
90-min match, and check the <=3.5 GPU-hour cost gate.

Stages (each wall-clock timed independently):
  decode   PyAV decode + sampling to --sample-fps
  detect   RF-DETR pretrained COCO (person + sports ball), batched;
           full-frame and/or supervision.InferenceSlicer per --slicer
  track    BoT-SORT from `trackers` (camera-motion compensation);
           falls back to supervision.ByteTrack if the import fails
  cluster  team assignment recipe: player crops -> SigLIP -> UMAP(3D) -> KMeans(k=2)
  render   30-second annotated sample clip (supervision annotators + cv2)

Outputs in --out: results.json + report.md (90-min extrapolation, $ at T4 and
Spot rates, PASS/FAIL vs the 3.5h gate).

Smoke test on Apple Silicon (sanity only, not a cost measurement):
  python run_spike.py --video footage/clip.mp4 --smoke
Full run on a rented GPU:
  python run_spike.py --video footage/match.mp4 --device cuda --slicer both
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, NoReturn

import numpy as np

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
from game_time import in_play_plan  # noqa: E402  (pure, stdlib-only marker->window translation)

SECOND_HALF_TID_OFFSET = 1_000_000  # keep 2nd-half tracker ids from colliding with 1st-half ids


def _fail(what: str, hint: str) -> NoReturn:
    print(f"ERROR: {what}\n  fix: {hint}", file=sys.stderr)
    sys.exit(1)


try:
    import cv2
except ImportError as e:
    _fail(f"opencv import failed: {e}", "pip install opencv-python-headless==4.13.0.92")

try:
    import av
except ImportError as e:
    _fail(f"PyAV import failed: {e}", "pip install av==17.1.0")

try:
    import supervision as sv
except ImportError as e:
    _fail(f"supervision import failed: {e}", "pip install supervision==0.28.0")

try:
    import torch
except ImportError as e:
    _fail(f"torch import failed: {e}", "pip install torch==2.12.0 (see pytorch.org for CUDA wheels)")

# COCO category ids used by RF-DETR pretrained checkpoints (raw sparse ids).
PERSON_ID = 1
BALL_ID = 37
WANTED_NAMES = {"person", "sports ball"}

MATCH_SECONDS = 90 * 60
GATE_HOURS = 3.5
RATE_T4_ACA = 0.84  # ACA serverless T4 + 4 vCPU + 16 GiB, all-in $/hr
RATE_T4_SPOT = 0.32  # AML NC8as_T4_v3 Spot $/hr


# --------------------------------------------------------------------------- timing


class StageTimer:
    """Accumulating per-stage wall-clock timer."""

    def __init__(self) -> None:
        self.seconds: dict[str, float] = {}
        self.units: dict[str, int] = {}

    @contextmanager
    def time(self, stage: str, units: int = 0) -> Iterator[None]:
        t0 = time.perf_counter()
        try:
            yield
        finally:
            self.add(stage, time.perf_counter() - t0, units)

    def add(self, stage: str, seconds: float, units: int = 0) -> None:
        self.seconds[stage] = self.seconds.get(stage, 0.0) + seconds
        self.units[stage] = self.units.get(stage, 0) + units

    def fps(self, stage: str) -> float:
        s = self.seconds.get(stage, 0.0)
        return self.units.get(stage, 0) / s if s > 0 else 0.0

    def as_dict(self) -> dict[str, dict[str, float]]:
        return {
            k: {"seconds": round(v, 3), "units": self.units.get(k, 0), "units_per_sec": round(self.fps(k), 3)}
            for k, v in self.seconds.items()
        }


# --------------------------------------------------------------------------- video io


@dataclass
class VideoMeta:
    path: str
    duration_s: float
    native_fps: float
    width: int
    height: int


def probe_video(path: Path) -> VideoMeta:
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        duration = float(stream.duration * stream.time_base) if stream.duration else (
            float(container.duration / av.time_base) if container.duration else 0.0
        )
        fps = float(stream.average_rate) if stream.average_rate else 25.0
        return VideoMeta(str(path), duration, fps, stream.codec_context.width, stream.codec_context.height)


def iter_sampled_frames(
    path: Path,
    sample_fps: float,
    max_seconds: float | None,
    timer: StageTimer | None,
    start_s: float = 0.0,
) -> Iterator[tuple[int, float, np.ndarray]]:
    """Yield (sample_index, pts_seconds, rgb_frame) at sample_fps for t in [start_s, max_seconds].

    The sampling grid is anchored at t=0 regardless of start_s, so chunked runs
    of the same video land on the same global grid. max_seconds is an ABSOLUTE
    end timestamp. Decode work is accumulated into timer stage 'decode'
    (timer=None to skip, e.g. for the slicer re-decode pass).
    """
    interval = 1.0 / sample_fps
    next_t = int(start_s / interval) * interval if start_s > 0 else 0.0
    idx = 0
    raw = 0
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        if start_s > 0:
            container.seek(int(start_s / stream.time_base), stream=stream, backward=True)
        decoder = container.decode(stream)
        while True:
            t0 = time.perf_counter()
            try:
                frame = next(decoder, None)
            except Exception as exc:  # corrupt packet mid-file: end gracefully, keep the data
                print(f"WARNING: decode error after {idx} sampled frames ({exc!r}); ending decode early")
                if timer:
                    timer.add("decode", time.perf_counter() - t0)
                return
            if frame is None:
                if timer:
                    timer.add("decode", time.perf_counter() - t0)
                return
            t = frame.time if frame.time is not None else raw / max(1.0, float(stream.average_rate or 25.0))
            raw += 1
            take = t + 1e-9 >= next_t and t + 1e-9 >= start_s
            rgb = frame.to_ndarray(format="rgb24") if take else None
            if timer:
                timer.add("decode", time.perf_counter() - t0, 1 if take else 0)
            if max_seconds is not None and t > max_seconds:
                return
            if t + 1e-9 >= next_t:
                while next_t <= t:
                    next_t += interval
            if take:
                yield idx, t, rgb
                idx += 1


# --------------------------------------------------------------------------- detection


def pick_device(arg: str) -> str:
    if arg != "auto":
        return arg
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def load_detector(model_size: str, device: str, resolution: int | None) -> Any:
    try:
        import rfdetr
    except ImportError:
        _fail("rfdetr import failed", "pip install rfdetr==1.7.1")
    classes = {"nano": "RFDETRNano", "small": "RFDETRSmall", "medium": "RFDETRMedium", "large": "RFDETRLarge"}
    cls = getattr(rfdetr, classes[model_size])
    kwargs: dict[str, Any] = {"device": device}
    if resolution:
        kwargs["resolution"] = resolution
    try:
        return cls(**kwargs)
    except Exception as exc:  # e.g. mps unsupported op
        if device != "cpu":
            print(f"WARNING: detector init on {device} failed ({exc}); retrying on cpu")
            kwargs["device"] = "cpu"
            return cls(**kwargs)
        raise


def detect_batch(model: Any, frames: list[np.ndarray], threshold: float) -> list[sv.Detections]:
    result = model.predict(frames, threshold=threshold, include_source_image=False)
    return [result] if isinstance(result, sv.Detections) else list(result)


def keep_classes(det: sv.Detections, names: set[str], ids: set[int]) -> sv.Detections:
    if len(det) == 0:
        return det
    class_names = det.data.get("class_name") if det.data else None
    if class_names is not None:
        mask = np.array([str(n).lower() in names for n in class_names], dtype=bool)
    else:
        mask = np.isin(det.class_id, list(ids))
    return det[mask]


def only_people(det: sv.Detections) -> sv.Detections:
    return keep_classes(det, {"person"}, {PERSON_ID})


# --------------------------------------------------------------------------- pitch mask


def compute_pitch_mask(rgb: np.ndarray, scale_w: int = 320) -> tuple[np.ndarray | None, float]:
    """Largest green region of the frame, as a downscaled bool mask.

    Returns (mask, scale). mask is None when no plausible pitch is visible
    (replays, extreme pans) — callers should then keep all detections.
    """
    h, w = rgb.shape[:2]
    scale = scale_w / w
    small = cv2.resize(rgb, (scale_w, int(h * scale)))
    hsv = cv2.cvtColor(small, cv2.COLOR_RGB2HSV)
    green = cv2.inRange(hsv, (32, 40, 40), (90, 255, 255))
    green = cv2.morphologyEx(green, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(green, connectivity=4)
    if n < 2:
        return None, scale
    biggest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    frac = stats[biggest, cv2.CC_STAT_AREA] / (small.shape[0] * small.shape[1])
    if frac < 0.15:  # pitch not meaningfully in frame — can't trust the filter
        return None, scale
    return labels == biggest, scale


def filter_on_pitch(rgb: np.ndarray, det: sv.Detections) -> tuple[sv.Detections, int]:
    """Drop detections whose feet are off the pitch (sideline people, benches)."""
    if len(det) == 0:
        return det, 0
    mask, scale = compute_pitch_mask(rgb)
    if mask is None:
        return det, 0
    keep = np.zeros(len(det), dtype=bool)
    mh, mw = mask.shape
    for i, (x1, _y1, x2, y2) in enumerate(det.xyxy):
        cx = int((x1 + x2) / 2 * scale)
        cy = int(y2 * scale)
        cx, cy = min(max(cx, 0), mw - 1), min(max(cy, 0), mh - 1)
        # tolerate a few px of mask noise at the feet
        y0, y1b = max(0, cy - 3), min(mh, cy + 4)
        x0, x1b = max(0, cx - 3), min(mw, cx + 4)
        keep[i] = bool(mask[y0:y1b, x0:x1b].any())
    return det[keep], int((~keep).sum())


# --------------------------------------------------------------------------- tracking


def make_tracker(sample_fps: float) -> tuple[Callable[[sv.Detections, np.ndarray], sv.Detections], str]:
    try:
        from trackers import BoTSORTTracker

        tracker = BoTSORTTracker(frame_rate=sample_fps, lost_track_buffer=30, enable_cmc=True)
        return (lambda det, frame: tracker.update(det, frame=frame)), "trackers.BoTSORTTracker (CMC on)"
    except ImportError as exc:
        print(f"WARNING: `trackers` BoT-SORT unavailable ({exc}); falling back to supervision.ByteTrack")
        bt = sv.ByteTrack(frame_rate=max(1, round(sample_fps)))
        return (lambda det, frame: bt.update_with_detections(det)), "supervision.ByteTrack (fallback)"


class TrackStore:
    """Accumulates per-frame tracked detections; saved as tracks.npz for the merge pass."""

    def __init__(self) -> None:
        self.frames: list[np.ndarray] = []
        self.ts: list[np.ndarray] = []
        self.tids: list[np.ndarray] = []
        self.boxes: list[np.ndarray] = []
        self.confs: list[np.ndarray] = []

    def add(self, idx: int, t: float, tracked: sv.Detections) -> None:
        n = len(tracked)
        if n == 0 or tracked.tracker_id is None:
            return
        self.frames.append(np.full(n, idx, dtype=np.int32))
        self.ts.append(np.full(n, t, dtype=np.float32))
        self.tids.append(tracked.tracker_id.astype(np.int32))
        self.boxes.append(tracked.xyxy.astype(np.float32))
        conf = tracked.confidence if tracked.confidence is not None else np.ones(n)
        self.confs.append(conf.astype(np.float32))

    def save(self, path: Path) -> int:
        if not self.frames:
            return 0
        rows = int(sum(len(f) for f in self.frames))
        np.savez_compressed(
            path,
            frame=np.concatenate(self.frames),
            t=np.concatenate(self.ts),
            tid=np.concatenate(self.tids),
            xyxy=np.concatenate(self.boxes),
            conf=np.concatenate(self.confs),
        )
        return rows


@dataclass
class TrackletRegistry:
    spans: dict[int, list[float]] = field(default_factory=dict)  # tid -> [first_t, last_t, n_frames]

    def observe(self, tracked: sv.Detections, t: float) -> None:
        if tracked.tracker_id is None:
            return
        for tid in tracked.tracker_id:
            tid = int(tid)
            if tid < 0:
                continue
            span = self.spans.get(tid)
            if span is None:
                self.spans[tid] = [t, t, 1]
            else:
                span[1] = t
                span[2] += 1

    def stats(self, processed_seconds: float, sample_fps: float) -> dict[str, Any]:
        if not self.spans:
            return {"n_tracklets": 0}
        durations = [(last - first) + 1.0 / sample_fps for first, last, _ in self.spans.values()]
        minutes = max(processed_seconds / 60.0, 1e-9)
        return {
            "n_tracklets": len(self.spans),
            "mean_duration_s": round(statistics.mean(durations), 2),
            "median_duration_s": round(statistics.median(durations), 2),
            "max_duration_s": round(max(durations), 2),
            "tracklets_per_minute": round(len(self.spans) / minutes, 2),
            "note": "tracklets/min is an ID-switch proxy: ~22-30/90min would be perfect persistence; "
            "hundreds/min means constant identity churn",
        }


# --------------------------------------------------------------------------- render


class ClipRenderer:
    """Writes an annotated sample clip for frames whose pts falls in the window."""

    def __init__(self, out_path: Path, fps: float, start_s: float, duration_s: float) -> None:
        self.out_path = out_path
        self.fps = fps
        self.start_s = start_s
        self.end_s = start_s + duration_s
        self.writer: cv2.VideoWriter | None = None
        self.frames_written = 0
        self.ellipse = sv.EllipseAnnotator(color_lookup=sv.ColorLookup.TRACK)
        self.label = sv.LabelAnnotator(color_lookup=sv.ColorLookup.TRACK, text_scale=0.4)

    def wants(self, t: float) -> bool:
        return self.start_s <= t < self.end_s

    def add(self, rgb: np.ndarray, tracked: sv.Detections) -> None:
        if self.writer is None:
            h, w = rgb.shape[:2]
            self.out_path.parent.mkdir(parents=True, exist_ok=True)
            self.writer = cv2.VideoWriter(
                str(self.out_path), cv2.VideoWriter_fourcc(*"mp4v"), self.fps, (w, h)
            )
        scene = rgb.copy()
        if len(tracked) > 0 and tracked.tracker_id is not None:
            scene = self.ellipse.annotate(scene, tracked)
            labels = [f"#{int(tid)}" for tid in tracked.tracker_id]
            scene = self.label.annotate(scene, tracked, labels=labels)
        self.writer.write(cv2.cvtColor(scene, cv2.COLOR_RGB2BGR))
        self.frames_written += 1

    def close(self) -> None:
        if self.writer is not None:
            self.writer.release()


# --------------------------------------------------------------------------- team clustering


def crop_one(rgb: np.ndarray, xyxy: np.ndarray) -> np.ndarray | None:
    h, w = rgb.shape[:2]
    x1, y1, x2, y2 = (int(v) for v in xyxy)
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)
    if x2 - x1 < 12 or y2 - y1 < 24:
        return None
    crop = rgb[y1:y2, x1:x2]
    if crop.shape[0] > 256:  # bound memory; SigLIP resizes to 224 anyway
        scale = 256 / crop.shape[0]
        crop = cv2.resize(crop, (max(1, int(crop.shape[1] * scale)), 256))
    return crop


def sample_tracked_crops(
    rgb: np.ndarray,
    tracked: sv.Detections,
    idx: int,
    crop_records: list[tuple[int, np.ndarray]],
    tid_counts: dict[int, int],
    cap_total: int,
    cap_per_tid: int = 4,
) -> None:
    """Collect crops ATTRIBUTED to tracklets — the merge pass needs per-tracklet appearance."""
    if tracked.tracker_id is None or len(crop_records) >= cap_total:
        return
    for j, tid in enumerate(tracked.tracker_id):
        tid = int(tid)
        if tid_counts.get(tid, 0) >= cap_per_tid or len(crop_records) >= cap_total:
            continue
        if (idx + tid) % 5:  # spread samples over each tracklet's lifetime
            continue
        crop = crop_one(rgb, tracked.xyxy[j])
        if crop is not None:
            crop_records.append((tid, crop))
            tid_counts[tid] = tid_counts.get(tid, 0) + 1


def embed_crops(crops: list[np.ndarray], device: str, batch: int, timer: StageTimer) -> np.ndarray:
    try:
        from transformers import AutoImageProcessor, SiglipVisionModel
    except ImportError:
        _fail("transformers/SigLIP import failed", "pip install transformers==5.10.2")
    name = "google/siglip-base-patch16-224"
    with timer.time("cluster_model_load"):
        # Image processor only — AutoProcessor would also load SiglipTokenizer,
        # which needs sentencepiece; we never tokenize text.
        processor = AutoImageProcessor.from_pretrained(name)
        try:
            model = SiglipVisionModel.from_pretrained(name).to(device).eval()
        except Exception as exc:  # e.g. mps unsupported op
            if device == "cpu":
                raise
            print(f"WARNING: SigLIP on {device} failed ({exc}); retrying on cpu")
            device = "cpu"
            model = SiglipVisionModel.from_pretrained(name).to(device).eval()
    out: list[np.ndarray] = []
    for i in range(0, len(crops), batch):
        chunk = crops[i : i + batch]
        with timer.time("cluster_embed", units=len(chunk)):
            inputs = processor(images=chunk, return_tensors="pt").to(device)
            with torch.no_grad():
                pooled = model(**inputs).pooler_output
            out.append(pooled.float().cpu().numpy())
        if (i // batch) % 10 == 0:
            print(f"  cluster: embedded {min(i + batch, len(crops))}/{len(crops)} crops")
    return np.concatenate(out, axis=0) if out else np.zeros((0, 768), dtype=np.float32)


def cluster_teams(embeddings: np.ndarray, timer: StageTimer) -> tuple[dict[str, Any], np.ndarray | None]:
    if embeddings.shape[0] < 20:
        return {"status": "skipped", "reason": f"only {embeddings.shape[0]} crops collected"}, None
    try:
        import umap
        from sklearn.cluster import KMeans
        from sklearn.metrics import silhouette_score
    except ImportError:
        _fail("umap/sklearn import failed", "pip install umap-learn==0.5.12 scikit-learn==1.9.0")
    with timer.time("cluster_fit", units=embeddings.shape[0]):
        projected = umap.UMAP(n_components=3, random_state=42).fit_transform(embeddings)
        kmeans = KMeans(n_clusters=2, n_init=10, random_state=42)
        labels = kmeans.fit_predict(projected)
        sil = float(silhouette_score(projected, labels))
    sizes = np.bincount(labels, minlength=2).tolist()
    return {
        "status": "ok",
        "n_crops": int(embeddings.shape[0]),
        "cluster_sizes": sizes,
        "silhouette_umap3d": round(sil, 3),
        "note": "silhouette > ~0.5 with roughly balanced clusters = clean kit separation; "
        "low/lopsided = kit clash, bibs, or referee/keeper contamination",
    }, labels


def save_tracklet_embeddings(
    out_dir: Path,
    crop_tids: list[int],
    embeddings: np.ndarray,
    team_labels: np.ndarray | None,
) -> dict[str, Any]:
    """Mean L2-normalized SigLIP embedding + majority team per tracklet → tracklet_embeddings.npz."""
    if embeddings.shape[0] == 0:
        return {"status": "skipped", "reason": "no crops"}
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    unit = embeddings / np.clip(norms, 1e-8, None)
    by_tid: dict[int, list[int]] = {}
    for row, tid in enumerate(crop_tids):
        by_tid.setdefault(tid, []).append(row)
    ids = np.array(sorted(by_tid), dtype=np.int32)
    means = np.zeros((len(ids), unit.shape[1]), dtype=np.float32)
    teams = np.full(len(ids), -1, dtype=np.int8)
    counts = np.zeros(len(ids), dtype=np.int16)
    for k, tid in enumerate(ids):
        rows = by_tid[int(tid)]
        m = unit[rows].mean(axis=0)
        means[k] = m / max(float(np.linalg.norm(m)), 1e-8)
        counts[k] = len(rows)
        if team_labels is not None:
            votes = np.bincount(team_labels[rows], minlength=2)
            teams[k] = int(np.argmax(votes))
    # Per-team mean crop embedding (in raw SigLIP space): lets chunked runs align
    # their independently-fit KMeans labels (cluster 0 in one chunk may be cluster 1
    # in another). Zero rows when a team has no crops.
    team_means = np.zeros((2, unit.shape[1]), dtype=np.float32)
    if team_labels is not None:
        for lab in (0, 1):
            rows = team_labels == lab
            if rows.any():
                m = unit[rows].mean(axis=0)
                team_means[lab] = m / max(float(np.linalg.norm(m)), 1e-8)
    np.savez_compressed(
        out_dir / "tracklet_embeddings.npz",
        ids=ids, emb=means, team=teams, n_crops=counts, team_means=team_means,
    )
    return {"status": "ok", "tracklets_with_embeddings": int(len(ids))}


# --------------------------------------------------------------------------- slicer benchmark


def benchmark_slicer(
    model: Any,
    video: Path,
    sample_fps: float,
    seconds: float,
    threshold: float,
    slice_wh: int,
    overlap_wh: int,
) -> dict[str, Any]:
    def callback(tile: np.ndarray) -> sv.Detections:
        return model.predict(tile, threshold=threshold, include_source_image=False)

    slicer = sv.InferenceSlicer(callback=callback, slice_wh=slice_wh, overlap_wh=overlap_wh)
    local = StageTimer()
    n = 0
    detections_total = 0
    print(f"slicer benchmark: ~{seconds:.0f}s of footage, slice_wh={slice_wh}, overlap_wh={overlap_wh}")
    for _, _, rgb in iter_sampled_frames(video, sample_fps, seconds, None):
        with local.time("sliced_detect", units=1):
            det = slicer(rgb)
        detections_total += len(det)
        n += 1
        if n % 25 == 0:
            print(f"  slicer: {n} frames, {local.fps('sliced_detect'):.2f} fps")
    if n == 0:
        return {"status": "skipped", "reason": "no frames decoded for benchmark"}
    return {
        "status": "ok",
        "frames": n,
        "seconds": round(local.seconds["sliced_detect"], 2),
        "fps": round(local.fps("sliced_detect"), 3),
        "mean_detections_per_frame": round(detections_total / n, 1),
        "slice_wh": slice_wh,
        "overlap_wh": overlap_wh,
    }


# --------------------------------------------------------------------------- extrapolation


def extrapolate(
    timer: StageTimer,
    frames_processed: int,
    sample_fps: float,
    crops_collected: int,
    crop_cap: int,
    sliced_fps: float | None,
    detect_mode: str,
) -> dict[str, Any]:
    full_frames = MATCH_SECONDS * sample_fps
    scale = full_frames / max(frames_processed, 1)

    def linear(stage: str) -> float:
        return timer.seconds.get(stage, 0.0) * scale

    embed_s = timer.seconds.get("cluster_embed", 0.0)
    embed_full = embed_s * (crop_cap / max(crops_collected, 1)) if crops_collected else 0.0
    fixed = (
        timer.seconds.get("model_load", 0.0)
        + timer.seconds.get("cluster_model_load", 0.0)
        + embed_full
        + timer.seconds.get("cluster_fit", 0.0)
        + timer.seconds.get("render", 0.0)
    )

    def total(detect_seconds: float) -> dict[str, Any]:
        s = linear("decode") + detect_seconds + linear("track") + fixed
        hours = s / 3600.0
        return {
            "total_seconds": round(s, 1),
            "gpu_hours": round(hours, 3),
            "cost_usd_aca_t4": round(hours * RATE_T4_ACA, 2),
            "cost_usd_aml_spot": round(hours * RATE_T4_SPOT, 2),
            "passes_3p5h_gate": hours <= GATE_HOURS,
        }

    out: dict[str, Any] = {
        "assumes_frames": int(full_frames),
        "frames_measured": frames_processed,
        "fixed_overhead_seconds": round(fixed, 1),
        "detect_mode_in_main_pass": detect_mode,
    }
    detect_fps = timer.fps("detect")
    if detect_fps > 0:
        # The main pass detects full-frame unless --slicer on; with --slicer both,
        # the sliced numbers come from the separate benchmark segment below.
        label = "sliced" if detect_mode == "on" else "fullframe"
        out[label] = total(full_frames / detect_fps)
        out[label]["detect_fps"] = round(detect_fps, 2)
    if sliced_fps and sliced_fps > 0 and detect_mode != "on":
        out["sliced"] = total(full_frames / sliced_fps)
        out["sliced"]["detect_fps"] = round(sliced_fps, 2)
        if detect_fps > 0:
            out["slicer_cost_multiplier"] = round(detect_fps / sliced_fps, 2)
    return out


# --------------------------------------------------------------------------- report


def write_report(out_dir: Path, results: dict[str, Any]) -> Path:
    ex = results["extrapolation_90min"]
    lines = [
        f"# Spike timing report — {Path(results['video']['path']).name}",
        "",
        f"Generated {results['generated_at']} · device `{results['config']['device']}` · "
        f"detector `{results['config']['detector']}` · tracker `{results['tracker_backend']}`",
        "",
        "## Per-stage wall-clock (measured)",
        "",
        "| stage | seconds | units | units/sec |",
        "|---|---:|---:|---:|",
    ]
    for stage, row in results["stages"].items():
        lines.append(f"| {stage} | {row['seconds']:.1f} | {row['units']} | {row['units_per_sec']:.2f} |")
    lines += [
        "",
        f"Frames processed: {results['frames_processed']} "
        f"({results['processed_seconds']:.0f}s of footage at {results['config']['sample_fps']} fps analysis rate)",
        "",
        "## Extrapolation to a 90-minute match",
        "",
        f"Assumes {ex['assumes_frames']} analysed frames; decode/detect/track scale linearly, "
        f"cluster scaled to a {results['config']['crop_cap']}-crop cap, model load + render counted as fixed "
        f"({ex['fixed_overhead_seconds']}s).",
        "",
        "| variant | detect fps | GPU-hours | $ @ ACA T4 $0.84/hr | $ @ Spot $0.32/hr | ≤3.5h gate |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for variant in ("fullframe", "sliced"):
        if variant in ex:
            v = ex[variant]
            verdict = "PASS" if v["passes_3p5h_gate"] else "FAIL"
            lines.append(
                f"| {variant} | {v.get('detect_fps', 0):.2f} | {v['gpu_hours']:.2f} | "
                f"${v['cost_usd_aca_t4']:.2f} | ${v['cost_usd_aml_spot']:.2f} | **{verdict}** |"
            )
    if "slicer_cost_multiplier" in ex:
        lines.append("")
        lines.append(f"Measured slicer detection-cost multiplier: **{ex['slicer_cost_multiplier']}×**")
    lines += [
        "",
        "## Tracklets (ID-switch proxy)",
        "",
        "```json",
        json.dumps(results["tracklets"], indent=2),
        "```",
        "",
        "## Team clustering",
        "",
        "```json",
        json.dumps(results["team_cluster"], indent=2),
        "```",
        "",
        "Caveats: smoke/MPS runs measure nothing about GPU cost — only CUDA runs count for the gate. "
        "Broadcast footage answers throughput only; degradation needs amateur footage "
        "(see report_template.md).",
        "",
    ]
    path = out_dir / "report.md"
    path.write_text("\n".join(lines))
    return path


# --------------------------------------------------------------------------- main


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--video", required=True, type=Path)
    p.add_argument("--device", default="auto", choices=["auto", "cuda", "mps", "cpu"])
    p.add_argument("--sample-fps", type=float, default=12.5)
    p.add_argument("--start-seconds", type=float, default=0.0, help="start processing at this timestamp (chunked runs)")
    p.add_argument("--max-seconds", type=float, default=None, help="ABSOLUTE end timestamp to stop at")
    # operator timeline markers (prod worker path): when --kickoff-s is set the run is bounded to
    # [kickoff, end] and the halftime gap [halftime, second-half] is SKIPPED in-pass (warm-up,
    # halftime and post-match are never analysed). Overrides --start-seconds/--max-seconds.
    p.add_argument("--kickoff-s", type=float, default=None, help="1st-half kickoff (s); enables in-play marker mode")
    p.add_argument("--halftime-s", type=float, default=None, help="end of 1st half (s)")
    p.add_argument("--second-half-kickoff-s", type=float, default=None, help="2nd-half kickoff (s); skips the halftime gap")
    p.add_argument("--end-s", type=float, default=None, help="full-time (s); default = end of video")
    p.add_argument("--tid-offset", type=int, default=0, help="offset added to tracker ids (chunk namespacing)")
    p.add_argument("--smoke", action="store_true", help="60s sanity run (local/MPS); not a cost measurement")
    p.add_argument("--slicer", default="both", choices=["on", "off", "both"],
                   help="'both' = full-frame main pass + timed slicer benchmark segment (default)")
    p.add_argument("--slice-wh", type=int, default=640)
    p.add_argument("--slice-overlap", type=int, default=100)
    p.add_argument("--slicer-seconds", type=float, default=20.0, help="footage seconds for the slicer benchmark")
    p.add_argument("--model", default="medium", choices=["nano", "small", "medium", "large"])
    p.add_argument("--resolution", type=int, default=None, help="override detector input resolution")
    p.add_argument("--batch", type=int, default=8, help="detection batch size")
    p.add_argument("--threshold", type=float, default=0.5)
    p.add_argument("--crop-cap", type=int, default=12000, help="max tracklet-attributed crops (clustering + merge)")
    p.add_argument("--render-seconds", type=float, default=30.0)
    p.add_argument("--render-start", type=float, default=None,
                   help="sample-clip start (seconds into footage); default ~40%% in, past warmup")
    p.add_argument("--optimize", action="store_true",
                   help="call model.optimize_for_inference() (torch.jit.trace; incompatible with --slicer)")
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args()
    if args.smoke:
        args.max_seconds = args.max_seconds or 60.0
        args.slicer_seconds = min(args.slicer_seconds, 10.0)
        args.crop_cap = min(args.crop_cap, 300)
        args.render_seconds = min(args.render_seconds, 10.0)
        args.batch = min(args.batch, 4)
    return args


def main() -> None:
    args = parse_args()
    if not args.video.exists():
        _fail(f"video not found: {args.video}", "run download_footage.py first")

    device = pick_device(args.device)
    meta = probe_video(args.video)

    # Marker mode: translate operator timeline markers into an in-play window + halftime gap.
    # Overrides --start-seconds/--max-seconds; when off (no --kickoff-s) behaviour is unchanged.
    marker_gap = None
    mk_start, mk_end, mk_gap = in_play_plan(
        args.kickoff_s, args.halftime_s, args.second_half_kickoff_s, args.end_s
    )
    if mk_start is not None:
        args.start_seconds = mk_start
        args.max_seconds = mk_end if mk_end is not None else meta.duration_s
        marker_gap = mk_gap
        gap_note = f" | skip halftime {mk_gap[0]:.0f}-{mk_gap[1]:.0f}s" if mk_gap else ""
        print(f"marker  : in-play [{args.start_seconds:.0f}, {args.max_seconds:.0f}]s{gap_note}")

    end_s = min(meta.duration_s, args.max_seconds) if args.max_seconds else meta.duration_s
    planned_s = max(0.0, end_s - args.start_seconds)
    if marker_gap:  # the skipped halftime gap isn't decoded — don't count it in the ETA/plan
        planned_s = max(0.0, planned_s - (marker_gap[1] - marker_gap[0]))
    planned_frames = max(1, int(planned_s * args.sample_fps))
    out_dir = args.out or (
        Path(__file__).resolve().parent / "results" / f"{args.video.stem}-{datetime.now():%Y%m%d-%H%M%S}"
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"video   : {meta.path} ({meta.width}x{meta.height} @ {meta.native_fps:.2f} fps, {meta.duration_s:.0f}s)")
    print(f"plan    : {planned_s:.0f}s -> ~{planned_frames} frames at {args.sample_fps} fps | device={device} "
          f"| detector=rfdetr-{args.model} | slicer={args.slicer} | batch={args.batch}")
    if device != "cuda":
        print("NOTE    : non-CUDA run — timings are sanity-only, NOT valid for the cost gate.")

    timer = StageTimer()
    with timer.time("model_load"):
        model = load_detector(args.model, device, args.resolution)
    if args.optimize:
        if args.slicer != "off":
            print("WARNING: --optimize traces a fixed batch; slicer single-tile calls may fail. Prefer --slicer off.")
        try:
            with timer.time("model_load"):
                model.optimize_for_inference(compile=True, batch_size=args.batch)
            print("optimize_for_inference: ok")
        except Exception as exc:
            print(f"WARNING: optimize_for_inference failed ({exc}); continuing unoptimized")

    update_tracker, tracker_backend = make_tracker(args.sample_fps)
    print(f"tracker : {tracker_backend}")

    slicer_for_main: sv.InferenceSlicer | None = None
    if args.slicer == "on":
        slicer_for_main = sv.InferenceSlicer(
            callback=lambda tile: model.predict(tile, threshold=args.threshold, include_source_image=False),
            slice_wh=args.slice_wh,
            overlap_wh=args.slice_overlap,
        )

    if args.render_start is not None:
        render_start = args.render_start  # absolute timestamp
    elif planned_s > 600:
        render_start = args.start_seconds + 0.4 * planned_s  # deep into the run: actual play, not warmup
    else:
        render_start = args.start_seconds + (30.0 if planned_s >= args.render_seconds + 30.0 else 0.0)
    if marker_gap is not None and args.render_start is None and render_start > marker_gap[0]:
        # planned_s is gap-compressed; map the compressed offset back onto the REAL timeline so the
        # sample clip lands on decoded in-play frames rather than inside the skipped halftime gap.
        render_start += marker_gap[1] - marker_gap[0]
    renderer = ClipRenderer(out_dir / "sample_clip.mp4", args.sample_fps, render_start, args.render_seconds)
    registry = TrackletRegistry()
    track_store = TrackStore()
    crop_records: list[tuple[int, np.ndarray]] = []
    tid_crop_counts: dict[int, int] = {}
    off_pitch_dropped = 0

    frames_done = 0
    last_t = 0.0
    wall_start = time.perf_counter()
    batch_buf: list[tuple[int, float, np.ndarray]] = []
    seg_offset = [args.tid_offset]  # bumped at the halftime boundary so 2nd-half ids don't collide

    def process_batch(buf: list[tuple[int, float, np.ndarray]]) -> None:
        nonlocal frames_done, last_t, off_pitch_dropped
        frames = [rgb for _, _, rgb in buf]
        if slicer_for_main is not None:
            dets = []
            for f in frames:
                with timer.time("detect", units=1):
                    dets.append(slicer_for_main(f))
        else:
            with timer.time("detect", units=len(frames)):
                dets = detect_batch(model, frames, args.threshold)
        for (idx, t, rgb), det in zip(buf, dets):
            people = only_people(det)
            with timer.time("pitchmask", units=1):
                people, n_dropped = filter_on_pitch(rgb, people)
            off_pitch_dropped += n_dropped
            with timer.time("track", units=1):
                tracked = update_tracker(people, rgb)
            if tracked.tracker_id is not None and len(tracked) > 0:
                tracked = tracked[tracked.tracker_id >= 0]
                if seg_offset[0]:
                    tracked.tracker_id = tracked.tracker_id + seg_offset[0]
            registry.observe(tracked, t)
            track_store.add(idx, t, tracked)
            sample_tracked_crops(rgb, tracked, idx, crop_records, tid_crop_counts, args.crop_cap)
            if renderer.wants(t):
                with timer.time("render", units=1):
                    renderer.add(rgb, tracked)
            frames_done += 1
            last_t = t
            if frames_done % 200 == 0:
                elapsed = time.perf_counter() - wall_start
                frac = frames_done / planned_frames
                eta = elapsed / frac - elapsed if frac > 0 else 0.0
                print(
                    f"  {frames_done}/{planned_frames} frames ({frac * 100:.1f}%) | "
                    f"detect {timer.fps('detect'):.2f} fps | track {timer.fps('track'):.2f} fps | "
                    f"eta {eta / 60:.1f} min"
                )
            if frames_done % 5000 == 0:  # crash/OOM insurance: cheap checkpoint of timings so far
                (out_dir / "results-partial.json").write_text(
                    json.dumps({"frames_done": frames_done, "stages": timer.as_dict()}, indent=2)
                )

    print("main pass: decode -> detect -> track ...")
    main_pass_error: str | None = None
    reset_pending = marker_gap is not None  # reset the tracker when we first cross into the 2nd half
    try:
        for item in iter_sampled_frames(args.video, args.sample_fps, args.max_seconds, timer, args.start_seconds):
            if marker_gap is not None:
                t = item[1]
                if marker_gap[0] <= t < marker_gap[1]:
                    continue  # skip the halftime gap: no detect/track/cluster work on dead time
                if reset_pending and t >= marker_gap[1]:
                    if batch_buf:
                        process_batch(batch_buf)  # flush the 1st-half remainder first
                        batch_buf = []
                    update_tracker = make_tracker(args.sample_fps)[0]  # fresh tracks for the 2nd half
                    seg_offset[0] += SECOND_HALF_TID_OFFSET            # ...in a separate id space
                    reset_pending = False
            batch_buf.append(item)
            if len(batch_buf) >= args.batch:
                process_batch(batch_buf)
                batch_buf = []
        if batch_buf:
            process_batch(batch_buf)
    except Exception:
        import traceback

        main_pass_error = traceback.format_exc()
        print(f"ERROR: main pass aborted at frame {frames_done} — continuing with partial data\n{main_pass_error}")
    finally:
        renderer.close()
    processed_seconds = last_t if frames_done else 0.0
    if frames_done and marker_gap is not None:
        # the halftime gap sits inside last_t but was never processed — don't count it as footage,
        # or the tracklets-per-minute quality proxy is biased low by the gap fraction.
        processed_seconds = max(0.0, processed_seconds - (marker_gap[1] - marker_gap[0]))
    print(f"main pass done: {frames_done} frames, {processed_seconds:.0f}s of footage, "
          f"{len(crop_records)} tracklet-attributed crops, {off_pitch_dropped} off-pitch detections dropped, "
          f"clip frames={renderer.frames_written}")
    n_track_rows = track_store.save(out_dir / "tracks.npz")
    print(f"tracks.npz: {n_track_rows} rows")

    print("team clustering (SigLIP -> UMAP -> KMeans) ...")
    crop_tids = [tid for tid, _ in crop_records]
    crops = [c for _, c in crop_records]
    embeddings = embed_crops(crops, device, 64, timer) if crops else np.zeros((0, 768), dtype=np.float32)
    team_cluster, crop_team_labels = cluster_teams(embeddings, timer)
    embed_summary = save_tracklet_embeddings(out_dir, crop_tids, embeddings, crop_team_labels)
    print(f"tracklet embeddings: {embed_summary}")

    slicer_benchmark: dict[str, Any] = {"status": "skipped", "reason": f"--slicer {args.slicer}"}
    if args.slicer == "both":
        slicer_benchmark = benchmark_slicer(
            model, args.video, args.sample_fps, args.slicer_seconds,
            args.threshold, args.slice_wh, args.slice_overlap,
        )

    sliced_fps = slicer_benchmark.get("fps") if slicer_benchmark.get("status") == "ok" else None
    results: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "config": {
            "device": device,
            "detector": f"rfdetr-{args.model}" + (f"@{args.resolution}" if args.resolution else ""),
            "sample_fps": args.sample_fps,
            "batch": args.batch,
            "threshold": args.threshold,
            "slicer_mode": args.slicer,
            "crop_cap": args.crop_cap,
            "smoke": args.smoke,
            "start_seconds": args.start_seconds,
            "max_seconds": args.max_seconds,
            "tid_offset": args.tid_offset,
            "markers": {
                "kickoff_s": args.kickoff_s,
                "halftime_s": args.halftime_s,
                "second_half_kickoff_s": args.second_half_kickoff_s,
                "end_s": args.end_s,
                "skipped_gap_s": marker_gap,
            },
        },
        "video": vars(meta),
        "tracker_backend": tracker_backend,
        "main_pass_error": main_pass_error,
        "frames_processed": frames_done,
        "processed_seconds": round(processed_seconds, 1),
        "stages": timer.as_dict(),
        "tracklets": registry.stats(processed_seconds, args.sample_fps),
        "team_cluster": team_cluster,
        "tracklet_embeddings": embed_summary,
        "off_pitch_dropped": off_pitch_dropped,
        "render_start_s": render_start,
        "slicer_benchmark": slicer_benchmark,
        "extrapolation_90min": extrapolate(
            timer, frames_done, args.sample_fps, len(crops), args.crop_cap, sliced_fps, args.slicer
        ),
    }

    json_path = out_dir / "results.json"
    json_path.write_text(json.dumps(results, indent=2))
    report_path = write_report(out_dir, results)
    print(f"\nwrote {json_path}\nwrote {report_path}\nwrote {renderer.out_path}")
    ex = results["extrapolation_90min"]
    for variant in ("fullframe", "sliced"):
        if variant in ex:
            v = ex[variant]
            print(f"{variant:9s}: {v['gpu_hours']:.2f} GPU-h -> ${v['cost_usd_aca_t4']:.2f} (ACA T4) | "
                  f"gate {'PASS' if v['passes_3p5h_gate'] else 'FAIL'}")


if __name__ == "__main__":
    main()
