"""Deterministic checks scoring; reasons never enter any correctness calculation."""

from __future__ import annotations

import json
from collections import Counter
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
    "Modal answer/share uses every valid answer, including unclear and ungraded cells; ties sort lexically. "
    "Majority baseline uses all selected graded truth classes (uncertain kit excluded), independent of abstention; "
    "information requires modal share <90% and accuracy > baseline +5 percentage points. "
    "Gate 1 also splits its two questions. Gate 2 requires false-yes <=10% AND measurable touch recall >=50%. "
    "Raw recall = yes / all selected truth-positive clips, counting unclear/failed reads as misses. "
    "Touch recall is null when mean spacing >1s or sampling metadata is missing; raw counts remain. "
    "Accuracy metrics exclude failed reads; attempted/scored/failed counts remain visible. "
    "Thinking rate and wall/clip include all attempts. Reasons are logged only, never scored."
)
THRESHOLDS = {
    "off_pitch_false_yes_rate": {"operator": "<=", "threshold": 0.10},
    "off_pitch_idle_touch_false_yes_rate": {"operator": "<=", "threshold": 0.10},
    "touch_recall": {"operator": ">=", "threshold": 0.50},
    "macro_accuracy": {"operator": ">=", "threshold": 0.80},
    "abstain_rate": {"operator": "<=", "threshold": 0.40},
}

SAMPLING_REASON = "not measurable at this sampling: mean frame spacing exceeds 1.0 s"


def sampling_metrics(results: list[dict], truths: dict) -> dict:
    """Use distinct instants, not crop/context image counts or requested interval."""
    clips = []
    for result in results:
        window = truths[result["clip_id"]].get("window", {})
        duration = window.get("end_s", 0) - window.get("start_s", 0)
        timestamps = {f["t"] for f in result.get("sent_frames", []) if "t" in f}
        count = len(timestamps)
        known = duration > 0 and count > 0
        clips.append(
            {
                "clip_id": result["clip_id"],
                "window_s": duration if duration > 0 else None,
                "distinct_frames": count,
                "frames_per_second_of_window": count / duration if known else None,
                "mean_spacing_s": duration / max(count - 1, 1) if known else None,
            }
        )
    fps = [c["frames_per_second_of_window"] for c in clips]
    spacing = mean(c["mean_spacing_s"] for c in clips)
    complete = bool(clips) and all(v is not None for v in fps)
    reason = (
        "not measurable at this sampling: missing window or sampled timestamps"
        if not complete
        else SAMPLING_REASON
        if spacing > 1.0
        else None
    )
    return {
        "frames_per_second_of_window": {
            "mean": mean(fps),
            "min": min((v for v in fps if v is not None), default=None),
        },
        "mean_spacing_s": spacing,
        "touch_recall_reason": reason,
        "definition": "N distinct timestamps / full window seconds; spacing = window / (N-1), or full window for one frame; unweighted means over clips. Missing geometry withholds recall. Passing this check does not prove a touch was sampled.",
        "clips": clips,
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
    parts = [
        results[k]["status"]
        for k in ("off_pitch_idle_touch_false_yes_rate", "touch_recall")
    ]
    results["gate2"] = {
        "operator": "AND",
        "threshold": None,
        "value": None,
        "status": "WITHHELD"
        if "WITHHELD" in parts
        else "PASS"
        if all(p == "PASS" for p in parts)
        else "FAIL",
        "reason": overall.get("touch_recall_reason"),
        "requires": "touch false-yes <=10% AND measurable touch recall >=50%",
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
    sampling = sampling_metrics(results, truths)
    questions = {
        q: aggregate_question(
            [c["metrics"]["questions"][q] for c in scored], binary=q in BINARY_QUESTIONS
        )
        for q in QUESTIONS
    }
    derived = [derive_truth(truths[r["clip_id"]]) for r in results]
    for q, metric in questions.items():
        answers = Counter(c["checks"][q]["answer"] for c in scored)
        modal = min(answers, key=lambda a: (-answers[a], a)) if answers else None
        expected = Counter(
            t["expected"][q] for t in derived if t["expected"][q] is not None
        )
        baseline = ratio(max(expected.values(), default=0), sum(expected.values()))
        share = ratio(answers[modal], sum(answers.values())) if modal else None
        accuracy = metric["accuracy"]
        hits = sum(
            c["checks"][q]["answer"] == "yes"
            and c["metrics"]["questions"][q]["truth"] == "yes"
            for c in scored
        )
        raw_recall = ratio(hits, expected["yes"]) if q in BINARY_QUESTIONS else None
        reason = sampling["touch_recall_reason"] if q == "player_touches_ball" else None
        metric.update(
            modal_answer=modal,
            modal_answer_share=share,
            answer_count=sum(answers.values()),
            answer_distribution=dict(sorted(answers.items())),
            majority_baseline_accuracy=baseline,
            majority_truth_count=max(expected.values(), default=0),
            graded_truth_count=sum(expected.values()),
            accuracy_minus_baseline=accuracy - baseline
            if accuracy is not None and baseline is not None
            else None,
            information=bool(
                share is not None
                and share < 0.9
                and accuracy is not None
                and baseline is not None
                and accuracy > baseline + 0.05
            ),
            true_positive_count=hits if q in BINARY_QUESTIONS else None,
            recall_truth_positive_count=expected["yes"]
            if q in BINARY_QUESTIONS
            else None,
            raw_recall=raw_recall,
            recall=None if reason else raw_recall,
            recall_reason=reason,
        )
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
        **{
            f"off_pitch_{q}": aggregate_question(
                [
                    c["metrics"]["questions"][q]
                    for c in scored
                    if "off_pitch" in c["metrics"]["truth_activity"]
                ]
            )
            for q in ("player_on_pitch", "play_in_progress")
        },
        "off_pitch": aggregate_question(gate1),
        "off_pitch_idle_touch": aggregate_question(gate2),
    }
    overall = {
        "attempted_clips": len(clips),
        "scored_clips": len(scored),
        "failed_clips": len(clips) - len(scored),
        "questions": questions,
        "gates": gates,
        "sampling": sampling,
        "frames_per_second_of_window": sampling["frames_per_second_of_window"],
        "touch_recall": questions["player_touches_ball"]["recall"],
        "touch_recall_raw": questions["player_touches_ball"]["raw_recall"],
        "touch_recall_reason": sampling["touch_recall_reason"],
        "touch_yes_count": questions["player_touches_ball"]["true_positive_count"],
        "touch_truth_positive_count": questions["player_touches_ball"][
            "recall_truth_positive_count"
        ],
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
        "schema_version": "film-room-checks-report-v2",
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
