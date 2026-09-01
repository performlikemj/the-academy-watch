#!/usr/bin/env python3
"""Run one Film Room adapter sequentially and write a resumable scored report."""

from __future__ import annotations

import argparse
import importlib
import json
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


def _run_metadata(
    adapter: str, model: str | None, clips: list[str], anchor_mode: str
) -> dict:
    return {
        "adapter": adapter,
        "model": model,
        "clips": clips,
        "anchor_mode": anchor_mode if adapter == "qwen3vl_ollama" else None,
    }


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
            if _load_json(run_path) == metadata:
                return directory
        except (OSError, ValueError):
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


def _write_run_metadata(output_dir: Path, metadata: dict) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    run_path = output_dir / "run.json"
    if run_path.is_file() and _load_json(run_path) != metadata:
        raise ValueError(
            f"run metadata mismatch in {output_dir}; choose a new --run-id instead of mixing anchor modes"
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
    metadata = _run_metadata(args.adapter, args.model, selected_ids, args.anchor_mode)
    output_dir = _output_dir(args, metadata)
    _write_run_metadata(output_dir, metadata)
    claims_dir = output_dir / "claims"
    claims_dir.mkdir(parents=True, exist_ok=True)

    adapter = _adapter_module(args.adapter)
    cfg = {
        "ollama_url": args.ollama_url,
        "model": args.model,
        "timeout_s": args.timeout,
        "anchor_mode": args.anchor_mode,
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
        "\nclip_id                                      status    claims  unboxed  boxed  echo  unsupported  hollow  wall_s"
    )
    print("-" * 117)
    for clip in report["clips"]:
        metrics = clip.get("metrics") or {}

        def pct(key: str) -> str:
            value = metrics.get(key)
            return "—" if value is None else f"{value * 100:.1f}%"

        print(
            f"{str(clip['clip_id']):44} {clip['status']:9} {str(metrics.get('claim_count', '—')):>6} "
            f"{pct('supported_rate_unboxed'):>7} {pct('supported_rate_boxed'):>6} "
            f"{str(metrics.get('echo_suspect_count', '—')):>5} "
            f"{pct('unsupported_rate'):>12} {pct('hollow_rate'):>7} "
            f"{str(clip.get('wall_s') if clip.get('wall_s') is not None else '—'):>7}"
        )
    overall = report["overall"]
    print(
        f"overall: supported_unboxed={overall['supported_rate_unboxed']} "
        f"supported_boxed={overall['supported_rate_boxed']} echo_suspect={overall['echo_suspect_count']} "
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
        "--force", action="store_true", help="overwrite existing per-clip claims files"
    )
    return parser


def main() -> int:
    report, output_dir = run_benchmark(_parser().parse_args())
    print_summary(report, output_dir)
    return 1 if report["overall"]["failed_clips"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
