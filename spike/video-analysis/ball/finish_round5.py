"""Post-fit scoring, diagnostic checkpoints and RF-only suggestion preparation."""

from __future__ import annotations
from output_guard import guard_outputs
import json
from pathlib import Path
from ball_truth_kit import import_labels
from common import HERE, dump, sha256
from compare_ball import load_measurements
from fair_protocol import evaluate
from extra_detections import load_extra
from human_loop import frame_catalog, write_jsonl
from review_round5 import capture, select_rf
from checkpoint_provenance import declared_passes, validate_saved_passes


def main():
    guard_outputs(
        Path.home() / "models/tinyball/round5-evidence.json",
        Path.home() / "models/tinyball/round5-kit-suggestions.jsonl",
        *(
            Path.home() / "models/tinyball" / f"mj-r5-rf-{c}" / "metrics-scored.json"
            for c in "ab"
        ),
        inputs=[Path.home() / "codex-runs/ball-human-truth.jsonl"],
    )
    root = Path.home() / "models/tinyball"
    # Check every final and diagnostic before scoring or writing any artifacts.
    validate_saved_passes(declared_passes(root), root)
    paths = {
        "yolo-r2-b": root / "r5-yolo-low/detections.json",
        "rf-b": root / "r5-rfb-low/detections.json",
        **{f"rf-r5-{c}": root / f"r5-rf-{c}-final-low/detections.json" for c in "ab"},
    }
    data = capture(paths)
    data["fit_protocol_at_completion"] = {
        "snapshot": json.loads((HERE / "fixtures/round5_execution.json").read_text()),
        "sha256": sha256(HERE / "fixtures/round5_execution.json"),
    }
    data["evaluation_start"] = json.loads(
        (root / "round5-evaluation-start.json").read_text()
    )
    if (
        data["evaluation_start"]["protocol_sha256"]
        != data["fit_protocol_at_completion"]["sha256"]
    ):
        raise ValueError("evaluation protocol differs from fitting protocol")
    m = load_measurements()
    labels = import_labels(
        Path.home() / "codex-runs/ball-human-truth.jsonl", frame_catalog(m)
    )
    split = data["protocol"]["split"]
    data["fits"] = {}
    data["datasets"] = {}
    data["learning_curve"] = {}
    for letter in "ab":
        directory = root / f"mj-r5-rf-{letter}"
        fit = json.loads((directory / "fit_summary.json").read_text())
        if (
            sha256(directory / "fit_summary.json")
            != data["evaluation_start"]["fit_summaries_sha256"][letter]
        ):
            raise ValueError("fit summary changed after evaluation began")
        if sha256(directory / "weights.pt") != fit["weights_sha256"]:
            raise ValueError("changed final checkpoint")
        if (
            data["models"][f"rf-r5-{letter}"]["saved_pass_provenance"]["weights_sha256"]
            != fit["weights_sha256"]
        ):
            raise ValueError("final saved pass came from a different checkpoint")
        if fit["protocol_sha256"] != data["fit_protocol_at_completion"]["sha256"]:
            raise ValueError(
                "fit protocol changed after completion; preserve and audit its snapshot"
            )
        data["fits"][f"rf-r5-{letter}"] = fit
        data["datasets"][f"rf-r5-{letter}"] = json.loads(
            (directory / "dataset.json").read_text()
        )
        if not (
            fit["labels_sha256"]
            == data["labels_sha256"]
            == data["datasets"][f"rf-r5-{letter}"]["labels_sha256"]
        ):
            raise ValueError("human labels changed during fitting or evaluation")
        for checkpoint in fit["checkpoints"]:
            epoch = checkpoint["epoch"]
            path = root / f"r5-rf-{letter}-epoch-{epoch:02d}-low/detections.json"
            checkpoint_data = load_extra([f"checkpoint={path}"], m)["checkpoint"]
            if checkpoint_data["threshold"] != 0.01:
                raise ValueError("checkpoint curve requires confidence 0.01 saved pass")
            if checkpoint_data["weights_sha256"] != checkpoint["sha256"]:
                raise ValueError(
                    "diagnostic saved pass came from a different checkpoint"
                )
            outputs = checkpoint_data["outputs"]
            result = evaluate(m, labels, outputs, split)
            result["checkpoint_sha256"] = checkpoint["sha256"]
            data["learning_curve"][f"rf-r5-{letter} / epoch-{epoch}"] = result
        data["learning_curve"][f"rf-r5-{letter} / FINAL"] = data["models"][
            f"rf-r5-{letter}"
        ]
        dump(
            directory / "metrics-scored.json",
            {
                **fit,
                "fair_protocol": data["models"][f"rf-r5-{letter}"],
                "evaluation_label": data["evaluation_label"],
                "effective_final_model_selection": data["selection_rule"],
                "configuration_note": "Config preserves the fit-start declaration. Final model selection was amended during fit-a epoch1, before any new held-out evaluation; replay initialization was corrected before fit b. Numeric training settings did not change. See the committed execution fixture for both decisions.",
            },
        )

    data["best_new_rf_final_selected"] = select_rf(data["models"], only_new=True)
    best = data["best_rf_final_selected"]
    source_id = "mj-r4-rf-b" if best == "rf-b" else "mj-r5-rf-" + best[-1]
    threshold = data["models"][best]["operating_points"]["1"]["threshold"]
    selected = json.loads(paths[best].read_text())
    suggestions = []
    for cid, out in selected["outputs"].items():
        for row in out["frames"]:
            ds = [d for d in row["detections"] if d["confidence"] >= threshold]
            if ds:
                d = max(ds, key=lambda d: d["confidence"])
                suggestions.append(
                    {
                        "clip": cid,
                        "t": row["t"],
                        "x": d["xy"][0],
                        "y": d["xy"][1],
                        "score": d["confidence"],
                        "source": f"model:{source_id}:r5-train-fp1",
                    }
                )
    destination = root / "round5-kit-suggestions.jsonl"
    write_jsonl(destination, suggestions)
    data["kit"] = {
        "model": best,
        "threshold": threshold,
        "source": f"model:{source_id}:r5-train-fp1",
        "suggestions": len(suggestions),
        "unlabelled": 1105 - len(labels),
        "unlabelled_with_suggestion": sum(
            (r["clip"], r["t"]) not in labels for r in suggestions
        ),
        "suggestions_sha256": sha256(destination),
        "existing_labels_sha256": sha256(
            Path.home() / "codex-runs/ball-human-truth.jsonl"
        ),
        "build_version": 8,
        "confirmed_seed_labels": 1057,
    }
    dump(root / "round5-evidence.json", data)
    print(
        json.dumps(
            {
                "best_rf": best,
                "best_new_rf": data["best_new_rf_final_selected"],
                "kit": data["kit"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
