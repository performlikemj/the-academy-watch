#!/usr/bin/env python3
"""Prototype: read jersey number / kit color / role from entity crops with a local
MLX VLM (concierge-phase identity anchoring on Apple Silicon).

Usage:
  .venv-vlm/bin/python identify_crops.py --crops-dir results/v8/vlm_test \
      [--model mlx-community/Qwen2.5-VL-7B-Instruct-4bit] [--out results.json]
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

PROMPT = (
    'Look at this football player. Reply ONLY with JSON: '
    '{"jersey_number": <number or null if not readable>, '
    '"shirt_color": "<color>", '
    '"role": "<outfield|goalkeeper|referee|not_a_player>"}'
)


def parse_json_block(text: str) -> dict | None:
    m = re.search(r"\{.*?\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--crops-dir", required=True, type=Path)
    p.add_argument("--model", default="mlx-community/Qwen2.5-VL-7B-Instruct-4bit")
    p.add_argument("--out", type=Path, default=None)
    p.add_argument("--max-tokens", type=int, default=60)
    args = p.parse_args()

    from mlx_vlm import generate, load
    from mlx_vlm.prompt_utils import apply_chat_template

    print(f"loading {args.model} ...")
    model, processor = load(args.model)
    config = model.config

    results: dict[str, dict | str] = {}
    crops = sorted(args.crops_dir.glob("*.jpg"))
    t0 = time.perf_counter()
    for i, crop in enumerate(crops):
        formatted = apply_chat_template(processor, config, PROMPT, num_images=1)
        out = generate(model, processor, formatted, [str(crop)], max_tokens=args.max_tokens, temperature=0.0, verbose=False)
        text = out.text if hasattr(out, "text") else str(out)
        parsed = parse_json_block(text)
        results[crop.name] = parsed if parsed else f"UNPARSED: {text[:120]}"
        print(f"[{i + 1}/{len(crops)}] {crop.name}: {results[crop.name]}")
    dt = time.perf_counter() - t0
    print(f"\n{len(crops)} crops in {dt:.1f}s ({dt / max(1, len(crops)):.2f}s/crop)")

    out_path = args.out or (args.crops_dir / "identify_results.json")
    out_path.write_text(json.dumps(results, indent=2))
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
