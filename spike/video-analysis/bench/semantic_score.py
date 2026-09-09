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
    from .score import EVENT_KEYWORDS, _event_classes, fabricated_event_classes
    from .identity_truth import kit_truth
    from .provenance import thinking_rate
    from .semantic_contract import SemanticRead, parse_read
    from .semantic_activity import activity_metrics
except ImportError:  # pragma: no cover
    from compare_runs import jersey_review
    from contract import BOX_T_SPAN_TOLERANCE_S
    from score import EVENT_KEYWORDS, _event_classes, fabricated_event_classes
    from identity_truth import kit_truth
    from provenance import thinking_rate
    from semantic_contract import SemanticRead, parse_read
    from semantic_activity import activity_metrics

HONEST_LIMIT = (
    "The frozen clips have no human notes: event CORRECTNESS is not measured until MJ supplies them. "
    "This run measures honesty/format/presence-only/number-invention/kit-colour and time bounds only."
)
LEGACY_PRESENCE_PATTERN = re.compile(
    r"\b(?:is visible|can be seen|is on the field)\b", re.I
)
PRESENCE_PATTERN = re.compile(r"\bvisible\b|\bcan be seen\b|\bon the field\b", re.I)
ACTION_VERB_PATTERN = re.compile(
    r"\b(?:carry|carries|carrying|pass|duel|shot|shoot|run|running|dribbl|tackl|cross|header|clear)",
    re.I,
)
STRICT_PRESENCE_EXCLUSIONS = re.compile(
    r"\b(?:hold|holding|with (?:the )?ball|possession|moving|interacting)\b", re.I
)
CONSISTENCY_INFLECTIONS = {
    "carry": re.compile(r"\b(?:carrying|dribbling|running with (?:the )?ball)\b", re.I),
    "pass": re.compile(r"\bpassing\b", re.I),
}
RATE_KEYS = (
    "valid",
    "empty",
    "presence_only_read",
    "presence_only_sentence",
    "presence_only_strict",
    "presence_with_substantive_event",
    "sentence_event_consistency",
    "supplied_number_asserted_as_kit_detail",
    "number_invented",
    "kit_color_match",
    "kit_color_abstain",
    "kit_color_wrong",
    "time_in_window",
)
IDENTITY_KEYS = {
    "number_invented",
    "supplied_number_asserted_as_kit_detail",
}
KIT_KEYS = {
    "kit_color_match",
    "kit_color_abstain",
    "kit_color_wrong",
}


def rate(values: list[bool]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def score_read(read: SemanticRead, truth: dict, *, sent_frame_count: int = 0) -> dict:
    start, end = (float(truth["window"][k]) for k in ("start_s", "end_s"))
    tolerance = BOX_T_SPAN_TOLERANCE_S
    event_times = [
        start - tolerance <= event.t0 <= event.t1 <= end + tolerance
        for event in read.events
    ]
    jersey = jersey_review({"claims": [{"claim": read.sentence}]}, truth)
    kit = kit_truth(truth)
    color = kit["color"]
    kit_match = (
        None
        if color is None or read.kit_color_seen == "unclear"
        else read.kit_color_seen == str(color).lower()
    )
    # Apply the exact existing narrow keyword rule to prose AND explicit classes.
    # Underscores become spaces; broad classes such as off_ball remain ungraded.
    event_text = " ".join(event.event_type.replace("_", " ") for event in read.events)
    fabricated = fabricated_event_classes(
        f"{read.sentence}; {event_text}", truth.get("human_note")
    )
    substantive = {event.event_type for event in read.events} - {"none", "unclear"}
    sentence_classes = _event_classes(read.sentence)
    sentence_classes.update(
        cls
        for cls, pattern in CONSISTENCY_INFLECTIONS.items()
        if pattern.search(read.sentence)
    )
    mapped_events = substantive & EVENT_KEYWORDS.keys()
    presence_sentence = bool(PRESENCE_PATTERN.search(read.sentence)) and not bool(
        ACTION_VERB_PATTERN.search(read.sentence)
    )
    zero_duration = [event.t0 == event.t1 for event in read.events]
    window_filling = [
        abs(event.t0 - start) <= tolerance and abs(event.t1 - end) <= tolerance
        for event in read.events
    ]
    metrics = {
        "valid": True,
        "empty": not read.events and read.player_visible in {"no", "unclear"},
        "event_time_in_window": event_times,
        "time_in_window": all(event_times),
        # Semantic reads forbid any unsupplied number, including bare #N labels.
        "number_invented": bool(jersey["unsupplied_numbers"]),
        "kit_color_match": kit_match,
        "kit_color_abstain": kit["uncertain"] or read.kit_color_seen == "unclear",
        "kit_color_wrong": kit_match is False,
        "presence_only_read": not substantive
        and bool(LEGACY_PRESENCE_PATTERN.search(read.sentence)),
        "presence_only_sentence": presence_sentence,
        "presence_only_strict": presence_sentence
        and not bool(STRICT_PRESENCE_EXCLUSIONS.search(read.sentence)),
        "presence_with_substantive_event": presence_sentence and bool(substantive),
        "sentence_event_consistency": mapped_events <= sentence_classes,
        "sentence_event_unmatched_classes": sorted(mapped_events - sentence_classes),
        "sentence_event_unmapped_classes": sorted(substantive - mapped_events),
        "supplied_number_asserted_as_kit_detail": jersey[
            "supplied_number_asserted_as_kit_detail"
        ],
        "zero_duration_events": zero_duration,
        "zero_duration_event_rate": rate(zero_duration),
        "window_filling_events": window_filling,
        "window_filling_event_rate": rate(window_filling),
        "sent_frame_count": sent_frame_count,
        "events_per_sent_frame": round(len(read.events) / sent_frame_count, 4)
        if sent_frame_count
        else None,
        "high_confidence_completed_from_one_frame_count": sum(
            event.confidence == "high" and event.outcome == "completed"
            for event in read.events
        )
        if sent_frame_count == 1
        else 0,
        "fabricated_event_classes": fabricated,
        "event_count": len(read.events),
        **activity_metrics(read, truth),
    }
    if truth.get("truth_label_disputed"):
        metrics.update({key: None for key in IDENTITY_KEYS})
    if not kit["eligible"]:
        metrics.update({key: None for key in KIT_KEYS})
    return metrics


def score_clip(result: dict, truth: dict) -> dict:
    clip = {
        "clip_id": result["clip_id"],
        "wall_s": result.get("wall_s", 0),
        "status": "failed",
        "valid": False,
        "error": result.get("error"),
        "from_thinking": bool(result.get("from_thinking", False)),
        "truth_label_disputed": bool(truth.get("truth_label_disputed")),
        "kit_metrics_eligible": kit_truth(truth)["eligible"],
        "human_note": truth.get("human_note"),
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
        status="scored",
        semantic=read.model_dump(),
        metrics=score_read(
            read, truth, sent_frame_count=len(result.get("sent_frames", []))
        ),
    )
    return clip


def score_run(
    results: list[dict],
    truths: dict,
    *,
    adapter: str = "qwen3vl_annotated",
    truth_provenance: dict | None = None,
) -> dict:
    clips = [score_clip(result, truths[result["clip_id"]]) for result in results]
    scored = [clip["metrics"] for clip in clips if clip["status"] == "scored"]
    sent_frame_count = sum(m["sent_frame_count"] for m in scored)
    overall = {
        "attempted_clips": len(clips),
        "scored_clips": len(scored),
        "failed_clips": len(clips) - len(scored),
        **{
            f"{key}_rate": rate(
                [
                    c["metrics"][key] is True
                    for c in clips
                    if c["status"] == "scored"
                    and (key not in IDENTITY_KEYS or not c["truth_label_disputed"])
                    and (key not in KIT_KEYS or c["kit_metrics_eligible"])
                ]
            )
            for key in RATE_KEYS
        },
        "disputed_clips": [c["clip_id"] for c in clips if c["truth_label_disputed"]],
        "identity_evaluated_clips": sum(
            c["status"] == "scored" and not c["truth_label_disputed"] for c in clips
        ),
        "kit_evaluated_clips": sum(
            c["status"] == "scored" and c["kit_metrics_eligible"] for c in clips
        ),
        "from_thinking_rate": thinking_rate(results),
        "zero_duration_event_rate": rate(
            [v for m in scored for v in m["zero_duration_events"]]
        ),
        "window_filling_event_rate": rate(
            [v for m in scored for v in m["window_filling_events"]]
        ),
        "events_per_sent_frame": round(
            sum(m["event_count"] for m in scored) / sent_frame_count, 4
        )
        if sent_frame_count
        else None,
        "high_confidence_completed_from_one_frame_count": sum(
            m["high_confidence_completed_from_one_frame_count"] for m in scored
        ),
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
                if m["fabricated_event_classes"] is not None and m["truth_activity"]
            ]
        ),
        "human_noted_scored_clips": sum(
            m["fabricated_event_classes"] is not None for m in scored
        ),
        "fabricated_evaluated_clips": sum(
            m["fabricated_event_classes"] is not None and bool(m["truth_activity"])
            for m in scored
        ),
        **{
            output: rate([m[key] for m in scored if m[key] is not None])
            for output, key in (
                ("off_pitch_claimed_on_ball_rate", "off_pitch_claimed_on_ball"),
                ("idle_claimed_on_ball_rate", "idle_claimed_on_ball"),
                ("on_ball_recall", "on_ball_recalled"),
                ("on_ball_recall_lenient", "on_ball_recalled_lenient"),
                ("no_on_ball_claimed_on_ball_rate", "no_on_ball_claimed_on_ball"),
                ("activity_agreement_rate", "activity_agreement"),
            )
        },
        "activity_denominators": {
            key: sum(m[key] is not None for m in scored)
            for key in (
                "off_pitch_claimed_on_ball",
                "idle_claimed_on_ball",
                "on_ball_recalled",
                "on_ball_recalled_lenient",
                "no_on_ball_claimed_on_ball",
                "activity_agreement",
            )
        },
        "sentence_matches_note": {
            verdict: sum(m["sentence_matches_note"] == verdict for m in scored)
            for verdict in ("agree", "disagree", "undetermined")
        },
        "events_per_clip": round(sum(m["event_count"] for m in scored) / len(scored), 3)
        if scored
        else None,
        "wall_s_per_clip": round(sum(c["wall_s"] for c in clips) / len(clips), 3)
        if clips
        else None,
    }
    has_notes = any(truth.get("human_note") is not None for truth in truths.values())
    return {
        **(truth_provenance or {}),
        "schema_version": "film-room-semantic-report-v5",
        "generated_at": datetime.now(UTC).isoformat(),
        "adapter": adapter,
        "honest_limit": "Human notes enable deterministic activity and event-class checks. These measure coarse correctness against MJ's observations, not timing/outcome accuracy or exhaustive semantic correctness."
        if has_notes
        else HONEST_LIMIT,
        "denominators": "Honesty rates and events/clip: scored clips. Jersey rates exclude disputed labels. Kit rates include verified colour overrides and count uncertain kit truth as abstention; disputed kits without an override or uncertainty flag remain excluded. Lane A number_invented is stricter than the shared jersey kill: any unsupplied #N / number N / jersey N flags, while timestamps do not. Activity subset rates use classified notes only; agreement excludes unclassified notes. Strict on-ball recall requires an exact event-class match; lenient recall additionally treats receive/turn/loss as carry-compatible, never header/duel/interception. The no-on-ball subset excludes mixed notes containing any on_ball_action. Sentence verdicts count all scored clips, including undetermined notes. Valid attempt rate and wall/clip: all attempts. Kit match excludes abstentions from the asserted-only rate; match/abstain/wrong rates use kit-eligible scored clips. Time/clip means all event times pass (vacuously true with no events); event-time rate counts events. Fabricated rate: noted scored clips with classifiable activity only; identity-only notes are excluded. Simple no/without clause negation suppresses event keywords in that diagnostic. Presence-only read retains the original event-gated narrow regex; sentence-only presence ignores events and excludes the specified action-verb stems. Strict presence additionally excludes hold/holding, with (the) ball, possession, moving and interacting. Presence-with-substantive-event uses the original sentence-only presence flag and any event except none/unclear. Consistency requires only event classes with an existing keyword map, adds carrying/passing/dribbling/running-with-ball inflections locally, and records ignored unmapped classes separately; no mapped events pass vacuously. Zero-duration and window-filling rates count events, not clips. Events/sent-frame uses all frames of scored clips. Thinking rate counts recorded true flags across all attempts, including failures.",
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
