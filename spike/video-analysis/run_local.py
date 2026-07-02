#!/usr/bin/env python3
"""
run_local.py — end-to-end LOCAL Film Room pipeline on Apple Silicon.

Takes a match video and produces the loader-ready artifacts the product consumes,
running every stage on this Mac (no cloud GPU). This is the "footage in -> valuable
data out" system the concierge flow needs, validated viable by bench_detect.py
(RF-DETR detection runs faster-than-realtime on MPS, numerically identical to CPU).

Pipeline (each stage runs in the venv that has its deps):
  1. detect+track+cluster   run_spike.py        (.venv-bench, torch+rfdetr, --device mps)
        -> tracks.npz, tracklet_embeddings.npz, results.json
  2. merge fragments        merge_tracklets.py  (.venv-merge, numpy/opencv)
        -> entities.json, merge_report.json
  3. read jersey numbers    anchor_identity.py  (.venv-vlm, mlx-vlm — Apple Silicon)
        -> identity/{crops/, crops_index.json, reads.json, votes.json}
  4. number-driven chains   invert_identity.py  (.venv-merge)
        -> inverted/{fragments.json, votes.json, chains.json}   <- the loader artifacts dir

Then it prints the load_video_artifacts.py command and the capture_meta['local'] dict
to attach to the VideoMatch so the review UI (footage window + crops + bbox track) works.

Usage:
  # full run on a clip (detect..chains), then load into match 7:
  python run_local.py --video footage/veo-sample.mp4 --name local-demo --match-id 7
  # detection-only proof (skip the VLM identity stages):
  python run_local.py --video footage/veo-sample.mp4 --name probe --skip-vlm --max-seconds 60

License posture unchanged: RF-DETR (Apache-2.0), SigLIP (Apache-2.0), BoT-SORT
(Apache-2.0), Gemma-4 MLX (Apache-2.0). No ultralytics anywhere.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path

SPIKE_DIR = Path(__file__).resolve().parent
VENV_BENCH = SPIKE_DIR / ".venv-bench" / "bin" / "python"   # torch + rfdetr (detection)
VENV_MERGE = SPIKE_DIR / ".venv-merge" / "bin" / "python"   # numpy/opencv (merge/invert)
VENV_VLM = SPIKE_DIR / ".venv-vlm" / "bin" / "python"       # mlx-vlm (jersey reader)

GPU_ENV = {
    "HF_HOME": str(SPIKE_DIR / ".cache" / "hf"),
    "TORCH_HOME": str(SPIKE_DIR / ".cache" / "torch"),
    "PYTORCH_ENABLE_MPS_FALLBACK": "1",      # unsupported MPS op -> CPU instead of crash
    "HF_HUB_DISABLE_PROGRESS_BARS": "1",
}


def _fail(msg: str) -> None:
    print(f"\nFATAL: {msg}")
    raise SystemExit(1)


def run_stage(name: str, venv: Path, script: str, extra: list[str], env_extra: dict | None = None) -> float:
    if not venv.exists():
        _fail(f"venv missing for stage '{name}': {venv}\n"
              f"  create it, e.g.: uv venv {venv.parent.parent} --python 3.13 --seed")
    cmd = [str(venv), script, *extra]
    env = {**os.environ, **(env_extra or {})}
    print(f"\n{'='*70}\n[{name}] {' '.join(cmd)}\n{'='*70}")
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, cwd=str(SPIKE_DIR), env=env)
    dt = time.perf_counter() - t0
    if proc.returncode != 0:
        _fail(f"stage '{name}' exited {proc.returncode} after {dt:.1f}s")
    print(f"[{name}] done in {dt:.1f}s")
    return dt


def _video_duration(path: Path) -> float | None:
    try:
        import av
        with av.open(str(path)) as c:
            s = c.streams.video[0]
            if s.duration:
                return float(s.duration * s.time_base)
            if c.duration:
                return float(c.duration / av.time_base)
    except Exception:
        pass
    return None


def in_play_segments(args, duration: float | None) -> list[tuple[float, float | None]] | None:
    """Build in-play [start, end] segments from operator markers, skipping warmup/halftime/post.
    Returns None when no --kickoff is set (fall back to the --start/--max single window)."""
    if args.kickoff is None:
        return None
    end = args.end if args.end is not None else duration
    ht, sh = args.halftime, args.second_half_kickoff
    if ht is not None and sh is not None:
        segs = [(args.kickoff, ht), (sh, end)]   # two halves, halftime skipped
    elif ht is not None:
        segs = [(args.kickoff, ht)]              # only first half marked
    else:
        segs = [(args.kickoff, end)]            # whole in-play as one window (skip warmup+post)
    return [(s, e) for (s, e) in segs if s is not None and (e is None or e > s)]


def main() -> None:
    p = argparse.ArgumentParser(description="End-to-end local Film Room pipeline (Apple Silicon)")
    p.add_argument("--video", type=Path, required=True)
    p.add_argument("--name", default="local-run", help="run name -> results/<name>")
    p.add_argument("--device", default="mps", choices=["mps", "cpu", "cuda", "auto"])
    p.add_argument("--start-seconds", type=float, default=0.0)
    p.add_argument("--max-seconds", type=float, default=None, help="absolute end timestamp (clip)")
    # Game-time markers (operator-verified): process ONLY in-play, skipping warmup/halftime/post.
    # Setting --kickoff switches on marker mode (REPLACES --start/--max). Saves GPU+VLM compute and
    # removes warmup/sideline non-player detections (a Step-1 precision failure source).
    p.add_argument("--kickoff", type=float, default=None, help="first-half kickoff (s) — enables marker mode")
    p.add_argument("--halftime", type=float, default=None, help="end of first half (s)")
    p.add_argument("--second-half-kickoff", type=float, default=None, help="second-half kickoff (s)")
    p.add_argument("--end", type=float, default=None, help="full-time (s); default = end of video")
    p.add_argument("--model", default="medium", choices=["nano", "small", "medium", "large"])
    p.add_argument("--slicer", default="off", choices=["off", "on", "both"])
    p.add_argument("--vlm-model", default="mlx-community/gemma-4-E4B-it-qat-4bit")
    p.add_argument("--skip-vlm", action="store_true", help="stop after merge (detection-only proof)")
    p.add_argument("--skip-render", action="store_true", help="skip annotated clip rendering (faster)")
    p.add_argument("--match-id", type=int, default=None, help="emit the loader command for this VideoMatch id")
    p.add_argument("--out", type=Path, default=None, help="results dir (default results/<name>)")
    args = p.parse_args()

    if not args.video.exists():
        _fail(f"video not found: {args.video}")
    video = args.video.resolve()
    results = (args.out or (SPIKE_DIR / "results" / args.name)).resolve()
    results.mkdir(parents=True, exist_ok=True)

    timings: dict[str, float] = {}

    # ---- 1+2. detect + track + cluster (GPU on MPS), then merge -----------
    # Marker mode (--kickoff set): run detect per IN-PLAY half with tid-offset namespacing and
    # combine — skipping warmup/halftime/post. Otherwise: the single --start/--max window.
    duration = _video_duration(video)
    segs = in_play_segments(args, duration)
    base = ["--video", str(video), "--device", args.device, "--model", args.model, "--slicer", args.slicer]
    in_play_s: float | None = None

    if not segs:
        da = base + ["--out", str(results), "--start-seconds", str(args.start_seconds)]
        if args.max_seconds is not None:
            da += ["--max-seconds", str(args.max_seconds)]
        timings["detect"] = run_stage(f"detect (run_spike, {args.device})", VENV_BENCH, "run_spike.py", da, GPU_ENV)
        timings["merge"] = run_stage("merge (merge_tracklets)", VENV_MERGE, "merge_tracklets.py",
                                     ["--results-dir", str(results), "--video", str(video)])
    elif len(segs) == 1:
        s, e = segs[0]
        da = base + ["--out", str(results), "--start-seconds", str(s)]
        if e is not None:
            da += ["--max-seconds", str(e)]
        timings["detect"] = run_stage(f"detect in-play [{s:.0f},{e}] ({args.device})", VENV_BENCH, "run_spike.py", da, GPU_ENV)
        timings["merge"] = run_stage("merge (merge_tracklets)", VENV_MERGE, "merge_tracklets.py",
                                     ["--results-dir", str(results), "--video", str(video)])
        in_play_s = (e - s) if e is not None else None
    else:
        chunk_dirs: list[str] = []
        t_detect = 0.0
        in_play_s = 0.0
        for i, (s, e) in enumerate(segs):
            seg_dir = results / f"seg{i}"
            da = base + ["--out", str(seg_dir), "--start-seconds", str(s),
                         "--tid-offset", str((i + 1) * 1_000_000), "--render-start", "999999"]
            if e is not None:
                da += ["--max-seconds", str(e)]
            t_detect += run_stage(f"detect half {i} [{s:.0f},{e}] ({args.device})", VENV_BENCH, "run_spike.py", da, GPU_ENV)
            chunk_dirs.append(str(seg_dir))
            if e is not None:
                in_play_s += e - s
        timings["detect"] = t_detect
        timings["merge"] = run_stage("merge (combine in-play halves)", VENV_MERGE, "merge_tracklets.py",
                                     ["--results-dir", str(results), "--video", str(video), "--chunk-dirs", *chunk_dirs])

    if segs is not None and in_play_s and duration:
        print(f"\n[game-time] processing {in_play_s:.0f}s of {duration:.0f}s in-play — skipping "
              f"~{duration - in_play_s:.0f}s ({100 * (duration - in_play_s) / duration:.0f}%) warmup/halftime/post\n")

    artifacts_dir = results / "inverted"
    if not args.skip_vlm:
        # ---- 3. read jersey numbers (MLX VLM, Apple Silicon) --------------
        anchor_args = ["--results-dir", str(results), "--video", str(video), "--model", args.vlm_model]
        if args.skip_render:
            anchor_args += ["--skip-render"]
        timings["vlm_read"] = run_stage("vlm-read (anchor_identity)", VENV_VLM, "anchor_identity.py",
                                        anchor_args, GPU_ENV)

        # ---- 4. number-driven chains (CPU) -------------------------------
        invert_args = ["--results-dir", str(results), "--video", str(video)]
        if args.skip_render:
            invert_args += ["--skip-render"]
        timings["chain"] = run_stage("chain (invert_identity)", VENV_MERGE, "invert_identity.py", invert_args)

    # ---- build the review-UI tracks dir (flat tracks.npz -> chunk*/ layout)
    # video_dev_artifacts globs <tracks_dir>/chunk*/tracks.npz; a single local run
    # writes a flat tracks.npz, so expose it under a chunk0/ symlink.
    flat_tracks = results / "tracks.npz"
    ui_tracks = results / "ui_tracks"
    if flat_tracks.exists():
        (ui_tracks / "chunk0").mkdir(parents=True, exist_ok=True)
        link = ui_tracks / "chunk0" / "tracks.npz"
        if link.is_symlink() or link.exists():
            link.unlink()
        os.symlink(flat_tracks, link)

    # ---- summary + handoff -------------------------------------------------
    total = sum(timings.values())
    print(f"\n{'#'*70}\n# LOCAL PIPELINE COMPLETE  ({args.name})\n{'#'*70}")
    print("per-stage wall-clock:")
    for k, v in timings.items():
        print(f"  {k:10s} {v:8.1f}s")
    print(f"  {'TOTAL':10s} {total:8.1f}s")

    if args.skip_vlm:
        print("\n--skip-vlm: detection+merge only. entities.json written; "
              "no chains/loader artifacts (re-run without --skip-vlm for the full report).")
        print(f"inspect: {results}/entities.json , {results}/merge_report.json")
        return

    capture_local = {
        "footage": str(video),
        "crops_dir": str(results / "identity" / "crops"),
        "crops_index": str(results / "identity" / "crops_index.json"),
        "tracks_dir": str(ui_tracks),
        "fragments": str(artifacts_dir / "fragments.json"),
    }
    print(f"\nloader artifacts dir : {artifacts_dir}")
    print("  contains:", ", ".join(sorted(f.name for f in artifacts_dir.glob("*.json"))) if artifacts_dir.exists() else "(missing!)")
    print("\ncapture_meta['local'] to set on the VideoMatch (dev/local only):")
    print(json.dumps({"local": capture_local}, indent=2))
    print("\nNOTE: crops_index.json is keyed by MERGE entity ids (anchor_identity), while chains "
          "reference INVERT fragment ids — so the review-UI crop strip is PARTIAL for chains whose "
          "members are high-id fragments (pre-existing spike behaviour; same as the v8 demo). "
          "The per-player report and the bbox-track (tid join) are unaffected. "
          "Proper fix = have invert_identity emit inverted/crops_index.json re-keyed to fragment ids.")

    if args.match_id is not None:
        print("\nload into the product DB (from academy-watch-backend, with its venv):")
        print(f"  ../.loan/bin/python src/scripts/load_video_artifacts.py \\\n"
              f"      --match-id {args.match_id} --artifacts-dir {artifacts_dir}")
        print("  then POST /api/admin/video/matches/%d/finalize to build the per-player report." % args.match_id)


if __name__ == "__main__":
    main()
