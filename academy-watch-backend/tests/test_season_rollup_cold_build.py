"""D4a off-container season-rollup cold-build runner."""

from datetime import UTC, datetime

import pytest
from flask import Flask
from sqlalchemy import select
from sqlalchemy.engine import make_url
from src.models.follow import PlayerShadowStats
from src.models.journey import PlayerJourney, PlayerJourneyEntry
from src.models.league import AcademyPlayerSeasonStats, db
from src.models.season_rollup import PlayerSeasonCell, PlayerSeasonTotal
from src.models.weekly import Fixture, FixturePlayerStats
from src.routes import season_rollup as admin_routes
from src.scripts import season_rollup_cold_build as runner

SEASON = 2025
MARKER_TIME = datetime(2020, 1, 1, tzinfo=UTC)


@pytest.fixture
def app():
    application = Flask(__name__)
    application.config.update(
        TESTING=True,
        SECRET_KEY="test-secret",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(application)

    context = application.app_context()
    context.push()
    db.create_all()
    yield application
    db.session.remove()
    db.drop_all()
    context.pop()


def _shadow(player_api_id: int, *, season: int = SEASON, minutes: int = 90) -> PlayerShadowStats:
    row = PlayerShadowStats(
        player_api_id=player_api_id,
        team_api_id=player_api_id + 1000,
        team_name=f"Shadow {player_api_id}",
        season=season,
        appearances=1,
        goals=0,
        assists=0,
        minutes=minutes,
    )
    db.session.add(row)
    return row


def _apss(player_api_id: int) -> AcademyPlayerSeasonStats:
    row = AcademyPlayerSeasonStats(
        player_api_id=player_api_id,
        player_name=f"Academy {player_api_id}",
        league_api_id=player_api_id + 2000,
        league_name="Youth League",
        team_api_id=player_api_id + 3000,
        team_name=f"Academy {player_api_id}",
        season=SEASON,
        appearances=1,
        goals=0,
        assists=0,
        minutes=90,
    )
    db.session.add(row)
    return row


def _orphan_total(player_api_id: int) -> PlayerSeasonTotal:
    row = PlayerSeasonTotal(
        player_api_id=player_api_id,
        season=SEASON,
        level_group="senior",
        appearances=1,
        goals=0,
        assists=0,
        minutes=90,
        primary_source="shadow",
        fixtures_minutes=0,
        journey_minutes=0,
        computed_at=MARKER_TIME,
    )
    db.session.add(row)
    return row


def _orphan_cell(player_api_id: int) -> PlayerSeasonCell:
    row = PlayerSeasonCell(
        player_api_id=player_api_id,
        season=SEASON,
        source="shadow",
        club_api_id=player_api_id + 4000,
        club_name=f"Orphan {player_api_id}",
        competition_tier="league",
        level_group="senior",
        appearances=1,
        goals=0,
        assists=0,
        minutes=90,
        synced_at=MARKER_TIME,
    )
    db.session.add(row)
    return row


def _invoke(app, monkeypatch, *args: str) -> int:
    monkeypatch.setattr(runner, "get_app", lambda: app)
    return runner.main(list(args))


def _route_candidate_ids(*, season: int | None = None) -> list[int]:
    candidates = admin_routes._candidate_player_ids(season=season).subquery()
    return list(db.session.execute(select(candidates.c.player_api_id).order_by(candidates.c.player_api_id)).scalars())


def test_players_mode_builds_only_requested_players(app, monkeypatch, capsys):
    _shadow(101, season=2024)
    for player_api_id in (101, 102, 103):
        _shadow(player_api_id)
    db.session.commit()

    # Give the unrequested player an old rollup marker so the test catches an
    # accidental population scan or refresh, not only an accidental insert.
    runner.season_rollup_service.refresh_player(102, season=SEASON, session=db.session)
    untouched_total = PlayerSeasonTotal.query.filter_by(player_api_id=102, season=SEASON).one()
    untouched_cell = PlayerSeasonCell.query.filter_by(player_api_id=102, season=SEASON).one()
    untouched_total.computed_at = MARKER_TIME
    untouched_cell.synced_at = MARKER_TIME
    db.session.commit()

    real_commit = db.session.commit
    commit_count = 0

    def _counted_commit():
        nonlocal commit_count
        commit_count += 1
        return real_commit()

    monkeypatch.setattr(db.session, "commit", _counted_commit)

    result = _invoke(
        app,
        monkeypatch,
        "--players",
        "103,101,103",
        "--season",
        str(SEASON),
        "--batch-size",
        "1",
    )

    assert result == 0
    output_lines = capsys.readouterr().out.splitlines()
    assert len([line for line in output_lines if line.startswith("processed=")]) == 2
    assert commit_count == 2
    db.session.expire_all()
    assert {
        (row.player_api_id, row.season, row.source)
        for row in PlayerSeasonCell.query.order_by(PlayerSeasonCell.player_api_id, PlayerSeasonCell.season)
    } == {
        (101, SEASON, "shadow"),
        (102, SEASON, "shadow"),
        (103, SEASON, "shadow"),
    }
    assert {
        (row.player_api_id, row.season, row.primary_source)
        for row in PlayerSeasonTotal.query.order_by(PlayerSeasonTotal.player_api_id, PlayerSeasonTotal.season)
    } == {
        (101, SEASON, "shadow"),
        (102, SEASON, "shadow"),
        (103, SEASON, "shadow"),
    }
    assert PlayerSeasonCell.query.filter_by(player_api_id=101, season=2024).count() == 0
    assert PlayerSeasonTotal.query.filter_by(player_api_id=101, season=2024).count() == 0
    assert PlayerSeasonTotal.query.filter_by(player_api_id=102).one().computed_at == MARKER_TIME.replace(tzinfo=None)
    assert PlayerSeasonCell.query.filter_by(player_api_id=102).one().synced_at == MARKER_TIME.replace(tzinfo=None)


def test_all_mode_after_limit_resume_matches_endpoint_population(app, monkeypatch):
    fixture = Fixture(fixture_id_api=10, season=SEASON, competition_name="Premier League")
    db.session.add(fixture)
    db.session.flush()
    db.session.add(
        FixturePlayerStats(
            fixture_id=fixture.id,
            player_api_id=10,
            team_api_id=1010,
            minutes=90,
            goals=0,
            assists=0,
        )
    )
    _apss(20)
    _shadow(30)
    journey = PlayerJourney(player_api_id=40, player_name="Legacy Journey")
    db.session.add(journey)
    db.session.flush()
    db.session.add(
        PlayerJourneyEntry(
            journey_id=journey.id,
            player_api_id=None,
            season=SEASON,
            club_api_id=4040,
            club_name="Journey Club",
            appearances=1,
            minutes=90,
            goals=0,
        )
    )
    _orphan_total(50)
    _orphan_cell(60)
    db.session.commit()

    expected = _route_candidate_ids(season=SEASON)
    assert expected == [10, 20, 30, 40, 50, 60]

    real_refresh = runner.season_rollup_service.refresh_player
    calls: list[tuple[int, int | None]] = []

    def _recording_refresh(player_api_id, season=None, session=None):
        calls.append((player_api_id, season))
        return real_refresh(player_api_id, season=season, session=session)

    monkeypatch.setattr(runner.season_rollup_service, "refresh_player", _recording_refresh)

    cursor = 0
    for expected_page in ([10, 20], [30, 40], [50, 60]):
        result = _invoke(
            app,
            monkeypatch,
            "--all",
            "--season",
            str(SEASON),
            "--after",
            str(cursor),
            "--limit",
            "2",
            "--batch-size",
            "2",
        )
        assert result == 0
        assert [player_api_id for player_api_id, _season in calls[-2:]] == expected_page
        cursor = expected_page[-1]

    assert calls == [(player_api_id, SEASON) for player_api_id in expected]
    db.session.expire_all()
    assert {row.player_api_id for row in PlayerSeasonTotal.query.all()} == {10, 20, 30, 40}
    assert {row.player_api_id for row in PlayerSeasonCell.query.all()} == {10, 20, 30, 40}
    assert PlayerSeasonTotal.query.filter_by(player_api_id=50).count() == 0
    assert PlayerSeasonCell.query.filter_by(player_api_id=60).count() == 0


def test_poison_player_is_skipped_reported_and_batch_commits_survive(app, monkeypatch, capsys):
    for player_api_id in (201, 202, 203):
        _shadow(player_api_id)
    db.session.commit()

    real_refresh = runner.season_rollup_service.refresh_player

    def _poison_after_writes(player_api_id, season=None, session=None):
        result = real_refresh(player_api_id, season=season, session=session)
        if player_api_id == 202:
            raise RuntimeError("poison player")
        return result

    monkeypatch.setattr(runner.season_rollup_service, "refresh_player", _poison_after_writes)

    result = _invoke(app, monkeypatch, "--players", "203,201,202", "--batch-size", "3")

    assert result == 0
    output = capsys.readouterr().out
    assert "processed=2 failed=1 last_id=203" in output
    assert "summary processed=2 failed=1 failed_ids=[202]" in output

    # A fresh session proves the successful siblings reached the outer commit,
    # while the poison player's writes were rolled back to its SAVEPOINT.
    db.session.remove()
    assert {row.player_api_id for row in PlayerSeasonCell.query.all()} == {201, 203}
    assert {row.player_api_id for row in PlayerSeasonTotal.query.all()} == {201, 203}
    assert {row.player_api_id for row in PlayerShadowStats.query.all()} == {201, 202, 203}


def test_dry_run_reports_candidate_bounds_without_writes(app, monkeypatch, capsys):
    _shadow(301)
    _shadow(303)
    _orphan_total(305)
    db.session.commit()

    before = [
        (row.id, row.player_api_id, row.season, row.computed_at)
        for row in PlayerSeasonTotal.query.order_by(PlayerSeasonTotal.id)
    ]
    source_before = [
        (row.id, row.player_api_id, row.season, row.minutes)
        for row in PlayerShadowStats.query.order_by(PlayerShadowStats.id)
    ]

    def _unexpected_refresh(*_args, **_kwargs):
        pytest.fail("dry-run must not call refresh_player")

    monkeypatch.setattr(runner.season_rollup_service, "refresh_player", _unexpected_refresh)

    result = _invoke(app, monkeypatch, "--all", "--season", str(SEASON), "--dry-run")

    assert result == 0
    assert capsys.readouterr().out == "candidates=3 first_id=301 last_id=305\n"
    after = [
        (row.id, row.player_api_id, row.season, row.computed_at)
        for row in PlayerSeasonTotal.query.order_by(PlayerSeasonTotal.id)
    ]
    assert after == before
    assert [
        (row.id, row.player_api_id, row.season, row.minutes)
        for row in PlayerShadowStats.query.order_by(PlayerShadowStats.id)
    ] == source_before
    assert PlayerSeasonCell.query.count() == 0


def test_database_bootstrap_uses_only_app_db_components(monkeypatch):
    monkeypatch.setattr(runner.dotenv, "load_dotenv", lambda *_args, **_kwargs: False)
    monkeypatch.setenv("SQLALCHEMY_DATABASE_URI", "sqlite:///must-not-win.db")
    monkeypatch.setenv("DB_USER", "pooler-user")
    monkeypatch.setenv("DB_PASSWORD", "pooler-password")
    monkeypatch.setenv("DB_HOST", "pooler.example.test")
    monkeypatch.setenv("DB_PORT", "6543")
    monkeypatch.setenv("DB_NAME", "academy-watch")
    monkeypatch.setenv("DB_SSLMODE", "verify-full")

    application = runner.get_app()
    url = make_url(application.config["SQLALCHEMY_DATABASE_URI"])

    assert url.drivername == "postgresql+psycopg"
    assert (url.username, url.password) == ("pooler-user", "pooler-password")
    assert (url.host, url.port, url.database) == ("pooler.example.test", 6543, "academy-watch")
    assert url.query["sslmode"] == "verify-full"
    assert application.config["SQLALCHEMY_ENGINE_OPTIONS"] == {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }


def test_setup_failure_returns_nonzero(monkeypatch):
    def _fatal_app_setup():
        raise RuntimeError("database bootstrap failed")

    monkeypatch.setattr(runner, "get_app", _fatal_app_setup)

    assert runner.main(["--all"]) == 1


def test_runner_refuses_azure_container_app_environment(monkeypatch):
    monkeypatch.setenv("CONTAINER_APP_REVISION", "ca-loan-army-backend--revision")

    def _unexpected_app_setup():
        pytest.fail("container guard must run before database setup")

    monkeypatch.setattr(runner, "get_app", _unexpected_app_setup)

    assert runner.main(["--all"]) == 1
