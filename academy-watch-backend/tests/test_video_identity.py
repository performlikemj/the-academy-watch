"""Tests for the video identity service (vote/chain rules proven in the Phase 0
spike) and the worker-artifact persistence + credit ledger flows."""

import pytest
from flask import Flask
from src.models.league import Team, db
from src.models.video import (
    VideoCreditLedger,
    VideoMatch,
    VideoRosterEntry,
    VideoTracklet,
)
from src.services.video_identity import (
    auto_bind,
    build_chains,
    persist_artifacts,
    vote_fragment,
)

# --------------------------------------------------------------------------- voting


class TestVoteFragment:
    def test_two_agreeing_reads_anchor(self):
        v = vote_fragment([{"jersey_number": 10}, {"jersey_number": 10}])
        assert v["anchored"] and v["jersey_number"] == 10 and v["confidence"] == "high"

    def test_single_read_is_weak_never_anchored(self):
        v = vote_fragment([{"jersey_number": 7}])
        assert not v["anchored"] and v["weak_number"] == 7

    def test_digit_doubling_supports_top_number(self):
        # OCR artifact: "44" on a #4 shirt must not rival 4
        v = vote_fragment([{"jersey_number": 4}, {"jersey_number": 4}, {"jersey_number": 44}])
        assert v["anchored"] and v["jersey_number"] == 4 and v["confidence"] == "high"

    def test_two_multiply_attested_numbers_refused_as_splice(self):
        reads = [{"jersey_number": n} for n in (10, 10, 14, 14, 14)]
        v = vote_fragment(reads)
        assert v["contaminated"] and not v["anchored"] and v["jersey_number"] is None

    def test_outvoted_rival_lowers_confidence(self):
        v = vote_fragment([{"jersey_number": 12}, {"jersey_number": 12}, {"jersey_number": 15}])
        assert v["anchored"] and v["jersey_number"] == 12 and v["confidence"] == "low"

    def test_role_votes_collected(self):
        v = vote_fragment([{"role": "not_a_player"}, {"role": "not_a_player"}, {"role": "outfield"}])
        assert v["role"] == "not_a_player" and not v["anchored"]

    def test_garbage_numbers_ignored(self):
        v = vote_fragment([{"jersey_number": 0}, {"jersey_number": 100}, {"jersey_number": True}])
        assert v["number_votes"] == {} and not v["anchored"]


# --------------------------------------------------------------------------- chains


def _frag(fid, team, first, last, visible):
    return {"entity_id": fid, "team": team, "first_s": first, "last_s": last, "visible_s": visible}


def _strong(number, confidence="high"):
    return vote_fragment([{"jersey_number": number}] * 2) | {"confidence": confidence}


class TestBuildChains:
    def test_disjoint_fragments_chain_by_number(self):
        frags = [_frag(1, 0, 0, 100, 90), _frag(2, 0, 200, 300, 80)]
        votes = {1: _strong(9), 2: _strong(9)}
        chains, conflicts = build_chains(votes, frags)
        assert len(chains) == 1
        assert chains[0]["player_key"] == "T0#9"
        assert chains[0]["member_fragment_ids"] == [1, 2]
        assert not conflicts

    def test_overlapping_same_number_is_conflict_not_merge(self):
        # one person cannot be in two places: physics check refuses the merge
        frags = [_frag(1, 0, 0, 100, 90), _frag(2, 0, 50, 150, 70)]
        votes = {1: _strong(9), 2: _strong(9)}
        chains, conflicts = build_chains(votes, frags)
        assert len(chains) == 1 and chains[0]["member_fragment_ids"] == [1]
        assert len(conflicts) == 1 and conflicts[0]["fragment_id"] == 2

    def test_same_number_different_teams_are_distinct_players(self):
        frags = [_frag(1, 0, 0, 100, 90), _frag(2, 1, 0, 100, 90)]
        votes = {1: _strong(10), 2: _strong(10)}
        chains, _ = build_chains(votes, frags)
        assert {c["player_key"] for c in chains} == {"T0#10", "T1#10"}

    def test_weak_fragment_joins_strong_chain(self):
        frags = [_frag(1, 0, 0, 100, 90), _frag(2, 0, 200, 250, 40)]
        votes = {1: _strong(4), 2: vote_fragment([{"jersey_number": 4}])}
        chains, _ = build_chains(votes, frags)
        assert chains[0]["member_fragment_ids"] == [1, 2]
        assert chains[0]["strong_fragment_ids"] == [1]

    def test_single_weak_read_never_names_a_player(self):
        frags = [_frag(1, 0, 0, 50, 40)]
        votes = {1: vote_fragment([{"jersey_number": 8}])}
        chains, _ = build_chains(votes, frags)
        assert chains == []

    def test_two_independent_weak_reads_may_seed_a_chain(self):
        frags = [_frag(1, 0, 0, 50, 40), _frag(2, 0, 100, 150, 40)]
        votes = {
            1: vote_fragment([{"jersey_number": 8}]),
            2: vote_fragment([{"jersey_number": 8}]),
        }
        chains, _ = build_chains(votes, frags)
        assert len(chains) == 1 and chains[0]["confidence"] == "low"

    def test_unlabeled_team_fragments_ignored(self):
        frags = [_frag(1, -1, 0, 100, 90)]
        votes = {1: _strong(5)}
        chains, _ = build_chains(votes, frags)
        assert chains == []


# --------------------------------------------------------------------------- persistence


@pytest.fixture
def video_app():
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def match(video_app):
    team = Team(team_id=1, name="Test FC", country="England", season=2026)
    db.session.add(team)
    db.session.flush()
    m = VideoMatch(team_id=team.id, status="processing", our_kit_color="red")
    db.session.add(m)
    db.session.add(VideoRosterEntry(video_match_id=1, player_name="John Smith", jersey_number=10))
    db.session.commit()
    return m


def _artifacts():
    return {
        "fragments": [
            _frag(1, 0, 0, 100, 90),
            _frag(2, 0, 200, 300, 80),
            _frag(3, 1, 0, 400, 200),
            _frag(4, 0, 500, 540, 35),  # leftover, no reads
            _frag(5, 0, 600, 610, 5),  # below MIN_FRAGMENT_VISIBLE_S — dropped
        ],
        "votes": {
            "entities": [
                {"entity_id": 1, **vote_fragment([{"jersey_number": 10}] * 3)},
                {"entity_id": 2, **vote_fragment([{"jersey_number": 10}] * 2)},
                {"entity_id": 3, **vote_fragment([{"jersey_number": 7}] * 2)},
            ]
        },
    }


class TestPersistArtifacts:
    def test_creates_chains_and_leftovers_and_flips_status(self, match):
        result = persist_artifacts(match, _artifacts())
        assert match.status == "needs_tagging"
        rows = db.session.query(VideoTracklet).all()
        kinds = {(t.pipeline_key, t.kind) for t in rows}
        assert ("T0#10", "chain") in kinds and ("T1#7", "chain") in kinds
        assert ("E4", "fragment") in kinds
        assert ("E5", "fragment") not in kinds  # too short for human time
        assert result["chains"] == 2

    def test_auto_bind_after_side_confirmation(self, match):
        persist_artifacts(match, _artifacts())
        match.our_team_cluster = 0
        db.session.commit()
        bound = auto_bind(match)
        assert bound == 1
        t = db.session.query(VideoTracklet).filter_by(pipeline_key="T0#10").one()
        entry = db.session.query(VideoRosterEntry).filter_by(jersey_number=10).one()
        assert t.roster_entry_id == entry.id and t.tag_source == "auto"
        # opposition #7 chain must NOT bind to our roster
        t7 = db.session.query(VideoTracklet).filter_by(pipeline_key="T1#7").one()
        assert t7.roster_entry_id is None

    def test_rerun_preserves_human_tags(self, match):
        persist_artifacts(match, _artifacts())
        entry = db.session.query(VideoRosterEntry).one()
        t = db.session.query(VideoTracklet).filter_by(pipeline_key="T0#10").one()
        t.roster_entry_id = entry.id
        t.tag_source = "human"
        db.session.commit()
        persist_artifacts(match, _artifacts())  # pipeline re-run
        t2 = db.session.query(VideoTracklet).filter_by(pipeline_key="T0#10").one()
        assert t2.id == t.id and t2.tag_source == "human"


class TestCreditLedger:
    def test_balance_sums_deltas(self, video_app):
        team = Team(team_id=2, name="Ledger FC", country="England", season=2026)
        db.session.add(team)
        db.session.flush()
        for delta, reason in ((5, "purchase"), (-1, "debit"), (1, "refund")):
            db.session.add(VideoCreditLedger(team_id=team.id, delta=delta, reason=reason))
        db.session.commit()
        assert VideoCreditLedger.balance(team.id) == 5
        assert VideoCreditLedger.balance(9999) == 0
