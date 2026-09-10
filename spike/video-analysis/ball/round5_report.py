"""Fair comparison supersedes the fixed-confidence historical headlines."""

from __future__ import annotations
from fair_protocol import BUCKETS
from round5_framing import (
    HEADLINE,
    BIG_BALL,
    EPOCHS,
    COUNTERFACTUAL,
    COMPUTE,
    SPEED,
    FUTURE,
)
from round3_report import f, pair

OLD_LABEL = "held-out (mild prior tuning exposure: the 640-vs-960 recipe choice in round 1 saw these clips in aggregate)"
NEW_LABEL = "held-out (recipe-selected on these clips)"


def relabel(data):
    """Update presentation, preserving hashed historical protocol snapshots verbatim."""
    if isinstance(data, dict):
        return {
            k: v if k == "protocol_snapshot" else relabel(v) for k, v in data.items()
        }
    if isinstance(data, list):
        return [relabel(v) for v in data]
    if isinstance(data, str):
        return data.replace(OLD_LABEL, NEW_LABEL)
    return data


def markdown(data, historical):
    p = data["round5"]
    e = p["measurements"]
    order = ["yolo-r2-b", "rf-b"] + sorted(
        n for n in e["models"] if n.startswith("rf-r5-")
    )
    models = {name: e["models"][name] for name in order}
    selected = e["best_rf_final_selected"]
    qualified = (
        models[selected]["operating_points"]["1"]["held"]["groups"]["all"][
            "false_per_10s"
        ]
        <= 2
    )
    passing = [
        f"{name} at TRAIN target {budget}"
        for name, row in models.items()
        for budget, op in row["operating_points"].items()
        if op["held"]["gate"] == "PASS"
    ]
    lines = [
        "# Fair comparison — no winner at a strict budget",
        "",
        HEADLINE,
        "",
        "Gate on recipe-selected clips: **"
        + (", ".join(passing) or "no candidate passes either operating point")
        + "**.",
        "",
        "This section supersedes the round-4 head-to-head headline. **A shared confidence threshold is not a fair operating point across model families.** Product direction remains RF-DETR (Apache-2.0); ultralytics is bench-only and must not enter the serving path.",
        "",
        f"Current RF model selected across FINAL checkpoints: **{selected}** ({'eligible at ≤2 H false/10s' if qualified else 'UNQUALIFIED lowest-false kit fallback'}). Each fit exports its FINAL checkpoint. Gate: H on-ball top-1 ≥80% AND strict H false/10s ≤1.0. Intermediate held-out learning-curve numbers do not select anything. Final H metrics select the model under the declared ≤2 false/10s rule (or an explicitly unqualified lowest-false fallback); this is optimistic.",
        "",
        f"T = 14 TRAIN clips (631 visible, 122 no-ball); H = **{NEW_LABEL}**, six clips (244 visible, 60 no-ball). On-ball denominators: T 300, H 122. All includes training clips. All 20 clips are from match m04. H on-ball is just 102 frames of m04-n17-t717-253073-260377 and 20 of m04-n17-t717-416826-418915; player n17-t717 also appears in TRAIN. **Two clips from one match cannot establish a winner.**",
        "",
        "Thresholds are chosen from TRAIN no-ball scores only: the lowest threshold retaining at most floor(target × 122 / 20) false boxes; >= comparison, ties removed together. Thus nominal TRAIN 1.0 and 2.0 budgets allow 6 and 12 boxes (0.984 and 1.967/10s). All 1105 scheduled frames were freshly inferred down to confidence 0.01. Scores below that floor are censored; the curve cannot describe lower thresholds.",
        "",
        "Manual-only frames are harder: MJ hand-clicked frames where useful suggestions were absent. Lower manual-only recall is expected from that selection and is not, by itself, evidence of model bias. Accepted-source provenance remains attached to exported labels.",
        "",
        "## Primary operating points",
        "",
        "| Model | TRAIN target | Threshold | On-ball top-1 T / H | Manual top-1 T / H | Strict false/10s T / H | H McNemar wins / losses vs YOLO | Exact p | Gate H |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for name, row in models.items():
        for budget, op in row["operating_points"].items():
            t, h = (op[s]["groups"] for s in ("train", "held"))
            mc = op["mcnemar_vs_yolo"]
            lines.append(
                f"| {name} | {budget} | {op['threshold']:.17g} | {pair(t['on_ball']['top1_recall'], h['on_ball']['top1_recall'], True)} | {pair(t['on_ball']['manual_top1_recall'], h['on_ball']['manual_top1_recall'], True)} | {pair(t['all']['false_per_10s'], h['all']['false_per_10s'])} | {mc['wins']} / {mc['losses']} | {mc['exact_two_sided_p']:.4g} | {op['held']['gate']} |"
            )
    lines += [
        "",
        "### Matched held-out false-rate budgets — diagnostic only",
        "",
        "Maximum hits out of122 at or below each false-count budget. These thresholds use H, so this is descriptive, not deployable calibration. One false box is20/60=0.333 per10s; the lead changes hands every one or two boxes.",
        "",
        "| H false/10s (box budget) | YOLO r2-b | RF b | RF r5-a | RF r5-b |",
        "|---|---:|---:|---:|---:|",
    ]
    for r in e["framing"]["matched_false_rate_diagnostic_only"]:
        if r["false_boxes_budget"] in (3, 4, 5, 6, 9, 10):
            lines.append(
                f"| {r['false_per_10s']:.2f} ({r['false_boxes_budget']}) | "
                + " | ".join(str(r["hits"][n]) for n in order)
                + " |"
            )
    lines += [
        "",
        "TRAIN calibration is in-sample: its no-ball frames were also training negatives. Approximate target1 H/TRAIN ratios are YOLO1.7×, r5-a2.0×, r5-b1.4×, RF b3.0×. Using the achieved0.9836 TRAIN rate, exact ratios are "
        + ", ".join(
            f"{n} {e['framing']['calibration_false_ratios'][n]:.2f}×" for n in order
        )
        + ". A TRAIN-chosen operating point does not imply an equal H error rate.",
        "",
        e["framing"]["selection"],
    ]
    lines += [
        "",
        e["selection_audit"]["preview_discrepancy"],
        "",
        "Both new fits started from COCO and stopped at the 90-minute budget after three complete epochs plus part of epoch4. Only six hard tiles were mined (five negative, one positive retaining its annotation). No evidence more epochs help at strict budgets; do not plan longer m04 training.",
        "",
        "Large-ball / n21 summary (H only, recipe-selected on these clips):",
        "",
        "| Model | ≥24px hits/22 at TRAIN 1 / 2 / fixed0.1 | N21 false boxes on5 no-ball frames at TRAIN 1 / 2 / fixed0.1 |",
        "|---|---:|---:|",
    ]
    for name, row in models.items():
        scopes = [row["operating_points"][b]["held"] for b in ("1", "2")] + [
            row["fixed_0.1_not_comparable"]["held"]
        ]
        large = " / ".join(
            str(r["size_buckets"][">=24"]["hits"]) + "/22" for r in scopes
        )
        n21 = " / ".join(
            str(
                next(
                    c["no_ball_predictions"]
                    for c in r["per_clip"]
                    if "n21-t3011" in c["clip"]
                )
            )
            for r in scopes
        )
        lines.append(f"| {name} | {large} | {n21} |")
    lines += [
        "",
        "Exact two-sided McNemar is a frame-level diagnostic; adjacent frames correlate, so its nominal p value is optimistic. YOLO comparisons use each model's own TRAIN-chosen threshold for the same target, not the same numeric threshold or a threshold matched on H.",
        "",
        "## Precision, localisation and output volume",
        "",
        "| Model / TRAIN target / group | Top-1 recall T / H | Top-1 precision T / H | Manual recall T / H | Oracle over N boxes T / H | Boxes/visible frame T / H | Median top-1 error px T / H |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, row in models.items():
        for budget, op in row["operating_points"].items():
            for group in ("on_ball", "all"):
                t, h = (op[s]["groups"][group] for s in ("train", "held"))
                cells = [
                    pair(t[k], h[k], True)
                    for k in (
                        "top1_recall",
                        "top1_precision",
                        "manual_top1_recall",
                        "oracle_recall",
                    )
                ]
                cells += [
                    pair(t["boxes_per_visible_frame"], h["boxes_per_visible_frame"]),
                    pair(t["top1_error_px"]["median"], h["top1_error_px"]["median"]),
                ]
                lines.append(
                    f"| {name} / {budget} / {group} | " + " | ".join(cells) + " |"
                )
    lines += [
        "",
        "## False boxes by clip",
        "",
        "No-ball means **no ball visible to the labeller**. Every retained detection on such a frame counts false, even an actual ball the labeller missed or an apparent spare ball. Path credits are a sensitivity analysis only, never used to choose thresholds or pass the gate.",
        "",
        "The path-credit rule is unchanged: within 50 native px of the linear interpolation between bracketing visible clicks, with a total bracket gap ≤1.01s. Terminal no-ball frames without both brackets receive no credit; this includes the n21 examples.",
        "",
        "| Model / TRAIN target | Strict false/10s T / H | Path-credited false/10s T / H | Credits T / H |",
        "|---|---:|---:|---:|",
    ]
    for name, row in models.items():
        for budget, op in row["operating_points"].items():
            t, h = (op[s]["path_sensitivity"] for s in ("train", "held"))
            lines.append(
                f"| {name} / {budget} | {pair(t['false_per_10s'], h['false_per_10s'])} | {pair(t['path_credited_false_per_10s'], h['path_credited_false_per_10s'])} | {t['credits']} / {h['credits']} |"
            )
    for scope in ("train", "held"):
        lines += [
            "",
            f"{scope.upper()} clip counts (columns are model / TRAIN target):",
            "",
            "| Clip | No-ball frames | "
            + " | ".join(f"{n} / {b}" for n in models for b in ("1", "2"))
            + " |",
            "|---|---:|" + "---:|" * (2 * len(models)),
        ]
        reference = next(iter(models.values()))["operating_points"]["1"][scope][
            "per_clip"
        ]
        for i, clip in enumerate(reference):
            counts = [
                str(
                    r["operating_points"][b][scope]["per_clip"][i][
                        "no_ball_predictions"
                    ]
                )
                for r in models.values()
                for b in ("1", "2")
            ]
            lines.append(
                f"| {clip['clip']} | {clip['no_ball_frames']} | "
                + " | ".join(counts)
                + " |"
            )
    lines += [
        "",
        "### N21 source-pixel inspection",
        "",
        e["framing"]["n21_note"],
        "",
        p["n21_visual_review"]["fresh_pass"],
        "",
        p["n21_visual_review"]["policy"],
        "",
        p["n21_visual_review"]["private_evidence"],
        "",
        e["framing"]["n21_three_rules"]["definition"],
        "",
        "Each cell: false/10s; overall top-1 recall (hits/visible). Directions are false/recall versus YOLO at the same TRAIN budget. On-ball recall is unchanged: n21 is off_pitch.",
        "",
        "| Model / TRAIN budget | As labelled | Any visible ball (credit-only false; provisional recall) | Match ball only | Directions vs YOLO: labelled / any / match |",
        "|---|---:|---:|---:|---|",
    ]
    for r in e["framing"]["n21_three_rules"]["rows"]:
        rules = [
            r["rules"][k]
            for k in ("as_labelled", "any_visible_ball", "match_ball_only")
        ]
        cells = [
            f"{v['false_per_10s']:.2f}; {100 * v['overall_top1_recall']:.2f}% ({v['top1_hits']}/{v['visible']})"
            for v in rules
        ]
        directions = " / ".join(
            f"{v['direction_vs_yolo']['false']} false, {v['direction_vs_yolo']['recall']} recall"
            for v in rules
        )
        lines.append(
            f"| {r['model']} / {r['train_budget']} | "
            + " | ".join(cells)
            + f" | {directions} |"
        )
    lines += [
        "",
        "At TRAIN-2 r5-a changes from more false alarms than YOLO under as-labelled and match-ball-only rules to fewer under visible-ball credits; r5-b remains higher under all three displayed rules only with credit-only false counting. All RF models have higher overall recall than YOLO under each displayed sensitivity, but these are recipe-selected clips with provisional semantics, not evidence of a winner.",
        "",
        p.get("n21_full_relabel_note", ""),
        "",
        e["framing"]["n21_three_rules"]["pending"][:1].upper()
        + e["framing"]["n21_three_rules"]["pending"][1:]
        + ". Adjudication sheet: ~/codex-runs/ball-r5-n21/adjudicate-s0-s10.png. No label was changed. The new sheet includes all11 current labels, source context, an enlarged background region and retained boxes from all four models at both budgets.",
        "",
        "## Size buckets: top-1 hits / visible labels",
        "",
        "Sizes are the same independent matched RF baseline-box short sides as previous rounds, not inferred from this round's successes. Unknown sizes stay in the denominator. These are teacher box estimates, not human-drawn boundaries. TRAIN has only one independently sized ≥24px on-ball example; H has 22.",
        "",
        BIG_BALL,
        "",
        "TRAIN targets are synthetic:592/631 sit at the18.680435px floor,23 are≥24px, maximum32.85px. A1.2× zoom raises the floor to22.42px, still below24px. These631 targets differ from the independent matched-size on-ball bucket (only1 TRAIN label≥24px).",
        "",
        "| Model / TRAIN target | Bucket | TRAIN hits / labels | H hits / labels |",
        "|---|---|---:|---:|",
    ]
    for name, row in models.items():
        for budget, op in row["operating_points"].items():
            for bucket in BUCKETS:
                t, h = (op[s]["size_buckets"][bucket] for s in ("train", "held"))
                lines.append(
                    f"| {name} / {budget} | {bucket} | {t['hits']}/{t['visible']} | {h['hits']}/{h['visible']} |"
                )
    lines += [
        "",
        "## Fixed 0.1, not comparable across models",
        "",
        "These secondary numbers reproduce the prior convention. All explicitly includes training clips. They must not be read as an equal-error head-to-head.",
        "",
        "| Model | On-ball top-1 All / T / H | Manual-only All / T / H | Oracle over N All / T / H | Top-1 precision All / T / H | Strict false/10s All / T / H | Boxes/visible on-ball All / T / H |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, row in models.items():
        cohorts = [
            row["fixed_0.1_not_comparable"][s]["groups"]
            for s in ("all", "train", "held")
        ]
        cells = [
            " / ".join(f(c["on_ball"][k], True) for c in cohorts)
            for k in (
                "top1_recall",
                "manual_top1_recall",
                "oracle_recall",
                "top1_precision",
            )
        ]
        cells += [
            " / ".join(f(c["all"]["false_per_10s"]) for c in cohorts),
            " / ".join(f(c["on_ball"]["boxes_per_visible_frame"]) for c in cohorts),
        ]
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    lines += [
        "",
        "## Training and diagnostic learning curves",
        "",
        p["protocol"]["config"]["augmentation"],
        "",
        p["protocol"]["config"]["schedule"]
        + ". AdamW, FP32, batch8, seed42; official layer-wise parameter groups, gradient norm clipping0.1. Native 960×540 content is padded to 960², never squashed. Scale targets remain clamp(TRAIN affine(y),18.6804351807,48). No observed-box override from the superseded long-training brief. Pseudo labels off.",
        "",
        p["protocol"]["config"]["replay"],
        "",
        p["pre_replay_correction"],
        "",
        p["selection_amendment_before_new_evaluation"],
        "",
        COUNTERFACTUAL,
        "",
        COMPUTE,
        "",
        EPOCHS,
        "",
        "Every base TRAIN tile is included in each complete epoch (631 positive, 2381 negative); replay adds one copy of each mined hard tile, retaining its positive annotation when present. Mining is performed on unaugmented TRAIN images only. Stopping compares unaugmented base-TRAIN loss, avoiding a changing replay mixture; three complete epochs without >1% improvement, 12-epoch / 90-minute phase-boundary budget. Final partial epochs are reported, never called complete.",
        "",
        "Seed42 is shared, but MPS uses deterministic-algorithm warnings rather than guaranteed bitwise determinism. The TRAIN histories already differ before replay begins. A single fit per setting cannot isolate replay's causal effect from run variation; full per-epoch losses are retained in the JSON.",
        "",
        "| Fit | Complete epochs + partial tiles | Total tile views | Minutes | Stop reason | Hard negatives per refresh (epoch: count) |",
        "|---|---:|---:|---:|---|---|",
    ]
    for name, fit in e.get("fits", {}).items():
        refresh = (
            ", ".join(
                f"{r['after_epoch']}: {r['hard_tiles']} ({r['negative_tiles']} negative)"
                for r in fit["replay_refreshes"]
            )
            or "none"
        )
        last = fit["history"][-1]
        epochs = str(fit["epochs_complete"])
        if not last["complete"]:
            epochs += f" + {last['views']}/{3012 + last['replay_tiles']} tiles"
        lines.append(
            f"| {name} | {epochs} | {fit['images_seen']} | {fit['training_s'] / 60:.2f} | {fit['stop_reason']} | {refresh} |"
        )
    lines += [
        "",
        "Checkpoints below are diagnostic only. Both fits had finished before any of these held-out evaluations. Thresholds are re-chosen on TRAIN for each checkpoint; no number below selects a checkpoint or alters a fit.",
        "",
        "| Fit / checkpoint | TRAIN target | Threshold | Top-1 on-ball T / H | False/10s T / H | Censoring |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for name, row in e.get("learning_curve", {}).items():
        for budget, op in row["operating_points"].items():
            t, h = (op[s]["groups"] for s in ("train", "held"))
            lines.append(
                f"| {name} | {budget} | {op['threshold']:.17g} | {pair(t['on_ball']['top1_recall'], h['on_ball']['top1_recall'], True)} | {pair(t['all']['false_per_10s'], h['all']['false_per_10s'])} | {'SAVE FLOOR: target not reached' if op['threshold'] == 0.01 and op['achieved_false_per_10s'] < float(budget) else '—'} |"
            )
    lines += [
        "",
        "The full held-out recall-versus-false/10s staircase (all score breakpoints down to 0.01) is committed in the JSON at round5.measurements.models.<model>.held_curve_diagnostic_only. It is a diagnostic curve, not an operating-point selection source.",
        "",
        "## Track versus truth at TRAIN-chosen operating points",
        "",
        "| Model / TRAIN target | Coverage T / H | Longest correct seconds T / H | Wrong / track points T / H | Track precision T / H | Wrong frames T / H |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, row in models.items():
        for budget, op in row["operating_points"].items():
            t, h = (op[s]["tracks"]["groups"]["all"] for s in ("train", "held"))
            lines.append(
                f"| {name} / {budget} | {pair(t['coverage'], h['coverage'], True)} | {pair(t['longest_correct_s'], h['longest_correct_s'])} | {pair(t['wrong_per_track_point'], h['wrong_per_track_point'], True)} | {pair(t['track_precision'], h['track_precision'], True)} | {t['wrong_object_frames']} / {h['wrong_object_frames']} |"
            )
    lines += [
        "",
        "Track precision and wrong-point rates use track points on visible labelled frames; no-ball and unlabelled frames do not enter those denominators. Coverage penalises a tracker that emits little.",
        "",
        "## Controlled throughput and a 90-minute match",
        "",
    ]
    throughput = e.get("throughput", {})
    if throughput:
        lines += [
            throughput["protocol"],
            "",
            f"Timing status: **{throughput['timing_status']}**; total quiet wait {throughput['total_quiet_wait_s']:.1f}s of the shared 900s cap. mediaanalysisd and PhotosReliveWidget are nonblocking steady background by orchestrator decision; active model generation and bench jobs remain blocking until the wait budget expires.",
            "",
            SPEED,
            "",
            "Four repeats had mean mediaanalysisd CPU≥30%, each also the slowest repeat of its model/sampling mode: r5-a native1, rf-b native1, rf-b sampled2, YOLO sampled2. They are labelled contended and retained in medians/ranges. This coincidence does not establish causation. RF b's2fps match projection ranges25.54–41.09min across repeats (about25–41min).",
            "",
            throughput["projection"],
            "",
            throughput["old_yolo_discrepancy"],
            "",
            throughput["contention_observation"]["limitation"],
            "",
            "| Model | Mode | Repeat FPS: sampled / native | Median FPS: sampled / native | 90 min at 2fps: wall min | 90 min at native fps: wall min |",
            "|---|---|---:|---:|---:|---:|",
        ]
        for name, row in throughput["models"].items():
            lines.append(
                f"| {name} | {row['mode']} | {', '.join(f(r['fps']) for r in row['repeats'])} / {', '.join(f(r['fps']) for r in row['native_repeats'])} | {f(row['median_fps'])} / {f(row['native_median_fps'])} | {f(row['match_2fps_minutes'])} | {f(row['match_native_minutes'])} |"
            )
        lines += [
            "",
            "Per-repeat caveats (summaries only; process IDs, resident memory and per-second traces are private):",
            "",
            "| Model / sampling / repeat | Status | mediaanalysisd CPU mean / max % | AGX GPU mean / max % |",
            "|---|---|---:|---:|",
        ]
        for name, row in throughput["models"].items():
            for sampling, key in (("sampled", "repeats"), ("native", "native_repeats")):
                for repeat in row[key]:
                    cpu = repeat["mediaanalysisd_cpu_percent"]
                    gpu = repeat["agx_gpu_utilisation_percent"]
                    lines.append(
                        f"| {name} / {sampling} / {repeat['repeat']} | {repeat['timing_status']} | {cpu['mean']:.1f} / {cpu['max']:.1f} | {gpu['mean']:.1f} / {gpu['max']:.1f} |"
                    )
        lines += [
            "",
            "| Model | Sampled FPS min–max | Native FPS min–max | 2fps match minutes min–max | Native match minutes min–max |",
            "|---|---:|---:|---:|---:|",
        ]
        for name, row in throughput["models"].items():
            lines.append(
                f"| {name} | "
                + " | ".join(
                    "–".join(f(v) for v in row[k])
                    for k in (
                        "repeats_fps_range",
                        "native_repeats_fps_range",
                        "match_2fps_minutes_range",
                        "match_native_minutes_range",
                    )
                )
                + " |"
            )
        lines += [
            "",
            f"Source frame rate: {throughput['native_fps']:.8f} fps. Mode fallback errors: {throughput['errors'] or 'none'}.",
            "",
            f"Optimized-versus-eager TRAIN probe: {throughput.get('optimized_train_parity', {})}.",
        ]
    lines += [
        "",
        "## Method for future rounds",
        "",
        FUTURE,
        "",
        "## What a fresh match must test",
        "",
        "Label a different match at a different venue/day, with players absent from training; freeze it as the true holdout before any recipe or threshold choice. Use blind initial annotation or an independently reviewed sample to check suggestion conditioning. Include distant balls, close/large balls, blur and occlusion, no-visible-ball intervals, footwear/line distractors and spare balls. Define the match-ball identity explicitly. Compare at TRAIN-chosen operating points with per-clip/sequence counts, not independent-frame claims. These 20 clips cannot support a product winner claim.",
        "",
        "Better source pixels help, but do not fix the problem alone: the prior bucket extrapolation was 60.7% → 66.4% held-out for 2× ball pixels, not a measurement. Scale diversity and semantic negatives still matter. A 4K/follow-cam export is a hypothesis to test on fresh footage, not a guarantee.",
        "",
        "## Kit and execution",
        "",
        str(e.get("kit", {})),
        "",
        "The kit is seeded only from the selected RF-DETR model at its TRAIN-chosen 1.0 operating point. MJ's existing 1057 labels are preserved, including accepted-source provenance; 48 scheduled frames remain unlabelled. Review suggestions, click remaining visible balls or mark no ball, then export. Keep new-match labels separate as the true holdout.",
        "",
        "Player-overlap buckets in historical analyses still use YOLO11n person detections: bench-only, not a licence-clean serving dependency. Frozen aggregate fixtures contain no label coordinates, images or checkpoints. Original protocol snapshots retain historical wording for hash verification; all current evaluation presentation uses ‘recipe-selected on these clips’.",
        "",
        p["protocol"]["corrections"],
        "",
        p["prior_push"],
        "",
        p.get("framing_review", {}).get("test_environment", ""),
        "",
        str(p.get("verification", {})),
        "",
    ]
    audit = p.get("checkpoint_integrity_review")
    if audit:
        lines += [
            "### Checkpoint integrity verification",
            "",
            audit["validation_rule"],
            "",
            audit["result"],
            "",
            "SHA256 prefixes below; full hashes and audit reproduction are in the execution fixture. No passes rerun; no table cells changed.",
            "",
            "| Pass | Weights path (private) | Declared | Recorded | On disk | Status |",
            "|---|---|---|---|---|---|",
        ]
        for row in audit["passes"]:
            lines.append(
                f"| {row['pass_id']} | {row['weights_path']} | "
                f"{row['declared_sha256'][:12]} | {row['recorded_sha256'][:12]} | "
                f"{row['on_disk_sha256'][:12]} | {row['status']} |"
            )
        lines += [""]
    lines += [
        "Outstanding limits: " + " ".join(p.get("not_done", [])),
        "",
        "# Historical rounds 1–4 — fixed 0.1, not comparable across model families",
        "",
        "The following numeric tables are retained for audit and comparison. Their fixed-confidence head-to-head interpretation and prior optimistic-exposure wording are superseded above.",
        "",
        historical.replace(OLD_LABEL, NEW_LABEL),
    ]
    return "\n".join(lines).rstrip() + "\n"
