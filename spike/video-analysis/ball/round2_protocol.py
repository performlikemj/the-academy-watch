"""Freeze a balanced 14/6 clip partition without hiding prior tuning exposure."""

from __future__ import annotations

import hashlib
import itertools
from collections import Counter

from metrics import clip_class

SEED = "ball-human-r2-split-v1"


def overlaps(a, b):
    return max(a["window"]["start_s"], b["window"]["start_s"]) < min(
        a["window"]["end_s"], b["window"]["end_s"]
    )


def choose_split(measurements, prior_split):
    """Rank feasible complete partitions by SHA256, never by label/model metrics.

    Prior fitted clips must stay in training for continuation weights. All native
    source-window overlap stays on one side. Prior evaluation exposure cannot be
    undone by a new partition: explicitly enumerate it for the operator.
    """
    clips = measurements["clips"]
    eligible = [c for c in clips if c["clip_id"] not in prior_split["train"]]
    options = []
    for subset in itertools.combinations(eligible, 6):
        counts = Counter(clip_class(c) for c in subset)
        if counts != {"on_ball": 2, "off_pitch": 2, "other": 2}:
            continue
        names = sorted(c["clip_id"] for c in subset)
        train = [c for c in clips if c["clip_id"] not in names]
        if any(overlaps(a, b) for a in subset for b in train):
            continue
        rank = hashlib.sha256((SEED + "\n" + "\n".join(names)).encode()).hexdigest()
        options.append((rank, names))
    if not options:
        raise ValueError("no 14/6 partition satisfies continuation/overlap constraints")
    rank, held = min(options)
    return {
        "train": [c["clip_id"] for c in clips if c["clip_id"] not in held],
        "held_out": held,
        "smoke_resubstitution_only": False,
        "seed": SEED,
        "rank": rank,
        "feasible_partitions": len(options),
        "prior_tuning_exposed_holdout": sorted(
            set(held) & set(prior_split["held_out"])
        ),
        "previously_untouched_holdout": not bool(
            set(held) & set(prior_split["held_out"])
        ),
    }


def validate_split(
    split, measurements, labels, initial_split=None, *, allow_prior_tuning=False
):
    exposed = set(split.get("prior_tuning_exposed_holdout", []))
    exposed |= set(split["held_out"]) & set((initial_split or {}).get("held_out", []))
    if exposed and not allow_prior_tuning:
        raise ValueError(
            "holdout has prior hyperparameter-selection exposure; explicit exception required"
        )
    train, held = split["train"], split["held_out"]
    ids = {c["clip_id"] for c in measurements["clips"]}
    if (
        len(train) != 14
        or len(held) != 6
        or len(set(train + held)) != 20
        or set(train + held) != ids
    ):
        raise ValueError(
            "split requires 14 unique train and six disjoint held-out clips"
        )
    labelled = {cid for cid, _ in labels}
    if not ids <= labelled:
        raise ValueError("all 20 split clips require human labels")
    by_id = {c["clip_id"]: c for c in measurements["clips"]}
    if Counter(clip_class(by_id[c]) for c in held) != {
        "on_ball": 2,
        "off_pitch": 2,
        "other": 2,
    }:
        raise ValueError(
            "held-out classes must be two on-ball, two off-pitch, two other"
        )
    if any(overlaps(by_id[a], by_id[b]) for a in train for b in held):
        raise ValueError("overlapping source footage cannot cross the split")
    if initial_split and set(initial_split["train"]) & set(held):
        raise ValueError("continuation weights already trained on a held-out clip")
    return split


def markdown(protocol):
    lines = [
        "Round 2: " + protocol["status"] + ".",
        "",
        protocol["issue"],
        "",
        "Proposed deterministic split (not an untouched holdout):",
        "",
        "| Role | Clip |",
        "|---|---|",
    ]
    for role in ("train", "held_out"):
        for cid in protocol["split"][role]:
            lines.append(f"| {role} | {cid} |")
    lines += [
        "",
        protocol["resolution_reason"],
        "",
        "Round-1 measurements retained below:",
        "",
    ]
    return "\n".join(lines)
