"""Deterministic proxy/human scores, never a fabricated ball truth label."""

from __future__ import annotations
import itertools
import math
import statistics
import sys
from pathlib import Path
from ball_track import track

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from grounding import interpolated_box  # noqa: E402
from bench.semantic_activity import truth_activity  # noqa: E402


def agreement(votes, radius=40.0):
    """Pair consensus centres from distinct fixed voters; never self-vote.

    All qualifying pair midpoints are retained to avoid arbitrarily discarding
    multiple plausible balls. A 3x3 RF variant is not a fourth voter.
    """
    if len(votes) != 3:
        raise ValueError("proxy requires exactly three candidate voters")
    centres = []
    for a, b in itertools.combinations(votes.values(), 2):
        for da in a:
            for db in b:
                if math.dist(da["xy"], db["xy"]) <= radius:
                    point = [(x + y) / 2 for x, y in zip(da["xy"], db["xy"])]
                    if point not in centres:
                        centres.append(point)
    return sorted(centres)


def match(detections, centres, radius=40.0):
    return any(
        math.dist(d["xy"], point) <= radius for d in detections for point in centres
    )


def ratio(n, d):
    return n / d if d else None


def clip_metrics(clip, raw, proxy, threshold, human=None):
    rows = [
        {
            **f,
            "detections": [d for d in f["detections"] if d["confidence"] >= threshold],
        }
        for f in raw["frames"]
    ]
    activity = truth_activity(clip["truth_data"].get("human_note"))
    on = "on_ball_action" in activity and "off_pitch" not in activity
    off = "off_pitch" in activity
    eligible = hits = human_visible = human_hits = labelled = invisible_detections = 0
    preview = preview_eligible = 0
    confidence: list[float] = []
    sizes: list[float] = []
    detections_count = 0
    for row in rows:
        ds = row["detections"]
        detections_count += len(ds)
        confidence.extend(d["confidence"] for d in ds)
        sizes.extend(d["size_px"] for d in ds if d["size_px"] is not None)
        centres = proxy[row["t"]]
        if centres:
            eligible += 1
            hits += match(ds, centres)
        label = (human or {}).get((clip["clip_id"], row["t"]))
        if label:
            labelled += 1
            if label["visible"]:
                human_visible += 1
                human_hits += match(ds, [[label["x"], label["y"]]])
            else:
                invisible_detections += len(ds)
        box = interpolated_box(clip["truth_data"]["box_track"], row["t"])
        if box:
            preview_eligible += 1
            foot = [(box[0] + box[2]) / 2, box[3]]
            preview += any(
                math.dist(d["xy"], foot) <= 1.5 * (box[3] - box[1]) for d in ds
            )
    tracking = track(rows, clip["duration_s"])
    return {
        "clip": clip["clip_id"],
        "on_ball": on,
        "off_pitch": off,
        "frames": len(rows),
        "duration_s": clip["duration_s"],
        "wall_s": raw["wall_s"],
        "fps": len(rows) / raw["wall_s"],
        "proxy_visible_frames": eligible,
        "proxy_detected_frames": hits,
        "detection_rate_proxy": ratio(hits, eligible),
        "proxy_coverage": ratio(eligible, len(rows)),
        "off_pitch_false_ball_count_proxy": detections_count if off else None,
        "false_per_10s_proxy": detections_count * 10 / clip["duration_s"]
        if off
        else None,
        "detections_count": detections_count,
        "mean_confidence": statistics.mean(confidence) if confidence else None,
        "ball_px_min": min(sizes) if sizes else None,
        "ball_px_median": statistics.median(sizes) if sizes else None,
        "continuity": tracking["continuity"],
        "track_fragments": tracking["fragments"],
        "touch_preview_frames": preview,
        "touch_preview_eligible_frames": preview_eligible,
        "human": {
            "labelled_frames": labelled,
            "visible_frames": human_visible,
            "detected_frames": human_hits,
            "detection_rate": ratio(human_hits, human_visible),
            "invisible_frame_detections": invisible_detections,
            "invisible_frames": labelled - human_visible,
        },
        "_sizes": sizes,
        "_confidence": confidence,
    }


def overall(rows):
    on, off = [r for r in rows if r["on_ball"]], [r for r in rows if r["off_pitch"]]
    confidence = [x for r in rows for x in r["_confidence"]]
    sizes = [x for r in rows for x in r["_sizes"]]
    visible = sum(r["proxy_visible_frames"] for r in on)
    detected = sum(r["proxy_detected_frames"] for r in on)
    rate = ratio(detected, visible)
    false = ratio(
        10 * sum(r["off_pitch_false_ball_count_proxy"] for r in off),
        sum(r["duration_s"] for r in off),
    )
    h_visible = sum(r["human"]["visible_frames"] for r in on)
    h_hits = sum(r["human"]["detected_frames"] for r in on)
    wall = sum(r["wall_s"] for r in rows)
    h_false = ratio(
        10 * sum(r["human"]["invisible_frame_detections"] for r in off),
        sum(r["human"]["invisible_frames"] for r in off) / 2,
    )
    h_complete = all(r["human"]["labelled_frames"] == r["frames"] for r in on + off)
    return {
        "frames": sum(r["frames"] for r in rows),
        "clips": len(rows),
        "on_ball_clips": len(on),
        "off_pitch_clips": len(off),
        "wall_s": wall,
        "wall_s_per_clip": wall / len(rows),
        "fps": sum(r["frames"] for r in rows) / wall,
        "detection_rate_proxy": rate,
        "proxy_visible_on_ball_frames": visible,
        "proxy_detected_on_ball_frames": detected,
        "proxy_coverage_on_ball": ratio(visible, sum(r["frames"] for r in on)),
        "false_per_10s_proxy": false,
        "gate_proxy": "UNMEASURABLE"
        if rate is None or false is None
        else "PASS"
        if rate >= 0.8 and false <= 1
        else "FAIL",
        "mean_confidence": statistics.mean(confidence) if confidence else None,
        "ball_px_min": min(sizes) if sizes else None,
        "ball_px_median": statistics.median(sizes) if sizes else None,
        "continuity": sum(r["continuity"] * r["duration_s"] for r in rows)
        / sum(r["duration_s"] for r in rows),
        "track_fragments": sum(r["track_fragments"] for r in rows),
        "touch_preview": {
            name: {
                "near_frames": sum(r["touch_preview_frames"] for r in subset),
                "box_available_frames": sum(
                    r["touch_preview_eligible_frames"] for r in subset
                ),
                "rate": ratio(
                    sum(r["touch_preview_frames"] for r in subset),
                    sum(r["touch_preview_eligible_frames"] for r in subset),
                ),
            }
            for name, subset in [("on_ball", on), ("off_pitch", off)]
        },
        "human": {
            "labelled_frames": sum(r["human"]["labelled_frames"] for r in rows),
            "visible_on_ball_frames": h_visible,
            "detected_on_ball_frames": h_hits,
            "detection_rate": ratio(h_hits, h_visible),
            "false_per_10s": h_false,
            "gate": "PENDING"
            if not human_label_count(rows)
            else "PARTIAL_HUMAN_REVIEW"
            if not h_complete
            else "UNMEASURABLE"
            if not h_visible or h_false is None
            else "PASS"
            if h_hits / h_visible >= 0.8 and h_false <= 1
            else "FAIL",
        },
    }


def human_label_count(rows):
    return sum(r["human"]["labelled_frames"] for r in rows)
