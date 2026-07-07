"""D1 zero-migration season-API contract (proposal §4 / §7 D1).

Drives the two single-player endpoints end-to-end to lock in:

1. ``?season=<int>`` scopes every read to that season; no param is unchanged.
2. ``season_bounds`` validation → HTTP 400 on a non-int or out-of-range season.
3. The on-read provenance object (FPS vs PlayerJourneyEntry senior minutes),
   including the Gore-style ``cup-gap`` case (journey > fixtures) and the
   youth/international/prior-season exclusions.
"""

import os
from datetime import UTC, datetime

import pytest
from flask import Flask


class _StubAPIClient:
    """No-network stand-in: games_played=0 so the freshness-sync branch is inert."""

    def __init__(self, *args, **kwargs):
        pass

    def _fetch_player_team_season_totals_api(self, *args, **kwargs):
        return {"games_played": 0}


PLAYER_API = 303010  # Gore
PARENT_API = 33
LOAN_API = 777
OPP_API = 999

# Limited-coverage (PlayerStatsCache) and shadow (PlayerShadowStats) fixtures for
# the ?season-scoping regressions below.
LIMITED_PLAYER_API = 500500
LIMITED_CLUB_API = 501
SHADOW_PLAYER_API = 600600
SHADOW_CLUB_API = 601
GENERIC_OPP_API = 909


@pytest.fixture
def app(monkeypatch):
    os.environ.setdefault("SKIP_API_HANDSHAKE", "1")
    os.environ.setdefault("API_USE_STUB_DATA", "true")

    import src.api_football_client as apifc

    monkeypatch.setattr(apifc, "APIFootballClient", _StubAPIClient)

    # Import the models so their tables register on the metadata before
    # create_all (players_bp imports them lazily, inside the endpoints).
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


def _team(api_id, name):
    from src.models.league import Team, db

    team = Team(team_id=api_id, name=name, country="England", season=2025, logo=f"{api_id}.png")
    db.session.add(team)
    db.session.flush()
    return team


def _seed_gore():
    """FPS: two 90' league matches (season 2025) at the loan club = 180 min.
    Journey (senior 2025): 300 min → cup-inclusive, so fixtures < journey =
    ``cup-gap``. Decoys the provenance MUST ignore: a youth 2025 entry (500),
    an international 2025 entry (200), and a prior-season 2024 senior entry
    (1000). Only the single senior-2025 entry (300) may count."""
    from src.models.journey import PlayerJourney, PlayerJourneyEntry
    from src.models.league import db
    from src.models.tracked_player import TrackedPlayer
    from src.models.weekly import Fixture, FixturePlayerStats

    parent = _team(PARENT_API, "Parent FC")
    _team(LOAN_API, "Loan FC")
    _team(OPP_API, "Opponent FC")

    tp = TrackedPlayer(
        player_api_id=PLAYER_API,
        player_name="Daniel Gore",
        position="Midfielder",
        team_id=parent.id,
        status="on_loan",
        current_club_api_id=LOAN_API,
        current_club_name="Loan FC",
        data_depth="full_stats",
        is_active=True,
    )
    db.session.add(tp)

    for i in range(2):
        fx = Fixture(
            fixture_id_api=8100 + i,
            season=2025,
            date_utc=datetime(2025, 9, 1 + 7 * i, tzinfo=UTC),
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
                minutes=90,
                goals=1,
                assists=0,
                rating=7.5,
            )
        )

    journey = PlayerJourney(player_api_id=PLAYER_API, player_name="Daniel Gore")
    db.session.add(journey)
    db.session.flush()
    for season, minutes, is_youth, is_intl in [
        (2025, 300, False, False),  # the only counting entry
        (2025, 500, True, False),  # youth — excluded
        (2025, 200, False, True),  # international — excluded
        (2024, 1000, False, False),  # prior season — excluded
    ]:
        db.session.add(
            PlayerJourneyEntry(
                journey_id=journey.id,
                season=season,
                club_api_id=LOAN_API,
                club_name="Loan FC",
                minutes=minutes,
                appearances=5,
                goals=1,
                assists=0,
                is_youth=is_youth,
                is_international=is_intl,
            )
        )
    db.session.commit()


class TestProvenanceObject:
    def test_season_stats_carries_cup_gap_provenance(self, app, client):
        _seed_gore()
        res = client.get(f"/api/players/{PLAYER_API}/season-stats?season=2025")
        assert res.status_code == 200
        prov = res.get_json()["provenance"]
        assert prov["fixtures_minutes"] == 180
        assert prov["journey_minutes"] == 300  # senior-2025 only; decoys excluded
        assert prov["source"] == "journey"
        assert prov["reconcile_flag"] == "cup-gap"
        assert prov["delta_pct"] == 40.0

    def test_no_param_matches_explicit_current_season(self, app, client):
        _seed_gore()
        no_param = client.get(f"/api/players/{PLAYER_API}/season-stats").get_json()
        explicit = client.get(f"/api/players/{PLAYER_API}/season-stats?season=2025").get_json()
        # Discovery default resolves to MAX(fixtures.season)=2025 — identical.
        assert no_param["provenance"] == explicit["provenance"]
        assert no_param["season"] == explicit["season"]

    def test_existing_source_field_untouched(self, app, client):
        _seed_gore()
        data = client.get(f"/api/players/{PLAYER_API}/season-stats").get_json()
        # Local FPS rows exist → the existing top-level `source` stays "local-db",
        # NOT overwritten by the provenance winner ("journey").
        assert data["source"] == "local-db"
        assert data["provenance"]["source"] == "journey"

    def test_empty_season_provenance_is_none(self, app, client):
        _seed_gore()
        prov = client.get(f"/api/players/{PLAYER_API}/season-stats?season=2026").get_json()["provenance"]
        assert prov == {
            "source": "none",
            "fixtures_minutes": 0,
            "journey_minutes": 0,
            "delta_pct": 0.0,
            "reconcile_flag": None,
        }


class TestSeasonScoping:
    def test_stats_scopes_match_log_to_requested_season(self, app, client):
        _seed_gore()
        rows_2025 = client.get(f"/api/players/{PLAYER_API}/stats?season=2025").get_json()
        assert len(rows_2025) == 2
        rows_2026 = client.get(f"/api/players/{PLAYER_API}/stats?season=2026").get_json()
        assert rows_2026 == []

    def test_stats_no_param_unchanged(self, app, client):
        _seed_gore()
        rows = client.get(f"/api/players/{PLAYER_API}/stats").get_json()
        assert len(rows) == 2
        assert {r["loan_team_name"] for r in rows} == {"Loan FC"}


class TestSeasonBoundsValidation:
    @pytest.mark.parametrize("endpoint", ["stats", "season-stats"])
    def test_non_integer_season_is_400(self, app, client, endpoint):
        _seed_gore()
        res = client.get(f"/api/players/{PLAYER_API}/{endpoint}?season=abc")
        assert res.status_code == 400
        assert "error" in res.get_json()

    @pytest.mark.parametrize("endpoint", ["stats", "season-stats"])
    def test_out_of_range_season_is_400(self, app, client, endpoint):
        _seed_gore()
        # 2024 is below MIN(fixtures.season)=2025; 2099 is far above the horizon.
        assert client.get(f"/api/players/{PLAYER_API}/{endpoint}?season=2024").status_code == 400
        assert client.get(f"/api/players/{PLAYER_API}/{endpoint}?season=2099").status_code == 400

    @pytest.mark.parametrize("endpoint", ["stats", "season-stats"])
    def test_empty_season_param_treated_as_no_param(self, app, client, endpoint):
        _seed_gore()
        # `?season=` (present but empty) must not 400 — it means "no season".
        assert client.get(f"/api/players/{PLAYER_API}/{endpoint}?season=").status_code == 200


def _seed_limited_player():
    """events_only player with PlayerStatsCache ONLY for season 2025 (20 apps,
    4 goals, 1700 min). A lone 2025 fixture anchors season_bounds and
    stats_season_with_data to 2025, so ``compute_stats()`` — pinned to the
    with-data season — speaks only for 2025. current_club is wired so the clubs
    breakdown renders (guards the zero-path clubs block against a stray
    ``computed`` reference)."""
    from src.models.league import PlayerStatsCache, db
    from src.models.tracked_player import TrackedPlayer
    from src.models.weekly import Fixture

    club = _team(LIMITED_CLUB_API, "Limited FC")
    _team(GENERIC_OPP_API, "Opp FC")
    db.session.add(
        Fixture(
            fixture_id_api=8200,
            season=2025,
            date_utc=datetime(2025, 9, 1, tzinfo=UTC),
            competition_name="League Two",
            home_team_api_id=LIMITED_CLUB_API,
            away_team_api_id=GENERIC_OPP_API,
            home_goals=0,
            away_goals=0,
        )
    )
    tp = TrackedPlayer(
        player_api_id=LIMITED_PLAYER_API,
        player_name="Limited Guy",
        position="Forward",
        team_id=club.id,
        status="on_loan",
        current_club_api_id=LIMITED_CLUB_API,
        current_club_db_id=club.id,
        current_club_name="Limited FC",
        data_depth="events_only",
        is_active=True,
    )
    db.session.add(tp)
    db.session.add(
        PlayerStatsCache(
            player_api_id=LIMITED_PLAYER_API,
            team_api_id=LIMITED_CLUB_API,
            season=2025,
            stats_coverage="limited",
            appearances=20,
            goals=4,
            assists=3,
            minutes_played=1700,
        )
    )
    db.session.commit()


def _seed_shadow_player():
    """Worldwide-followed shadow (NO TrackedPlayer) with PlayerShadowStats only
    for season 2025 (15 apps, 6 goals, 1200 min). A lone 2025 fixture anchors
    the valid season range."""
    from src.models.follow import PlayerShadow, PlayerShadowStats
    from src.models.league import db
    from src.models.weekly import Fixture

    db.session.add(
        Fixture(
            fixture_id_api=8300,
            season=2025,
            date_utc=datetime(2025, 9, 1, tzinfo=UTC),
            competition_name="Serie B",
            home_team_api_id=SHADOW_CLUB_API,
            away_team_api_id=GENERIC_OPP_API,
            home_goals=0,
            away_goals=0,
        )
    )
    db.session.add(
        PlayerShadow(
            player_api_id=SHADOW_PLAYER_API,
            player_name="Shadow Guy",
            current_club_name="Shadow FC",
            is_active=True,
        )
    )
    db.session.add(
        PlayerShadowStats(
            player_api_id=SHADOW_PLAYER_API,
            team_api_id=SHADOW_CLUB_API,
            season=2025,
            appearances=15,
            goals=6,
            assists=2,
            minutes=1200,
        )
    )
    db.session.commit()


class TestLimitedCoverageSeasonScoping:
    """The limited-coverage branch must not serve compute_stats()'s (single-season)
    numbers under a DIFFERENT requested season label."""

    def test_no_param_serves_with_data_season(self, app, client):
        _seed_limited_player()
        data = client.get(f"/api/players/{LIMITED_PLAYER_API}/season-stats").get_json()
        assert data["source"] == "limited-coverage"
        assert data["appearances"] == 20
        assert data["goals"] == 4
        assert data["clubs"][0]["appearances"] == 20  # breakdown mirrors headline

    def test_explicit_matching_season_serves_data(self, app, client):
        _seed_limited_player()
        data = client.get(f"/api/players/{LIMITED_PLAYER_API}/season-stats?season=2025").get_json()
        assert data["appearances"] == 20
        assert data["goals"] == 4

    def test_explicit_off_season_returns_zeros_not_mislabel(self, app, client):
        _seed_limited_player()
        data = client.get(f"/api/players/{LIMITED_PLAYER_API}/season-stats?season=2026").get_json()
        # The 2025 cache numbers must NOT be served under the 2026/27 label.
        assert data["season"] == "2026/2027"
        assert data["source"] == "limited-coverage"
        assert data["appearances"] == 0
        assert data["minutes"] == 0
        assert data["goals"] == 0
        assert data["assists"] == 0
        assert data["clubs"][0]["appearances"] == 0  # no stray `computed` ref → no 500
        # headline now AGREES with the season-scoped provenance (all-zero)
        assert data["provenance"]["fixtures_minutes"] == 0
        assert data["provenance"]["journey_minutes"] == 0


class TestShadowSeasonScoping:
    """The shadow branch must scope to the requested season, not blanket-serve
    MAX(PlayerShadowStats.season)."""

    def test_no_param_serves_latest_shadow_season(self, app, client):
        _seed_shadow_player()
        data = client.get(f"/api/players/{SHADOW_PLAYER_API}/season-stats").get_json()
        assert data["source"] == "shadow"
        assert data["appearances"] == 15
        assert data["goals"] == 6

    def test_explicit_matching_season_serves_data(self, app, client):
        _seed_shadow_player()
        data = client.get(f"/api/players/{SHADOW_PLAYER_API}/season-stats?season=2025").get_json()
        assert data["source"] == "shadow"
        assert data["appearances"] == 15

    def test_explicit_off_season_returns_zeros_not_latest(self, app, client):
        _seed_shadow_player()
        data = client.get(f"/api/players/{SHADOW_PLAYER_API}/season-stats?season=2026").get_json()
        # 2025 shadow totals must NOT be served under the 2026/27 label.
        assert data["season"] == "2026/2027"
        assert data["source"] == "shadow"
        assert data["appearances"] == 0
        assert data["goals"] == 0
        assert data["minutes"] == 0
