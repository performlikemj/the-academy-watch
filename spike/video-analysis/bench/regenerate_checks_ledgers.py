#!/usr/bin/env python3
"""Regenerate the three current checks ledgers from committed execution inputs."""

import argparse
import json
from pathlib import Path

try:
    from .compare_checks import main as compare_main
except ImportError:  # pragma: no cover
    from compare_checks import main as compare_main


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    for lane in ("lane-b", "lane-b-models", "lane-c-crops"):
        execution = Path(__file__).parent / "fixtures" / f"{lane}-execution.json"
        config = json.loads(execution.read_text())["regeneration"]
        stem = args.output_dir / config["output_stem"]
        command = [
            "--reports-root",
            str(args.reports_root),
            "--manifest",
            str(args.manifest),
            "--execution",
            str(execution),
            "--out-json",
            str(stem.with_suffix(".json")),
            "--out-md",
            str(stem.with_suffix(".md")),
            "--runs",
            *[f"{k}={v}" for k, v in config["runs"].items()],
        ]
        if config["allow_mixed"]:
            command.append("--allow-mixed")
        compare_main(command)
        print(f"Regenerated {stem}.json and .md from saved outputs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
