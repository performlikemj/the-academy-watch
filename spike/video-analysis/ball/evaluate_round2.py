"""Single all-frame pass per frozen round-2 fit; never changes model selection."""

from __future__ import annotations
import argparse
import json
from pathlib import Path
from common import DEFAULT_MANIFEST, DEFAULT_SOURCE, dump, load_dataset, sha256
from compare_ball import load_measurements
from train_tiny_ball import predict_all


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=Path.home() / "models/tinyball")
    a = p.parse_args()
    selection_path = a.root / "round2-selection.json"
    selection = json.loads(selection_path.read_text())
    if set(selection["fits"]) != set("abcd") or selection["evaluation_started"]:
        p.error("requires all four frozen fits and no previous evaluation")
    import cv2
    import torch
    from ultralytics import YOLO

    cv2.setNumThreads(1)
    torch.set_num_threads(8)
    _, clips = load_dataset(DEFAULT_MANIFEST, DEFAULT_SOURCE)
    m = load_measurements()
    # This separate marker preserves the original pre-evaluation selection bytes.
    dump(
        a.root / "round2-evaluation-start.json",
        {"selection_sha256": sha256(selection_path), "selected": selection["selected"]},
    )
    for letter, fit in selection["fits"].items():
        out = a.root / f"mj-r2-{letter}"
        if sha256(out / "weights.pt") != fit["weights_sha256"]:
            raise ValueError(f"checkpoint changed after TRAIN-only selection: {out}")
        if (out / "detections.json").exists():
            raise ValueError(f"saved pass already exists: {out}")
        _, suggestions = predict_all(
            YOLO(str(out / "weights.pt")),
            clips,
            out,
            out.name,
            "mps",
            m["frozen_set_id"],
            False,
            fit["model_input_px"],
        )
        saved = json.loads((out / "detections.json").read_text())
        saved.update(
            training_split=fit["split"],
            training_labels_sha256=fit["labels_sha256"],
            weights_sha256=fit["weights_sha256"],
        )
        dump(out / "detections.json", saved)
        print(f"EVALUATED {letter}: 1105 frames, {suggestions} suggestions", flush=True)


if __name__ == "__main__":
    main()
