"""Qwen3-VL Ollama adapter with the tracked player visibly constrained."""

from __future__ import annotations

import os
import math
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
    scale_box,
    temp_directory,
)

DEFAULT_MODEL = "qwen3-vl:8b"
ANCHOR_MODES = frozenset({"first", "all"})
FIRST_CONTRACT_PROMPT = """You are reviewing sampled frames from one football clip.
the first image identifies the player with a red rectangle; the other images are unlabelled — find that same player yourself and box the evidence region in those frames.
Describe ONLY that player. Never identify or guess a player name. Never
infer a jersey number: #{jersey_number} is supplied only as a tracking label. The images provided are exactly
{frame_width}x{frame_height} pixels, and their timestamps in absolute source seconds are: {timestamps}.

Return one JSON object only with this exact shape:
{{"claims":[{{"claim":str,"t0":number,"t1":number,"box":[x1,y1,x2,y2]|null,
"confidence":"low|medium|high","visibility":"clear|partial|unclear"}}]}}

For every claim, t0 and t1 must be absolute source seconds inside [{window_start}, {window_end}]. Return the box of
the visible evidence region for that claim in the coordinates of the IMAGE PROVIDED ({frame_width}x{frame_height}).
The evidence box must cover only the tracked player region that supports the sentence. If the boxed player or
action is not visible enough to support a claim, omit the claim. Use visibility="unclear" and low confidence when
evidence is genuinely unclear. Do not invent an action, outcome, statistic, formation, identity, name, or readable
number."""
ALL_CONTRACT_PROMPT = """You are reviewing sampled frames from one football clip. Every frame contains a thin red
rectangle labelled #{jersey_number}. Describe ONLY the boxed player. Never identify or guess a player name. Never
infer a jersey number: #{jersey_number} is supplied only as a tracking label. The images provided are exactly
{frame_width}x{frame_height} pixels, and their timestamps in absolute source seconds are: {timestamps}.

Return one JSON object only with this exact shape:
{{"claims":[{{"claim":str,"t0":number,"t1":number,"box":[x1,y1,x2,y2]|null,
"confidence":"low|medium|high","visibility":"clear|partial|unclear"}}]}}

For every claim, t0 and t1 must be absolute source seconds inside [{window_start}, {window_end}]. Return the box of
the visible evidence region for that claim in the coordinates of the IMAGE PROVIDED ({frame_width}x{frame_height}).
The evidence box must cover only the tracked player region that supports the sentence. If the boxed player or
action is not visible enough to support a claim, omit the claim. Use visibility="unclear" and low confidence when
evidence is genuinely unclear. Do not invent an action, outcome, statistic, formation, identity, name, or readable
number."""


def build_prompt(
    truth: dict,
    timestamps: list[float],
    sent_size: tuple[int, int],
    anchor_mode: str,
) -> str:
    if anchor_mode not in ANCHOR_MODES:
        raise ValueError(
            f"anchor_mode must be one of {', '.join(sorted(ANCHOR_MODES))}"
        )
    template = FIRST_CONTRACT_PROMPT if anchor_mode == "first" else ALL_CONTRACT_PROMPT
    return template.format(
        jersey_number=int(truth["jersey_number"]),
        frame_width=sent_size[0],
        frame_height=sent_size[1],
        timestamps=", ".join(f"{timestamp:.3f}" for timestamp in timestamps),
        window_start=float(truth["window"]["start_s"]),
        window_end=float(truth["window"]["end_s"]),
    )


def apply_anchors(frames: list[dict], truth: dict, anchor_mode: str) -> list[dict]:
    """Draw identity anchors and record their exact sent-image rectangles."""
    if anchor_mode not in ANCHOR_MODES:
        raise ValueError(
            f"anchor_mode must be one of {', '.join(sorted(ANCHOR_MODES))}"
        )
    anchored_frames = []
    source_size = tuple(int(value) for value in truth["frame_size"])
    for index, frame in enumerate(frames):
        if anchor_mode == "first" and index > 0:
            continue
        frame_path = Path(frame["path"])
        absolute_s = float(frame["t"])
        box = interpolated_box(truth.get("box_track") or [], absolute_s)
        if box is None:
            raise RuntimeError(
                f"truth box is unavailable at sampled time {absolute_s:.3f}s"
            )
        sent_size = (int(frame["sent_w"]), int(frame["sent_h"]))
        sent_box = scale_box(box, source_size, sent_size)
        draw_truth_box(frame_path, sent_box, int(truth["jersey_number"]))
        anchored_frames.append(
            {
                "t": absolute_s,
                "box": sent_box,
                "box_source_space": box,
                "sent_w": sent_size[0],
                "sent_h": sent_size[1],
            }
        )
    return anchored_frames


def sent_frame_size(frames: list[dict]) -> tuple[int, int]:
    sizes = {(int(frame["sent_w"]), int(frame["sent_h"])) for frame in frames}
    if len(sizes) != 1:
        raise RuntimeError(
            f"sampled frames have inconsistent sent sizes: {sorted(sizes)}"
        )
    return next(iter(sizes))


def convert_claim_boxes(
    claims: list[dict], source_size: tuple[int, int], sent_size: tuple[int, int]
) -> list[dict]:
    """Preserve model-space boxes and convert scoring boxes to source pixels."""
    for claim in claims:
        model_box = claim.get("box")
        claim["box_model_space"] = (
            list(model_box) if isinstance(model_box, (list, tuple)) else model_box
        )
        if (
            isinstance(model_box, (list, tuple))
            and len(model_box) == 4
            and all(
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(float(value))
                for value in model_box
            )
        ):
            claim["box"] = scale_box(model_box, sent_size, source_size)
    return claims


def tag_boxed_frames(claims: list[dict], anchored_frames: list[dict]) -> list[dict]:
    """Mark whether each claim's t0 cites an image carrying a drawn rectangle."""
    anchored_times = [float(frame["t"]) for frame in anchored_frames]
    for claim in claims:
        t0 = claim.get("t0")
        claim["boxed_frame"] = bool(
            isinstance(t0, (int, float))
            and not isinstance(t0, bool)
            and any(abs(float(t0) - timestamp) <= 0.5 for timestamp in anchored_times)
        )
    return claims


def run(clip: str | Path, truth: dict, cfg: dict) -> dict:
    clip = Path(clip)
    model = cfg.get("model") or os.getenv("BENCH_MODEL") or DEFAULT_MODEL
    anchor_mode = cfg.get("anchor_mode", "first")
    started = time.monotonic()
    raw = ""
    claims = []
    frames = []
    anchored_frames = []
    error = None
    response_metadata: dict[str, object] = {}
    try:
        with temp_directory("evidence-qwen3vl-") as temp_dir:
            frames = extract_sample_frames(clip, truth, Path(temp_dir) / "frames")
            if not frames:
                raise RuntimeError("clip yielded no sample frames")
            sent_size = sent_frame_size(frames)
            anchored_frames = apply_anchors(frames, truth, anchor_mode)
            raw = ollama_chat_with_options(
                build_prompt(
                    truth,
                    [float(frame["t"]) for frame in frames],
                    sent_size,
                    anchor_mode,
                ),
                ollama_url=cfg.get(
                    "ollama_url", qwen_match_analysis.DEFAULT_OLLAMA_URL
                ),
                model=model,
                timeout_s=float(cfg.get("timeout_s", 300)),
                image_paths=[Path(frame["path"]) for frame in frames],
                options={
                    "num_predict": max(1, min(int(cfg.get("num_predict", 400)), 400)),
                    "repeat_penalty": float(cfg.get("repeat_penalty", 1.15)),
                },
                response_metadata=response_metadata,
            )
            claims = convert_claim_boxes(
                tag_boxed_frames(parse_claims(raw), anchored_frames),
                tuple(int(value) for value in truth["frame_size"]),
                sent_size,
            )
            if not any(not claim["malformed"] for claim in claims):
                error = "no parseable claims"
    except Exception as exc:  # run_bench/scorer applies the mechanical-failure rule
        error = f"{type(exc).__name__}: {exc}"
    return {
        "claims_raw": raw,
        "claims": claims,
        "wall_s": round(time.monotonic() - started, 3),
        "tokens": None,
        "model": model,
        "anchor_mode": anchor_mode,
        "sent_frames": frames,
        "anchored_frames": anchored_frames,
        "from_thinking": bool(response_metadata.get("from_thinking", False)),
        "error": error,
    }
