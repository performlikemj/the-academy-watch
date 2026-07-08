"""D3b season-rollup service — feeders, totals resolution, choke point.

The anchor test (proposal §2, gates everything): Gore-shaped player, season 2025
senior → minutes = the journey figure taken whole, primary_source=journey,
fixtures_minutes < journey_minutes, reconcile_flag='cup-gap', avg_rating
fixtures-sourced. Plus the other coverage-map buckets, level_group split, the
noise filter, refresh idempotency/transactionality, and choke-point batching.
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
    )
    db.session.add(e)
    return e


# ---------------------------------------------------------------------------
# anchor + coverage buckets
# ---------------------------------------------------------------------------
def test_gore_anchor_cup_gap(app):
    """fixtures 2583 < journey 2936 → headline journey 2936, flag cup-gap."""
    player = 303010
    fx1 = _fixture(1, 2025)
    fx2 = _fixture(2, 2025)
    _fps(fx1, player, 100, minutes=1290, goals=5, rating=7.0)
    _fps(fx2, player, 100, minutes=1293, goals=6, rating=8.0)  # fixtures = 2583 min
    j = _journey(player)
    _entry(j, player, 2025, 100, minutes=1468, goals=6, apps=17)
    _entry(j, player, 2025, 100, minutes=1468, goals=6, apps=17, league_name="FA Cup")  # journey = 2936
    db.session.commit()

    svc.refresh_player(player, season=2025)
    db.session.commit()

    total = PlayerSeasonTotal.query.filter_by(player_api_id=player, season=2025, level_group="senior").one()
    assert total.minutes == 2936
    assert total.primary_source == "journey"
    assert total.fixtures_minutes == 2583
    assert total.journey_minutes == 2936
    assert total.reconcile_flag == "cup-gap"
    # avg_rating ALWAYS fixtures-sourced (minutes-weighted 7.0/8.0).
    assert total.avg_rating is not None
    assert abs(float(total.avg_rating) - (7.0 * 1290 + 8.0 * 1293) / 2583) < 0.01
    # both sources visible in the breakdown; headline never a cross-source sum.
    assert set(total.source_breakdown) == {"fixtures", "journey"}


def test_fixtures_invisible(app):
    player = 555
    j = _journey(player)
    _entry(j, player, 2025, 200, minutes=1500, goals=3)
    db.session.commit()
    svc.refresh_player(player, season=2025)
    db.session.commit()

    total = PlayerSeasonTotal.query.filter_by(player_api_id=player, level_group="senior").one()
    assert total.primary_source == "journey"
    assert total.minutes == 1500
    assert total.fixtures_minutes == 0
    assert total.reconcile_flag == "fixtures-invisible"
    assert total.avg_rating is None  # no fixtures


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


# ---------------------------------------------------------------------------
# journey hook mechanics (savepoint-wrapped refresh, same transaction)
# ---------------------------------------------------------------------------
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
# tier classifier
# ---------------------------------------------------------------------------
def test_competition_tier_classifier():
    assert svc.classify_competition_tier("Premier League") == "league"
    assert svc.classify_competition_tier("FA Cup") == "domestic_cup"
    assert svc.classify_competition_tier("Carabao Cup") == "league_cup"
    assert svc.classify_competition_tier("UEFA Champions League") == "continental"
    assert svc.classify_competition_tier(None) == "league"
