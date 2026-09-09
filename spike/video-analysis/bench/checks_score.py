"""Deterministic checks scoring; reasons never enter any correctness calculation."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

try:
    from .checks_contract import (
        BINARY_QUESTIONS,
        CONTRACT_VERSION,
        QUESTIONS,
        ChecksRead,
        parse_read,
    )
    from .checks_truth import TRUTH_VERSION, derive_truth
    from .provenance import thinking_rate
except ImportError:  # pragma: no cover
    from checks_contract import (
        BINARY_QUESTIONS,
        CONTRACT_VERSION,
        QUESTIONS,
        ChecksRead,
        parse_read,
    )
    from checks_truth import TRUTH_VERSION, derive_truth
    from provenance import thinking_rate

DENOMINATORS = (
    "Accuracy = correct / graded answered (unclear excluded). Abstain = unclear / eligible; "
    "coverage = graded answered / eligible. Binary eligibility requires yes/no truth. "
    "Kit eligibility follows lane A: uncertain kit truth forces abstention even for an asserted colour. "
    "False-yes = yes / truth-no cells; false-no = no / truth-yes cells, including abstentions in those truth denominators. "
    "Kit has no yes/no rates. Macro accuracy averages available accuracies across six questions; "
    "macro false-yes averages available rates across five binary questions; overall abstain is pooled over eligible cells. "
    "Gate 1 pools player_on_pitch and play_in_progress over off-pitch clips (14 cells on full set); "
    "Gate 2 uses player_touches_ball over off-pitch or idle clips with truth no (9 clips; mixed receive excluded). "
    "All metrics exclude failed reads; attempted/scored/failed counts remain visible. "
    "Thinking rate and wall/clip include all attempts. Reasons are logged only, never scored."
)
THRESHOLDS = {
    "off_pitch_false_yes_rate": {"operator": "<=", "threshold": 0.10},
    "off_pitch_idle_touch_false_yes_rate": {"operator": "<=", "threshold": 0.10},
    "macro_accuracy": {"operator": ">=", "threshold": 0.80},
    "abstain_rate": {"operator": "<=", "threshold": 0.40},
}


def ratio(n: int | float, d: int) -> float | None:
    return n / d if d else None


def mean(values) -> float | None:
    values = [v for v in values if v is not None]
    return ratio(sum(values), len(values))


def score_read(read: ChecksRead, truth: dict) -> dict:
    derived = derive_truth(truth)
    metrics = {}
    for q in QUESTIONS:
        response = getattr(read, q)
        expected = derived["expected"][q]
        eligible = (
            derived["kit_eligible"] if q == "kit_color_seen" else expected is not None
        )
        forced = q == "kit_color_seen" and derived["kit_uncertain"]
        abstain = eligible and (forced or response.answer == "unclear")
        answered = eligible and not abstain and expected is not None
        wrong = answered and response.answer != expected
        metrics[q] = {
            "truth": expected,
            "eligible": eligible,
            "answered": answered,
            "abstain": abstain,
            "correct": answered and not wrong,
            "false_yes": answered and expected == "no" and response.answer == "yes",
            "false_no": answered and expected == "yes" and response.answer == "no",
            "confident_wrong": wrong and response.confidence == "high",
        }
    return {"questions": metrics, "truth_activity": derived["truth_activity"]}


def score_clip(result: dict, truth: dict) -> dict:
    clip = {
        "clip_id": result["clip_id"],
        "status": "failed",
        "wall_s": result.get("wall_s", 0),
        "error": result.get("error"),
        "from_thinking": result.get("from_thinking") is True,
    }
    try:
        read = (
            parse_read(result["checks_raw"])
            if "checks_raw" in result
            else ChecksRead.model_validate(result.get("checks"))
        )
    except (ValidationError, TypeError):
        clip["error"] = clip["error"] or "checks schema validation failed"
        return clip
    if clip["error"]:
        return clip
    clip.update(
        status="scored", checks=read.model_dump(), metrics=score_read(read, truth)
    )
    return clip


def aggregate_question(cells: list[dict], *, binary=True) -> dict:
    eligible = [c for c in cells if c["eligible"]]
    count = len(eligible)
    answered = sum(c["answered"] for c in eligible)
    correct = sum(c["correct"] for c in eligible)
    abstain = sum(c["abstain"] for c in eligible)
    negative = sum(c["truth"] == "no" for c in eligible)
    positive = sum(c["truth"] == "yes" for c in eligible)
    false_yes = sum(c["false_yes"] for c in eligible)
    false_no = sum(c["false_no"] for c in eligible)
    return {
        "eligible_count": count,
        "answered_count": answered,
        "correct_count": correct,
        "abstain_count": abstain,
        "truth_no_count": negative,
        "truth_yes_count": positive,
        "false_yes_count": false_yes,
        "false_no_count": false_no,
        "accuracy": ratio(correct, answered),
        "abstain_rate": ratio(abstain, count),
        "coverage": ratio(answered, count),
        "false_yes_rate": ratio(false_yes, negative) if binary else None,
        "false_no_rate": ratio(false_no, positive) if binary else None,
        "confident_wrong_count": sum(c["confident_wrong"] for c in eligible),
    }


def threshold_results(overall: dict, *, complete: bool = True) -> dict:
    results = {}
    for key, rule in THRESHOLDS.items():
        value = overall[key]
        passed = (
            None
            if value is None or not complete
            else (
                value <= rule["threshold"]
                if rule["operator"] == "<="
                else value >= rule["threshold"]
            )
        )
        results[key] = {
            **rule,
            "value": value,
            "status": "WITHHELD" if passed is None else "PASS" if passed else "FAIL",
        }
    return results


def score_run(
    results: list[dict],
    truths: dict,
    *,
    adapter="qwen3vl_checks",
    truth_provenance: dict | None = None,
) -> dict:
    clips = [score_clip(r, truths[r["clip_id"]]) for r in results]
    scored = [c for c in clips if c["status"] == "scored"]
    questions = {
        q: aggregate_question(
            [c["metrics"]["questions"][q] for c in scored], binary=q in BINARY_QUESTIONS
        )
        for q in QUESTIONS
    }
    gate1 = [
        c["metrics"]["questions"][q]
        for c in scored
        if "off_pitch" in c["metrics"]["truth_activity"]
        for q in ("player_on_pitch", "play_in_progress")
    ]
    gate2 = [
        c["metrics"]["questions"]["player_touches_ball"]
        for c in scored
        if set(c["metrics"]["truth_activity"]) & {"off_pitch", "idle_on_pitch"}
        and c["metrics"]["questions"]["player_touches_ball"]["truth"] == "no"
    ]
    gates = {
        "off_pitch": aggregate_question(gate1),
        "off_pitch_idle_touch": aggregate_question(gate2),
    }
    overall = {
        "attempted_clips": len(clips),
        "scored_clips": len(scored),
        "failed_clips": len(clips) - len(scored),
        "questions": questions,
        "gates": gates,
        "off_pitch_false_yes_rate": gates["off_pitch"]["false_yes_rate"],
        "off_pitch_idle_touch_false_yes_rate": gates["off_pitch_idle_touch"][
            "false_yes_rate"
        ],
        "macro_accuracy": mean(q["accuracy"] for q in questions.values()),
        "macro_false_yes_rate": mean(
            questions[q]["false_yes_rate"] for q in BINARY_QUESTIONS
        ),
        "abstain_rate": ratio(
            sum(q["abstain_count"] for q in questions.values()),
            sum(q["eligible_count"] for q in questions.values()),
        ),
        "from_thinking_rate": thinking_rate(results),
        "wall_s_per_clip": ratio(sum(c["wall_s"] for c in clips), len(clips)),
    }
    return {
        "schema_version": "film-room-checks-report-v1",
        "contract_version": CONTRACT_VERSION,
        "truth_version": TRUTH_VERSION,
        **(truth_provenance or {}),
        "adapter": adapter,
        "denominators": DENOMINATORS,
        "overall": overall,
        "clips": clips,
    }


def write_report(report: dict, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n"
    )
    (output_dir / "report.md").write_text(
        DENOMINATORS
        + "\n\n```json\n"
        + json.dumps(report["overall"], indent=2)
        + "\n```\n"
    )
