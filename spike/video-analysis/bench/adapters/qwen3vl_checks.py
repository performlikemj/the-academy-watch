"""Closed questions over lane A's imported annotated frame feed."""

from __future__ import annotations

import os
import time
from pathlib import Path

from pydantic import ValidationError

try:
    from ..checks_contract import CONTRACT_VERSION, parse_read, response_schema
except ImportError:  # pragma: no cover
    from checks_contract import CONTRACT_VERSION, parse_read, response_schema

from .common import ollama_chat_with_options, qwen_match_analysis, temp_directory
from .qwen3vl_annotated import DEFAULT_MODEL, prepare_frames

PROMPT_VERSION = "film-room-checks-prompt-v1-reasons"


def build_prompt(truth: dict, timestamps: list[float]) -> str:
    return f"""Answer six checks about the same marked player in these chronological football frames.
Every frame has a magenta box and supplied #{int(truth["jersey_number"])} label. Treat the magenta box as identity only. The label is not evidence of a jersey number.
Return one JSON object matching the supplied schema. Each question has answer and confidence (low, medium, high), and one short reason (at most 80 characters). Include a reason for each answer, in at most five words. No other text.
For the first five questions answer exactly yes, no, or unclear:
player_on_pitch: Is the marked player on the field of play, excluding sideline, bench and warm-up area?
play_in_progress: Is the ball in play in this window, excluding warm-up, walking off and stoppages?
ball_near_player: Does the ball come within roughly two body-lengths of the marked player at any point?
player_touches_ball: Does the marked player clearly play the ball (pass, shot, header or control) at least once?
player_running: Does the marked player run, rather than walk or stand, at some point?
kit_color_seen: Answer red, blue, white, black, yellow, green, other, or unclear. Read the clothing, not the magenta annotation.
Unclear is the correct answer whenever the frames do not clearly show it. Never guess. Do not infer actions between frames. A single still cannot establish motion or a ball touch unless clearly visible. Never use other players' actions as evidence for the marked player.
Window source seconds: {truth["window"]["start_s"]} to {truth["window"]["end_s"]}.
Sample source seconds, in image order: {", ".join(f"{t:.3f}" for t in timestamps)}."""


def call_model(prompt: str, frames: list[dict], cfg: dict, metadata: dict):
    num_ctx = qwen_match_analysis.resolve_num_ctx("BENCH_NUM_CTX", "QWEN_NUM_CTX")
    if num_ctx not in (None, 65536):
        raise ValueError("checks lane requires num_ctx 65536 or omitted")
    raw = ollama_chat_with_options(
        prompt,
        ollama_url=cfg.get("ollama_url", qwen_match_analysis.DEFAULT_OLLAMA_URL),
        model=cfg.get("model") or os.getenv("BENCH_MODEL") or DEFAULT_MODEL,
        timeout_s=float(cfg.get("timeout_s", 300)),
        image_paths=[Path(f["path"]) for f in frames],
        options={
            "num_predict": max(1, min(int(cfg.get("num_predict", 400)), 400)),
            "repeat_penalty": float(cfg.get("repeat_penalty", 1.15)),
        },
        response_metadata=metadata,
        response_schema=response_schema(),
    )
    metadata["raw"] = raw
    return parse_read(raw)


def run(clip: str | Path, truth: dict, cfg: dict) -> dict:
    started = time.monotonic()
    metadata: dict = {}
    frames, anchors = [], []
    parsed, error = None, None
    try:
        with temp_directory("evidence-checks-") as directory:
            frames, anchors = prepare_frames(clip, truth, cfg, Path(directory))
            parsed = call_model(
                build_prompt(truth, [f["t"] for f in frames]), frames, cfg, metadata
            )
    except ValidationError:
        error = "checks schema validation failed"
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    return {
        "checks_raw": metadata.get("raw", ""),
        "checks": parsed.model_dump() if parsed is not None else None,
        "contract_version": CONTRACT_VERSION,
        "wall_s": round(time.monotonic() - started, 3),
        "model": cfg.get("model") or os.getenv("BENCH_MODEL") or DEFAULT_MODEL,
        "anchor_mode": "all",
        "anchor_color": "magenta",
        "format_mode": "schema",
        "sent_frames": frames,
        "anchored_frames": anchors,
        "done_reason": metadata.get("done_reason"),
        "from_thinking": bool(metadata.get("from_thinking", False)),
        "error": error,
    }
