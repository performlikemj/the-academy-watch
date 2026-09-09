"""Deterministic review targets and unconfirmed suggestions from saved outputs."""

from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
from ball_track import track
from common import dump
from metrics import clip_class


def frame_catalog(measurements):
    return [
        {
            **{k: r[k] for k in ("t", "frame_index", "sample_index")},
            "clip": c["clip_id"],
            "source_size": c["source_size"],
            "class": clip_class(c),
            "path": f"{c['clip_id']}/{r['sample_index']:05d}.jpg",
        }
        for c in measurements["clips"]
        for r in measurements["outputs"]["rf_full"][c["clip_id"]]["frames"]
    ]


def review_plan(frames):
    on = [f for f in frames if f["class"] == "on_ball"]
    off = [f for f in frames if f["class"] == "off_pitch"]
    third = [f for f in off if f["sample_index"] % 3 == 0]
    remaining = [f for f in off if f not in third]
    needed = min(100, len(off)) - len(third)
    extra = (
        [
            remaining[round(i * (len(remaining) - 1) / (needed - 1))]
            for i in range(needed)
        ]
        if needed > 1
        else remaining[: max(0, needed)]
    )

    def compact(rows):
        return [{"clip": f["clip"], "t": f["t"]} for f in rows]

    return {
        "on_ball": compact(on),
        "off_pitch": compact(third + extra),
        "every_third_offpitch": compact(third),
        "offpitch_topup": compact(extra),
        "offpitch_clips": list(dict.fromkeys(f["clip"] for f in off)),
        "target": len(on) + len(third) + len(extra),
        "recipe": "Every third off-pitch sample starting at index 0; 74 frames in this set. Add 26 evenly spread non-selected samples to reach 100; all 540 on-ball frames. No model selects targets.",
    }


def saved_suggestions(measurements):
    result = []
    names = ("rf_3x3", "rf_2x2", "wasb_2x2")
    for c in measurements["clips"]:
        cid = c["clip_id"]
        longest: dict[str, dict] = {}
        for name in names:
            raw = measurements["outputs"][name][cid]
            tr = track(raw["frames"], c["duration_s"])
            if not tr["fragment_intervals"]:
                longest[name] = {}
                continue
            fragment = max(
                range(len(tr["fragment_intervals"])),
                key=lambda i: (
                    tr["fragment_intervals"][i][1] - tr["fragment_intervals"][i][0]
                ),
            )
            longest[name] = {
                p["t"]: p["observed_xy"]
                for p in tr["points"]
                if p["fragment"] == fragment
            }
        for i, row in enumerate(measurements["outputs"]["rf_3x3"][cid]["frames"]):
            eligible: list[tuple[dict, str]] = []
            for name in names:
                xy = longest[name].get(row["t"])
                if xy is not None:
                    eligible.extend(
                        (d, name)
                        for d in measurements["outputs"][name][cid]["frames"][i][
                            "detections"
                        ]
                        if math.dist(d["xy"], xy) < 1e-5
                    )
            if not eligible:
                eligible = [
                    (d, "rf_3x3") for d in row["detections"] if d["confidence"] >= 0.3
                ]
            if eligible:
                d, name = max(
                    eligible,
                    key=lambda pair: (
                        pair[0]["confidence"],
                        pair[1],
                        tuple(pair[0]["xy"]),
                    ),
                )
                result.append(
                    {
                        "clip": cid,
                        "t": row["t"],
                        "x": d["xy"][0],
                        "y": d["xy"][1],
                        "score": d["confidence"],
                        "source": name,
                    }
                )
    return result


def write_jsonl(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(r, sort_keys=True, allow_nan=False) + "\n" for r in rows)
    )


def load_suggestions(path, frames):
    if path is None:
        return []
    allowed = {(f["clip"], f["t"]): f for f in frames}
    seen = set()
    rows = []
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if set(r) != {"clip", "t", "x", "y", "score", "source"} or not isinstance(
            r["clip"], str
        ):
            raise ValueError("invalid suggestion schema")
        if any(
            type(r[k]) not in (int, float) or not math.isfinite(r[k])
            for k in ("t", "x", "y", "score")
        ):
            raise ValueError("finite suggestion numbers required")
        key = r["clip"], r["t"]
        if key not in allowed or key in seen:
            raise ValueError("unknown or duplicate suggestion frame")
        if (
            not isinstance(r["source"], str)
            or not r["source"]
            or not 0 <= r["score"] <= 1
            or not all(
                0 <= r[k] < limit
                for k, limit in zip(("x", "y"), allowed[key]["source_size"])
            )
        ):
            raise ValueError("invalid suggestion coordinates/score/source")
        seen.add(key)
        rows.append(r)
    return rows


if __name__ == "__main__":
    from compare_ball import load_measurements

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--out", type=Path, default=Path.home() / "ball-truth-review/suggestions.jsonl"
    )
    a = p.parse_args()
    m = load_measurements()
    rows = saved_suggestions(m)
    write_jsonl(a.out, rows)
    dump(a.out.with_suffix(".plan.json"), review_plan(frame_catalog(m)))
    print(f"{len(rows)} unconfirmed suggestions: {a.out}")
