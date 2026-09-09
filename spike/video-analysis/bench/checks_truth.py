"""MJ's explicit note-derived rule table, with directive exceptions disclosed."""

import re

try:
    from .checks_contract import QUESTIONS
    from .identity_truth import kit_truth
    from .semantic_activity import truth_activity
except ImportError:  # pragma: no cover
    from checks_contract import QUESTIONS
    from identity_truth import kit_truth
    from semantic_activity import truth_activity

TRUTH_VERSION = "film-room-checks-truth-v1"
RULE_TABLE = {
    "player_on_pitch": "off_pitch=no; other classified=yes; unclassified (n24)=ungraded",
    "play_in_progress": "off_pitch=no; on_ball_action/defensive_track_back/positional_only=yes; idle throw-in (n04-307417)=no; other idle (n10)=ungraded; mixed receive (n04-243433)=yes",
    "ball_near_player": "off_pitch=no; on_ball_action=yes; other idle=no; defensive/positional/unclassified=ungraded",
    "player_touches_ball": "off_pitch=no; on_ball_action=yes (including mixed n04-243433); other idle=no; defensive/positional/unclassified=ungraded",
    "player_running": "off_pitch or non-on-ball walk/stand=no; mixed receive/walking n04-243433=ungraded; run/track back/goes or went forward/challenge=yes; n17-416826=yes by explicit directive override; other=ungraded",
    "kit_color_seen": "identity_truth.kit_truth: uncertainty takes precedence and counts as abstention; verified override restores colour independently of disputed label; unavailable disputed colour=ungraded",
}
RUNNING_YES = re.compile(
    r"\b(?:run(?:s|ning)?|track(?:s|ed|ing)? back|(?:goes|went) forward|challeng\w*)\b",
    re.I,
)
RUNNING_NO = re.compile(r"\b(?:walk\w*|stand\w*|sidelines?|stretch\w*)\b", re.I)
# This note has no running phrase. MJ's lane-B directive explicitly grades it yes.
RUNNING_DIRECTIVE = {
    "m04-n17-t717-416826-418915": "receives ball in midfield. playing as false 9 or 10 spot. loses the ball"
}


def derive_truth(truth: dict) -> dict:
    note = truth.get("human_note") or ""
    activity = truth_activity(note)
    expected = dict.fromkeys(QUESTIONS)
    sources = dict.fromkeys(QUESTIONS, "ungraded: no explicit rule")
    off = "off_pitch" in activity
    on_ball = "on_ball_action" in activity
    idle = "idle_on_pitch" in activity
    if activity:
        expected["player_on_pitch"] = "no" if off else "yes"
        if off:
            for q in ("play_in_progress", "ball_near_player", "player_touches_ball"):
                expected[q] = "no"
        else:
            if on_ball or set(activity) & {"defensive_track_back", "positional_only"}:
                expected["play_in_progress"] = "yes"
            elif idle and re.search(r"throw[ -]in", note, re.I):
                expected["play_in_progress"] = "no"
            if on_ball or idle:
                for q in ("ball_near_player", "player_touches_ball"):
                    expected[q] = "yes" if on_ball else "no"
        if off or (not on_ball and RUNNING_NO.search(note)):
            expected["player_running"] = "no"
        elif RUNNING_YES.search(note):
            expected["player_running"] = "yes"
    cid = truth.get("clip_id")
    if cid in RUNNING_DIRECTIVE and note == RUNNING_DIRECTIVE[cid]:
        expected["player_running"] = "yes"
        sources["player_running"] = (
            "explicit MJ lane-B directive override, not a running keyword"
        )
    kit = kit_truth(truth)
    expected["kit_color_seen"] = kit["color"]
    for q, value in expected.items():
        if value is not None and sources[q].startswith("ungraded"):
            sources[q] = RULE_TABLE[q]
    if kit["uncertain"]:
        sources["kit_color_seen"] = (
            "uncertain kit truth: forced abstention (lane A policy)"
        )
    return {
        "expected": expected,
        "sources": sources,
        "truth_activity": activity,
        "kit_uncertain": kit["uncertain"],
        "kit_eligible": kit["eligible"]
        and (kit["color"] is not None or kit["uncertain"]),
    }
