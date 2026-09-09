"""Explicit lexical activity checks against human notes, not a semantic judge."""

from __future__ import annotations

import re

try:
    from .semantic_contract import ACTION_TYPES
except ImportError:  # pragma: no cover
    from semantic_contract import ACTION_TYPES

# Keep finer note actions even when the model contract cannot express them.
# In particular, receiving, losing or heading a ball does not establish a carry.
ACTION_RULES = {
    "pass": r"\bpass(?:es|ed|ing)?\b",
    "carry": r"\b(?:carr(?:y|ies|ied|ying)|dribbl\w*)\b|\brunning with (?:the )?ball\b",
    "duel": r"\b(?:duels?|challeng\w*|tackl\w*)\b",
    "shot": r"\b(?:shots?|shoot\w*)\b",
    "defensive_action": r"\bintercept\w*\b",
    "header": r"\b(?:heads? the ball|headers?)\b",
    "receive": r"\breceiv\w*\b",
    "turn": r"\bhalf[ -]turn\b",
    "loss": r"\blos(?:e|es|ing|t) the ball\b",
    "cross": r"\bcross(?:es|ed|ing)?\b",
    "goalkeeping": r"\b(?:saves?|saved|saving)\b",
}
ACTIVITY_RULES = {
    "off_pitch": r"\b(?:sidelines?|warm[ -]?up|warming up|stretch\w*|walking off|coming off|hamstring)\b",
    "idle_on_pitch": r"\b(?:just walks? around|just walking around|waits?|waiting)\b|\bball doesn['’]t come\b",
    "defensive_track_back": r"\btrack(?:s|ed|ing)? back\b|\bwalking back on defense\b",
    "positional_only": r"\b(?:cent(?:er|re) back|touchline|stays wide)\b",
}
ON_BALL_TYPES = frozenset(ACTION_TYPES) - {"off_ball", "none", "unclear"}
HOLDING_BALL = re.compile(r"\bholding (?:the )?ball\b", re.I)


def hits(table: dict[str, str], text: str) -> set[str]:
    return {key for key, pattern in table.items() if re.search(pattern, text, re.I)}


def action_classes(text: str) -> set[str]:
    # A missed header is not affirmative evidence of heading the ball (MJ n22).
    text = re.sub(r"\bmiss(?:es|ed|ing)?\s+(?:a |the )?header\b", "", text, flags=re.I)
    return hits(ACTION_RULES, text)


def truth_activity(note: str | None) -> list[str]:
    if not note:
        return []
    activities = hits(ACTIVITY_RULES, note)
    activities.discard("positional_only")
    if action_classes(note):
        activities.add("on_ball_action")
    if not activities and "positional_only" in hits(ACTIVITY_RULES, note):
        activities.add("positional_only")
    return sorted(activities)


def sentence_verdict(note: str | None, sentence: str) -> str:
    """Require positive class overlap without an explicit incompatible assertion."""
    expected = set(truth_activity(note))
    if not expected:
        return "undetermined"
    expected_actions = action_classes(note or "")
    observed_actions = action_classes(sentence)
    observed = set(truth_activity(sentence))
    on_pitch = bool(re.search(r"\bon (?:the )?(?:field|pitch)\b", sentence, re.I))
    if "off_pitch" in expected:
        if observed_actions or (on_pitch and "off_pitch" not in observed):
            return "disagree"
    elif "off_pitch" in observed:
        return "disagree"
    if observed_actions - expected_actions:
        return "disagree"
    if HOLDING_BALL.search(sentence) and not HOLDING_BALL.search(note or ""):
        return "undetermined"  # Possession assertion without a matching note detail.
    if observed_actions & expected_actions or observed & expected:
        return "agree"
    return "undetermined"


def activity_metrics(read, truth: dict) -> dict:
    note = truth.get("human_note")
    expected = set(truth_activity(note))
    expected_actions = action_classes(note or "")
    event_types = {e.event_type for e in read.events}
    on_ball_events = event_types & ON_BALL_TYPES
    sentence_actions = action_classes(read.sentence)
    model = {
        "on_ball"
        if on_ball_events or sentence_actions or HOLDING_BALL.search(read.sentence)
        else "off_ball"
    }
    lenient_actions = expected_actions | (
        {"carry"} if expected_actions & {"receive", "turn", "loss"} else set()
    )
    if any(e.phase == "stoppage" for e in read.events):
        model.add("stoppage")
    if "off_pitch" in truth_activity(read.sentence):
        model.add("off_pitch")
    # Agreement is coarse activity compatibility, not event/outcome accuracy.
    agreement = None
    if expected:
        if "off_pitch" in expected:
            agreement = "on_ball" not in model and "off_pitch" in model
        elif "on_ball_action" in expected:
            agreement = "on_ball" in model
        else:
            agreement = "on_ball" not in model and "off_pitch" not in model
    return {
        "truth_activity": sorted(expected),
        "truth_action_classes": sorted(expected_actions),
        "unmapped_truth_action_classes": sorted(expected_actions - ON_BALL_TYPES),
        "model_activity": sorted(model),
        "model_on_ball_event_classes": sorted(on_ball_events),
        "matching_on_ball_event_classes": sorted(expected_actions & on_ball_events),
        "matching_on_ball_event_classes_lenient": sorted(
            lenient_actions & on_ball_events
        ),
        "no_on_ball_claimed_on_ball": bool(on_ball_events)
        if expected and "on_ball_action" not in expected
        else None,
        "off_pitch_claimed_on_ball": bool(on_ball_events)
        if "off_pitch" in expected
        else None,
        "idle_claimed_on_ball": bool(on_ball_events)
        if "idle_on_pitch" in expected
        else None,
        "on_ball_recalled": bool(expected_actions & on_ball_events)
        if "on_ball_action" in expected
        else None,
        "on_ball_recalled_lenient": bool(lenient_actions & on_ball_events)
        if "on_ball_action" in expected
        else None,
        "activity_agreement": agreement,
        "sentence_matches_note": sentence_verdict(note, read.sentence),
    }
