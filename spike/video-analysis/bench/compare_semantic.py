#!/usr/bin/env python3
"""Re-score annotated runs against current local notes and emit a deterministic ledger."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from .provenance import load_truth_snapshot
    from .semantic_score import RATE_KEYS, score_run
except ImportError:  # pragma: no cover
    from provenance import load_truth_snapshot
    from semantic_score import RATE_KEYS, score_run

CAVEATS = [
    "Truth box_track stands in for the production tracker's persisted geometry on every sampled frame. Tracker accuracy and unlabelled-player grounding are not evaluated.",
    "No boxes are requested from the VLM, so rectangle echo is not a model-geometry failure mode in this lane. The supplied jersey label is not proof of number legibility.",
    "Dense samples are spread across the window, capped at 12; 30s/3 is a sparse annotated control. These isolate sampling under the same semantic contract, not a comparison to the old grounding score.",
    "Presence-only and jersey checks are narrow regex rules, not semantic judgments; kit-colour checks compare the explicit field only. Goal and name prohibitions are prompt rules, not verified truth guarantees.",
    "fabricated_rate evaluates the 19 notes with classifiable activity; n24's identity-only note is excluded from its denominator while per-clip keyword mismatches remain visible for audit. Simple no/without clauses suppress negated event keywords. Activity-subset rates are the primary findings; absence of a keyword is not proof an event never occurred.",
    "Sequential single passes, without repeats or confidence intervals. Wall time includes extraction/drawing and all failed attempts; Ollama may reuse a warm model. Temporary frame paths record provenance but images are removed after each call.",
    "Uniform target samples falling in tracking gaps snap to the nearest recorded track timestamp within 0.5s, remaining distinct and chronological; target_t and sampling_shift_s record every adjustment. Larger gaps fail before inference. Geometry is never extrapolated across gaps.",
    "All 20 frozen kit fields say red and both measured runs used red rectangles. MJ confirms n24 is actually black; its verified black override is now used. The evaluated set has just one verified non-red kit and remains dominated by red, with two uncertain warm-up kits counted as abstentions. Future lane-A model inputs use magenta; these saved outputs were not rerun.",
    "Every lane-A response (40/40) was read from Ollama's thinking field despite think=false. Schema-valid parsing is established; the format grammar's effect on that field is unverified. The transport is unchanged.",
    "Sentence-only presence applies the specified verb-stem exclusion literally: moving, interacting and holding are not excluded. The added strict rate excludes hold/holding, with (the) ball, possession, moving and interacting. Consistency adds carrying/passing/dribbling/running-with-ball inflections and excludes unmapped event classes from its requirement; ignored classes remain visible in JSON. Presence-with-substantive-event uses the original sentence-only flag. These are lexical diagnostics, not semantic accuracy.",
    "Truth and note hashes describe the current rescoring snapshot across all manifest truth files. Historical run.json files retain their original launch metadata; absent inference-time hashes are not retroactively asserted.",
    "No adoption recommendation; MJ owns that decision.",
    "Headline denominator correction: there are 13 clips with classified activity but no on-ball action, not 14. Mixed n04-243433 explicitly includes a receive and half-turn and is excluded from that group; its idle subset flag remains. Headline counts are 12/13 dense and 10/13 prod30. The requested 12-frames/single-still wording is shorthand: actual means are 11.9 versus 1.45 frames, and only 13/20 prod30 attempts send exactly one frame. Single passes do not establish a general causal effect of sampling density.",
    "MJ reports 'some misses as far as boxes are concerned': truth box_track has visible tracker misses. These are geometry/input errors, not model errors, and may affect semantic reads.",
    "m04-n24-t3013-679939-681217 has a disputed truth label: MJ wrote 'wrong number. this is number 12 from the shorts'. The frozen #24 binding is not corrected by inference; this clip remains visible and excluded from jersey denominators, while kit metrics use kit_color_truth_override black. MJ's appended clarification confirms BLACK warm-up kit and black shorts: the earlier fps2 video lane and annotated prod30 read black correctly, while frozen kit_color red is wrong. The original label/colour fields are retained for audit. m04-n22-t3012-070707-074371 and m04-n03-t1406-385962-387137 have kit_color_uncertain true: their kit metrics abstain, neither matching nor wrong.",
    "Activity agreement is coarse compatibility: all on-ball notes can agree with any on-ball model activity even when event recall fails. A mixed idle/on-ball note is eligible for both subset rates; the idle rate is not itself proof of fabrication on that mixed clip. Strict recall gives no carry credit for header/receive/turn/loss. Lenient recall additionally permits receive/turn/loss as carry-compatible, never header/duel/interception. Carry appears on 36/40 saved reads (19 dense, 17 prod30), so strict recall is more discriminating. Outcomes and event timing are not graded against the notes.",
    "Sentence verdicts are lexical class overlap, not full entailment: agree requires a shared activity/action class and no detected incompatible assertion; disagree requires an incompatible class/context; otherwise undetermined. Holding (the) ball is an on-ball assertion without an action-class match: an unsupported holding detail makes an otherwise agreeing sentence undetermined. These checks do not robustly resolve negation, actor attribution or temporal order.",
]


def comparison_read(clip: dict | None) -> dict | None:
    if clip is None:
        return None
    if clip["status"] != "scored":
        return {"status": clip["status"], "error": clip.get("error")}
    return {
        "semantic": {
            "sentence": clip["semantic"]["sentence"],
            "events": [
                {key: event[key] for key in ("event_type", "outcome")}
                for event in clip["semantic"]["events"]
            ],
        },
        "metrics": {
            key: clip["metrics"][key]
            for key in (
                "truth_activity",
                "activity_agreement",
                "on_ball_recalled",
                "on_ball_recalled_lenient",
                "sentence_matches_note",
            )
        },
    }


def compare(
    reports_root: Path,
    runs: dict[str, str],
    manifest_path: Path,
    *,
    allow_mixed: bool = False,
) -> dict:
    if len(runs) != 2:
        raise ValueError("provide the dense and prod30 runs")
    manifest = json.loads(manifest_path.read_text())
    truths, truth_provenance = load_truth_snapshot(manifest_path)
    selected = None
    lanes, raw_runs, coverage, frame_facts, original_scored = {}, {}, {}, {}, {}
    reference = None
    mixed_settings = {}
    for name, run in runs.items():
        directory = reports_root / run
        settings = json.loads((directory / "run.json").read_text())
        identity = {key: settings[key] for key in ("adapter", "model", "frozen_set_id")}
        if not all(isinstance(value, str) and value for value in identity.values()):
            raise ValueError("each run requires adapter, model and frozen-set metadata")
        reference = reference or identity
        differences = {
            key: value for key, value in identity.items() if value != reference[key]
        }
        if settings["adapter"] != "qwen3vl_annotated":
            differences["adapter"] = settings["adapter"]
        if settings["frozen_set_id"] != manifest["frozen_set_id"]:
            differences["frozen_set_id"] = settings["frozen_set_id"]
        if differences:
            if not allow_mixed:
                raise ValueError(
                    "adapter/model/frozen-set must match both runs and supplied truth; use --allow-mixed to override"
                )
            mixed_settings[name] = differences
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
        raw = []
        for cid in selected:
            path = directory / "claims" / f"{cid}.json"
            if path.is_file():
                row = json.loads(path.read_text())
                if row.get("clip_id") != cid:
                    raise ValueError("raw result clip ID differs from its filename")
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
        report = score_run(raw, truths, truth_provenance=truth_provenance)
        report["generated_at"] = original.get("generated_at")
        scored = [c for c in report["clips"] if c["status"] == "scored"]
        frames = [frame for row in raw for frame in row["sent_frames"]]
        shifts = [abs(frame.get("sampling_shift_s", 0)) for frame in frames]
        frame_facts[name] = {
            **identity,
            "attempted_clips": len(raw),
            "mean_boxed_frames_per_clip": round(
                sum(len(row.get("anchored_frames", [])) for row in raw) / len(raw), 3
            )
            if raw
            else None,
            "single_frame_attempts": sum(len(row["sent_frames"]) == 1 for row in raw),
        }
        lanes[name] = {
            "sent_frame_count": len(frames),
            "sent_frames_per_attempt": round(len(frames) / len(raw), 3)
            if raw
            else None,
            "shifted_frame_count": sum(shift > 0 for shift in shifts),
            "max_sampling_shift_s": max(shifts, default=0),
            "run": run,
            "settings": settings,
            "report": report,
            "unrun_clips": coverage[name]["missing_clip_ids"],
            "five_sentences": [
                {"clip_id": c["clip_id"], "sentence": c["semantic"]["sentence"]}
                for c in scored[:5]
            ],
            "sampling": [
                {
                    "clip_id": r["clip_id"],
                    "sent_frames": r["sent_frames"],
                    "anchored_frames": r["anchored_frames"],
                    "done_reason": r.get("done_reason"),
                    "from_thinking": r.get("from_thinking"),
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
    metadata = {
        "complete": all(
            not c["missing_clip_ids"] and not c["stop_markers"]
            for c in coverage.values()
        ),
        "coverage": coverage,
        "shared_scored_clip_ids": shared_ids,
        "shared_scored_clips": len(shared_ids),
        "allow_mixed": allow_mixed,
        "mixed_settings": mixed_settings,
        "frame_facts": frame_facts,
        "paired_overall": paired,
        "paired_counts": {
            name: {
                key: sum(
                    c.get("metrics", {}).get(key) is True
                    for c in lane["report"]["clips"]
                    if c["clip_id"] in shared
                )
                for key in (
                    "no_on_ball_claimed_on_ball",
                    "off_pitch_claimed_on_ball",
                    "on_ball_recalled",
                    "on_ball_recalled_lenient",
                )
            }
            for name, lane in lanes.items()
        },
        "denominators": "The scored/failed columns and per-run reports retain all attempts. All other comparison-table metrics and activity headline counts use only shared scored clip IDs, scored in both saved reports and current rescoring. Frame facts use all recorded raw attempts, including failures.",
    }
    return {
        "experiment": "E1c lane A — annotated dense frames, semantic-only contract",
        "state": "measured" if metadata["complete"] else "incomplete",
        "honest_limit": next(iter(lanes.values()))["report"]["honest_limit"],
        "frozen_set_id": manifest["frozen_set_id"],
        **truth_provenance,
        "sentence_selection": "First five scored clips in manifest order, verbatim; no quality selection.",
        "lanes": lanes,
        "headline": activity_headline(metadata),
        "comparison_metadata": metadata,
        "per_clip_comparison": [
            {
                "clip_id": cid,
                "human_note": truths[cid].get("human_note"),
                "truth_label_disputed": bool(truths[cid].get("truth_label_disputed")),
                "reads": {
                    name: comparison_read(
                        next(
                            (c for c in lane["report"]["clips"] if c["clip_id"] == cid),
                            None,
                        )
                    )
                    for name, lane in lanes.items()
                },
            }
            for cid in (selected or [])
        ],
        "caveats": CAVEATS,
    }


def activity_headline(metadata: dict) -> str:
    if not metadata["complete"]:
        return "INCOMPLETE COMPARISON — headline withheld"
    facts = metadata["frame_facts"]
    names = sorted(
        facts,
        key=lambda name: facts[name]["mean_boxed_frames_per_clip"] or 0,
        reverse=True,
    )
    dense, sparse = names
    runs = [metadata["paired_overall"][name] for name in names]
    denominators = [r["activity_denominators"] for r in runs]
    if not metadata["shared_scored_clips"] or any(
        not d["no_on_ball_claimed_on_ball"] or not d["on_ball_recalled"]
        for d in denominators
    ):
        return "Insufficient shared scored clips with classified human notes — headline withheld."

    d_count, s_count = (
        metadata["paired_counts"][name]["no_on_ball_claimed_on_ball"] for name in names
    )
    d_total, s_total = (d["no_on_ball_claimed_on_ball"] for d in denominators)
    strict = max(metadata["paired_counts"][name]["on_ball_recalled"] for name in names)
    lenient = max(
        metadata["paired_counts"][name]["on_ball_recalled_lenient"] for name in names
    )
    on_ball = denominators[0]["on_ball_recalled"]
    models = (
        facts[dense]["model"]
        if facts[dense]["model"] == facts[sparse]["model"]
        else f"{facts[dense]['model']} ({dense}) and {facts[sparse]['model']} ({sparse})"
    )
    return (
        f"On {metadata['shared_scored_clips']} shared scored clips, {models} invented on-ball play for {d_count} of {d_total} "
        f"clips where MJ saw none ({dense}) and {s_count} of {s_total} ({sparse}), "
        f"matched MJ's actual action on at most {strict} of {on_ball} on-ball clips "
        f"({lenient} of {on_ball} lenient). The runs sent a mean {facts[dense]['mean_boxed_frames_per_clip']:g} "
        f"boxed frames per clip vs {facts[sparse]['mean_boxed_frames_per_clip']:g}; the sparse run ({sparse}) "
        f"had a single frame on {facts[sparse]['single_frame_attempts']} of {facts[sparse]['attempted_clips']} attempts."
    )


def markdown(result: dict) -> str:
    metadata = result["comparison_metadata"]
    keys = (
        [
            "no_on_ball_claimed_on_ball_rate",
            "off_pitch_claimed_on_ball_rate",
            "idle_claimed_on_ball_rate",
            "on_ball_recall",
            "on_ball_recall_lenient",
            "activity_agreement_rate",
            "fabricated_rate",
            "sentence_matches_note",
        ]
        + [f"{k}_rate" for k in RATE_KEYS]
        + [
            "zero_duration_event_rate",
            "window_filling_event_rate",
            "events_per_sent_frame",
            "high_confidence_completed_from_one_frame_count",
            "from_thinking_rate",
            "valid_attempt_rate",
            "time_in_window_event_rate",
            "events_per_clip",
            "wall_s_per_clip",
        ]
    )
    lines = [
        result["headline"],
        "",
        f"Shared scored clips: {metadata['shared_scored_clips']}. {metadata['denominators']}",
        "",
        *(
            [
                f"- {name}: missing clip IDs: {', '.join(c['missing_clip_ids']) or 'none'}; stop markers: {json.dumps(c['stop_markers'], sort_keys=True)}"
                for name, c in metadata["coverage"].items()
            ]
            if not metadata["complete"]
            else []
        ),
        *(
            [
                f"Mixed settings explicitly allowed: {json.dumps(metadata['mixed_settings'], sort_keys=True)}. All scores use the supplied manifest truth.",
                "",
            ]
            if metadata["mixed_settings"]
            else []
        ),
        result["honest_limit"],
        "",
        result["experiment"],
        "",
        "Off-pitch clips given on-ball events: "
        + "; ".join(
            f"{lane['run']} {metadata['paired_counts'][name]['off_pitch_claimed_on_ball']}/{metadata['paired_overall'][name]['activity_denominators']['off_pitch_claimed_on_ball']}"
            for name, lane in result["lanes"].items()
        )
        + ".",
        "",
        next(iter(result["lanes"].values()))["report"]["denominators"],
        "",
        "| Run | Scored / failed | " + " | ".join(keys) + " |",
        "|---|---:|" + "---:|" * len(keys),
    ]
    for name, lane in result["lanes"].items():
        overall = metadata["paired_overall"][name]
        values = [
            "N/A"
            if overall[k] is None
            else "/".join(
                str(overall[k][v]) for v in ("agree", "disagree", "undetermined")
            )
            if k == "sentence_matches_note"
            else f"{overall[k]:.2%}"
            if k.endswith("_rate") or k in {"on_ball_recall", "on_ball_recall_lenient"}
            else str(overall[k])
            for k in keys
        ]
        lines.append(
            f"| {lane['run']} | {lane['report']['overall']['scored_clips']} / {lane['report']['overall']['failed_clips']} | "
            + " | ".join(values)
            + " |"
        )
    lines += [""]
    lines += [
        "Sentence counts are agree/disagree/undetermined. Full per-run report denominators (comparison rates above use shared clips):",
        "",
        *[
            f"- {lane['run']}: {lane['report']['overall']['activity_denominators']}; jersey eligible {lane['report']['overall']['identity_evaluated_clips']}; kit eligible {lane['report']['overall']['kit_evaluated_clips']}; noted clips {lane['report']['overall']['human_noted_scored_clips']}; fabrication eligible {lane['report']['overall']['fabricated_evaluated_clips']}"
            for lane in result["lanes"].values()
        ],
        "",
    ]
    lines += [
        f"- {lane['run']}: {lane['sent_frame_count']} sent frames ({lane['sent_frames_per_attempt']}/attempt); {lane['shifted_frame_count']} gap-adjusted timestamps, maximum shift {lane['max_sampling_shift_s']}s."
        for lane in result["lanes"].values()
    ]
    lines += ["", result["sentence_selection"]]
    for lane in result["lanes"].values():
        lines += ["", f"Five sentences — {lane['run']}:", ""]
        lines += [
            f"- `{row['clip_id']}`: “{row['sentence']}”"
            for row in lane["five_sentences"]
        ]
        failures = [c for c in lane["report"]["clips"] if c["status"] == "failed"]
        if failures:
            lines += ["", "Failures:", ""] + [
                f"- `{c['clip_id']}`: {c['error']}" for c in failures
            ]
        if lane["unrun_clips"]:
            lines += ["", f"Unrun: {', '.join(lane['unrun_clips'])}"]

    def cell(value):
        return (
            str(value if value is not None else "")
            .replace("|", "&#124;")
            .replace("\n", " ")
        )

    names = list(result["lanes"])
    lines += [
        "",
        f"All {len(result['per_clip_comparison'])} clips — MJ notes verbatim:",
        "",
        f"| Clip | MJ note | {names[0]} sentence | {names[0]} events (type/outcome) | {names[1]} sentence | {names[1]} events (type/outcome) | truth_activity | {names[0]} verdict | {names[1]} verdict |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for row in result["per_clip_comparison"]:
        values = [row["clip_id"], row["human_note"]]
        verdicts, activities = [], []
        for name in names:
            clip = row["reads"][name] or {}
            read = clip.get("semantic", {})
            m = clip.get("metrics", {})
            values += [
                read.get("sentence", clip.get("error", "unrun")),
                ", ".join(
                    f"{e['event_type']}/{e['outcome']}" for e in read.get("events", [])
                ),
            ]
            activities = m.get("truth_activity", activities)
            verdicts.append(
                f"activity: {'undetermined' if m.get('activity_agreement') is None else 'agree' if m['activity_agreement'] else 'disagree'}; sentence: {m.get('sentence_matches_note', 'undetermined')}; event recall: {'N/A' if m.get('on_ball_recalled') is None else 'hit' if m['on_ball_recalled'] else 'miss'}"
            )
        values += [
            (", ".join(activities) or "unclassified")
            + (" (label disputed)" if row["truth_label_disputed"] else ""),
            *verdicts,
        ]
        lines.append("| " + " | ".join(cell(v) for v in values) + " |")
    lines += ["", "Caveats:", ""] + [f"- {c}" for c in result["caveats"]]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--runs",
        nargs="+",
        default=["dense=e1c-annotated-dense", "prod30=e1c-annotated-prod30"],
    )
    parser.add_argument(
        "--allow-mixed",
        action="store_true",
        help="allow differing adapter/model/frozen-set metadata; scores still use supplied truth",
    )
    parser.add_argument("--out-json", type=Path, required=True)
    parser.add_argument("--out-md", type=Path, required=True)
    args = parser.parse_args(argv)
    runs = {}
    for entry in args.runs:
        name, separator, directory = entry.partition("=")
        if not separator or not name or not directory or name in runs:
            parser.error("runs must be unique NAME=DIR pairs")
        runs[name] = directory
    result = compare(
        args.reports_root, runs, args.manifest, allow_mixed=args.allow_mixed
    )
    args.out_json.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    args.out_md.write_text(markdown(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
