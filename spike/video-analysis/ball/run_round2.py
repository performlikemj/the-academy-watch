"""Four prespecified MPS fits; freeze selection before any evaluation."""

from __future__ import annotations
import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from common import dump


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=Path.home() / "models/tinyball")
    p.add_argument("--logs", type=Path, default=Path.home() / "codex-runs")
    a = p.parse_args()
    here = Path(__file__).resolve().parent
    protocol = here / "fixtures/round2_execution.json"
    fits: dict[str, Any] = {}
    for letter in "abcd":
        parent = (
            min(fits, key=lambda k: fits[k]["best_train_loss"])
            if letter == "d"
            else None
        )
        imgsz = (
            fits[parent]["model_input_px"] if parent else 1280 if letter == "c" else 960
        )
        init = a.root / (
            f"mj-r2-{parent}/weights.pt"
            if parent
            else "yolo11n.pt"
            if letter == "a"
            else "mj-r1-960/weights.pt"
        )
        out = a.root / f"mj-r2-{letter}"
        cmd = [
            sys.executable,
            str(here / "train_tiny_ball.py"),
            "--human-jsonl",
            str(Path.home() / "codex-runs/ball-human-truth.jsonl"),
            "--out",
            str(out),
            "--init",
            str(init),
            "--imgsz",
            str(imgsz),
            "--epochs",
            "200" if letter == "d" else "100",
            "--train-minutes",
            "40" if letter == "d" else "23" if letter == "c" else "20",
            "--batch",
            "8" if imgsz == 1280 else "16",
            "--patience",
            "6",
            "--split-json",
            str(protocol),
            "--allow-prior-tuning",
            "--train-loss-only",
            "--defer-evaluation",
        ]
        print(f"START {letter}: {imgsz}, init={init}", flush=True)
        with (a.logs / f"ball-mj-r2-{letter}.log").open("x") as log:
            subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, check=True)
        fits[letter] = json.loads((out / "fit_summary.json").read_text())
        dump(
            a.root / "round2-fit-state.json",
            {"fits": fits, "evaluation_started": False},
        )
        print(
            f"DONE {letter}: {fits[letter]['training_s'] / 60:.2f} minutes; TRAIN loss {fits[letter]['best_train_loss']}",
            flush=True,
        )
    selected = min(fits, key=lambda k: fits[k]["best_train_loss"])
    dump(
        a.root / "round2-selection.json",
        {
            "fits": fits,
            "selected": selected,
            "selection": "Minimum TRAIN loss only; frozen before any round-2 model evaluation",
            "evaluation_started": False,
        },
    )
    print(f"ALL FOUR FITS COMPLETE; selected {selected} on TRAIN loss only", flush=True)


if __name__ == "__main__":
    main()
