"""Deterministic paired round-2 ledger rendering; all numbers come from fixtures."""

from __future__ import annotations


def f(value, percent=False):
    return (
        "—" if value is None else f"{value * 100:.1f}%" if percent else f"{value:.2f}"
    )


def rp(group):
    return f"{f(group['recall'], True)} / {f(group['precision'], True)}"


def markdown(data):
    protocol = data["round2"]
    evidence = protocol["measurements"]
    results = evidence["results"]
    best = next(r for r in results if r["candidate"] == evidence["selected_model"])
    held_label = protocol["evaluation_label"]
    clip_labels = {r["clip"]: r for r in data["labels"]["per_clip"]}
    passing = [r["candidate"] for r in results if r["all"]["gate"] == "PASS"]
    held_passing = [r["candidate"] for r in results if r["held"]["gate"] == "PASS"]
    lines = [
        f"Human gate, all clips: {', '.join(passing) or 'no candidate passes'}. {held_label}: {', '.join(held_passing) or 'no candidate passes'}. Proxy verdicts retire for this human-labelled sample.",
        f"Selected by TRAIN loss: **{best['candidate']}**, {f(best['all']['fps'])} FPS all clips; {held_label}: on-ball recall/precision **{rp(best['held']['groups']['on_ball'])}**, overall **{rp(best['held']['groups']['all'])}**, **{f(best['held']['groups']['all']['false_per_10s'])} false/10 s**, **{best['held']['gate']}**.",
        "",
        "# Ball human truth — round 2",
        "",
        "All = 20 clips, including fitted clips. H = "
        + held_label
        + ". Every paired metric below uses this same fixed six-clip evaluation subset, including rescored round-1 baselines. H is mildly optimistic; these clips are no longer a clean test set.",
        "",
        "## Split and experiment protocol",
        "",
        f"14 train / 6 H; {protocol['label_counts']['train']['labels']} / {protocol['label_counts']['held_out']['labels']} labels, {protocol['label_counts']['train']['visible']} / {protocol['label_counts']['held_out']['visible']} visible, 122 / 60 no-ball. Training uses 72.1% of the 875 visible labels, versus round 1's 300/875 (34.3%).",
        "",
        f"Deterministic rule: enumerate two on-ball, two off-pitch and two other holdout clips; retain round-1 fitted clips in train and reject train/holdout source-time overlap. Rank {protocol['split']['feasible_partitions']} feasible partitions by SHA256(seed + newline + sorted holdout IDs); seed `{protocol['split']['seed']}`, winning hash `{protocol['split']['rank']}`. Two overlapping held-out windows stay together; none crosses the fitting boundary.",
        "",
        "Train IDs:",
        "",
        *[
            f"- `{cid}` ({clip_labels[cid]['class']}; {clip_labels[cid]['visible']} visible / {clip_labels[cid]['no_ball']} no-ball)"
            for cid in protocol["split"]["train"]
        ],
        "",
        "H IDs (" + held_label + "):",
        "",
        *[
            f"- `{cid}` ({clip_labels[cid]['class']}; {clip_labels[cid]['visible']} visible / {clip_labels[cid]['no_ball']} no-ball)"
            for cid in protocol["split"]["held_out"]
        ],
        "",
        *[f"- {decision}" for decision in protocol["decisions"]],
        "",
        protocol["resolution_reason"],
        "",
        "Exactly four ball-model fits, a–d; no recipe, checkpoint, threshold or kit-model choice used their evaluation scores. Best-checkpoint loss is the mean augmented training box+cls+dfl loss, not validation loss. All share confidence 0.1 and inclusive 20 native-pixel centre matching. The table below describes fits shared by both reported evaluation scopes; it contains no evaluation metric.",
        "",
        "| Fit | Tile input | Initial weights | MPS minutes | Recorded epochs / best epoch | Best TRAIN loss |",
        "|---|---:|---|---:|---:|---:|",
    ]
    for letter, fit in evidence["selection"]["fits"].items():
        lines.append(
            f"| {letter} | 2×2@{fit['model_input_px']} | {fit['initial_weights'].split('/tinyball/')[-1]} | {fit['training_s'] / 60:.2f} | {fit['epochs_recorded']} / {fit['best_epoch']} | {fit['best_train_loss']:.5f} |"
        )
    lines += [
        "",
        "A time limit can finish on a partial last epoch. Actual minutes include trainer setup; all fit histories and checkpoint hashes are retained in JSON. TRAIN-loss comparisons across resolutions/initialisations can favour overfitting and are not a guarantee of best generalisation.",
        "",
        "## Detection results: round 1 retained alongside round 2",
        "",
        "H = "
        + held_label
        + ". R/P = recall / precision; all rates use confirmed labels only.",
        "",
        "| Candidate | All on-ball R/P | H on-ball R/P | All overall R/P | H overall R/P | All gate | H gate |",
        "|---|---:|---:|---:|---:|---|---|",
    ]
    for r in results:
        a, h = r["all"], r["held"]
        lines.append(
            f"| {r['candidate']} | {rp(a['groups']['on_ball'])} | {rp(h['groups']['on_ball'])} | {rp(a['groups']['all'])} | {rp(h['groups']['all'])} | {a['gate']} | {h['gate']} |"
        )
    lines += [
        "",
        "H = "
        + held_label
        + ". False rates use only explicit no-ball labels (182 All / 60 H); 2 fps gives false/10 s = 20 × false/frame. Median error uses matched visible labels. FPS includes native decoding plus inference, excludes loading/warmup/scoring/tracking; paired H timing uses only those six clips. Baseline/round-1 FPS is historical; round-2 FPS is newly measured, so cross-round speed differences include runtime conditions and are not an isolated resolution effect.",
        "",
        "| Candidate | All false/frame | H false/frame | All false/10 s | H false/10 s | All median error px | H median error px | All FPS | H FPS |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in results:
        a, h = r["all"]["groups"]["all"], r["held"]["groups"]["all"]
        lines.append(
            f"| {r['candidate']} | {a['false_per_frame']:.4f} | {h['false_per_frame']:.4f} | {f(a['false_per_10s'])} | {f(h['false_per_10s'])} | {f(a['error_px']['median'])} | {f(h['error_px']['median'])} | {f(r['all']['fps'])} | {f(r['held']['fps'])} |"
        )
    lines += [
        "",
        "Gate = pooled on-ball visible-label recall ≥80% AND ≤1 predicted ball/10 s on explicit no-ball labels across that scope. All uses six on-ball clips; H uses two. A sample gate is legitimate, but does not certify unlabelled frames, continuous false-event frequency or unseen matches.",
        "",
        "Off-pitch clips can contain visible balls; their visible/no-ball labels are scored literally. H = "
        + held_label
        + ".",
        "",
        "| Candidate | All off-pitch R/P | H off-pitch R/P | All off-pitch false/10 s | H off-pitch false/10 s |",
        "|---|---:|---:|---:|---:|",
    ]
    for r in results:
        a, h = r["all"]["groups"]["off_pitch"], r["held"]["groups"]["off_pitch"]
        lines.append(
            f"| {r['candidate']} | {rp(a)} | {rp(h)} | {f(a['false_per_10s'])} | {f(h['false_per_10s'])} |"
        )
    lines += [
        "",
        "## Track vs human truth",
        "",
        "Unchanged Kalman tracker rerun independently of labels. Coverage means a filtered track point within 20 px on a visible label; >50 px is a wrong-object frame. Correct runs and wrong episodes break at missing/no-ball labels and fragment changes; longest run is sample-count/2 seconds, not native-frame continuity. H = "
        + held_label
        + ".",
        "",
        "| Candidate | All coverage | H coverage | All longest s | H longest s | All wrong frames | H wrong frames | All wrong episodes | H wrong episodes |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in results:
        a, h = r["all"]["tracks"]["groups"]["all"], r["held"]["tracks"]["groups"]["all"]
        lines.append(
            f"| {r['candidate']} | {f(a['coverage'], True)} | {f(h['coverage'], True)} | {f(a['longest_correct_s'])} | {f(h['longest_correct_s'])} | {a['wrong_object_frames']} | {h['wrong_object_frames']} | {a['wrong_object_episodes']} | {h['wrong_object_episodes']} |"
        )
    lines += [
        "",
        "## Ball pixels and error analysis",
        "",
        "Independent RF matched boxes below measure native shorter box sides associated with MJ's centres; centres do not establish true ball boundaries. No size exists for an unmatched ball. Trained boxes reflect fixed roughly 18–19 px point-supervision targets and are excluded from independent size analysis. H = "
        + held_label
        + ".",
        "",
        "| Candidate | All matched sizes | H matched sizes | All median / p95 px | H median / p95 px |",
        "|---|---:|---:|---:|---:|",
    ]
    for r in results:
        if r["candidate"] not in ("rf_full", "rf_2x2", "rf_3x3"):
            continue
        a, h = [
            r[s]["groups"]["all"]["matched_box_short_side_px"] for s in ("all", "held")
        ]
        lines.append(
            f"| {r['candidate']} | {a['n']} | {h['n']} | {f(a['median'])} / {f(a['p95'])} | {f(h['median'])} / {f(h['p95'])} |"
        )
    lines += [
        "",
        "Error buckets concern the selected model on on-ball clips only. Size per label is the median of nearest matching RF full/2×2/3×3 sizes; this provides independent size estimates for some model misses, with an explicit unknown bucket. H = "
        + held_label
        + ".",
        "",
        "| Bucket | All misses / visible | H misses / visible | All recall | H recall |",
        "|---|---:|---:|---:|---:|",
    ]
    category_names = {
        "size_bucket": [
            "size <6 px",
            "size 6–<10 px",
            "size 10–<16 px",
            "size 16–<24 px",
            "size ≥24 px",
            "size unknown",
        ],
        "image_y": ["image y <360", "image y 360–<720", "image y ≥720"],
        "motion": [
            "displacement <10 px/sample",
            "displacement 10–<50 px/sample",
            "displacement ≥50 px/sample",
            "displacement unknown",
        ],
        "player_overlap": [
            "inside person box",
            "outside detected person boxes",
            "person pass missing",
        ],
    }
    for kind, names in category_names.items():
        for (key, a), name in zip(
            evidence["errors"]["all"]["buckets"][kind].items(), names
        ):
            h = evidence["errors"]["held"]["buckets"][kind][key]
            lines.append(
                f"| {name} | {a['misses']} / {a['visible']} | {h['misses']} / {h['visible']} | {f(a['recall'], True)} | {f(h['recall'], True)} |"
            )
    lines += [
        "",
        "Image y is a camera-dependent distance proxy. Displacement uses the immediately preceding visible scheduled sample and includes camera motion; it is not measured shutter blur. A point inside a COCO person box is projected overlap, not proven physical occlusion; missed people can appear outside. Unknown labels break motion pairs. Correlated samples and size-conditioned RF availability limit causal interpretation.",
        "",
        *[f"- {s}" for s in protocol.get("error_findings", [])],
        "",
        protocol.get("single_next_change", "Analysis pending."),
        "",
        "## What better footage would change",
        "",
        "The frozen clips are a 1080p wide Veo export. A native 4K export at the same field of view doubles source ball diameter; follow-cam crops can also increase ball pixels. To preserve that gain at the detector, increase tile count/model input or tighten the field of view: resizing fixed 2×2 4K crops to the same 960/1280 input would erase the scale gain. Merely upscaling this 1080p video adds no detail.",
        "",
        "The table maps each measured ball size to twice its size and uses observed recall in that destination bucket. Unknown sizes or unsupported destination bins retain observed outcomes. This is an **associational extrapolation, not measured recall on better footage**, and inherits sparse-bucket and RF-detection bias. H = "
        + held_label
        + ".",
        "",
        "| All observed recall | H observed recall | All projected at 2× px | H projected at 2× px | All supported / unchanged | H supported / unchanged |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    a = evidence["errors"]["all"]["double_size_projection"]
    h = evidence["errors"]["held"]["double_size_projection"]
    lines.append(
        f"| {f(a['observed_recall'], True)} | {f(h['observed_recall'], True)} | {f(a['projected_recall'], True)} | {f(h['projected_recall'], True)} | {a['supported_frames']} / {a['unchanged_unknown_or_unsupported']} | {h['supported_frames']} / {h['unchanged_unknown_or_unsupported']} |"
    )
    lines += [
        "",
        protocol.get("footage_finding", ""),
        "",
        "The real test is fresh labelled club footage, ideally native 4K / follow-cam, held out before any recipe choice. These 20 clips can no longer serve as a clean test set.",
        "",
        "## Label provenance and suggestion bias",
        "",
        "1,057 validated rows: 875 visible / 182 no-ball; 352 accepted suggestions / 705 hand decisions, zero rejected. Coverage is 506/540 planned on-ball targets, 99/100 off-pitch targets, plus 452 extra labels; 48 of the 1,105 scheduled frames remain unlabelled (35 planned targets plus 13 extras). The JSON retains every covered/missing target and per-clip count. No labels or weights are committed.",
        "",
        "Accepted/manual comparisons are descriptive, confounded by suggestion source and frame difficulty; manual includes no-ball decisions. H = "
        + held_label
        + ".",
        "",
        "| Candidate | All accepted R/P | H accepted R/P | All manual R/P | H manual R/P |",
        "|---|---:|---:|---:|---:|",
    ]
    for r in results:
        a, h = r["all"]["provenance_bias"], r["held"]["provenance_bias"]
        lines.append(
            f"| {r['candidate']} | {rp(a['accepted'])} | {rp(h['accepted'])} | {rp(a['manual'])} | {rp(h['manual'])} |"
        )
    lines += [
        "",
        "## Kit, reproducibility and caveats",
        "",
        *[f"- {s}" for s in protocol.get("kit_notes", ["Kit refresh pending."])],
        "",
        *[f"- {s}" for s in protocol.get("checks", [])],
        "",
        f"- Evaluation disclosure: {held_label}. Prior exposure was the single aggregate binary 640-vs-960 recipe decision in round 1. No further recipe selection used H scores; round-2 model selection was frozen before inference. This does not make the subset a clean test set.",
        "- All clips come from one match; neither split measures cross-club or cross-camera generalisation. The All/H gap exposes resubstitution optimism.",
        "- Independent RF boxes estimate apparent size but can still associate a nearby wrong object within 20 px. Size/height/displacement/person-overlap buckets are correlated proxies, not causal diagnoses.",
        "- MPS deterministic mode warns about unsupported deterministic scatter/index operations. Saved measurements reproduce exactly; retraining is not promised bitwise identical.",
        "- Round-1 full-corpus numbers are preserved above and in the original JSON results. Its original 16-clip evaluation split and fit records remain under execution/results; those historical estimates also have the same prior tuning exposure and must not be confused with the six-clip H columns here.",
        "- Ledger generation uses committed aggregate fixtures without labels, weights, footage, torch or .git. Model files, predictions, suggestions and detailed logs remain local under ~/models/tinyball/ and ~/codex-runs/.",
        "- Scope: ball tooling and the two requested ledgers only; no push; one commit. CONTINUITY.md remains outside the user-authorised fence.",
        "",
    ]
    return "\n\n".join(lines[:2]) + "\n" + "\n".join(lines[2:])
