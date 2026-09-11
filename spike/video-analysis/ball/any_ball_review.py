"""Migrate private labels and rank a review queue using saved boxes only."""

from __future__ import annotations
import argparse
import json
import shutil
from pathlib import Path

from ball_truth_kit import import_labels, build
from checkpoint_provenance import validate_saved_passes
from common import DEFAULT_SOURCE, dump, sha256
from compare_ball import load_measurements
from extra_detections import load_extra
from human_loop import frame_catalog, write_jsonl
from label_rule import BASE_REVIEW_KEYS, review_keys
from compare_label_exports import compare


def saved_boxes(outputs):
    best = {}
    for source, clips in outputs.items():
        for cid, clip in clips.items():
            for frame in clip["frames"]:
                key = cid, round(frame["t"], 6)
                for detection in frame["detections"]:
                    if not detection.get("box") or detection["confidence"] < 0.3:
                        continue
                    row = {
                        "clip": cid,
                        "t": key[1],
                        "x": detection["xy"][0],
                        "y": detection["xy"][1],
                        "score": detection["confidence"],
                        "source": source,
                    }
                    if key not in best or (-row["score"], row["source"]) < (
                        -best[key]["score"],
                        best[key]["source"],
                    ):
                        best[key] = row
    return best


def review_queue(frames, labels, outputs, base_keys=BASE_REVIEW_KEYS):
    best = saved_boxes(outputs)
    keys = review_keys(labels, base_keys)
    catalog = {(f["clip"], round(f["t"], 6)): f for f in frames}
    if keys - catalog.keys():
        raise ValueError("review keys absent from frame catalog")
    queue = [
        {
            "clip": key[0],
            "t": key[1],
            "sample_index": catalog[key]["sample_index"],
            "suggestion": best.get(key),
        }
        for key in keys
    ]
    return sorted(
        queue,
        key=lambda r: (
            -(r["suggestion"]["score"] if r["suggestion"] else -1),
            r["clip"],
            r["t"],
        ),
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    home = Path.home()
    p.add_argument(
        "--input", type=Path, default=home / "codex-runs/ball-human-truth.jsonl"
    )
    p.add_argument(
        "--output",
        type=Path,
        default=home / "codex-runs/ball-human-truth-v2-build14.jsonl",
    )
    p.add_argument("--kit", type=Path, default=home / "ball-truth-review-build14")
    p.add_argument(
        "--sync", type=Path, default=home / "codex-runs/ball-truth-review-build14"
    )
    p.add_argument(
        "--baseline", type=Path, default=home / "codex-runs/ball-human-truth.jsonl"
    )
    p.add_argument("--frames-dir", type=Path, default=home / "ball-truth-review")
    a = p.parse_args()
    original_hash = sha256(a.input)
    source_diff = compare(a.baseline, a.input)
    if a.output.exists() or a.input.resolve() == a.output.resolve():
        p.error("migration requires a NEW output file; never overwrite labels")
    if any(
        (a.sync / name).exists()
        for name in ("index.html", "build.json", "any-ball-review.json")
    ):
        p.error("sync build already exists; use a new sync directory")
    if (a.kit / "index.html").exists() or (a.kit / "build.json").exists():
        p.error("kit directory already contains a build; use a new directory")
    if a.kit.resolve() == a.frames_dir.resolve() or not a.kit.name.endswith("-build14"):
        p.error("use a separate versioned kit directory ending -build14")
    m = load_measurements()
    frames = frame_catalog(m)
    labels = import_labels(a.input, frames)
    root = home / "models/tinyball"
    paths = {f"rf-r5-{c}": root / f"r5-rf-{c}-final-low/detections.json" for c in "ab"}
    validate_saved_passes(paths, root)
    extras = load_extra([f"{k}={v}" for k, v in paths.items()], m)
    outputs = {**m["outputs"], **{k: v["outputs"] for k, v in extras.items()}}
    queue = review_queue(frames, labels, outputs)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    write_jsonl(a.output, list(labels.values()))
    a.kit.mkdir(parents=True, exist_ok=True)
    dump(a.kit / "any-ball-review.json", queue)
    dump(a.kit / "review-suggestions.json", list(saved_boxes(outputs).values()))
    build(
        DEFAULT_SOURCE,
        a.kit,
        a.frames_dir / "suggestions.jsonl",
        a.output,
        a.kit / "any-ball-review.json",
        frames_dir=a.frames_dir,
        review_suggestions=a.kit / "review-suggestions.json",
    )
    audit = {
        "schema_version": 2,
        "source_diff_vs_baseline": source_diff,
        "input_sha256": original_hash,
        "output_sha256": sha256(a.output),
        "labels": len(labels),
        "review_frames": len(queue),
        "suggestions": sum(r["suggestion"] is not None for r in queue),
        "top10": queue[:10],
        "saved_sources": sorted(outputs),
        "ordering": "Box confidence >=0.3, highest raw score first; source name breaks box ties; clip/time breaks queue ties; no-box frames last. WASB points are not boxes.",
    }
    dump(a.kit / "migration.json", audit)
    a.sync.mkdir(parents=True, exist_ok=True)
    for name in (
        "index.html",
        "build.json",
        "any-ball-review.json",
        "review-suggestions.json",
        "migration.json",
    ):
        shutil.copy2(a.kit / name, a.sync / name)
    assert sha256(a.input) == original_hash
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
