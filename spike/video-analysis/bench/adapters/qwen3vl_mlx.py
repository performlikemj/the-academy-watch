"""Reserved mlx-vlm native-video adapter for the basecamp E1 pass.

The intended implementation loads ``mlx-community/Qwen3-VL-8B-Instruct-4bit``
with mlx-vlm, passes the clip as native video plus the same grounded contract
prompt, and records generated-token counts from the mlx-vlm response. It must
not silently fall back to sampled Ollama frames because that would make the two
E1 lanes incomparable.
"""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_MODEL = "mlx-community/Qwen3-VL-8B-Instruct-4bit"
STUB_ERROR = (
    "qwen3vl_mlx is an E0 stub: wire the mlx-vlm native-video call on basecamp "
    "after mlx-vlm and mlx-community/Qwen3-VL-8B-Instruct-4bit are installed"
)


def run(clip: str | Path, truth: dict, cfg: dict) -> dict:
    del clip, truth
    return {
        "claims_raw": "",
        "claims": [],
        "wall_s": 0.0,
        "tokens": None,
        "model": cfg.get("model") or os.getenv("BENCH_MLX_MODEL") or DEFAULT_MODEL,
        "error": STUB_ERROR,
    }
