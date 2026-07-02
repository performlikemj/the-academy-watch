"""Tests for the learning loop — accuracy, recalibration, training manifest (pure)."""

from types import SimpleNamespace

from src.services.video_learning import match_accuracy, recalibration_signals, training_manifest


def _t(**kw):
    base = {
        "kind": "chain",
        "review_action": None,
        "roster_entry_id": None,
        "suggested_number": 10,
        "confidence": "high",
    }
    base.update(kw)
    return SimpleNamespace(**base)


def _roster(d):
    return {k: SimpleNamespace(jersey_number=v) for k, v in d.items()}


def test_match_accuracy():
    ts = [
        _t(review_action="confirmed", roster_entry_id=1, suggested_number=10),  # number matches roster → correct
        _t(review_action="reassigned", roster_entry_id=2, suggested_number=7),  # model said 7, human 12 → wrong
        _t(review_action="dismissed"),
        _t(review_action="split"),
        _t(review_action=None),  # unreviewed
    ]
    a = match_accuracy(ts, _roster({1: 10, 2: 12}))
    assert a["chains_total"] == 5 and a["reviewed"] == 4 and a["unreviewed"] == 1
    assert a["confirmed"] == 1 and a["reassigned"] == 1 and a["dismissed"] == 1 and a["splits"] == 1
    assert a["auto_tag_precision"] == round(1 / 4, 3)
    assert a["number_read_accuracy"] == 0.5  # 1 of 2 bound reviewed chains read the number correctly


def test_recalibration_flags_overmerge_and_wrong_highconf():
    ts = [
        _t(review_action="split"),
        _t(review_action="dismissed"),
        _t(review_action="reassigned", confidence="high"),
        _t(review_action="reassigned", confidence="high"),
        _t(review_action="confirmed", confidence="high"),
    ]
    r = recalibration_signals(ts)
    assert r["splits"] == 1 and r["dismissed"] == 1
    assert any("over-merge" in s for s in r["suggestions"])
    assert any("High-confidence" in s for s in r["suggestions"])  # 2 wrong / 3 high = 67% > 30%


def test_training_manifest_consent_gate():
    rows = [
        {
            "file": "e1.jpg",
            "label": "player",
            "confirmed_number": 10,
            "consent": "club_owned",
            "side": "ours",
            "match_id": 4,
            "contaminated": False,
        },
        {
            "file": "e2.jpg",
            "label": "player",
            "confirmed_number": 7,
            "consent": "third_party_no_consent",
            "side": "opposition",
            "match_id": 4,
            "contaminated": False,
        },
        {
            "file": "e3.jpg",
            "label": "not_a_player",
            "confirmed_number": None,
            "consent": "club_owned",
            "side": "ours",
            "match_id": 4,
            "contaminated": False,
        },
        {
            "file": "e4.jpg",
            "label": "player",
            "confirmed_number": 10,
            "consent": "club_owned",
            "side": "ours",
            "match_id": 4,
            "contaminated": True,
        },
    ]
    m = training_manifest(rows)
    assert m["n_reader_examples"] == 1  # only e1 (e2 no consent, e4 contaminated)
    assert m["n_negatives"] == 1  # e3
    assert m["n_reid_identities"] == 1  # 4:ours:10
