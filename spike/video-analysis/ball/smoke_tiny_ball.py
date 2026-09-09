"""Generate explicitly synthetic one-clip proxy labels OUTSIDE truth, then smoke."""

from __future__ import annotations
import argparse
import math
import subprocess
import sys
from pathlib import Path
from compare_ball import load_measurements
from common import dump
from human_loop import write_jsonl
from metrics import clip_class


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    if a.out.exists():
        p.error("use a new smoke output path")
    m = load_measurements()
    c = next(c for c in m["clips"] if clip_class(c) == "on_ball")
    cid = c["clip_id"]
    rows = []
    for full, tiled in zip(
        m["outputs"]["rf_full"][cid]["frames"], m["outputs"]["rf_2x2"][cid]["frames"]
    ):
        pairs = [
            (x, y)
            for x in full["detections"]
            for y in tiled["detections"]
            if math.dist(x["xy"], y["xy"]) <= 40
        ]
        pair = (
            max(pairs, key=lambda p: p[0]["confidence"] * p[1]["confidence"])
            if pairs
            else None
        )
        rows.append(
            {
                "clip": cid,
                "t": full["t"],
                "x": (pair[0]["xy"][0] + pair[1]["xy"][0]) / 2 if pair else None,
                "y": (pair[0]["xy"][1] + pair[1]["xy"][1]) / 2 if pair else None,
                "visible": bool(pair),
            }
        )
    label_path = a.out.with_name(a.out.name + "-SYNTHETIC-labels.jsonl")
    write_jsonl(label_path, rows)
    dump(
        label_path.with_suffix(".provenance.json"),
        {
            "synthetic": True,
            "human_truth": False,
            "source": "RF full/2x2 proxy pair within40px; absent pair becomes synthetic negative ONLY for smoke",
            "clip": cid,
            "frames": len(rows),
        },
    )
    subprocess.run(
        [
            sys.executable,
            str(Path(__file__).with_name("train_tiny_ball.py")),
            "--human-jsonl",
            str(label_path),
            "--out",
            str(a.out),
            "--synthetic-smoke",
            "--epochs",
            "2",
        ],
        check=True,
    )


if __name__ == "__main__":
    main()
