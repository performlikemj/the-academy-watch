"""Detector self-agreement and box counts are diagnostics; only humans score balls."""

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

PROXY_VERDICT = "UNMEASURABLE (proxy)"


def agreement(votes, radius=40.0):
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


def pair_decomposition(votes):
    rf = match(votes["rf_full"], [d["xy"] for d in votes["rf_2x2"]])
    wasb = any(
        match(votes[n], [d["xy"] for d in votes["wasb"]]) for n in ("rf_full", "rf_2x2")
    )
    return {
        "rf_pair_only": rf and not wasb,
        "with_wasb": wasb,
        "rf_pair": rf,
        "any_pair": rf or wasb,
    }


def match(detections, centres, radius=40.0):
    return any(math.dist(d["xy"], xy) <= radius for d in detections for xy in centres)


def ratio(n, d):
    return n / d if d else None


def clip_class(clip):
    activity = truth_activity(clip["truth_data"].get("human_note"))
    return (
        "off_pitch"
        if "off_pitch" in activity
        else "on_ball"
        if "on_ball_action" in activity
        else "other"
    )


def clip_metrics(clip, raw, proxy, threshold, human=None):
    rows = [
        {
            **f,
            "detections": [d for d in f["detections"] if d["confidence"] >= threshold],
        }
        for f in raw["frames"]
    ]
    group = clip_class(clip)
    eligible = hits = human_visible = human_hits = labelled = unmatched = 0
    preview = preview_eligible = 0
    confidence: list[float] = []
    sizes: list[float] = []
    count = 0
    for row in rows:
        ds = row["detections"]
        count += len(ds)
        confidence.extend(d["confidence"] for d in ds)
        sizes.extend(d["size_px"] for d in ds if d["size_px"] is not None)
        centres = proxy[row["t"]]
        if centres:
            eligible += 1
            hits += match(ds, centres)
        label = (human or {}).get((clip["clip_id"], row["t"]))
        if label:
            labelled += 1
            found = False
            if label["visible"]:
                human_visible += 1
                found = match(ds, [[label["x"], label["y"]]])
                human_hits += found
            # One labelled match ball permits at most one matched prediction.
            # Other candidates, including duplicates and other real balls, are
            # false for this declared single-match-ball target on labelled frames.
            unmatched += len(ds) - int(found)
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
        "on_ball": group == "on_ball",
        "off_pitch": group == "off_pitch",
        "frames": len(rows),
        "duration_s": clip["duration_s"],
        "wall_s": raw["wall_s"],
        "fps": len(rows) / raw["wall_s"],
        "proxy_agreement_frames": eligible,
        "proxy_matched_frames": hits,
        "self_agreement_rate_proxy": ratio(hits, eligible),
        "proxy_coverage": ratio(eligible, len(rows)),
        "boxes_per_10s_offpitch": count * 10 / clip["duration_s"]
        if group == "off_pitch"
        else None,
        "detections_count": count,
        "boxes_per_frame": ratio(count, len(rows)),
        "mean_confidence": statistics.mean(confidence) if confidence else None,
        "box_px_min": min(sizes) if sizes else None,
        "box_px_median": statistics.median(sizes) if sizes else None,
        "continuity": tracking["continuity"],
        "track_fragments": tracking["fragments"],
        "longest_track_s": tracking["longest_track_s"],
        "touch_preview_frames": preview,
        "touch_preview_eligible_frames": preview_eligible,
        "touch_preview_rate": ratio(preview, preview_eligible),
        "human": {
            "labelled_frames": labelled,
            "visible_frames": human_visible,
            "detected_frames": human_hits,
            "detection_rate": ratio(human_hits, human_visible),
            "unmatched_detections": unmatched,
            "labelled_exposure_s": labelled / 2,
        },
        "_sizes": sizes,
        "_confidence": confidence,
    }


def overall(rows):
    on = [r for r in rows if r["on_ball"]]
    off = [r for r in rows if r["off_pitch"]]
    confidence = [v for r in rows for v in r["_confidence"]]
    sizes = [v for r in rows for v in r["_sizes"]]
    agreement_frames = sum(r["proxy_agreement_frames"] for r in on)
    hits = sum(r["proxy_matched_frames"] for r in on)
    h_visible = sum(r["human"]["visible_frames"] for r in on)
    h_hits = sum(r["human"]["detected_frames"] for r in on)
    h_off = sum(r["human"]["labelled_frames"] for r in off)
    h_false = ratio(
        10 * sum(r["human"]["unmatched_detections"] for r in off), h_off / 2
    )
    complete_on = bool(on) and all(
        r["human"]["labelled_frames"] == r["frames"] for r in on
    )
    enough = complete_on and h_off >= 100
    labelled = sum(r["human"]["labelled_frames"] for r in rows)
    gate = (
        "PENDING"
        if not labelled
        else "PARTIAL_HUMAN_REVIEW"
        if not enough
        else "UNMEASURABLE (human)"
        if not h_visible
        else "PASS (human sample)"
        if h_hits / h_visible >= 0.8 and h_false is not None and h_false <= 1
        else "FAIL (human sample)"
    )
    wall = sum(r["wall_s"] for r in rows)
    frames = sum(r["frames"] for r in rows)
    return {
        "frames": frames,
        "clips": len(rows),
        "on_ball_clips": len(on),
        "off_pitch_clips": len(off),
        "wall_s": wall,
        "wall_s_per_clip": wall / len(rows),
        "fps": frames / wall,
        "self_agreement_rate_proxy": ratio(hits, agreement_frames),
        "proxy_agreement_on_ball_frames": agreement_frames,
        "proxy_matched_on_ball_frames": hits,
        "proxy_coverage_on_ball": ratio(agreement_frames, sum(r["frames"] for r in on)),
        "boxes_per_10s_offpitch": ratio(
            10 * sum(r["detections_count"] for r in off),
            sum(r["duration_s"] for r in off),
        ),
        "boxes_per_frame": sum(r["detections_count"] for r in rows) / frames,
        "gate_proxy": PROXY_VERDICT,
        "mean_confidence": statistics.mean(confidence) if confidence else None,
        "box_px_min": min(sizes) if sizes else None,
        "box_px_median": statistics.median(sizes) if sizes else None,
        "continuity": sum(r["continuity"] * r["duration_s"] for r in rows)
        / sum(r["duration_s"] for r in rows),
        "track_fragments": sum(r["track_fragments"] for r in rows),
        "longest_track_s": max(r["longest_track_s"] for r in rows),
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
            "labelled_frames": labelled,
            "visible_on_ball_frames": h_visible,
            "detected_on_ball_frames": h_hits,
            "detection_rate": ratio(h_hits, h_visible),
            "labelled_offpitch_frames": h_off,
            "false_per_10s": h_false,
            "all_onball_labelled": complete_on,
            "minimum_offpitch_labels": 100,
            "gate": gate,
        },
    }


def retrack_saved(measurements):
    """Re-track only the saved 0.1 RF boxes; no model or decoder imports."""
    results = {}
    for name in ("rf_full", "rf_2x2", "rf_3x3"):
        per_clip = []
        for c in measurements["clips"]:
            raw = measurements["outputs"][name][c["clip_id"]]
            result = track(raw["frames"], c["duration_s"])
            per_clip.append(
                {
                    "clip": c["clip_id"],
                    "class": clip_class(c),
                    "duration_s": c["duration_s"],
                    **result,
                    "single_speed_bounded_hypothesis": result["fragments"] == 1
                    and result["continuity"] >= 0.8,
                }
            )
        groups = {}
        for group in ("on_ball", "off_pitch", "other", "all"):
            selected = [r for r in per_clip if group == "all" or r["class"] == group]
            groups[group] = {
                "clips": len(selected),
                "fragments": sum(r["fragments"] for r in selected),
                "continuity": sum(r["continuity"] * r["duration_s"] for r in selected)
                / sum(r["duration_s"] for r in selected),
                "longest_track_s": max(r["longest_track_s"] for r in selected),
                "single_hypothesis_clips": sum(
                    r["single_speed_bounded_hypothesis"] for r in selected
                ),
            }
        results[name] = {"threshold": 0.1, "groups": groups, "per_clip": per_clip}
    return results


def label_plan(measurements):
    """All on-ball samples plus 100 evenly spread off-pitch samples, no model cues."""
    on, off = [], []
    for c in measurements["clips"]:
        frames = [
            {"clip": c["clip_id"], "t": r["t"]}
            for r in measurements["outputs"]["rf_full"][c["clip_id"]]["frames"]
        ]
        if clip_class(c) == "on_ball":
            on.extend(frames)
        elif clip_class(c) == "off_pitch":
            off.append(frames)
    counts = [0] * len(off)
    while sum(counts) < 100:
        progressed = False
        for i, frames in enumerate(off):
            if counts[i] < len(frames) and sum(counts) < 100:
                counts[i] += 1
                progressed = True
        if not progressed:
            raise ValueError("fewer than 100 off-pitch samples")
    selected: list[dict] = []
    for frames, count in zip(off, counts):
        selected.extend(
            frames[round(i * (len(frames) - 1) / (count - 1))] for i in range(count)
        )
    return {
        "on_ball": on,
        "off_pitch": selected,
        "instruction": "Label all 540 on-ball frames and these 100 off-pitch frames (or another representative 100); visible match-ball xy OR explicitly not visible. Uncertain frames remain unlabelled. Human sample gate needs all on-ball plus >=100 off-pitch labels.",
    }
