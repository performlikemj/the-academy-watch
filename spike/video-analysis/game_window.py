#!/usr/bin/env python3
"""
game_window.py — CHEAP, CPU-ONLY game-time detector (runs BEFORE any GPU work).

Goal (MJ): identify when the game actually starts/ends so the expensive GPU+VLM pipeline
only processes IN-PLAY time — skipping warmups, handshakes, halftime and celebrations. That
saves compute AND removes the sideline/warmup non-player detections that the identity
diagnosis found are a major false-positive source. Output is a SUGGESTION the operator
verifies/overrides (the VideoMatch already has kickoff_s/halftime_s/second_half_kickoff_s).

Why this beats the existing post-GPU `detect_activity_windows` (which was fooled by the
warmup crowd, guessing 770s vs the true ~900-1100s on v8): it keys on the SPATIAL SPREAD of
motion, not raw activity. Warmup/halftime motion is CLUSTERED (drills in one area, a huddle);
in-play motion is spread ACROSS THE WHOLE PITCH (two teams of 11). Spread separates them.

CPU only: PyAV decode (reuses run_spike.iter_sampled_frames' efficient seek) + OpenCV frame
differencing on small grayscale frames. No torch, no GPU, no model. Apache/MIT/BSD only.

Usage:
  .venv-merge/bin/python game_window.py --video footage/<match>.mp4 [--probe-fps 2] [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

try:
    import av
    import cv2
except Exception as exc:  # pragma: no cover
    print(f"FATAL: need PyAV + OpenCV: {exc}")
    raise SystemExit(2)


def _iter_frames(path: Path, fps: float):
    """Decode `path`, yielding (t_seconds, rgb) sampled at ~fps. Non-sampled frames are
    decoded but not converted (cheap). CPU only (PyAV/ffmpeg) — no torch/supervision."""
    interval = 1.0 / fps
    next_t = 0.0
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        rate = float(stream.average_rate or 25.0)
        raw = 0
        for frame in container.decode(stream):
            t = frame.time if frame.time is not None else raw / max(1.0, rate)
            raw += 1
            if t + 1e-9 >= next_t:
                yield t, frame.to_ndarray(format="rgb24")
                while next_t <= t:
                    next_t += interval

# tunables
PROBE_W = 192          # downscale width for the motion map (cheap)
GRID = (6, 8)          # rows x cols pitch grid for the spread metric
PIX_DIFF = 18          # per-pixel abs-diff over this = "moved"
CELL_ON = 0.02         # cell counts as active if this fraction of its pixels moved
MERGE_GAP_S = 75.0     # bridge in-play runs separated by gaps shorter than this
MIN_SEGMENT_S = 300.0  # a real half is at least this long (drops blips); lower for clips


def motion_series(video: Path, probe_fps: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per sampled frame: (t, spread, magnitude). spread = fraction of pitch-grid cells with
    motion (high when both teams are spread across the field); magnitude = mean abs-diff."""
    gh, gw = GRID
    prev = None
    ts: list[float] = []
    spread: list[float] = []
    mag: list[float] = []
    for t, rgb in _iter_frames(video, probe_fps):
        g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        h = int(round(g.shape[0] * PROBE_W / g.shape[1]))
        g = cv2.resize(g, (PROBE_W, h), interpolation=cv2.INTER_AREA)
        # crop to a grid-divisible size
        ch, cw = h // gh, PROBE_W // gw
        g = g[: ch * gh, : cw * gw]
        if prev is not None and prev.shape == g.shape:
            moved = (cv2.absdiff(g, prev) > PIX_DIFF)
            cells = moved.reshape(gh, ch, gw, cw).mean(axis=(1, 3))  # per-cell motion fraction
            spread.append(float((cells > CELL_ON).mean()))           # fraction of active cells
            mag.append(float(moved.mean()))
            ts.append(float(t))
        prev = g
    return np.asarray(ts), np.asarray(spread), np.asarray(mag)


def _smooth(x: np.ndarray, win: int) -> np.ndarray:
    if win <= 1 or x.size == 0:
        return x
    k = np.ones(win) / win
    return np.convolve(x, k, mode="same")


def _runs(mask: np.ndarray, ts: np.ndarray) -> list[list[float]]:
    runs: list[list[float]] = []
    i = 0
    n = len(mask)
    while i < n:
        if mask[i]:
            j = i
            while j + 1 < n and mask[j + 1]:
                j += 1
            runs.append([float(ts[i]), float(ts[j])])
            i = j + 1
        else:
            i += 1
    return runs


def _merge(runs: list[list[float]], gap: float) -> list[list[float]]:
    if not runs:
        return []
    out = [runs[0][:]]
    for s, e in runs[1:]:
        if s - out[-1][1] <= gap:
            out[-1][1] = e
        else:
            out.append([s, e])
    return out


def detect(video: Path, probe_fps: float, smooth_s: float, min_segment_s: float) -> dict:
    ts, spread, mag = motion_series(video, probe_fps)
    if ts.size < 5:
        return {"error": "too few frames decoded", "frames": int(ts.size)}
    win = max(1, int(round(smooth_s * probe_fps)))
    sm = _smooth(spread, win)
    lo, hi = float(np.percentile(sm, 20)), float(np.percentile(sm, 90))
    thr = lo + 0.45 * (hi - lo)  # in-play when spread is well above the quiet baseline
    runs = _merge(_runs(sm > thr, ts), MERGE_GAP_S)
    segments = [r for r in runs if (r[1] - r[0]) >= min_segment_s]
    segments.sort(key=lambda r: -(r[1] - r[0]))  # longest first = the halves

    suggest: dict = {"kickoff_s": None, "halftime_s": None,
                     "second_half_kickoff_s": None, "end_s": None}
    confidence = "low"
    if segments:
        halves = sorted(segments[:2], key=lambda r: r[0])  # chronological
        suggest["kickoff_s"] = round(halves[0][0], 1)
        if len(halves) >= 2:
            suggest["halftime_s"] = round(halves[0][1], 1)
            suggest["second_half_kickoff_s"] = round(halves[1][0], 1)
            suggest["end_s"] = round(halves[1][1], 1)
            gap = halves[1][0] - halves[0][1]
            # only trust it if both halves are plausibly half-length AND the halftime gap is real;
            # warmup shooting-drills span the pitch and routinely fool this — verify always.
            plausible = (halves[0][1] - halves[0][0] >= 1500 and halves[1][1] - halves[1][0] >= 1500
                         and 300 <= gap <= 1800)
            confidence = "medium" if plausible else "low"
        else:
            suggest["end_s"] = round(halves[0][1], 1)
            confidence = "low"
    in_play = sum((s["end_s"] or 0) - (s["kickoff_s"] or 0) for s in [suggest]) if suggest["kickoff_s"] else 0
    total = float(ts[-1])
    return {
        "video": str(video),
        "probe_fps": probe_fps,
        "footage_total_s": round(total, 1),
        "spread_threshold": round(thr, 4),
        "in_play_segments": [[round(a, 1), round(b, 1)] for a, b in sorted(segments, key=lambda r: r[0])],
        "suggested_markers": suggest,
        "confidence": confidence,
        "in_play_s": round(in_play, 1),
        "skipped_s": round(total - in_play, 1) if in_play else None,
        "compute_saved_pct": round(100 * (total - in_play) / total, 1) if in_play else None,
    }


def main() -> None:
    p = argparse.ArgumentParser(description="CPU-only game-time (kickoff/halftime/end) detector")
    p.add_argument("--video", type=Path, required=True)
    p.add_argument("--probe-fps", type=float, default=2.0)
    p.add_argument("--smooth-s", type=float, default=20.0, help="moving-average window for spread")
    p.add_argument("--min-segment-s", type=float, default=MIN_SEGMENT_S,
                   help="shortest run counted as a half (lower for clips)")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    if not args.video.exists():
        raise SystemExit(f"video not found: {args.video}")
    rep = detect(args.video, args.probe_fps, args.smooth_s, args.min_segment_s)
    m = rep.get("suggested_markers", {})
    print(f"\n{'='*60}\nGAME-WINDOW DETECTION  ({Path(rep.get('video','?')).name})")
    print(f"{'='*60}")
    print(f"  footage total      : {rep.get('footage_total_s')}s")
    print(f"  in-play segments   : {rep.get('in_play_segments')}")
    print(f"  SUGGESTED kickoff  : {m.get('kickoff_s')}s  halftime: {m.get('halftime_s')}s")
    print(f"            2nd-half : {m.get('second_half_kickoff_s')}s  end: {m.get('end_s')}s")
    print(f"  confidence         : {rep.get('confidence')}")
    print(f"  compute saved      : ~{rep.get('compute_saved_pct')}% (skip {rep.get('skipped_s')}s of non-play)")
    print(f"{'='*60}\n  ^ verify/override these, then process only [kickoff..halftime]+[2nd-half..end]\n")
    if args.json:
        print(json.dumps(rep, indent=2))


if __name__ == "__main__":
    main()
