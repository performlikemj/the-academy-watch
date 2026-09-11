"""Aggregate-only fair-protocol capture from fresh saved low-confidence passes."""

from __future__ import annotations
import argparse
import gzip
import json
from pathlib import Path
from ball_truth_kit import import_labels
from common import HERE, dump, sha256
from compare_ball import load_measurements
from extra_detections import load_extra
from fair_protocol import evaluate, hits, mcnemar
from human_loop import frame_catalog
from metrics import clip_class
from review_round3 import freeze
from checkpoint_provenance import FINAL_PASSES, validate_saved_passes
from output_guard import guard_outputs
from label_rule import RULES, rule_metadata


def capture(paths, root=None, label_path=None, label_rule="as_labelled"):
    validate_saved_passes(paths, root)
    m = load_measurements()
    label_path = label_path or Path.home() / "codex-runs/ball-human-truth.jsonl"
    labels = import_labels(label_path, frame_catalog(m))
    protocol = json.loads((HERE / "fixtures/round5_execution.json").read_text())
    split = protocol["split"]
    extras = load_extra([f"{k}={v}" for k, v in paths.items()], m)
    if any(payload["threshold"] != 0.01 for payload in extras.values()):
        raise ValueError(
            "fair protocol requires fresh passes saved down to confidence 0.01"
        )
    # load_extra stores a validated envelope; see its public schema.
    outputs = {k: extras[k]["outputs"] for k in paths}
    rows = {k: evaluate(m, labels, v, split) for k, v in outputs.items()}
    on = {c["clip_id"] for c in m["clips"] if clip_class(c) == "on_ball"} & set(
        split["held_out"]
    )
    baseline = "yolo-r2-b"
    for name, row in rows.items():
        for budget, op in row["operating_points"].items():
            base = rows[baseline]["operating_points"][budget]
            op["mcnemar_vs_yolo"] = mcnemar(
                hits(outputs[name], labels, on, op["threshold"]),
                hits(outputs[baseline], labels, on, base["threshold"]),
            )
        row["fixed_0.1_mcnemar"] = mcnemar(
            hits(outputs[name], labels, on, 0.1),
            hits(outputs[baseline], labels, on, 0.1),
        )
        row["detections_sha256"] = sha256(paths[name])
        row["inference_timing_note"] = (
            "Accuracy-capture wall times are incidental, not controlled throughput; "
            "use the separate interleaved benchmark. Unrelated GPU work was observed "
            "during new-model accuracy capture."
        )
        row["saved_pass_provenance"] = {
            k: extras[name][k]
            for k in (
                "weights_sha256",
                "source_sha256",
                "training_labels_sha256",
                "threshold",
                "licence",
            )
        }
    return {
        **rule_metadata(labels, label_rule),
        "evaluation_label": protocol["evaluation_label"],
        "models": rows,
        "best_rf_final_selected": select_rf(rows),
        "labels_sha256": sha256(label_path),
        "protocol": protocol,
        "selection_rule": protocol["protocol"]["config"]["model_selection"],
    }


def select_rf(rows, only_new=False):
    names = [
        n for n in rows if n != "yolo-r2-b" and (not only_new or n.startswith("rf-r5-"))
    ]

    def values(name):
        g = rows[name]["operating_points"]["1"]["held"]["groups"]
        return g["on_ball"]["top1_recall"], g["all"]["false_per_10s"]

    eligible = [n for n in names if values(n)[1] <= 2]
    if eligible:
        return min(eligible, key=lambda n: (-values(n)[0], values(n)[1], n))
    return min(names, key=lambda n: (values(n)[1], -values(n)[0], n))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--extra", action="append", default=[])
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--freeze", action="store_true")
    p.add_argument("--human-jsonl", type=Path)
    p.add_argument("--label-rule", choices=RULES, default="as_labelled")
    a = p.parse_args()
    if a.freeze and a.label_rule == "any_ball":
        p.error("rule-A machinery cannot replace the committed historical fixtures")
    label_path = a.human_jsonl or Path.home() / "codex-runs/ball-human-truth.jsonl"
    guard_outputs(
        a.out,
        inputs=[label_path, *(raw.split("=", 1)[-1] for raw in a.extra)],
        parser=p,
    )
    fixture = HERE / "fixtures/round5_scored_output.json.gz"
    if a.freeze:
        with gzip.open(fixture, "rt") as stream:
            historical = json.load(stream)
        historical_hash = historical["labels_sha256"]
        if sha256(label_path) != historical_hash:
            p.error(
                "--freeze requires the historical label file identity; fixture unchanged"
            )
    root = Path.home() / "models/tinyball"
    paths = {
        "yolo-r2-b": root / "r5-yolo-low/detections.json",
        "rf-b": root / "r5-rfb-low/detections.json",
    }
    if a.freeze:
        if a.extra:
            p.error("--freeze forbids --extra; use the recorded model set")
        paths = {
            name: root / folder / "detections.json"
            for name, folder in FINAL_PASSES.items()
        }
        if set(paths) != set(historical["models"]):
            p.error("--freeze requires exactly the recorded model set")
        try:
            if any(
                sha256(path) != historical["models"][name]["detections_sha256"]
                for name, path in paths.items()
            ):
                p.error(
                    "--freeze detection-file identity differs from the recorded fixture"
                )
        except OSError as error:
            p.error(f"cannot verify recorded detections: {error}")
    for raw in a.extra:
        name, path = raw.split("=", 1)
        paths[name] = Path(path)
    result = capture(paths, label_path=label_path, label_rule=a.label_rule)
    if a.freeze and (
        result["labels_sha256"] != historical_hash
        or sha256(label_path) != historical_hash
    ):
        p.error("label identity changed during capture; fixture unchanged")
    if result["provisional"]:
        print(result["provisional"])
    if a.freeze:
        if set(result["models"]) != set(paths) or any(
            result["models"][name]["detections_sha256"]
            != historical["models"][name]["detections_sha256"]
            or sha256(path) != historical["models"][name]["detections_sha256"]
            for name, path in paths.items()
        ):
            p.error("recorded detection identity changed during capture")
    guard_outputs(a.out, inputs=[label_path, *paths.values()], parser=p)
    if a.freeze:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        freeze(a.out, result)
    else:
        dump(a.out, result)
    for name, row in result["models"].items():
        for budget, op in row["operating_points"].items():
            print(
                name,
                budget,
                op["threshold"],
                [
                    (
                        s,
                        op[s]["groups"]["on_ball"]["top1_recall"],
                        op[s]["groups"]["all"]["false_per_10s"],
                    )
                    for s in ("train", "held")
                ],
                op["mcnemar_vs_yolo"],
            )


if __name__ == "__main__":
    main()
