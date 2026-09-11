"""Freeze executed aggregate evidence and regenerate both ledgers without labels."""

from __future__ import annotations
from output_guard import guard_outputs
import argparse
import shutil
import json
from pathlib import Path
from build_human_report import generate
from common import HERE, dump, sha256
from review_round3 import freeze
from round5_framing import enrich


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out", type=Path, required=True, help="Fresh aggregate bundle directory"
    )
    args = parser.parse_args()
    guard_outputs(
        args.out,
        inputs=[Path.home() / "models/tinyball", HERE / "fixtures"],
        parser=parser,
    )
    root = Path.home() / "models/tinyball"
    logs = Path.home() / "codex-runs"
    e = json.loads((root / "round5-evidence.json").read_text())
    e["throughput"] = json.loads((root / "round5-throughput.json").read_text())
    build = json.loads((Path.home() / "ball-truth-review/build.json").read_text())
    if build["build_version"] != 8 or build["confirmed_seed_labels"] != 1057:
        raise ValueError("round5 kit not refreshed preserving labels")
    if build["suggestions_by_source"] != {e["kit"]["source"]: e["kit"]["suggestions"]}:
        raise ValueError("kit source differs from selected RF")
    e["kit"].update(
        build={
            k: build[k]
            for k in (
                "build_version",
                "clips",
                "confirmed_seed_labels",
                "fps",
                "frames",
                "frozen_set_id",
                "suggestions",
                "suggestions_by_source",
            )
        },
        index_sha256=sha256(Path.home() / "ball-truth-review/index.html"),
        browser_verification=(logs / "ball-r5-kit-check.log").read_text().strip(),
    )
    protocol_path = HERE / "fixtures/round5_execution.json"
    p = json.loads(protocol_path.read_text())
    p["status"] = (
        "Executed: both predeclared fits, final/checkpoint fair scoring, controlled throughput and RF-only kit refresh complete"
    )
    p["scoring_code_sha256"] = {
        name: sha256(HERE / name)
        for name in (
            "fair_protocol.py",
            "checkpoint_provenance.py",
            "review_round5.py",
            "finish_round5.py",
            "round5_inference.py",
            "throughput_round5.py",
            "benchmark_activity.py",
            "run_round5.py",
        )
    }
    p["private_artifacts"] = {
        "models": "~/models/tinyball/mj-r5-rf-{a,b}",
        "low_confidence_passes": "~/models/tinyball/r5-*-low/detections.json",
        "n21_crops": "~/codex-runs/ball-r5-n21/",
        "kit": "~/ball-truth-review/",
        "suggestions": "~/codex-runs/ball-human-round5-suggestions.jsonl",
    }
    e["protocol"] = p
    args.out.mkdir(parents=True)
    for source in (HERE / "fixtures").iterdir():
        if source.is_file() and source.suffix in {".json", ".gz"}:
            shutil.copyfile(source, args.out / source.name)
    dump(args.out / "round5_execution.json", p)
    if p.get("framing_review"):
        e = enrich(e)
    freeze(args.out / "round5_scored_output.json.gz", e)
    generate(args.out / "human", fixtures=args.out)
    print("Wrote fresh aggregate bundle and regenerated JSON and Markdown")


if __name__ == "__main__":
    main()
