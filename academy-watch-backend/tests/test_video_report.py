"""Tests for the structured confidence-per-field player-report builder."""

import pytest
from flask import Flask
from src.models.league import db
from src.models.video import VideoTracklet
from src.services.video_report import (
    build_player_report,
    tracklet_number_votes,
    tracklet_to_bound,
)


@pytest.fixture
def report_app():
    app = Flask(__name__)
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:", SQLALCHEMY_TRACK_MODIFICATIONS=False)
    db.init_app(app)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def _bound(**kw):
    base = {
        "confidence": "high",
        "visible_s": 60.0,
        "first_s": 100.0,
        "last_s": 200.0,
        "tag_source": "auto",
        "contaminated": False,
        "number_votes": {"10": 3},
    }
    base.update(kw)
    return base


class TestIdentityGate:
    def test_human_tag_is_strongest(self):
        r = build_player_report(
            jersey_number=10,
            team_cluster=0,
            our_team_cluster=0,
            bound=[_bound(tag_source="human", confidence="low")],
            match_duration_s=2700,
        )
        assert r["identity"]["confidence"] == "human_confirmed"
        assert r["identity"]["source"] == "human"
        assert r["identity"]["human_reviewed"] is True

    def test_auto_high_clean_is_high(self):
        r = build_player_report(
            jersey_number=10,
            team_cluster=0,
            our_team_cluster=0,
            bound=[_bound(confidence="high", contaminated=False)],
            match_duration_s=2700,
        )
        assert r["identity"]["confidence"] == "high"

    def test_auto_low_is_low(self):
        r = build_player_report(
            jersey_number=10,
            team_cluster=0,
            our_team_cluster=0,
            bound=[_bound(confidence="low")],
            match_duration_s=2700,
        )
        assert r["identity"]["confidence"] == "low"

    def test_contamination_blocks_high_and_flags_splice(self):
        r = build_player_report(
            jersey_number=4,
            team_cluster=0,
            our_team_cluster=0,
            bound=[_bound(confidence="high", contaminated=True, number_votes={"4": 3, "10": 3})],
            match_duration_s=2700,
        )
        assert r["identity"]["confidence"] == "low"  # high blocked by contamination
        assert r["identity"]["splice_risk"] is True

    def test_human_overrides_even_with_contamination(self):
        r = build_player_report(
            jersey_number=4,
            team_cluster=0,
            our_team_cluster=0,
            bound=[_bound(tag_source="human", contaminated=True)],
            match_duration_s=2700,
        )
        assert r["identity"]["confidence"] == "human_confirmed"
        assert r["identity"]["splice_risk"] is True  # still surfaced

    def test_empty_bound_is_unverified(self):
        r = build_player_report(
            jersey_number=9,
            team_cluster=None,
            our_team_cluster=None,
            bound=[],
            match_duration_s=None,
        )
        assert r["identity"]["confidence"] == "unverified"
        assert r["coverage"]["confident_windows"] == 0
        assert r["coverage"]["pct_of_match"] is None


class TestCoverage:
    def test_minutes_windows_and_pct(self):
        r = build_player_report(
            jersey_number=10,
            team_cluster=0,
            our_team_cluster=0,
            bound=[_bound(visible_s=120, first_s=100, last_s=400), _bound(visible_s=60, first_s=800, last_s=900)],
            match_duration_s=2700,
        )
        cov = r["coverage"]
        assert cov["on_camera_min"] == 3.0
        assert cov["confident_windows"] == 2
        assert cov["pct_of_match"] == round(180 / 2700, 3)
        assert cov["span_s"] == [100.0, 900.0]

    def test_no_duration_means_no_pct(self):
        r = build_player_report(
            jersey_number=10,
            team_cluster=0,
            our_team_cluster=0,
            bound=[_bound()],
            match_duration_s=None,
        )
        assert r["coverage"]["pct_of_match"] is None


class TestTeamLabel:
    def test_ours_vs_opposition(self):
        ours = build_player_report(
            jersey_number=1, team_cluster=0, our_team_cluster=0, bound=[_bound()], match_duration_s=None
        )
        opp = build_player_report(
            jersey_number=1, team_cluster=1, our_team_cluster=0, bound=[_bound()], match_duration_s=None
        )
        assert ours["identity"]["team"] == "ours"
        assert opp["identity"]["team"] == "opposition"

    def test_unknown_side_is_none(self):
        r = build_player_report(
            jersey_number=1, team_cluster=None, our_team_cluster=None, bound=[_bound()], match_duration_s=None
        )
        assert r["identity"]["team"] is None


class TestMetrics:
    def test_minutes_is_real_rest_suppressed(self):
        r = build_player_report(
            jersey_number=10,
            team_cluster=0,
            our_team_cluster=0,
            bound=[_bound(visible_s=90)],
            match_duration_s=2700,
        )
        by_key = {m["key"]: m for m in r["metrics"]}
        assert by_key["minutes_on_camera"]["kind"] == "point"
        assert by_key["minutes_on_camera"]["confidence"] == "high"
        assert by_key["minutes_on_camera"]["value"] == 1.5
        # everything needing homography is structurally present but suppressed (never faked)
        for k in ("distance_m", "fastest_sustained_kmh", "sprint_count", "heatmap"):
            assert by_key[k]["suppressed"] is True
            assert by_key[k]["value"] is None
        assert by_key["touches"]["kind"] == "beta"

    def test_votes_aggregated_and_sorted(self):
        r = build_player_report(
            jersey_number=10,
            team_cluster=0,
            our_team_cluster=0,
            bound=[_bound(number_votes={"10": 4}), _bound(number_votes={"10": 2, "12": 1})],
            match_duration_s=2700,
        )
        votes = r["identity"]["votes"]
        assert votes["10"] == 6 and votes["12"] == 1
        assert list(votes.keys())[0] == "10"  # most-voted first


class TestVoteExtraction:
    def test_fragment_shape(self):
        assert dict(tracklet_number_votes({"number_votes": {"10": 2}})) == {"10": 2}

    def test_chain_shape(self):
        got = dict(tracklet_number_votes({"votes": {"1": {"10": 3}, "2": {"10": 1, "12": 1}}}))
        assert got == {"10": 4, "12": 1}

    def test_garbage_evidence_is_safe(self):
        assert dict(tracklet_number_votes(None)) == {}
        assert dict(tracklet_number_votes({"votes": "nope"})) == {}
        assert dict(tracklet_number_votes({"number_votes": {"x": "y"}})) == {}


class TestOrmBridge:
    """tracklet_to_bound must read real VideoTracklet rows (chain evidence shape)."""

    def test_chain_tracklet_round_trips_into_report(self, report_app):
        t = VideoTracklet(
            video_match_id=1,
            kind="chain",
            pipeline_key="T0#10",
            team_cluster=0,
            suggested_number=10,
            confidence="high",
            contaminated=False,
            first_s=120.0,
            last_s=480.0,
            visible_s=150.0,
            tag_source="auto",
            evidence={"member_fragment_ids": [1, 2], "votes": {"1": {"10": 4}, "2": {"10": 2, "12": 1}}},
        )
        db.session.add(t)
        db.session.commit()
        bound = tracklet_to_bound(t)
        assert bound["confidence"] == "high"
        assert bound["visible_s"] == 150.0
        assert bound["number_votes"] == {"10": 6, "12": 1}
        r = build_player_report(
            jersey_number=10,
            team_cluster=0,
            our_team_cluster=0,
            bound=[bound],
            match_duration_s=2700,
        )
        assert r["identity"]["confidence"] == "high"
        assert r["identity"]["votes"]["10"] == 6
        assert r["coverage"]["on_camera_min"] == 2.5
