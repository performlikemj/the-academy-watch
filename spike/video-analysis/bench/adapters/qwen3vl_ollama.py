"""Qwen3-VL Ollama adapter with the tracked player visibly constrained."""

from __future__ import annotations

import os
import time
from pathlib import Path

try:
    from ..contract import parse_claims
except ImportError:  # pragma: no cover
    from contract import parse_claims

from .common import (
    draw_truth_box,
    extract_sample_frames,
    interpolated_box,
    ollama_chat_with_options,
    qwen_match_analysis,
    temp_directory,
)

DEFAULT_MODEL = "qwen3-vl:8b"
CONTRACT_PROMPT = """You are reviewing sampled frames from one football clip. Every frame contains a thin red
rectangle labelled #{jersey_number}. Describe ONLY the boxed player. Never identify or guess a player name. Never
infer a jersey number: #{jersey_number} is supplied only as a tracking label. The source video is {frame_width}x{frame_height}
pixels, and the frame timestamps in absolute source seconds are: {timestamps}.

Return one JSON object only with this exact shape:
{{"claims":[{{"claim":str,"t0":number,"t1":number,"box":[x1,y1,x2,y2]|null,
"confidence":"low|medium|high","visibility":"clear|partial|unclear"}}]}}

For every claim, t0 and t1 must be absolute source seconds inside [{window_start}, {window_end}]. Return the box of
the visible evidence region for that claim in SOURCE pixel coordinates, not coordinates from the resized prompt
image. Use the supplied source dimensions to convert coordinates. The evidence box must cover only the tracked
player region that supports the sentence. If the boxed player or action is not visible enough to support a claim,
omit the claim. Use visibility="unclear" and low confidence when evidence is genuinely unclear. Do not invent an
action, outcome, statistic, formation, identity, name, or readable number."""


def build_prompt(truth: dict, timestamps: list[float]) -> str:
    return CONTRACT_PROMPT.format(
        jersey_number=int(truth["jersey_number"]),
        frame_width=int(truth["frame_size"][0]),
        frame_height=int(truth["frame_size"][1]),
        timestamps=", ".join(f"{timestamp:.3f}" for timestamp in timestamps),
        window_start=float(truth["window"]["start_s"]),
        window_end=float(truth["window"]["end_s"]),
    )


def run(clip: str | Path, truth: dict, cfg: dict) -> dict:
    clip = Path(clip)
    model = cfg.get("model") or os.getenv("BENCH_MODEL") or DEFAULT_MODEL
    started = time.monotonic()
    raw = ""
    claims = []
    error = None
    try:
        with temp_directory("evidence-qwen3vl-") as temp_dir:
            frames = extract_sample_frames(clip, truth, Path(temp_dir) / "frames")
            if not frames:
                raise RuntimeError("clip yielded no sample frames")
            for frame_path, absolute_s in frames:
                box = interpolated_box(truth.get("box_track") or [], absolute_s)
                if box is None:
                    raise RuntimeError(
                        f"truth box is unavailable at sampled time {absolute_s:.3f}s"
                    )
                draw_truth_box(
                    frame_path, box, truth["frame_size"], int(truth["jersey_number"])
                )
            raw = ollama_chat_with_options(
                build_prompt(truth, [absolute_s for _path, absolute_s in frames]),
                ollama_url=cfg.get(
                    "ollama_url", qwen_match_analysis.DEFAULT_OLLAMA_URL
                ),
                model=model,
                timeout_s=float(cfg.get("timeout_s", 300)),
                image_paths=[path for path, _absolute_s in frames],
                options={
                    "num_predict": max(1, min(int(cfg.get("num_predict", 400)), 400)),
                    "repeat_penalty": 1.15,
                },
            )
            claims = parse_claims(raw)
    except Exception as exc:  # run_bench/scorer applies the mechanical-failure rule
        error = f"{type(exc).__name__}: {exc}"
    return {
        "claims_raw": raw,
        "claims": claims,
        "wall_s": round(time.monotonic() - started, 3),
        "tokens": None,
        "model": model,
        "error": error,
    }
