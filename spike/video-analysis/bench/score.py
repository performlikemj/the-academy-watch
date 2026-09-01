"""Deterministic scoring and report generation for Film Room evidence claims."""

from __future__ import annotations

import json
import math
import re
import statistics
from datetime import UTC, datetime
from pathlib import Path

try:
    from .contract import normalize_claim, parse_claims
except ImportError:  # pragma: no cover - direct script/import from bench directory
    from contract import normalize_claim, parse_claims

TIME_TOLERANCE_S = 0.5
IOU_THRESHOLD = 0.5
CONTAINMENT_THRESHOLD = 0.8
ECHO_BOX_TOLERANCE_PX = 2.0
TRACKING_GAP_MULTIPLIER = 2.0
MIN_INTERPOLATION_GAP_S = 0.25

# Intentionally narrow: an event is fabricated only when an explicit event
# keyword appears in the claim and no synonym for that class occurs in the note.
EVENT_KEYWORDS = {
    "goal": ("goal", "scores", "scored"),
    "shot": ("shot", "shoots", "strikes at goal"),
    "pass": ("pass", "passes", "passed"),
    "cross": ("cross", "crosses", "crossed"),
    "carry": ("carry", "carries", "dribble", "dribbles"),
    "duel": ("duel", "challenge", "tackle", "tackles"),
    "save": ("save", "saves", "saved"),
    "foul": ("foul", "fouled"),
    "corner": ("corner",),
    "free_kick": ("free kick", "free-kick"),
    "penalty": ("penalty",),
    "throw_in": ("throw in", "throw-in"),
    "offside": ("offside",),
}


def _rate(count: int, total: int) -> float | None:
    return round(count / total, 4) if total else None


def _box_area(box: list[float]) -> float:
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def _intersection(a: list[float], b: list[float]) -> float:
    return max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(
        0.0, min(a[3], b[3]) - max(a[1], b[1])
    )


def box_matches(
    claim_box: list[float], truth_box: list[float]
) -> tuple[bool, float, float]:
    """Return grounded, IoU, and fraction of the claim box inside truth."""
    intersection = _intersection(claim_box, truth_box)
    claim_area = _box_area(claim_box)
    truth_area = _box_area(truth_box)
    union = claim_area + truth_area - intersection
    iou = intersection / union if union > 0 else 0.0
    containment = intersection / claim_area if claim_area > 0 else 0.0
    grounded = iou >= IOU_THRESHOLD or containment >= CONTAINMENT_THRESHOLD
    return grounded, round(iou, 4), round(containment, 4)


def tracking_cadence_s(box_track: list[list]) -> float | None:
    """Return the median positive interval between truth-box samples."""
    timestamps = sorted(float(row[0]) for row in box_track)
    gaps = [
        right - left for left, right in zip(timestamps, timestamps[1:]) if right > left
    ]
    return float(statistics.median(gaps)) if gaps else None


def max_interpolation_gap_s(box_track: list[list]) -> float:
    """Return the largest adjacent sample gap safe to interpolate."""
    cadence = tracking_cadence_s(box_track)
    return max(
        MIN_INTERPOLATION_GAP_S,
        TRACKING_GAP_MULTIPLIER * cadence if cadence is not None else 0.0,
    )


def _truth_box_at_time(
    box_track: list[list], timestamp_s: float
) -> tuple[list[float] | None, bool]:
    """Return a truth box and whether the requested time is in a tracking gap."""
    if not box_track or not math.isfinite(timestamp_s):
        return None, False
    rows = sorted(box_track, key=lambda row: float(row[0]))
    if timestamp_s < float(rows[0][0]) or timestamp_s > float(rows[-1][0]):
        return None, False
    interpolation_limit = max_interpolation_gap_s(rows)
    for index, row in enumerate(rows):
        row_t = float(row[0])
        if math.isclose(timestamp_s, row_t, abs_tol=1e-9):
            return [float(value) for value in row[1:5]], False
        if row_t > timestamp_s:
            left = rows[index - 1]
            left_t = float(left[0])
            if row_t - left_t > interpolation_limit:
                return None, True
            fraction = (timestamp_s - left_t) / (row_t - left_t)
            return (
                [
                    float(left[column])
                    + fraction * (float(row[column]) - float(left[column]))
                    for column in range(1, 5)
                ],
                False,
            )
    return [float(value) for value in rows[-1][1:5]], False


def interpolate_truth_box(
    box_track: list[list], timestamp_s: float
) -> list[float] | None:
    """Interpolate a truth box only across samples at the normal cadence."""
    truth_box, _untracked_gap = _truth_box_at_time(box_track, timestamp_s)
    return truth_box


def _event_classes(text: str) -> set[str]:
    normalized = re.sub(r"\s+", " ", text.casefold())
    return {
        event_class
        for event_class, keywords in EVENT_KEYWORDS.items()
        if any(
            re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", normalized)
            for keyword in keywords
        )
    }


def fabricated_event_classes(claim: str, human_note: str | None) -> list[str] | None:
    if human_note is None:
        return None
    return sorted(_event_classes(claim) - _event_classes(human_note))


def _normalize_adapter_claim(claim: dict) -> dict:
    contract_claim = {
        key: claim.get(key)
        for key in ("claim", "t0", "t1", "box", "confidence", "visibility")
    }
    if claim.get("box_t_source") != "fallback_t0" and "box_t" in claim:
        contract_claim["box_t"] = claim.get("box_t")
    normalized = normalize_claim(contract_claim)
    if claim.get("box_t_source") == "fallback_t0":
        normalized["box_t_source"] = "fallback_t0"
    inherited_malformed = bool(claim.get("malformed"))
    inherited_fields = (
        claim.get("malformed_fields")
        if isinstance(claim.get("malformed_fields"), list)
        else []
    )
    malformed_fields = sorted(set(normalized["malformed_fields"] + inherited_fields))
    malformed = normalized["malformed"] or inherited_malformed
    model_box = claim.get("box_model_space", normalized["box"])
    if not (
        isinstance(model_box, (list, tuple))
        and len(model_box) == 4
        and all(
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(float(value))
            for value in model_box
        )
    ):
        model_box = None
    else:
        model_box = [float(value) for value in model_box]
    box_space = claim.get("box_space")
    if box_space not in {"normalized_1000", "image_pixels"}:
        box_space = None
    box_sanity_reason = claim.get("box_sanity_reason")
    if not isinstance(box_sanity_reason, str) or not box_sanity_reason:
        box_sanity_reason = None
    return {
        **normalized,
        "box_model_space": model_box,
        "box_space": box_space,
        "box_sanity_reason": box_sanity_reason,
        "malformed": malformed,
        "malformed_fields": malformed_fields,
        "boxed_frame": claim.get("boxed_frame") is True,
    }


def _drawn_anchor_frame(
    claim_box_t: float | None, anchored_frames: list[dict]
) -> dict | None:
    if claim_box_t is None:
        return None
    candidates = []
    for frame in anchored_frames:
        timestamp = frame.get("t") if isinstance(frame, dict) else None
        box = frame.get("box") if isinstance(frame, dict) else None
        if (
            isinstance(timestamp, (int, float))
            and not isinstance(timestamp, bool)
            and isinstance(box, list)
            and len(box) == 4
            and all(
                isinstance(value, (int, float)) and not isinstance(value, bool)
                for value in box
            )
        ):
            candidates.append((abs(float(claim_box_t) - float(timestamp)), frame))
    if not candidates:
        return None
    distance, frame = min(candidates, key=lambda item: item[0])
    return frame if distance <= TIME_TOLERANCE_S else None


def _echo_comparison_box(
    model_box: list[float] | None, box_space: str | None, anchor: dict | None
) -> list[float] | None:
    if model_box is None or anchor is None:
        return None
    if box_space != "normalized_1000":
        return model_box
    sent_w = anchor.get("sent_w")
    sent_h = anchor.get("sent_h")
    if not (
        isinstance(sent_w, (int, float))
        and not isinstance(sent_w, bool)
        and sent_w > 0
        and isinstance(sent_h, (int, float))
        and not isinstance(sent_h, bool)
        and sent_h > 0
    ):
        return None
    return [
        model_box[0] * float(sent_w) / 1000,
        model_box[1] * float(sent_h) / 1000,
        model_box[2] * float(sent_w) / 1000,
        model_box[3] * float(sent_h) / 1000,
    ]


def _matches_drawn_box(
    claim_box: list[float] | None, drawn_box: list[float] | None
) -> bool:
    return bool(
        claim_box is not None
        and drawn_box is not None
        and all(
            abs(claim_value - drawn_value) <= ECHO_BOX_TOLERANCE_PX
            for claim_value, drawn_value in zip(claim_box, drawn_box)
        )
    )


def score_claim(
    claim: dict, truth: dict, anchored_frames: list[dict] | None = None
) -> dict:
    normalized = _normalize_adapter_claim(claim)
    malformed_fields = normalized["malformed_fields"]
    malformed = normalized["malformed"]

    window = truth["window"]
    has_time = normalized["t0"] is not None and normalized["t1"] is not None
    has_box = normalized["box"] is not None
    time_grounded = bool(
        has_time
        and normalized["t0"] <= normalized["t1"]
        and normalized["t0"] >= float(window["start_s"]) - TIME_TOLERANCE_S
        and normalized["t1"] <= float(window["end_s"]) + TIME_TOLERANCE_S
    )
    box_track = truth.get("box_track") or []
    box_t = normalized["box_t"]
    truth_box, no_truth_at_time = (
        _truth_box_at_time(box_track, box_t) if box_t is not None else (None, False)
    )
    if has_box and truth_box is not None:
        box_grounded, iou, containment = box_matches(normalized["box"], truth_box)
    else:
        box_grounded, iou, containment = False, None, None
    midpoint = (normalized["t0"] + normalized["t1"]) / 2 if has_time else None
    truth_box_at_midpoint, _no_truth_at_midpoint = (
        _truth_box_at_time(box_track, midpoint)
        if midpoint is not None
        else (None, False)
    )
    if has_box and truth_box_at_midpoint is not None:
        (
            box_grounded_at_midpoint,
            iou_at_midpoint,
            containment_at_midpoint,
        ) = box_matches(normalized["box"], truth_box_at_midpoint)
    else:
        box_grounded_at_midpoint = False
        iou_at_midpoint = None
        containment_at_midpoint = None
    hollow = not has_time or not has_box
    supported = not malformed and time_grounded and box_grounded
    fabricated_classes = fabricated_event_classes(
        normalized["claim"], truth.get("human_note")
    )
    drawn_anchor_frame = (
        _drawn_anchor_frame(normalized["box_t"], anchored_frames or [])
        if normalized["boxed_frame"]
        else None
    )
    drawn_anchor_box = (
        [float(value) for value in drawn_anchor_frame["box"]]
        if drawn_anchor_frame is not None
        else None
    )
    echo_comparison_box = _echo_comparison_box(
        normalized["box_model_space"], normalized["box_space"], drawn_anchor_frame
    )
    echo_suspect = normalized["boxed_frame"] and _matches_drawn_box(
        echo_comparison_box, drawn_anchor_box
    )

    return {
        **normalized,
        "malformed": malformed,
        "malformed_fields": malformed_fields,
        "time_grounded": time_grounded,
        "box_grounded": box_grounded,
        "box_grounded_at_midpoint": box_grounded_at_midpoint,
        "hollow": hollow,
        "supported": supported,
        "unsupported": not supported,
        "no_truth_at_time": no_truth_at_time,
        "truth_box_at_box_t": [round(value, 3) for value in truth_box]
        if truth_box is not None
        else None,
        "truth_box_at_midpoint": [round(value, 3) for value in truth_box_at_midpoint]
        if truth_box_at_midpoint is not None
        else None,
        "iou": iou,
        "claim_box_containment": containment,
        "iou_at_midpoint": iou_at_midpoint,
        "claim_box_containment_at_midpoint": containment_at_midpoint,
        "drawn_anchor_box": [round(value, 3) for value in drawn_anchor_box]
        if drawn_anchor_box is not None
        else None,
        "echo_suspect": echo_suspect,
        "fabricated": bool(fabricated_classes)
        if fabricated_classes is not None
        else None,
        "fabricated_event_classes": fabricated_classes,
    }


def _claims_from_result(result: dict) -> list[dict]:
    claims = result.get("claims")
    if isinstance(claims, list):
        return claims
    return parse_claims(result.get("claims_raw", ""))


def _clip_metrics(scored_claims: list[dict]) -> dict:
    total = len(scored_claims)
    supported = sum(bool(claim["supported"]) for claim in scored_claims)
    time_only = sum(
        bool(claim["time_grounded"] and not claim["box_grounded"])
        for claim in scored_claims
    )
    hollow = sum(bool(claim["hollow"]) for claim in scored_claims)
    malformed = sum(bool(claim["malformed"]) for claim in scored_claims)
    box_sanity_guard_count = sum(
        claim["box_sanity_reason"] is not None for claim in scored_claims
    )
    untracked_gap = sum(bool(claim["no_truth_at_time"]) for claim in scored_claims)
    fabricated_evaluated = [
        claim for claim in scored_claims if claim["fabricated"] is not None
    ]
    fabricated = sum(bool(claim["fabricated"]) for claim in fabricated_evaluated)
    boxed_claims = [claim for claim in scored_claims if claim["boxed_frame"]]
    unboxed_claims = [claim for claim in scored_claims if not claim["boxed_frame"]]
    return {
        "claim_count": total,
        "boxed_claim_count": len(boxed_claims),
        "unboxed_claim_count": len(unboxed_claims),
        "supported_rate": _rate(supported, total),
        "supported_rate_unboxed": _rate(
            sum(bool(claim["supported"]) for claim in unboxed_claims),
            len(unboxed_claims),
        ),
        "supported_rate_boxed": _rate(
            sum(bool(claim["supported"]) for claim in boxed_claims),
            len(boxed_claims),
        ),
        "box_grounded_rate": _rate(
            sum(bool(claim["box_grounded"]) for claim in scored_claims), total
        ),
        "box_grounded_at_midpoint_rate": _rate(
            sum(bool(claim["box_grounded_at_midpoint"]) for claim in scored_claims),
            total,
        ),
        "box_grounded_rate_unboxed": _rate(
            sum(bool(claim["box_grounded"]) for claim in unboxed_claims),
            len(unboxed_claims),
        ),
        "box_grounded_rate_boxed": _rate(
            sum(bool(claim["box_grounded"]) for claim in boxed_claims),
            len(boxed_claims),
        ),
        "box_grounded_at_midpoint_rate_unboxed": _rate(
            sum(bool(claim["box_grounded_at_midpoint"]) for claim in unboxed_claims),
            len(unboxed_claims),
        ),
        "box_grounded_at_midpoint_rate_boxed": _rate(
            sum(bool(claim["box_grounded_at_midpoint"]) for claim in boxed_claims),
            len(boxed_claims),
        ),
        "echo_suspect_count": sum(
            bool(claim["echo_suspect"]) for claim in scored_claims
        ),
        "box_sanity_guard_count": box_sanity_guard_count,
        "untracked_gap": untracked_gap,
        "untracked_gap_rate": _rate(untracked_gap, total),
        "time_only_rate": _rate(time_only, total),
        "unsupported_rate": _rate(total - supported, total),
        "hollow_rate": _rate(hollow, total),
        "malformed_rate": _rate(malformed, total),
        "fabricated_rate": _rate(fabricated, len(fabricated_evaluated)),
    }


def score_clip(result: dict, truth: dict | None) -> dict:
    """Score one adapter result, applying mechanical and no-truth honesty rules."""
    base = {
        "clip_id": result.get("clip_id") or (truth or {}).get("clip_id"),
        "model": result.get("model"),
        "wall_s": result.get("wall_s"),
        "tokens": result.get("tokens"),
        "anchor_mode": result.get("anchor_mode"),
        "box_space": result.get("box_space"),
        "error": result.get("error"),
    }
    if result.get("error"):
        return {**base, "status": "failed", "claims": [], "metrics": _clip_metrics([])}
    if truth is None:
        return {
            **base,
            "status": "observed",
            "claims": [
                _normalize_adapter_claim(claim) for claim in _claims_from_result(result)
            ],
            "metrics": None,
        }
    anchored_frames = result.get("anchored_frames")
    anchored_frames = anchored_frames if isinstance(anchored_frames, list) else []
    scored_claims = [
        score_claim(claim, truth, anchored_frames)
        for claim in _claims_from_result(result)
    ]
    return {
        **base,
        "status": "scored",
        "claims": scored_claims,
        "metrics": _clip_metrics(scored_claims),
    }


def score_run(
    results: list[dict], truths: dict[str, dict], *, adapter: str | None = None
) -> dict:
    clips = [
        score_clip(result, truths.get(str(result.get("clip_id")))) for result in results
    ]
    scored_clips = [clip for clip in clips if clip["status"] == "scored"]
    aggregate_claims = [claim for clip in scored_clips for claim in clip["claims"]]
    metrics = _clip_metrics(aggregate_claims)
    metrics["claims_per_clip"] = (
        round(len(aggregate_claims) / len(scored_clips), 3) if scored_clips else None
    )
    walls = [
        float(clip["wall_s"])
        for clip in clips
        if isinstance(clip.get("wall_s"), (int, float))
    ]
    tokens = [
        int(clip["tokens"])
        for clip in clips
        if isinstance(clip.get("tokens"), int)
        and not isinstance(clip.get("tokens"), bool)
    ]
    metrics.update(
        {
            "wall_s_per_clip": round(sum(walls) / len(walls), 3) if walls else None,
            "tokens_per_clip": round(sum(tokens) / len(tokens), 3) if tokens else None,
            "failed_clips": sum(clip["status"] == "failed" for clip in clips),
            "observed_clips": sum(clip["status"] == "observed" for clip in clips),
            "scored_clips": len(scored_clips),
        }
    )
    anchor_modes = {
        clip["anchor_mode"] for clip in clips if clip.get("anchor_mode") is not None
    }
    box_spaces = {
        clip["box_space"] for clip in clips if clip.get("box_space") is not None
    }
    return {
        "schema_version": "film-room-evidence-report-v5",
        "generated_at": datetime.now(UTC).isoformat(),
        "adapter": adapter,
        "anchor_mode": next(iter(anchor_modes))
        if len(anchor_modes) == 1
        else ("mixed" if anchor_modes else None),
        "box_space": next(iter(box_spaces))
        if len(box_spaces) == 1
        else ("mixed" if box_spaces else None),
        "overall": metrics,
        "clips": clips,
        "scoring_rules": {
            "time_tolerance_s": TIME_TOLERANCE_S,
            "box": f"IoU >= {IOU_THRESHOLD} OR claim-box containment >= {CONTAINMENT_THRESHOLD}",
            "box_time": "box_grounded is evaluated against truth at box_t; box_grounded_at_midpoint preserves the former comparison definition",
            "supported": "well-formed AND time_grounded AND box_grounded",
            "headline": "supported_rate_unboxed; claims whose cited frame did not carry a drawn truth rectangle",
            "boxed_control": "supported_rate_boxed; echo-prone control claims citing an anchored frame",
            "echo_suspect": f"boxed-frame claim whose returned box matches the drawn rectangle within {ECHO_BOX_TOLERANCE_PX:g}px on all four sides",
            "box_sanity_guard": "declared-space conversion flags physically impossible or suspicious boxes as malformed",
            "truth_interpolation": f"adjacent samples only when separated by <= max({MIN_INTERPOLATION_GAP_S:g}s, {TRACKING_GAP_MULTIPLIER:g}x the truth track's median cadence)",
            "no_truth_at_time": "box_t lies inside a larger tracking gap; the claim is unsupported and counted as untracked_gap",
            "time_only": "time_grounded AND NOT box_grounded",
            "hollow": "missing/invalid time interval OR box is null/invalid",
            "fabricated": "conservative explicit keyword-class mismatch; evaluated only when human_note is non-null",
            "failed": "adapter error mechanically forces failed and discards any claims text",
            "observed": "missing truth is reported but excluded from grounding aggregates",
        },
    }


def render_markdown(report: dict) -> str:
    overall = report["overall"]

    def percent(value: float | None) -> str:
        return "—" if value is None else f"{value * 100:.1f}%"

    lines = [
        "# Film Room Evidence Bench Report",
        "",
        f"Generated: {report['generated_at']}",
        f"Adapter: `{report.get('adapter') or 'unspecified'}`",
        f"Anchor mode: `{report.get('anchor_mode') or 'none'}`",
        f"Box space: `{report.get('box_space') or 'unspecified'}`",
        "",
        "## Overall",
        "",
        "| Scored clips | Failed | Observed | Claims/clip | Box grounded @ box_t | Box grounded @ midpoint | **Supported unboxed (E1 headline)** | Supported boxed (control) | Echo suspects | Box guards | Untracked gap | Time-only | Unsupported | Hollow | Wall s/clip | Tokens/clip |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        "| {scored_clips} | {failed_clips} | {observed_clips} | {claims_per_clip} | {box_grounded} | {box_grounded_midpoint} | **{supported_unboxed}** | {supported_boxed} | {echo_suspect} | {box_guards} | {untracked_gap} | {time_only} | {unsupported} | {hollow} | {wall} | {tokens} |".format(
            scored_clips=overall["scored_clips"],
            failed_clips=overall["failed_clips"],
            observed_clips=overall["observed_clips"],
            claims_per_clip=overall["claims_per_clip"]
            if overall["claims_per_clip"] is not None
            else "—",
            box_grounded=percent(overall["box_grounded_rate"]),
            box_grounded_midpoint=percent(overall["box_grounded_at_midpoint_rate"]),
            supported_unboxed=percent(overall["supported_rate_unboxed"]),
            supported_boxed=percent(overall["supported_rate_boxed"]),
            echo_suspect=overall["echo_suspect_count"],
            box_guards=overall["box_sanity_guard_count"],
            untracked_gap=overall["untracked_gap"],
            time_only=percent(overall["time_only_rate"]),
            unsupported=percent(overall["unsupported_rate"]),
            hollow=percent(overall["hollow_rate"]),
            wall=overall["wall_s_per_clip"]
            if overall["wall_s_per_clip"] is not None
            else "—",
            tokens=overall["tokens_per_clip"]
            if overall["tokens_per_clip"] is not None
            else "—",
        ),
        "",
        "## Per clip",
        "",
        "| Clip | Status | Claims | Box grounded @ box_t | Box grounded @ midpoint | Supported unboxed | Supported boxed | Echo suspects | Box guards | Untracked gap | Time-only | Unsupported | Hollow | Fabricated | Wall s | Tokens |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for clip in report["clips"]:
        metrics = clip.get("metrics") or {}
        lines.append(
            "| {clip_id} | {status} | {count} | {box_grounded} | {box_grounded_midpoint} | {supported_unboxed} | {supported_boxed} | {echo_suspect} | {box_guards} | {untracked_gap} | {time_only} | {unsupported} | {hollow} | {fabricated} | {wall} | {tokens} |".format(
                clip_id=clip["clip_id"],
                status=clip["status"],
                count=metrics.get("claim_count", "—"),
                box_grounded=percent(metrics.get("box_grounded_rate")),
                box_grounded_midpoint=percent(
                    metrics.get("box_grounded_at_midpoint_rate")
                ),
                supported_unboxed=percent(metrics.get("supported_rate_unboxed")),
                supported_boxed=percent(metrics.get("supported_rate_boxed")),
                echo_suspect=metrics.get("echo_suspect_count", "—"),
                box_guards=metrics.get("box_sanity_guard_count", "—"),
                untracked_gap=metrics.get("untracked_gap", "—"),
                time_only=percent(metrics.get("time_only_rate")),
                unsupported=percent(metrics.get("unsupported_rate")),
                hollow=percent(metrics.get("hollow_rate")),
                fabricated=percent(metrics.get("fabricated_rate")),
                wall=clip.get("wall_s") if clip.get("wall_s") is not None else "—",
                tokens=clip.get("tokens") if clip.get("tokens") is not None else "—",
            )
        )
    lines.extend(
        [
            "",
            "## Scoring notes",
            "",
            f"- Time grounding requires the complete claim interval inside the truth window ± {TIME_TOLERANCE_S:.1f}s.",
            f"- Box grounding compares the returned box with the interpolated truth box at `box_t`; it requires IoU ≥ {IOU_THRESHOLD:.1f} or at least {CONTAINMENT_THRESHOLD * 100:.0f}% claim-box containment. `box_grounded_at_midpoint` reports the former definition for comparison.",
            f"- Truth boxes interpolate only across adjacent samples no more than max({MIN_INTERPOLATION_GAP_S:g}s, {TRACKING_GAP_MULTIPLIER:g}× median cadence) apart. A `box_t` inside a larger gap is `no_truth_at_time`, counted under `untracked_gap`, and unsupported.",
            "- `supported_rate_unboxed` is the E1 headline; it excludes claims citing images that carried a drawn truth rectangle.",
            "- `supported_rate_boxed` is the echo-prone control. `echo_suspect_count` flags returned boxes within 2px of the drawn rectangle on all sides.",
            "- `box_sanity_guard_count` counts declared-space boxes marked malformed because conversion made them physically impossible or exposed a likely normalized/pixel mismatch.",
            "- A malformed claim cannot be supported. A hollow claim lacks a valid time interval or box.",
            "- Fabrication is a deliberately conservative explicit keyword-class comparison and is omitted when `human_note` is null.",
            "- Mechanical adapter errors are `failed`; clips without truth are `observed` and excluded from grounding aggregates.",
            "",
        ]
    )
    return "\n".join(lines)


def write_report(report: dict, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "report.json"
    markdown_path = output_dir / "report.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    markdown_path.write_text(render_markdown(report))
    return json_path, markdown_path
