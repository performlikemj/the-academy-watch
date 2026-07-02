"""Tests for player_pulse_service — deterministic newsworthiness scoring.

Covers: each signal contributes as documented (stat deltas, milestones, status
change, level jump, per-90 spike, opt-in injuries), the total weighted sum,
scoring determinism, upsert idempotence, dry-run writes nothing, the injury
signal stays OFF unless an api_client is explicitly passed, and the followed-
player enumeration dedups a player across watchlist + follow list.

Exercises the service directly (no HTTP): the admin endpoints are Builder B's.
"""

from datetime import date, datetime

import pytest
from flask import Flask
from src.models.follow import Follow, FollowList
from src.models.journey import PlayerJourney, PlayerJourneyEntry
from src.models.league import League, PlayerStatsCache, Team, db
from src.models.pulse import PlayerPulse
from src.models.scout_watchlist import ScoutWatchlistEntry
from src.models.tracked_player import TrackedPlayer
from src.models.weekly import Fixture, FixturePlayerStats
from src.services import player_pulse_service as pulse

WINDOW_END = date(2025, 9, 8)  # window covers 2025-09-02 .. 2025-09-08


@pytest.fixture
def app():
    flask_app = Flask(__name__)
    flask_app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret-key",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(flask_app)
    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def seeded(app):
    """A parent academy + loan club and a handful of tracked players with
    fixtures shaped for each signal."""
    league = League(league_id=39, name="Premier League", country="England", season=2025, is_european_top_league=True)
    db.session.add(league)
    db.session.flush()
    parent = Team(team_id=33, name="Manchester United", country="England", season=2025, league_id=league.id)
    loan_club = Team(team_id=901, name="Rio FC", country="Brazil", season=2025, league_id=league.id)
    db.session.add_all([parent, loan_club])
    db.session.flush()

    # 1001: in-form loan striker (stat deltas + form spike, no milestones)
    striker = TrackedPlayer(
        player_api_id=1001,
        player_name="Alfie Striker",
        position="Attacker",
        team_id=parent.id,
        status="on_loan",
        current_club_api_id=901,
        current_club_name="Rio FC",
        current_club_db_id=loan_club.id,
        data_depth="full_stats",
        is_active=True,
    )
    # 1003: keeper, first_team, no fixtures (used for status-change + injury tests)
    keeper = TrackedPlayer(
        player_api_id=1003,
        player_name="Charlie Gloves",
        position="Goalkeeper",
        team_id=parent.id,
        status="first_team",
        data_depth="full_stats",
        is_active=True,
    )
    db.session.add_all([striker, keeper])
    db.session.flush()

    # Baseline fixtures BEFORE the window for 1001 (so debut/first-goal never fire)
    _add_stats(_fixture(datetime(2025, 8, 10), 901), 1001, 901, minutes=90, goals=1)
    _add_stats(_fixture(datetime(2025, 8, 17), 901), 1001, 901, minutes=90, assists=1)
    _add_stats(_fixture(datetime(2025, 8, 24), 901), 1001, 901, minutes=90)
    # Window fixtures for 1001: 3 goals, 1 assist, 2 apps, 170 mins
    _add_stats(_fixture(datetime(2025, 9, 3), 901), 1001, 901, minutes=90, goals=2, assists=1)
    _add_stats(_fixture(datetime(2025, 9, 6), 901), 1001, 901, minutes=80, goals=1)
    db.session.commit()
    return {"parent": parent, "loan_club": loan_club}


_FIXTURE_SEQ = [0]


def _fixture(when: datetime, home_api_id: int) -> Fixture:
    _FIXTURE_SEQ[0] += 1
    fx = Fixture(fixture_id_api=_FIXTURE_SEQ[0], season=2025, home_team_api_id=home_api_id, date_utc=when)
    db.session.add(fx)
    db.session.flush()
    return fx


def _add_stats(fx, player_api_id, team_api_id, *, minutes=0, goals=0, assists=0, substitute=False):
    db.session.add(
        FixturePlayerStats(
            fixture_id=fx.id,
            player_api_id=player_api_id,
            team_api_id=team_api_id,
            minutes=minutes,
            goals=goals,
            assists=assists,
            substitute=substitute,
        )
    )


def _seed_prev_pulse(pid, context, window_end=date(2025, 9, 1), score=0.0):
    db.session.add(
        PlayerPulse(
            player_api_id=pid,
            window_end=window_end,
            score=score,
            delta_json={"context": context, "signals": {}, "window_totals": {}, "score": score},
        )
    )
    db.session.commit()


class _InjuryClient:
    def __init__(self, count):
        self._count = count

    def get_player_injuries(self, player_id, season=None):
        return [{"n": i} for i in range(self._count)]


# --------------------------------------------------------------------------- #
# Stat-delta signals + total weighted sum
# --------------------------------------------------------------------------- #


class TestStatDeltas:
    def test_in_form_striker_scores_all_stat_signals(self, seeded):
        result = pulse.compute_pulse(WINDOW_END, player_api_ids=[1001])
        row = PlayerPulse.query.filter_by(player_api_id=1001, window_end=WINDOW_END).one()
        signals = row.delta_json["signals"]
        assert set(signals) == {"goals", "assists", "appearances", "minutes", "per90_spike"}
        assert signals["goals"]["value"] == 3
        assert signals["goals"]["points"] == 6.0
        assert signals["assists"]["value"] == 1
        assert signals["assists"]["points"] == 1.5
        assert signals["appearances"]["value"] == 2
        assert signals["minutes"]["value"] == 170
        # 6.0 + 1.5 + 1.0 + (170/90*0.5) + 2.0 (spike) = 11.44
        assert row.score == 11.44
        assert result["scored"] == 1
        assert result["top"][0]["player_api_id"] == 1001

    def test_window_totals_and_context_are_provenance(self, seeded):
        pulse.compute_pulse(WINDOW_END, player_api_ids=[1001])
        row = PlayerPulse.query.filter_by(player_api_id=1001, window_end=WINDOW_END).one()
        assert row.delta_json["window_totals"] == {
            "appearances": 2,
            "goals": 3,
            "assists": 1,
            "minutes": 170,
            "starts": 2,
        }
        ctx = row.delta_json["context"]
        assert ctx["name"] == "Alfie Striker"
        assert ctx["status"] == "on_loan"
        assert ctx["current_club"] == "Rio FC"

    def test_quiet_player_scores_zero(self, seeded):
        # keeper 1003 has no fixtures and no prior pulse → nothing fires
        pulse.compute_pulse(WINDOW_END, player_api_ids=[1003])
        row = PlayerPulse.query.filter_by(player_api_id=1003, window_end=WINDOW_END).one()
        assert row.score == 0.0
        assert row.delta_json["signals"] == {}


# --------------------------------------------------------------------------- #
# Milestones
# --------------------------------------------------------------------------- #


class TestMilestones:
    def _add_newbie(self, seeded, player_api_id=1002):
        newbie = TrackedPlayer(
            player_api_id=player_api_id,
            player_name="Debut Kid",
            position="Midfielder",
            team_id=seeded["parent"].id,
            status="academy",
            current_club_api_id=901,
            current_club_name="Rio FC",
            data_depth="full_stats",
            is_active=True,
        )
        db.session.add(newbie)
        db.session.flush()
        _add_stats(_fixture(datetime(2025, 9, 3), 901), player_api_id, 901, minutes=90, goals=1, substitute=False)
        db.session.commit()

    def _add_journey(self, player_api_id, entries=()):
        journey = PlayerJourney(player_api_id=player_api_id, player_name="Debut Kid")
        db.session.add(journey)
        db.session.flush()
        for e in entries:
            db.session.add(PlayerJourneyEntry(journey_id=journey.id, **e))
        db.session.commit()
        return journey

    def test_debut_first_goal_first_start(self, seeded):
        # Genuine academy debutant: journey exists and shows NO senior history
        # (only youth apps), so the fuller-career check corroborates the firsts.
        self._add_newbie(seeded)
        self._add_journey(
            1002,
            entries=[
                {
                    "season": 2024,
                    "club_api_id": 33,
                    "level": "U21",
                    "entry_type": "academy",
                    "is_youth": True,
                    "appearances": 20,
                    "goals": 6,
                }
            ],
        )

        pulse.compute_pulse(WINDOW_END, player_api_ids=[1002])
        signals = PlayerPulse.query.filter_by(player_api_id=1002, window_end=WINDOW_END).one().delta_json["signals"]
        assert signals["milestone_debut"]["points"] == 4.0
        assert signals["milestone_first_goal"]["points"] == 3.5
        assert signals["milestone_first_start"]["points"] == 2.5

    def test_no_milestone_without_career_corroboration(self, seeded):
        # FixturePlayerStats-before is empty but there is NO career record to
        # confirm this is a first (e.g. rollout ingestion) → stay silent rather
        # than fabricate a debut/first-goal/first-start.
        self._add_newbie(seeded, player_api_id=1010)
        pulse.compute_pulse(WINDOW_END, player_api_ids=[1010])
        signals = PlayerPulse.query.filter_by(player_api_id=1010, window_end=WINDOW_END).one().delta_json["signals"]
        assert "milestone_debut" not in signals
        assert "milestone_first_goal" not in signals
        assert "milestone_first_start" not in signals

    def test_no_debut_when_prior_senior_history_in_journey(self, seeded):
        # 27-year-old signing into a covered league from an UNCOVERED one: no
        # FixturePlayerStats before the window, but the journey shows a long
        # senior career → no fabricated debut / first goal / first start.
        self._add_newbie(seeded, player_api_id=1011)
        self._add_journey(
            1011,
            entries=[
                {
                    "season": 2023,
                    "club_api_id": 5000,
                    "level": "First Team",
                    "entry_type": "first_team",
                    "is_youth": False,
                    "appearances": 120,
                    "goals": 40,
                }
            ],
        )
        pulse.compute_pulse(WINDOW_END, player_api_ids=[1011])
        signals = PlayerPulse.query.filter_by(player_api_id=1011, window_end=WINDOW_END).one().delta_json["signals"]
        assert "milestone_debut" not in signals
        assert "milestone_first_goal" not in signals
        assert "milestone_first_start" not in signals

    def test_no_first_goal_when_prior_senior_goals_in_stats_cache(self, seeded):
        # Prior senior goals live in PlayerStatsCache (lower-league coverage), so
        # a covered-league goal this window is NOT his first senior goal. The
        # debut is likewise suppressed (cache shows prior senior appearances).
        self._add_newbie(seeded, player_api_id=1012)
        self._add_journey(1012)  # journey present but sparse; cache carries history
        db.session.add(PlayerStatsCache(player_api_id=1012, team_api_id=7000, season=2024, appearances=30, goals=9))
        db.session.commit()
        pulse.compute_pulse(WINDOW_END, player_api_ids=[1012])
        signals = PlayerPulse.query.filter_by(player_api_id=1012, window_end=WINDOW_END).one().delta_json["signals"]
        assert "milestone_first_goal" not in signals
        assert "milestone_debut" not in signals

    def test_no_debut_when_prior_appearances_exist(self, seeded):
        # 1001 has August fixtures → no debut / first-goal milestone in the window
        pulse.compute_pulse(WINDOW_END, player_api_ids=[1001])
        signals = PlayerPulse.query.filter_by(player_api_id=1001, window_end=WINDOW_END).one().delta_json["signals"]
        assert "milestone_debut" not in signals
        assert "milestone_first_goal" not in signals


# --------------------------------------------------------------------------- #
# Status change + level jump (vs prior window)
# --------------------------------------------------------------------------- #


class TestStatusAndLevel:
    def test_status_change_fires_against_prior_window(self, seeded):
        _seed_prev_pulse(1003, {"status": "on_loan", "current_level": None})
        pulse.compute_pulse(WINDOW_END, player_api_ids=[1003])
        signals = PlayerPulse.query.filter_by(player_api_id=1003, window_end=WINDOW_END).one().delta_json["signals"]
        assert signals["status_change"]["from_status"] == "on_loan"
        assert signals["status_change"]["to_status"] == "first_team"
        assert signals["status_change"]["label"] == "Promoted to first team"
        assert signals["status_change"]["points"] == 3.5

    def test_no_status_change_without_prior_window(self, seeded):
        pulse.compute_pulse(WINDOW_END, player_api_ids=[1003])
        signals = PlayerPulse.query.filter_by(player_api_id=1003, window_end=WINDOW_END).one().delta_json["signals"]
        assert "status_change" not in signals

    def test_level_jump_fires(self, seeded):
        prospect = TrackedPlayer(
            player_api_id=1004,
            player_name="Riser",
            position="Defender",
            team_id=seeded["parent"].id,
            status="academy",
            current_level="Senior",
            data_depth="full_stats",
            is_active=True,
        )
        db.session.add(prospect)
        db.session.commit()
        _seed_prev_pulse(1004, {"status": "academy", "current_level": "U21"})
        pulse.compute_pulse(WINDOW_END, player_api_ids=[1004])
        signals = PlayerPulse.query.filter_by(player_api_id=1004, window_end=WINDOW_END).one().delta_json["signals"]
        assert signals["milestone_level_jump"]["from_level"] == "U21"
        assert signals["milestone_level_jump"]["to_level"] == "Senior"
        assert signals["milestone_level_jump"]["points"] == 3.5

    def test_journey_current_status_overrides_tracked_status(self, seeded):
        db.session.add(PlayerJourney(player_api_id=1003, current_status="sold"))
        db.session.commit()
        pulse.compute_pulse(WINDOW_END, player_api_ids=[1003])
        ctx = PlayerPulse.query.filter_by(player_api_id=1003, window_end=WINDOW_END).one().delta_json["context"]
        assert ctx["status"] == "sold"


# --------------------------------------------------------------------------- #
# Per-90 spike
# --------------------------------------------------------------------------- #


class TestPer90Spike:
    def test_spike_present_for_in_form_striker(self, seeded):
        pulse.compute_pulse(WINDOW_END, player_api_ids=[1001])
        signals = PlayerPulse.query.filter_by(player_api_id=1001, window_end=WINDOW_END).one().delta_json["signals"]
        assert "per90_spike" in signals
        assert signals["per90_spike"]["points"] == 2.0
        assert signals["per90_spike"]["baseline_per90"] > 0

    def test_no_spike_without_baseline_minutes(self, seeded):
        # Fresh player with only window minutes → baseline below the gate
        p = TrackedPlayer(
            player_api_id=1006,
            player_name="No Base",
            position="Attacker",
            team_id=seeded["parent"].id,
            status="on_loan",
            current_club_api_id=901,
            current_club_name="Rio FC",
            data_depth="full_stats",
            is_active=True,
        )
        db.session.add(p)
        db.session.flush()
        _add_stats(_fixture(datetime(2025, 9, 4), 901), 1006, 901, minutes=90, goals=1)
        db.session.commit()
        pulse.compute_pulse(WINDOW_END, player_api_ids=[1006])
        signals = PlayerPulse.query.filter_by(player_api_id=1006, window_end=WINDOW_END).one().delta_json["signals"]
        assert "per90_spike" not in signals


# --------------------------------------------------------------------------- #
# Injury (opt-in only)
# --------------------------------------------------------------------------- #


class TestInjurySignal:
    def test_injury_new_fires_with_client(self, seeded):
        _seed_prev_pulse(1003, {"status": "first_team", "absences": 0})
        pulse.compute_pulse(WINDOW_END, player_api_ids=[1003], api_client=_InjuryClient(2))
        signals = PlayerPulse.query.filter_by(player_api_id=1003, window_end=WINDOW_END).one().delta_json["signals"]
        assert signals["injury_new"]["value"] == 2
        assert signals["injury_new"]["points"] == 1.5

    def test_injury_cleared_fires_with_client(self, seeded):
        _seed_prev_pulse(1003, {"status": "first_team", "absences": 3})
        pulse.compute_pulse(WINDOW_END, player_api_ids=[1003], api_client=_InjuryClient(1))
        signals = PlayerPulse.query.filter_by(player_api_id=1003, window_end=WINDOW_END).one().delta_json["signals"]
        assert signals["injury_cleared"]["value"] == 2

    def test_no_injury_signal_without_client(self, seeded):
        # Even with a prior absence baseline, the bulk path (api_client=None)
        # never calls the network and records no injury signal.
        _seed_prev_pulse(1003, {"status": "first_team", "absences": 0})
        pulse.compute_pulse(WINDOW_END, player_api_ids=[1003])
        row = PlayerPulse.query.filter_by(player_api_id=1003, window_end=WINDOW_END).one()
        assert "injury_new" not in row.delta_json["signals"]
        assert row.delta_json["context"]["absences"] is None


# --------------------------------------------------------------------------- #
# Idempotence / determinism / dry-run / enumeration
# --------------------------------------------------------------------------- #


class TestUpsertAndRun:
    def test_upsert_idempotent_and_deterministic(self, seeded):
        first = pulse.compute_pulse(WINDOW_END, player_api_ids=[1001])
        first_score = PlayerPulse.query.filter_by(player_api_id=1001, window_end=WINDOW_END).one().score
        second = pulse.compute_pulse(WINDOW_END, player_api_ids=[1001])
        rows = PlayerPulse.query.filter_by(player_api_id=1001, window_end=WINDOW_END).all()
        assert len(rows) == 1  # upsert, not duplicate
        assert rows[0].score == first_score  # deterministic
        assert first["top"][0]["score"] == second["top"][0]["score"]

    def test_dry_run_writes_nothing(self, seeded):
        result = pulse.compute_pulse(WINDOW_END, player_api_ids=[1001], dry_run=True)
        assert result["dry_run"] is True
        assert result["upserted"] == 0
        assert PlayerPulse.query.count() == 0
        assert result["top"][0]["player_api_id"] == 1001  # preview still computed

    def test_followed_ids_dedup_across_watchlist_and_list(self, seeded):
        # 1001 followed twice (watchlist + a player-kind follow); 1003 via list.
        db.session.add(ScoutWatchlistEntry(user_account_id=1, player_api_id=1001))
        fl = FollowList(user_account_id=1, name="My List", is_active=True)
        db.session.add(fl)
        db.session.flush()
        db.session.add_all(
            [
                Follow(list_id=fl.id, kind="player", selector={"player_api_id": 1001}),
                Follow(list_id=fl.id, kind="player", selector={"player_api_id": 1003}),
            ]
        )
        db.session.commit()

        result = pulse.compute_pulse(WINDOW_END)  # player_api_ids=None → enumerate all
        assert result["players_considered"] == 2  # 1001 counted once
        assert PlayerPulse.query.filter_by(player_api_id=1001).count() == 1
        assert PlayerPulse.query.filter_by(player_api_id=1003).count() == 1
