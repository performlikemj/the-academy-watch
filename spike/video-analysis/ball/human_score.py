"""Human-only 20 source-pixel metrics; never infer labels or ball box extents."""

from __future__ import annotations

from label_rule import rule_metadata, banner_tables
from collections import Counter
import math
import statistics

from ball_track import track
from metrics import clip_class, ratio


def distribution(values):
    values = sorted(values)
    if not values:
        return {"n": 0, "median": None, "p95": None}
    # Nearest-rank percentile, including for small samples.
    return {
        "n": len(values),
        "median": statistics.median(values),
        "p95": values[math.ceil(0.95 * len(values)) - 1],
    }


def score_rows(rows, labels):
    labelled = visible = hits = predictions = no_ball = false = 0
    top_hits = top_predictions = 0
    manual_visible = manual_hits = manual_top_hits = visible_predictions = 0
    top_errors = []
    errors, sizes = [], []
    for row in rows:
        label = labels.get((row["clip"], row["t"]))
        if label is None:
            continue
        labelled += 1
        ds = row["detections"]
        predictions += len(ds)
        top_predictions += bool(ds)
        if not label["visible"]:
            no_ball += 1
            false += len(ds)
            continue
        visible += 1
        visible_predictions += len(ds)
        manual = not label.get("source_accepted", False)
        manual_visible += manual
        top = max(ds, key=lambda d: d.get("confidence", 0), default=None)
        if top is not None:
            top_error = math.dist(top["xy"], [label["x"], label["y"]])
            if top_error <= 20:
                top_hits += 1
                manual_top_hits += manual
                top_errors.append(top_error)
        nearest = min(
            ds, key=lambda d: math.dist(d["xy"], [label["x"], label["y"]]), default=None
        )
        if nearest is not None:
            error = math.dist(nearest["xy"], [label["x"], label["y"]])
            if error <= 20:
                hits += 1
                manual_hits += manual
                errors.append(error)
                if (
                    nearest.get("box") is not None
                    and nearest.get("size_px") is not None
                ):
                    sizes.append(nearest["size_px"])
    return {
        "labelled": labelled,
        "visible": visible,
        "matched": hits,
        "predictions": predictions,
        "recall": ratio(hits, visible),  # historical alias: oracle over N boxes
        "oracle_recall": ratio(hits, visible),
        "top1_matched": top_hits,
        "top1_predictions": top_predictions,
        "top1_recall": ratio(top_hits, visible),
        "top1_precision": ratio(top_hits, top_predictions),
        "manual_visible": manual_visible,
        "manual_top1_matched": manual_top_hits,
        "manual_oracle_matched": manual_hits,
        "predictions_on_visible_frames": visible_predictions,
        "manual_oracle_recall": ratio(manual_hits, manual_visible),
        "manual_top1_recall": ratio(manual_top_hits, manual_visible),
        "boxes_per_frame": ratio(predictions, labelled),
        "boxes_per_visible_frame": ratio(visible_predictions, visible),
        "top1_error_px": distribution(top_errors),
        "oracle_hits_beyond_10px": sum(e > 10 for e in errors),
        "top1_hits_beyond_10px": sum(e > 10 for e in top_errors),
        "precision": ratio(hits, predictions),
        "unmatched": predictions - hits,
        "no_ball_frames": no_ball,
        "no_ball_predictions": false,
        "no_ball_exposure_s": no_ball / 2,
        "false_per_frame": ratio(false, no_ball),
        "false_per_10s": ratio(20 * false, no_ball),
        "error_px": distribution(errors),
        "matched_box_short_side_px": distribution(sizes),
    }


def score_track(rows, labels, duration_s):
    tracked = track(rows, duration_s)
    points = {p["t"]: p for p in tracked["points"]}
    visible = covered = wrong = jumps = track_visible = 0
    longest = run = 0
    previous_correct = previous_wrong = False
    previous_fragment = None
    for row in rows:
        label = labels.get((row["clip"], row["t"]))
        point = points.get(row["t"])
        correct = bad = False
        fragment = point["fragment"] if point else None
        if label and label["visible"]:
            visible += 1
            if point:
                track_visible += 1
                distance = math.dist(point["xy"], [label["x"], label["y"]])
                correct, bad = distance <= 20, distance > 50
                covered += correct
                wrong += bad
                jumps += bad and (not previous_wrong or fragment != previous_fragment)
        run = (
            run + 1
            if correct and previous_correct and fragment == previous_fragment
            else int(correct)
        )
        longest = max(longest, run)
        previous_correct, previous_wrong, previous_fragment = correct, bad, fragment
    return {
        "visible": visible,
        "covered": covered,
        "coverage": ratio(covered, visible),
        "longest_correct_frames": longest,
        "longest_correct_s": longest / 2,
        "wrong_object_frames": wrong,
        "wrong_per_visible": ratio(wrong, visible),
        "track_points_on_visible_frames": track_visible,
        "wrong_per_track_point": ratio(wrong, track_visible),
        "track_precision": ratio(covered, track_visible),
        "wrong_object_episodes": jumps,
    }


def audit(measurements, labels):
    plan = measurements["human_label_plan"]
    target_keys = {
        (f["clip"], f["t"]) for group in ("on_ball", "off_pitch") for f in plan[group]
    }
    coverage = {}
    for group in ("on_ball", "off_pitch"):
        covered = [f for f in plan[group] if (f["clip"], f["t"]) in labels]
        missing = [f for f in plan[group] if (f["clip"], f["t"]) not in labels]
        coverage[group] = {
            "target": len(plan[group]),
            "covered": len(covered),
            "covered_targets": covered,
            "missing_targets": missing,
        }
    per_clip = []
    for c in measurements["clips"]:
        cid = c["clip_id"]
        selected = [r for (key, _), r in labels.items() if key == cid]
        total = len(measurements["outputs"]["rf_full"][cid]["frames"])
        per_clip.append(
            {
                "clip": cid,
                "class": clip_class(c),
                "rows": len(selected),
                "visible": sum(r["visible"] for r in selected),
                "no_ball": sum(not r["visible"] for r in selected),
                "accepted": sum(r.get("source_accepted", False) for r in selected),
                "manual": sum(not r.get("source_accepted", False) for r in selected),
                "unlabelled": total - len(selected),
            }
        )
    return {
        "rows": len(labels),
        "visible": sum(r["visible"] for r in labels.values()),
        "no_ball": sum(not r["visible"] for r in labels.values()),
        "accepted": sum(r.get("source_accepted", False) for r in labels.values()),
        "manual": sum(not r.get("source_accepted", False) for r in labels.values()),
        "manual_visible": sum(
            r["visible"] and not r.get("source_accepted", False)
            for r in labels.values()
        ),
        "accepted_sources": dict(
            Counter(
                r["accepted_source"]
                for r in labels.values()
                if r.get("source_accepted")
            )
        ),
        "rejected": [],
        "coverage": coverage,
        "extra": len(set(labels) - target_keys),
        "unlabelled": sum(r["unlabelled"] for r in per_clip),
        "per_clip": per_clip,
    }


def score_candidate(
    measurements, labels, name, outputs, threshold=0.1, synthetic=False, split=None
):
    rows, per_clip, tracks = [], [], []
    groups = {c["clip_id"]: clip_class(c) for c in measurements["clips"]}
    for c in measurements["clips"]:
        cid = c["clip_id"]
        selected = [
            {
                **r,
                "clip": cid,
                "detections": [
                    d for d in r["detections"] if d["confidence"] >= threshold
                ],
            }
            for r in outputs[cid]["frames"]
        ]
        rows.extend(selected)
        per_clip.append(
            {"clip": cid, "class": groups[cid], **score_rows(selected, labels)}
        )
        tracks.append(
            {
                "clip": cid,
                "class": groups[cid],
                **score_track(selected, labels, c["duration_s"]),
            }
        )
    grouped = {
        g: score_rows([r for r in rows if g == "all" or groups[r["clip"]] == g], labels)
        for g in ("all", "on_ball", "off_pitch", "other")
    }
    track_groups = {}
    for group in grouped:
        selected = [r for r in tracks if group == "all" or r["class"] == group]
        visible = sum(r["visible"] for r in selected)
        track_groups[group] = {
            "visible": visible,
            "covered": sum(r["covered"] for r in selected),
            "coverage": ratio(sum(r["covered"] for r in selected), visible),
            "longest_correct_s": max(r["longest_correct_s"] for r in selected),
            "wrong_object_frames": sum(r["wrong_object_frames"] for r in selected),
            "wrong_per_visible": ratio(
                sum(r["wrong_object_frames"] for r in selected), visible
            ),
            "wrong_object_episodes": sum(r["wrong_object_episodes"] for r in selected),
            "track_points_on_visible_frames": sum(
                r["track_points_on_visible_frames"] for r in selected
            ),
            "wrong_per_track_point": ratio(
                sum(r["wrong_object_frames"] for r in selected),
                sum(r["track_points_on_visible_frames"] for r in selected),
            ),
            "track_precision": ratio(
                sum(r["covered"] for r in selected),
                sum(r["track_points_on_visible_frames"] for r in selected),
            ),
        }
    recall, false = grouped["on_ball"]["top1_recall"], grouped["all"]["false_per_10s"]
    gate = (
        "UNMEASURABLE"
        if recall is None or false is None
        else "PASS"
        if recall >= 0.8 and false <= 1
        else "FAIL"
    )
    if any(r["class"] == "on_ball" and not r["labelled"] for r in per_clip):
        gate = "UNMEASURABLE"
    if synthetic:
        gate = "SYNTHETIC SMOKE — NOT RESULTS"
    bias = {
        source: score_rows(
            rows,
            {
                k: v
                for k, v in labels.items()
                if bool(v.get("source_accepted")) == accepted
            },
        )
        for source, accepted in (("accepted", True), ("manual", False))
    }
    held_out = (
        score_rows([r for r in rows if r["clip"] in split["held_out"]], labels)
        if split
        else None
    )
    missing_all = len(rows) - grouped["all"]["labelled"]
    missing_on = (
        sum(groups[r["clip"]] == "on_ball" for r in rows)
        - grouped["on_ball"]["labelled"]
    )
    false_lower_bound = ratio(
        20 * grouped["all"]["no_ball_predictions"],
        grouped["all"]["no_ball_frames"] + missing_all,
    )
    recall_upper_bound = ratio(
        grouped["on_ball"]["top1_matched"] + missing_on,
        grouped["on_ball"]["visible"] + missing_on,
    )
    held_groups = (
        {
            group: score_rows(
                [
                    r
                    for r in rows
                    if r["clip"] in split["held_out"]
                    and (group == "all" or groups[r["clip"]] == group)
                ],
                labels,
            )
            for group in grouped
        }
        if split
        else None
    )
    all_clip_gate = gate
    if held_groups and not synthetic:
        hr, hf = (
            held_groups["on_ball"]["top1_recall"],
            held_groups["all"]["false_per_10s"],
        )
        gate = (
            "UNMEASURABLE"
            if hr is None or hf is None
            else "PASS"
            if hr >= 0.8 and hf <= 1
            else "FAIL"
        )
    return {
        "all_clip_gate": all_clip_gate,
        "headline_scope": "held-out only" if split else "all clips; unfitted baseline",
        "held_out_fps": (
            sum(len(outputs[c]["frames"]) for c in split["held_out"])
            / sum(outputs[c]["wall_s"] for c in split["held_out"])
        )
        if split and split["held_out"]
        else None,
        "missing_label_bounds": {
            "on_ball_recall_upper_bound": recall_upper_bound,
            "no_ball_false_per_10s_lower_bound": false_lower_bound,
            "failure_unavoidable_on_full_frozen_schedule": not synthetic
            and (
                (false_lower_bound is not None and false_lower_bound > 1)
                or (recall_upper_bound is not None and recall_upper_bound < 0.8)
            ),
        },
        "candidate": name,
        "threshold": threshold,
        "synthetic_smoke": synthetic,
        "fps": len(rows) / sum(r["wall_s"] for r in outputs.values()),
        "gate": gate,
        "groups": grouped,
        "per_clip": per_clip,
        "tracks": {"groups": track_groups, "per_clip": tracks},
        "provenance_bias": bias,
        "held_out": held_out,
        "training_split": split,
        "held_out_groups": held_groups,
    }


def score(measurements, labels, extras, label_rule="as_labelled"):
    metadata = rule_metadata(labels, label_rule)
    results = [
        score_candidate(measurements, labels, name, measurements["outputs"][name])
        for name in ("rf_full", "rf_2x2", "rf_3x3", "wasb", "wasb_2x2")
    ]
    results += [
        score_candidate(
            measurements,
            labels,
            name,
            data["outputs"],
            data["threshold"],
            data["synthetic_smoke"],
            data.get("training_split"),
        )
        for name, data in extras.items()
    ]
    return {
        "schema_version": 1,
        **metadata,
        "frozen_set_id": measurements["frozen_set_id"],
        "labels": audit(measurements, labels),
        "results": results,
        "definitions": [
            "Human-sample PASS/FAIL is legitimate; proxy verdicts retire for these results. Gate: highest-confidence top-1 visible-frame recall on on-ball clips >=80%, and <=1 prediction per 10 seconds on ALL explicitly no-ball labels. Missing targets are excluded, never inferred; this is not certification of unlabelled frames or unseen matches.",
            "20 source-pixel inclusive match radius. Top-1 uses the highest-confidence prediction (saved order breaks ties). Nearest-of-N recall is a secondary oracle over N boxes; at most one oracle match per visible label and duplicates count against oracle precision. Boxes/frame uses labelled frames only. Confidence 0.1 for all five saved baselines and trained models; no threshold search.",
            "Missing-label bounds are deliberately optimistic: assume every missing on-ball sample is visible and correctly detected by top-1 for the recall upper bound; assume all 48 missing samples are no-ball with zero predictions for the false-rate lower bound. These separate best cases need not hold together. If either still fails, completing labels cannot rescue that candidate on the frozen schedule. Bounds never replace actual sample metrics.",
            "No-ball = no ball visible to the labeller; a correct but human-invisible ball still counts false. False-per-frame uses ONLY no-ball labels; false/10s = count *20 / no-ball frames at the frozen 2fps exposure. Sparse samples estimate an exposure-normalised rate, not continuous video event counts.",
            "Ball size is nearest matched detector box SHORT SIDE in native source pixels, median and nearest-rank p95. Human centres confirm association, not box boundaries or true physical diameter. Undetected balls have no size measurement, so this distribution is detection-conditioned. WASB points have no size. Trained point-box sizes are supervision-dependent and must not be treated as independent size measurements.",
            "Tracks rerun unchanged Kalman association without label guidance; score filtered points. Correct runs require successive scheduled samples within 20px in the same fragment; missing/no-ball/incorrect labels break runs. >50px wrong-object frames and contiguous wrong episodes are both counted. Wrong-per-track-point and track precision use only track points on visible-labelled frames; coverage also penalises missing points. Tracks on no-ball frames are outside this particular precision denominator; intervening unlabelled frames break episodes.",
            "Accepted/manual bias comparison is descriptive and confounded by frame difficulty and suggestion source, not an independent causal estimate. Manual includes explicit no-ball decisions. Publish manual-only top-1 and oracle recall alongside pooled recall. Accepted labels retain accepted_source and accepted_score; future suggestions from the model under test risk forward confirmation bias.",
            "Baseline FPS reuses measured native decode+inference timings; model load, warmup, scoring and tracking excluded. Trained whole-corpus scores include training clips; held-out results are reported separately. All clips come from one match, limiting generalisation.",
        ],
    }


def fmt(value, percent=False):
    return (
        "—" if value is None else f"{value * 100:.2f}%" if percent else f"{value:.3f}"
    )


def candidate_name(row):
    return row["candidate"] + (" [SYNTHETIC]" if row["synthetic_smoke"] else "")


def markdown(data):
    """CLI report; trained headlines are strictly held-out, all-clip separate."""
    results = data["results"]
    lines = [
        "Human gate: top-1 on-ball recall >=80% AND no-ball false/10s <=1. Proxy verdicts retire.",
        "",
        "Trained headline metrics use held-out clips only; all-clip numbers explicitly include training. Held-out (mild prior tuning exposure: the 640-vs-960 recipe choice in round 1 saw these clips in aggregate). These clips are no longer a clean test set.",
        "",
        "| Candidate | Headline scope | Top-1 on recall (manual-only) | Oracle over N boxes | Oracle precision | Boxes/visible on frame | No-ball false/10s | FPS | Gate | Incl. training clips: top-1 / oracle / manual top-1 |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|---:|",
    ]
    for r in results:
        g = r["held_out_groups"] or r["groups"]
        on, a = g["on_ball"], g["all"]
        full = r["groups"]["on_ball"]
        fps = r["held_out_fps"] if r["held_out_fps"] is not None else r["fps"]
        lines.append(
            f"| {candidate_name(r)} | {r['headline_scope']} | {fmt(on['top1_recall'], True)} ({fmt(on['manual_top1_recall'], True)}) | {fmt(on['oracle_recall'], True)} | {fmt(on['precision'], True)} | {fmt(on['boxes_per_visible_frame'])} | {fmt(a['false_per_10s'])} | {fps:.2f} | {r['gate']} | {fmt(full['top1_recall'], True)} / {fmt(full['oracle_recall'], True)} / {fmt(full['manual_top1_recall'], True)} |"
        )
    lines += [
        "",
        "| Candidate / scope / group | Visible / no-ball | Pooled top-1 / oracle over N boxes | Manual top-1 / oracle | Top-1 / oracle precision | False/frame | Top-1 median error px |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for r in results:
        for scope, groups in (
            ("incl. training clips", r["groups"]),
            ("held-out only", r["held_out_groups"]),
        ):
            for group, a in (groups or {}).items():
                lines.append(
                    f"| {candidate_name(r)} / {scope} / {group} | {a['visible']} / {a['no_ball_frames']} | {fmt(a['top1_recall'], True)} / {fmt(a['oracle_recall'], True)} | {fmt(a['manual_top1_recall'], True)} / {fmt(a['manual_oracle_recall'], True)} | {fmt(a['top1_precision'], True)} / {fmt(a['precision'], True)} | {fmt(a['false_per_frame'])} | {fmt(a['top1_error_px']['median'])} |"
                )
    lines += [
        "",
        "| Track / group (all clips, incl. training) | Coverage | Precision on visible-labelled points | Longest correct s | Wrong frames / track points (rate) | Wrong / visible rate | Episodes |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for r in results:
        for group, t in r["tracks"]["groups"].items():
            lines.append(
                f"| {candidate_name(r)} / {group} | {fmt(t['coverage'], True)} | {fmt(t['track_precision'], True)} | {t['longest_correct_s']:.1f} | {t['wrong_object_frames']} / {t['track_points_on_visible_frames']} ({fmt(t['wrong_per_track_point'], True)}) | {fmt(t['wrong_per_visible'], True)} | {t['wrong_object_episodes']} |"
            )
    audit_data = data["labels"]
    lines += [
        "",
        f"Labels: {audit_data['rows']} validated, {audit_data['visible']} visible / {audit_data['no_ball']} no-ball, {audit_data['accepted']} accepted / {audit_data['manual']} manual, {len(audit_data['rejected'])} rejected. Accepted sources: {audit_data['accepted_sources']}. Exact coverage and per-clip scores are in JSON.",
        "",
    ]
    lines += [f"- {s}" for s in data["definitions"]]
    if "match_ball_note" in data:
        lines += [data["match_ball_note"]]
    return banner_tables("\n".join(lines), data)


if __name__ == "__main__":
    from score_from_saved import main

    main()
