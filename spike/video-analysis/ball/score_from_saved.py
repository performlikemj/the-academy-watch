"""Score every saved candidate from MJ's JSONL, without inference or media access."""

from __future__ import annotations
import argparse
import json
from pathlib import Path
from common import DEFAULT_REPORT, HERE, dump
from extra_detections import load_extra
from compare_ball import (
    MEASUREMENTS,
    candidate_label,
    compare,
    load_measurements,
    markdown,
)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--human-jsonl", type=Path, required=True)
    p.add_argument("--measurements", type=Path, default=MEASUREMENTS)
    p.add_argument("--out-prefix", type=Path, default=DEFAULT_REPORT / "human-followup")
    p.add_argument(
        "--extra-detections", action="append", default=[], metavar="NAME=PATH"
    )
    p.add_argument(
        "--allow-synthetic",
        action="store_true",
        help="Allow synthetic extras, badged SYNTHETIC in every result row",
    )
    a = p.parse_args()
    measurements = load_measurements(a.measurements)
    try:
        extras = load_extra(
            a.extra_detections, measurements, allow_synthetic=a.allow_synthetic
        )
    except ValueError as error:
        p.error(str(error))
    data = compare(
        measurements,
        json.loads((HERE / "fixtures/execution.json").read_text()),
        a.human_jsonl,
        extras,
    )
    dump(a.out_prefix.with_suffix(".json"), data)
    a.out_prefix.with_suffix(".md").write_text(markdown(data))
    for r in data["results"]:
        print(candidate_label(r), r["threshold"], r["overall"]["human"])
    print("Wrote", a.out_prefix.with_suffix(".json"), a.out_prefix.with_suffix(".md"))


if __name__ == "__main__":
    main()
