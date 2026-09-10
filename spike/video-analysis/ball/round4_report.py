"""Deterministic trainer-swap report, retaining prior rounds as historical evidence."""

from __future__ import annotations

from round3_report import f, pair


def markdown(data, historical):
    p = data["round4"]
    e = p["measurements"]
    rows = e["results"]
    selected = e["current_best_licence_clean"]
    diagnostic = e["diagnostic_recall_leader"]
    best = next(r for r in rows if r["candidate"] == (selected or diagnostic))
    bar = next(r for r in rows if r["candidate"] == "tinyball-r2-b")
    h = best["held"]["groups"]
    delta = 100 * (
        h["on_ball"]["top1_recall"] - bar["held"]["groups"]["on_ball"]["top1_recall"]
    )
    passing = [r["candidate"] for r in rows if r["held"]["gate"] == "PASS"]
    improvements = e["improvements_over_r2_b"]
    legend = f"All = all 20 clips (incl. training clips); H = {p['evaluation_label']}. All / H always uses the same fixed 14/6 split. H has 244 visible / 60 no-ball labels overall, including 122 visible on-ball labels. These clips have also informed subsequent error analysis and model selection; H is optimistic and is not a clean test set."
    lines = [
        f"Trainer swap — held-out top-1 real gate: **{', '.join(passing) or 'no candidate passes'}**.",
        "",
        f"{'Current best licence-clean model' if selected else 'No RF-DETR model qualifies at ≤2 false/10s; diagnostic recall leader'}: **{selected or diagnostic}**, H on-ball top-1 **{f(h['on_ball']['top1_recall'], True)}**, manual-only {f(h['on_ball']['manual_top1_recall'], True)}, **{f(h['all']['false_per_10s'])} false/10s**, {f(best['held']['fps'])} FPS. Versus YOLO r2-b: **{delta:+.2f} percentage points** H on-ball recall.",
        "",
        f"Improvement under the required recall-and-false-rate rule: **{', '.join(improvements) or 'none'}**. The RF-DETR product direction does not depend on YOLO winning this benchmark.",
        "",
        p["product_policy"],
        "",
        "RF-DETR Nano uses the Apache-2.0 implementation and official COCO weights; the installed package licence is recorded with its hash in the execution fixture. [Upstream package and model licensing](https://github.com/roboflow/rf-detr#license).",
        "",
        "# Trainer swap: RF-DETR versus YOLO11-nano",
        "",
        legend,
        "",
        "Selection intentionally uses the highest H on-ball top-1 recall among RF runs with H strict false/10s ≤2. Selected estimates are optimistic by construction. Improvement requires beating r2-b's 68.03% H top-1 **without increasing** its 1.67 false/10s. The separate real gate remains ≥80% top-1 and ≤1 false/10s. No confidence-threshold search: every run uses ≥0.1 and inclusive 20 native px matching.",
        "",
        "## Held-out headline, with training-inclusive results separate",
        "",
        "| Candidate | H top-1 | H manual-only | H oracle over N boxes | Incl. training: All top-1 / manual / oracle | Boxes/visible on frame All / H | Strict false/10s All / H | FPS All / H | Gate All / H | Training min |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|---:|",
    ]
    for r in rows:
        a, h = (r[s]["groups"]["on_ball"] for s in ("all", "held"))
        aa, hh = (r[s]["groups"]["all"] for s in ("all", "held"))
        fits = (
            e["fits"]
            if r["candidate"].startswith("tinyball-r4-")
            else data["round3"]["measurements"]["fits"]
            if r["candidate"].startswith("tinyball-r3-")
            else data["round2"]["measurements"]["selection"]["fits"]
        )
        minutes = fits[r["candidate"][-1]]["training_s"] / 60
        lines.append(
            f"| {r['candidate']} | {f(h['top1_recall'], True)} | {f(h['manual_top1_recall'], True)} | {f(h['oracle_recall'], True)} | {f(a['top1_recall'], True)} / {f(a['manual_top1_recall'], True)} / {f(a['oracle_recall'], True)} | {pair(a['boxes_per_visible_frame'], h['boxes_per_visible_frame'])} | {pair(aa['false_per_10s'], hh['false_per_10s'])} | {pair(r['all']['fps'], r['held']['fps'])} | {r['all']['gate']} / {r['held']['gate']} | {minutes:.2f} |"
        )
    lines += [
        "",
        "## Precision, localisation and overall detection",
        "",
        legend,
        "",
        "| Candidate / group | Top-1 recall All / H | Manual-only top-1 All / H | Top-1 precision All / H | Oracle over N recall All / H | Oracle precision All / H | Top-1 median error px All / H | Oracle median error px All / H | Boxes/labelled frame All / H |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        for group in ("on_ball", "all"):
            a, h = (r[s]["groups"][group] for s in ("all", "held"))
            cells = [
                pair(a[k], h[k], True)
                for k in (
                    "top1_recall",
                    "manual_top1_recall",
                    "top1_precision",
                    "oracle_recall",
                    "precision",
                )
            ]
            cells += [
                pair(a[k]["median"], h[k]["median"])
                for k in ("top1_error_px", "error_px")
            ]
            cells += [pair(a["boxes_per_frame"], h["boxes_per_frame"])]
            lines.append(f"| {r['candidate']} / {group} | " + " | ".join(cells) + " |")
    lines += [
        "",
        "Top-1 precision counts one highest-confidence prediction per labelled frame, including false predictions on no-ball frames in that group. Oracle precision counts all emitted guesses in its denominator. All and H precision each use their own labels; no whole-corpus precision is paired with H recall. FPS includes native decoding, padding, inference and NMS; excludes loading/warmup and scoring/tracking. Historical YOLO timings were not rerun; runtime differences prevent attributing the entire FPS gap to architecture.",
        "",
        "On-ball H manual-only recall is lower because MJ hand-clicked frames where no suggestion existed: a harder subset. This is expected difficulty confounding, not by itself evidence of model bias. Overall cohort comparisons also change clip composition and can reverse that ordering, as the overall RF rows show. Accepted-source provenance remains available; suggestions are unconfirmed and must never become automatic labels.",
        "",
        "## No-ball and near-path sensitivity",
        "",
        legend,
        "",
        "No-ball = no ball visible to the labeller. Every emitted box counts false, even a potentially correct ball MJ could not see. Path credits are only a sensitivity analysis (≤50px from a linear path bracketed by visible labels ≤1.01s apart), not verified invisible-ball detections; the gate uses strict counts.",
        "",
        "| Candidate | False count / no-ball frames All / H | False/frame All / H | Strict false/10s All / H | Near-path credits All / H | Path-credited false/10s All / H |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        a, h = (r[s]["groups"]["all"] for s in ("all", "held"))
        pa, ph = (e["path_sensitivity"][r["candidate"]][s] for s in ("all", "held"))
        lines.append(
            f"| {r['candidate']} | {a['no_ball_predictions']}/{a['no_ball_frames']} / {h['no_ball_predictions']}/{h['no_ball_frames']} | {a['false_per_frame']:.4f} / {h['false_per_frame']:.4f} | {pair(a['false_per_10s'], h['false_per_10s'])} | {pa['credits']} / {ph['credits']} | {pair(pa['path_credited_false_per_10s'], ph['path_credited_false_per_10s'])} |"
        )
    lines += [
        "",
        "## Exact fit configurations and training-only scale rule",
        "",
        "Both fits were specified before evaluation. No alternative floor was tried. Affine(y) = -12.4205756808 + 0.04820986555 × native image y; TRAIN-only R²=0.4943506566, 545 matched observations from 631 visible training labels. Every target is clamp(affine(y), 18.6804351807, 48) px. This deliberately supersedes round 3's direct matched-size override. 592/631 targets sit at the floor, 23 are ≥24px; median 18.68px, maximum 32.85px. Box extents are teacher estimates associated with human clicks, not manually drawn ball boundaries.",
        "",
        "Native 2×2 tiles are 960×540, padded below with 420px RGB114 to 960×960. At 640, content is 640×360 and minimum target 12.45px; at 960, content is 960×540 and minimum target 18.68px. No anisotropic squash. Each fit uses 3012 training tiles: 631 positive/2381 negative. No held-out or unlabelled frame is a training negative. Pseudo-labels were off and require --pseudo.",
        "",
        "| Fit | Class / square resolution | Initialization | Batch / accumulation | Complete epochs + partial tiles | Final optimizer steps | MPS training minutes | LR / encoder LR | Seed |",
        "|---|---|---|---:|---:|---:|---:|---|---:|",
    ]
    for c, fit in e["fits"].items():
        partial = sum(r["images"] for r in fit["history"] if not r["complete"])
        lines.append(
            f"| {c} | {fit['model']} / {fit['resolution']} | {'COCO Nano' if c == 'a' else 'a final checkpoint; fresh optimizer'} | {fit['batch']} / {fit['gradient_accumulation']} | {fit['epochs_complete']} + {partial}/3012 | {fit['optimizer_steps']} | {fit['training_s'] / 60:.2f} | {fit['lr']:.3g} / {fit['lr_encoder']:.3g} | {fit['seed']} |"
        )
    lines += [
        "",
        f"Run b adds {e['fits']['b']['training_s'] / 60:.2f} training minutes after a; cumulative a→b cost is {sum(v['training_s'] for v in e['fits'].values()) / 60:.2f} minutes. Model loading, dataset preparation and later inference are outside these training timers.",
    ]
    lines += [
        "",
        "AdamW, weight decay 0.0001; RF-DETR official encoder layer decay 0.8 and decoder component decay 0.7; 100-step linear warmup, constant thereafter (epoch100 step decay is configured but not reached). Gradient norm clip 0.1, FP32, no EMA, horizontal flip 0.5 only. 100 epochs requested, 29-minute fit cap with six complete TRAIN-epoch patience. Final parameters at the last optimizer step are exported, including a budget-ended partial epoch; no minimum-loss checkpoint is restored. Final/partial epoch losses and full package/configuration provenance are retained in JSON. MPS deterministic algorithms warn where kernels cannot be deterministic.",
        "",
        "### Train clip ids",
        "",
    ]
    lines += [f"- `{c}`" for c in p["split"]["train"]]
    lines += ["", f"### {p['evaluation_label']}: clip ids", ""]
    lines += [f"- `{c}`" for c in p["split"]["held_out"]]
    lines += [
        "",
        "## Size buckets: highest-confidence hits / visible labels",
        "",
        legend,
        "",
        "Sizes are the same frozen independent RF full/2×2/3×3 matched-box short-side median used in round 3. RF-DETR's learned target sizes do not define these buckets. Missing teacher matches remain unknown; excluding them would flatter recall.",
        "",
        "| Candidate | <6px All / H | 6–<10px All / H | 10–<16px All / H | 16–<24px All / H | ≥24px All / H | Unknown All / H |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        a, h = (
            e["errors"][r["candidate"]]["top1"][s]["buckets"]["size_bucket"]
            for s in ("all", "held")
        )
        cells = [
            f"{a[k]['matched']}/{a[k]['visible']} / {h[k]['matched']}/{h[k]['visible']}"
            for k in ("0", "1", "2", "3", "4", "unknown")
        ]
        lines.append(f"| {r['candidate']} | " + " | ".join(cells) + " |")
    lines += [
        "",
        "## Matching-rule sanity floors",
        "",
        legend,
        "",
        "Same permanent seed 20260911, 100 repetitions; corrupt label positions within each evaluation scope while keeping detections fixed. Means below are sanity floors, not alternate truth or a threshold-tuning set.",
        "",
        "| RF candidate / control | On-ball top-1 mean All / H | On-ball oracle mean All / H |",
        "|---|---:|---:|",
    ]
    for name in ("tinyball-r4-rf-a", "tinyball-r4-rf-b"):
        for method in ("shuffled_within_clip", "uniform_random"):
            a, h = (
                e["controls"]["results"][s][method][name]["on_ball"]
                for s in ("all", "held")
            )
            lines.append(
                f"| {name} / {method} | {pair(a['top1_recall']['mean'], h['top1_recall']['mean'], True)} | {pair(a['oracle_recall']['mean'], h['oracle_recall']['mean'], True)} |"
            )
    lines += [
        "",
        "## Track versus truth",
        "",
        legend,
        "",
        (
            "Best eligible RF-DETR versus YOLO r2-b."
            if selected
            else "No eligible licence-clean model: show the RF recall leader diagnostically alongside YOLO r2-b."
        ),
        "",
        "| Candidate | Coverage All / H | Longest correct run seconds All / H | Wrong frames All / H | Track points on visible labels All / H | Wrong/track-point All / H | Track precision All / H | Wrong episodes All / H |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in (bar, best):
        a, h = (r[s]["tracks"]["groups"]["all"] for s in ("all", "held"))
        lines.append(
            f"| {r['candidate']} | {pair(a['coverage'], h['coverage'], True)} | {pair(a['longest_correct_s'], h['longest_correct_s'])} | {a['wrong_object_frames']} / {h['wrong_object_frames']} | {a['track_points_on_visible_frames']} / {h['track_points_on_visible_frames']} | {pair(a['wrong_per_track_point'], h['wrong_per_track_point'], True)} | {pair(a['track_precision'], h['track_precision'], True)} | {a['wrong_object_episodes']} / {h['wrong_object_episodes']} |"
        )
    lines += [
        "",
        "Unchanged Kalman parameters; correct≤20px, wrong>50px. Rates use emitted track points when a visible label exists; no-ball track points are outside this precision denominator. Coverage penalises silence, so a sparse track cannot claim quality from a small wrong count alone.",
        "",
        "## Verdict, next experiment and footage",
        "",
        p.get("verdict", "Verdict pending execution completion."),
        "",
        p.get("next_step", "Next step pending measured error buckets."),
        "",
        "Better footage would multiply ball pixels, but it is not an established fix on its own. Historical r2-d's 2×-pixels extrapolation was 60.7→66.4% H oracle recall, not measured 4K performance. Size-bucket associations are confounded by distance, occlusion and teacher-matched selection. They neither predict false rates nor establish an 80%/1-false gate pass. Fresh labelled 4K/follow-cam club clips must be reserved as the true test.",
        "",
        "## Kit and execution caveats",
        "",
        p["kit"].get("status", "pending"),
        "",
    ]
    lines += [f"- {v}" for v in p["decisions"]]
    if p.get("verification"):
        lines += ["", "Verification: " + p["verification"]["summary"]]
    lines += ["", "Not done:", ""]
    lines += [f"- {v}" for v in p.get("not_done", [])]
    lines += [
        "",
        "# Historical rounds 1–3 (retained verbatim)",
        "",
        "The current product direction and round 4 verdict above supersede historical current-best and proposed-next-experiment statements below. Historical tables retain their original measurements and caveats.",
        "",
        historical,
    ]
    return "\n".join(lines)
