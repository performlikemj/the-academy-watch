"""D3c admin rebuild surface and rows-behind gauge."""

from datetime import UTC, datetime, timedelta

import pytest
from flask import Flask
from sqlalchemy.dialects import postgresql
from src.models.follow import PlayerShadowStats
from src.models.journey import PlayerJourney, PlayerJourneyEntry
from src.models.league import AcademyPlayerSeasonStats, Team, db
from src.models.season_rollup import PlayerSeasonCell, PlayerSeasonTotal
from src.models.tracked_player import TrackedPlayer
from src.models.weekly import Fixture, FixturePlayerStats
from src.routes import season_rollup as admin_routes
from src.routes.api import api_bp
from src.routes.season_rollup import season_rollup_bp

ADMIN_KEY = "test-admin-key"
REBUILD_URL = "/api/admin/season-rollup/rebuild"
STATUS_URL = "/api/admin/season-rollup/status"
NOW = datetime(2026, 7, 15, 0, tzinfo=UTC)


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", ADMIN_KEY)
    monkeypatch.setenv("ADMIN_IP_WHITELIST", "")

    application = Flask(__name__)
    application.config.update(
        TESTING=True,
        SECRET_KEY="test-secret-key",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(application)
    application.register_blueprint(api_bp, url_prefix="/api")
    application.register_blueprint(season_rollup_bp, url_prefix="/api")

    context = application.app_context()
    context.push()
    db.create_all()
    yield application
    db.session.remove()
    db.drop_all()
    context.pop()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def admin_headers(app):
    from src.auth import issue_user_token

    token = issue_user_token("admin@test.com", role="admin")["token"]
    return {"Authorization": f"Bearer {token}", "X-API-Key": ADMIN_KEY}


def _shadow(player: int, *, season: int = 2025, updated_at=NOW, minutes: int = 90):
    row = PlayerShadowStats(
        player_api_id=player,
        team_api_id=player + 1000,
        team_name=f"Shadow {player}",
        season=season,
        appearances=1 if minutes else 0,
        goals=0,
        minutes=minutes,
        updated_at=updated_at,
    )
    db.session.add(row)
    return row


def _apss(player: int, *, updated_at=NOW, minutes: int = 90):
    row = AcademyPlayerSeasonStats(
        player_api_id=player,
        player_name=f"Academy {player}",
        league_api_id=700 + player,
        league_name="Youth League",
        team_api_id=player + 2000,
        team_name=f"Academy {player}",
        season=2025,
        appearances=1 if minutes else 0,
        goals=0,
        minutes=minutes,
        updated_at=updated_at,
    )
    db.session.add(row)
    return row


def _total(
    player: int,
    *,
    season: int = 2025,
    level_group: str = "senior",
    computed_at=NOW,
    primary_source: str = "shadow",
    minutes: int = 90,
):
    row = PlayerSeasonTotal(
        player_api_id=player,
        season=season,
        level_group=level_group,
        appearances=1,
        goals=0,
        minutes=minutes,
        primary_source=primary_source,
        fixtures_minutes=minutes if primary_source == "fixtures" else 0,
        journey_minutes=minutes if primary_source == "journey" else 0,
        computed_at=computed_at,
    )
    db.session.add(row)
    return row


def _cell(
    player: int,
    *,
    source: str,
    club: int,
    level_group: str = "senior",
    synced_at=NOW,
):
    row = PlayerSeasonCell(
        player_api_id=player,
        season=2025,
        source=source,
        club_api_id=club,
        competition_tier="league" if level_group == "senior" else "youth",
        level_group=level_group,
        appearances=1,
        goals=0,
        minutes=90,
        synced_at=synced_at,
    )
    db.session.add(row)
    return row


def _status(client, headers, *, exact: bool = False):
    url = f"{STATUS_URL}?exact=1" if exact else STATUS_URL
    response = client.get(url, headers=headers)
    assert response.status_code == 200
    return response.get_json()


def test_endpoints_require_admin_dual_auth(client):
    assert client.post(f"{REBUILD_URL}?scope=all").status_code == 401
    assert client.get(STATUS_URL).status_code == 401


@pytest.mark.parametrize(
    "query,error_part",
    [
        ("", "scope"),
        ("?scope=unknown", "scope"),
        ("?scope=player", "player_api_id"),
        ("?scope=player&player_api_id=nope", "player_api_id"),
        ("?scope=season", "season"),
        ("?scope=season&season=nope", "season"),
        ("?scope=all&cursor=-1", "cursor"),
        ("?scope=stale&cursor=nope", "cursor"),
    ],
)
def test_rebuild_validates_scope_arguments(client, admin_headers, query, error_part):
    response = client.post(f"{REBUILD_URL}{query}", headers=admin_headers)
    assert response.status_code == 400
    assert error_part in response.get_json()["error"]


def test_player_scope_rebuilds_and_is_idempotent(client, admin_headers):
    player = 101
    _shadow(player)
    db.session.commit()

    first = client.post(f"{REBUILD_URL}?scope=player&player_api_id={player}", headers=admin_headers)
    assert first.status_code == 200
    assert first.get_json() == {"processed": 1, "failed": [], "remaining": 0, "cursor": None}
    assert PlayerSeasonTotal.query.filter_by(player_api_id=player).count() == 1

    second = client.post(f"{REBUILD_URL}?scope=player&player_api_id={player}", headers=admin_headers)
    assert second.status_code == 200
    assert second.get_json() == {"processed": 1, "failed": [], "remaining": 0, "cursor": None}
    assert PlayerSeasonTotal.query.filter_by(player_api_id=player).count() == 1


def test_season_scope_is_bounded_and_leaves_other_seasons_untouched(client, admin_headers):
    player = 201
    _shadow(player, season=2024, minutes=80)
    _shadow(player, season=2025, minutes=90)
    db.session.commit()
    admin_routes.season_rollup_service.refresh_player(player, session=db.session)
    db.session.commit()
    old_total = PlayerSeasonTotal.query.filter_by(player_api_id=player, season=2024).one()
    old_computed_at = old_total.computed_at

    response = client.post(
        f"{REBUILD_URL}?scope=season&season=2025&batch_size=1",
        headers=admin_headers,
    )
    assert response.status_code == 200
    assert response.get_json() == {"processed": 1, "failed": [], "remaining": 0, "cursor": None}
    db.session.expire_all()
    assert PlayerSeasonTotal.query.filter_by(player_api_id=player, season=2024).one().computed_at == old_computed_at
    assert PlayerSeasonTotal.query.filter_by(player_api_id=player, season=2025).count() == 1


def test_all_scope_pages_every_source_and_orphan_derived_rows(client, admin_headers, monkeypatch):
    fixture = Fixture(fixture_id_api=10, season=2025, competition_name="Premier League")
    db.session.add(fixture)
    db.session.flush()
    db.session.add(
        FixturePlayerStats(
            fixture_id=fixture.id,
            player_api_id=10,
            team_api_id=1,
            minutes=90,
            goals=0,
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
            season=2025,
            club_api_id=400,
            appearances=1,
            minutes=90,
            goals=0,
            stats_synced_at=NOW,
        )
    )
    _total(50)  # totals-only orphan must be selectable so rebuild can delete it
    db.session.commit()

    calls = []

    def _record(player_api_id, season=None, session=None):
        calls.append((player_api_id, season, session))
        return {"cells": 0, "totals": 0}

    monkeypatch.setattr(admin_routes.season_rollup_service, "refresh_player", _record)

    first = client.post(f"{REBUILD_URL}?scope=all&batch_size=2", headers=admin_headers)
    assert first.status_code == 200
    assert first.get_json() == {"processed": 2, "failed": [], "remaining": 1, "cursor": 20}

    second = client.post(f"{REBUILD_URL}?scope=all&batch_size=2&cursor=20", headers=admin_headers)
    assert second.status_code == 200
    assert second.get_json() == {"processed": 2, "failed": [], "remaining": 1, "cursor": 40}

    third = client.post(f"{REBUILD_URL}?scope=all&batch_size=2&cursor=40", headers=admin_headers)
    assert third.status_code == 200
    assert third.get_json() == {"processed": 1, "failed": [], "remaining": 0, "cursor": None}
    assert [(player, season) for player, season, _session in calls] == [
        (10, None),
        (20, None),
        (30, None),
        (40, None),
        (50, None),
    ]
    assert all(session is db.session for _player, _season, session in calls)


def test_bounded_candidate_query_is_postgresql_safe(app):
    statement = admin_routes._candidate_player_ids(after=10, per_source_limit=25)
    sql = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    # Source-local DISTINCT avoids PostgreSQL's rejection of a GROUP BY player
    # query whose correlated old-cell EXISTS also references source.season.
    assert sql.count("SELECT DISTINCT") == 6
    assert "GROUP BY fixture_player_stats.player_api_id" not in sql
    assert "GROUP BY player_journeys.player_api_id" not in sql
    assert "GROUP BY academy_player_season_stats.player_api_id" not in sql
    assert "GROUP BY player_shadow_stats.player_api_id" not in sql


def test_all_scope_caps_batch_size_at_100(client, admin_headers, monkeypatch):
    for player in range(1, 103):
        _total(player)
    db.session.commit()
    monkeypatch.setattr(
        admin_routes.season_rollup_service,
        "refresh_player",
        lambda *args, **kwargs: {"cells": 0, "totals": 0},
    )

    response = client.post(f"{REBUILD_URL}?scope=all&batch_size=999", headers=admin_headers)
    assert response.status_code == 200
    assert response.get_json() == {"processed": 100, "failed": [], "remaining": 1, "cursor": 100}


@pytest.mark.parametrize("batch_query", ["", "&batch_size=0", "&batch_size=-1", "&batch_size=abc"])
def test_all_scope_uses_bounded_default_for_missing_or_invalid_batch_size(
    client,
    admin_headers,
    monkeypatch,
    batch_query,
):
    for player in range(1, 27):
        _total(player)
    db.session.commit()
    monkeypatch.setattr(
        admin_routes.season_rollup_service,
        "refresh_player",
        lambda *args, **kwargs: {"cells": 0, "totals": 0},
    )

    response = client.post(f"{REBUILD_URL}?scope=all{batch_query}", headers=admin_headers)
    assert response.status_code == 200
    assert response.get_json() == {"processed": 25, "failed": [], "remaining": 1, "cursor": 25}


def test_rebuild_scopes_do_not_run_the_global_status_count(client, admin_headers, monkeypatch):
    _shadow(240)
    db.session.commit()

    def _unexpected_global_count(*_args, **_kwargs):
        raise AssertionError("rebuild must not execute the platform-wide status count")

    monkeypatch.setattr(admin_routes, "_count_ids", _unexpected_global_count)
    response = client.post(f"{REBUILD_URL}?scope=stale&batch_size=1", headers=admin_headers)
    assert response.status_code == 200
    assert response.get_json() == {"processed": 1, "failed": [], "remaining": 0, "cursor": None}


def test_all_scope_rebuild_deletes_totals_only_orphan_and_rerun_is_noop(client, admin_headers):
    _total(250)
    db.session.commit()

    first = client.post(f"{REBUILD_URL}?scope=all", headers=admin_headers)
    assert first.status_code == 200
    assert first.get_json() == {"processed": 1, "failed": [], "remaining": 0, "cursor": None}
    assert PlayerSeasonTotal.query.filter_by(player_api_id=250).count() == 0

    second = client.post(f"{REBUILD_URL}?scope=all", headers=admin_headers)
    assert second.status_code == 200
    assert second.get_json() == {"processed": 0, "failed": [], "remaining": 0, "cursor": None}


def test_batch_savepoints_keep_successes_and_report_failed_id(client, admin_headers, monkeypatch):
    for player in (261, 262, 263):
        _total(player)
    db.session.commit()
    calls = []

    def _fail_middle_once(player_api_id, **_kwargs):
        calls.append(player_api_id)
        if player_api_id == 262:
            raise RuntimeError("bad player")
        return {"cells": 0, "totals": 0}

    monkeypatch.setattr(admin_routes.season_rollup_service, "refresh_player", _fail_middle_once)
    first = client.post(f"{REBUILD_URL}?scope=all&batch_size=3", headers=admin_headers)
    assert first.status_code == 200
    # The savepoint keeps 261/263, the sweep TERMINATES (cursor null), and the
    # failing id is surfaced for an out-of-band scope=player retry.
    assert first.get_json() == {"processed": 2, "failed": [262], "remaining": 0, "cursor": None}
    assert calls == [261, 262, 263]

    monkeypatch.setattr(
        admin_routes.season_rollup_service,
        "refresh_player",
        lambda *args, **kwargs: {"cells": 0, "totals": 0},
    )
    retry = client.post(f"{REBUILD_URL}?scope=player&player_api_id=262", headers=admin_headers)
    assert retry.status_code == 200
    assert retry.get_json() == {"processed": 1, "failed": [], "remaining": 0, "cursor": None}


def test_persistent_failure_is_reported_once_and_sweep_terminates(client, admin_headers, monkeypatch):
    for player in range(271, 276):
        _total(player)
    db.session.commit()
    calls = []

    def _fail_first(player_api_id, **_kwargs):
        calls.append(player_api_id)
        if player_api_id == 271:
            raise RuntimeError("persistent bad player")
        return {"cells": 0, "totals": 0}

    monkeypatch.setattr(admin_routes.season_rollup_service, "refresh_player", _fail_first)

    first = client.post(f"{REBUILD_URL}?scope=all&batch_size=2", headers=admin_headers)
    assert first.status_code == 200
    assert first.get_json() == {"processed": 1, "failed": [271], "remaining": 1, "cursor": 272}

    second = client.post(
        f"{REBUILD_URL}?scope=all&batch_size=2&cursor={first.get_json()['cursor']}",
        headers=admin_headers,
    )
    assert second.status_code == 200
    assert second.get_json() == {"processed": 2, "failed": [], "remaining": 1, "cursor": 274}

    third = client.post(
        f"{REBUILD_URL}?scope=all&batch_size=2&cursor={second.get_json()['cursor']}",
        headers=admin_headers,
    )
    assert third.status_code == 200
    # Forward-only cursor: the poison row 271 does not rewind the sweep, which
    # converges to a null cursor after one pass instead of looping forever.
    assert third.get_json() == {"processed": 1, "failed": [], "remaining": 0, "cursor": None}
    assert calls == [271, 272, 273, 274, 275]


def test_stale_scope_uses_exact_source_clocks_and_converges(client, admin_headers):
    # No total yet: stale regardless of the source clock.
    _shadow(301, updated_at=NOW - timedelta(days=2))

    # Source clock newer than its senior total: stale.
    _shadow(302, updated_at=NOW)
    _total(302, computed_at=NOW - timedelta(days=1))

    # Total newer than the source: fresh.
    _shadow(303, updated_at=NOW - timedelta(days=2))
    _total(303, computed_at=NOW - timedelta(days=1))

    # A newer senior total must not mask an older youth total.
    _apss(304, updated_at=NOW)
    _shadow(304, updated_at=NOW - timedelta(days=3))
    _total(304, level_group="youth", primary_source="apss", computed_at=NOW - timedelta(days=1))
    _total(304, level_group="senior", computed_at=NOW + timedelta(hours=1))

    # Journey freshness resolves the canonical id through the parent when the
    # sea01 denormalized player_api_id has not been backfilled.
    journey = PlayerJourney(player_api_id=305, player_name="Legacy")
    db.session.add(journey)
    db.session.flush()
    db.session.add(
        PlayerJourneyEntry(
            journey_id=journey.id,
            player_api_id=None,
            season=2025,
            club_api_id=3050,
            appearances=1,
            minutes=90,
            goals=0,
            stats_synced_at=NOW,
        )
    )
    _total(305, primary_source="journey", computed_at=NOW - timedelta(days=1))

    # Permanent pre-season noise without an old cell is not stale forever.
    _apss(306, updated_at=NOW, minutes=0)
    db.session.commit()

    assert _status(client, admin_headers, exact=True)["stale_players"] == 4

    first = client.post(f"{REBUILD_URL}?scope=stale&batch_size=2", headers=admin_headers)
    assert first.status_code == 200
    assert first.get_json() == {"processed": 2, "failed": [], "remaining": 1, "cursor": 302}

    second = client.post(
        f"{REBUILD_URL}?scope=stale&batch_size=2&cursor={first.get_json()['cursor']}",
        headers=admin_headers,
    )
    assert second.status_code == 200
    assert second.get_json() == {"processed": 1, "failed": [], "remaining": 1, "cursor": 304}

    third = client.post(
        f"{REBUILD_URL}?scope=stale&batch_size=2&cursor={second.get_json()['cursor']}",
        headers=admin_headers,
    )
    assert third.status_code == 200
    assert third.get_json() == {"processed": 1, "failed": [], "remaining": 0, "cursor": None}
    assert _status(client, admin_headers, exact=True)["stale_players"] == 0


def test_noise_stub_cannot_borrow_another_journey_level_cell(client, admin_headers):
    player = 390
    journey = PlayerJourney(player_api_id=player, player_name="Mixed Levels")
    db.session.add(journey)
    db.session.flush()
    db.session.add_all(
        [
            PlayerJourneyEntry(
                journey_id=journey.id,
                season=2025,
                club_api_id=3900,
                appearances=1,
                minutes=90,
                goals=0,
                stats_synced_at=NOW,
            ),
            PlayerJourneyEntry(
                journey_id=journey.id,
                season=2025,
                club_api_id=3901,
                is_youth=True,
                appearances=0,
                minutes=0,
                goals=0,
                stats_synced_at=NOW,
            ),
        ]
    )
    db.session.commit()

    built = client.post(f"{REBUILD_URL}?scope=player&player_api_id={player}", headers=admin_headers)
    assert built.status_code == 200
    assert PlayerSeasonTotal.query.filter_by(player_api_id=player, level_group="senior").count() == 1
    assert PlayerSeasonTotal.query.filter_by(player_api_id=player, level_group="youth").count() == 0
    assert _status(client, admin_headers, exact=True)["stale_players"] == 0


def test_senior_fixture_cell_does_not_mask_missing_youth_fixture_cell(client, admin_headers):
    player = 395
    senior_fixture = Fixture(fixture_id_api=394, season=2025, competition_name="Premier League")
    youth_fixture = Fixture(fixture_id_api=395, season=2025, competition_name="Premier League 2 Division One")
    db.session.add_all([senior_fixture, youth_fixture])
    db.session.flush()
    db.session.add_all(
        [
            FixturePlayerStats(
                fixture_id=senior_fixture.id,
                player_api_id=player,
                team_api_id=3940,
                minutes=90,
                goals=0,
            ),
            FixturePlayerStats(
                fixture_id=youth_fixture.id,
                player_api_id=player,
                team_api_id=3950,
                minutes=90,
                goals=0,
            ),
        ]
    )
    _cell(player, source="fixtures", club=3940, level_group="senior")
    _total(player, level_group="senior", primary_source="fixtures")
    db.session.commit()

    assert _status(client, admin_headers, exact=True)["stale_players"] == 1
    rebuilt = client.post(f"{REBUILD_URL}?scope=stale", headers=admin_headers)
    assert rebuilt.status_code == 200
    assert rebuilt.get_json() == {"processed": 1, "failed": [], "remaining": 0, "cursor": None}
    assert (
        PlayerSeasonCell.query.filter_by(
            player_api_id=player,
            source="fixtures",
            level_group="senior",
        ).count()
        == 1
    )
    assert (
        PlayerSeasonCell.query.filter_by(
            player_api_id=player,
            source="fixtures",
            level_group="youth",
        ).count()
        == 1
    )
    assert PlayerSeasonTotal.query.filter_by(player_api_id=player, level_group="youth").count() == 1
    assert _status(client, admin_headers, exact=True)["stale_players"] == 0


def test_team_delete_rolls_back_when_rollup_refresh_fails(client, admin_headers, monkeypatch):
    player = 396
    team = Team(
        team_id=3960,
        name="Atomic FC",
        country="England",
        season=2025,
        is_tracked=True,
        newsletters_active=True,
    )
    db.session.add(team)
    db.session.flush()
    db.session.add(TrackedPlayer(player_api_id=player, player_name="Atomic Player", team_id=team.id))
    fixture = Fixture(fixture_id_api=396, season=2025, competition_name="Premier League")
    db.session.add(fixture)
    db.session.flush()
    db.session.add(
        FixturePlayerStats(
            fixture_id=fixture.id,
            player_api_id=player,
            team_api_id=team.team_id,
            minutes=90,
            goals=0,
        )
    )
    _cell(player, source="fixtures", club=team.team_id)
    _total(player, primary_source="fixtures")
    db.session.commit()
    team_id = team.id

    def _boom(*_args, **_kwargs):
        raise RuntimeError("simulated rollup failure")

    monkeypatch.setattr(admin_routes.season_rollup_service, "refresh_player", _boom)
    response = client.delete(f"/api/admin/teams/{team_id}/data", headers=admin_headers)

    assert response.status_code == 500
    assert response.get_json()["error"] == "Failed to delete team data"
    db.session.expire_all()
    assert FixturePlayerStats.query.filter_by(player_api_id=player).count() == 1
    assert TrackedPlayer.query.filter_by(player_api_id=player, team_id=team_id).count() == 1
    restored_team = db.session.get(Team, team_id)
    assert (restored_team.is_tracked, restored_team.newsletters_active) == (True, True)
    assert PlayerSeasonCell.query.filter_by(player_api_id=player, source="fixtures").count() == 1
    assert PlayerSeasonTotal.query.filter_by(player_api_id=player).count() == 1


def test_stale_cursor_above_all_work_terminates(client, admin_headers):
    # A caller resuming with a cursor above every remaining id has, by the
    # forward-only keyset contract, already scanned that work: the sweep
    # terminates (cursor null) instead of rewinding to zero.
    _shadow(399, updated_at=NOW)
    db.session.commit()

    response = client.post(f"{REBUILD_URL}?scope=stale&cursor=999", headers=admin_headers)
    assert response.status_code == 200
    assert response.get_json() == {"processed": 0, "failed": [], "remaining": 0, "cursor": None}


def test_stale_scope_advances_bounded_scan_pages_that_contain_no_stale_players(client, admin_headers):
    old = NOW - timedelta(days=2)
    fresh_total = NOW - timedelta(days=1)
    for player in range(1, 31):
        _shadow(player, updated_at=old)
        if player < 30:
            _total(player, computed_at=fresh_total)
    db.session.commit()

    cursor = None
    for expected_cursor in (5, 10, 15, 20, 25):
        cursor_query = "" if cursor is None else f"&cursor={cursor}"
        response = client.post(
            f"{REBUILD_URL}?scope=stale&batch_size=5{cursor_query}",
            headers=admin_headers,
        )
        assert response.status_code == 200
        assert response.get_json() == {
            "processed": 0,
            "failed": [],
            "remaining": 1,
            "cursor": expected_cursor,
        }
        cursor = response.get_json()["cursor"]

    final = client.post(
        f"{REBUILD_URL}?scope=stale&batch_size=5&cursor={cursor}",
        headers=admin_headers,
    )
    assert final.status_code == 200
    assert final.get_json() == {"processed": 1, "failed": [], "remaining": 0, "cursor": None}


def test_stale_zeroed_source_removes_old_cells_then_converges(client, admin_headers):
    row = _apss(401, updated_at=NOW - timedelta(days=2))
    db.session.commit()
    built = client.post(f"{REBUILD_URL}?scope=player&player_api_id=401", headers=admin_headers)
    assert built.status_code == 200
    assert PlayerSeasonCell.query.filter_by(player_api_id=401, source="apss").count() == 1
    computed_at = PlayerSeasonTotal.query.filter_by(player_api_id=401, level_group="youth").one().computed_at

    row.appearances = 0
    row.minutes = 0
    row.goals = 0
    row.updated_at = computed_at + timedelta(microseconds=1)
    db.session.commit()
    assert _status(client, admin_headers, exact=True)["stale_players"] == 1

    rebuilt = client.post(f"{REBUILD_URL}?scope=stale", headers=admin_headers)
    assert rebuilt.status_code == 200
    assert rebuilt.get_json() == {"processed": 1, "failed": [], "remaining": 0, "cursor": None}
    assert PlayerSeasonCell.query.filter_by(player_api_id=401, source="apss").count() == 0
    assert PlayerSeasonTotal.query.filter_by(player_api_id=401, level_group="youth").count() == 0
    assert _status(client, admin_headers, exact=True)["stale_players"] == 0


def test_default_status_gauge_skips_exact_stale_enumeration(client, admin_headers, monkeypatch):
    # A source newer than its total is stale, but the default gauge must decide
    # ``behind`` from cheap MAX clocks without running the exact enumeration.
    _shadow(600, updated_at=NOW)
    _total(600, computed_at=NOW - timedelta(days=1))
    db.session.commit()

    def _boom(*_args, **_kwargs):
        raise AssertionError("default /status must not run the exact stale enumeration")

    monkeypatch.setattr(admin_routes, "_stale_player_ids", _boom)
    body = _status(client, admin_headers)
    assert body["behind"] is True
    assert "stale_players" not in body


def test_status_exact_flag_reports_stale_player_count(client, admin_headers):
    _shadow(601, updated_at=NOW)
    _total(601, computed_at=NOW - timedelta(days=1))  # stale: source newer
    _shadow(602, updated_at=NOW - timedelta(days=2))
    _total(602, computed_at=NOW - timedelta(days=1))  # fresh: total newer
    db.session.commit()

    default_body = _status(client, admin_headers)
    assert default_body["behind"] is True
    assert "stale_players" not in default_body

    exact_body = _status(client, admin_headers, exact=True)
    assert exact_body["stale_players"] == 1


def test_status_returns_totals_freshness_and_source_cell_counts(client, admin_headers):
    old = NOW - timedelta(days=2)
    middle = NOW - timedelta(days=1)
    _shadow(501, updated_at=NOW)
    _total(501, computed_at=middle)
    _total(502, level_group="senior", computed_at=NOW)
    _total(502, level_group="youth", primary_source="apss", computed_at=old)
    _cell(501, source="fixtures", club=1, synced_at=old)
    _cell(502, source="fixtures", club=2, synced_at=old)
    _cell(502, source="journey", club=3, level_group="youth", synced_at=old)
    db.session.commit()

    # Default gauge is cheap: newest source clock (shadow NOW) is not later than
    # the newest computed_at (502 senior NOW), so the coarse gauge reads caught up.
    # The per-source cell breakdown scans the largest table, so it is NOT on the
    # pollable default path — only the four index-served clocks + the totals scan.
    body = _status(client, admin_headers)
    assert body == {
        "total_totals_rows": 3,
        "behind": False,
        "last_computed_at": NOW.replace(tzinfo=None).isoformat(),
        "last_source_change_at": NOW.replace(tzinfo=None).isoformat(),
    }
    assert "by_source_cells" not in body
    # ?exact=1 adds both reconciliation extras: the per-source cell breakdown and
    # the exact stale count (still sees 501, shadow NOW > its total middle).
    exact_body = _status(client, admin_headers, exact=True)
    assert exact_body["by_source_cells"] == {"fixtures": 2, "journey": 1}
    assert exact_body["stale_players"] == 1


def test_empty_status_is_zeroed(client, admin_headers):
    assert _status(client, admin_headers) == {
        "total_totals_rows": 0,
        "behind": False,
        "last_computed_at": None,
        "last_source_change_at": None,
    }
    exact_body = _status(client, admin_headers, exact=True)
    assert exact_body["by_source_cells"] == {}
    assert exact_body["stale_players"] == 0
