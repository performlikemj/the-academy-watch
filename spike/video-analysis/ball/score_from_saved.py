"""Score every saved candidate from MJ's JSONL, without inference or media access."""

from __future__ import annotations
import argparse
import json
from pathlib import Path
from common import DEFAULT_REPORT, HERE, dump
from extra_detections import load_extra
from compare_ball import MEASUREMENTS, compare, load_measurements, markdown


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--human-jsonl", type=Path, required=True)
    p.add_argument("--measurements", type=Path, default=MEASUREMENTS)
    p.add_argument("--out-prefix", type=Path, default=DEFAULT_REPORT / "human-followup")
    p.add_argument(
        "--extra-detections", action="append", default=[], metavar="NAME=PATH"
    )
    a = p.parse_args()
    measurements = load_measurements(a.measurements)
    data = compare(
        measurements,
        json.loads((HERE / "fixtures/execution.json").read_text()),
        a.human_jsonl,
        load_extra(a.extra_detections, measurements),
    )
    dump(a.out_prefix.with_suffix(".json"), data)
    a.out_prefix.with_suffix(".md").write_text(markdown(data))
    for r in data["results"]:
        print(r["candidate"], r["threshold"], r["overall"]["human"])
    print("Wrote", a.out_prefix.with_suffix(".json"), a.out_prefix.with_suffix(".md"))


if __name__ == "__main__":
    main()
