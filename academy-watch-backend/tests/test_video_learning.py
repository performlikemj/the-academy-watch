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
        # one human split = one tombstone (the operation) + two low-conf chain segments
        _t(kind="tombstone", review_action="split", confidence="low"),
        _t(review_action="split", confidence="low"),  # segment — excluded from tallies
        _t(review_action="split", confidence="low"),  # segment — excluded from tallies
        _t(review_action=None),  # unreviewed
    ]
    a = match_accuracy(ts, _roster({1: 10, 2: 12}))
    # 6 chain rows (tombstone excluded); the 2 un-re-tagged split segments count as unreviewed
    assert a["chains_total"] == 6 and a["reviewed"] == 3 and a["unreviewed"] == 3
    assert a["confirmed"] == 1 and a["reassigned"] == 1 and a["dismissed"] == 1
    assert a["splits"] == 1  # one operation, not two segments
    # denominator = confirmed + reassigned + dismissed + splits = 4 (segments excluded)
    assert a["auto_tag_precision"] == round(1 / 4, 3)
    assert a["number_read_accuracy"] == 0.5  # 1 of 2 bound reviewed chains read the number correctly


def test_split_counts_once_and_segments_excluded_from_precision():
    # a lone split (tombstone + two segments) must count as ONE operation, and the two
    # machine-made segments must not enlarge the precision denominator.
    ts = [
        _t(review_action="confirmed", roster_entry_id=1, suggested_number=10),
        _t(kind="tombstone", review_action="split", confidence="low"),
        _t(review_action="split", confidence="low"),  # segment
        _t(review_action="split", confidence="low"),  # segment
    ]
    a = match_accuracy(ts, _roster({1: 10}))
    assert a["splits"] == 1
    # decided = confirmed(1) + split op(1) = 2 → 1/2, NOT 1/4 (if both segments counted)
    assert a["auto_tag_precision"] == 0.5


def test_recalibration_flags_overmerge_and_wrong_highconf():
    ts = [
        _t(kind="tombstone", review_action="split", confidence="low"),  # one split operation
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
