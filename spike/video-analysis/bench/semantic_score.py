"""Deterministic semantic-lane honesty metrics; event correctness needs notes."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

try:
    from .compare_runs import jersey_review
    from .contract import BOX_T_SPAN_TOLERANCE_S
    from .score import fabricated_event_classes
    from .semantic_contract import SemanticRead, parse_read
except ImportError:  # pragma: no cover
    from compare_runs import jersey_review
    from contract import BOX_T_SPAN_TOLERANCE_S
    from score import fabricated_event_classes
    from semantic_contract import SemanticRead, parse_read

HONEST_LIMIT = (
    "The frozen clips have no human notes: event CORRECTNESS is not measured until MJ supplies them. "
    "This run measures honesty/format/presence-only/number-invention/kit-colour and time bounds only."
)
PRESENCE_PATTERN = re.compile(r"\b(?:is visible|can be seen|is on the field)\b", re.I)
RATE_KEYS = (
    "valid",
    "empty",
    "presence_only",
    "number_invented",
    "kit_color_match",
    "kit_color_abstain",
    "kit_color_wrong",
    "time_in_window",
)


def rate(values: list[bool]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def score_read(read: SemanticRead, truth: dict) -> dict:
    start, end = (float(truth["window"][k]) for k in ("start_s", "end_s"))
    tolerance = BOX_T_SPAN_TOLERANCE_S
    event_times = [
        start - tolerance <= event.t0 <= event.t1 <= end + tolerance
        for event in read.events
    ]
    jersey = jersey_review({"claims": [{"claim": read.sentence}]}, truth)
    color = truth.get("kit_color")
    kit_match = (
        None
        if color is None or read.kit_color_seen == "unclear"
        else read.kit_color_seen == str(color).lower()
    )
    # Apply the exact existing narrow keyword rule to prose AND explicit classes.
    # Underscores become spaces; broad classes such as off_ball remain ungraded.
    event_text = " ".join(event.event_type.replace("_", " ") for event in read.events)
    fabricated = fabricated_event_classes(
        f"{read.sentence} {event_text}", truth.get("human_note")
    )
    return {
        "valid": True,
        "empty": not read.events and read.player_visible in {"no", "unclear"},
        "event_time_in_window": event_times,
        "time_in_window": all(event_times),
        "number_invented": jersey["invented_jersey_number_kill"],
        "kit_color_match": kit_match,
        "kit_color_abstain": read.kit_color_seen == "unclear",
        "kit_color_wrong": kit_match is False,
        "presence_only": not any(
            event.event_type not in {"none", "unclear"} for event in read.events
        )
        and bool(PRESENCE_PATTERN.search(read.sentence)),
        "fabricated_event_classes": fabricated,
        "event_count": len(read.events),
    }


def score_clip(result: dict, truth: dict) -> dict:
    clip = {
        "clip_id": result["clip_id"],
        "wall_s": result.get("wall_s", 0),
        "status": "failed",
        "valid": False,
        "error": result.get("error"),
    }
    try:
        # Revalidate stored results when re-scoring; cached parsed data cannot hide bad raw JSON.
        read = (
            parse_read(result["semantic_raw"])
            if "semantic_raw" in result
            else SemanticRead.model_validate(result.get("semantic"))
        )
    except (ValidationError, TypeError):
        clip["error"] = clip["error"] or "semantic schema validation failed"
        return clip
    clip["valid"] = True
    if clip["error"]:
        return clip
    clip.update(
        status="scored", semantic=read.model_dump(), metrics=score_read(read, truth)
    )
    return clip


def score_run(
    results: list[dict], truths: dict, *, adapter: str = "qwen3vl_annotated"
) -> dict:
    clips = [score_clip(result, truths[result["clip_id"]]) for result in results]
    scored = [clip["metrics"] for clip in clips if clip["status"] == "scored"]
    overall = {
        "attempted_clips": len(clips),
        "scored_clips": len(scored),
        "failed_clips": len(clips) - len(scored),
        **{f"{key}_rate": rate([m[key] is True for m in scored]) for key in RATE_KEYS},
        "valid_attempt_rate": rate([c["valid"] for c in clips]),
        "kit_color_match_when_asserted_rate": rate(
            [m["kit_color_match"] for m in scored if m["kit_color_match"] is not None]
        ),
        "time_in_window_event_rate": rate(
            [v for m in scored for v in m["event_time_in_window"]]
        ),
        "fabricated_rate": rate(
            [
                bool(m["fabricated_event_classes"])
                for m in scored
                if m["fabricated_event_classes"] is not None
            ]
        ),
        "human_noted_scored_clips": sum(
            m["fabricated_event_classes"] is not None for m in scored
        ),
        "events_per_clip": round(sum(m["event_count"] for m in scored) / len(scored), 3)
        if scored
        else None,
        "wall_s_per_clip": round(sum(c["wall_s"] for c in clips) / len(clips), 3)
        if clips
        else None,
    }
    has_notes = any(truth.get("human_note") is not None for truth in truths.values())
    return {
        "schema_version": "film-room-semantic-report-v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "adapter": adapter,
        "honest_limit": "Human notes enable only the existing conservative keyword mismatch rule on noted clips; event correctness is not fully measured."
        if has_notes
        else HONEST_LIMIT,
        "denominators": "Honesty rates and events/clip: scored clips. Valid attempt rate and wall/clip: all attempts. Kit match excludes abstentions from the asserted-only rate; match/abstain/wrong rates use all scored clips. Time/clip means all event times pass (vacuously true with no events); event-time rate counts events. Fabricated rate: noted scored clips only.",
        "overall": overall,
        "clips": clips,
    }


def render_markdown(report: dict) -> str:
    lines = [
        report["honest_limit"],
        "",
        report["denominators"],
        "",
        "| Metric | Value |",
        "|---|---:|",
    ]
    lines += [
        f"| {key} | {value if value is not None else 'N/A'} |"
        for key, value in report["overall"].items()
    ]
    lines += ["", "| Clip | Status | Sentence / failure |", "|---|---|---|"]
    for clip in report["clips"]:
        sentence = clip.get("semantic", {}).get("sentence") or clip.get("error", "")
        lines.append(
            f"| {clip['clip_id']} | {clip['status']} | {sentence.replace('|', '&#124;')} |"
        )
    return "\n".join(lines) + "\n"


def write_report(report: dict, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n"
    )
    (output_dir / "report.md").write_text(render_markdown(report))
