"""One saved inference pass for each of the two completed scale-aware fits."""

from __future__ import annotations
import json
from pathlib import Path
from common import DEFAULT_MANIFEST, DEFAULT_SOURCE, HERE, dump, load_dataset, sha256
from compare_ball import load_measurements
from train_tiny_ball import predict_all


def main():
    root = Path.home() / "models/tinyball"
    state_path = root / "round3-fit-state.json"
    state = json.loads(state_path.read_text())
    if set(state["fits"]) != set("ab") or state["evaluation_started"]:
        raise ValueError("Both fits must finish before evaluation")
    marker = root / "round3-evaluation-start.json"
    if marker.exists():
        raise ValueError("Evaluation already started; preserve saved evidence")
    import cv2
    import torch
    from ultralytics import YOLO

    cv2.setNumThreads(1)
    torch.set_num_threads(8)
    _, clips = load_dataset(DEFAULT_MANIFEST, DEFAULT_SOURCE)
    m = load_measurements()
    dump(
        marker,
        {
            "fit_state_sha256": sha256(state_path),
            "protocol_sha256": sha256(HERE / "fixtures/round3_execution.json"),
        },
    )
    for letter, fit in state["fits"].items():
        out = root / f"mj-r3-{letter}"
        if (
            sha256(out / "weights.pt") != fit["weights_sha256"]
            or (out / "detections.json").exists()
        ):
            raise ValueError("Changed checkpoint or existing saved pass")
        _, suggestions = predict_all(
            YOLO(str(out / "weights.pt")),
            clips,
            out,
            out.name,
            "mps",
            m["frozen_set_id"],
            False,
            960,
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
