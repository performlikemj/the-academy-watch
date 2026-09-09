#!/usr/bin/env python3
"""Deterministic paired checks comparison; incomplete coverage withholds thresholds."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from .checks_contract import CONTRACT_VERSION, QUESTIONS
    from .checks_score import DENOMINATORS, THRESHOLDS, score_run, threshold_results
    from .checks_truth import RULE_TABLE, TRUTH_VERSION, derive_truth
    from .provenance import load_truth_snapshot
except ImportError:  # pragma: no cover
    from checks_contract import CONTRACT_VERSION, QUESTIONS
    from checks_score import DENOMINATORS, THRESHOLDS, score_run, threshold_results
    from checks_truth import RULE_TABLE, TRUTH_VERSION, derive_truth
    from provenance import load_truth_snapshot

CAVEATS = [
    "n=20, one sequential pass per sampling policy; no repeats or causal claim about density. Smoke and diagnostic are separate from the comparison.",
    "Truth is derived deterministically from MJ's notes via semantic_activity plus the explicit checks rules. This is not independent exhaustive video annotation. n17-416826 running=yes is a directive override without a running keyword; mixed n04-243433 running remains ungraded.",
    "Gate 2 excludes mixed idle/on-ball n04-243433 because its note explicitly records a receive; it is not truth-negative. The two gates measure individual check assertions, not a production gate's combined decision.",
    "Lane A's saved reads used red boxes; this lane uses magenta. Most kits remain red, with one verified black override and two uncertain warm-up kits forced to abstain. These data do not isolate annotation colour effects.",
    "MJ reports tracker misses. Supplied truth box_track stands in for production tracking; identity/input mistakes may affect readings. Labels are supplied identity, not independent jersey evidence.",
    "Every frame imports lane A's spread sampling and magenta drawing. Targets in tracking gaps snap to a recorded timestamp within 0.5s; larger gaps fail. Temporary frame files are removed after each call.",
    "Schema validation establishes the contract, not visual correctness or whether Ollama applies format grammar to thinking. The production transport and its existing thinking fallback are unchanged.",
    "Reason strings are verbatim audit text and never scored. Failed reads remain failed; comparison metrics use only shared scored IDs. Thresholds are withheld for incomplete coverage or no shared scores.",
    "Wall time includes extraction/drawing and failures, with warm-model effects possible. Thinking rate counts all attempts in full-run reports; comparison rates use shared attempts.",
    "No adoption call: MJ owns that decision. This bench does not wire checks into the production honesty gate.",
]


def compare(
    reports_root: Path, runs: dict[str, str], manifest_path: Path, *, allow_mixed=False
) -> dict:
    if len(runs) != 2:
        raise ValueError("provide exactly two runs")
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
        "denominators": "All comparison rates use shared IDs scored in both saved reports and current rescoring. Full-run reports retain every attempt. Frame facts use all raw attempts. Configured wall caps alone do not imply an incomplete run.",
    }
    ordered = sorted(
        frame_facts,
        key=lambda n: frame_facts[n]["mean_boxed_frames_per_clip"] or 0,
        reverse=True,
    )
    headline = (
        "INCOMPLETE COMPARISON — headline withheld"
        if not complete
        else (
            "No shared scored clips — headline withheld"
            if not shared
            else f"On {len(shared)} shared scored clips: "
            + "; ".join(
                f"{lanes[n]['run']} ({frame_facts[n]['model']}, {frame_facts[n]['mean_boxed_frames_per_clip']:g} boxed frames/attempt): off-pitch false-yes {pct(paired[n]['off_pitch_false_yes_rate'])}, off-pitch/idle touch false-yes {pct(paired[n]['off_pitch_idle_touch_false_yes_rate'])}"
                for n in ordered
            )
            + ". Adoption belongs to MJ."
        )
    )
    return {
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
        "caveats": CAVEATS,
    }


def pct(value):
    return "N/A" if value is None else f"{value:.2%}"


def cell(value):
    return str(value).replace("|", "&#124;").replace("\n", "<br>")


def markdown(result: dict) -> str:
    meta = result["comparison_metadata"]
    lines = [
        result["headline"],
        "",
        "Gate numbers (false-yes count / truth-no cells):",
        "",
        "| Run | Off-pitch on-pitch/in-progress | Off-pitch + idle touch |",
        "|---|---:|---:|",
    ]
    for name, lane in result["lanes"].items():
        m = meta["paired_overall"][name]
        lines.append(
            f"| {lane['run']} | "
            + " | ".join(
                f"{g['false_yes_count']}/{g['truth_no_count']} ({pct(g['false_yes_rate'])})"
                for g in m["gates"].values()
            )
            + " |"
        )
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
        "| Run | Scored/failed | Wall s/clip (all attempts) | Macro accuracy | Macro false-yes | Abstain | From thinking (all attempts) |",
        "|---|---:|---:|---:|---:|---:|---:|",
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
            f"| {lane['run']} | {full['scored_clips']}/{full['failed_clips']} | {wall} | {pct(m['macro_accuracy'])} | {pct(m['macro_false_yes_rate'])} | {pct(m['abstain_rate'])} | {pct(full['from_thinking_rate'])} |"
        )
    lines += [
        "",
        "Per-question comparison:",
        "",
        "| Run | Question | Eligible/answered | Accuracy | Abstain | False-yes | False-no | Coverage | High-confidence wrong |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, lane in result["lanes"].items():
        for q, m in meta["paired_overall"][name]["questions"].items():
            lines.append(
                f"| {lane['run']} | {q} | {m['eligible_count']}/{m['answered_count']} | "
                + " | ".join(
                    pct(m[k])
                    for k in (
                        "accuracy",
                        "abstain_rate",
                        "false_yes_rate",
                        "false_no_rate",
                        "coverage",
                    )
                )
                + f" | {m['confident_wrong_count']} |"
            )
    lines += [
        "",
        "Thresholds (MJ decides adoption):",
        "",
        "| Run | Metric | Threshold | Measured | Result |",
        "|---|---|---:|---:|---|",
    ]
    for name, rules in meta["threshold_results"].items():
        for metric, rule in rules.items():
            lines.append(
                f"| {result['lanes'][name]['run']} | {metric} | {rule['operator']} {pct(rule['threshold'])} | {pct(rule['value'])} | {rule['status']} |"
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
        "| Clip | Run | Status | " + " | ".join(QUESTIONS) + " |",
        "|---|---|---|" + "---|" * len(QUESTIONS),
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
            lines.append("| " + " | ".join(cell(v) for v in values) + " |")
    lines += ["", result["reason_selection"]]
    for lane in result["lanes"].values():
        lines += ["", f"Five reasons — {lane['run']}:", ""] + [
            f"- `{r['clip_id']}` / {r['question']}: “{r['reason']}”"
            for r in lane["five_reasons"]
        ]
    lines += ["", "Thinking-channel diagnostic:", ""]
    for row in result.get("thinking_channel_diagnostic", {}).get("calls", []):
        lines.append(
            f"- {row['format_mode']}: JSON field={row['json_field']}; content empty={row['content_empty']}; validates={row['validated']}; selected={row.get('selected_field', 'none')}; done_reason={row.get('done_reason', 'unavailable')}; error={row.get('error') or 'none'}."
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
    ] + [f"- {c}" for c in CAVEATS]
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
    parser.add_argument("--diagnostic", type=Path)
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
        args.reports_root, runs, args.manifest, allow_mixed=args.allow_mixed
    )
    if args.diagnostic:
        result["thinking_channel_diagnostic"] = json.loads(args.diagnostic.read_text())
    args.out_json.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    args.out_md.write_text(markdown(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
