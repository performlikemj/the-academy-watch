"""Aggregate-only fair-protocol capture from fresh saved low-confidence passes."""

from __future__ import annotations
import argparse
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


def capture(paths):
    m = load_measurements()
    label_path = Path.home() / "codex-runs/ball-human-truth.jsonl"
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
    a = p.parse_args()
    root = Path.home() / "models/tinyball"
    paths = {
        "yolo-r2-b": root / "r5-yolo-low/detections.json",
        "rf-b": root / "r5-rfb-low/detections.json",
    }
    for raw in a.extra:
        name, path = raw.split("=", 1)
        paths[name] = Path(path)
    result = capture(paths)
    dump(a.out, result)
    if a.freeze:
        freeze(HERE / "fixtures/round5_scored_output.json.gz", result)
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
