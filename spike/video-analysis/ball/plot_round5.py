"""Standalone diagnostic curves from aggregate fixtures; never choose thresholds."""

from __future__ import annotations
import argparse
import gzip
import json
from pathlib import Path
from common import HERE


def main():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--fixture", type=Path, default=HERE / "fixtures/round5_scored_output.json.gz"
    )
    p.add_argument(
        "--out", type=Path, default=Path.home() / "codex-runs/ball-r5-fair-curves.png"
    )
    a = p.parse_args()
    e = json.loads(gzip.decompress(a.fixture.read_bytes()))
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), sharey=True)
    for name, row in e["models"].items():
        points = row["held_curve_diagnostic_only"]
        xs = [r["false_per_10s"] for r in points]
        ys = [100 * r["recall"] for r in points]
        for ax in axes:
            (line,) = ax.plot(xs, ys, label=name, linewidth=1.7)
            for budget, marker in (("1", "o"), ("2", "s")):
                g = row["operating_points"][budget]["held"]["groups"]
                ax.scatter(
                    g["all"]["false_per_10s"],
                    100 * g["on_ball"]["top1_recall"],
                    color=line.get_color(),
                    marker=marker,
                    s=45,
                    zorder=4,
                )
    for ax in axes:
        ax.axvline(1, color="gray", linestyle="--", alpha=0.5)
        ax.axhline(80, color="gray", linestyle="--", alpha=0.5)
        ax.set_ylim(0, 101)
        ax.set_xlabel("Held-out false boxes / 10 seconds")
        ax.grid(alpha=0.2)
    axes[0].set_xlim(0, 8)
    axes[0].set_title("Operating region")
    axes[1].set_xlim(left=0)
    axes[1].set_title("Full curve down to confidence 0.01")
    axes[0].set_ylabel("Held-out on-ball top-1 recall (%)")
    axes[1].legend(loc="lower right")
    fig.suptitle(
        "Recipe-selected on these clips: diagnostic curves, not threshold selection"
    )
    fig.text(
        0.5,
        0.01,
        "Circle: TRAIN 1.0 false/10s budget. Square: TRAIN 2.0. Two on-ball clips from one match cannot establish a winner.",
        ha="center",
        fontsize=9,
    )
    fig.tight_layout(rect=(0, 0.04, 1, 0.94))
    fig.savefig(a.out, dpi=180)
    print(a.out)


if __name__ == "__main__":
    main()
