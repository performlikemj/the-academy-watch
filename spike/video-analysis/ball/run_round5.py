"""Finish the two predeclared fits, then run all final/checkpoint diagnostics."""

from __future__ import annotations
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from common import HERE, dump, sha256


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--first-pid", type=int, required=True)
    a = p.parse_args()
    root = Path.home() / "models/tinyball"
    logs = Path.home() / "codex-runs"
    protocol = json.loads((HERE / "fixtures/round5_execution.json").read_text())
    dump(root / "round5-protocol-at-training.json", protocol)
    while not (root / "mj-r5-rf-a/fit_summary.json").exists():
        os.kill(a.first_pid, 0)
        time.sleep(5)
    for name, digest in protocol["training_code_sha256"].items():
        if sha256(HERE / name) != digest:
            raise ValueError("training source changed after protocol freeze")
    with (logs / "ball-r5-fit-b.log").open("x") as log:
        subprocess.run(
            [
                sys.executable,
                str(HERE / "train_round5.py"),
                "--out",
                str(root / "mj-r5-rf-b"),
                "--replay",
            ],
            stdout=log,
            stderr=subprocess.STDOUT,
            check=True,
        )
    for letter in "ab":
        out = root / f"mj-r5-rf-{letter}"
        fit = json.loads((out / "fit_summary.json").read_text())
        passes = [("final", out / "weights.pt")] + [
            (f"epoch-{r['epoch']:02d}", Path(r["path"])) for r in fit["checkpoints"]
        ]
        for tag, path in passes:
            target = root / f"r5-rf-{letter}-{tag}-low"
            with (logs / f"ball-r5-rf-{letter}-{tag}-low.log").open("x") as log:
                subprocess.run(
                    [
                        sys.executable,
                        str(HERE / "round5_inference.py"),
                        "--model",
                        str(path),
                        "--out",
                        str(target),
                    ],
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    check=True,
                )
            print(f"saved {letter} {tag}", flush=True)
    print("Both final fits and diagnostic checkpoints complete", flush=True)


if __name__ == "__main__":
    main()
