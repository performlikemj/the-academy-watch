"""Tests for the human-correction -> training-label feedback builder.

build_feedback_labels is a pure projection over plain attribute reads, so these
use SimpleNamespace stubs — no Flask app or database needed.
"""

from types import SimpleNamespace

from src.services.video_feedback import build_feedback_labels


def _match(our=0, mid=4):
    return SimpleNamespace(id=mid, our_team_cluster=our)


def _tracklet(**kw):
    base = {
        "id": 1,
        "pipeline_key": "T0#10",
        "kind": "chain",
        "team_cluster": 0,
        "suggested_number": 10,
        "confidence": "high",
        "contaminated": False,
        "evidence": {"number_votes": {"10": 3}},
        "roster_entry_id": 57,
        "tag_source": "human",
        "dismissed": False,
        "reviewed_at": "2026-06-18",
        "review_action": "confirmed",
    }
    base.update(kw)
    return SimpleNamespace(**base)


def _roster(rid=57, num=10):
    return {rid: SimpleNamespace(id=rid, jersey_number=num)}


def _crops(_t):
    return [{"file": "e0867_00.jpg", "t": 12.3, "frame": 100, "laplacian_var": 900.0}]


def test_our_side_confirmed_yields_labeled_crops():
    rows = list(
        build_feedback_labels(
            match=_match(), tracklets=[_tracklet()], roster_by_id=_roster(), crops_for_tracklet=_crops
        )
    )
    assert len(rows) == 1
    r = rows[0]
    assert r["confirmed_number"] == 10
    assert r["side"] == "ours" and r["consent"] == "club_owned"
    assert r["source"] == "human" and r["label"] == "player"
    # the model's original prediction rides alongside the human truth
    assert r["original_suggested_number"] == 10
    assert r["original_number_votes"] == {"10": 3}
    assert r["crop_id"] == "e0867_00"


def test_auto_only_is_excluded():
    # an unreviewed auto-tag is the model's own guess, never exported as ground truth
    t = _tracklet(tag_source="auto", reviewed_at=None, review_action=None, dismissed=False)
    rows = list(build_feedback_labels(match=_match(), tracklets=[t], roster_by_id=_roster(), crops_for_tracklet=_crops))
    assert rows == []


def test_reviewed_at_without_action_is_not_ground_truth():
    # bind_tags no longer stamps reviewed_at without an action, but the exporter must
    # also refuse such a row defensively (gate on review_action, not reviewed_at).
    t = _tracklet(tag_source="auto", reviewed_at="2026-06-18", review_action=None, dismissed=False)
    rows = list(build_feedback_labels(match=_match(), tracklets=[t], roster_by_id=_roster(), crops_for_tracklet=_crops))
    assert rows == []


def test_opposition_consent_gate():
    t = _tracklet(team_cluster=1, roster_entry_id=None)  # opposition relative to our=0
    # default (side='ours') keeps opposition out of the corpus entirely
    assert (
        list(build_feedback_labels(match=_match(our=0), tracklets=[t], roster_by_id={}, crops_for_tracklet=_crops))
        == []
    )
    # side='all' includes it but tags the lack of consent
    rows = list(
        build_feedback_labels(
            match=_match(our=0), tracklets=[t], roster_by_id={}, crops_for_tracklet=_crops, side="all"
        )
    )
    assert len(rows) == 1
    assert rows[0]["side"] == "opposition"
    assert rows[0]["consent"] == "third_party_no_consent"
    assert rows[0]["confirmed_number"] is None


def test_dismissed_is_not_a_player_negative():
    t = _tracklet(dismissed=True, roster_entry_id=None, review_action="dismissed")
    rows = list(build_feedback_labels(match=_match(), tracklets=[t], roster_by_id=_roster(), crops_for_tracklet=_crops))
    assert len(rows) == 1
    assert rows[0]["label"] == "not_a_player"
    assert rows[0]["confirmed_number"] is None
