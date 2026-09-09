#!/usr/bin/env python3
"""Re-score annotated runs against current local notes and emit a deterministic ledger."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

try:
    from .apply_notes import load_truths
    from .semantic_score import RATE_KEYS, score_run
except ImportError:  # pragma: no cover
    from apply_notes import load_truths
    from semantic_score import RATE_KEYS, score_run

CAVEATS = [
    "Truth box_track stands in for the production tracker's persisted geometry on every sampled frame. Tracker accuracy and unlabelled-player grounding are not evaluated.",
    "No boxes are requested from the VLM, so rectangle echo is not a model-geometry failure mode in this lane. The supplied jersey label is not proof of number legibility.",
    "Dense samples are spread across the window, capped at 12; 30s/3 is a sparse annotated control. These isolate sampling under the same semantic contract, not a comparison to the old grounding score.",
    "Presence-only and jersey checks are narrow regex rules, not semantic judgments; kit-colour checks compare the explicit field only. Goal and name prohibitions are prompt rules, not verified truth guarantees.",
    "The conservative event keyword mismatch rule becomes available only on clips with human notes; it is neither a complete event taxonomy nor a measure of event correctness.",
    "Sequential single passes, without repeats or confidence intervals. Wall time includes extraction/drawing and all failed attempts; Ollama may reuse a warm model. Temporary frame paths record provenance but images are removed after each call.",
    "Uniform target samples falling in tracking gaps snap to the nearest recorded track timestamp within 0.5s, remaining distinct and chronological; target_t and sampling_shift_s record every adjustment. Larger gaps fail before inference. Geometry is never extrapolated across gaps.",
    "No adoption recommendation; MJ owns that decision.",
]


def compare(reports_root: Path, runs: dict[str, str], manifest_path: Path) -> dict:
    if len(runs) != 2:
        raise ValueError("provide the dense and prod30 runs")
    manifest = json.loads(manifest_path.read_text())
    truths = {truth["clip_id"]: truth for _, truth in load_truths(manifest_path)}
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
        report = score_run(raw, truths)
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
        "human_notes_sha256": hashlib.sha256(
            json.dumps(
                {cid: truths[cid].get("human_note") for cid in selected}, sort_keys=True
            ).encode()
        ).hexdigest(),
        "sentence_selection": "First five scored clips in manifest order, verbatim; no quality selection.",
        "lanes": lanes,
        "caveats": CAVEATS,
    }


def markdown(result: dict) -> str:
    keys = [f"{k}_rate" for k in RATE_KEYS] + [
        "valid_attempt_rate",
        "time_in_window_event_rate",
        "fabricated_rate",
        "events_per_clip",
        "wall_s_per_clip",
    ]
    lines = [
        result["honest_limit"],
        "",
        result["experiment"],
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
            else f"{overall[k]:.2%}"
            if k.endswith("_rate")
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
