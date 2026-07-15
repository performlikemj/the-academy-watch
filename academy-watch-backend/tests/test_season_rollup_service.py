"""D3b season-rollup service — feeders, totals resolution, choke point.

The anchor test (proposal §2, gates everything): a Gore-shaped player flips
from a 2,941-minute fixtures headline to a 3,000-minute journey headline as the
journey source catches up, while cells stay source-separated and ``avg_rating``
stays fixtures-only. Plus the other coverage-map buckets, level_group split,
the noise filter, refresh idempotency/transactionality, and real sync hooks.
"""

import pytest
from flask import Flask

# Importing the service at module top registers every model it touches (journey,
# weekly, follow.PlayerShadowStats, league.AcademyPlayerSeasonStats, season_rollup)
# into db.metadata BEFORE the app fixture's create_all() runs.
from src.models.follow import PlayerShadowStats
from src.models.journey import PlayerJourney, PlayerJourneyEntry
from src.models.league import AcademyPlayerSeasonStats, db
from src.models.season_rollup import PlayerSeasonCell, PlayerSeasonTotal
from src.models.weekly import Fixture, FixturePlayerStats
from src.services import season_rollup_service as svc


@pytest.fixture
def app():
    flask_app = Flask(__name__)
    flask_app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(flask_app)
    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()


# ---------------------------------------------------------------------------
# builders
# ---------------------------------------------------------------------------
def _fixture(fid, season, comp="Premier League"):
    fx = Fixture(fixture_id_api=fid, season=season, competition_name=comp)
    db.session.add(fx)
    db.session.flush()
    return fx


def _fps(fx, player, team, minutes, goals=0, assists=0, rating=None, saves=None, gc=None, yellows=0):
    db.session.add(
        FixturePlayerStats(
            fixture_id=fx.id,
            player_api_id=player,
            team_api_id=team,
            minutes=minutes,
            goals=goals,
            assists=assists,
            rating=rating,
            saves=saves,
            goals_conceded=gc,
            yellows=yellows,
        )
    )


def _journey(player, name="Gore"):
    j = PlayerJourney(player_api_id=player, player_name=name)
    db.session.add(j)
    db.session.flush()
    return j


def _entry(j, player, season, club, minutes, goals=0, assists=0, apps=0, **kw):
    e = PlayerJourneyEntry(
        journey_id=j.id,
        player_api_id=player,
        season=season,
        club_api_id=club,
        club_name=kw.get("club_name", f"Club{club}"),
        league_name=kw.get("league_name", "Championship"),
        minutes=minutes,
        goals=goals,
        assists=assists,
        appearances=apps,
        is_youth=kw.get("is_youth", False),
        is_international=kw.get("is_international", False),
        stats_source=kw.get("stats_source", "legacy-basic"),
        rating=kw.get("rating"),
    )
    db.session.add(e)
    return e


# ---------------------------------------------------------------------------
# anchor + coverage buckets
# ---------------------------------------------------------------------------
def test_gore_shaped_anchor_flips_whole_source_on_refresh(app):
    """Rotherham league+cup cells stay separate while the headline flips whole."""
    player = 303010
    club = 73
    league_fx = _fixture(1, 2025, comp="Championship")
    cup_fx = _fixture(2, 2025, comp="FA Cup")
    _fps(league_fx, player, club, minutes=2500, goals=5, assists=4, rating=7.0)
    _fps(cup_fx, player, club, minutes=441, goals=1, assists=1, rating=8.0)
    j = _journey(player)
    _entry(
        j,
        player,
        2025,
        club,
        minutes=2500,
        goals=7,
        assists=6,
        apps=30,
        club_name="Rotherham United",
        stats_source="journey-api",
        rating=9.0,
    )
    journey_cup = _entry(
        j,
        player,
        2025,
        club,
        minutes=436,
        goals=2,
        assists=1,
        apps=4,
        club_name="Rotherham United",
        league_name="FA Cup",
        stats_source="journey-api",
        rating=10.0,
    )
    db.session.commit()

    svc.refresh_player(player, season=2025)
    db.session.commit()

    cells = {
        (cell.source, cell.competition_tier): cell
        for cell in PlayerSeasonCell.query.filter_by(player_api_id=player, season=2025).all()
    }
    assert set(cells) == {
        ("fixtures", "league"),
        ("fixtures", "domestic_cup"),
        ("journey", "league"),
        ("journey", "domestic_cup"),
    }
    assert {key: cell.minutes for key, cell in cells.items()} == {
        ("fixtures", "league"): 2500,
        ("fixtures", "domestic_cup"): 441,
        ("journey", "league"): 2500,
        ("journey", "domestic_cup"): 436,
    }
    assert all(cell.club_api_id == club for cell in cells.values())

    total = PlayerSeasonTotal.query.filter_by(player_api_id=player, season=2025, level_group="senior").one()
    assert (total.primary_source, total.minutes, total.reconcile_flag) == (
        "fixtures",
        2941,
        "journey-under-sync",
    )
    assert (total.appearances, total.goals, total.assists) == (2, 6, 5)
    assert total.fixtures_minutes == 2941
    assert total.journey_minutes == 2936
    assert total.source_breakdown["fixtures"]["minutes"] == 2941
    assert total.source_breakdown["journey"]["minutes"] == 2936
    expected_fixture_rating = (7.0 * 2500 + 8.0 * 441) / 2941
    assert float(total.avg_rating) == pytest.approx(expected_fixture_rating, abs=0.01)

    # Journey catches up: refreshing must replace its cup cell and flip every
    # headline stat to the journey subtotal, never add the two sources.
    journey_cup.minutes = 500
    db.session.commit()
    db.session.expunge_all()
    svc.refresh_player(player, season=2025)
    db.session.commit()

    refreshed_cells = {
        (cell.source, cell.competition_tier): cell
        for cell in PlayerSeasonCell.query.filter_by(player_api_id=player, season=2025).all()
    }
    assert len(refreshed_cells) == 4
    assert refreshed_cells[("fixtures", "league")].minutes == 2500
    assert refreshed_cells[("fixtures", "domestic_cup")].minutes == 441
    assert refreshed_cells[("journey", "league")].minutes == 2500
    assert refreshed_cells[("journey", "domestic_cup")].minutes == 500

    refreshed = PlayerSeasonTotal.query.filter_by(player_api_id=player, season=2025, level_group="senior").one()
    assert (refreshed.primary_source, refreshed.minutes, refreshed.reconcile_flag) == (
        "journey",
        3000,
        "cup-gap",
    )
    assert (refreshed.appearances, refreshed.goals, refreshed.assists) == (34, 9, 7)
    assert (refreshed.fixtures_minutes, refreshed.journey_minutes) == (2941, 3000)
    assert refreshed.source_breakdown["fixtures"]["minutes"] == 2941
    assert refreshed.source_breakdown["journey"]["minutes"] == 3000
    assert float(refreshed.avg_rating) == pytest.approx(expected_fixture_rating, abs=0.01)


def test_fixtures_invisible(app):
    player = 555
    j = _journey(player)
    _entry(j, player, 2025, 200, minutes=1500, goals=3, stats_source="journey-api", rating=9.75)
    db.session.commit()
    svc.refresh_player(player, season=2025)
    db.session.commit()

    total = PlayerSeasonTotal.query.filter_by(player_api_id=player, level_group="senior").one()
    assert total.primary_source == "journey"
    assert total.minutes == 1500
    assert total.fixtures_minutes == 0
    assert total.reconcile_flag == "fixtures-invisible"
    journey_cell = PlayerSeasonCell.query.filter_by(player_api_id=player, source="journey").one()
    assert float(journey_cell.avg_rating) == pytest.approx(9.75)
    assert total.avg_rating is None  # a real journey rating never feeds the total


def test_journey_under_sync(app):
    """fixtures strictly larger → headline fixtures, flag journey-under-sync."""
    player = 777
    fx = _fixture(10, 2025)
    _fps(fx, player, 300, minutes=2000, goals=4, rating=7.5)
    j = _journey(player)
    _entry(j, player, 2025, 300, minutes=1500, goals=3)
    db.session.commit()
    svc.refresh_player(player, season=2025)
    db.session.commit()

    total = PlayerSeasonTotal.query.filter_by(player_api_id=player, level_group="senior").one()
    assert total.primary_source == "fixtures"
    assert total.minutes == 2000
    assert total.fixtures_minutes == 2000
    assert total.journey_minutes == 1500
    assert total.reconcile_flag == "journey-under-sync"


def test_level_group_split(app):
    """youth + senior + international journey entries → three totals rows."""
    player = 888
    j = _journey(player)
    _entry(j, player, 2025, 400, minutes=1200, goals=2)  # senior
    _entry(j, player, 2025, 401, minutes=800, goals=1, is_youth=True, league_name="U21 Premier League")
    _entry(j, player, 2025, 402, minutes=270, goals=1, is_international=True, league_name="Euro U21")
    db.session.commit()
    svc.refresh_player(player, season=2025)
    db.session.commit()

    groups = {t.level_group: t for t in PlayerSeasonTotal.query.filter_by(player_api_id=player).all()}
    assert set(groups) == {"senior", "youth", "international"}
    assert groups["senior"].minutes == 1200
    assert groups["youth"].minutes == 800
    assert groups["international"].minutes == 270


def test_youth_apss_and_shadow_sources(app):
    """APSS feeds youth; shadow feeds senior; both appear in source_breakdown."""
    player = 999
    db.session.add(
        AcademyPlayerSeasonStats(
            player_api_id=player,
            league_api_id=1,
            season=2025,
            team_api_id=500,
            team_name="Academy",
            appearances=10,
            minutes=850,
            goals=4,
            rating=7.2,
        )
    )
    db.session.add(
        PlayerShadowStats(
            player_api_id=player, team_api_id=600, team_name="Shadow FC", season=2025, minutes=900, goals=2
        )
    )
    db.session.commit()
    svc.refresh_player(player, season=2025)
    db.session.commit()

    youth = PlayerSeasonTotal.query.filter_by(player_api_id=player, level_group="youth").one()
    assert youth.primary_source == "apss"
    assert youth.minutes == 850
    senior = PlayerSeasonTotal.query.filter_by(player_api_id=player, level_group="senior").one()
    assert senior.primary_source == "shadow"
    assert senior.minutes == 900


def test_noise_filter_skips_empty_stub(app):
    """0 apps AND 0 min AND 0 goals produces no cell and no total (the 740 stubs)."""
    player = 111
    j = _journey(player)
    _entry(j, player, 2026, 700, minutes=0, goals=0, apps=0)  # pre-season stub
    _entry(j, player, 2025, 700, minutes=900, goals=2, apps=12)  # real
    db.session.commit()
    svc.refresh_player(player)  # season=None → all seasons
    db.session.commit()

    assert PlayerSeasonTotal.query.filter_by(player_api_id=player, season=2026).count() == 0
    assert PlayerSeasonCell.query.filter_by(player_api_id=player, season=2026).count() == 0
    assert PlayerSeasonTotal.query.filter_by(player_api_id=player, season=2025).count() == 1


def test_refresh_is_idempotent(app):
    player = 222
    fx = _fixture(20, 2025)
    _fps(fx, player, 800, minutes=90, goals=1, rating=7.0)
    j = _journey(player)
    _entry(j, player, 2025, 800, minutes=95, goals=1)
    db.session.commit()

    svc.refresh_player(player, season=2025)
    db.session.commit()
    svc.refresh_player(player, season=2025)
    db.session.commit()

    assert PlayerSeasonTotal.query.filter_by(player_api_id=player, season=2025).count() == 1
    # one journey cell + one fixtures cell, not duplicated
    assert PlayerSeasonCell.query.filter_by(player_api_id=player, season=2025).count() == 2


def test_refresh_participates_in_caller_transaction(app):
    """refresh_player does not commit — a caller rollback discards the rollup."""
    player = 333
    j = _journey(player)
    _entry(j, player, 2025, 900, minutes=500, goals=1)
    db.session.commit()

    svc.refresh_player(player, season=2025)
    assert PlayerSeasonTotal.query.filter_by(player_api_id=player).count() == 1  # visible pre-commit
    db.session.rollback()
    assert PlayerSeasonTotal.query.filter_by(player_api_id=player).count() == 0  # rolled back


def test_season_scoped_refresh_leaves_other_seasons(app):
    player = 444
    j = _journey(player)
    _entry(j, player, 2024, 100, minutes=1000, goals=2)
    _entry(j, player, 2025, 100, minutes=1100, goals=3)
    db.session.commit()
    svc.refresh_player(player)  # build both
    db.session.commit()

    # Re-refresh only 2025 — 2024 totals must remain untouched.
    svc.refresh_player(player, season=2025)
    db.session.commit()
    assert PlayerSeasonTotal.query.filter_by(player_api_id=player, season=2024).count() == 1
    assert PlayerSeasonTotal.query.filter_by(player_api_id=player, season=2025).count() == 1


# ---------------------------------------------------------------------------
# choke point
# ---------------------------------------------------------------------------
def test_choke_queue_dedups_and_batches(app):
    """Enqueue same (player, season) 3× → one refresh; batch of 2 players → one flush."""
    p1, p2 = 1001, 1002
    for p in (p1, p2):
        j = _journey(p)
        _entry(j, p, 2025, 100, minutes=800, goals=1)
    db.session.commit()

    svc.queue_player_refresh(p1, 2025)
    svc.queue_player_refresh(p1, 2025)
    svc.queue_player_refresh(p1, 2025)
    svc.queue_player_refresh(p2, 2025)
    assert db.session.info[svc._DIRTY_KEY] == {(p1, 2025), (p2, 2025)}

    refreshed = svc.flush_player_refresh_queue()
    assert refreshed == 2
    assert not db.session.info[svc._DIRTY_KEY]  # drained
    assert PlayerSeasonTotal.query.filter_by(season=2025).count() == 2


def test_flush_empty_queue_is_noop(app):
    assert svc.flush_player_refresh_queue() == 0


def test_choke_flush_commits(app):
    """flush owns its own commit — rollup persists without a caller commit."""
    player = 1003
    j = _journey(player)
    _entry(j, player, 2025, 100, minutes=700, goals=1)
    db.session.commit()

    svc.queue_player_refresh(player, 2025)
    svc.flush_player_refresh_queue()
    db.session.remove()  # brand-new session; only committed rows survive
    assert PlayerSeasonTotal.query.filter_by(player_api_id=player).count() == 1


def test_choke_flush_requeues_failed_pair_for_retry(app, monkeypatch):
    player = 1004
    journey = _journey(player)
    _entry(journey, player, 2025, 100, minutes=600, goals=1)
    db.session.commit()

    real_refresh = svc.refresh_player
    calls = []

    def _fail_once(player_api_id, season=None, session=None):
        calls.append((player_api_id, season))
        if len(calls) == 1:
            raise RuntimeError("transient rollup failure")
        return real_refresh(player_api_id, season=season, session=session)

    monkeypatch.setattr(svc, "refresh_player", _fail_once)
    svc.queue_player_refresh(player, 2025)

    assert svc.flush_player_refresh_queue() == 0
    assert db.session.info[svc._DIRTY_KEY] == {(player, 2025)}
    assert PlayerSeasonTotal.query.filter_by(player_api_id=player).count() == 0

    assert svc.flush_player_refresh_queue() == 1
    assert not db.session.info[svc._DIRTY_KEY]
    total = PlayerSeasonTotal.query.filter_by(player_api_id=player, season=2025).one()
    assert total.minutes == 600
    assert calls == [(player, 2025), (player, 2025)]


# ---------------------------------------------------------------------------
# real producer hooks + journey savepoint mechanics
# ---------------------------------------------------------------------------
def test_journey_sync_hook_builds_cells_and_totals_end_to_end(app):
    """The real sync_player hook persists journey data and its rollup together."""
    from src.services.journey_sync import JourneySyncService

    player = 2000

    class FakeJourneyApi:
        def _make_request(self, endpoint, params):
            if endpoint == "players/seasons":
                assert params == {"player": player}
                return {"response": [2025]}
            if endpoint == "players":
                assert params == {"id": player, "season": 2025}
                return {
                    "response": [
                        {
                            "player": {
                                "id": player,
                                "name": "Hook Player",
                                "birth": {},
                                "nationality": "England",
                            },
                            "statistics": [
                                {
                                    "team": {"id": 77, "name": "Rotherham United"},
                                    "league": {"id": 40, "name": "Championship", "country": "England"},
                                    "games": {"appearences": 10, "minutes": 900, "rating": "7.40"},
                                    "goals": {"total": 2, "assists": 3},
                                }
                            ],
                        }
                    ]
                }
            raise AssertionError(f"unexpected API request: {endpoint} {params}")

        def get_player_transfers(self, player_api_id):
            assert player_api_id == player
            return []

    journey = JourneySyncService(api_client=FakeJourneyApi()).sync_player(player, force_full=True)

    assert journey is not None
    entry = PlayerJourneyEntry.query.filter_by(player_api_id=player, season=2025).one()
    assert (entry.club_api_id, entry.appearances, entry.minutes, entry.goals) == (77, 10, 900, 2)
    cell = PlayerSeasonCell.query.filter_by(player_api_id=player, season=2025, source="journey").one()
    assert (cell.club_api_id, cell.appearances, cell.minutes, cell.goals) == (77, 10, 900, 2)
    total = PlayerSeasonTotal.query.filter_by(player_api_id=player, season=2025, level_group="senior").one()
    assert (total.primary_source, total.minutes, total.goals, total.reconcile_flag) == (
        "journey",
        900,
        2,
        "fixtures-invisible",
    )


def test_fps_writer_choke_point_refreshes_player_season(app, monkeypatch):
    """A real fixture producer queues, commits, and drains the rollup refresh."""
    from src.routes import api as api_routes

    player = 2003
    fixture_payload = {
        "fixture": {
            "id": 9001,
            "date": "2025-09-13T15:00:00+00:00",
            "status": {"short": "FT"},
        },
        "league": {"name": "League One", "season": 2025},
        "teams": {
            "home": {"id": 77, "name": "Rotherham United"},
            "away": {"id": 88, "name": "Opponent"},
        },
        "goals": {"home": 2, "away": 0},
    }

    class FakeFixtureApi:
        def get_fixtures_for_team_cached(self, team_id, season, start, end):
            assert (team_id, season, start) == (77, 2025, "2025-08-01")
            assert end >= start
            return [fixture_payload]

        def get_player_stats_for_fixture(self, player_api_id, season, fixture_id):
            assert (player_api_id, season, fixture_id) == (player, 2025, 9001)
            return {
                "statistics": [
                    {
                        "games": {"minutes": 90, "substitute": False, "position": "Midfielder", "rating": 7.6},
                        "goals": {"total": 1, "assists": 1},
                    }
                ]
            }

        def get_fixture_lineups(self, fixture_id):
            assert fixture_id == 9001
            return {"response": []}

    monkeypatch.setattr("src.api_football_client.APIFootballClient", lambda: FakeFixtureApi())

    assert api_routes._sync_player_club_fixtures(player, 77, 2025) == 1
    fps = FixturePlayerStats.query.filter_by(player_api_id=player).one()
    assert (fps.minutes, fps.goals, fps.assists) == (90, 1, 1)
    cell = PlayerSeasonCell.query.filter_by(player_api_id=player, season=2025, source="fixtures").one()
    assert (cell.minutes, cell.goals, cell.assists) == (90, 1, 1)
    total = PlayerSeasonTotal.query.filter_by(player_api_id=player, season=2025, level_group="senior").one()
    assert (total.primary_source, total.minutes, total.goals, total.assists) == ("fixtures", 90, 1, 1)
    assert not db.session.info.get(svc._DIRTY_KEY)


def test_journey_hook_savepoint_atomic(app):
    """Mirror JourneySyncService.sync_player's hook: flush entries, refresh
    inside a SAVEPOINT, then ONE outer commit persists journey + rollup."""
    player = 2001
    j = _journey(player)
    _entry(j, player, 2025, 100, minutes=1000, goals=2)
    db.session.flush()
    with db.session.begin_nested():
        svc.refresh_player(player, season=2025, session=db.session)
    db.session.commit()

    db.session.remove()  # fresh session — only committed rows survive
    assert PlayerJourneyEntry.query.filter_by(player_api_id=player).count() == 1
    assert PlayerSeasonTotal.query.filter_by(player_api_id=player, season=2025).count() == 1


def test_journey_hook_savepoint_rollback_preserves_journey(app, monkeypatch):
    """A refresh failure rolls back ONLY the derived rows (savepoint); the
    API-expensive journey write still commits."""
    player = 2002
    j = _journey(player)
    _entry(j, player, 2025, 100, minutes=1000, goals=2)
    db.session.flush()

    def _boom(*a, **k):
        raise RuntimeError("simulated rollup failure")

    monkeypatch.setattr(svc, "refresh_player", _boom)
    try:
        with db.session.begin_nested():
            svc.refresh_player(player, season=2025, session=db.session)
    except RuntimeError:
        pass  # exactly what sync_player's try/except does
    db.session.commit()

    db.session.remove()
    assert PlayerJourneyEntry.query.filter_by(player_api_id=player).count() == 1  # journey survived
    assert PlayerSeasonTotal.query.filter_by(player_api_id=player).count() == 0  # rollup rolled back


# ---------------------------------------------------------------------------
# youth-fixture level_group (regression: youth-team FPS must not read senior)
# ---------------------------------------------------------------------------
def test_youth_fixture_folds_into_youth_level_group(app):
    """A youth-team FPS row (academy sync path, e.g. 'Premier League 2') folds
    into the youth level_group, never senior — a pure academy kid must not rank
    on the senior Scout list on U21 minutes (proposal §6 Q10)."""
    player = 606
    senior_fx = _fixture(30, 2025, comp="Championship")
    youth_fx = _fixture(31, 2025, comp="Premier League 2 Division One")
    _fps(senior_fx, player, 100, minutes=900, goals=2, rating=7.0)
    _fps(youth_fx, player, 101, minutes=800, goals=5, rating=8.0)
    db.session.commit()

    svc.refresh_player(player, season=2025)
    db.session.commit()

    groups = {t.level_group: t for t in PlayerSeasonTotal.query.filter_by(player_api_id=player).all()}
    assert set(groups) == {"senior", "youth"}
    assert groups["senior"].minutes == 900
    assert groups["senior"].primary_source == "fixtures"
    assert groups["youth"].minutes == 800
    assert groups["youth"].primary_source == "fixtures"
    youth_cells = PlayerSeasonCell.query.filter_by(player_api_id=player, level_group="youth").all()
    assert youth_cells and all(c.competition_tier == "youth" for c in youth_cells)


def test_youth_competition_classifier():
    assert svc._is_youth_competition("Premier League 2 Division One") is True
    assert svc._is_youth_competition("U18 Premier League - North") is True
    assert svc._is_youth_competition("UEFA Youth League") is True
    assert svc._is_youth_competition("Premier League") is False
    assert svc._is_youth_competition("Championship") is False
    assert svc._is_youth_competition(None) is False
    assert svc._fixture_level_and_tier("Premier League 2 Division One") == ("youth", "youth")
    assert svc._fixture_level_and_tier("Premier League") == ("senior", "league")


# ---------------------------------------------------------------------------
# journey feeder robustness (regression: NULL denormalized player_api_id)
# ---------------------------------------------------------------------------
def test_journey_feeder_reads_via_journey_join_when_denorm_null(app):
    """PJE rows with a NULL denormalized player_api_id (every ~77k legacy row
    pre-sea01-backfill) still feed the rollup, resolved through the parent
    journey — otherwise a pre-backfill refresh silently drops the journey source
    and the Gore anchor would not hold in prod."""
    player = 707
    j = _journey(player)
    db.session.add(
        PlayerJourneyEntry(
            journey_id=j.id,
            player_api_id=None,  # legacy row: denormalized column unset
            season=2025,
            club_api_id=808,
            club_name="Legacy FC",
            league_name="Championship",
            minutes=1800,
            goals=4,
            appearances=20,
            stats_source="legacy-basic",
        )
    )
    db.session.commit()

    svc.refresh_player(player, season=2025)
    db.session.commit()

    total = PlayerSeasonTotal.query.filter_by(player_api_id=player, level_group="senior").one()
    assert total.primary_source == "journey"
    assert total.minutes == 1800
    assert total.journey_minutes == 1800


# ---------------------------------------------------------------------------
# tier classifier
# ---------------------------------------------------------------------------
def test_competition_tier_classifier():
    assert svc.classify_competition_tier("Premier League") == "league"
    assert svc.classify_competition_tier("FA Cup") == "domestic_cup"
    assert svc.classify_competition_tier("Carabao Cup") == "league_cup"
    assert svc.classify_competition_tier("UEFA Champions League") == "continental"
    assert svc.classify_competition_tier(None) == "league"
