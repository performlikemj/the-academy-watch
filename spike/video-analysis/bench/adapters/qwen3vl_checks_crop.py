"""Lane C: the lane B questions and transport over player-centred crops."""

from __future__ import annotations

import os
import time
from pathlib import Path

from PIL import Image
from pydantic import ValidationError

from .common import (
    crop_player_frame,
    draw_truth_box,
    interpolated_box,
    qwen_match_analysis as qwen_match_analysis,
    scale_box,
    temp_directory,
)
from .qwen3vl_annotated import ANCHOR_COLOR, prepare_sample_frames
from .qwen3vl_checks import (
    CONTRACT_VERSION,
    DEFAULT_MODEL,
    PROMPT_VERSION as BASE_PROMPT_VERSION,
    build_prompt as base_prompt,
    call_model,
)

PROMPT_VERSION = BASE_PROMPT_VERSION + "-crop"
CROP_VERSION = "player-square-v1"


def build_prompt(truth: dict, timestamps: list[float], *, context=False) -> str:
    sentence = "Each image is a close crop centred on the marked player"
    if context:
        sentence += ", followed by the full frame for context"
    first, rest = base_prompt(truth, timestamps).split("\n", 1)
    return first + "\n" + sentence + ".\n" + rest


def prepare_frames(clip: str | Path, truth: dict, cfg: dict, directory: Path):
    extracted = prepare_sample_frames(clip, truth, cfg, directory)
    frames, anchors = [], []
    for index, frame in enumerate(extracted):
        source_box = interpolated_box(truth.get("box_track") or [], frame["t"])
        if source_box is None:
            raise RuntimeError(f"truth box unavailable at {frame['t']}")
        decoded_size = (frame["sent_w"], frame["sent_h"])
        box = scale_box(source_box, tuple(truth["frame_size"]), decoded_size)
        output = directory / f"crop-{index:02d}.png"
        geometry = crop_player_frame(Path(frame["path"]), output, box)
        draw_truth_box(
            output, geometry["box"], int(truth["jersey_number"]), color=ANCHOR_COLOR
        )
        crop = {
            **frame,
            **geometry,
            "path": str(output),
            "image_kind": "crop",
            "sent_w": 768,
            "sent_h": 768,
        }
        frames.append(crop)
        anchors.append(
            {
                **geometry,
                "t": frame["t"],
                "image_kind": "crop",
                "box_source_space": source_box,
                "sent_w": 768,
                "sent_h": 768,
            }
        )
        if cfg.get("crop_context", False):
            context_path = directory / f"context-{index:02d}.png"
            size = (512, round(decoded_size[1] * 512 / decoded_size[0]))
            with Image.open(frame["path"]) as source:
                source.resize(size, Image.Resampling.LANCZOS).save(context_path)
            context_box = scale_box(box, decoded_size, size)
            draw_truth_box(
                context_path,
                context_box,
                int(truth["jersey_number"]),
                color=ANCHOR_COLOR,
            )
            frames.append(
                {
                    **frame,
                    "path": str(context_path),
                    "image_kind": "context",
                    "sent_w": size[0],
                    "sent_h": size[1],
                }
            )
            anchors.append(
                {
                    "t": frame["t"],
                    "image_kind": "context",
                    "box": context_box,
                    "box_source_space": source_box,
                    "sent_w": size[0],
                    "sent_h": size[1],
                }
            )
    return frames, anchors


def run(clip: str | Path, truth: dict, cfg: dict) -> dict:
    started = time.monotonic()
    metadata: dict = {}
    frames, anchors = [], []
    parsed, error = None, None
    try:
        with temp_directory("evidence-checks-crop-") as directory:
            frames, anchors = prepare_frames(clip, truth, cfg, Path(directory))
            timestamps = [f["t"] for f in frames if f["image_kind"] == "crop"]
            parsed = call_model(
                build_prompt(truth, timestamps, context=cfg.get("crop_context", False)),
                frames,
                cfg,
                metadata,
            )
    except ValidationError:
        error = "checks schema validation failed"
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    return {
        "checks_raw": metadata.get("raw", ""),
        "checks": parsed.model_dump() if parsed is not None else None,
        "contract_version": CONTRACT_VERSION,
        "prompt_version": PROMPT_VERSION,
        "crop_version": CROP_VERSION,
        "crop_context": bool(cfg.get("crop_context", False)),
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
