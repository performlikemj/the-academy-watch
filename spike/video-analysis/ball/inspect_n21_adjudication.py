"""Render saved boxes and current MJ labels on n21 frames; no inference."""

from pathlib import Path
import gzip
import argparse
import json
from common import HERE, DEFAULT_MANIFEST, DEFAULT_SOURCE, dump, load_dataset, samples


def main():
    import cv2
    import numpy as np

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all-frames", action="store_true")
    args = parser.parse_args()
    cv2.setNumThreads(1)
    root = Path.home() / "models/tinyball"
    out = Path.home() / "codex-runs/ball-r5-n21"
    out.mkdir(exist_ok=True)
    e = json.loads(
        gzip.decompress((HERE / "fixtures/round5_scored_output.json.gz").read_bytes())
    )
    definitions = [
        ("yolo-r2-b", "r5-yolo-low", "Y", (0, 220, 220)),
        ("rf-b", "r5-rfb-low", "RF", (255, 150, 0)),
        ("rf-r5-a", "r5-rf-a-final-low", "A", (0, 220, 0)),
        ("rf-r5-b", "r5-rf-b-final-low", "B", (220, 0, 220)),
    ]
    _, clips = load_dataset(DEFAULT_MANIFEST, DEFAULT_SOURCE)
    clip = next(c for c in clips if "n21-t3011" in c["clip_id"])
    cid = clip["clip_id"]
    outputs = {
        n: {
            r["sample_index"]: r
            for r in json.loads((root / folder / "detections.json").read_text())[
                "outputs"
            ][cid]["frames"]
        }
        for n, folder, _, _ in definitions
    }
    human = {
        (r["clip"], r["t"]): r
        for r in map(
            json.loads,
            (Path.home() / "codex-runs/ball-human-truth.jsonl")
            .read_text()
            .splitlines(),
        )
    }
    indices = range(11) if args.all_frames else range(6, 11)
    panels, records, crops = [], [], []
    for sample, stack in samples(clip):
        i = sample["sample_index"]
        if i not in indices:
            continue
        image = cv2.cvtColor(stack[-1], cv2.COLOR_RGB2BGR)
        painted = image.copy()
        truth = human[(cid, sample["t"])]
        if truth["visible"]:
            cv2.drawMarker(
                painted,
                (round(truth["x"]), round(truth["y"])),
                (255, 255, 255),
                cv2.MARKER_CROSS,
                16,
                2,
            )
        labels = []
        for name, _, short, color in definitions:
            for j, d in enumerate(outputs[name][i]["detections"]):
                budgets = [
                    b
                    for b in ("1", "2")
                    if d["confidence"]
                    >= e["models"][name]["operating_points"][b]["threshold"]
                ]
                if not budgets:
                    continue
                x0, y0, x1, y1 = map(round, d["box"])
                cv2.rectangle(painted, (x0, y0), (x1, y1), color, 2)
                tag = short + "/".join(budgets) + f" {d['confidence']:.3f}"
                labels.append((tag, color))
                records.append(
                    {
                        "model": name,
                        "sample_index": i,
                        "detection_index": j,
                        "budgets": budgets,
                        "box": d["box"],
                        "xy": d["xy"],
                        "confidence": d["confidence"],
                    }
                )
                if name.startswith("rf-r5-"):
                    for b in budgets:
                        stem = f"{name}-T{b}-s{i}-d{j}"
                        cv2.imwrite(
                            str(out / (stem + "-box.png")),
                            image[max(0, y0) : y1, max(0, x0) : x1],
                        )
                        context = image[
                            max(0, y0 - 60) : min(1080, y1 + 60),
                            max(0, x0 - 60) : min(1920, x1 + 60),
                        ].copy()
                        cv2.rectangle(
                            context,
                            (min(60, x0), min(60, y0)),
                            (min(60, x0) + x1 - x0, min(60, y0) + y1 - y0),
                            color,
                            1,
                        )
                        context = cv2.resize(context, (360, 360))
                        cv2.putText(
                            context,
                            stem,
                            (5, 22),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.5,
                            color,
                            1,
                        )
                        cv2.imwrite(str(out / (stem + "-context.png")), context)
                        crops.append(context)
        panel = np.full((980, 640, 3), 30, np.uint8)
        cv2.putText(
            panel,
            f"s{i}  t={sample['t']:.3f}  MJ: {'VISIBLE' if truth['visible'] else 'NO BALL'}",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 255, 255),
            1,
        )
        panel[50:410] = cv2.resize(painted, (640, 360))
        # Same source region across all five frames, visibly marked as enlargement.
        panel[435:795] = cv2.resize(painted[345:615, 970:1450], (640, 360))
        cv2.putText(
            panel,
            "Enlargement; boxes retained at T1 and/or T2",
            (10, 425),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 255, 255),
            1,
        )
        for line, (tag, color) in enumerate(labels):
            cv2.putText(
                panel,
                tag,
                (10 + (line % 2) * 315, 820 + (line // 2) * 23),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                color,
                1,
            )
        if not labels:
            cv2.putText(
                panel,
                "No retained boxes at either budget",
                (10, 835),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 255, 255),
                1,
            )
        cv2.putText(
            panel,
            "Y: YOLO r2-b; RF: old RF b; A/B: r5 fits",
            (10, 955),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255, 255, 255),
            1,
        )
        if truth["visible"]:
            provenance = (
                truth.get("accepted_source")
                if truth.get("source_accepted")
                else "manual click"
            )
            cv2.putText(
                panel,
                "MJ: " + provenance + " (white cross)",
                (10, 930),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (255, 255, 255),
                1,
            )
        panels.append(panel)
    assert len(panels) == len(indices)
    sheet_name = "adjudicate-s0-s10.png" if args.all_frames else "adjudicate-s6-s10.png"
    if args.all_frames:
        panels.append(np.zeros_like(panels[0]))
        sheet = cv2.vconcat([cv2.hconcat(panels[k : k + 4]) for k in range(0, 12, 4)])
    else:
        sheet = cv2.hconcat(panels)
    cv2.imwrite(str(out / sheet_name), sheet)
    if crops:
        width = 4
        crops += [np.zeros_like(crops[0])] * ((-len(crops)) % width)
        cv2.imwrite(
            str(
                out
                / (
                    "r5-fits-s0-s10-both-budgets.png"
                    if args.all_frames
                    else "r5-fits-both-budgets.png"
                )
            ),
            cv2.vconcat(
                [cv2.hconcat(crops[k : k + width]) for k in range(0, len(crops), width)]
            ),
        )
    dump(
        out
        / (
            "adjudication-s0-s10-private-boxes.json"
            if args.all_frames
            else "adjudication-private-boxes.json"
        ),
        records,
    )
    print(out / sheet_name)
    for r in records:
        print(r)


if __name__ == "__main__":
    main()
