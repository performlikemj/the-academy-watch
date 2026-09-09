"""Data-derived comparison artifacts and limits, without inference or rescoring."""

import hashlib
import json
from pathlib import Path

CROP_CONTEXT_CAVEAT = (
    "Crop spatial confound: the sideline is largely cropped out of crops-only images; "
    "crop+context supplies only a 512-wide full frame, not the wide baseline. All three "
    "crop variants are excluded from the gate-1 headline. Their on-pitch numbers do not "
    "isolate sideline recognition. A ball outside the crop also confounds ball-near."
)
REVIEW_ESTIMATE_CAVEAT = (
    "Reviewed dataset: dense true-touch still spacing is 1.58–6.62 s; "
    "run-wide mean spacing is 2.49 s dense and 23.99 s sparse. "
    "Review estimate: a perfect detector would score approximately 1/6 dense and 0/6 sparse, "
    "making the 2/6 crop scheduling rule 'unattainable by construction' under that assumption. "
    "This is not a measured detector bound: spacing alone cannot establish visibility, "
    "a perfect-detector score or mathematical impossibility. Human touch timestamps and "
    "frame-level visibility labels are still needed."
)


def is_crop(lane):
    return lane["settings"]["adapter"] == "qwen3vl_checks_crop"


def temporal_caveat(lane):
    sampling = lane["report"]["overall"]["sampling"]
    spacing = sampling["mean_spacing_s"]
    text = "unknown" if spacing is None else f"{spacing:.2f} s"
    reason = sampling["touch_recall_reason"] or "sampled action visibility not verified"
    return (
        f"Temporal confound: mean spacing {text}; touch recall {reason}. "
        "Running/motion rows also lack continuous evidence; raw accuracy is not proof of motion recognition."
    )


def crop_geometry(lane):
    per_clip, crops = [], []
    for row in lane["sampling"]:
        frames = row.get("sent_frames") or []
        selected = [f for f in frames if f.get("image_kind") == "crop"]
        contexts = [f for f in frames if f.get("image_kind") == "context"]
        crops.extend(selected)
        per_clip.append(
            {
                "clip_id": row["clip_id"],
                "sampled_instants": len({f["t"] for f in frames}),
                "sent_images": len(frames),
                "crop_images": len(selected),
                "context_images": len(contexts),
            }
        )
    if not crops:
        return None
    return {
        "crop_side_px_min": min(f["crop_side_px"] for f in crops),
        "crop_side_px_max": max(f["crop_side_px"] for f in crops),
        "crop_scale_min": min(f["crop_scale"] for f in crops),
        "crop_scale_max": max(f["crop_scale"] for f in crops),
        "crop_output_size": [crops[0]["sent_w"], crops[0]["sent_h"]],
        "context_width": 512 if lane["settings"].get("crop_context") else None,
        "per_clip_counts": per_clip,
        "sampled_instants": sum(c["sampled_instants"] for c in per_clip),
        "sent_images": sum(c["sent_images"] for c in per_clip),
        "coordinate_space": "Decoded lane-B frames; source truth scaled before crop geometry",
        "confound": CROP_CONTEXT_CAVEAT,
    }


def load_examples(directory: Path):
    rows = json.loads((directory / "examples.json").read_text())
    for row in rows:
        path = Path(row["path"])
        if path.resolve().parent != directory.resolve():
            raise ValueError("example crop must be inside --example-crops directory")
        if hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
            raise ValueError("example crop hash mismatch")
    return rows


def add_facts(result, *, baseline_run=None, example_crops=None):
    lanes = result["lanes"]
    paired = result["comparison_metadata"]["paired_overall"]
    result["question_caveats"] = {}
    for name, lane in lanes.items():
        caveats = {
            "player_touches_ball": temporal_caveat(lane),
            "player_running": temporal_caveat(lane),
        }
        if is_crop(lane):
            for q in ("player_on_pitch", "play_in_progress", "ball_near_player"):
                caveats[q] = CROP_CONTEXT_CAVEAT
        result["question_caveats"][name] = caveats
        result["touch_recall"][name]["confound"] = temporal_caveat(lane)
        result["touch_recall"][name]["perfect_detector_estimate"] = (
            REVIEW_ESTIMATE_CAVEAT
        )
    # Preserve both published spellings; both are derived from current truth.
    result["true_touch_clips"] = result["touch_clips"]
    for row in result["true_touch_clips"]:
        row["sampling"] = {}
        for name, lane in lanes.items():
            attempt = next(
                (r for r in lane["sampling"] if r["clip_id"] == row["clip_id"]), {}
            )
            times = sorted({f["t"] for f in attempt.get("sent_frames") or []})
            row["sampling"][name] = {
                "distinct_frames": len(times),
                "mean_still_spacing_s": (times[-1] - times[0]) / (len(times) - 1)
                if len(times) > 1
                else None,
                "confound": temporal_caveat(lane),
            }
        row["confound"] = (
            "Temporal sampling; raw no/unclear is not evidence of inability to detect a visible touch. "
            + REVIEW_ESTIMATE_CAVEAT
        )
    result["crop_geometry"] = {
        name: geometry
        for name, lane in lanes.items()
        if is_crop(lane) and (geometry := crop_geometry(lane)) is not None
    }
    if result["crop_geometry"]:
        candidates = {
            name: lane
            for name, lane in lanes.items()
            if is_crop(lane) and lane["settings"]["model"] == "qwen3-vl:8b"
        }
        recalls = {
            lane["run"]: {
                "count": paired[name]["touch_yes_count"],
                "denominator": paired[name]["touch_truth_positive_count"],
                "touch_recall": paired[name]["touch_recall"],
                "confound": temporal_caveat(lane),
            }
            for name, lane in candidates.items()
        }
        complete = (
            result["comparison_metadata"]["complete"]
            and all(
                lane["report"]["overall"]["scored_clips"]
                == len(lane["settings"]["clips"])
                for lane in candidates.values()
            )
            and bool(candidates)
            and all(r["denominator"] == 6 for r in recalls.values())
        )
        result["decision_32b"] = {
            "run": any(r["count"] >= 2 for r in recalls.values()) if complete else None,
            "recalls": recalls,
            "rule": "Historical scheduling rule: at least 2 affirmative touches out of the six truth-positive clips in any complete 8B crop variant.",
            "confound": "The original scheduling rule cannot assess detector capability with these stills. "
            + REVIEW_ESTIMATE_CAVEAT,
            "adoption_decision": False,
        }
        result["caveats"] += [CROP_CONTEXT_CAVEAT, REVIEW_ESTIMATE_CAVEAT]
    if baseline_run is not None:
        if baseline_run not in paired:
            raise ValueError("--baseline-run must name a selected run")
        result["baseline_run"] = baseline_run
        baseline = paired[baseline_run]["questions"]
        result["per_question_deltas_pp"] = {
            name: {
                q: {
                    key: 100 * (m[key] - baseline[q][key])
                    if m[key] is not None and baseline[q][key] is not None
                    else None
                    for key in ("accuracy", "abstain_rate", "false_yes_rate", "recall")
                }
                for q, m in metrics["questions"].items()
            }
            for name, metrics in paired.items()
        }
    if example_crops:
        result["example_crops"] = load_examples(example_crops)
