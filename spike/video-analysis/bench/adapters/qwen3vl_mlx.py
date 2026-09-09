"""Native Qwen3-VL video through an isolated mlx-vlm Python worker."""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from .common import (
    VIDEO_ANALYSIS_DIR,
    absolute_timestamp,
    image_dimensions,
    qwen_match_analysis,
    sample_timestamps,
    scale_box,
)
from .qwen3vl_ollama import (
    apply_anchors,
    build_prompt,
    convert_claim_boxes,
    parse_claims,
    tag_boxed_frames,
)

DEFAULT_MODEL = "mlx-community/Qwen3-VL-8B-Instruct-4bit"
DEFAULT_PYTHON = "~/mlx-vlm-venv/bin/python"


def resolved_python() -> str:
    # Do not resolve symlinks: that would bypass the worker's venv.
    return str(
        Path(os.getenv("BENCH_MLX_PYTHON") or DEFAULT_PYTHON).expanduser().absolute()
    )


def prepare_anchor(clip: Path, truth: dict, directory: Path) -> tuple[dict, list[dict]]:
    local_s, absolute_s = sample_timestamps(truth, limit=1)[0]
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg must be available on PATH")
    output = directory / "anchor.jpg"
    qwen_match_analysis.extract_frame(
        clip,
        output,
        local_s,
        Path(ffmpeg),
        Path(ffmpeg).resolve().parent,
        VIDEO_ANALYSIS_DIR / "sandbox" / "ffmpeg_decode.sb",
        False,
        None,
    )
    width, height = image_dimensions(output)
    frame = {"path": str(output), "t": absolute_s, "sent_w": width, "sent_h": height}
    return frame, apply_anchors([frame], truth, "first")


def run(clip: str | Path, truth: dict, cfg: dict) -> dict:
    started = time.monotonic()
    model = cfg.get("model") or os.getenv("BENCH_MLX_MODEL") or DEFAULT_MODEL
    result = {
        "claims_raw": "",
        "claims": [],
        "tokens": None,
        "model": model,
        "anchor_mode": "first",
        "box_space": "normalized_1000",
        "sent_frames": [],
        "anchored_frames": [],
        "error": None,
    }
    try:
        fps = float(cfg.get("fps", os.getenv("BENCH_MLX_FPS", "2.0")))
        if not math.isfinite(fps) or fps <= 0:
            raise ValueError("fps must be positive and finite")
        if (
            cfg.get("anchor_mode", "first") != "first"
            or cfg.get("box_space", "normalized_1000") != "normalized_1000"
        ):
            raise ValueError("MLX requires anchor-mode first and normalized_1000 boxes")
        with tempfile.TemporaryDirectory(
            prefix="mlx-", dir=cfg.get("scratch_dir")
        ) as tmp:
            anchor, anchors = prepare_anchor(Path(clip), truth, Path(tmp))
            result["anchored_frames"] = anchors
            prompt = build_prompt(
                truth, [anchor["t"]], (anchor["sent_w"], anchor["sent_h"]), "first"
            )
            prompt += (
                "\nThe image is the identity anchor only; the video is the clip. "
                "All video frames are unlabelled. Track the same player through the video. "
                f"The clip starts at absolute source time {truth['window']['start_s']:.3f}s. "
                "Video times are clip-local: add that start time for ALL returned times. "
                "Video sampled timestamps in absolute source seconds: __VIDEO_TIMESTAMPS__. "
                "The video processor may resize frames; boxes remain normalized 0-1000 relative to the entire frame. "
                "No Markdown or code fences. Begin the response with { and end with }."
            )
            request = {
                "clip": str(Path(clip).resolve()),
                "anchor_image": anchor["path"],
                "prompt": prompt,
                "model": model,
                "fps": fps,
                "start_s": float(truth["window"]["start_s"]),
                "max_tokens": max(1, min(int(cfg.get("num_predict", 400)), 400)),
                "temperature": 0.0,
                "repetition_penalty": float(cfg.get("repeat_penalty", 1.15)),
                "repetition_context_size": 64,
            }
            completed = subprocess.run(
                [
                    cfg.get("mlx_python") or resolved_python(),
                    str(Path(__file__).with_name("mlx_worker.py")),
                ],
                input=json.dumps(request),
                text=True,
                capture_output=True,
                timeout=max(
                    0.1, float(cfg.get("timeout_s", 120)) - (time.monotonic() - started)
                ),
                check=False,
            )
            worker = json.loads(completed.stdout)
            if completed.returncode or worker.get("error"):
                raise RuntimeError(
                    worker.get("error") or f"MLX worker exited {completed.returncode}"
                )
            if worker["model"] != model:
                raise ValueError("worker model does not match requested model")
            width, height = int(worker["sent_w"]), int(worker["sent_h"])
            times = worker["sampled_frame_times"]
            if (
                min(width, height) <= 0
                or not times
                or any(not math.isfinite(t) or t < 0 for t in times)
                or times != sorted(set(times))
            ):
                raise ValueError("invalid worker frame provenance")
            result.update(
                claims_raw=worker["text"],
                tokens=worker["generation_tokens"],
                prompt_tokens=worker["prompt_tokens"],
                generation_tokens=worker["generation_tokens"],
                worker_wall_s=worker["wall_s"],
                fps=fps,
                effective_fps=worker.get("effective_fps"),
                sent_frames=[
                    {
                        "path": str(clip),
                        "t": absolute_timestamp(truth, t),
                        "sent_w": width,
                        "sent_h": height,
                    }
                    for t in times
                ],
            )
            # Echo checks compare with the anchor after the image processor resize.
            size = (int(worker["anchor_sent_w"]), int(worker["anchor_sent_h"]))
            for frame in anchors:
                frame["box"] = scale_box(
                    frame["box"], (frame["sent_w"], frame["sent_h"]), size
                )
                frame["sent_w"], frame["sent_h"] = size
            parsed = parse_claims(worker["text"])
            if not any(not claim["malformed"] for claim in parsed):
                result["error"] = "no parseable claims"
            result["claims"] = convert_claim_boxes(
                tag_boxed_frames(parsed, anchors),
                tuple(truth["frame_size"]),
                (width, height),
                "normalized_1000",
            )
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    result["wall_s"] = round(time.monotonic() - started, 3)
    return result
