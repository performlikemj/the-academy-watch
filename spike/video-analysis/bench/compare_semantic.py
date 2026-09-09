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
    "The original fabricated_rate now evaluates all 20 notes, including the disputed identity-only note; absence of an event keyword is not proof the event never occurred. Activity checks separately grade only notes with an activity classification.",
    "Sequential single passes, without repeats or confidence intervals. Wall time includes extraction/drawing and all failed attempts; Ollama may reuse a warm model. Temporary frame paths record provenance but images are removed after each call.",
    "Uniform target samples falling in tracking gaps snap to the nearest recorded track timestamp within 0.5s, remaining distinct and chronological; target_t and sampling_shift_s record every adjustment. Larger gaps fail before inference. Geometry is never extrapolated across gaps.",
    "All 20 frozen kit fields say red and both measured runs used red rectangles. MJ confirms n24 is actually black; that disputed clip is excluded. Kit-colour matching remains uninformative until the evaluated set includes verified non-red kits. Future lane-A model inputs use magenta; these saved outputs were not rerun.",
    "Every lane-A response (40/40) was read from Ollama's thinking field despite think=false. Schema-valid parsing is established; the format grammar's effect on that field is unverified. The transport is unchanged.",
    "Sentence-only presence applies the specified verb-stem exclusion literally: moving, interacting and holding are not excluded. Consistency uses the unchanged conservative score._event_classes vocabulary, so carrying/passing inflections and unmapped broad types may remain unmatched; these are lexical diagnostics, not semantic accuracy.",
    "Truth and note hashes describe the current rescoring snapshot across all manifest truth files. Historical run.json files retain their original launch metadata; absent inference-time hashes are not retroactively asserted.",
    "No adoption recommendation; MJ owns that decision.",
    "MJ reports 'some misses as far as boxes are concerned': truth box_track has visible tracker misses. These are geometry/input errors, not model errors, and may affect semantic reads.",
    "m04-n24-t3013-679939-681217 has a disputed truth label: MJ wrote 'wrong number. this is number 12 from the shorts'. The frozen #24 binding is not corrected by inference; this clip remains visible but is excluded from both scorers' jersey/kit denominators. MJ's appended clarification confirms BLACK warm-up kit and black shorts: the earlier fps2 video lane and annotated prod30 read black correctly, while frozen kit_color red is wrong. The frozen label/colour fields are retained for audit and excluded from metrics.",
    "Activity agreement is coarse compatibility: all on-ball notes can agree with any on-ball model activity even when event recall fails. A mixed idle/on-ball note is eligible for both subset rates; the idle rate is not itself proof of fabrication on that mixed clip. Header/receive/turn/loss remain distinct note classes absent from ACTION_TYPES, so generic carry earns no event recall credit. Outcomes and event timing are not graded against the notes.",
    "Sentence verdicts are lexical class overlap, not full entailment: agree requires a shared activity/action class and no detected incompatible assertion; disagree requires an incompatible class/context; otherwise undetermined. They do not validate every detail or robustly resolve negation, actor attribution or temporal order.",
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
                "sentence_matches_note",
            )
        },
    }


def compare(reports_root: Path, runs: dict[str, str], manifest_path: Path) -> dict:
    if len(runs) != 2:
        raise ValueError("provide the dense and prod30 runs")
    manifest = json.loads(manifest_path.read_text())
    truths, truth_provenance = load_truth_snapshot(manifest_path)
    selected = None
    lanes = {}
    for name, run in runs.items():
        directory = reports_root / run
        settings = json.loads((directory / "run.json").read_text())
        if (
            settings["adapter"] != "qwen3vl_annotated"
            or settings["frozen_set_id"] != manifest["frozen_set_id"]
        ):
            raise ValueError("semantic adapter and matching frozen set required")
        if selected is not None and settings["clips"] != selected:
            raise ValueError("runs must select the same clips in the same order")
        selected = settings["clips"]
        original = json.loads((directory / "report.json").read_text())
        raw = [
            json.loads((directory / "claims" / f"{cid}.json").read_text())
            for cid in selected
            if (directory / "claims" / f"{cid}.json").is_file()
        ]
        report = score_run(raw, truths, truth_provenance=truth_provenance)
        report["generated_at"] = original["generated_at"]
        scored = [c for c in report["clips"] if c["status"] == "scored"]
        frames = [frame for row in raw for frame in row["sent_frames"]]
        shifts = [abs(frame.get("sampling_shift_s", 0)) for frame in frames]
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
            "unrun_clips": [
                cid for cid in selected if cid not in {r["clip_id"] for r in raw}
            ],
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
    return {
        "experiment": "E1c lane A — annotated dense frames, semantic-only contract",
        "state": "measured",
        "honest_limit": next(iter(lanes.values()))["report"]["honest_limit"],
        "frozen_set_id": manifest["frozen_set_id"],
        **truth_provenance,
        "sentence_selection": "First five scored clips in manifest order, verbatim; no quality selection.",
        "lanes": lanes,
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


def markdown(result: dict) -> str:
    keys = (
        [
            "fabricated_rate",
            "off_pitch_claimed_on_ball_rate",
            "idle_claimed_on_ball_rate",
            "on_ball_recall",
            "activity_agreement_rate",
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
        result["honest_limit"],
        "",
        result["experiment"],
        "",
        "Off-pitch clips given on-ball events: "
        + "; ".join(
            f"{lane['run']} {sum(c.get('metrics', {}).get('off_pitch_claimed_on_ball') is True for c in lane['report']['clips'])}/{lane['report']['overall']['activity_denominators']['off_pitch_claimed_on_ball']}"
            for lane in result["lanes"].values()
        )
        + ".",
        "",
        next(iter(result["lanes"].values()))["report"]["denominators"],
        "",
        "| Run | Scored / failed | " + " | ".join(keys) + " |",
        "|---|---:|" + "---:|" * len(keys),
    ]
    for lane in result["lanes"].values():
        overall = lane["report"]["overall"]
        values = [
            "N/A"
            if overall[k] is None
            else "/".join(
                str(overall[k][v]) for v in ("agree", "disagree", "undetermined")
            )
            if k == "sentence_matches_note"
            else f"{overall[k]:.2%}"
            if k.endswith("_rate") or k == "on_ball_recall"
            else str(overall[k])
            for k in keys
        ]
        lines.append(
            f"| {lane['run']} | {overall['scored_clips']} / {overall['failed_clips']} | "
            + " | ".join(values)
            + " |"
        )
    lines += [""]
    lines += [
        "Sentence counts are agree/disagree/undetermined. Activity and identity denominators per run:",
        "",
        *[
            f"- {lane['run']}: {lane['report']['overall']['activity_denominators']}; identity eligible {lane['report']['overall']['identity_evaluated_clips']}; noted clips {lane['report']['overall']['human_noted_scored_clips']}"
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
    parser.add_argument("--out-json", type=Path, required=True)
    parser.add_argument("--out-md", type=Path, required=True)
    args = parser.parse_args(argv)
    runs = {}
    for entry in args.runs:
        name, separator, directory = entry.partition("=")
        if not separator or not name or not directory or name in runs:
            parser.error("runs must be unique NAME=DIR pairs")
        runs[name] = directory
    result = compare(args.reports_root, runs, args.manifest)
    args.out_json.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    args.out_md.write_text(markdown(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
