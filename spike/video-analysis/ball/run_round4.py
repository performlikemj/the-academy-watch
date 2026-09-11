"""The two frozen RF-DETR fits; evaluation is an explicit later invocation."""

from __future__ import annotations

from output_guard import guard_outputs
import argparse
import subprocess
import sys
from pathlib import Path

from common import HERE


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--start-at", choices=["a", "b"], default="a")
    a = p.parse_args()
    guard_outputs(
        *(
            Path.home() / "models/tinyball" / f"mj-r4-rf-{c}"
            for c in ("ab" if a.start_at == "a" else "b")
        ),
        *(
            Path.home() / f"codex-runs/ball-mj-r4-rf-{c}.log"
            for c in ("ab" if a.start_at == "a" else "b")
        ),
        parser=p,
    )
    root = Path.home() / "models/tinyball"
    for letter in "ab" if a.start_at == "a" else "b":
        cmd = [
            sys.executable,
            str(HERE / "train_tiny_ball_rfdetr.py"),
            "--human-jsonl",
            str(Path.home() / "codex-runs/ball-human-truth.jsonl"),
            "--out",
            str(root / f"mj-r4-rf-{letter}"),
            "--resolution",
            "640" if letter == "a" else "960",
            "--lr",
            ".0001" if letter == "a" else ".00005",
        ]
        if letter == "b":
            cmd += ["--init", str(root / "mj-r4-rf-a/weights.pt")]
        with (Path.home() / f"codex-runs/ball-mj-r4-rf-{letter}.log").open("x") as log:
            subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, check=True)
        print(f"RF fit {letter} complete, no held-out evaluation", flush=True)


if __name__ == "__main__":
    main()
