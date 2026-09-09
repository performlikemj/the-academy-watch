"""Annotated stills with tracker-owned geometry and schema-constrained meaning."""

from __future__ import annotations

import math
import os
import time
from pathlib import Path

from pydantic import ValidationError

try:
    from ..semantic_contract import (
        VOCABULARIES,
        SemanticRead,
        parse_read,
        response_schema,
    )
except ImportError:  # pragma: no cover
    from semantic_contract import (
        VOCABULARIES,
        SemanticRead,
        parse_read,
        response_schema,
    )

from .common import (
    absolute_timestamp,
    extract_sample_frames,
    interpolated_box,
    ollama_chat_with_options,
    qwen_match_analysis,
    sample_timestamps,
    temp_directory,
)
from .qwen3vl_ollama import apply_anchors

DEFAULT_MODEL = "qwen3-vl:8b"
ANCHOR_COLOR = (255, 0, 255)


def spread_timestamps(
    truth: dict, interval_s: float = 0.5, limit: int = 12
) -> list[tuple[float, float]]:
    """Cadence determines count; spread capped samples across the entire window."""
    if not math.isfinite(interval_s) or interval_s <= 0 or limit < 1:
        raise ValueError("sampling interval and limit must be positive")
    cadence = sample_timestamps(truth, interval_s=interval_s, limit=limit)
    if len(cadence) <= 1:
        return cadence
    first = cadence[0][0]
    duration = float(truth["window"]["end_s"]) - float(truth["window"]["start_s"])
    last = max(first, duration - min(0.05, duration / 2))
    return [
        (round(local, 3), absolute_timestamp(truth, local))
        for i in range(len(cadence))
        for local in [first + (last - first) * i / (len(cadence) - 1)]
    ]


def annotated_timestamps(
    truth: dict, targets: list[tuple[float, float]]
) -> list[tuple[float, float]]:
    """Snap gap samples to real tracked timestamps within 0.5s; never bridge a gap."""
    start = float(truth["window"]["start_s"])
    end = float(truth["window"]["end_s"])
    track = truth.get("box_track") or []
    observations = sorted(
        {
            float(row[0])
            for row in track
            if len(row) >= 5 and start <= float(row[0]) < end
        }
    )
    selected = []
    used = set()
    for local, absolute in targets:
        if interpolated_box(track, absolute) is None:
            nearby = [
                t for t in observations if abs(t - absolute) <= 0.5 and t not in used
            ]
            if not nearby:
                raise RuntimeError(
                    f"truth box is unavailable within 0.5s of sampled time {absolute:.3f}s"
                )
            absolute = min(nearby, key=lambda t: (abs(t - absolute), t))
            local = round(absolute - start, 3)
        if absolute in used or (selected and absolute <= selected[-1][1]):
            raise RuntimeError(
                "annotated timestamps must remain distinct and chronological"
            )
        used.add(absolute)
        selected.append((local, absolute))
    return selected


def build_prompt(truth: dict, timestamps: list[float]) -> str:
    vocab = "\n".join(
        f"{key} must be exactly one of: {', '.join(values)}."
        for key, values in VOCABULARIES.items()
    )
    return f"""Review these chronological football frames. Every image has a magenta rectangle labelled #{int(truth["jersey_number"])} around the same tracked player.
The tracker owns geometry; describe only the marked player's visible meaning. Do not return boxes or coordinates.
Never name a player. Never state a jersey number other than the drawn label; that label is supplied tracking identity, not proof that a number is readable.
Never claim a goal unless visibly scored. Do not invent actions or outcomes between sampled images.
Return one JSON object matching the supplied schema, with 0 to 3 events, player_visible, kit_color_seen, and sentence.
The sentence must be one sentence of at most 200 characters describing only what is visible.
Use no events, none, or unclear when nothing is visible; these are correct answers. Use low confidence for uncertain evidence.
Read the kit colour from the player, not the magenta rectangle. Use unclear when it cannot be seen.
Window absolute source seconds: [{float(truth["window"]["start_s"]):.3f}, {float(truth["window"]["end_s"]):.3f}].
Sampled timestamps in image order (absolute source seconds): {", ".join(f"{t:.3f}" for t in timestamps)}.
Every event's t0 and t1 must be ordered absolute source seconds inside this window.
{vocab}"""


def call_model(
    prompt: str, frames: list[dict], cfg: dict, metadata: dict
) -> SemanticRead:
    """Typed model boundary; persist the exact response for local bench auditing."""
    num_ctx = qwen_match_analysis.resolve_num_ctx("BENCH_NUM_CTX", "QWEN_NUM_CTX")
    if num_ctx not in (None, 65536):
        raise ValueError("annotated lane requires num_ctx 65536 or omitted")
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


def prepare_frames(clip: str | Path, truth: dict, cfg: dict, directory: Path):
    """Shared annotated feed: spread, bounded gap snapping, and magenta identity."""
    targets = spread_timestamps(
        truth,
        float(cfg.get("sample_interval", 0.5)),
        int(cfg.get("sample_limit", 12)),
    )
    timestamps = annotated_timestamps(truth, targets)
    extracted = extract_sample_frames(
        Path(clip), truth, Path(directory), timestamps=timestamps
    )
    for frame, (_, target_t) in zip(extracted, targets):
        frame["target_t"] = target_t
        frame["sampling_shift_s"] = round(frame["t"] - target_t, 3)
    if not extracted:
        raise RuntimeError("clip yielded no sample frames")
    anchors = apply_anchors(extracted, truth, "all", color=ANCHOR_COLOR)
    return extracted, anchors


def run(clip: str | Path, truth: dict, cfg: dict) -> dict:
    started = time.monotonic()
    metadata: dict = {}
    frames, anchors = [], []
    parsed = None
    error = None
    try:
        with temp_directory("evidence-annotated-") as directory:
            frames, anchors = prepare_frames(clip, truth, cfg, Path(directory))
            parsed = call_model(
                build_prompt(truth, [f["t"] for f in frames]), frames, cfg, metadata
            )
    except ValidationError:
        error = "semantic schema validation failed"
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    return {
        "semantic_raw": metadata.get("raw", ""),
        "semantic": parsed.model_dump() if parsed is not None else None,
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
