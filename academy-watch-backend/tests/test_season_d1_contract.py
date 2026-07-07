"""D1 season-API CONTRACT pins (proposal §4 / §6 / §7 D1).

Companion to ``test_season_api_d1.py`` (which drives the endpoint happy paths).
This file locks the four contract surfaces the D1 design is judged on, filling
the gaps the endpoint suite leaves open:

1. **Resolver surfaces** (``academy_window.resolve_stats_season`` /
   ``season_bounds``) as a direct unit: ``discovery`` falls back to the latest
   season WITH fixtures; ``compare`` deliberately does NOT fall back and returns
   the wall-clock season so a not-yet-started compare column renders empty
   ("season not started"); an out-of-range / non-integer request raises
   ``ValueError`` and the routes turn that into HTTP 400.
2. **``?season`` contract** on ``/stats`` and ``/season-stats``: no param is
   byte-identical to the pre-param behaviour (exact seeded field values); an
   explicit PAST season returns that season only; out-of-bounds → 400.
3. **Closed season ranges**: with fixtures seeded in TWO seasons, a single-season
   read must NOT double-count. This is the regression that fires the day the
   2026-27 fixtures land (the old open-ended ``date_utc >=`` filters summed every
   season; the D1 fix scopes them to ``Fixture.season ==``).
4. **Provenance buckets**: the on-read ``_season_provenance`` object routes the
   FPS-vs-PJE senior-minutes reconciliation into exactly one of ``cup-gap``
   (journey > fixtures > 0, the Gore case), ``fixtures-invisible`` (journey-only),
   ``journey-under-sync`` (fixtures > journey), or ``None`` (agree / both zero) —
   with youth / international / other-season journey entries excluded.

Season values are API-Football season START years (2025 == 2025-26).
"""

import os
from datetime import UTC, date, datetime

import pytest
from flask import Flask


class _StubAPIClient:
    """No-network stand-in: games_played=0 so the freshness-sync branch is inert
    and the endpoints do zero I/O (mirrors test_season_api_d1.py)."""

    def __init__(self, *args, **kwargs):
        pass

    def _fetch_player_team_season_totals_api(self, *args, **kwargs):
        return {"games_played": 0}


# Distinct id spaces per concern so a stray cross-test collision would be loud.
FULL_PLAYER_API = 700700
GK_PLAYER_API = 700701  # goalkeeper spanning two clubs across two seasons
PARENT_API = 33
LOAN_API = 777
LOAN2_API = 778  # a second, later-season-only loan club
OPP_API = 999

PROV_PLAYER_API = 710710  # provenance-unit player (no TrackedPlayer needed)
PROV_TEAM_API = 711


@pytest.fixture
def app(monkeypatch):
    os.environ.setdefault("SKIP_API_HANDSHAKE", "1")
    os.environ.setdefault("API_USE_STUB_DATA", "true")

    import src.api_football_client as apifc

    monkeypatch.setattr(apifc, "APIFootballClient", _StubAPIClient)

    # Register the models on the metadata before create_all (players_bp imports
    # them lazily inside the endpoints).
    from src.models import follow, journey, tracked_player, weekly  # noqa: F401
    from src.models.league import db
    from src.routes.players import players_bp

    application = Flask(__name__)
    application.config.update(
        TESTING=True,
        SECRET_KEY="test-secret",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        RATELIMIT_ENABLED=False,
    )
    db.init_app(application)
    application.register_blueprint(players_bp, url_prefix="/api")

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


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


def _team(api_id, name):
    from src.models.league import Team, db

    team = Team(team_id=api_id, name=name, country="England", season=2025, logo=f"{api_id}.png")
    db.session.add(team)
    db.session.flush()
    return team


def _add_fixture_stats(
    player_api_id, team_api_id, season, minutes_list, *, fx_base, goals=1, assists=0, goals_conceded=None
):
    """Seed one Fixture + one FixturePlayerStats per entry in ``minutes_list``,
    all in ``season`` at ``team_api_id``. ``fx_base`` keys unique fixture ids.
    ``goals_conceded`` defaults to ``None`` (NULL) so existing callers are
    byte-identical; pass ``0`` to seed a GK clean sheet that the clean-sheets
    read (``goals_conceded == 0``) will count."""
    from src.models.league import db
    from src.models.weekly import Fixture, FixturePlayerStats

    for i, minutes in enumerate(minutes_list):
        fx = Fixture(
            fixture_id_api=fx_base + i,
            season=season,
            date_utc=datetime(season, 9, 1 + i, tzinfo=UTC),
            competition_name="Championship",
            home_team_api_id=team_api_id,
            away_team_api_id=OPP_API,
            home_goals=1,
            away_goals=0,
        )
        db.session.add(fx)
        db.session.flush()
        db.session.add(
            FixturePlayerStats(
                fixture_id=fx.id,
                player_api_id=player_api_id,
                team_api_id=team_api_id,
                minutes=minutes,
                goals=goals,
                assists=assists,
                goals_conceded=goals_conceded,
                rating=7.0,
            )
        )


def _add_journey_entries(player_api_id, entries, *, player_name="Contract Player"):
    """``entries`` = iterable of ``(season, minutes, is_youth, is_international)``."""
    from src.models.journey import PlayerJourney, PlayerJourneyEntry
    from src.models.league import db

    journey = PlayerJourney(player_api_id=player_api_id, player_name=player_name)
    db.session.add(journey)
    db.session.flush()
    for season, minutes, is_youth, is_intl in entries:
        db.session.add(
            PlayerJourneyEntry(
                journey_id=journey.id,
                season=season,
                club_api_id=PROV_TEAM_API,
                club_name="Prov FC",
                minutes=minutes,
                appearances=5,
                goals=1,
                assists=0,
                is_youth=is_youth,
                is_international=is_intl,
            )
        )


def _seed_single_season_full_player():
    """A full-coverage on-loan player with FPS ONLY in season 2025 (two 90'
    matches = 180 min at the loan club). Discovery resolves to 2025 regardless
    of wall clock (2025 either IS the calendar season or is MAX-with-data), so
    the no-param assertions are deterministic across the Aug-2026 rollover."""
    from src.models.league import db
    from src.models.tracked_player import TrackedPlayer

    parent = _team(PARENT_API, "Parent FC")
    _team(LOAN_API, "Loan FC")
    _team(OPP_API, "Opponent FC")
    db.session.add(
        TrackedPlayer(
            player_api_id=FULL_PLAYER_API,
            player_name="Single Season Guy",
            position="Midfielder",
            team_id=parent.id,
            status="on_loan",
            current_club_api_id=LOAN_API,
            current_club_name="Loan FC",
            data_depth="full_stats",
            is_active=True,
        )
    )
    _add_fixture_stats(FULL_PLAYER_API, LOAN_API, 2025, [90, 90], fx_base=9600, goals=1)
    db.session.commit()


def _seed_two_season_full_player():
    """Same player, FPS in TWO seasons at the loan club: 2025 = two 90' matches
    (180 min), 2026 = one 90' match (90 min). Cross-season total is 270; a
    correctly season-scoped read never reports 270."""
    from src.models.league import db
    from src.models.tracked_player import TrackedPlayer

    parent = _team(PARENT_API, "Parent FC")
    _team(LOAN_API, "Loan FC")
    _team(OPP_API, "Opponent FC")
    db.session.add(
        TrackedPlayer(
            player_api_id=FULL_PLAYER_API,
            player_name="Two Season Guy",
            position="Midfielder",
            team_id=parent.id,
            status="on_loan",
            current_club_api_id=LOAN_API,
            current_club_name="Loan FC",
            data_depth="full_stats",
            is_active=True,
        )
    )
    _add_fixture_stats(FULL_PLAYER_API, LOAN_API, 2025, [90, 90], fx_base=9700, goals=1)
    _add_fixture_stats(FULL_PLAYER_API, LOAN_API, 2026, [90], fx_base=9750, goals=1)
    db.session.commit()


def _seed_gk_two_seasons_two_clubs():
    """A full-coverage on-loan GOALKEEPER whose fixtures make BOTH open-range
    Q12 sites REVEAL a season-filter regression that the single-club/no-clean-
    sheet seeds above cannot (both mutations stay green against them):

    - **Clean-sheets** (team-filtered to the resolved-season club list): club A
      (``LOAN_API``) keeps a clean sheet in BOTH seasons — 2025: two 90' clean
      sheets, 2026: one 90' clean sheet. A 2025 read scoped by ``Fixture.season``
      counts 2; reverting that one site to an open ``date_utc >=`` filter folds
      in A's 2026 clean sheet and reports 3. Club A must appear in both seasons
      or the club-list filter would mask the leak on its own.
    - **Distinct-teams club list**: club B (``LOAN2_API``) plays a SINGLE 2026
      fixture (a goal conceded — not a clean sheet, but still a distinct club).
      A 2025 read's club set is therefore ``{A}`` (``has_multiple_clubs`` False);
      an open-range revert leaks B in and flips ``has_multiple_clubs`` / the
      ``loan_team`` label.
    """
    from src.models.league import db
    from src.models.tracked_player import TrackedPlayer

    parent = _team(PARENT_API, "Parent FC")
    _team(LOAN_API, "Loan FC")
    _team(LOAN2_API, "Loan FC 2")
    _team(OPP_API, "Opponent FC")
    db.session.add(
        TrackedPlayer(
            player_api_id=GK_PLAYER_API,
            player_name="Keeper Guy",
            position="Goalkeeper",
            team_id=parent.id,
            status="on_loan",
            current_club_api_id=LOAN_API,
            current_club_name="Loan FC",
            data_depth="full_stats",
            is_active=True,
        )
    )
    # Club A: clean sheets in BOTH seasons (2 in 2025, 1 in 2026).
    _add_fixture_stats(GK_PLAYER_API, LOAN_API, 2025, [90, 90], fx_base=9900, goals=0, goals_conceded=0)
    _add_fixture_stats(GK_PLAYER_API, LOAN_API, 2026, [90], fx_base=9950, goals=0, goals_conceded=0)
    # Club B: one 2026 appearance, a goal conceded (a distinct 2026-only club).
    _add_fixture_stats(GK_PLAYER_API, LOAN2_API, 2026, [90], fx_base=9980, goals=0, goals_conceded=1)
    db.session.commit()


# ---------------------------------------------------------------------------
# 1. Resolver surfaces (discovery fallback / compare no-fallback / bounds)
# ---------------------------------------------------------------------------


class TestResolverSurfaces:
    """``resolve_stats_season`` + ``season_bounds`` as a direct unit. ``today`` is
    passed explicitly so nothing hinges on the wall clock."""

    def _seed_fixture(self, season, fx_id):
        from src.models.league import db
        from src.models.weekly import Fixture

        db.session.add(
            Fixture(
                fixture_id_api=fx_id,
                season=season,
                date_utc=datetime(season, 9, 1, tzinfo=UTC),
                home_team_api_id=1,
                away_team_api_id=2,
            )
        )
        db.session.commit()

    def test_discovery_falls_back_to_latest_season_with_fixtures(self, app):
        from src.models.league import db
        from src.utils.academy_window import resolve_stats_season

        # Only 2025 fixtures exist; wall clock frozen past the Aug-2026 rollover
        # so the calendar season is 2026 but no 2026 fixtures exist yet.
        self._seed_fixture(2025, 1)
        got = resolve_stats_season(db.session, surface="discovery", today=date(2026, 8, 1))
        assert got == 2025, "discovery must fall back to the latest season that HAS fixtures"

    def test_compare_does_not_fall_back_and_signals_not_started(self, app):
        from src.models.league import db
        from src.utils.academy_window import resolve_stats_season

        # Same seed: only 2025 fixtures, wall clock = 2026-08-01 (calendar 2026).
        self._seed_fixture(2025, 1)
        compare = resolve_stats_season(db.session, surface="compare", today=date(2026, 8, 1))
        discovery = resolve_stats_season(db.session, surface="discovery", today=date(2026, 8, 1))
        # compare returns the wall-clock season WITHOUT the with-data fallback, so
        # a compare column for a season with no fixtures renders empty rather than
        # borrowing 2025's numbers. It must diverge from discovery here.
        assert compare == 2026
        assert discovery == 2025
        assert compare != discovery, "compare must NOT reuse discovery's with-data fallback"

    def test_explicit_request_honored_verbatim_on_every_surface(self, app):
        from src.models.league import db
        from src.utils.academy_window import resolve_stats_season

        self._seed_fixture(2025, 1)
        # An explicit in-range request is returned as-is regardless of surface.
        for surface in ("discovery", "compare"):
            assert resolve_stats_season(db.session, requested=2025, surface=surface, today=date(2026, 8, 1)) == 2026 - 1
        # String ints (what the route actually receives from request.args) coerce.
        assert resolve_stats_season(db.session, requested="2025", today=date(2025, 9, 1)) == 2025

    def test_season_bounds_span_min_fixture_to_next_season(self, app):
        from src.models.league import db
        from src.utils.academy_window import season_bounds

        self._seed_fixture(2025, 1)
        # low = MIN(fixtures.season) = 2025; high = current_stats_season + 1.
        assert season_bounds(db.session, today=date(2025, 9, 1)) == (2025, 2026)

    def test_season_bounds_low_is_min_fixture_season(self, app):
        from src.models.league import db
        from src.utils.academy_window import season_bounds

        # Two fixture seasons: low tracks the MIN, not the MAX.
        self._seed_fixture(2024, 1)
        self._seed_fixture(2025, 2)
        assert season_bounds(db.session, today=date(2025, 9, 1)) == (2024, 2026)

    def test_season_bounds_falls_back_when_no_fixtures(self, app):
        from src.models.league import db
        from src.utils.academy_window import season_bounds

        # No fixtures at all: low falls back to current_stats_season so the range
        # never inverts (low <= high).
        low, high = season_bounds(db.session, today=date(2025, 9, 1))
        assert (low, high) == (2025, 2026)
        assert low <= high

    def test_out_of_range_request_raises_valueerror(self, app):
        from src.models.league import db
        from src.utils.academy_window import resolve_stats_season

        self._seed_fixture(2025, 1)  # bounds = [2025, 2026]
        with pytest.raises(ValueError):
            resolve_stats_season(db.session, requested=2024, today=date(2025, 9, 1))  # below low
        with pytest.raises(ValueError):
            resolve_stats_season(db.session, requested=2099, today=date(2025, 9, 1))  # above high

    def test_non_integer_request_raises_valueerror(self, app):
        from src.models.league import db
        from src.utils.academy_window import resolve_stats_season

        self._seed_fixture(2025, 1)
        with pytest.raises(ValueError):
            resolve_stats_season(db.session, requested="abc", today=date(2025, 9, 1))


# ---------------------------------------------------------------------------
# 2. ?season contract on both endpoints
# ---------------------------------------------------------------------------


class TestSeasonParamContract:
    def test_stats_no_param_exact_field_values(self, app, client):
        _seed_single_season_full_player()
        rows = client.get(f"/api/players/{FULL_PLAYER_API}/stats").get_json()
        assert isinstance(rows, list)
        assert len(rows) == 2
        assert {r["loan_team_name"] for r in rows} == {"Loan FC"}
        assert sum(r["minutes"] for r in rows) == 180
        assert sum(r["goals"] for r in rows) == 2

    def test_season_stats_no_param_exact_field_values(self, app, client):
        _seed_single_season_full_player()
        data = client.get(f"/api/players/{FULL_PLAYER_API}/season-stats").get_json()
        assert data["season"] == "2025/2026"
        assert data["source"] == "local-db"
        assert data["appearances"] == 2
        assert data["minutes"] == 180
        assert data["goals"] == 2
        assert data["provenance"]["fixtures_minutes"] == 180

    def test_no_param_byte_identical_to_explicit_current_season(self, app, client):
        # The whole point of the additive ?season plumbing: with no param the
        # response must equal what the resolved display season returns explicitly.
        _seed_single_season_full_player()
        stats_none = client.get(f"/api/players/{FULL_PLAYER_API}/stats").get_json()
        stats_expl = client.get(f"/api/players/{FULL_PLAYER_API}/stats?season=2025").get_json()
        assert stats_none == stats_expl

        ss_none = client.get(f"/api/players/{FULL_PLAYER_API}/season-stats").get_json()
        ss_expl = client.get(f"/api/players/{FULL_PLAYER_API}/season-stats?season=2025").get_json()
        assert ss_none == ss_expl

    def test_explicit_past_season_returns_that_season_only(self, app, client):
        # Two seasons seeded; asking for the PAST season (2025) returns 2025's
        # figures and nothing from 2026.
        _seed_two_season_full_player()
        rows = client.get(f"/api/players/{FULL_PLAYER_API}/stats?season=2025").get_json()
        assert len(rows) == 2
        assert sum(r["minutes"] for r in rows) == 180

        ss = client.get(f"/api/players/{FULL_PLAYER_API}/season-stats?season=2025").get_json()
        assert ss["season"] == "2025/2026"
        assert ss["minutes"] == 180
        assert ss["appearances"] == 2

    @pytest.mark.parametrize("endpoint", ["stats", "season-stats"])
    @pytest.mark.parametrize("bad", ["abc", "2024", "2099"])
    def test_out_of_bounds_or_non_integer_is_400(self, app, client, endpoint, bad):
        # 2024 is below MIN(fixtures.season)=2025; 2099 above the horizon; abc a
        # non-int. The route maps the resolver's ValueError to HTTP 400.
        _seed_single_season_full_player()
        res = client.get(f"/api/players/{FULL_PLAYER_API}/{endpoint}?season={bad}")
        assert res.status_code == 400
        assert "error" in res.get_json()

    @pytest.mark.parametrize("endpoint", ["stats", "season-stats"])
    def test_empty_season_param_is_treated_as_no_param(self, app, client, endpoint):
        # `?season=` (present but empty) is falsy → resolver default, not a 400.
        _seed_single_season_full_player()
        assert client.get(f"/api/players/{FULL_PLAYER_API}/{endpoint}?season=").status_code == 200


# ---------------------------------------------------------------------------
# 3. Closed season ranges — single-season reads must not double-count
# ---------------------------------------------------------------------------


class TestClosedSeasonRanges:
    """Fixtures in 2025 (180 min) AND 2026 (90 min); cross-season total = 270.
    A season-scoped read never returns 270 — the pre-D1 open-ended ``date_utc >=``
    filter would, the day 2026-27 fixtures land."""

    def test_stats_match_log_scoped_per_season(self, app, client):
        _seed_two_season_full_player()
        rows_25 = client.get(f"/api/players/{FULL_PLAYER_API}/stats?season=2025").get_json()
        rows_26 = client.get(f"/api/players/{FULL_PLAYER_API}/stats?season=2026").get_json()
        assert len(rows_25) == 2 and sum(r["minutes"] for r in rows_25) == 180
        assert len(rows_26) == 1 and sum(r["minutes"] for r in rows_26) == 90
        # No season yields the union of both seasons' 3 matches / 270 minutes.
        assert len(rows_25) + len(rows_26) == 3

    def test_season_stats_aggregate_scoped_per_season(self, app, client):
        _seed_two_season_full_player()
        ss_25 = client.get(f"/api/players/{FULL_PLAYER_API}/season-stats?season=2025").get_json()
        ss_26 = client.get(f"/api/players/{FULL_PLAYER_API}/season-stats?season=2026").get_json()
        assert ss_25["minutes"] == 180 and ss_25["appearances"] == 2
        assert ss_26["minutes"] == 90 and ss_26["appearances"] == 1
        # Provenance minutes are season-scoped too — never the 270 cross-season sum.
        assert ss_25["provenance"]["fixtures_minutes"] == 180
        assert ss_26["provenance"]["fixtures_minutes"] == 90

    def test_default_path_serves_a_single_season_not_the_sum(self, app, client):
        # The no-param display path resolves to ONE season (which one depends on
        # the wall clock relative to the Aug rollover); it must never fold both
        # seasons together into 270.
        _seed_two_season_full_player()
        rows = client.get(f"/api/players/{FULL_PLAYER_API}/stats").get_json()
        total = sum(r["minutes"] for r in rows)
        assert total in (180, 90)
        assert total != 270, "default path double-counted across seasons"

        ss = client.get(f"/api/players/{FULL_PLAYER_API}/season-stats").get_json()
        assert ss["minutes"] in (180, 90)
        assert ss["minutes"] != 270

    def test_clean_sheets_scoped_per_season(self, app, client):
        # The clean-sheets read is the third Q12 site and is team-filtered to the
        # resolved-season club list, so a cross-season leak is only observable
        # when the SAME club keeps clean sheets in a later season. Club A does
        # (1 in 2026), so a 2025 read must count exactly its two 2025 clean
        # sheets; an open-ended ``date_utc >=`` revert of THIS site alone would
        # fold in A's 2026 clean sheet and report 3.
        _seed_gk_two_seasons_two_clubs()
        ss_25 = client.get(f"/api/players/{GK_PLAYER_API}/season-stats?season=2025").get_json()
        ss_26 = client.get(f"/api/players/{GK_PLAYER_API}/season-stats?season=2026").get_json()
        assert ss_25["clean_sheets"] == 2, "2025 clean sheets must exclude the club's 2026 clean sheet"
        # 2026: club A's clean sheet + club B's goal-conceded appearance = 1.
        assert ss_26["clean_sheets"] == 1

    def test_distinct_club_list_scoped_per_season(self, app, client):
        # The distinct-teams club list is the fourth Q12 site. Club B plays ONLY
        # in 2026, so a 2025 read's club set is {A}: has_multiple_clubs False,
        # loan_team "Loan FC". An open-range revert leaks B into 2025 and flips
        # both. 2026 legitimately spans both clubs.
        _seed_gk_two_seasons_two_clubs()
        ss_25 = client.get(f"/api/players/{GK_PLAYER_API}/season-stats?season=2025").get_json()
        assert ss_25["loan_team"] == "Loan FC"
        assert ss_25["has_multiple_clubs"] is False, "the 2026-only club must not leak into the 2025 club set"

        ss_26 = client.get(f"/api/players/{GK_PLAYER_API}/season-stats?season=2026").get_json()
        assert ss_26["has_multiple_clubs"] is True

        # The /stats match log for 2025 shows only club A's rows (season-scoped);
        # 2026 spans two distinct clubs (club B's name resolves via the team
        # resolver, so assert distinctness rather than pinning its label).
        rows_25 = client.get(f"/api/players/{GK_PLAYER_API}/stats?season=2025").get_json()
        assert {r["loan_team_name"] for r in rows_25} == {"Loan FC"}
        rows_26 = client.get(f"/api/players/{GK_PLAYER_API}/stats?season=2026").get_json()
        assert len(rows_26) == 2
        assert len({r["loan_team_name"] for r in rows_26}) == 2
        assert "Loan FC" in {r["loan_team_name"] for r in rows_26}


# ---------------------------------------------------------------------------
# 4. Provenance buckets (direct unit on _season_provenance)
# ---------------------------------------------------------------------------


class TestProvenanceBuckets:
    """``_season_provenance(player, season)`` reconciles FPS senior minutes vs
    PJE senior-season-total minutes into exactly one reconcile bucket."""

    def test_cup_gap_gore_numbers(self, app):
        # The real Gore 2025-26 shape: 2,583 league minutes from fixtures vs 2,936
        # cup-inclusive minutes from the journey summary → journey wins, cup-gap.
        from src.models.league import db
        from src.routes.players import _season_provenance

        _add_fixture_stats(PROV_PLAYER_API, PROV_TEAM_API, 2025, [900, 900, 783], fx_base=9800)
        _add_journey_entries(PROV_PLAYER_API, [(2025, 2936, False, False)])
        db.session.commit()

        prov = _season_provenance(PROV_PLAYER_API, 2025)
        assert prov["fixtures_minutes"] == 2583
        assert prov["journey_minutes"] == 2936
        assert prov["source"] == "journey"
        assert prov["reconcile_flag"] == "cup-gap"
        assert prov["delta_pct"] == 12.0  # (2936-2583)/2936*100, 1dp

    def test_fixtures_invisible_journey_only(self, app):
        # Journey has senior minutes but no per-match fixtures exist for the
        # player this season → the whole season is fixtures-invisible.
        from src.models.league import db
        from src.routes.players import _season_provenance

        _add_journey_entries(PROV_PLAYER_API, [(2025, 1500, False, False)])
        db.session.commit()

        prov = _season_provenance(PROV_PLAYER_API, 2025)
        assert prov["fixtures_minutes"] == 0
        assert prov["journey_minutes"] == 1500
        assert prov["source"] == "journey"
        assert prov["reconcile_flag"] == "fixtures-invisible"
        assert prov["delta_pct"] == 100.0

    def test_journey_under_sync_fixtures_gt_journey(self, app):
        # Fixtures prove MORE minutes than the (lagging) journey summary knows →
        # fixtures win the headline, journey flagged as under-sync.
        from src.models.league import db
        from src.routes.players import _season_provenance

        _add_fixture_stats(PROV_PLAYER_API, PROV_TEAM_API, 2025, [900, 600], fx_base=9820)
        _add_journey_entries(PROV_PLAYER_API, [(2025, 1000, False, False)])
        db.session.commit()

        prov = _season_provenance(PROV_PLAYER_API, 2025)
        assert prov["fixtures_minutes"] == 1500
        assert prov["journey_minutes"] == 1000
        assert prov["source"] == "fixtures"
        assert prov["reconcile_flag"] == "journey-under-sync"
        assert prov["delta_pct"] == -33.3  # (1000-1500)/1500*100, 1dp

    def test_sources_agree_no_flag(self, app):
        # Equal minutes → journey wins the tie (cup-inclusive convention) but
        # there is nothing to reconcile, so no flag and zero delta.
        from src.models.league import db
        from src.routes.players import _season_provenance

        _add_fixture_stats(PROV_PLAYER_API, PROV_TEAM_API, 2025, [900], fx_base=9840)
        _add_journey_entries(PROV_PLAYER_API, [(2025, 900, False, False)])
        db.session.commit()

        prov = _season_provenance(PROV_PLAYER_API, 2025)
        assert prov["source"] == "journey"
        assert prov["reconcile_flag"] is None
        assert prov["delta_pct"] == 0.0

    def test_both_zero_source_none(self, app):
        # Nothing seeded for the season → source "none", no flag.
        from src.routes.players import _season_provenance

        prov = _season_provenance(PROV_PLAYER_API, 2025)
        assert prov == {
            "source": "none",
            "fixtures_minutes": 0,
            "journey_minutes": 0,
            "delta_pct": 0.0,
            "reconcile_flag": None,
        }

    def test_journey_minutes_exclude_youth_international_and_other_seasons(self, app):
        # Only the senior, in-season entry (900) counts. Youth (500) and
        # international (400) 2025 entries and a prior-season 2024 senior (1000)
        # entry are all excluded — so journey=900, and with no fixtures the bucket
        # is fixtures-invisible.
        from src.models.league import db
        from src.routes.players import _season_provenance

        _add_journey_entries(
            PROV_PLAYER_API,
            [
                (2025, 900, False, False),  # counts
                (2025, 500, True, False),  # youth — excluded
                (2025, 400, False, True),  # international — excluded
                (2024, 1000, False, False),  # prior season — excluded
            ],
        )
        db.session.commit()

        prov = _season_provenance(PROV_PLAYER_API, 2025)
        assert prov["journey_minutes"] == 900
        assert prov["fixtures_minutes"] == 0
        assert prov["reconcile_flag"] == "fixtures-invisible"
