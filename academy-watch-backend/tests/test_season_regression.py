"""Regression coverage for the season-foundation branch (A1-A3).

Locks in the three defects the ``feat/season-foundation`` remediation fixed, so
a future refactor can't silently reintroduce them:

1. **Returned-loanee stat attribution.** Every season stat read used to key on
   ``TrackedPlayer.current_club_api_id``. When a loan-return transfer flips a
   player's current club back to the parent (or leaves it NULL, common for
   first-team rows), his whole loan season vanished — 0 minutes on the profile
   match log, absent from Scout Desk — even though the ``FixturePlayerStats``
   rows exist at the loan club. Fixed by deriving the season's clubs from the
   fixture data itself. This file asserts ``compute_stats``,
   ``GET /players/<id>/stats`` and the Scout base query (``GET /scout/players``)
   all surface the loan-club season regardless of where the tracked row points.

2. **Orphan guard (stored-attribution floor).** A transient journey sync that
   resolves NO academy evidence (API youth-coverage gap / tenure-gate flicker →
   empty ``academy_ids``) must NOT deactivate an established in-window academy
   row whose stored journey attribution still lists the club. A genuinely
   out-of-window alumnus row must still deactivate.

3. **August rollover.** ``current_stats_season`` rolls the DISPLAY season over
   on 1 August, but the calendar season can turn before any of its fixtures are
   ingested. ``stats_season_with_data`` falls back to the latest season that
   actually HAS fixtures so a not-yet-started season never blanks the platform.
   Frozen to 2026-08-01 with fixtures only for 2025: the service returns 2026 as
   the calendar season but 2025 as the with-data season, and the display paths
   keep rendering the 2025 numbers instead of zeros.
"""

import os
from datetime import UTC, date, datetime

import pytest
from flask import Flask


class _StubAPIClient:
    """No-network stand-in. Returns a non-empty dict so ``api_totals_failed`` is
    False and ``games_played=0`` so the freshness-sync branch never fires — the
    player-stats endpoint therefore does zero network I/O in tests."""

    def __init__(self, *args, **kwargs):
        pass

    def _fetch_player_team_season_totals_api(self, *args, **kwargs):
        return {"games_played": 0}


@pytest.fixture
def app(monkeypatch):
    os.environ.setdefault("SKIP_API_HANDSHAKE", "1")
    os.environ.setdefault("API_USE_STUB_DATA", "true")

    import src.api_football_client as apifc

    monkeypatch.setattr(apifc, "APIFootballClient", _StubAPIClient)

    from src.models.league import db
    from src.routes.players import players_bp
    from src.routes.scout import scout_bp
    from src.routes.teams import teams_bp

    application = Flask(__name__)
    application.config.update(
        TESTING=True,
        SECRET_KEY="test-secret",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        RATELIMIT_ENABLED=False,
    )
    db.init_app(application)
    # scout_bp / players_bp register before any api_bp catch-all would (not
    # registered here) — mirrors main.py's load-bearing order.
    application.register_blueprint(scout_bp, url_prefix="/api")
    application.register_blueprint(players_bp, url_prefix="/api")
    application.register_blueprint(teams_bp, url_prefix="/api")

    ctx = application.app_context()
    ctx.push()
    db.create_all()
    yield application
    db.session.remove()
    db.drop_all()
    ctx.pop()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def sync_service(app):
    from src.services.journey_sync import JourneySyncService

    return JourneySyncService()


# ---------------------------------------------------------------------------
# Shared seed helpers (assume an active app context — the `app` fixture pushes one)
# ---------------------------------------------------------------------------

PARENT_API = 33
LOAN_API = 777
OPP_API = 999
PLAYER_API = 303010  # Daniel Gore's real API id, kept for provenance


def _team(api_id, name):
    from src.models.league import Team, db

    team = Team(team_id=api_id, name=name, country="England", season=2025, logo=f"{api_id}.png")
    db.session.add(team)
    db.session.flush()
    return team


def _seed_returned_loanee(current_club_api_id, *, loan_minutes=90, loan_apps=3, season=2025):
    """A returned loanee: tracked at the parent academy club, current club flipped
    back to the parent (or NULL), but the real season is a full loan spell at
    another club recorded in FixturePlayerStats. Returns the parent Team + the id.
    """
    from src.models.tracked_player import TrackedPlayer
    from src.models.weekly import Fixture, FixturePlayerStats, db

    parent = _team(PARENT_API, "Parent FC")
    _team(LOAN_API, "Loan FC")
    _team(OPP_API, "Opponent FC")

    tp = TrackedPlayer(
        player_api_id=PLAYER_API,
        player_name="Gore Regression",
        position="Midfielder",
        team_id=parent.id,
        status="first_team",
        current_club_api_id=current_club_api_id,  # parent id OR None — the bug trigger
        current_club_name="Parent FC" if current_club_api_id else None,
        data_depth="full_stats",
        is_active=True,
    )
    db.session.add(tp)

    for i in range(loan_apps):
        fx = Fixture(
            fixture_id_api=8000 + i,
            season=season,
            date_utc=datetime(season, 9, 1 + 7 * i, tzinfo=UTC),
            competition_name="Championship",
            home_team_api_id=LOAN_API,
            away_team_api_id=OPP_API,
            home_goals=1,
            away_goals=0,
        )
        db.session.add(fx)
        db.session.flush()
        db.session.add(
            FixturePlayerStats(
                fixture_id=fx.id,
                player_api_id=PLAYER_API,
                team_api_id=LOAN_API,
                minutes=loan_minutes,
                goals=1,
                assists=0,
                rating=7.5,
            )
        )
    db.session.commit()
    return parent, tp.id


# ---------------------------------------------------------------------------
# 1. Returned-loanee stat attribution (A1 read-path hardening)
# ---------------------------------------------------------------------------


class TestReturnedLoaneeAttribution:
    """current_club points at the parent / NULL, but the season lives at the loan
    club — all three season-stat reads must attribute it anyway."""

    @pytest.mark.parametrize("current_club", [PARENT_API, None], ids=["current=parent", "current=NULL"])
    def test_compute_stats_returns_loan_minutes(self, app, current_club):
        from src.models.league import db
        from src.models.tracked_player import TrackedPlayer

        _, tp_id = _seed_returned_loanee(current_club, loan_minutes=90, loan_apps=3)
        tp = db.session.get(TrackedPlayer, tp_id)

        stats = tp.compute_stats()

        # Keyed on current_club_api_id (the bug) this returned zeros; season-scoped
        # across the clubs actually played it returns the loan spell.
        assert stats["minutes_played"] == 270
        assert stats["appearances"] == 3
        assert stats["goals"] == 3
        assert stats["stats_coverage"] == "full"

    @pytest.mark.parametrize("current_club", [PARENT_API, None], ids=["current=parent", "current=NULL"])
    def test_players_stats_endpoint_includes_loan_club(self, app, client, current_club):
        _seed_returned_loanee(current_club, loan_minutes=90, loan_apps=3)

        res = client.get(f"/api/players/{PLAYER_API}/stats")
        assert res.status_code == 200
        rows = res.get_json()
        assert isinstance(rows, list)
        # The loan club's three match rows render even though no tracked-row field
        # points at it — they come from the FixturePlayerStats UNION.
        assert len(rows) == 3
        assert {r["loan_team_name"] for r in rows} == {"Loan FC"}
        assert sum(r["minutes"] for r in rows) == 270

    @pytest.mark.parametrize("current_club", [PARENT_API, None], ids=["current=parent", "current=NULL"])
    def test_scout_base_query_surfaces_season_minutes(self, app, client, current_club):
        _seed_returned_loanee(current_club, loan_minutes=90, loan_apps=3)

        res = client.get("/api/scout/players?search=gore")
        assert res.status_code == 200
        data = res.get_json()
        assert data["total"] == 1
        row = data["players"][0]
        assert row["player_id"] == PLAYER_API
        # Scout Desk shows one season figure per player, summed across clubs — the
        # loan season, not a zero-at-current-club blank.
        assert row["minutes_played"] == 270
        assert row["appearances"] == 3
        assert row["goals"] == 3


# ---------------------------------------------------------------------------
# 2. Orphan guard: stored-attribution floor (A2/A3 write guard)
# ---------------------------------------------------------------------------


class TestOrphanGuard:
    """An empty-evidence sync must not orphan an in-window academy row that the
    journey still attributes to the club; a genuine aged-out row still deactivates."""

    def _journey_with_stored_attribution(self, player_api_id, club_api_id, last_season):
        """Journey carrying a PERSISTED academy attribution but NO youth entries
        this run, so _compute_academy_club_ids takes an empty-computation path and
        must lean on the stored attribution (the floor) to decide."""
        from src.models.journey import PlayerJourney
        from src.models.league import db

        journey = PlayerJourney(
            player_api_id=player_api_id,
            player_name=f"Orphan {player_api_id}",
            academy_club_ids=[club_api_id],
            academy_last_seasons={str(club_api_id): last_season},
        )
        db.session.add(journey)
        db.session.flush()
        return journey

    def _tracked_at(self, player_api_id, team, journey):
        from src.models.league import db
        from src.models.tracked_player import TrackedPlayer

        tp = TrackedPlayer(
            player_api_id=player_api_id,
            player_name=f"Orphan {player_api_id}",
            team_id=team.id,
            status="first_team",
            data_source="journey-sync",
            journey_id=journey.id,
            is_active=True,
        )
        db.session.add(tp)
        db.session.flush()
        return tp

    def test_empty_sync_does_not_deactivate_in_window_row(self, app, sync_service):
        from src.models.league import db
        from src.utils.academy_window import current_academy_season

        recent = current_academy_season()  # in window
        club = _team(100, "Feyenoord")
        journey = self._journey_with_stored_attribution(600, 100, recent)
        row = self._tracked_at(600, club, journey)
        db.session.commit()

        # This run resolves no fresh academy evidence (no youth entries).
        sync_service._compute_academy_club_ids(journey)

        assert row.is_active is True, "the stored-attribution floor must spare an in-window orphan"

    def test_out_of_window_row_still_deactivates(self, app, sync_service):
        from src.models.league import db
        from src.utils.academy_window import academy_window_start

        old = academy_window_start() - 2  # aged out of the tracking window
        club = _team(100, "Feyenoord")
        journey = self._journey_with_stored_attribution(601, 100, old)
        row = self._tracked_at(601, club, journey)
        db.session.commit()

        sync_service._compute_academy_club_ids(journey)

        assert row.is_active is False, "a genuinely out-of-window alumnus must still deactivate"


# ---------------------------------------------------------------------------
# 3. August rollover: with-data fallback keeps the platform from blanking (A1/P4)
# ---------------------------------------------------------------------------


class _FrozenDate(date):
    """date subclass whose today() is pinned to 2026-08-01 — past the 1 Aug stats
    rollover while fixtures still only exist for season 2025."""

    _frozen = date(2026, 8, 1)

    @classmethod
    def today(cls):
        return cls._frozen


class TestAugustRollover:
    def test_current_stats_season_rolls_over_on_august(self):
        from src.utils.academy_window import current_stats_season

        # August hinge (distinct from the academy window's July hinge).
        assert current_stats_season(date(2026, 7, 31)) == 2025
        assert current_stats_season(date(2026, 8, 1)) == 2026

    def test_with_data_falls_back_to_latest_season_with_fixtures(self, app):
        from src.models.league import db
        from src.models.weekly import Fixture
        from src.utils.academy_window import current_stats_season, stats_season_with_data

        # Only season-2025 fixtures exist.
        db.session.add(
            Fixture(
                fixture_id_api=1,
                season=2025,
                date_utc=datetime(2025, 9, 1, tzinfo=UTC),
                home_team_api_id=1,
                away_team_api_id=2,
            )
        )
        db.session.commit()

        aug_first = date(2026, 8, 1)
        # Calendar season has already rolled to 2026 ...
        assert current_stats_season(aug_first) == 2026
        # ... but with no 2026 fixtures the with-data season stays on 2025 rather
        # than pointing at an empty season and blanking every stats page.
        assert stats_season_with_data(db.session, aug_first) == 2025

        # Once a 2026 fixture lands the fallback self-heals to the calendar season.
        db.session.add(
            Fixture(
                fixture_id_api=2,
                season=2026,
                date_utc=datetime(2026, 8, 20, tzinfo=UTC),
                home_team_api_id=1,
                away_team_api_id=2,
            )
        )
        db.session.commit()
        assert stats_season_with_data(db.session, aug_first) == 2026

    def test_display_paths_do_not_blank_on_august_first(self, app, client, monkeypatch):
        """Frozen to 2026-08-01 with only 2025 fixtures, both compute_stats and the
        player-stats endpoint keep rendering the 2025 season instead of zeros."""
        import src.utils.academy_window as aw
        from src.models.league import db
        from src.models.tracked_player import TrackedPlayer

        _, tp_id = _seed_returned_loanee(PARENT_API, loan_minutes=90, loan_apps=3, season=2025)

        # Pin "today" to the day after the August rollover.
        monkeypatch.setattr(aw, "date", _FrozenDate)
        assert aw.current_stats_season() == 2026  # calendar rolled ...
        assert aw.stats_season_with_data(db.session) == 2025  # ... display falls back

        tp = db.session.get(TrackedPlayer, tp_id)
        stats = tp.compute_stats()
        assert stats["minutes_played"] == 270, "compute_stats blanked on the Aug rollover"

        res = client.get(f"/api/players/{PLAYER_API}/stats")
        assert res.status_code == 200
        rows = res.get_json()
        assert len(rows) == 3, "player-stats endpoint blanked on the Aug rollover"
        assert sum(r["minutes"] for r in rows) == 270
