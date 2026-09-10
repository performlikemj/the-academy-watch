"""Regenerate human evidence ledgers from label-free aggregate execution fixtures."""

from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path

from common import HERE, ROOT, dump
from human_score import markdown

FIXTURE = HERE / "fixtures/human_measurements.json.gz"
EXECUTION = HERE / "fixtures/human_execution.json"
PREFIX = ROOT / "ledgers/research/evidence-bench-2026-09-11-ball-human"


def generate(out_prefix=PREFIX):
    data = json.loads(gzip.decompress(FIXTURE.read_bytes()))
    data["execution"] = json.loads(EXECUTION.read_text())
    round2_path = HERE / "fixtures/round2_execution.json"
    prefix = ""
    if round2_path.exists():
        from round2_protocol import markdown as round2_markdown

        data["round2"] = json.loads(round2_path.read_text())
        data["round1_evaluation_note"] = (
            data["round2"]["evaluation_label"]
            + "; root results retain the historical 16-clip evaluation subset. "
            "Round-2 paired tables rescore every candidate on the same fixed six clips."
        )
        prefix = round2_markdown(data["round2"])
    round2_measurements = HERE / "fixtures/round2_measurements.json.gz"
    if round2_measurements.exists():
        from round2_report import markdown as complete_round2_markdown

        data["round2"]["measurements"] = json.loads(
            gzip.decompress(round2_measurements.read_bytes())
        )
        rendered = complete_round2_markdown(data)
    else:
        rendered = prefix + markdown(data)
    dump(out_prefix.with_suffix(".json"), data)
    out_prefix.with_suffix(".md").write_text(rendered)
    return data


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--capture",
        type=Path,
        help="Freeze aggregate score_from_saved JSON; never accepts JSONL labels",
    )
    p.add_argument("--out-prefix", type=Path, default=PREFIX)
    a = p.parse_args()
    if a.capture:
        data = json.loads(a.capture.read_text())
        if (
            data.get("schema_version") != 1
            or "results" not in data
            or "labels" not in data
        ):
            p.error("expected aggregate human scoring report")

        # No human coordinates, raw label records, or weights in execution fixture.
        def check(value):
            if isinstance(value, dict):
                if {"x", "y"} & value.keys():
                    raise ValueError("coordinates cannot be committed")
                for item in value.values():
                    check(item)
            elif isinstance(value, list):
                for item in value:
                    check(item)

        check(data)
        FIXTURE.write_bytes(
            gzip.compress(
                (json.dumps(data, sort_keys=True, indent=2) + "\n").encode(), mtime=0
            )
        )
    generate(a.out_prefix)


if __name__ == "__main__":
    main()
