"""Human-only 20 source-pixel metrics; never infer labels or ball box extents."""

from __future__ import annotations

from collections import Counter
import math
import json
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
    errors, sizes = [], []
    for row in rows:
        label = labels.get((row["clip"], row["t"]))
        if label is None:
            continue
        labelled += 1
        ds = row["detections"]
        predictions += len(ds)
        if not label["visible"]:
            no_ball += 1
            false += len(ds)
            continue
        visible += 1
        nearest = min(
            ds, key=lambda d: math.dist(d["xy"], [label["x"], label["y"]]), default=None
        )
        if nearest is not None:
            error = math.dist(nearest["xy"], [label["x"], label["y"]])
            if error <= 20:
                hits += 1
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
        "recall": ratio(hits, visible),
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
        }
    recall, false = grouped["on_ball"]["recall"], grouped["all"]["false_per_10s"]
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
        grouped["on_ball"]["matched"] + missing_on,
        grouped["on_ball"]["visible"] + missing_on,
    )
    return {
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
        "held_out_groups": {
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
        else None,
    }


def score(measurements, labels, extras):
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
        "frozen_set_id": measurements["frozen_set_id"],
        "labels": audit(measurements, labels),
        "results": results,
        "definitions": [
            "Human-sample PASS/FAIL is legitimate; proxy verdicts retire for these results. Gate: pooled visible-frame recall on six on-ball clips >=80%, and <=1 prediction per 10 seconds on ALL explicitly no-ball labels. Missing targets are excluded, never inferred; this is not certification of unlabelled frames or unseen matches.",
            "20 source-pixel inclusive match radius; at most one nearest prediction matches each visible label, duplicates count against precision. Confidence 0.1 for all five saved baselines and trained models; no threshold search.",
            "Missing-label bounds are deliberately optimistic: assume every missing on-ball sample is visible and correctly detected for the recall upper bound; assume all 48 missing samples are no-ball with zero predictions for the false-rate lower bound. These separate best cases need not hold together. If either still fails, completing labels cannot rescue that candidate on the frozen schedule. Bounds never replace actual sample metrics.",
            "False-per-frame uses ONLY no-ball labels; false/10s = count *20 / no-ball frames at the frozen 2fps exposure. Sparse samples estimate an exposure-normalised rate, not continuous video event counts.",
            "Ball size is nearest matched detector box SHORT SIDE in native source pixels, median and nearest-rank p95. Human centres confirm association, not box boundaries or true physical diameter. Undetected balls have no size measurement, so this distribution is detection-conditioned. WASB points have no size. Trained point-box sizes are supervision-dependent and must not be treated as independent size measurements.",
            "Tracks rerun unchanged Kalman association without label guidance; score filtered points. Correct runs require successive scheduled samples within 20px in the same fragment; missing/no-ball/incorrect labels break runs. >50px wrong-object frames and contiguous wrong episodes are both counted; intervening unlabelled frames break episodes.",
            "Accepted/manual bias comparison is descriptive and confounded by frame difficulty and suggestion source, not an independent causal estimate. Manual includes explicit no-ball decisions.",
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
    results = data["results"]
    passing = [
        f"{candidate_name(r)} ({r['fps']:.2f} FPS)"
        for r in results
        if r["gate"] == "PASS"
    ]
    lines = [
        f"Human gate: {', '.join(passing) if passing else 'no candidate passes'}. Proxy verdicts retire for this human-labelled sample.",
        "",
    ]
    for r in results:
        if r["held_out"]:
            h = r["held_out"]
            lines.append(
                f"{candidate_name(r)} held out: recall {fmt(h['recall'], True)}, precision {fmt(h['precision'], True)}, no-ball false/frame {fmt(h['false_per_frame'])}, {r['fps']:.2f} FPS."
            )
            if r.get("held_out_groups"):
                on = r["held_out_groups"]["on_ball"]
                lines.append(
                    f"Its two held-out on-ball clips: recall {fmt(on['recall'], True)}, precision {fmt(on['precision'], True)}, no-ball false/frame {fmt(on['false_per_frame'])} ({on['visible']} visible / {on['no_ball_frames']} no-ball labels)."
                )
    lines += [
        "",
        "| Candidate | On recall | On precision | No-ball false/10s | Median error px (all) | FPS | Real sample gate |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for r in results:
        a, on = r["groups"]["all"], r["groups"]["on_ball"]
        name = r["candidate"] + (" [SYNTHETIC]" if r["synthetic_smoke"] else "")
        lines.append(
            f"| {name} | {fmt(on['recall'], True)} | {fmt(on['precision'], True)} | {fmt(a['false_per_10s'])} | {fmt(a['error_px']['median'])} | {r['fps']:.2f} | {r['gate']} |"
        )
    lines += [
        "",
        "| Candidate / group | Labels / visible / no-ball | Recall | Precision | False/frame (no-ball) | Median error px | Box short side median / p95 px (n) |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for r in results:
        for group, a in r["groups"].items():
            b = a["matched_box_short_side_px"]
            lines.append(
                f"| {candidate_name(r)} / {group} | {a['labelled']} / {a['visible']} / {a['no_ball_frames']} | {fmt(a['recall'], True)} | {fmt(a['precision'], True)} | {fmt(a['false_per_frame'])} | {fmt(a['error_px']['median'])} | {fmt(b['median'])} / {fmt(b['p95'])} ({b['n']}) |"
            )
    unavoidable = [
        candidate_name(r)
        for r in results
        if r.get("missing_label_bounds", {}).get(
            "failure_unavoidable_on_full_frozen_schedule"
        )
    ]
    if unavoidable:
        lines += [
            "",
            "Even optimistically filling all missing labels cannot rescue the frozen-schedule gate for: "
            + ", ".join(unavoidable)
            + ". Per-candidate bounds are recorded in JSON.",
        ]
    rf_sizes = next((r for r in results if r["candidate"] == "rf_2x2"), None)
    if rf_sizes:
        all_sizes = rf_sizes["groups"]["all"]["matched_box_short_side_px"]
        manual_sizes = rf_sizes["provenance_bias"]["manual"][
            "matched_box_short_side_px"
        ]
        lines += [
            "",
            f"Human-associated RF 2x2 ball box short side: median {fmt(all_sizes['median'])} px / p95 {fmt(all_sizes['p95'])} px over {all_sizes['n']} matched frames. On independently hand-clicked frames: {fmt(manual_sizes['median'])} / {fmt(manual_sizes['p95'])} px over {manual_sizes['n']} matches. These are detector extents around confirmed ball centres, not human-measured boundaries.",
        ]
    label_audit = data["labels"]
    lines += [
        "",
        f"Labels: {label_audit['rows']} validated; {label_audit['visible']} visible / {label_audit['no_ball']} no-ball; {label_audit['accepted']} accepted / {label_audit['manual']} manual; {len(label_audit['rejected'])} rejected. Accepted sources: {label_audit['accepted_sources']}.",
        f"Target coverage: {label_audit['coverage']['on_ball']['covered']}/540 on-ball + {label_audit['coverage']['off_pitch']['covered']}/100 off-pitch; {label_audit['extra']} extra; {label_audit['unlabelled']} unlabelled. Exact covered/missing target keys are in the JSON ledger.",
        "",
        "| Clip | Class | Labels | Visible | No-ball | Accepted | Manual | Missing |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for r in label_audit["per_clip"]:
        lines.append(
            "| "
            + " | ".join(
                str(r[k])
                for k in (
                    "clip",
                    "class",
                    "rows",
                    "visible",
                    "no_ball",
                    "accepted",
                    "manual",
                    "unlabelled",
                )
            )
            + " |"
        )
    lines += [
        "",
        "| Track / group | Coverage within 20px | Longest correct s | >50px frames / visible | Wrong episodes |",
        "|---|---:|---:|---:|---:|",
    ]
    for r in results:
        for group, t in r["tracks"]["groups"].items():
            lines.append(
                f"| {candidate_name(r)} / {group} | {fmt(t['coverage'], True)} | {t['longest_correct_s']:.1f} | {t['wrong_object_frames']}/{t['visible']} ({fmt(t['wrong_per_visible'], True)}) | {t['wrong_object_episodes']} |"
            )
    lines += [
        "",
        "| Candidate | Accepted recall / precision / median error | Manual recall / precision / median error |",
        "|---|---:|---:|",
    ]
    for r in results:
        cells = [
            f"{fmt(a['recall'], True)} / {fmt(a['precision'], True)} / {fmt(a['error_px']['median'])} px"
            for a in r["provenance_bias"].values()
        ]
        lines.append(f"| {candidate_name(r)} | " + " | ".join(cells) + " |")
    execution = data.get("execution", {})
    if execution:
        lines += [
            "",
            "Training and execution:",
            "",
            "| Model | MPS minutes | Epochs completed / requested | Tile input px | Held-out recall | Held-out precision | No-ball false/frame | FPS |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for run in execution.get("training", []):
            lines.append(
                f"| {run['candidate']} | {run['training_minutes']:.2f} | {run['epochs_completed']} / {run['epochs_requested']} | {run['model_input_px']} | {fmt(run['held_out_recall'], True)} | {fmt(run['held_out_precision'], True)} | {fmt(run['held_out_no_ball_false_per_frame'])} | {run['fps']:.2f} |"
            )
        lines += ["", "Exact frozen clip split:", "", "| Role | Clip |", "|---|---|"]
        for role in ("train", "held_out"):
            for cid in execution.get("split", {}).get(role, []):
                lines.append(f"| {role} | {cid} |")
        if execution.get("dataset_counts"):
            lines += [
                "",
                "Tile counts: "
                + json.dumps(execution["dataset_counts"], sort_keys=True)
                + ".",
            ]
        lines += [
            "",
            "Recorded commands (training uses the external MPS environment):",
            "",
            "```sh",
        ]
        lines += [r["command"] for r in execution.get("training", [])]
        lines += ["```", "", "Decisions:", ""]
        lines += [f"- {item}" for item in execution.get("decisions", [])]
        if execution.get("kit"):
            lines += [
                "",
                "Kit refresh:",
                "",
                "```json",
                json.dumps(execution["kit"], indent=2, sort_keys=True),
                "```",
            ]
        lines += ["", "Verification:", ""]
        lines += [f"- {item}" for item in execution.get("checks", [])]
        if execution.get("not_done"):
            lines += ["", "Not done:", ""] + [
                f"- {item}" for item in execution["not_done"]
            ]
        lines += [
            "",
            "Hashes, full execution provenance, per-clip scores and exact target coverage are retained in the JSON ledger and committed execution fixture.",
        ]
    lines += ["", "Definitions and caveats:", ""] + [
        f"- {s}" for s in data["definitions"]
    ]
    return "\n".join(lines) + "\n"
