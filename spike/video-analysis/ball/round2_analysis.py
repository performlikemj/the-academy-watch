"""Paired all/held-out evidence and predeclared error buckets from saved predictions."""

from __future__ import annotations
import argparse
import gzip
import json
import math
import statistics
from pathlib import Path
from typing import Any
from ball_truth_kit import import_labels
from common import HERE, dump, sha256
from compare_ball import load_measurements
from extra_detections import load_extra
from human_loop import frame_catalog
from human_score import score_candidate
from metrics import clip_class, ratio


def gate(groups):
    recall, false = groups["on_ball"]["recall"], groups["all"]["false_per_10s"]
    if recall is None or false is None:
        return "UNMEASURABLE"
    return "PASS" if recall >= 0.8 and false <= 1 else "FAIL"


def paired_score(measurements, labels, name, outputs, split):
    result = {"candidate": name}
    for scope, selected in (
        ("all", labels),
        ("held", {k: v for k, v in labels.items() if k[0] in split["held_out"]}),
    ):
        scored = score_candidate(measurements, selected, name, outputs)
        cids = set(outputs) if scope == "all" else set(split["held_out"])
        result[scope] = {k: scored[k] for k in ("groups", "tracks", "provenance_bias")}
        result[scope]["gate"] = gate(scored["groups"])
        result[scope]["fps"] = sum(len(outputs[c]["frames"]) for c in cids) / sum(
            outputs[c]["wall_s"] for c in cids
        )
    return result


def bucket(value, bounds):
    return next((i for i, limit in enumerate(bounds) if value < limit), len(bounds))


def independent_sizes(measurements, labels):
    sizes: dict[tuple[str, float], list[float]] = {}
    for name in ("rf_full", "rf_2x2", "rf_3x3"):
        for cid, output in measurements["outputs"][name].items():
            for row in output["frames"]:
                key = (cid, row["t"])
                label = labels.get(key)
                if not label or not label["visible"]:
                    continue
                ds = [
                    d
                    for d in row["detections"]
                    if d["confidence"] >= 0.1
                    and d.get("size_px") is not None
                    and d.get("box") is not None
                ]
                nearest = min(
                    ds,
                    key=lambda d: math.dist(d["xy"], [label["x"], label["y"]]),
                    default=None,
                )
                if nearest and math.dist(nearest["xy"], [label["x"], label["y"]]) <= 20:
                    sizes.setdefault(key, []).append(nearest["size_px"])
    return {key: statistics.median(values) for key, values in sizes.items()}


def error_records(measurements, labels, outputs, people):
    sizes = independent_sizes(measurements, labels)
    person_rows = {
        (cid, r["t"]): r["boxes"]
        for cid, rows in people["outputs"].items()
        for r in rows
    }
    records = []
    for clip in measurements["clips"]:
        if clip_class(clip) != "on_ball":
            continue
        cid = clip["clip_id"]
        previous = None
        for row in outputs[cid]["frames"]:
            key = (cid, row["t"])
            label = labels.get(key)
            if label and label["visible"]:
                point = [label["x"], label["y"]]
                hit = any(
                    d["confidence"] >= 0.1 and math.dist(d["xy"], point) <= 20
                    for d in row["detections"]
                )
                movement = (
                    math.dist(point, [previous["x"], previous["y"]])
                    if previous and previous["visible"]
                    else None
                )
                size = sizes.get(key)
                records.append(
                    {
                        "clip": cid,
                        "hit": hit,
                        "size": size,
                        "size_bucket": "unknown"
                        if size is None
                        else str(bucket(size, [6, 10, 16, 24])),
                        "image_y": str(bucket(label["y"], [360, 720])),
                        "motion": "unknown"
                        if movement is None
                        else str(bucket(movement, [10, 50])),
                        "player_overlap": "unknown"
                        if key not in person_rows
                        else "inside"
                        if any(
                            a <= point[0] <= c and b <= point[1] <= d
                            for a, b, c, d in person_rows[key]
                        )
                        else "outside",
                    }
                )
            previous = label
    return records


def error_summary(records):
    definitions = {
        "size_bucket": ["0", "1", "2", "3", "4", "unknown"],
        "image_y": ["0", "1", "2"],
        "motion": ["0", "1", "2", "unknown"],
        "player_overlap": ["inside", "outside", "unknown"],
    }
    groups: dict[str, Any] = {}
    for kind, categories in definitions.items():
        groups[kind] = {}
        for category in categories:
            selected = [r for r in records if r[kind] == category]
            hits = sum(r["hit"] for r in selected)
            groups[kind][category] = {
                "visible": len(selected),
                "matched": hits,
                "misses": len(selected) - hits,
                "recall": ratio(hits, len(selected)),
            }
    supported = 0
    expected = 0.0
    for row in records:
        target = (
            str(bucket(row["size"] * 2, [6, 10, 16, 24]))
            if row["size"] is not None
            else None
        )
        empirical = groups["size_bucket"].get(target, {}).get("recall")
        if empirical is None:
            expected += row["hit"]
        else:
            supported += 1
            expected += empirical
    return {
        "visible": len(records),
        "misses": sum(not r["hit"] for r in records),
        "buckets": groups,
        "double_size_projection": {
            "observed_recall": ratio(sum(r["hit"] for r in records), len(records)),
            "projected_recall": ratio(expected, len(records)),
            "supported_frames": supported,
            "unchanged_unknown_or_unsupported": len(records) - supported,
            "expected_matches": expected,
            "definition": "Associational extrapolation: each measured size moves to its doubled-size bucket and takes that bucket measured recall. Unknown size/unsupported bucket keeps observed outcome. No causal adjustment, no claim of measured 4K performance; sparse buckets and RF selection bias limit reliability.",
        },
    }


def capture(root, human_jsonl):
    m = load_measurements()
    labels = import_labels(human_jsonl, frame_catalog(m))
    selection = json.loads((root / "round2-selection.json").read_text())
    execution = json.loads((HERE / "fixtures/round2_execution.json").read_text())
    split = execution["split"]
    label_hash = sha256(human_jsonl)
    if any(
        fit["labels_sha256"] != label_hash or fit["split"] != split
        for fit in selection["fits"].values()
    ):
        raise ValueError("fitting/evaluation label hash or split changed")
    marker = json.loads((root / "round2-evaluation-start.json").read_text())
    if marker["selection_sha256"] != sha256(root / "round2-selection.json"):
        raise ValueError("selection changed after evaluation began")
    specs = [
        f"tinyball-r1={root / 'mj-r1/detections.json'}",
        f"tinyball-r1-960={root / 'mj-r1-960/detections.json'}",
    ] + [
        f"tinyball-r2-{letter}={root / f'mj-r2-{letter}/detections.json'}"
        for letter in "abcd"
    ]
    extras = load_extra(specs, m)
    for letter, fit in selection["fits"].items():
        extra = extras[f"tinyball-r2-{letter}"]
        if (
            extra["training_labels_sha256"] != label_hash
            or extra["training_split"] != split
            or extra["weights_sha256"] != fit["weights_sha256"]
        ):
            raise ValueError("saved pass does not match the frozen fit")
    candidates = {
        name: output
        for name, output in m["outputs"].items()
        if name in ("rf_full", "rf_2x2", "rf_3x3", "wasb", "wasb_2x2")
    }
    candidates.update({name: d["outputs"] for name, d in extras.items()})
    results = []
    for name, outputs in candidates.items():
        paired = paired_score(m, labels, name, outputs, split)
        paired["all"]["evaluation_label"] = "all clips (includes training clips)"
        paired["held"]["evaluation_label"] = execution["evaluation_label"]
        results.append(paired)
        if name.startswith("tinyball-r2-"):
            letter = name.removeprefix("tinyball-r2-")
            dump(
                root / f"mj-r2-{letter}/metrics.json",
                {**paired, "fit": selection["fits"][letter]},
            )
        print(f"scored {name}", flush=True)
    selected_name = f"tinyball-r2-{selection['selected']}"
    people = json.loads((root / "round2-people.json").read_text())
    expected = m["outputs"]["rf_full"]
    if (
        people["source_sha256"] != m["runs"]["rf_full"]["source_sha256"]
        or set(people["outputs"]) != set(expected)
        or any(
            [r["t"] for r in people["outputs"][cid]]
            != [r["t"] for r in output["frames"]]
            for cid, output in expected.items()
        )
    ):
        raise ValueError("person proxy source/schedule mismatch")
    records = error_records(m, labels, candidates[selected_name], people)
    evidence = {
        "schema_version": 1,
        "status": "all four saved passes and paired scoring complete; selection snapshot was frozen before evaluation",
        "evaluation_label": execution["evaluation_label"],
        "results": results,
        "selected_model": selected_name,
        "selection": selection,
        "selection_sha256": sha256(root / "round2-selection.json"),
        "label_sha256": sha256(human_jsonl),
        "people_sha256": sha256(root / "round2-people.json"),
        "people_recipe": people["recipe"],
        "datasets": {
            letter: json.loads((root / f"mj-r2-{letter}/dataset.json").read_text())
            for letter in "abcd"
        },
        "run_files": {
            letter: {
                "fit_args_sha256": sha256(root / f"mj-r2-{letter}/fit/args.yaml"),
                "results_csv_sha256": sha256(root / f"mj-r2-{letter}/fit/results.csv"),
                "log_sha256": sha256(
                    Path.home() / f"codex-runs/ball-mj-r2-{letter}.log"
                ),
            }
            for letter in "abcd"
        },
        "errors": {
            "all": error_summary(records),
            "held": error_summary(
                [r for r in records if r["clip"] in split["held_out"]]
            ),
        },
        "files": {
            name: {
                "detections_sha256": sha256(Path(spec.partition("=")[2])),
                "weights_sha256": extras[name]["weights_sha256"],
            }
            for name, spec in zip(extras, specs)
        },
    }
    dump(root / "round2-evidence.json", evidence)
    payload = json.dumps(evidence, sort_keys=True, indent=2, allow_nan=False) + "\n"
    # No human coordinates or individual human records in the committed fixture.
    if '"x":' in payload or '"y":' in payload or '"hit":' in payload:
        raise ValueError("raw labels/coordinates cannot be committed")
    (HERE / "fixtures/round2_measurements.json.gz").write_bytes(
        gzip.compress(payload.encode(), mtime=0)
    )
    return evidence


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=Path.home() / "models/tinyball")
    p.add_argument(
        "--human-jsonl",
        type=Path,
        default=Path.home() / "codex-runs/ball-human-truth.jsonl",
    )
    a = p.parse_args()
    capture(a.root, a.human_jsonl)


if __name__ == "__main__":
    main()
