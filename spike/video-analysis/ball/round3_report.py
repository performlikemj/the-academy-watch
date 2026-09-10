"""Review-corrected ledger: held-out headlines, explicit oracle and training columns."""

from __future__ import annotations


def f(v, percent=False):
    return "—" if v is None else f"{v * 100:.2f}%" if percent else f"{v:.2f}"


def pair(a, h, percent=False):
    return f"{f(a, percent)} / {f(h, percent)}"


def headline(rows):
    lines = [
        "| Candidate | H top-1 (manual-only) | H oracle over N boxes (manual-only) | H oracle precision | H boxes/visible on frame | H false/10s | H FPS | H gate | Incl. training clips: top-1 (manual) / oracle | All boxes / false/10s / FPS / gate |",
        "|---|---:|---:|---:|---:|---:|---:|---|---:|---:|",
    ]
    for r in rows:
        a, h = r["all"]["groups"]["on_ball"], r["held"]["groups"]["on_ball"]
        af, hf = (r[s]["groups"]["all"]["false_per_10s"] for s in ("all", "held"))
        lines.append(
            f"| {r['candidate']} | {f(h['top1_recall'], True)} ({f(h['manual_top1_recall'], True)}) | {f(h['oracle_recall'], True)} ({f(h['manual_oracle_recall'], True)}) | {f(h['precision'], True)} | {f(h['boxes_per_visible_frame'])} | {f(hf)} | {f(r['held']['fps'])} | {r['held']['gate']} | {f(a['top1_recall'], True)} ({f(a['manual_top1_recall'], True)}) / {f(a['oracle_recall'], True)} ({f(a['manual_oracle_recall'], True)}) | {f(a['boxes_per_visible_frame'])} / {f(af)} / {f(r['all']['fps'])} / {r['all']['gate']} |"
        )
    return lines


def markdown(data):
    p = data["round3"]
    e = p["measurements"]
    rows = e["results"]
    best = next((r for r in rows if r["candidate"] == e["current_best"]), None)
    label = p["evaluation_label"]
    legend = f"All = all 20 clips (incl. training clips); H = {label}, using the fixed six clips unless explicitly stated otherwise. Paired cells are All / H."
    h = best["held"]["groups"] if best else {}
    passing = [r["candidate"] for r in rows if r["held"]["gate"] == "PASS"]
    lines = [
        f"Human top-1 gate: **{', '.join(passing) or 'no candidate passes'}**. Proxy verdicts retire for this labelled sample.",
        "",
        (
            f"Current best under the authorized ≤2 false/10s selection rule: **{best['candidate']}**. H on-ball top-1 **{f(h['on_ball']['top1_recall'], True)}**, oracle over N boxes {f(h['on_ball']['oracle_recall'], True)}, oracle precision {f(h['on_ball']['precision'], True)}, **{f(h['all']['false_per_10s'])} false/10s**, {f(best['held']['fps'])} FPS; real gate **{best['held']['gate']}**."
            if best
            else "No model meets the current-best eligibility rule."
        ),
        "",
        f"{label}. **Current-best selection now uses held-out results and is optimistic beyond that prior exposure.** Fresh labelled club footage is the true test; these 20 clips are no longer a clean test set.",
        "",
        "# Ball human truth — round 3 review and scale targets",
        "",
        "Gate = highest-confidence top-1 on-ball recall ≥80% AND ≤1 detection/10s on explicit no-ball frames. Model eligibility at ≤2 false/10s is a separate selection rule, not a PASS. Matching is inclusive 20 native px at confidence ≥0.1; ties use saved order. Oracle precision credits at most one nearest box per visible label and penalises all duplicate guesses. Top-1 precision is reported separately below. Boxes/frame in headlines uses visible on-ball frames, matching the reviewer; JSON also retains boxes per all labelled frames.",
        "",
        "## Corrected round-1 headline (original 4/16 split)",
        "",
        f"H = {label}: original 16 evaluation clips for this table, 575 visible / 144 no-ball. On-ball H is the same two clips and 122 visible labels used below. Baselines are filtered to those same clips for comparability; none was fitted on this dataset. The All column preserves the reviewer’s six-on-ball-clip ranking.",
        "",
    ]
    lines += headline(e.get("round1_native_results", []))
    lines += [
        "",
        "Round-1 r1-960 was previously presented using 300 training on-ball labels plus 122 held-out labels. Its honest pipeline recall is **58.20% top-1 held-out**, versus 59.02% oracle; oracle precision on those same on-ball labels is 83.72%. All-clip 77.49% top-1 and 77.73% oracle are resubstitution-contaminated. Among round-1 candidates, r1-960 has the highest All on-ball top-1 recall; rf_3x3 falls from 87.20% oracle to 74.17% top-1 and fails the recall leg on all six on-ball clips.",
        "",
        "## Corrected round-2 and new scale-run headline (common 14/6 split)",
        "",
        legend,
        "",
    ]
    lines += headline(rows)
    lines += [
        "",
        "The all-clip columns are descriptive training-inclusive numbers. H false rates use 60 no-ball labels across all six H clips, while H recall/precision in the headline use the two on-ball clips. This is the predefined gate scope, not a mixture of training/test precision. FPS includes decode + inference and excludes loading, warmup, scoring and tracking. Baseline/R1/R2 timings are historical saved-pass measurements, not contemporaneous speed controls.",
        "",
        "## Precision, localisation and no-ball exposure",
        "",
        legend,
        "",
        "| Candidate | On top-1 precision All / H | On oracle precision All / H | On top-1 median error px All / H | On oracle median error px All / H | No-ball false/frame All / H | No-ball counts All / H |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        a, h = (r[s]["groups"]["on_ball"] for s in ("all", "held"))
        aa, hh = (r[s]["groups"]["all"] for s in ("all", "held"))
        lines.append(
            f"| {r['candidate']} | {pair(a['top1_precision'], h['top1_precision'], True)} | {pair(a['precision'], h['precision'], True)} | {pair(a['top1_error_px']['median'], h['top1_error_px']['median'])} | {pair(a['error_px']['median'], h['error_px']['median'])} | {aa['false_per_frame']:.4f} / {hh['false_per_frame']:.4f} | {aa['no_ball_predictions']}/{aa['no_ball_frames']} / {hh['no_ball_predictions']}/{hh['no_ball_frames']} |"
        )
    lines += [
        "",
        "| Candidate / group | Pooled top-1 All / H | Manual-only top-1 All / H | Oracle over N boxes All / H | Manual-only oracle All / H | Oracle precision All / H | False/10s All / H |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        for group in ("all", "off_pitch"):
            a, h = (r[s]["groups"][group] for s in ("all", "held"))
            lines.append(
                f"| {r['candidate']} / {group} | {pair(a['top1_recall'], h['top1_recall'], True)} | {pair(a['manual_top1_recall'], h['manual_top1_recall'], True)} | {pair(a['oracle_recall'], h['oracle_recall'], True)} | {pair(a['manual_oracle_recall'], h['manual_oracle_recall'], True)} | {pair(a['precision'], h['precision'], True)} | {pair(a['false_per_10s'], h['false_per_10s'])} |"
            )
    lines += [
        "",
        "## Permanent matching-rule controls",
        "",
        legend,
        "",
        e["controls"]["definition"],
        "",
        "Reviewer reference: shuffled-within-clip oracle recall about 4.0–5.5%, uniform random 0.2–1.2%, median hit error 1.4–1.9 px and <1.1% of hits beyond 10 px. The reviewer did not supply RNG seed/repetition/population details. The permanent controls below explicitly use seed 20260911, 100 ordinary permutations or random-centre replicates; differences are disclosed, not forced to those reference ranges. They are sanity floors, never gate candidates or training data. The reviewer’s hit-error range concerns the useful RF/YOLO matches, not every WASB result; exact hit counts below also expose RF2x2 on-ball 4/351 beyond 10px (1.14%), versus 7/757 overall (0.92%).",
        "",
        "| Candidate / sanity floor | On-ball top-1 mean All / H | On-ball oracle over N boxes mean All / H |",
        "|---|---:|---:|",
    ]
    for r in rows:
        for method in ("shuffled_within_clip", "uniform_random"):
            a, h = (
                e["controls"]["results"][s][method][r["candidate"]]["on_ball"]
                for s in ("all", "held")
            )
            lines.append(
                f"| {r['candidate']} / {method} | {pair(a['top1_recall']['mean'], h['top1_recall']['mean'], True)} | {pair(a['oracle_recall']['mean'], h['oracle_recall']['mean'], True)} |"
            )
    lines += [
        "",
        "| Candidate | Actual on-ball oracle median error px All / H | Hits beyond 10px / hits All / H |",
        "|---|---:|---:|",
    ]
    for r in rows:
        a, h = (r[s]["groups"]["on_ball"] for s in ("all", "held"))
        lines.append(
            f"| {r['candidate']} | {pair(a['error_px']['median'], h['error_px']['median'])} | {a['oracle_hits_beyond_10px']}/{a['matched']} / {h['oracle_hits_beyond_10px']}/{h['matched']} |"
        )
    lines += [
        "",
        "## No-ball visibility sensitivity",
        "",
        "**No-ball = no ball visible to the labeller.** Every detection on those frames counts false, even if it is a real ball MJ could not see. The reviewer classified 129 of 182 no-ball frames as mid-play; this is reviewer-supplied context, not a new occlusion annotation.",
        "",
        e["path_sensitivity_r1_original_split"]["definition"],
        "",
        "| r1-960 sensitivity scope | Strict false/10s All / H | Path-credited false/10s All / H | Credited detections All / H | Gate All / H |",
        "|---|---:|---:|---:|---|",
    ]
    for scope, key in (
        ("Original R1 16-clip H", "path_sensitivity_r1_original_split"),
        ("Common six-clip H", "path_sensitivity_common_six"),
    ):
        a, h = (e[key][s] for s in ("all", "held"))
        lines.append(
            f"| {scope} | {pair(a['strict_false_per_10s'], h['strict_false_per_10s'])} | {pair(a['path_credited_false_per_10s'], h['path_credited_false_per_10s'])} | {a['credits']} / {h['credits']} | FAIL / FAIL |"
        )
    lines += [
        "",
        "The two credits reproduce 2.42 → 2.20 false/10s All, still failing. One is in the original R1 holdout; both are in the R2/R3 train set. No labels are changed.",
        "",
        "## Track vs truth",
        "",
        legend,
        "",
        "Unchanged Kalman association reruns on saved detections without truth guidance. Track precision = points within 20px / track points where a visible label exists. Wrong rate = >50px points / that same denominator; report coverage alongside it so silence cannot look successful. Points on explicit no-ball and unlabelled frames are outside this precision denominator. Longest runs and episodes break on missing/no-ball/incorrect samples or fragment changes; seconds = correct samples/2.",
        "",
        "| Candidate | Coverage All / H | Track precision All / H | Longest correct s All / H | Wrong frames / track points All / H | Wrong per track point All / H | Wrong per visible All / H | Episodes All / H |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        a, h = (r[s]["tracks"]["groups"]["all"] for s in ("all", "held"))
        lines.append(
            f"| {r['candidate']} | {pair(a['coverage'], h['coverage'], True)} | {pair(a['track_precision'], h['track_precision'], True)} | {pair(a['longest_correct_s'], h['longest_correct_s'])} | {a['wrong_object_frames']}/{a['track_points_on_visible_frames']} / {h['wrong_object_frames']}/{h['track_points_on_visible_frames']} | {pair(a['wrong_per_track_point'], h['wrong_per_track_point'], True)} | {pair(a['wrong_per_visible'], h['wrong_per_visible'], True)} | {a['wrong_object_episodes']} / {h['wrong_object_episodes']} |"
        )
    lines += [
        "",
        "## Split, scale fit and the two new experiments",
        "",
        "Same deterministic 14/6 split as round 2: 753 training labels (631 visible, 122 no-ball), 304 H labels (244 visible, 60 no-ball). H contains two on-ball, two off-pitch and two other clips. Round 1 fitted only its four on-ball training clips (300 visible labels). Exact original and current split IDs and source hashes remain in JSON.",
        "",
        "| Role | Clip IDs |",
        "|---|---|",
    ]
    for role in ("train", "held_out"):
        lines.append(f"| {role} | " + "<br>".join(p["split"][role]) + " |")
    fit = p["scale_fit"]
    targets = p["target_distribution"]
    lines += [
        "",
        f"Actual TRAIN targets: median {targets['median_px']:.2f}px, p95 {targets['p95_px']:.2f}px; {targets['at_lower_clip']} clipped at 6px and {targets['at_upper_clip']} at 48px. There are 37 targets ≥24px: one on-ball, four other and 32 off-pitch. Large-ball supervision remains weak in the on-ball training domain; size correction does not add missing examples.",
        "",
    ]
    lines += [
        "",
        f"Affine native size estimate: **side = {fit['intercept_px']:.5f} + {fit['slope_px_per_image_y_px']:.8f} × image_y**; **R² {fit['r_squared']:.4f}**, {fit['observations']} nearest matched TRAIN boxes. {fit['fallback_labels']} of {fit['visible_train_labels']} visible train clicks need the affine fallback. Both recipes use the same train-only geometry fit. Matched apparent sizes are used directly where present; missing sizes use the fitted value, all clipped to [6,48] px. This replaces the fixed 18.68044 px side and removes its fixed doubling. Image y explains only part of scale variation; these detector extents are estimates, not human-drawn boxes.",
        "",
        "Exactly two new neural fits: r3-a repeats COCO-initialised r2-a; r3-b repeats r1-960-initialised r2-b. Both use 2×2@960, 100 requested epochs, 20-minute budget, batch 16, patience 6, seed 42 and the same AdamW/augmentation settings. Only target sizing changes. Checkpoint selection and early stopping use TRAIN loss only; no held-out images enter fitting. Time-budget mode can finish partial epochs and alter the effective schedule; MPS is not guaranteed bitwise deterministic.",
        "",
        "| Fit | Recipe / initial weights | MPS minutes | Recorded / selected epoch | Best TRAIN loss |",
        "|---|---|---:|---:|---:|",
    ]
    for round_name, fits in (
        ("r2", data["round2"]["measurements"]["selection"]["fits"]),
        ("r3", e.get("fits", {})),
    ):
        for letter, fit_record in fits.items():
            lines.append(
                f"| {round_name}-{letter} | 2×2@{fit_record['model_input_px']} / {fit_record['initial_weights'].split('/tinyball/')[-1]} | {fit_record['training_s'] / 60:.2f} | {fit_record['epochs_recorded']} / {fit_record['best_epoch']} | {fit_record['best_train_loss']:.5f} |"
            )
    lines += [
        "",
        "Round-1 recipes and timings remain visible for comparison:",
        "",
        "| Fit | Tile input | MPS minutes | Completed / requested epochs |",
        "|---|---:|---:|---:|",
    ]
    for r in data["execution"]["training"]:
        lines.append(
            f"| {r['candidate']} | {r['model_input_px']} | {r['training_minutes']:.2f} | {r['epochs_completed']} / {r['epochs_requested']} |"
        )
    lines += [
        "",
        p["selection_rule"],
        "",
        "Round 2 historically preselected d by TRAIN loss; that rule is superseded for current-best selection, not rewritten as if it had used evaluation. Its historical fit/selection snapshot remains in the execution fixture. The scale hypothesis itself was prompted by held-out error analysis, adding another source of optimism. Selection across R2 a–d and R3 a–b uses the common six-clip H subset; all runs and thresholds are reported.",
        "",
        "## Size-bucket recall: old versus scale-aware targets",
        "",
        legend,
        "",
        "Independent size = median of nearest matched RF full/2×2/3×3 shorter sides within 20px. Trained box sizes never define these buckets. Some model misses can therefore receive an independent estimate; unmatched labels retain an unknown-size bucket. Sizes are association-confirmed detector extents, not true human-measured diameters.",
        "",
        "| RF size estimator | Matched sizes All / H | Median / p95 native px All | Median / p95 native px H |",
        "|---|---:|---:|---:|",
    ]
    for r in rows:
        if r["candidate"] not in ("rf_full", "rf_2x2", "rf_3x3"):
            continue
        a, h = (
            r[s]["groups"]["all"]["matched_box_short_side_px"] for s in ("all", "held")
        )
        lines.append(
            f"| {r['candidate']} | {a['n']} / {h['n']} | {f(a['median'])} / {f(a['p95'])} | {f(h['median'])} / {f(h['p95'])} |"
        )
    sizes = [
        ("0", "<6"),
        ("1", "6–<10"),
        ("2", "10–<16"),
        ("3", "16–<24"),
        ("4", "≥24"),
        ("unknown", "unknown"),
    ]
    lines += [
        "",
        "| Recipe / size px | Visible All / H | Old top-1 All / H | New top-1 All / H | Old oracle All / H | New oracle All / H |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for letter in "ab":
        old = e["errors"][f"tinyball-r2-{letter}"]
        new = e["errors"].get(f"tinyball-r3-{letter}")
        if new is None:
            continue
        for key, name in sizes:

            def values(record, rule):
                return [
                    record[rule][s]["buckets"]["size_bucket"][key]
                    for s in ("all", "held")
                ]

            a, h = values(old, "top1")
            na, nh = values(new, "top1")
            oa, oh = values(old, "oracle")
            noa, noh = values(new, "oracle")
            lines.append(
                f"| {letter} / {name} | {a['visible']} / {h['visible']} | {pair(a['recall'], h['recall'], True)} | {pair(na['recall'], nh['recall'], True)} | {pair(oa['recall'], oh['recall'], True)} | {pair(noa['recall'], noh['recall'], True)} |"
            )
    lines += ["", p.get("scale_findings", "Scale experiments pending."), ""]
    if best:
        error = e["errors"][best["candidate"]]["top1"]
        lines += [
            "",
            f"Current best {best['candidate']}: **top-1** error buckets on on-ball clips. "
            + legend,
            "",
            "| Bucket | Misses / visible All | Misses / visible H | Top-1 recall All / H |",
            "|---|---:|---:|---:|",
        ]
        categories = {
            "size_bucket": sizes,
            "image_y": [
                ("0", "image y <360"),
                ("1", "image y 360–<720"),
                ("2", "image y ≥720"),
            ],
            "motion": [
                ("0", "motion <10 px/sample"),
                ("1", "motion 10–<50"),
                ("2", "motion ≥50"),
                ("unknown", "motion unknown"),
            ],
            "player_overlap": [
                ("inside", "inside player box"),
                ("outside", "outside detected player boxes"),
                ("unknown", "player pass unknown"),
            ],
        }
        for kind, names in categories.items():
            for key, name in names:
                a, h = (error[s]["buckets"][kind][key] for s in ("all", "held"))
                lines.append(
                    f"| {name} | {a['misses']}/{a['visible']} | {h['misses']}/{h['visible']} | {pair(a['recall'], h['recall'], True)} |"
                )
        lines += [
            "",
            "Image y is an imperfect distance proxy; 2fps displacement includes camera movement and is not measured blur. A click inside a saved COCO person box is projected overlap, not verified occlusion. Error categories overlap and their miss counts must not be added.",
            "",
            *[f"- {s}" for s in p.get("error_findings", [])],
            "",
            p.get(
                "single_next_change", "Scale experiments pending; no conclusion yet."
            ),
        ]
    lines += [
        "",
        "## What better footage would change",
        "",
        "The frozen footage is a 1080p wide Veo export. Native 4K at the same field of view would double source ball diameter; follow-cam can put more pixels on the ball. Preserve those pixels through tile count/input resolution or a tighter field of view: resizing fixed 4K tiles to the same input can erase the gain. Upscaling the current video adds no detail.",
        "",
        "**Better footage helps, but is not a fix on its own.** The historical r2-d oracle extrapolation was 60.7% → 66.4% H at 2× ball pixels, still below 80%; it is not measured 4K performance. Non-monotonic size recall and clear large-ball misses rule out presenting 4K as a solution by itself.",
        "",
        "| Projection / matching rule | Observed All / H | Extrapolated at 2× px All / H | Supported frames All / H |",
        "|---|---:|---:|---:|",
    ]
    for name, rule in [("tinyball-r2-d", "oracle")] + (
        [(best["candidate"], "top1")] if best else []
    ):
        a, h = (
            e["errors"][name][rule][s]["double_size_projection"]
            for s in ("all", "held")
        )
        lines.append(
            f"| {name} / {rule} | {pair(a['observed_recall'], h['observed_recall'], True)} | {pair(a['projected_recall'], h['projected_recall'], True)} | {a['supported_frames']} / {h['supported_frames']} |"
        )
    lines += [
        "",
        p.get("footage_finding", ""),
        "",
        "Projection maps each measurable ball to its doubled-size bucket and assigns that bucket’s empirical recall; unknown/unsupported bins retain observed outcomes. This is a fragile association, not a causal estimate. Sparse buckets, RF-conditioned size availability and reused evaluation clips limit it. The real test is new labelled club footage reserved before any tuning.",
        "",
        "## Label provenance and forward bias",
        "",
        legend,
        "",
        "1,057 validated labels: 875 visible / 182 no-ball, 352 accepted / 705 manual, zero rejected. Coverage: 506/540 on-ball targets, 99/100 off-pitch targets, plus 452 extras. 48 frames remain unlabelled. Exact coverage keys, per-clip counts and label SHA256 remain in JSON; labels and weights stay outside Git.",
        "",
        "Manual-only recall is beside pooled recall in every detection headline and group table. Acceptance records already require source_accepted, accepted_source and accepted_score in both Python and browser validation; Accept records the specific model source, and a hand click clears acceptance provenance. These fields survive import/export and allow next-round source-stratified scoring. Accepted/manual differences remain confounded by difficulty and source; they are not causal bias estimates.",
        "",
        "| Candidate | Pooled top-1 All / H | Manual top-1 All / H | Accepted top-1 All / H | Manual oracle All / H | Accepted oracle All / H |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        a, h = (r[s]["provenance_bias"] for s in ("all", "held"))
        aa, hh = (r[s]["groups"]["all"] for s in ("all", "held"))
        lines.append(
            f"| {r['candidate']} | {pair(aa['top1_recall'], hh['top1_recall'], True)} | {pair(a['manual']['top1_recall'], h['manual']['top1_recall'], True)} | {pair(a['accepted']['top1_recall'], h['accepted']['top1_recall'], True)} | {pair(a['manual']['oracle_recall'], h['manual']['oracle_recall'], True)} | {pair(a['accepted']['oracle_recall'], h['accepted']['oracle_recall'], True)} |"
        )
    lines += [
        "",
        "RF3x3’s accepted-suggestion oracle recall was 97.73% versus 83.75% manual across visible labels. Round-1 kit build 5 seeded 606 suggestions from r1-960; round-2 build 6 actually seeded 663 from r2-d. Both can bias future acceptance toward the supplying model. Manual-only reporting and source recording expose this risk but cannot make reused clips a clean test set.",
        "",
        "## Execution, kit and caveats",
        "",
        *[f"- {s}" for s in p.get("kit_notes", data["round2"].get("kit_notes", []))],
        "",
        *[f"- {s}" for s in p.get("decisions", [])],
        "",
        f"- Prior exposure: {label}. The r1-960 49.39% original held-out overall oracle recall also served as its own 640-vs-960 selection statistic: one binary aggregate choice. Round3 additionally uses held-out error analysis and explicit held-out model selection, so its selected estimate is more optimistic.",
        "- Round-1 exported last.pt; no held-out-selected best.pt leak. Round2/3 best.pt is selected only by augmented TRAIN loss, with held-out validation and final validation disabled. Model selection after these fits is separate and explicitly evaluation-based in round3.",
        "- The 20 clips come from one match; adjacent samples are correlated. Sample gate PASS/FAIL is legitimate under the stated labels and rules, but does not certify unseen matches or continuous event rates. False/10s is exposure-normalised from 2fps no-ball samples.",
        "- human_measurements.json.gz and round2_measurements.json.gz are historical filenames for scored aggregate output, not raw measurements or human labels. round3_scored_output.json.gz follows the clearer naming. Ledger rendering requires no labels, weights, footage, torch or .git.",
        "- All frozen numeric scoring is reproduced from saved detections; only the two newly authorized scale fits received new inference. The saved person pass is reused. No threshold search or third scale fit.",
        "",
        *[f"- {s}" for s in p.get("checks", [])],
        "",
        "Not done:",
        "",
        *[
            f"- {s}"
            for s in p.get(
                "not_done", ["Two scale experiments and final gates pending."]
            )
        ],
        "",
    ]
    return "\n".join(lines)
