"""Today's per-frame observation flow, represented as an honest time-only baseline."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from .common import (
    extract_sample_frames,
    ollama_chat_with_options,
    qwen_match_analysis,
    temp_directory,
)

DEFAULT_MODEL = qwen_match_analysis.DEFAULT_MODEL


def run(clip: str | Path, truth: dict, cfg: dict) -> dict:
    clip = Path(clip)
    model = cfg.get("model") or os.getenv("BENCH_BASELINE_MODEL") or DEFAULT_MODEL
    started = time.monotonic()
    sent_frames = []
    raw_frames = []
    claims = []
    error = None
    try:
        with temp_directory("evidence-baseline-") as temp_dir:
            sent_frames = extract_sample_frames(clip, truth, Path(temp_dir) / "frames")
            for frame in sent_frames:
                frame_path = Path(frame["path"])
                absolute_s = float(frame["t"])
                raw = ollama_chat_with_options(
                    qwen_match_analysis.build_observation_prompt(absolute_s),
                    ollama_url=cfg.get(
                        "ollama_url", qwen_match_analysis.DEFAULT_OLLAMA_URL
                    ),
                    model=model,
                    timeout_s=float(cfg.get("timeout_s", 300)),
                    image_path=frame_path,
                    options={},
                )
                raw_frames.append({"t": absolute_s, "response": raw})
                try:
                    observation = qwen_match_analysis.parse_observation(raw)
                except (json.JSONDecodeError, TypeError, ValueError):
                    claims.append(
                        {
                            "claim": raw,
                            "t0": absolute_s,
                            "t1": absolute_s,
                            "box_t": absolute_s,
                            "box": None,
                            "confidence": "low",
                            "visibility": "unclear",
                            "boxed_frame": False,
                            "malformed": True,
                            "malformed_fields": ["baseline_observation"],
                        }
                    )
                    continue
                sentences = [
                    observation["observation"],
                    *observation["notable_actions"],
                ]
                for sentence in sentences:
                    if isinstance(sentence, str) and sentence.strip():
                        claims.append(
                            {
                                "claim": sentence.strip(),
                                "t0": absolute_s,
                                "t1": absolute_s,
                                "box_t": absolute_s,
                                "box": None,
                                "confidence": "medium",
                                "visibility": "clear",
                                "boxed_frame": False,
                                "malformed": False,
                                "malformed_fields": [],
                            }
                        )
    except Exception as exc:  # mechanical adapter failures must survive as data
        error = f"{type(exc).__name__}: {exc}"
    return {
        "claims_raw": json.dumps({"frames": raw_frames}, ensure_ascii=False),
        "claims": claims,
        "wall_s": round(time.monotonic() - started, 3),
        "tokens": None,
        "model": model,
        "sent_frames": sent_frames,
        "error": error,
    }
