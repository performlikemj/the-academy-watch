"""Score every saved candidate from MJ's JSONL, without inference or media access."""

from __future__ import annotations
from output_guard import guard_outputs
import argparse
from pathlib import Path
from ball_truth_kit import import_labels
from common import DEFAULT_REPORT, dump, sha256
from extra_detections import load_extra
from compare_ball import MEASUREMENTS, load_measurements
from human_loop import frame_catalog
from human_score import score, markdown
from label_rule import RULES


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
        help="Allow explicitly badged synthetic diagnostics",
    )
    p.add_argument("--label-rule", choices=RULES, default="as_labelled")
    a = p.parse_args()
    guard_outputs(
        a.out_prefix.with_suffix(".json"),
        a.out_prefix.with_suffix(".md"),
        inputs=[
            a.human_jsonl,
            a.measurements,
            *(r.split("=", 1)[-1] for r in a.extra_detections),
        ],
        parser=p,
    )
    measurements = load_measurements(a.measurements)
    try:
        labels = import_labels(a.human_jsonl, frame_catalog(measurements))
        extras = load_extra(
            a.extra_detections, measurements, allow_synthetic=a.allow_synthetic
        )
    except ValueError as error:
        p.error(str(error))
    data = score(measurements, labels, extras, a.label_rule)
    data["labels"]["sha256"] = sha256(a.human_jsonl)
    dump(a.out_prefix.with_suffix(".json"), data)
    a.out_prefix.with_suffix(".md").write_text(markdown(data))
    print(data["match_ball_note"])
    if data["provisional"]:
        print(data["provisional"])
    for r in data["results"]:
        name = r["candidate"] + (" [SYNTHETIC]" if r["synthetic_smoke"] else "")
        print(
            name,
            r["gate"],
            r["headline_scope"],
            (r["held_out_groups"] or r["groups"])["on_ball"],
            "no-ball",
            (r["held_out_groups"] or r["groups"])["all"]["false_per_10s"],
        )
    print("Wrote", a.out_prefix.with_suffix(".json"), a.out_prefix.with_suffix(".md"))


if __name__ == "__main__":
    main()
