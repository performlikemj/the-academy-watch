"""Exactly two scale-aware repeats of round-2 a/b; no evaluation during fitting."""

from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path
from common import HERE, dump


def main():
    root = Path.home() / "models/tinyball"
    fits = {}
    for letter in "ab":
        out = root / f"mj-r3-{letter}"
        init = root / ("yolo11n.pt" if letter == "a" else "mj-r1-960/weights.pt")
        cmd = [
            sys.executable,
            str(HERE / "train_tiny_ball.py"),
            "--human-jsonl",
            str(Path.home() / "codex-runs/ball-human-truth.jsonl"),
            "--out",
            str(out),
            "--init",
            str(init),
            "--imgsz",
            "960",
            "--epochs",
            "100",
            "--train-minutes",
            "20",
            "--batch",
            "16",
            "--patience",
            "6",
            "--split-json",
            str(HERE / "fixtures/round2_execution.json"),
            "--allow-prior-tuning",
            "--train-loss-only",
            "--defer-evaluation",
            "--scale-targets",
        ]
        print(f"START {letter}: scale-aware 2x2@960, init={init}", flush=True)
        with (Path.home() / f"codex-runs/ball-mj-r3-{letter}.log").open("x") as log:
            subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, check=True)
        fits[letter] = json.loads((out / "fit_summary.json").read_text())
        dump(
            root / "round3-fit-state.json", {"fits": fits, "evaluation_started": False}
        )
        print(f"DONE {letter}: {fits[letter]['training_s'] / 60:.2f} min", flush=True)
    print(
        "Exactly two fits complete; select only after saved-pass evaluation under the authorized rule.",
        flush=True,
    )


if __name__ == "__main__":
    main()
