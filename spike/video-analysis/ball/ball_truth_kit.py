"""Extract every 2 fps sample of all windows for independent human ball clicks."""

from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
from label_rule import V2_FIELDS, migrate_row
from common import DEFAULT_SOURCE, HERE, dump
from label_rule import BASE_REVIEW_KEYS
import os


def import_labels(path, frames):
    """Strict human-only intake: unknown/duplicate times and bad points fail."""
    allowed = {(f["clip"], round(f["t"], 6)): f for f in frames}
    labels = {}
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if (
            not {"clip", "t", "x", "y", "visible"} <= set(row)
            or set(row)
            - V2_FIELDS
            - {
                "clip",
                "t",
                "x",
                "y",
                "visible",
                "source_accepted",
                "accepted_source",
                "accepted_score",
            }
            or type(row["visible"]) is not bool
        ):
            raise ValueError("expected {clip,t,x,y,visible}")
        if type(row["t"]) not in (int, float) or not math.isfinite(row["t"]):
            raise ValueError("finite timestamp required")
        key = row["clip"], round(row["t"], 6)
        if key not in allowed or key in labels:
            raise ValueError("unknown or duplicate clip/time")
        if row["visible"]:
            size = allowed[key]["source_size"]
            for v, limit in zip((row["x"], row["y"]), size):
                if (
                    type(v) not in (int, float)
                    or not math.isfinite(v)
                    or not 0 <= v < limit
                ):
                    raise ValueError("invalid source coordinates")
        elif row["x"] is not None or row["y"] is not None:
            raise ValueError("invisible coordinates must be null")
        if "source_accepted" in row and type(row["source_accepted"]) is not bool:
            raise ValueError("source_accepted must be boolean")
        if row.get("source_accepted"):
            if (
                not row["visible"]
                or not isinstance(row.get("accepted_source"), str)
                or not row["accepted_source"]
                or type(row.get("accepted_score")) not in (int, float)
                or not math.isfinite(row["accepted_score"])
                or not 0 <= row["accepted_score"] <= 1
            ):
                raise ValueError("accepted suggestion provenance required")
        elif "accepted_source" in row or "accepted_score" in row:
            raise ValueError("provenance requires source_accepted")
        labels[key] = migrate_row(row, allowed[key])
    return labels


PAGE = (HERE / "truth_page.html").read_text()


def render_page(
    frames,
    labels,
    queue,
    suggestions,
    targets,
    key,
    legacy_key,
    base_keys=BASE_REVIEW_KEYS,
    review_suggestions=None,
):
    payloads = {
        "FRAMES": frames,
        "LABELS": labels,
        "QUEUE": queue,
        "SUGGESTIONS": suggestions,
        "TARGETS": targets,
        "KEY": key,
        "LEGACY_KEY": legacy_key,
        "BASE_KEYS": sorted(f"{cid}|{t:.6f}" for cid, t in base_keys),
        "REVIEW_SUGGESTIONS": review_suggestions or [],
    }
    page = PAGE
    for token, filename in (
        ("IO", "truth_io.js"),
        ("STORAGE", "truth_storage.js"),
        ("LEGACY", "truth_legacy.js"),
        ("PAGE_JS", "truth_page.js"),
    ):
        page = page.replace(f"__{token}__", (HERE / filename).read_text())
    for token, payload in payloads.items():
        page = page.replace(f"__{token}__", json.dumps(payload).replace("<", "\\u003c"))
    return page


def build(
    source,
    out,
    suggestions=None,
    human_jsonl=None,
    review=None,
    reuse_only=True,
    frames_dir=None,
    review_suggestions=None,
):
    """New versioned HTML only; shared frame files and older builds are read-only."""
    from human_loop import review_plan, load_suggestions, frame_catalog
    from compare_ball import load_measurements

    out = Path(out)
    frames_dir = Path(frames_dir or Path.home() / "ball-truth-review")
    if out.resolve() == frames_dir.resolve() or not out.name.endswith("-build14"):
        raise ValueError(
            "build 14 requires a separate VERSIONED directory ending -build14"
        )
    if (out / "index.html").exists() or (out / "build.json").exists():
        raise ValueError("refusing to overwrite an existing kit build")
    old_build = json.loads((frames_dir / "build.json").read_text())
    m = load_measurements()
    if old_build["frozen_set_id"] != m["frozen_set_id"] or old_build["source"] != str(
        source
    ):
        raise ValueError("shared frame provenance mismatch")
    expected = frame_catalog(m)
    cached = json.loads((frames_dir / "frames.json").read_text())
    frame_keys = {(f["clip"], f["t"]) for f in expected}
    if (
        len(cached) != len(expected)
        or {(f["clip"], f["t"]) for f in cached} != frame_keys
    ):
        raise ValueError("shared frame schedule mismatch")
    frames = []
    for f in cached:
        path = frames_dir / f["path"]
        if not path.is_file():
            raise ValueError(f"missing shared frame: {path}")
        frames.append({**f, "path": os.path.relpath(path, out)})
    suggestion_rows = load_suggestions(suggestions, frames)
    plan = review_plan(frames)
    labels = list(import_labels(human_jsonl, frames).values()) if human_jsonl else []
    queue = json.loads(Path(review).read_text()) if review else []
    all_review_suggestions = (
        json.loads(Path(review_suggestions).read_text()) if review_suggestions else []
    )
    legacy_key = f"ball-human-v1:{m['frozen_set_id']}:{str(source)}:fps2"
    key = legacy_key.replace("ball-human-v1:", "ball-human-v2:", 1)
    page = render_page(
        frames,
        labels,
        queue,
        suggestion_rows,
        plan["on_ball"] + plan["off_pitch"],
        key,
        legacy_key,
        review_suggestions=all_review_suggestions,
    )
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(page)
    dump(
        out / "build.json",
        {
            "build_version": 14,
            "label_schema_version": 2,
            "review_frames": len(queue),
            "review_suggestions": sum(r["suggestion"] is not None for r in queue),
            "confirmed_seed_labels": len(labels),
            "storage_key": key,
            "legacy_input_key": legacy_key,
            "shared_frames": os.path.relpath(frames_dir, out),
            "suggestions": len(suggestion_rows),
            "suggestions_by_source": {
                name: sum(r["source"] == name for r in suggestion_rows)
                for name in sorted({r["source"] for r in suggestion_rows})
            },
            "review_plan": plan,
            "frozen_set_id": m["frozen_set_id"],
            "source": str(source),
            "fps": 2,
            "frames": len(frames),
            "clips": len({f["clip"] for f in frames}),
        },
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    p.add_argument(
        "--out", type=Path, default=Path.home() / "ball-truth-review-build14"
    )
    p.add_argument("--frames-dir", type=Path, default=Path.home() / "ball-truth-review")
    p.add_argument("--suggestions", type=Path)
    p.add_argument("--human-jsonl", type=Path)
    p.add_argument("--review", type=Path)
    p.add_argument("--review-suggestions", type=Path)
    a = p.parse_args()
    build(
        a.source,
        a.out,
        a.suggestions,
        a.human_jsonl,
        a.review,
        frames_dir=a.frames_dir,
        review_suggestions=a.review_suggestions,
    )
