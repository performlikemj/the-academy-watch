"""Three deterministic detection overlays (not human truth), kept in report dir."""

from __future__ import annotations
from output_guard import guard_outputs
import json
from common import DEFAULT_REPORT
from compare_ball import load_measurements
from metrics import agreement, interpolated_box


def generate(measurements, out=DEFAULT_REPORT):
    import cv2

    ids = [
        "m04-n12-t1411-237107-242145",
        "m04-n17-t717-416826-418915",
        "m04-n09-t1409-143096-143834",
    ]
    colors = {
        "rf_full": (80, 220, 255),
        "rf_2x2": (255, 180, 60),
        "rf_3x3": (220, 90, 230),
        "wasb": (70, 255, 80),
    }
    folder = out / "examples"
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for cid in ids:
        clip = next(c for c in measurements["clips"] if c["clip_id"] == cid)
        outputs = measurements["outputs"]
        # First WASB-visible frame, otherwise middle sample; deterministic policy.
        wasb = outputs["wasb"][cid]["frames"]
        index = next((i for i, r in enumerate(wasb) if r["detections"]), len(wasb) // 2)
        frame = wasb[index]
        cap = cv2.VideoCapture(clip["video"])
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame["frame_index"])
        ok, image = cap.read()
        cap.release()
        if not ok:
            raise RuntimeError("example decode failed")
        box = interpolated_box(clip["truth_data"]["box_track"], frame["t"])
        if box:
            a, b, c, d = map(round, box)
            cv2.rectangle(image, (a, b), (c, d), (255, 255, 255), 2)
        for name, color in colors.items():
            ds = outputs[name][cid]["frames"][index]["detections"]
            for det in ds:
                if det["confidence"] < 0.5:
                    continue
                x, y = map(round, det["xy"])
                cv2.circle(image, (x, y), 9, color, 2)
                label = f"{name}:{det['confidence']:.2f}"
                label_width = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)[
                    0
                ][0]
                cv2.putText(
                    image,
                    label,
                    (
                        max(0, min(x + 10, image.shape[1] - label_width - 4)),
                        max(110, y - 8),
                    ),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.45,
                    color,
                    1,
                    cv2.LINE_AA,
                )
        proxy = agreement(
            {
                name: outputs[name][cid]["frames"][index]["detections"]
                for name in ["rf_full", "rf_2x2", "wasb"]
            }
        )
        for xy in proxy:
            cv2.circle(image, tuple(map(round, xy)), 18, (30, 30, 255), 1)
        cv2.rectangle(image, (0, 0), (image.shape[1], 100), (15, 15, 15), -1)
        cv2.putText(
            image,
            f"{cid} t={frame['t']:.3f}s - DETECTIONS / PROXY, no human ball labels",
            (15, 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
        cv2.putText(
            image,
            "Displayed detections >=0.5; red rings: fixed 2-of-3 proxy at RF 0.1 / WASB 0.5; white: player track",
            (15, 57),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (220, 220, 220),
            1,
            cv2.LINE_AA,
        )
        for i, (name, color) in enumerate(colors.items()):
            cv2.putText(
                image,
                name,
                (15 + i * 220, 85),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                color,
                2,
                cv2.LINE_AA,
            )
        path = folder / f"{cid}.png"
        if not cv2.imwrite(str(path), image):
            raise RuntimeError("example write failed")
        paths.append(str(path))
    return paths


if __name__ == "__main__":
    guard_outputs(DEFAULT_REPORT / "examples")
    data = load_measurements()
    print(json.dumps(generate(data), indent=2))
