"""Save exact source-pixel evidence of RF b's held-out n21 false detections."""

from output_guard import guard_outputs
from pathlib import Path
import json
from ball_truth_kit import import_labels
from common import DEFAULT_MANIFEST, DEFAULT_SOURCE, dump, load_dataset, samples
from compare_ball import load_measurements
from human_loop import frame_catalog


def main():
    guard_outputs(
        Path.home() / "codex-runs/ball-r5-n21",
        inputs=[Path.home() / "codex-runs/ball-human-truth.jsonl"],
    )
    import cv2

    cv2.setNumThreads(1)
    root = Path.home() / "codex-runs/ball-r5-n21"
    root.mkdir(exist_ok=True)
    labels = import_labels(
        Path.home() / "codex-runs/ball-human-truth.jsonl",
        frame_catalog(load_measurements()),
    )
    outputs = json.loads(
        (Path.home() / "models/tinyball/r5-rfb-low/detections.json").read_text()
    )["outputs"]
    _, clips = load_dataset(DEFAULT_MANIFEST, DEFAULT_SOURCE)
    clip = next(c for c in clips if "n21-t3011" in c["clip_id"])
    cid = clip["clip_id"]
    rows = {r["t"]: r for r in outputs[cid]["frames"]}
    records = []
    panels = []
    for sample, stack in samples(clip):
        label = labels.get((cid, sample["t"]))
        if not label or label["visible"]:
            continue
        for d in rows[sample["t"]]["detections"]:
            if d["confidence"] < 0.1:
                continue
            x0, y0, x1, y1 = map(round, d["box"])
            image = cv2.cvtColor(stack[-1], cv2.COLOR_RGB2BGR)
            name = f"{sample['sample_index']:03d}-{len(records)}"
            cv2.imwrite(str(root / f"{name}-box.png"), image[y0:y1, x0:x1])
            crop = image[
                max(0, y0 - 100) : min(1080, y1 + 100),
                max(0, x0 - 100) : min(1920, x1 + 100),
            ].copy()
            cv2.imwrite(str(root / f"{name}-context.png"), crop)
            cv2.rectangle(
                crop, (100, 100), (100 + x1 - x0, 100 + y1 - y0), (0, 0, 255), 1
            )
            cv2.putText(
                crop, name, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2
            )
            panels.append(cv2.resize(crop, (400, 400)))
            records.append(
                {
                    "sample_index": sample["sample_index"],
                    "t": sample["t"],
                    "box": d["box"],
                    "confidence": d["confidence"],
                }
            )
    cv2.imwrite(str(root / "contact-sheet.png"), cv2.hconcat(panels))
    dump(root / "private-crops.json", records)
    print(root, len(records))


if __name__ == "__main__":
    main()
