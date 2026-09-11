"""Render saved RF hypotheses over source frames, without model inference."""

from __future__ import annotations
from output_guard import guard_outputs
from common import DEFAULT_REPORT, dump
from compare_ball import load_measurements
from metrics import interpolated_box


def generate(data, out=DEFAULT_REPORT):
    import cv2
    import numpy as np

    cid = "m04-n12-t1411-237107-242145"
    clip = next(c for c in data["clips"] if c["clip_id"] == cid)
    folder = out / "tracks"
    folder.mkdir(parents=True, exist_ok=True)
    paths, provenance = [], []
    for name, result in data["retracking"].items():
        row = next(r for r in result["per_clip"] if r["clip"] == cid)
        intervals = row["fragment_intervals"]
        fid = max(
            range(len(intervals)), key=lambda i: intervals[i][1] - intervals[i][0]
        )
        points = [p for p in row["points"] if p["fragment"] == fid]
        chosen = [points[i] for i in sorted({0, len(points) // 2, len(points) - 1})]
        panels = []
        times = []
        for point in chosen:
            t = point["t"]
            frame = next(f for f in data["outputs"][name][cid]["frames"] if f["t"] == t)
            capture = cv2.VideoCapture(clip["video"])
            capture.set(cv2.CAP_PROP_POS_FRAMES, frame["frame_index"])
            ok, image = capture.read()
            capture.release()
            if not ok:
                raise RuntimeError("track overlay decode failed")
            history = [p for p in points if t - 1 <= p["t"] <= t]
            for a, b in zip(history, history[1:]):
                cv2.line(
                    image,
                    tuple(map(round, a["xy"])),
                    tuple(map(round, b["xy"])),
                    (255, 255, 0),
                    3,
                )
            cv2.circle(
                image, tuple(map(round, point["observed_xy"])), 16, (0, 230, 255), 2
            )
            cv2.drawMarker(
                image,
                tuple(map(round, point["xy"])),
                (255, 255, 0),
                cv2.MARKER_CROSS,
                26,
                2,
            )
            box = interpolated_box(clip["truth_data"]["box_track"], t)
            if box:
                a, b, c, d = map(round, box)
                cv2.rectangle(image, (a, b), (c, d), (255, 255, 255), 2)
            cv2.rectangle(image, (0, 0), (image.shape[1], 102), (10, 10, 10), -1)
            caption = f"{name} @0.1 | {cid} | t={t:.3f} | UNVERIFIED TRACK HYPOTHESIS"
            detail = f"fragment {fid + 1}/{row['fragments']} | longest {row['longest_track_s']:.2f}s | clip continuity {row['continuity']:.1%}"
            for y, text in [
                (28, caption),
                (57, detail),
                (
                    85,
                    "Yellow: selected raw point; cyan: Kalman + preceding 1s in image coordinates; white: marked player",
                ),
            ]:
                cv2.putText(
                    image,
                    text,
                    (14, y),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.62,
                    (255, 255, 255),
                    1,
                    cv2.LINE_AA,
                )
            panels.append(image)
            times.append(t)
        path = folder / f"{name}-n12-track.png"
        if not cv2.imwrite(str(path), np.concatenate(panels, axis=0)):
            raise RuntimeError("track PNG write failed")
        paths.append(str(path))
        provenance.append(
            {
                "path": str(path),
                "candidate": name,
                "clip": cid,
                "times": times,
                "selection": "first/middle/last observation of longest fragment",
                "warning": "image-coordinate trajectory across camera motion; neither identity nor ball truth established",
            }
        )
    dump(folder / "provenance.json", provenance)
    return paths


if __name__ == "__main__":
    guard_outputs(DEFAULT_REPORT / "tracks")
    for path in generate(load_measurements()):
        print(path)
