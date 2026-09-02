"""Qwen3-VL Ollama adapter with the tracked player visibly constrained."""

from __future__ import annotations

import math
import os
import time
from pathlib import Path

try:
    from ..contract import CONFIDENCE_VALUES, VISIBILITY_VALUES, parse_claims
except ImportError:  # pragma: no cover
    from contract import CONFIDENCE_VALUES, VISIBILITY_VALUES, parse_claims

from .common import (
    draw_truth_box,
    extract_sample_frames,
    interpolated_box,
    ollama_chat_with_options,
    qwen_match_analysis,
    scale_box,
    temp_directory,
)
from grounding import impossible_box_reason, normalized_1000_to_source

DEFAULT_MODEL = "qwen3-vl:8b"
ANCHOR_MODES = frozenset({"first", "all"})
BOX_SPACES = frozenset({"normalized_1000", "image_pixels"})
DEFAULT_BOX_SPACE = "normalized_1000"
FORMAT_MODES = frozenset({"json", "schema"})
BOX_COORDINATE_INSTRUCTIONS = {
    "normalized_1000": (
        "Return the box as integers from 0 to 1000 relative to the image: x=0 is "
        "left, x=1000 is right, y=0 is top, and y=1000 is bottom. box_t must be "
        "the timestamp of the frame your box came from; t0..t1 may cover the whole "
        "action."
    ),
    "image_pixels": (
        "Return the box of the visible evidence region for that claim in the "
        "coordinates of the IMAGE PROVIDED ({frame_width}x{frame_height}). box_t "
        "must be the timestamp of the frame your box came from; t0..t1 may cover "
        "the whole action."
    ),
}
FIRST_CONTRACT_PROMPT = """You are reviewing sampled frames from one football clip.
the first image identifies the player with a red rectangle; the other images are unlabelled — find that same player yourself and box the evidence region in those frames.
Describe ONLY that player. Never identify or guess a player name. Never
infer a jersey number: #{jersey_number} is supplied only as a tracking label. The images provided are exactly
{frame_width}x{frame_height} pixels, and their timestamps in absolute source seconds are: {timestamps}.

Return one JSON object only with this exact shape:
{{"claims":[{{"claim":str,"t0":number,"t1":number,"box_t":number,"box":[x1,y1,x2,y2]|null,
"confidence":"low|medium|high","visibility":"clear|partial|unclear"}}]}}

For every claim, t0 and t1 must be absolute source seconds inside [{window_start}, {window_end}].
{box_coordinate_instruction}
The evidence box must cover only the tracked player region that supports the sentence. If the boxed player or
action is not visible enough to support a claim, omit the claim. Use visibility="unclear" and low confidence when
evidence is genuinely unclear. Do not invent an action, outcome, statistic, formation, identity, name, or readable
number."""
ALL_CONTRACT_PROMPT = """You are reviewing sampled frames from one football clip. Every frame contains a thin red
rectangle labelled #{jersey_number}. Describe ONLY the boxed player. Never identify or guess a player name. Never
infer a jersey number: #{jersey_number} is supplied only as a tracking label. The images provided are exactly
{frame_width}x{frame_height} pixels, and their timestamps in absolute source seconds are: {timestamps}.

Return one JSON object only with this exact shape:
{{"claims":[{{"claim":str,"t0":number,"t1":number,"box_t":number,"box":[x1,y1,x2,y2]|null,
"confidence":"low|medium|high","visibility":"clear|partial|unclear"}}]}}

For every claim, t0 and t1 must be absolute source seconds inside [{window_start}, {window_end}].
{box_coordinate_instruction}
The evidence box must cover only the tracked player region that supports the sentence. If the boxed player or
action is not visible enough to support a claim, omit the claim. Use visibility="unclear" and low confidence when
evidence is genuinely unclear. Do not invent an action, outcome, statistic, formation, identity, name, or readable
number."""


def bench_claim_schema() -> dict:
    """Build the bench claim schema lazily from the strict contract constants."""
    from typing import Literal

    from pydantic import BaseModel, ConfigDict, conlist

    class BenchClaim(BaseModel):
        model_config = ConfigDict(extra="forbid")

        claim: str
        t0: float
        t1: float
        box_t: float
        box: conlist(float, min_length=4, max_length=4) | None
        confidence: Literal[*tuple(sorted(CONFIDENCE_VALUES))]
        visibility: Literal[*tuple(sorted(VISIBILITY_VALUES))]

    class BenchClaims(BaseModel):
        model_config = ConfigDict(extra="forbid")

        claims: conlist(BenchClaim, max_length=3)

    return BenchClaims.model_json_schema()


def build_prompt(
    truth: dict,
    timestamps: list[float],
    sent_size: tuple[int, int],
    anchor_mode: str,
    box_space: str = DEFAULT_BOX_SPACE,
) -> str:
    if anchor_mode not in ANCHOR_MODES:
        raise ValueError(
            f"anchor_mode must be one of {', '.join(sorted(ANCHOR_MODES))}"
        )
    if box_space not in BOX_SPACES:
        raise ValueError(f"box_space must be one of {', '.join(sorted(BOX_SPACES))}")
    template = FIRST_CONTRACT_PROMPT if anchor_mode == "first" else ALL_CONTRACT_PROMPT
    return template.format(
        jersey_number=int(truth["jersey_number"]),
        frame_width=sent_size[0],
        frame_height=sent_size[1],
        timestamps=", ".join(f"{timestamp:.3f}" for timestamp in timestamps),
        window_start=float(truth["window"]["start_s"]),
        window_end=float(truth["window"]["end_s"]),
        box_coordinate_instruction=BOX_COORDINATE_INSTRUCTIONS[box_space].format(
            frame_width=sent_size[0], frame_height=sent_size[1]
        ),
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
    claims: list[dict],
    source_size: tuple[int, int],
    sent_size: tuple[int, int],
    box_space: str = DEFAULT_BOX_SPACE,
) -> list[dict]:
    """Preserve model-space boxes and convert scoring boxes to source pixels."""
    if box_space not in BOX_SPACES:
        raise ValueError(f"box_space must be one of {', '.join(sorted(BOX_SPACES))}")
    for claim in claims:
        model_box = claim.get("box")
        claim["box_space"] = box_space
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
            converted_box = (
                normalized_1000_to_source(model_box, source_size)
                if box_space == "normalized_1000"
                else scale_box(model_box, sent_size, source_size)
            )
            claim["box"] = converted_box
            reason = box_sanity_reason(
                model_box,
                converted_box,
                box_space=box_space,
                source_size=source_size,
                sent_size=sent_size,
            )
            if reason is not None:
                claim["malformed"] = True
                claim["malformed_fields"] = sorted(
                    set((claim.get("malformed_fields") or []) + [reason])
                )
                claim["box_sanity_reason"] = reason
    return claims


def box_sanity_reason(
    model_box: list[float] | tuple[float, ...],
    converted_box: list[float],
    *,
    box_space: str,
    source_size: tuple[int, int],
    sent_size: tuple[int, int],
) -> str | None:
    """Return an explicit reason when a converted box is physically implausible."""
    suffix = f"(space={box_space})"
    shared_reason = impossible_box_reason(converted_box, source_size)
    if shared_reason == "box outside frame":
        return f"box outside frame after conversion {suffix}"
    if shared_reason == "box area exceeds source frame":
        return f"box area exceeds source frame after conversion {suffix}"
    if shared_reason is not None:
        return f"{shared_reason} after conversion {suffix}"
    if (
        box_space == "image_pixels"
        and (sent_size[0] > 1000 or sent_size[1] > 1000)
        and all(float(value) <= 1000 for value in model_box)
    ):
        return (
            "image-pixel box uses only coordinates <=1000 while sent image is larger "
            f"{suffix}"
        )
    return None


def tag_boxed_frames(claims: list[dict], anchored_frames: list[dict]) -> list[dict]:
    """Mark whether each claim's box_t cites an image carrying a drawn rectangle."""
    anchored_times = [float(frame["t"]) for frame in anchored_frames]
    for claim in claims:
        box_t = claim.get("box_t")
        claim["boxed_frame"] = bool(
            isinstance(box_t, (int, float))
            and not isinstance(box_t, bool)
            and any(
                abs(float(box_t) - timestamp) <= 0.5 for timestamp in anchored_times
            )
        )
    return claims


def run(clip: str | Path, truth: dict, cfg: dict) -> dict:
    clip = Path(clip)
    model = cfg.get("model") or os.getenv("BENCH_MODEL") or DEFAULT_MODEL
    anchor_mode = cfg.get("anchor_mode", "first")
    box_space = cfg.get("box_space", DEFAULT_BOX_SPACE)
    format_mode = cfg.get("format_mode", "json")
    if format_mode not in FORMAT_MODES:
        raise ValueError(
            f"format_mode must be one of {', '.join(sorted(FORMAT_MODES))}"
        )
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
                    box_space,
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
                response_schema=(
                    bench_claim_schema() if format_mode == "schema" else None
                ),
            )
            parsed_claims = parse_claims(raw)
            has_parseable_claim = any(not claim["malformed"] for claim in parsed_claims)
            claims = convert_claim_boxes(
                tag_boxed_frames(parsed_claims, anchored_frames),
                tuple(int(value) for value in truth["frame_size"]),
                sent_size,
                box_space,
            )
            if not has_parseable_claim:
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
        "box_space": box_space,
        "format_mode": format_mode,
        "sent_frames": frames,
        "anchored_frames": anchored_frames,
        "from_thinking": bool(response_metadata.get("from_thinking", False)),
        "error": error,
    }
