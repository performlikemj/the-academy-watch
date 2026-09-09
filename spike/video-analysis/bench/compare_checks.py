#!/usr/bin/env python3
"""Deterministic multi-run checks comparison; incomplete coverage withholds thresholds."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from .checks_comparison_facts import CROP_CONTEXT_CAVEAT, add_facts, is_crop
    from .checks_contract import CONTRACT_VERSION, QUESTIONS
    from .checks_score import DENOMINATORS, THRESHOLDS, score_run, threshold_results
    from .checks_truth import RULE_TABLE, TRUTH_VERSION, derive_truth
    from .provenance import load_truth_snapshot
except ImportError:  # pragma: no cover
    from checks_comparison_facts import CROP_CONTEXT_CAVEAT, add_facts, is_crop
    from checks_contract import CONTRACT_VERSION, QUESTIONS
    from checks_score import DENOMINATORS, THRESHOLDS, score_run, threshold_results
    from checks_truth import RULE_TABLE, TRUTH_VERSION, derive_truth
    from provenance import load_truth_snapshot

CAVEATS = [
    "n=20, one sequential pass per sampling policy; no repeats or causal claim about density. Smoke and diagnostic are separate from the comparison.",
    "Truth is derived deterministically from MJ's notes via semantic_activity plus the explicit checks rules. This is not independent exhaustive video annotation. Challenges and receives alone do not establish running; mixed running/throw-in does not establish play-in-progress; a missed header establishes ball proximity.",
    "Gate 2 excludes mixed idle/on-ball n04-243433 because its note explicitly records a receive; it is not truth-negative. The two gates measure individual check assertions, not a production gate's combined decision.",
    "Lane A's saved reads used red boxes; this lane uses magenta. Most kits remain red, with one verified black override and two uncertain warm-up kits forced to abstain. These data do not isolate annotation colour effects.",
    "MJ reports tracker misses. Supplied truth box_track stands in for production tracking; identity/input mistakes may affect readings. Labels are supplied identity, not independent jersey evidence.",
    "Every frame imports lane A's spread sampling and magenta drawing. Targets in tracking gaps snap to a recorded timestamp within 0.5s; larger gaps fail. Temporary frame files are removed after each call.",
    "Schema validation establishes the contract, not visual correctness or whether Ollama applies format grammar to thinking. The production transport and its existing thinking fallback are unchanged.",
    "Reason strings are verbatim audit text and never scored. Failed reads remain failed; comparison metrics use only shared scored IDs. Thresholds are withheld for incomplete coverage or no shared scores.",
    "Wall time includes extraction/drawing and failures, with warm-model effects possible. Thinking rate counts all attempts in full-run reports; comparison rates use shared attempts.",
    "No adoption call: MJ owns that decision. This bench does not wire checks into the production honesty gate.",
]

TEMPORAL_CAVEAT = (
    "Every saved touch answer across the nine runs is no/unclear, but 12 frames spread over a long window "
    "leave multi-second gaps while a touch lasts a fraction of a second. The inspected n12 middle crop "
    "is clear and contains no nearby ball. Raw 0/6 is not evidence that the model cannot see a touch: "
    "these frames rarely contain one, and touch recall is not measurable at this sampling. "
    "Wide-frame on-pitch/sideline results retain context; crop on-pitch and ball-near results have a spatial confound. "
    "Follow-up: moment windows — at least 8 frames at at least 4 fps in the 2 s around a human-marked "
    "touch time; MJ must mark touch times on the six clips. No new inference in r2."
)


def metric_diff(before: dict, after: dict) -> dict:
    """Only previously published metrics; new metrics have no historical value."""
    changes = {}
    for key, value in before.items():
        if key not in after or value == after[key]:
            continue
        if isinstance(value, dict) and isinstance(after[key], dict):
            nested = metric_diff(value, after[key])
            if nested:
                changes[key] = nested
        else:
            changes[key] = {"before": value, "after": after[key]}
    return changes


def compare(
    reports_root: Path,
    runs: dict[str, str],
    manifest_path: Path,
    *,
    allow_mixed=False,
    execution: Path | None = None,
    baseline_run: str | None = None,
    example_crops: Path | None = None,
) -> dict:
    if len(runs) < 2:
        raise ValueError("provide at least two runs")
    manifest = json.loads(manifest_path.read_text())
    truths, provenance = load_truth_snapshot(manifest_path)
    selected, reference = None, None
    lanes, raw_runs, coverage, frame_facts, original_scored, mixed = (
        {},
        {},
        {},
        {},
        {},
        {},
    )
    for name, run in runs.items():
        directory = reports_root / run
        settings = json.loads((directory / "run.json").read_text())
        identity = {k: settings.get(k) for k in ("adapter", "model", "frozen_set_id")}
        if not all(isinstance(v, str) and v for v in identity.values()):
            raise ValueError("each run requires adapter, model and frozen-set metadata")
        if settings.get("contract_version") != CONTRACT_VERSION:
            raise ValueError("checks contract version must match")
        reference = reference or identity
        differences = {k: v for k, v in identity.items() if v != reference[k]}
        if identity["adapter"] != "qwen3vl_checks":
            differences["adapter"] = identity["adapter"]
        if identity["frozen_set_id"] != manifest["frozen_set_id"]:
            differences["frozen_set_id"] = identity["frozen_set_id"]
        if differences:
            if not allow_mixed:
                raise ValueError(
                    "adapter/model/frozen-set must match; use --allow-mixed to override"
                )
            mixed[name] = differences
        if selected is not None and settings["clips"] != selected:
            raise ValueError("runs must select the same clips in the same order")
        selected = settings["clips"]
        if (
            not selected
            or len(selected) != len(set(selected))
            or set(selected) - truths.keys()
        ):
            raise ValueError(
                "selected clips must be unique, nonempty and present in supplied truth"
            )
        original_path = directory / "report.json"
        original = (
            json.loads(original_path.read_text()) if original_path.is_file() else {}
        )
        if original and original.get("contract_version") != CONTRACT_VERSION:
            raise ValueError("saved report checks contract version must match")
        raw = []
        for cid in selected:
            path = directory / "claims" / f"{cid}.json"
            if path.is_file():
                row = json.loads(path.read_text())
                if row.get("clip_id") != cid:
                    raise ValueError("raw result clip ID differs from its filename")
                if row.get("contract_version") != CONTRACT_VERSION:
                    raise ValueError("raw checks contract version must match")
                raw.append(row)
        raw_runs[name] = raw
        raw_ids = {r["clip_id"] for r in raw}
        covered = {
            c["clip_id"]
            for c in original.get("clips", [])
            if c["status"] != "not_attempted"
        }
        original_scored[name] = {
            c["clip_id"] for c in original.get("clips", []) if c["status"] == "scored"
        }
        coverage[name] = {
            "missing_clip_ids": [
                cid for cid in selected if cid not in raw_ids or cid not in covered
            ],
            "missing_claim_clip_ids": [cid for cid in selected if cid not in raw_ids],
            "missing_report_clip_ids": [cid for cid in selected if cid not in covered],
            "stop_markers": {
                f"{source}.{key}": payload[key]
                for source, payload in (("run", settings), ("report", original))
                for key in ("stopped_early", "wall_cap_exceeded")
                if key in payload
                and payload[key] is not None
                and payload[key] is not False
            },
        }
        report = score_run(raw, truths, truth_provenance=provenance)
        frames = [f for r in raw for f in r.get("sent_frames", [])]
        shifts = [abs(f.get("sampling_shift_s", 0)) for f in frames]
        frame_facts[name] = {
            **identity,
            "attempted_clips": len(raw),
            "sample_interval": settings.get("sample_interval"),
            "sample_limit": settings.get("sample_limit"),
            "anchor_color": settings.get("anchor_color"),
            "mean_boxed_frames_per_clip": sum(
                len(r.get("anchored_frames", [])) for r in raw
            )
            / len(raw)
            if raw
            else None,
            "single_frame_attempts": sum(
                len(r.get("sent_frames", [])) == 1 for r in raw
            ),
            "sent_frame_count": len(frames),
            "shifted_frame_count": sum(s > 0 for s in shifts),
            "max_sampling_shift_s": max(shifts, default=0),
            "frames_per_second_of_window": report["overall"][
                "frames_per_second_of_window"
            ],
            "mean_spacing_s": report["overall"]["sampling"]["mean_spacing_s"],
        }
        # First available question reason per scored clip; then take first five clips.
        reasons = []
        for clip in report["clips"]:
            if clip["status"] != "scored":
                continue
            for q in QUESTIONS:
                reason = clip["checks"][q].get("reason")
                if reason is not None:
                    reasons.append(
                        {"clip_id": clip["clip_id"], "question": q, "reason": reason}
                    )
                    break
        lanes[name] = {
            "run": run,
            "settings": settings,
            "report": report,
            "five_reasons": reasons[:5],
            "sampling": [
                {
                    k: r.get(k)
                    for k in (
                        "clip_id",
                        "sent_frames",
                        "anchored_frames",
                        "done_reason",
                        "from_thinking",
                    )
                }
                for r in raw
            ],
        }
    shared = set.intersection(
        *(
            {c["clip_id"] for c in lane["report"]["clips"] if c["status"] == "scored"}
            & original_scored[name]
            for name, lane in lanes.items()
        )
    )
    shared_ids = [cid for cid in selected if cid in shared]
    paired = {
        name: score_run([r for r in raw_runs[name] if r["clip_id"] in shared], truths)[
            "overall"
        ]
        for name in lanes
    }
    # Temporal observability and the fixed positive denominator belong to each
    # full attempted run, even when paired accuracy excludes a failed read.
    for name, metrics in paired.items():
        full = lanes[name]["report"]["overall"]
        for key in (
            "sampling",
            "frames_per_second_of_window",
            "touch_recall",
            "touch_recall_raw",
            "touch_recall_reason",
            "touch_yes_count",
            "touch_truth_positive_count",
        ):
            metrics[key] = full[key]
        for q, question in metrics["questions"].items():
            for key in (
                "modal_answer",
                "modal_answer_share",
                "answer_count",
                "answer_distribution",
                "majority_baseline_accuracy",
                "majority_truth_count",
                "graded_truth_count",
            ):
                question[key] = full["questions"][q][key]
            accuracy, baseline = (
                question["accuracy"],
                question["majority_baseline_accuracy"],
            )
            question["accuracy_minus_baseline"] = (
                accuracy - baseline
                if accuracy is not None and baseline is not None
                else None
            )
            question["information"] = bool(
                question["modal_answer_share"] is not None
                and question["modal_answer_share"] < 0.9
                and accuracy is not None
                and baseline is not None
                and accuracy > baseline + 0.05
            )
        for key in (
            "recall",
            "raw_recall",
            "recall_reason",
            "true_positive_count",
            "recall_truth_positive_count",
        ):
            metrics["questions"]["player_touches_ball"][key] = full["questions"][
                "player_touches_ball"
            ][key]
    complete = all(
        not c["missing_clip_ids"] and not c["stop_markers"] for c in coverage.values()
    )
    metadata = {
        "complete": complete,
        "coverage": coverage,
        "shared_scored_clip_ids": shared_ids,
        "shared_scored_clips": len(shared_ids),
        "allow_mixed": allow_mixed,
        "mixed_settings": mixed,
        "frame_facts": frame_facts,
        "paired_overall": paired,
        "threshold_results": {
            name: threshold_results(m, complete=complete and bool(shared))
            for name, m in paired.items()
        },
        "denominators": "Comparison accuracy/error rates use shared IDs scored in every saved report and current rescoring. Modal distributions, majority baselines, touch counts/recall and temporal sampling use each full run, so abstention or another run's failure cannot remove valid answers or touch positives from those denominators. Full-run reports retain every attempt. Frame facts use all raw attempts. Configured wall caps alone do not imply an incomplete run.",
    }
    ordered = sorted(
        (name for name in frame_facts if not is_crop(lanes[name])),
        key=lambda n: frame_facts[n]["mean_boxed_frames_per_clip"] or 0,
        reverse=True,
    )
    metadata["gate1_excluded_runs"] = {
        name: CROP_CONTEXT_CAVEAT for name, lane in lanes.items() if is_crop(lane)
    }
    for name in metadata["gate1_excluded_runs"]:
        metadata["threshold_results"][name]["off_pitch_false_yes_rate"].update(
            status="WITHHELD", reason=CROP_CONTEXT_CAVEAT
        )
    headline = (
        "INCOMPLETE COMPARISON — headline withheld"
        if not complete
        else (
            "No shared scored clips — headline withheld"
            if not shared
            else f"On {len(shared)} shared scored clips (wide runs only; crops excluded from gate-1 headline): "
            + "; ".join(
                f"{lanes[n]['run']} ({frame_facts[n]['model']}, {frame_facts[n]['mean_boxed_frames_per_clip']:g} boxed frames/attempt): off-pitch false-yes {pct(paired[n]['off_pitch_false_yes_rate'])}, touch false-yes {pct(paired[n]['off_pitch_idle_touch_false_yes_rate'])}, touch recall {pct(paired[n]['touch_recall'])} (raw {paired[n]['touch_yes_count']}/{paired[n]['touch_truth_positive_count']}), gate 2 {metadata['threshold_results'][n]['gate2']['status']}"
                for n in ordered
            )
            + ". Adoption belongs to MJ."
        )
    )
    result = {
        "experiment": "E1d lane B — yes/no checks under the honesty gate",
        "state": "measured" if complete else "incomplete",
        "contract_version": CONTRACT_VERSION,
        "truth_version": TRUTH_VERSION,
        "frozen_set_id": manifest["frozen_set_id"],
        **provenance,
        "headline": headline,
        "denominators": DENOMINATORS,
        "rules": RULE_TABLE,
        "thresholds": THRESHOLDS,
        "comparison_metadata": metadata,
        "lanes": lanes,
        "reason_selection": "First available question reason per scored clip, in contract question order; first five such clips in selected manifest order, verbatim. Missing optional reasons are never invented.",
        "truth_table": [
            {
                "clip_id": cid,
                "human_note": truths[cid].get("human_note"),
                **derive_truth(truths[cid]),
            }
            for cid in selected
        ],
        "per_clip_comparison": [
            {
                "clip_id": cid,
                "reads": {
                    name: next(
                        (c for c in lane["report"]["clips"] if c["clip_id"] == cid),
                        {"status": "not_attempted"},
                    )
                    for name, lane in lanes.items()
                },
            }
            for cid in selected
        ],
        "caveats": CAVEATS
        + [
            TEMPORAL_CAVEAT,
            "Confidence is uncalibrated and prompt-sensitive: on both pilot clips, touch no/low changed to no/high after the reason instruction changed. Modal share and baseline comparisons expose near-constant priors; low touch false-yes alone is not sensitivity.",
        ],
    }
    result["touch_recall"] = {
        name: {
            k: m[k]
            for k in (
                "touch_recall",
                "touch_recall_raw",
                "touch_recall_reason",
                "touch_yes_count",
                "touch_truth_positive_count",
            )
        }
        for name, m in paired.items()
    }
    result["touch_clips"] = [
        row
        for row in result["per_clip_comparison"]
        if derive_truth(truths[row["clip_id"]])["expected"]["player_touches_ball"]
        == "yes"
    ]
    if execution:
        payload = json.loads(execution.read_text())
        result["execution"] = payload
        for key in (
            "experiment",
            "base_commit",
            "thinking_channel_diagnostic",
            "thinking_channel_diagnostics",
            "historical_32b_preflight",
            "model_27b",
            "smoke_27b",
            "known_truth_error",
        ):
            if key in payload.get("artifacts", {}):
                result[key] = payload["artifacts"][key]
        result["caveats"] += payload.get("extra_caveats", [])
        if complete and shared and payload.get("review_headline"):
            result["review_headline"] = payload["review_headline"]
        previous = payload.get("previous_truth", {})
        result["truth_cells_changed"] = [
            {
                "clip_id": row["clip_id"],
                "question": q,
                "before": previous[row["clip_id"]][q],
                "after": row["expected"][q],
            }
            for row in result["truth_table"]
            if row["clip_id"] in previous
            for q in QUESTIONS
            if previous[row["clip_id"]][q] != row["expected"][q]
        ]
        result["metric_changes"] = {
            name: metric_diff(old, paired[name])
            for name, old in payload.get("previous_metrics", {}).items()
            if name in paired
        }
        gate_keys = ("off_pitch_false_yes_rate", "off_pitch_idle_touch_false_yes_rate")
        unchanged = all(
            old.get(key) == paired[name][key]
            for name, old in payload.get("previous_metrics", {}).items()
            if name in paired
            for key in gate_keys
        )
        result["r2_summary"] = (
            f"{len(result['truth_cells_changed'])} truth cells corrected. Pooled false-yes gate numbers {'unchanged' if unchanged else 'changed; see deltas'}. "
            "The headline changes: gate 2 now requires measurable recall as well as low false-yes, so its former false-yes-only PASS is WITHHELD at this sampling. "
            "Macro accuracies and per-question metrics changed as listed; raw touch counts remain visible. "
            "The requested information heuristic can flag selective-abstention outputs despite zero affirmative touches; it is not a calibrated measure of visual information."
        )
    add_facts(result, baseline_run=baseline_run, example_crops=example_crops)
    return result


def pct(value):
    return "N/A" if value is None else f"{value:.2%}"


def cell(value):
    return str(value).replace("|", "&#124;").replace("\n", "<br>")


def markdown(result: dict) -> str:
    meta = result["comparison_metadata"]
    lines = []
    if result.get("review_headline"):
        lines += [
            result["review_headline"],
            "",
            "Review-requested synthesis, reproduced verbatim. The categorical wording is not a measured perfect-detector bound or a claim that every individual read was identical. Actual counts and confounds follow: temporal spacing does not prove that zero touches were visible, and crop views also remove sideline/ball context.",
            "",
        ]
    lines += [
        result["headline"],
        "",
        "Gate numbers (false-yes count / truth-no cells):",
        "",
        "| Run | Off-pitch on-pitch | Off-pitch in-progress | Gate 1 pooled | Touch false-yes | Raw touch yes/positive | Touch recall | Gate 2 | Confounds |",
        "|---|---:|---:|---:|---:|---:|---|---|---|",
    ]
    for name, lane in result["lanes"].items():
        m = meta["paired_overall"][name]
        lines.append(
            f"| {lane['run']} | "
            + " | ".join(
                f"{g['false_yes_count']}/{g['truth_no_count']} ({pct(g['false_yes_rate'])})"
                for g in m["gates"].values()
            )
            + f" | {m['touch_yes_count']}/{m['touch_truth_positive_count']} | {pct(m['touch_recall'])} | {meta['threshold_results'][name]['gate2']['status']} | {cell(result['touch_recall'][name]['confound'])} {CROP_CONTEXT_CAVEAT if is_crop(lane) else ''} |"
        )
    lines += [
        "",
        "Per-question comparison:",
        "",
        "| Run | Question | Eligible/answered | Accuracy | Majority baseline | Accuracy minus baseline | Modal answer | Modal share | Information | Abstain | False-yes | Recall | False-no | Coverage | High-confidence wrong | Confound |",
        "|---|---|---:|---:|---:|---:|---|---:|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for name, lane in result["lanes"].items():
        for q, m in meta["paired_overall"][name]["questions"].items():
            lines.append(
                f"| {lane['run']} | {q} | {m['eligible_count']}/{m['answered_count']} | {pct(m['accuracy'])} | {pct(m['majority_baseline_accuracy'])} | {pct(m['accuracy_minus_baseline'])} | {m['modal_answer']} | {pct(m['modal_answer_share'])} | {m['information']} | {pct(m['abstain_rate'])} | {pct(m['false_yes_rate'])} | {pct(m['recall'])} | {pct(m['false_no_rate'])} | {pct(m['coverage'])} | {m['confident_wrong_count']} | {cell(result['question_caveats'][name].get(q, '—'))} |"
            )
    if result.get("per_question_deltas_pp"):
        lines += [
            "",
            f"Per-question deltas in percentage points versus {result['baseline_run']} (same metric denominators as above):",
            "",
            "| Run | Question | Accuracy Δ | Abstain Δ | False-yes Δ | Recall Δ | Confound |",
            "|---|---|---:|---:|---:|---:|---|",
        ]
        for name, questions in result["per_question_deltas_pp"].items():
            for q, metrics in questions.items():
                values = ["N/A" if v is None else f"{v:+.2f}" for v in metrics.values()]
                lines.append(
                    f"| {result['lanes'][name]['run']} | {q} | "
                    + " | ".join(values)
                    + f" | {cell(result['question_caveats'][name].get(q, '—'))} |"
                )
    lines += [
        "",
        "Touch recall (raw counts retained; null recall is not a detector score):",
        "",
        "| Run | Raw affirmative touches | Recall | Sampling confound |",
        "|---|---:|---|---|",
    ]
    for name, facts in result["touch_recall"].items():
        lines.append(
            f"| {result['lanes'][name]['run']} | {facts['touch_yes_count']}/{facts['touch_truth_positive_count']} | {pct(facts['touch_recall'])} | {cell(facts['confound'])} |"
        )
    lines += [
        "",
        "Six truth-positive touch clips — answers/confidence and measured mean still spacing (single frame has no inter-still interval):",
        "",
        "| Clip | " + " | ".join(result["lanes"]) + " | Confound |",
        "|---|" + "---|" * (len(result["lanes"]) + 1),
    ]
    for row in result["true_touch_clips"]:
        values = []
        for name in result["lanes"]:
            answer = row["reads"][name].get("checks", {}).get("player_touches_ball", {})
            spacing = row["sampling"][name]["mean_still_spacing_s"]
            interval = "single/missing frame" if spacing is None else f"{spacing:.2f} s"
            values.append(
                f"{answer.get('answer', 'failed')}/{answer.get('confidence', '—')}; {interval}"
            )
        lines.append(
            f"| {row['clip_id']} | "
            + " | ".join(values)
            + f" | {cell(row['confound'])} |"
        )
    lines += ["", TEMPORAL_CAVEAT, ""]
    if result.get("r2_summary"):
        lines += [result["r2_summary"], ""]
    lines += [
        "",
        f"Shared scored clips: {meta['shared_scored_clips']}. {meta['denominators']}",
        "",
        DENOMINATORS,
        "",
    ]
    if not meta["complete"]:
        lines += [
            f"- {n}: missing {c['missing_clip_ids']}; stop markers {json.dumps(c['stop_markers'], sort_keys=True)}"
            for n, c in meta["coverage"].items()
        ]
    if meta["mixed_settings"]:
        lines += [
            f"Mixed settings explicitly allowed: {json.dumps(meta['mixed_settings'], sort_keys=True)}; scoring uses supplied truth.",
            "",
        ]
    lines += [
        "| Run | Model | Boxed frames/attempt | Scored/failed | Wall s/clip (all attempts) | Macro accuracy | Macro false-yes | Abstain | From thinking (all attempts) |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, lane in result["lanes"].items():
        full = lane["report"]["overall"]
        m = meta["paired_overall"][name]
        wall = (
            "N/A"
            if full["wall_s_per_clip"] is None
            else f"{full['wall_s_per_clip']:.3f}"
        )
        lines.append(
            f"| {lane['run']} | {lane['settings']['model']} | {meta['frame_facts'][name]['mean_boxed_frames_per_clip']} | {full['scored_clips']}/{full['failed_clips']} | {wall} | {pct(m['macro_accuracy'])} | {pct(m['macro_false_yes_rate'])} | {pct(m['abstain_rate'])} | {pct(full['from_thinking_rate'])} |"
        )
    lines += [
        "",
        "Thresholds (MJ decides adoption):",
        "",
        "| Run | Metric | Threshold | Measured | Result | Confound |",
        "|---|---|---:|---:|---|---|",
    ]
    for name, rules in meta["threshold_results"].items():
        for metric, rule in rules.items():
            lines.append(
                f"| {result['lanes'][name]['run']} | {metric} | {rule.get('requires', rule['operator'] + ' ' + pct(rule['threshold']))} | {pct(rule['value'])} | {rule['status']} | {cell(rule.get('reason') or (result['touch_recall'][name]['confound'] if metric in ('touch_recall', 'gate2', 'off_pitch_idle_touch_false_yes_rate') else '—'))} |"
            )
    lines += ["", "Truth rules:", ""] + [f"- {q}: {r}" for q, r in RULE_TABLE.items()]
    lines += [
        "",
        "Full truth table — ungraded cells shown as —; uncertain kit cells force abstention:",
        "",
        "| Clip | MJ note | " + " | ".join(QUESTIONS) + " |",
        "|---|---|" + "---|" * len(QUESTIONS),
    ]
    for row in result["truth_table"]:
        values = [row["clip_id"], row["human_note"]] + [
            row["expected"][q]
            or (
                "uncertain / abstain"
                if q == "kit_color_seen" and row["kit_uncertain"]
                else "—"
            )
            for q in QUESTIONS
        ]
        lines.append("| " + " | ".join(cell(v) for v in values) + " |")
    lines += [
        "",
        "All per-clip answers (answer / confidence):",
        "",
        "| Clip | Run | Status | "
        + " | ".join(
            q + " (temporal confound)"
            if q in ("player_touches_ball", "player_running")
            else q
            for q in QUESTIONS
        )
        + " | Confounds |",
        "|---|---|---|" + "---|" * (len(QUESTIONS) + 1),
    ]
    for row in result["per_clip_comparison"]:
        for name, read in row["reads"].items():
            answers = read.get("checks", {})
            values = [row["clip_id"], result["lanes"][name]["run"], read["status"]] + [
                f"{answers[q]['answer']} / {answers[q]['confidence']}"
                if q in answers
                else read.get("error", "—")
                for q in QUESTIONS
            ]
            values.append(
                result["touch_recall"][name]["confound"]
                + (" " + CROP_CONTEXT_CAVEAT if is_crop(result["lanes"][name]) else "")
            )
            lines.append("| " + " | ".join(cell(v) for v in values) + " |")
    lines += ["", result["reason_selection"]]
    for lane in result["lanes"].values():
        lines += ["", f"Five reasons — {lane['run']}:", ""] + [
            f"- `{r['clip_id']}` / {r['question']}: “{r['reason']}”"
            for r in lane["five_reasons"]
        ]
    lines += ["", "Thinking-channel diagnostic:", ""]
    diagnostics = result.get("thinking_channel_diagnostics") or {
        "saved": result.get("thinking_channel_diagnostic", {})
    }
    for model, diagnostic in diagnostics.items():
        for row in diagnostic.get("calls", []):
            lines.append(
                f"- {model} / {row['format_mode']}: JSON field={row['json_field']}; content empty={row['content_empty']}; validates={row['validated']}; selected={row.get('selected_field', 'none')}; done_reason={row.get('done_reason', 'unavailable')}; error={row.get('error') or 'none'}."
            )
    lines += ["", "Model/frame facts from run.json and raw attempts:", ""] + [
        f"- {name}: {json.dumps(facts, sort_keys=True)}"
        for name, facts in meta["frame_facts"].items()
    ]
    lines += [
        "",
        "Provenance:",
        "",
        f"- Truth SHA-256: `{result['truth_set_sha256_after_notes']}`",
        f"- Human-note SHA-256: `{result['human_notes_sha256']}`",
        f"- Contract: {CONTRACT_VERSION}; truth rules: {TRUTH_VERSION}.",
        "",
        "Caveats:",
        "",
    ] + [f"- {c}" for c in result.get("caveats", CAVEATS)]
    lines += [
        "",
        "Temporal sampling (distinct timestamps; context pairs counted once):",
        "",
        "| Run | FPS mean | FPS min | Mean spacing s | Touch recall reason |",
        "|---|---:|---:|---:|---|",
    ]
    for name, lane in result["lanes"].items():
        sampling = lane["report"]["overall"]["sampling"]
        fps = sampling["frames_per_second_of_window"]
        lines.append(
            f"| {lane['run']} | {fps['mean']} | {fps['min']} | {sampling['mean_spacing_s']} | {sampling['touch_recall_reason'] or 'sampling screen passed; touch visibility not verified'} |"
        )
    if result.get("truth_cells_changed"):
        lines += [
            "",
            "Truth cells changed in r2:",
            "",
            "| Clip | Question | Before | After |",
            "|---|---|---|---|",
        ]
        for row in result["truth_cells_changed"]:
            lines.append(
                f"| {row['clip_id']} | {row['question']} | {row['before']} | {row['after']} |"
            )
    if result.get("metric_changes"):
        lines += [
            "",
            "Metric changes from the preceding ledger (including per-question counts):",
            "",
            "```json",
            json.dumps(result["metric_changes"], indent=2),
            "```",
        ]
    if result.get("crop_geometry"):
        lines += [
            "",
            "Crop geometry (decoded lane-B frames, resized to 768 square):",
            "",
        ]
        for name, geometry in result["crop_geometry"].items():
            lines.append(
                f"- {name}: side {geometry['crop_side_px_min']}–{geometry['crop_side_px_max']} px; scale {geometry['crop_scale_min']:.3f}–{geometry['crop_scale_max']:.3f}; {geometry['sampled_instants']} instants / {geometry['sent_images']} images."
            )
        lines += [
            "",
            f"32B crop run: {'WITHHELD' if result['decision_32b']['run'] is None else 'YES' if result['decision_32b']['run'] else 'NO'} — evaluated from the saved 8B crop answers. {result['decision_32b']['confound']}",
            "",
            "Three inspected example crop PNGs (external, not committed):",
            "",
        ]
        lines += [
            f"- {r['path']} — SHA-256 {r['sha256']}"
            for r in result.get("example_crops", [])
        ]
    if result.get("execution"):
        lines += [
            "",
            "Execution/gates:",
            "",
            "```json",
            json.dumps(result["execution"], indent=2),
            "```",
        ]
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--runs",
        nargs="+",
        default=["dense=e1d-checks-dense", "prod30=e1d-checks-prod30"],
    )
    parser.add_argument("--allow-mixed", action="store_true")
    parser.add_argument(
        "--diagnostic",
        action="append",
        default=[],
        metavar="NAME=PATH",
        help="repeatable; a bare path retains legacy single-diagnostic behavior",
    )
    parser.add_argument(
        "--baseline-run", help="selected run alias used for per-question deltas"
    )
    parser.add_argument(
        "--touch-clips",
        action="store_true",
        help="explicitly request truth-derived touch tables (also included by default)",
    )
    parser.add_argument(
        "--example-crops",
        type=Path,
        help="directory containing examples.json and its PNGs",
    )
    parser.add_argument("--extra-caveat", action="append", default=[])
    parser.add_argument(
        "--execution",
        type=Path,
        help="committed execution/provenance JSON for deterministic regeneration",
    )
    parser.add_argument("--out-json", type=Path, required=True)
    parser.add_argument("--out-md", type=Path, required=True)
    args = parser.parse_args(argv)
    runs = {}
    for item in args.runs:
        name, sep, directory = item.partition("=")
        if not sep or not name or not directory or name in runs:
            parser.error("runs must be unique NAME=DIR pairs")
        runs[name] = directory
    result = compare(
        args.reports_root,
        runs,
        args.manifest,
        allow_mixed=args.allow_mixed,
        execution=args.execution,
        baseline_run=args.baseline_run,
        example_crops=args.example_crops,
    )
    diagnostic_names = set()
    for diagnostic in args.diagnostic:
        name, separator, path = diagnostic.partition("=")
        if separator:
            if not name or not path or name in diagnostic_names:
                parser.error("diagnostics must be unique NAME=PATH pairs")
            diagnostic_names.add(name)
            result.setdefault("thinking_channel_diagnostics", {})[name] = json.loads(
                Path(path).read_text()
            )
        else:
            result["thinking_channel_diagnostic"] = json.loads(
                Path(diagnostic).read_text()
            )
    result["caveats"] += args.extra_caveat
    args.out_json.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    args.out_md.write_text(markdown(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
