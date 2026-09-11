"""Rescore saved runs, freeze aggregate review evidence, and select by authorized rule."""

from __future__ import annotations
from output_guard import guard_outputs
import argparse
import gzip
import json
import math
from pathlib import Path
from ball_truth_kit import import_labels
from common import HERE, dump, sha256
from compare_ball import load_measurements
from extra_detections import load_extra
from human_loop import frame_catalog
from human_score import score
from matching_controls import controls
from round2_analysis import paired_score, error_records, error_summary


def freeze(path, data):
    payload = json.dumps(data, sort_keys=True, indent=2, allow_nan=False) + "\n"
    if any(key in payload for key in ('"x":', '"y":', '"xy":', '"hit":')):
        raise ValueError("Only aggregate scored output may enter fixtures")
    path.write_bytes(gzip.compress(payload.encode(), mtime=0))


def select_current(results):
    eligible = [
        r
        for r in results
        if r["candidate"].startswith(("tinyball-r2-", "tinyball-r3-"))
        and r["held"]["groups"]["all"]["false_per_10s"] is not None
        and r["held"]["groups"]["all"]["false_per_10s"] <= 2
        and r["held"]["groups"]["on_ball"]["top1_recall"] is not None
    ]
    if not eligible:
        return None
    return min(
        eligible,
        key=lambda r: (
            -r["held"]["groups"]["on_ball"]["top1_recall"],
            r["held"]["groups"]["all"]["false_per_10s"],
            r["candidate"],
        ),
    )["candidate"]


def path_sensitivity(outputs, labels, split):
    credits: dict[str, int] = {}
    for cid, output in outputs.items():
        visible = sorted(
            (t, v) for (c, t), v in labels.items() if c == cid and v["visible"]
        )
        for row in output["frames"]:
            label = labels.get((cid, row["t"]))
            if not label or label["visible"]:
                continue
            before = [(t, v) for t, v in visible if t < row["t"]]
            after = [(t, v) for t, v in visible if t > row["t"]]
            if not before or not after:
                continue
            t0, v0 = before[-1]
            t1, v1 = after[0]
            if t1 - t0 > 1.01:  # Two native 0.5005-second sampling steps.
                continue
            fraction = (row["t"] - t0) / (t1 - t0)
            point = [v0[k] + fraction * (v1[k] - v0[k]) for k in ("x", "y")]
            count = sum(
                d["confidence"] >= 0.1 and math.dist(d["xy"], point) <= 50
                for d in row["detections"]
            )
            if count:
                credits[cid] = credits.get(cid, 0) + count
    result = {
        "credits_per_clip": credits,
        "definition": "Sensitivity only, not verified invisible balls: credit detections within 50 native px of linear interpolation between visible clicks bracketing a no-ball frame, with total bracket gap <=1.01s (two 0.5005s samples). This explicitly specified reconstruction finds the reviewer two r1-960 near-path detections, including one 26.4px away (outside the 20px visible matching radius). The real gate always uses zero credits.",
    }
    for scope in ("all", "held"):
        selected = {
            cid for cid in outputs if scope == "all" or cid in split["held_out"]
        }
        no_ball = sum(
            not v["visible"] for (cid, _), v in labels.items() if cid in selected
        )
        false = sum(
            len([d for d in r["detections"] if d["confidence"] >= 0.1])
            for cid in selected
            for r in outputs[cid]["frames"]
            if (cid, r["t"]) in labels and not labels[(cid, r["t"])]["visible"]
        )
        credit = sum(n for cid, n in credits.items() if cid in selected)
        result[scope] = {
            "no_ball_frames": no_ball,
            "strict_false": false,
            "credits": credit,
            "strict_false_per_10s": 20 * false / no_ball,
            "path_credited_false_per_10s": 20 * (false - credit) / no_ball,
        }
    return result


def capture(root, human_jsonl, historical_only=False, out=None):
    destination = Path(out) if out is not None else HERE / "fixtures"
    if out is not None:
        guard_outputs(out, inputs=[human_jsonl, root])
        destination.mkdir(parents=True)
    m = load_measurements()
    labels = import_labels(human_jsonl, frame_catalog(m))
    protocol = json.loads((HERE / "fixtures/round3_execution.json").read_text())
    split = protocol["split"]
    model_dirs = {
        "tinyball-r1": "mj-r1",
        "tinyball-r1-960": "mj-r1-960",
        **{f"tinyball-r2-{c}": f"mj-r2-{c}" for c in "abcd"},
    }
    if not historical_only:
        model_dirs.update({f"tinyball-r3-{c}": f"mj-r3-{c}" for c in "ab"})
    specs = [
        f"{name}={root / directory / 'detections.json'}"
        for name, directory in model_dirs.items()
    ]
    extras = load_extra(specs, m)
    for name, saved in extras.items():
        if saved["training_labels_sha256"] != sha256(human_jsonl):
            raise ValueError(f"Label hash changed: {name}")
        if (
            name.startswith(("tinyball-r2-", "tinyball-r3-"))
            and saved["training_split"] != split
        ):
            raise ValueError(f"Training split changed: {name}")
        if saved["weights_sha256"] != sha256(root / model_dirs[name] / "weights.pt"):
            raise ValueError(f"Saved predictions/checkpoint mismatch: {name}")
    if not historical_only:
        state_path = root / "round3-fit-state.json"
        state = json.loads(state_path.read_text())
        marker = json.loads((root / "round3-evaluation-start.json").read_text())
        if set(state["fits"]) != set("ab") or marker["fit_state_sha256"] != sha256(
            state_path
        ):
            raise ValueError("Two-fit snapshot changed after evaluation")
        for letter in "ab":
            fit = json.loads((root / f"mj-r3-{letter}/fit_summary.json").read_text())
            if (
                fit != state["fits"][letter]
                or fit["weights_sha256"]
                != extras[f"tinyball-r3-{letter}"]["weights_sha256"]
            ):
                raise ValueError("Fit summary and saved checkpoint disagree")
        if any(
            sha256(HERE / name) != value
            for name, value in protocol["training_code_sha256"].items()
        ):
            raise ValueError(
                "Training implementation changed after fit protocol recording"
            )
    r1_extras = {
        k: v for k, v in extras.items() if k in ("tinyball-r1", "tinyball-r1-960")
    }
    r1 = score(m, labels, r1_extras)
    r1["labels"]["sha256"] = sha256(human_jsonl)
    freeze(destination / "human_measurements.json.gz", r1)
    candidates = {
        name: m["outputs"][name]
        for name in ("rf_full", "rf_2x2", "rf_3x3", "wasb", "wasb_2x2")
    }
    candidates.update({name: saved["outputs"] for name, saved in extras.items()})
    results = []
    for name, outputs in candidates.items():
        row = paired_score(m, labels, name, outputs, split)
        row["all"]["evaluation_label"] = "all clips (incl. training clips)"
        row["held"]["evaluation_label"] = protocol["evaluation_label"]
        results.append(row)
        print(f"Rescored {name}", flush=True)
    r2path = HERE / "fixtures/round2_measurements.json.gz"
    r2 = json.loads(gzip.decompress(r2path.read_bytes()))
    r2["results"] = [
        r for r in results if not r["candidate"].startswith("tinyball-r3-")
    ]
    r2["review_note"] = (
        "Round3 rescoring: top-1 gate, manual recall, track rates added. Historical TRAIN-only model selection and oracle error/projection evidence retained explicitly as historical."
    )
    freeze(destination / "round2_measurements.json.gz", r2)
    people_path = root / "round2-people.json"
    if sha256(people_path) != r2["people_sha256"]:
        raise ValueError("Saved person proxy changed")
    people = json.loads(people_path.read_text())
    errors = {}
    for name, outputs in candidates.items():
        if not name.startswith("tinyball-"):
            continue
        records = error_records(m, labels, outputs, people)
        # Maintain independent RF size/proxy buckets while adding highest-confidence outcome.
        tops = {
            (cid, row["t"]): max(
                [d for d in row["detections"] if d["confidence"] >= 0.1],
                key=lambda d: d["confidence"],
                default=None,
            )
            for cid, output in outputs.items()
            for row in output["frames"]
        }
        # error_records order is clip/schedule order over visible on-ball labels.
        from metrics import clip_class

        keys = [
            (c["clip_id"], row["t"])
            for c in m["clips"]
            if clip_class(c) == "on_ball"
            for row in outputs[c["clip_id"]]["frames"]
            if labels.get((c["clip_id"], row["t"]), {}).get("visible")
        ]
        top_records = []
        if len(keys) != len(records):
            raise ValueError("Error bucket and visible-label schedules disagree")
        for key, record in zip(keys, records):
            label, top = labels[key], tops[key]
            hit = bool(top and math.dist(top["xy"], [label["x"], label["y"]]) <= 20)
            top_records.append({**record, "hit": hit})
        errors[name] = {
            rule: {
                scope: error_summary(
                    [
                        r
                        for r in rows
                        if scope == "all" or r["clip"] in split["held_out"]
                    ]
                )
                for scope in ("all", "held")
            }
            for rule, rows in (("oracle", records), ("top1", top_records))
        }
    evidence = {
        "schema_version": 1,
        "status": "historical review complete; new fits pending"
        if historical_only
        else "complete",
        "results": results,
        "round1_native_results": [
            paired_score(
                m, labels, name, outputs, extras["tinyball-r1-960"]["training_split"]
            )
            for name, outputs in candidates.items()
            if name
            in (
                "rf_full",
                "rf_2x2",
                "rf_3x3",
                "wasb",
                "wasb_2x2",
                "tinyball-r1",
                "tinyball-r1-960",
            )
        ],
        "current_best": select_current(results),
        "errors": errors,
        "controls": controls(m, labels, candidates, split),
        "path_sensitivity_r1_original_split": path_sensitivity(
            candidates["tinyball-r1-960"],
            labels,
            extras["tinyball-r1-960"]["training_split"],
        ),
        "path_sensitivity_common_six": path_sensitivity(
            candidates["tinyball-r1-960"], labels, split
        ),
        "labels_sha256": sha256(human_jsonl),
        "people_sha256": sha256(people_path),
        "saved_passes": {
            name: {
                "sha256": sha256(root / directory / "detections.json"),
                "weights_sha256": extras[name]["weights_sha256"],
                "frames": sum(len(o["frames"]) for o in candidates[name].values()),
            }
            for name, directory in model_dirs.items()
        },
    }
    if not historical_only:
        evidence["evaluation_start"] = marker
        evidence["fit_state_sha256"] = sha256(state_path)
        evidence["fits"] = {
            letter: json.loads((root / f"mj-r3-{letter}/fit_summary.json").read_text())
            for letter in "ab"
        }
        evidence["datasets"] = {
            letter: json.loads((root / f"mj-r3-{letter}/dataset.json").read_text())
            for letter in "ab"
        }
        evidence["run_files"] = {
            letter: {
                name: sha256(root / f"mj-r3-{letter}" / name)
                for name in ("fit/results.csv", "fit/args.yaml")
            }
            for letter in "ab"
        }
        for name in ("tinyball-r3-a", "tinyball-r3-b"):
            dump(
                (
                    destination / (model_dirs[name] + "-metrics-scored.json")
                    if out is not None
                    else root / model_dirs[name] / "metrics.json"
                ),
                next(r for r in results if r["candidate"] == name),
            )
    freeze(destination / "round3_scored_output.json.gz", evidence)
    dump((destination if out is not None else root) / "round3-evidence.json", evidence)
    return evidence


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=Path.home() / "models/tinyball")
    p.add_argument(
        "--human-jsonl",
        type=Path,
        default=Path.home() / "codex-runs/ball-human-truth.jsonl",
    )
    p.add_argument("--historical-only", action="store_true")
    p.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Fresh directory for scored aggregates and enriched metrics",
    )
    a = p.parse_args()
    guard_outputs(a.out, inputs=[a.human_jsonl, a.root], parser=p)
    capture(a.root, a.human_jsonl, a.historical_only, out=a.out)


if __name__ == "__main__":
    main()
