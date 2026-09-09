#!/usr/bin/env python3
"""Three isolated /api/chat calls to audit format routing; no transport changes."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import time
import urllib.request
from pathlib import Path

from pydantic import ValidationError

try:
    from .adapters.qwen3vl_checks import (
        DEFAULT_MODEL,
        PROMPT_VERSION,
        build_prompt,
        prepare_frames,
    )
    from .adapters.common import temp_directory
    from .checks_contract import CONTRACT_VERSION, parse_read, response_schema
    from .provenance import load_truth_snapshot
except ImportError:  # pragma: no cover
    from adapters.qwen3vl_checks import (
        DEFAULT_MODEL,
        PROMPT_VERSION,
        build_prompt,
        prepare_frames,
    )
    from adapters.common import temp_directory
    from checks_contract import CONTRACT_VERSION, parse_read, response_schema
    from provenance import load_truth_snapshot

SMOKE_CLIP = "m04-n12-t1411-237107-242145"


def inspect_payload(payload: dict) -> dict:
    message = payload.get("message") or {}
    content, thinking = message.get("content"), message.get("thinking")
    fields, validation = [], {}
    for name, value in (("content", content), ("thinking", thinking)):
        try:
            json.loads(value)
            fields.append(f"message.{name}")
        except (TypeError, ValueError):
            pass
        try:
            parse_read(value)
            validation[name] = True
        except (TypeError, ValidationError):
            validation[name] = False
    empty = isinstance(content, str) and not content.strip()
    # Report exactly the channel selection used by the unchanged shared transport.
    selected = (
        "thinking"
        if empty and isinstance(thinking, str) and thinking.strip()
        else "content"
    )
    return {
        "json_field": ", ".join(fields) or "none",
        "json_fields": fields,
        "content_empty": empty,
        "content_missing": not isinstance(content, str),
        "validated": validation[selected] if isinstance(content, str) else False,
        "validation_by_field": validation,
        "selected_field": f"message.{selected}",
        "message": message,
        "done_reason": payload.get("done_reason"),
    }


def diagnose(
    manifest_path: Path,
    *,
    clip_id=SMOKE_CLIP,
    ollama_url="http://127.0.0.1:11434",
    model=DEFAULT_MODEL,
    timeout=120,
) -> dict:
    manifest = json.loads(manifest_path.read_text())
    truths, provenance = load_truth_snapshot(manifest_path)
    entry = next(c for c in manifest["clips"] if c["clip_id"] == clip_id)
    truth = truths[clip_id]
    calls = []
    with temp_directory("checks-format-diagnostic-") as directory:
        frames, anchors = prepare_frames(
            manifest_path.parent / entry["clip"],
            truth,
            {"sample_interval": 0.5, "sample_limit": 12},
            Path(directory),
        )
        prompt = build_prompt(truth, [f["t"] for f in frames])
        images = [
            base64.b64encode(Path(f["path"]).read_bytes()).decode("ascii")
            for f in frames
        ]
        for frame in frames:
            frame["sha256"] = hashlib.sha256(
                Path(frame["path"]).read_bytes()
            ).hexdigest()
        for mode in ("schema", "json", "none"):
            body = {
                "model": model,
                "think": False,
                "stream": False,
                "options": {
                    "num_ctx": 65536,
                    "num_predict": 400,
                    "temperature": 0,
                    "repeat_penalty": 1.15,
                },
                "messages": [{"role": "user", "content": prompt, "images": images}],
            }
            if mode != "none":
                body["format"] = response_schema() if mode == "schema" else "json"
            started = time.monotonic()
            try:
                request = urllib.request.Request(
                    f"{ollama_url.rstrip('/')}/api/chat",
                    data=json.dumps(body).encode(),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    payload = json.loads(response.read())
                row = {**inspect_payload(payload), "error": None}
            except Exception as exc:
                row = {
                    "json_field": "none",
                    "json_fields": [],
                    "content_empty": None,
                    "validated": False,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            calls.append(
                {
                    "format_mode": mode,
                    "wall_s": round(time.monotonic() - started, 3),
                    **row,
                }
            )
            print(
                json.dumps({k: v for k, v in calls[-1].items() if k != "message"}),
                flush=True,
            )
    return {
        "clip_id": clip_id,
        "model": model,
        "ollama_url": ollama_url,
        "contract_version": CONTRACT_VERSION,
        "prompt_version": PROMPT_VERSION,
        **provenance,
        "think": False,
        "num_ctx": 65536,
        "num_predict": 400,
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "sent_frames": frames,
        "anchored_frames": anchors,
        "calls": calls,
        "scope": "Three single requests, identical dense frames and prompt, only format varies. Raw message fields retained. No repairs, retries or shared-transport changes.",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out-json", type=Path, required=True)
    parser.add_argument("--clip", default=SMOKE_CLIP)
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--timeout", type=float, default=120)
    args = parser.parse_args(argv)
    result = diagnose(
        args.manifest,
        clip_id=args.clip,
        ollama_url=args.ollama_url,
        model=args.model,
        timeout=args.timeout,
    )
    args.out_json.write_text(json.dumps(result, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
