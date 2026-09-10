"""Saved RF-DETR/YOLO head-to-head; aggregate-only trainer-swap fixture."""

from __future__ import annotations

import gzip
import json
import math
import statistics
from pathlib import Path

from ball_truth_kit import import_labels
from common import HERE, dump, sha256
from compare_ball import load_measurements
from extra_detections import load_extra
from human_loop import frame_catalog
from matching_controls import controls
from metrics import clip_class
from rfdetr_data import scale_side
from review_round3 import freeze, path_sensitivity
from round2_analysis import (
    error_records,
    error_summary,
    independent_sizes,
    paired_score,
)


def select_rf(results):
    eligible = [
        r
        for r in results
        if r["candidate"].startswith("tinyball-r4-rf-")
        and r["held"]["groups"]["all"]["false_per_10s"] is not None
        and r["held"]["groups"]["all"]["false_per_10s"] <= 2
        and r["held"]["groups"]["on_ball"]["top1_recall"] is not None
    ]
    return (
        min(
            eligible,
            key=lambda r: (
                -r["held"]["groups"]["on_ball"]["top1_recall"],
                r["held"]["groups"]["all"]["false_per_10s"],
                r["candidate"],
            ),
        )["candidate"]
        if eligible
        else None
    )


def beats_bar(row, bar):
    r, b = row["held"]["groups"], bar["held"]["groups"]
    return (
        r["on_ball"]["top1_recall"] > b["on_ball"]["top1_recall"]
        and r["all"]["false_per_10s"] <= b["all"]["false_per_10s"]
    )


def errors_top1(m, labels, outputs, people, split):
    records = error_records(m, labels, outputs, people)
    keys = [
        (c["clip_id"], r["t"])
        for c in m["clips"]
        if clip_class(c) == "on_ball"
        for r in outputs[c["clip_id"]]["frames"]
        if labels.get((c["clip_id"], r["t"]), {}).get("visible")
    ]
    tops = {
        (cid, r["t"]): max(
            [d for d in r["detections"] if d["confidence"] >= 0.1],
            key=lambda d: d["confidence"],
            default=None,
        )
        for cid, output in outputs.items()
        for r in output["frames"]
    }

    if len(keys) != len(records):
        raise ValueError("error and label schedules disagree")
    top_records = []
    for key, record in zip(keys, records):
        label, top = labels[key], tops[key]
        top_records.append(
            {
                **record,
                "hit": bool(
                    top and math.dist(top["xy"], [label["x"], label["y"]]) <= 20
                ),
            }
        )
    return {
        rule: {
            scope: error_summary(
                [r for r in rows if scope == "all" or r["clip"] in split["held_out"]]
            )
            for scope in ("all", "held")
        }
        for rule, rows in (("oracle", records), ("top1", top_records))
    }


def large_scale_diagnostic(m, labels, fit, split):
    sizes = independent_sizes(m, labels)
    on = {c["clip_id"] for c in m["clips"] if clip_class(c) == "on_ball"}
    result: dict[str, object] = {
        "definition": "Post-fit diagnostic only. Independent observed short sides >=24px on on-ball labels versus the frozen TRAIN affine-plus-floor rule. H labels do not alter fitting or become training targets."
    }
    for scope, cids in (
        ("all", on),
        ("held", set(split["held_out"])),
        ("train", set(split["train"])),
    ):
        keys = [k for k, size in sizes.items() if k[0] in on & cids and size >= 24]
        targets = [scale_side(labels[k], fit, fit["clip_px"][0]) for k in keys]
        result[scope] = {
            "observed_large": len(keys),
            "rule_ge24": sum(s >= 24 for s in targets),
            "rule_median_px": statistics.median(targets) if targets else None,
            "observed_median_px": statistics.median([sizes[k] for k in keys])
            if keys
            else None,
        }
    return result


def capture(root, human_jsonl):
    protocol = json.loads((HERE / "fixtures/round4_execution.json").read_text())
    historical = json.loads(
        gzip.decompress((HERE / "fixtures/round3_scored_output.json.gz").read_bytes())
    )
    split = protocol["split"]
    m = load_measurements()
    labels = import_labels(human_jsonl, frame_catalog(m))
    model_dirs = {
        "tinyball-r2-b": "mj-r2-b",
        "tinyball-r3-a": "mj-r3-a",
        "tinyball-r3-b": "mj-r3-b",
        **{f"tinyball-r4-rf-{c}": f"mj-r4-rf-{c}" for c in "ab"},
    }
    extras = load_extra(
        [
            f"{name}={root / directory / 'detections.json'}"
            for name, directory in model_dirs.items()
        ],
        m,
    )
    state_path = root / "round4-fit-state.json"
    state = json.loads(state_path.read_text())
    marker = json.loads((root / "round4-evaluation-start.json").read_text())
    if set(state["fits"]) != set("ab") or marker["fit_state_sha256"] != sha256(
        state_path
    ):
        raise ValueError("two-fit snapshot changed after evaluation")
    for c, fit in state["fits"].items():
        if fit != json.loads((root / f"mj-r4-rf-{c}/fit_summary.json").read_text()):
            raise ValueError("fit history changed")
    for name, digest in protocol["training_code_sha256"].items():
        if sha256(HERE / name) != digest:
            raise ValueError("training code changed")
    people_path = root / "round2-people.json"
    if sha256(people_path) != historical["people_sha256"]:
        raise ValueError("person proxy changed")
    people = json.loads(people_path.read_text())
    results, errors, sensitivity = [], {}, {}
    for name, saved in extras.items():
        directory = root / model_dirs[name]
        if (
            saved["training_labels_sha256"] != sha256(human_jsonl)
            or saved["training_split"] != split
            or saved["weights_sha256"] != sha256(directory / "weights.pt")
        ):
            raise ValueError(f"saved pass provenance mismatch {name}")
        row = paired_score(m, labels, name, saved["outputs"], split)
        row["all"]["evaluation_label"] = "all clips (incl. training clips)"
        row["held"]["evaluation_label"] = protocol["evaluation_label"]
        results.append(row)
        errors[name] = errors_top1(m, labels, saved["outputs"], people, split)
        sensitivity[name] = path_sensitivity(saved["outputs"], labels, split)
        if name in historical["errors"]:
            old = next(r for r in historical["results"] if r["candidate"] == name)
            if row != old or errors[name] != historical["errors"][name]:
                raise ValueError(
                    "historical YOLO score changed; use Python3.11 for exact track math"
                )
        else:
            fit = state["fits"][name[-1]]
            dump(
                directory / "metrics.json",
                {
                    "status": "complete",
                    "licence": fit["licence"],
                    "licence_url": fit["licence_url"],
                    "fit": fit,
                    "scores": row,
                    "errors": errors[name],
                    "path_sensitivity": sensitivity[name],
                },
            )
        print(f"RF head-to-head scored {name}", flush=True)
    selected = select_rf(results)
    rf = [r for r in results if r["candidate"].startswith("tinyball-r4-rf-")]
    leader = max(rf, key=lambda r: r["held"]["groups"]["on_ball"]["top1_recall"])[
        "candidate"
    ]
    bar = next(r for r in results if r["candidate"] == "tinyball-r2-b")
    e = {
        "schema_version": 1,
        "results": results,
        "large_scale_diagnostic": large_scale_diagnostic(
            m,
            labels,
            json.loads((root / "mj-r4-rf-b/dataset.json").read_text())["box_recipe"],
            split,
        ),
        "errors": errors,
        "controls": controls(
            m,
            labels,
            {
                name: saved["outputs"]
                for name, saved in extras.items()
                if name.startswith("tinyball-r4-rf-")
            },
            split,
        ),
        "path_sensitivity": sensitivity,
        "current_best_licence_clean": selected,
        "diagnostic_recall_leader": leader,
        "improvements_over_r2_b": [r["candidate"] for r in rf if beats_bar(r, bar)],
        "fits": state["fits"],
        "fit_state_sha256": sha256(state_path),
        "evaluation_start": marker,
        "labels_sha256": sha256(human_jsonl),
        "people_sha256": sha256(people_path),
        "datasets": {
            c: json.loads((root / f"mj-r4-rf-{c}/dataset.json").read_text())
            for c in "ab"
        },
        "run_files": {
            c: {
                name: sha256(root / f"mj-r4-rf-{c}" / name)
                for name in (
                    "dataset/annotations.json",
                    "dataset.json",
                    "train_history.json",
                    "fit_summary.json",
                    "suggestions.jsonl",
                )
            }
            for c in "ab"
        },
        "saved_passes": {
            name: {
                "sha256": sha256(root / directory / "detections.json"),
                "weights_sha256": extras[name]["weights_sha256"],
                "frames": sum(
                    len(o["frames"]) for o in extras[name]["outputs"].values()
                ),
            }
            for name, directory in model_dirs.items()
        },
    }
    freeze(HERE / "fixtures/round4_scored_output.json.gz", e)
    dump(root / "round4-evidence.json", e)
    return e


if __name__ == "__main__":
    capture(
        Path.home() / "models/tinyball",
        Path.home() / "codex-runs/ball-human-truth.jsonl",
    )
