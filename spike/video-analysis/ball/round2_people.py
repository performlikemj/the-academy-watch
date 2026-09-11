"""Fixed general person detections for the image-overlap error proxy, not training."""

from __future__ import annotations
from output_guard import guard_outputs
import argparse
import json
from pathlib import Path
from common import DEFAULT_MANIFEST, DEFAULT_SOURCE, dump, load_dataset, samples, sha256


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--out", type=Path, default=Path.home() / "models/tinyball/round2-people.json"
    )
    a = p.parse_args()
    guard_outputs(a.out, parser=p)
    if a.out.exists():
        p.error("preserve existing person pass")
    selection = json.loads((a.out.parent / "round2-selection.json").read_text())
    if set(selection["fits"]) != set("abcd"):
        p.error("do not contend for MPS during fitting")
    import cv2
    import torch
    from ultralytics import YOLO

    cv2.setNumThreads(1)
    torch.set_num_threads(8)
    weights = Path.home() / "models/tinyball/yolo11n.pt"
    model = YOLO(str(weights))
    _, clips = load_dataset(DEFAULT_MANIFEST, DEFAULT_SOURCE)
    outputs = {}
    for clip in clips:
        rows = []
        for sample, stack in samples(clip):
            result = model.predict(
                cv2.cvtColor(stack[-1], cv2.COLOR_RGB2BGR),
                imgsz=1280,
                device="mps",
                classes=[0],
                conf=0.25,
                verbose=False,
            )[0]
            rows.append({"t": sample["t"], "boxes": result.boxes.xyxy.cpu().tolist()})
        outputs[clip["clip_id"]] = rows
        print(f"people {clip['clip_id']}: {len(rows)} frames", flush=True)
    dump(
        a.out,
        {
            "outputs": outputs,
            "source_sha256": sha256(DEFAULT_SOURCE),
            "weights_sha256": sha256(weights),
            "recipe": "COCO YOLO11n, class=person, full frame imgsz=1280, confidence=0.25, no tuning",
        },
    )


if __name__ == "__main__":
    main()
