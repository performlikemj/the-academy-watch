#!/usr/bin/env python3
"""Run one Film Room adapter sequentially and write a resumable scored report."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import os
from datetime import UTC, datetime
from pathlib import Path

try:
    from .score import score_run, write_report
except ImportError:  # pragma: no cover - direct script invocation
    from score import score_run, write_report

BENCH_DIR = Path(__file__).resolve().parent
DEFAULT_MANIFEST = BENCH_DIR / "frozen" / "manifest.json"
DEFAULT_REPORT_ROOT = BENCH_DIR / "report"
ADAPTERS = ("baseline", "qwen3vl_ollama", "qwen3vl_mlx")
MODEL_ENVIRONMENT = {
    "baseline": "BENCH_BASELINE_MODEL",
    "qwen3vl_ollama": "BENCH_MODEL",
    "qwen3vl_mlx": "BENCH_MLX_MODEL",
}
MAX_NUM_PREDICT = 400
DEFAULT_REPEAT_PENALTY = 1.15


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def _requested_clips(raw: str, manifest: dict) -> list[str]:
    available = [clip["clip_id"] for clip in manifest["clips"]]
    if raw == "all":
        return available
    requested = [item.strip() for item in raw.split(",") if item.strip()]
    unknown = sorted(set(requested) - set(available))
    if unknown:
        raise ValueError(f"unknown clip ids: {', '.join(unknown)}")
    if not requested:
        raise ValueError("--clips must be 'all' or a comma-separated clip-id list")
    return requested


def _resolved_model(adapter_name: str, requested_model: str | None) -> str:
    adapter = _adapter_module(adapter_name)
    resolved = (
        requested_model
        or os.getenv(MODEL_ENVIRONMENT[adapter_name])
        or adapter.DEFAULT_MODEL
    )
    if not isinstance(resolved, str) or not resolved.strip():
        raise ValueError("resolved model must be a non-empty string")
    return resolved


def _resolve_inference_settings(args: argparse.Namespace, manifest: dict) -> dict:
    frozen_set_id = manifest.get("frozen_set_id")
    if not isinstance(frozen_set_id, str) or not frozen_set_id:
        raise ValueError("manifest must contain a non-empty frozen_set_id")
    timeout_s = float(args.timeout)
    repeat_penalty = float(args.repeat_penalty)
    if not math.isfinite(timeout_s) or timeout_s <= 0:
        raise ValueError("--timeout must be a positive finite number")
    if not math.isfinite(repeat_penalty) or repeat_penalty <= 0:
        raise ValueError("--repeat-penalty must be a positive finite number")
    return {
        "adapter": args.adapter,
        "model": _resolved_model(args.adapter, args.model),
        "ollama_url": str(args.ollama_url),
        "timeout_s": timeout_s,
        "anchor_mode": args.anchor_mode,
        "num_predict": max(1, min(int(args.num_predict), MAX_NUM_PREDICT)),
        "repeat_penalty": repeat_penalty,
        "frozen_set_id": frozen_set_id,
    }


def _settings_fingerprint(settings: dict, clips: list[str]) -> str:
    canonical = json.dumps(
        {"settings": settings, "clips": clips},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


def _run_metadata(settings: dict, clips: list[str]) -> dict:
    return {
        "schema_version": "film-room-evidence-run-v3",
        **settings,
        "fingerprint": _settings_fingerprint(settings, clips),
        "clips": clips,
    }


def _metadata_matches(existing: object, expected: dict) -> bool:
    return bool(
        isinstance(existing, dict)
        and existing.get("fingerprint") == expected["fingerprint"]
        and existing == expected
    )


def _find_resume_dir(report_root: Path, metadata: dict) -> Path | None:
    if not report_root.is_dir():
        return None
    for directory in sorted(
        (path for path in report_root.iterdir() if path.is_dir()), reverse=True
    ):
        run_path = directory / "run.json"
        if not run_path.is_file() or (directory / "report.json").is_file():
            continue
        try:
            existing = _load_json(run_path)
            if _metadata_matches(existing, metadata):
                return directory
        except (KeyError, OSError, TypeError, ValueError):
            continue
    return None


def _output_dir(args: argparse.Namespace, metadata: dict) -> Path:
    if args.run_id:
        return args.report_root / args.run_id
    resumable = _find_resume_dir(args.report_root, metadata)
    if resumable is not None:
        return resumable
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    candidate = args.report_root / run_id
    suffix = 1
    while candidate.exists():
        candidate = args.report_root / f"{run_id}-{suffix}"
        suffix += 1
    return candidate


def _write_run_metadata(
    output_dir: Path, metadata: dict, *, force: bool = False
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    run_path = output_dir / "run.json"
    if run_path.is_file():
        existing = _load_json(run_path)
        if not _metadata_matches(existing, metadata) and not force:
            raise ValueError(
                f"resume fingerprint mismatch in {output_dir}; use --force or choose "
                "a new --run-id"
            )
    run_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")


def _adapter_module(name: str):
    package = f"{__package__}.adapters" if __package__ else "adapters"
    return importlib.import_module(f"{package}.{name}")


def run_benchmark(args: argparse.Namespace) -> tuple[dict, Path]:
    manifest_path = args.manifest.resolve()
    manifest = _load_json(manifest_path)
    selected_ids = _requested_clips(args.clips, manifest)
    selected = {
        clip["clip_id"]: clip
        for clip in manifest["clips"]
        if clip["clip_id"] in selected_ids
    }
    settings = _resolve_inference_settings(args, manifest)
    metadata = _run_metadata(settings, selected_ids)
    output_dir = _output_dir(args, metadata)
    _write_run_metadata(output_dir, metadata, force=args.force)
    claims_dir = output_dir / "claims"
    claims_dir.mkdir(parents=True, exist_ok=True)

    adapter = _adapter_module(args.adapter)
    cfg = {
        "ollama_url": settings["ollama_url"],
        "model": settings["model"],
        "timeout_s": settings["timeout_s"],
        "anchor_mode": settings["anchor_mode"],
        "num_predict": settings["num_predict"],
        "repeat_penalty": settings["repeat_penalty"],
    }
    results = []
    truths = {}
    for clip_id in selected_ids:
        entry = selected[clip_id]
        claims_path = claims_dir / f"{clip_id}.json"
        truth_path = manifest_path.parent / entry["truth"]
        clip_path = manifest_path.parent / entry["clip"]
        truth = _load_json(truth_path)
        truths[clip_id] = truth
        if claims_path.is_file() and not args.force:
            print(f"skip {clip_id} (claims file exists)")
            result = _load_json(claims_path)
        else:
            print(f"run  {clip_id}")
            result = adapter.run(clip_path, truth, cfg)
            result["clip_id"] = clip_id
            claims_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        results.append(result)

    report = score_run(results, truths, adapter=args.adapter)
    write_report(report, output_dir)
    return report, output_dir


def print_summary(report: dict, output_dir: Path) -> None:
    print(
        "\nclip_id                                      status    claims  unboxed  boxed  echo  gap  unsupported  hollow  wall_s"
    )
    print("-" * 122)
    for clip in report["clips"]:
        metrics = clip.get("metrics") or {}

        def pct(key: str) -> str:
            value = metrics.get(key)
            return "—" if value is None else f"{value * 100:.1f}%"

        print(
            f"{str(clip['clip_id']):44} {clip['status']:9} {str(metrics.get('claim_count', '—')):>6} "
            f"{pct('supported_rate_unboxed'):>7} {pct('supported_rate_boxed'):>6} "
            f"{str(metrics.get('echo_suspect_count', '—')):>5} "
            f"{str(metrics.get('untracked_gap', '—')):>4} "
            f"{pct('unsupported_rate'):>12} {pct('hollow_rate'):>7} "
            f"{str(clip.get('wall_s') if clip.get('wall_s') is not None else '—'):>7}"
        )
    overall = report["overall"]
    print(
        f"overall: supported_unboxed={overall['supported_rate_unboxed']} "
        f"supported_boxed={overall['supported_rate_boxed']} echo_suspect={overall['echo_suspect_count']} "
        f"untracked_gap={overall['untracked_gap']} "
        f"unsupported={overall['unsupported_rate']} hollow={overall['hollow_rate']} failed={overall['failed_clips']}"
    )
    print(f"report: {output_dir / 'report.json'}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adapter", choices=ADAPTERS, required=True)
    parser.add_argument(
        "--clips", default="all", help="all or comma-separated clip ids"
    )
    parser.add_argument(
        "--ollama-url", default=os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
    )
    parser.add_argument("--model")
    parser.add_argument(
        "--anchor-mode",
        choices=("first", "all"),
        default="first",
        help="qwen3vl_ollama identity anchors: first image only (default) or every image",
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--report-root", type=Path, default=DEFAULT_REPORT_ROOT)
    parser.add_argument(
        "--run-id", help="stable report directory name for explicit resume"
    )
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument(
        "--num-predict",
        type=int,
        default=MAX_NUM_PREDICT,
        help=f"generation-token cap (maximum {MAX_NUM_PREDICT})",
    )
    parser.add_argument("--repeat-penalty", type=float, default=DEFAULT_REPEAT_PENALTY)
    parser.add_argument(
        "--force", action="store_true", help="overwrite existing per-clip claims files"
    )
    return parser


def main() -> int:
    report, output_dir = run_benchmark(_parser().parse_args())
    print_summary(report, output_dir)
    return 1 if report["overall"]["failed_clips"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
