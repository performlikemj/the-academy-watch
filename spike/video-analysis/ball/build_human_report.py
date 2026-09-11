"""Regenerate human evidence ledgers from label-free aggregate execution fixtures."""

from __future__ import annotations

from output_guard import guard_outputs
import argparse
import gzip
import json
from pathlib import Path

from common import HERE, ROOT, dump
from human_score import markdown

FIXTURE = HERE / "fixtures/human_measurements.json.gz"
EXECUTION = HERE / "fixtures/human_execution.json"
PREFIX = ROOT / "ledgers/research/evidence-bench-2026-09-11-ball-human"


def generate(out_prefix=PREFIX, fixtures=None, capture=None):
    fixtures = Path(fixtures) if fixtures is not None else HERE / "fixtures"
    data = json.loads(
        gzip.decompress(
            (
                Path(capture)
                if capture is not None
                else fixtures / "human_measurements.json.gz"
            ).read_bytes()
        )
    )
    data["execution"] = json.loads((fixtures / "human_execution.json").read_text())
    round2_path = fixtures / "round2_execution.json"
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
    round2_measurements = fixtures / "round2_measurements.json.gz"
    if round2_measurements.exists():
        from round2_report import markdown as complete_round2_markdown

        data["round2"]["measurements"] = json.loads(
            gzip.decompress(round2_measurements.read_bytes())
        )
        rendered = complete_round2_markdown(data)
    else:
        rendered = prefix + markdown(data)
    round3_path = fixtures / "round3_execution.json"
    round3_scored = fixtures / "round3_scored_output.json.gz"
    if round3_path.exists() and round3_scored.exists():
        from round3_report import markdown as round3_markdown

        data["round3"] = json.loads(round3_path.read_text())
        data["round3"]["measurements"] = json.loads(
            gzip.decompress(round3_scored.read_bytes())
        )
        rendered = round3_markdown(data)
    round4_path = fixtures / "round4_execution.json"
    round4_scored = fixtures / "round4_scored_output.json.gz"
    if round4_path.exists() and round4_scored.exists():
        from round4_report import markdown as round4_markdown

        data["round4"] = json.loads(round4_path.read_text())
        data["round4"]["measurements"] = json.loads(
            gzip.decompress(round4_scored.read_bytes())
        )
        rendered = round4_markdown(data, rendered)
    round5_path = fixtures / "round5_execution.json"
    round5_scored = fixtures / "round5_scored_output.json.gz"
    if round5_path.exists() and round5_scored.exists():
        from round5_report import markdown as round5_markdown, relabel

        data["round5"] = json.loads(round5_path.read_text())
        data["round5"]["measurements"] = json.loads(
            gzip.decompress(round5_scored.read_bytes())
        )
        data = relabel(data)
        rendered = round5_markdown(data, rendered)
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
    p.add_argument(
        "--fixtures",
        type=Path,
        help="Read aggregate fixtures from a completed fresh bundle",
    )
    p.add_argument("--capture-out", type=Path, help="New gzip artifact for --capture")
    a = p.parse_args()
    if (a.capture is not None) != (a.capture_out is not None):
        p.error("--capture requires --capture-out (a new file)")
    guard_outputs(
        a.out_prefix.with_suffix(".json"),
        a.out_prefix.with_suffix(".md"),
        a.capture_out,
        inputs=[a.capture],
        parser=p,
    )
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
        a.capture_out.parent.mkdir(parents=True, exist_ok=True)
        a.capture_out.write_bytes(
            gzip.compress(
                (json.dumps(data, sort_keys=True, indent=2) + "\n").encode(), mtime=0
            )
        )
    generate(a.out_prefix, a.fixtures, a.capture_out)


if __name__ == "__main__":
    main()
