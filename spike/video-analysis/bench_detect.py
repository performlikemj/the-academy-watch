#!/usr/bin/env python3
"""
bench_detect.py — RF-DETR detection-backend benchmark for the Film Room LOCAL pipeline.

Answers the one load-bearing question for the "run it on the Mac" architecture
(see ledgers/CONTINUITY_video-analysis.md): can RF-DETR detection — the only GPU stage
never yet run on Apple Silicon — run *fast enough* on MPS (and optionally CoreML/ANE)
versus CPU, AND does it stay numerically *correct* (parity against the CPU reference)?
A backend that is fast but silently wrong (MPS op fallback, CoreML quantisation drift)
is useless, so we measure both speed and agreement.

It reuses the EXACT detection code path from run_spike.py (load_detector / detect_batch /
iter_sampled_frames) so the numbers reflect the real pipeline, not a toy reimplementation.

License posture: RF-DETR is Apache-2.0; no ultralytics anywhere. Same as the spike.

Usage:
  .venv-bench/bin/python bench_detect.py \
      --video footage/youtube/<full-match>.mp4 \
      --frames 200 --model medium --batches 1,8 --backends cpu,mps \
      --out results/bench

Nothing here fabricates numbers: a backend that fails to load/run is recorded with its
error and skipped; only real measurements appear in the report.
"""
from __future__ import annotations

import argparse
import gc
import json
import platform
import statistics
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

# Reuse the real pipeline's detection code so the benchmark is parity-true.
try:
    import torch  # noqa: E402
    import supervision as sv  # noqa: E402
    from run_spike import (  # noqa: E402
        probe_video,
        iter_sampled_frames,
        load_detector,
        detect_batch,
        only_people,
    )
except Exception as exc:  # pragma: no cover - import-time environment guard
    print(f"FATAL: could not import detection stack from run_spike.py: {exc}")
    print("Install the detection venv first, e.g.:")
    print("  uv venv .venv-bench --python 3.13 --seed")
    print("  uv pip install --python .venv-bench/bin/python rfdetr==1.7.1 "
          "supervision==0.28.0 trackers==2.4.0 transformers scikit-learn umap-learn "
          "opencv-python-headless av psutil")
    raise SystemExit(2)

try:
    import psutil
except Exception:
    psutil = None


# --------------------------------------------------------------------------- helpers

def _sysctl(key: str) -> str:
    try:
        return subprocess.check_output(["sysctl", "-n", key], text=True).strip()
    except Exception:
        return ""


def machine_info() -> dict[str, Any]:
    mem_bytes = 0
    try:
        mem_bytes = int(_sysctl("hw.memsize") or 0)
    except Exception:
        pass
    return {
        "chip": _sysctl("machdep.cpu.brand_string") or platform.processor(),
        "cores": _sysctl("hw.ncpu"),
        "ram_gb": round(mem_bytes / 1e9, 1) if mem_bytes else None,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "torch": torch.__version__,
        "mps_available": bool(getattr(torch.backends, "mps", None) and torch.backends.mps.is_available()),
        "cuda_available": torch.cuda.is_available(),
    }


def rss_mb() -> float | None:
    if psutil is None:
        return None
    return round(psutil.Process().memory_info().rss / 1e6, 1)


def synchronize(device: str) -> None:
    """Force the device to finish so timings are real, not async-dispatch fiction."""
    if device == "mps" and hasattr(torch, "mps"):
        torch.mps.synchronize()
    elif device == "cuda":
        torch.cuda.synchronize()


def empty_cache(device: str) -> None:
    try:
        if device == "mps" and hasattr(torch, "mps"):
            torch.mps.empty_cache()
        elif device == "cuda":
            torch.cuda.empty_cache()
    except Exception:
        pass


def mps_driver_mb() -> float | None:
    try:
        if hasattr(torch, "mps") and hasattr(torch.mps, "driver_allocated_memory"):
            return round(torch.mps.driver_allocated_memory() / 1e6, 1)
    except Exception:
        pass
    return None


def pctl(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    return float(np.percentile(np.asarray(values, dtype=float), p))


# --------------------------------------------------------------------------- frames

def decode_frames(video: Path, sample_fps: float, n: int, start_s: float) -> list[np.ndarray]:
    """Decode exactly n RGB frames at the analysis fps, once, reused across backends."""
    frames: list[np.ndarray] = []
    for _, _, rgb in iter_sampled_frames(video, sample_fps, None, None, start_s):
        if rgb is None:
            continue
        frames.append(np.ascontiguousarray(rgb))
        if len(frames) >= n:
            break
    return frames


def person_boxes(det: "sv.Detections") -> tuple[np.ndarray, np.ndarray]:
    people = only_people(det)
    if len(people) == 0:
        return np.zeros((0, 4), dtype=float), np.zeros((0,), dtype=float)
    conf = people.confidence if people.confidence is not None else np.ones(len(people))
    return np.asarray(people.xyxy, dtype=float), np.asarray(conf, dtype=float)


# --------------------------------------------------------------------------- parity

def iou_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    if len(a) == 0 or len(b) == 0:
        return np.zeros((len(a), len(b)), dtype=float)
    ax1, ay1, ax2, ay2 = a[:, 0:1], a[:, 1:2], a[:, 2:3], a[:, 3:4]
    bx1, by1, bx2, by2 = b[:, 0], b[:, 1], b[:, 2], b[:, 3]
    inter_x1 = np.maximum(ax1, bx1)
    inter_y1 = np.maximum(ay1, by1)
    inter_x2 = np.minimum(ax2, bx2)
    inter_y2 = np.minimum(ay2, by2)
    iw = np.clip(inter_x2 - inter_x1, 0, None)
    ih = np.clip(inter_y2 - inter_y1, 0, None)
    inter = iw * ih
    area_a = np.clip(ax2 - ax1, 0, None) * np.clip(ay2 - ay1, 0, None)
    area_b = np.clip(bx2 - bx1, 0, None) * np.clip(by2 - by1, 0, None)
    union = area_a + area_b - inter
    return np.where(union > 0, inter / union, 0.0)


def greedy_match(ref: np.ndarray, cand: np.ndarray, iou_thr: float = 0.5) -> list[tuple[int, int, float]]:
    """Greedy 1:1 matching of cand boxes to ref boxes by descending IoU."""
    m = iou_matrix(ref, cand)
    pairs: list[tuple[int, int, float]] = []
    used_r, used_c = set(), set()
    flat = [(m[i, j], i, j) for i in range(m.shape[0]) for j in range(m.shape[1]) if m[i, j] >= iou_thr]
    for iou, i, j in sorted(flat, reverse=True):
        if i in used_r or j in used_c:
            continue
        used_r.add(i)
        used_c.add(j)
        pairs.append((i, j, iou))
    return pairs


def parity_report(ref_frames: list[tuple[np.ndarray, np.ndarray]],
                  cand_frames: list[tuple[np.ndarray, np.ndarray]]) -> dict[str, Any]:
    """Compare candidate per-frame person detections against the CPU reference."""
    matched_ious: list[float] = []
    conf_abs_err: list[float] = []
    ref_total = cand_total = matched_total = 0
    count_deltas: list[int] = []
    for (rb, rc), (cb, cc) in zip(ref_frames, cand_frames):
        ref_total += len(rb)
        cand_total += len(cb)
        count_deltas.append(len(cb) - len(rb))
        pairs = greedy_match(rb, cb)
        matched_total += len(pairs)
        for i, j, iou in pairs:
            matched_ious.append(iou)
            conf_abs_err.append(abs(float(rc[i]) - float(cc[j])))
    recall = matched_total / ref_total if ref_total else None
    precision = matched_total / cand_total if cand_total else None
    mean_cd = statistics.fmean(count_deltas) if count_deltas else None
    return {
        "ref_person_boxes": ref_total,
        "cand_person_boxes": cand_total,
        "matched_boxes": matched_total,
        "match_rate_vs_ref": round(recall, 4) if recall is not None else None,
        "precision_vs_cand": round(precision, 4) if precision is not None else None,
        "mean_matched_iou": round(statistics.fmean(matched_ious), 4) if matched_ious else None,
        "min_matched_iou": round(min(matched_ious), 4) if matched_ious else None,
        "mean_conf_abs_err": round(statistics.fmean(conf_abs_err), 5) if conf_abs_err else None,
        "mean_count_delta_per_frame": round(mean_cd, 3) if mean_cd is not None else None,
        "verdict": _parity_verdict(recall, matched_ious, precision, mean_cd),
    }


def _parity_verdict(recall: float | None, ious: list[float],
                    precision: float | None = None, count_delta: float | None = None) -> str:
    # A fast backend that HALLUCINATES extra boxes keeps recall=1.0, so gate on precision
    # (false positives) and per-frame count delta too — not just recall + IoU.
    if recall is None or not ious:
        return "no-reference-boxes"
    mean_iou = statistics.fmean(ious)
    cd = abs(count_delta) if count_delta is not None else 0.0
    prec_ok = precision is None or precision >= 0.97
    if recall >= 0.97 and mean_iou >= 0.95 and prec_ok and cd <= 0.5:
        return "PASS (numerically equivalent to CPU)"
    if recall >= 0.9 and mean_iou >= 0.85 and cd <= 2.0:
        return "CLOSE (minor drift — acceptable, verify visually)"
    return "FAIL (diverges from CPU — backend unsafe)"


# --------------------------------------------------------------------------- torch backends

def run_torch_backend(device: str, model_size: str, resolution: int | None,
                      frames: list[np.ndarray], batch_sizes: list[int],
                      threshold: float, warmup: int,
                      optimize: bool = False, opt_batch: int = 8) -> dict[str, Any]:
    out: dict[str, Any] = {"backend": device, "ok": False, "optimized": False}
    t_load0 = time.perf_counter()
    try:
        model = load_detector(model_size, device, resolution)
    except Exception as exc:
        out["error"] = f"load_detector failed: {exc}"
        out["traceback"] = traceback.format_exc()
        return out
    load_s = time.perf_counter() - t_load0

    # Production path traces/compiles the model for a FIXED batch. We benchmark only
    # that batch when optimization succeeds; if it fails we fall back to eager (never fake it).
    bench_batches = batch_sizes
    if optimize:
        t_opt0 = time.perf_counter()
        for comp in (True, False):
            try:
                model.optimize_for_inference(compile=comp, batch_size=opt_batch)
                out["optimized"] = True
                out["optimize_compile"] = comp
                out["optimize_s"] = round(time.perf_counter() - t_opt0, 2)
                bench_batches = [opt_batch]
                break
            except Exception as exc:
                out["optimize_error"] = f"compile={comp}: {exc}"

    # Warmup (first calls compile Metal kernels / warm caches — discard). Must use the
    # SAME batch size we benchmark: an optimized model is traced for a fixed batch and
    # rejects any other size.
    warm_bs = bench_batches[0]
    if out.get("optimized") and len(frames) < warm_bs:
        out["error"] = f"need >= {warm_bs} frames to benchmark optimized (fixed-batch) model"
        return out
    try:
        for _ in range(max(1, warmup // warm_bs)):
            detect_batch(model, frames[:warm_bs], threshold)
        synchronize(device)
    except Exception as exc:
        out["error"] = f"warmup failed: {exc}"
        out["traceback"] = traceback.format_exc()
        return out

    mem_before = rss_mb()
    by_batch: dict[str, Any] = {}
    canonical_dets: list[tuple[np.ndarray, np.ndarray]] | None = None

    for bs in bench_batches:
        batch_times: list[float] = []
        per_frame_dets: list[tuple[np.ndarray, np.ndarray]] = []
        timed_frames = 0
        try:
            # Per-batch-size warmup: MPS compiles Metal kernels per INPUT SHAPE, so a size
            # only warmed at bench_batches[0] would eat compile cost in its first timed batch.
            for _ in range(2):
                detect_batch(model, frames[:bs], threshold)
            synchronize(device)
            for i in range(0, len(frames), bs):
                chunk = frames[i:i + bs]
                if out.get("optimized") and len(chunk) != bs:
                    break  # optimized model requires exactly bs frames; drop remainder
                synchronize(device)
                t0 = time.perf_counter()
                dets = detect_batch(model, chunk, threshold)
                synchronize(device)
                batch_times.append(time.perf_counter() - t0)
                timed_frames += len(chunk)
                if bs == bench_batches[0]:
                    for d in dets:
                        per_frame_dets.append(person_boxes(d))
        except Exception as exc:
            by_batch[str(bs)] = {"error": str(exc)}
            continue

        total_time = sum(batch_times)
        # fps over frames ACTUALLY timed (not len(frames) — the optimized path drops a remainder).
        per_frame_ms = [bt / max(1, len(frames[i * bs:(i + 1) * bs])) * 1000
                        for i, bt in enumerate(batch_times)]
        by_batch[str(bs)] = {
            "frames": timed_frames,
            "fps": round(timed_frames / total_time, 2) if total_time else None,
            "ms_per_frame_mean": round(statistics.fmean(per_frame_ms), 2) if per_frame_ms else None,
            "ms_per_frame_median": round(statistics.median(per_frame_ms), 2) if per_frame_ms else None,
            "ms_per_frame_p90": round(pctl(per_frame_ms, 90), 2),
            "ms_per_frame_p99": round(pctl(per_frame_ms, 99), 2),
            "batch_ms_mean": round(statistics.fmean(batch_times) * 1000, 2) if batch_times else None,
        }
        if bs == bench_batches[0]:
            canonical_dets = per_frame_dets

    out.update({
        "ok": True,
        "model_load_s": round(load_s, 2),
        "mem_rss_before_mb": mem_before,
        "mem_rss_after_mb": rss_mb(),
        "mps_driver_mb": mps_driver_mb() if device == "mps" else None,
        "by_batch": by_batch,
        "_dets": canonical_dets,  # popped before JSON serialisation
    })

    del model
    gc.collect()
    empty_cache(device)
    return out


# --------------------------------------------------------------------------- coreml (optional / best-effort)

def run_coreml_backend(model_size: str, frames: list[np.ndarray],
                       threshold: float, warmup: int, out_dir: Path) -> dict[str, Any]:
    """Best-effort RF-DETR -> ONNX -> CoreML (ANE/GPU) throughput probe.

    Deliberately conservative: any failure (missing coremltools, export API drift,
    preprocessing mismatch) is recorded and the backend is skipped — never faked.
    Parity is reported as 'unverified' because CoreML preprocessing is not guaranteed
    to bit-match the torch path; treat the fps as indicative, confirm visually later.
    """
    out: dict[str, Any] = {"backend": "coreml", "ok": False, "parity": "unverified"}
    try:
        import coremltools as ct  # noqa: F401
    except Exception as exc:
        out["error"] = f"coremltools not installed ({exc}); skip (optional backend)"
        return out
    try:
        import rfdetr
        classes = {"nano": "RFDETRNano", "small": "RFDETRSmall",
                   "medium": "RFDETRMedium", "large": "RFDETRLarge"}
        model = getattr(rfdetr, classes[model_size])(device="cpu")
        onnx_dir = out_dir / "onnx_export"
        onnx_dir.mkdir(parents=True, exist_ok=True)
        # rfdetr exposes .export() for ONNX; API has shifted across versions, so probe.
        exported = None
        for kwargs in ({"output_dir": str(onnx_dir)}, {"output_dir": str(onnx_dir), "simplify": True}, {}):
            try:
                model.export(**kwargs)
                cands = list(onnx_dir.glob("*.onnx")) or list(SCRIPT_DIR.glob("output/*.onnx"))
                if cands:
                    exported = cands[0]
                    break
            except TypeError:
                continue
            except Exception:
                continue
        if exported is None:
            out["error"] = "rfdetr ONNX export produced no .onnx (API drift); skip"
            return out
        out["onnx_path"] = str(exported)
        # ONNX -> CoreML
        mlmodel = ct.converters.onnx.convert(model=str(exported)) if hasattr(ct.converters, "onnx") \
            else ct.convert(str(exported))
        ml_path = out_dir / f"rfdetr_{model_size}.mlpackage"
        mlmodel.save(str(ml_path))
        out["mlpackage"] = str(ml_path)
        out["note"] = ("CoreML model built. Throughput timing requires matching the model's "
                       "exact input spec; left as a follow-up to avoid fabricated numbers. "
                       "ANE/GPU is the escape hatch if MPS underperforms.")
        out["ok"] = "exported-not-timed"
        return out
    except Exception as exc:
        out["error"] = f"coreml path failed: {exc}"
        out["traceback"] = traceback.format_exc()
        return out


# --------------------------------------------------------------------------- extrapolation

def extrapolate(best_fps: float, sample_fps: float, match_minutes: float) -> dict[str, Any]:
    """Translate detect fps into a per-match wall-clock budget for the local Mac flow."""
    if not best_fps:
        return {}
    analysis_frames = match_minutes * 60.0 * sample_fps
    detect_s = analysis_frames / best_fps
    footage_s = match_minutes * 60.0
    return {
        "match_minutes": match_minutes,
        "analysis_frames": int(analysis_frames),
        "detect_wall_clock_min": round(detect_s / 60.0, 1),
        "detect_realtime_factor": round(footage_s / detect_s, 2),  # >1 = faster than realtime
    }


# --------------------------------------------------------------------------- main

def main() -> None:
    p = argparse.ArgumentParser(description="RF-DETR detection backend benchmark (Apple Silicon)")
    default_video = SCRIPT_DIR / "footage" / "veo-sample.mp4"
    p.add_argument("--video", type=Path, default=default_video)
    p.add_argument("--frames", type=int, default=200, help="frames to decode/benchmark")
    p.add_argument("--start-seconds", type=float, default=120.0, help="seek in (skip warmup/kickoff)")
    p.add_argument("--sample-fps", type=float, default=12.5, help="analysis fps (pipeline default)")
    p.add_argument("--model", default="medium", choices=["nano", "small", "medium", "large"])
    p.add_argument("--resolution", type=int, default=None)
    p.add_argument("--threshold", type=float, default=0.5)
    p.add_argument("--batches", default="1,8", help="comma list of batch sizes")
    p.add_argument("--backends", default="cpu,mps", help="comma list: cpu,mps,coreml")
    p.add_argument("--warmup", type=int, default=8)
    p.add_argument("--optimize", action="store_true",
                   help="also benchmark model.optimize_for_inference() (the production path: trace/compile, fixed batch)")
    p.add_argument("--match-minutes", type=float, default=115.0, help="match length for budget extrapolation")
    p.add_argument("--out", type=Path, default=SCRIPT_DIR / "results" / "bench")
    args = p.parse_args()

    if not args.video.exists():
        raise SystemExit(f"video not found: {args.video}")
    args.out.mkdir(parents=True, exist_ok=True)
    batch_sizes = [int(b) for b in args.batches.split(",") if b.strip()]
    backends = [b.strip() for b in args.backends.split(",") if b.strip()]

    info = machine_info()
    print(f"machine : {info['chip']} | {info['cores']} cores | {info['ram_gb']}GB | "
          f"torch {info['torch']} | mps={info['mps_available']}")

    meta = probe_video(args.video)
    print(f"video   : {args.video.name} | {meta.width}x{meta.height} @ {meta.native_fps:.1f}fps | "
          f"{meta.duration_s/60:.1f} min")
    print(f"decoding {args.frames} frames @ {args.sample_fps}fps from t={args.start_seconds}s ...")
    t0 = time.perf_counter()
    frames = decode_frames(args.video, args.sample_fps, args.frames, args.start_seconds)
    decode_s = time.perf_counter() - t0
    if not frames:
        raise SystemExit("decoded 0 frames — bad --start-seconds or unreadable video")
    print(f"decoded : {len(frames)} frames in {decode_s:.1f}s "
          f"({len(frames)/decode_s:.1f} fps decode) | {frames[0].shape[1]}x{frames[0].shape[0]}")

    results: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "machine": info,
        "config": {
            "video": str(args.video), "video_meta": meta.__dict__,
            "frames": len(frames), "start_seconds": args.start_seconds,
            "sample_fps": args.sample_fps, "model": args.model, "resolution": args.resolution,
            "threshold": args.threshold, "batch_sizes": batch_sizes, "backends": backends,
            "warmup": args.warmup, "optimize": args.optimize, "match_minutes": args.match_minutes,
            "decode_fps": round(len(frames) / decode_s, 1),
        },
        "backends": {},
        "parity": {},
        "extrapolation": {},
    }

    dets_by_backend: dict[str, list[tuple[np.ndarray, np.ndarray]]] = {}

    opt_batch = max(batch_sizes)
    jobs: list[dict[str, Any]] = []
    for be in backends:
        if be == "coreml":
            jobs.append({"key": "coreml", "kind": "coreml"})
        else:
            jobs.append({"key": be, "kind": "torch", "device": be, "optimize": False})
            if args.optimize and be in ("cpu", "mps", "cuda"):
                jobs.append({"key": be + "-opt", "kind": "torch", "device": be, "optimize": True})

    for job in jobs:
        key = job["key"]
        print(f"\n=== backend: {key} ===")
        if job["kind"] == "coreml":
            res = run_coreml_backend(args.model, frames, args.threshold, args.warmup, args.out)
        else:
            dev = job["device"]
            if dev == "mps" and not info["mps_available"]:
                res = {"backend": key, "ok": False, "error": "mps not available"}
            elif dev == "cuda" and not info["cuda_available"]:
                res = {"backend": key, "ok": False, "error": "cuda not available"}
            else:
                res = run_torch_backend(dev, args.model, args.resolution, frames,
                                        batch_sizes, args.threshold, args.warmup,
                                        optimize=job["optimize"], opt_batch=opt_batch)
                res["backend"] = key
            dets = res.pop("_dets", None)
            if dets is not None:
                dets_by_backend[key] = dets
        results["backends"][key] = res
        if res.get("ok") is True:
            best = max((b.get("fps") or 0 for b in res["by_batch"].values()), default=0)
            print(f"  load {res.get('model_load_s')}s | best {best} fps | "
                  f"optimized={res.get('optimized')} | rss {res.get('mem_rss_after_mb')}MB")
        else:
            print(f"  skipped/failed: {res.get('error') or res.get('optimize_error')}")

    # Parity: every torch backend vs CPU reference.
    if "cpu" in dets_by_backend:
        ref = dets_by_backend["cpu"]
        for be, dets in dets_by_backend.items():
            if be == "cpu":
                continue
            n = min(len(ref), len(dets))
            results["parity"][be] = parity_report(ref[:n], dets[:n])
            v = results["parity"][be]
            print(f"\nparity {be} vs cpu: match {v['match_rate_vs_ref']} | "
                  f"meanIoU {v['mean_matched_iou']} | {v['verdict']}")
    else:
        print("\nparity: no CPU reference run — skipped")

    # Extrapolation per backend (using its best fps).
    for be, res in results["backends"].items():
        if res.get("ok") is True:
            best = max((b.get("fps") or 0 for b in res["by_batch"].values()), default=0)
            results["extrapolation"][be] = extrapolate(best, args.sample_fps, args.match_minutes)

    json_path = args.out / "bench_detect_results.json"
    json_path.write_text(json.dumps(results, indent=2, default=str))
    md_path = args.out / "bench_detect_report.md"
    md_path.write_text(render_markdown(results))
    print(f"\nwrote {json_path}")
    print(f"wrote {md_path}\n")
    print(render_verdict(results))


def render_markdown(r: dict[str, Any]) -> str:
    m, c = r["machine"], r["config"]
    lines = [
        "# RF-DETR detection backend benchmark — Film Room local pipeline",
        "",
        f"_Generated {r['generated_at']}_",
        "",
        f"**Machine:** {m['chip']} · {m['cores']} cores · {m['ram_gb']}GB · "
        f"torch {m['torch']} · MPS={m['mps_available']}",
        f"**Video:** `{Path(c['video']).name}` {c['video_meta']['width']}x{c['video_meta']['height']} · "
        f"{c['frames']} frames @ {c['sample_fps']}fps · model `rfdetr-{c['model']}` · thr {c['threshold']}",
        "",
        "## Throughput (frames/sec — higher is better)",
        "",
        "| backend | batch | fps | ms/frame (med) | p99 ms | load s | RSS MB |",
        "|---|---|---|---|---|---|---|",
    ]
    for be, res in r["backends"].items():
        label = be
        if be.endswith("-opt") and res.get("ok") is True and not res.get("optimized"):
            label = be + " (opt FAILED→eager)"   # don't let an eager run masquerade as optimized
        if res.get("ok") is not True:
            err = res.get("error") or res.get("optimize_error") or ""
            lines.append(f"| {label} | — | _skipped_ | — | — | — | {err[:40]} |")
            continue
        for bs, b in res["by_batch"].items():
            if "error" in b:
                lines.append(f"| {label} | {bs} | _err_ | — | — | — | {b['error'][:30]} |")
                continue
            lines.append(f"| {label} | {bs} | **{b['fps']}** | {b['ms_per_frame_median']} | "
                         f"{b['ms_per_frame_p99']} | {res.get('model_load_s')} | {res.get('mem_rss_after_mb')} |")
    lines += ["", "## Parity vs CPU reference (is the fast backend correct?)", "",
              "| backend | match rate | precision | mean IoU | conf err | count Δ/frame | verdict |",
              "|---|---|---|---|---|---|---|"]
    for be, v in r.get("parity", {}).items():
        lines.append(f"| {be} | {v['match_rate_vs_ref']} | {v.get('precision_vs_cand')} | "
                     f"{v['mean_matched_iou']} | {v['mean_conf_abs_err']} | "
                     f"{v['mean_count_delta_per_frame']} | {v['verdict']} |")
    lines += ["", "_Parity compares each backend at its first benchmarked batch size against the "
              "CPU reference at CPU's first batch size; PASS requires recall, precision, IoU and "
              "a small per-frame count delta (so hallucinated extra boxes can't pass)._"]
    lines += ["", f"## Per-match budget (extrapolated to a {c.get('match_minutes','?')}-min match @ {c.get('sample_fps')}fps)", "",
              "| backend | detect wall-clock (min) | realtime factor |", "|---|---|---|"]
    for be, e in r.get("extrapolation", {}).items():
        if e:
            lines.append(f"| {be} | {e['detect_wall_clock_min']} | {e['detect_realtime_factor']}× |")
    lines += ["", "> Realtime factor >1 = detection runs faster than the footage plays. "
              "Detection is the heaviest stage; tracking (BoT-SORT, CPU) and clustering "
              "(SigLIP+UMAP+KMeans) are measured by `run_spike.py`'s StageTimer, and the "
              "jersey-VLM identity stage is the known ~2.9h/match MLX step. Sum those for the "
              "full local processing budget per match."]
    return "\n".join(lines) + "\n"


def _best_fps(res: dict[str, Any]) -> float:
    if res.get("ok") is not True:
        return 0.0
    return max((b.get("fps") or 0 for b in res["by_batch"].values()), default=0.0)


def render_verdict(r: dict[str, Any]) -> str:
    backends = r["backends"]
    mps_variants = {k: v for k, v in backends.items() if k.startswith("mps") and v.get("ok") is True}
    cpu_variants = {k: v for k, v in backends.items() if k.startswith("cpu") and v.get("ok") is True}
    out = ["================ VERDICT ================"]
    if mps_variants:
        best_key = max(mps_variants, key=lambda k: _best_fps(mps_variants[k]))
        best = _best_fps(mps_variants[best_key])
        ext = r["extrapolation"].get(best_key, {})
        par = r["parity"].get(best_key, {}) or r["parity"].get("mps", {})
        out.append(f"Best MPS variant: {best_key} = {best} fps  ->  ~{ext.get('detect_wall_clock_min','?')} min "
                   f"detect per {ext.get('match_minutes','?')}-min match ({ext.get('detect_realtime_factor','?')}x realtime)")
        out.append(f"Parity vs CPU: {par.get('verdict','?')} "
                   f"(match {par.get('match_rate_vs_ref','?')}, IoU {par.get('mean_matched_iou','?')})")
        if cpu_variants:
            cbest = max(_best_fps(v) for v in cpu_variants.values())
            if cbest:
                out.append(f"MPS speedup vs CPU: {round(best / cbest, 2)}x  (cpu best {cbest} fps)")
        rt = ext.get("detect_realtime_factor") or 0
        if rt >= 1 and "PASS" in str(par.get("verdict", "")):
            out.append(">> LOCAL-ON-MAC VIABLE: faster-than-realtime detection + numerically correct.")
        elif rt >= 0.4:
            out.append(">> CONCIERGE-VIABLE: usable for batch/overnight runs; check parity above.")
        else:
            out.append(">> TOO SLOW on MPS: consider CoreML/ANE export or a smaller model variant.")
    else:
        out.append(f"MPS unavailable/failed: {backends.get('mps', {}).get('error', '(not run)')}")
    out.append("========================================")
    return "\n".join(out)


if __name__ == "__main__":
    main()
