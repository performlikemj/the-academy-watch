"""Freeze contracts: fail at HTTP transport; retain stored rows and client shapes."""

import ast
import importlib
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import Flask
from src.models.api_cache import APICache  # noqa: F401
from src.models.follow import FollowList, PlayerShadow
from src.models.journey import PlayerJourney, PlayerJourneyEntry
from src.models.league import Team, UserAccount, db
from src.models.player_match_entry import PlayerMatchEntry
from src.models.tracked_player import TrackedPlayer
from src.models.weekly import Fixture, FixturePlayerStats
from src.utils.data_mode import FrozenModeError

SOURCE = Path(__file__).resolve().parents[1] / "src"
MODULES = [
    "players",
    "journey",
    "api",
    "scout",
    "academy",
    "cohort",
    "curator",
    "newsletter_deadline",
    "gol",
    "journalist",
    "teams",
    "showcase",
]


def route_gates():
    gates = []
    for module in MODULES:
        for fn in ast.parse((SOURCE / "routes" / f"{module}.py").read_text()).body:
            if isinstance(fn, ast.FunctionDef):
                for dec in fn.decorator_list:
                    if isinstance(dec, ast.Name) and dec.id in {"api_enabled_route", "newsletters_enabled_route"}:
                        gates.append((module, fn.name, dec.id))
    return gates


@pytest.fixture
def frozen_app(monkeypatch):
    for key, value in {
        "API_FOOTBALL_FROZEN": "1",
        "API_USE_STUB_DATA": "true",
        "ADMIN_API_KEY": "freeze-key",
        "ADMIN_EMAILS": "freeze@example.com",
        "ADMIN_IP_WHITELIST": "",
        "OPENAI_API_KEY": "test",
        "GROQ_API_KEY": "test",
        "DB_HOST": "127.0.0.1",
        "DB_PORT": "55442",
        "DB_NAME": "freeze_f2_source",
        "DB_USER": "postgres",
        "DB_PASSWORD": "freeze-f2-local",
        "DB_SSLMODE": "disable",
    }.items():
        monkeypatch.setenv(key, value)

    def reject(*args, **kwargs):
        pytest.fail("Outbound HTTP attempted in frozen mode")

    monkeypatch.setattr("requests.sessions.Session.request", reject)
    monkeypatch.setattr("httpx.Client.send", reject)
    monkeypatch.setattr("httpx.AsyncClient.send", reject)
    app = Flask(__name__)
    app.config.update(
        TESTING=True, SECRET_KEY="freeze-test", SQLALCHEMY_DATABASE_URI="sqlite://", RATELIMIT_ENABLED=False
    )
    db.init_app(app)
    from src.extensions import limiter

    limiter.init_app(app)
    for module in MODULES:
        mod = importlib.import_module(f"src.routes.{module}")
        app.register_blueprint(getattr(mod, f"{module}_bp"), url_prefix="/api")
    with app.app_context():
        db.create_all()
        user = UserAccount(email="freeze@example.com", display_name="Freeze Tester", display_name_lower="freeze tester")
        team = Team(team_id=33, name="Freeze Test Academy", country="England", season=2025, is_active=True)
        db.session.add_all([user, team])
        db.session.flush()
        journey = PlayerJourney(
            player_api_id=990001,
            player_name="Freeze Test Player",
            birth_date="2000-02-01",
            current_status="released",
            last_synced_at=datetime(2026, 5, 20),
        )
        db.session.add(journey)
        db.session.flush()
        db.session.add(
            TrackedPlayer(
                player_api_id=990001,
                player_name="Freeze Test Player",
                team_id=team.id,
                birth_date="2000-02-01",
                status="released",
                data_source="journey-sync",
                data_depth="full_stats",
                is_active=True,
                journey_id=journey.id,
            )
        )
        db.session.add(
            PlayerJourneyEntry(
                journey_id=journey.id,
                season=2025,
                club_api_id=33,
                club_name=team.name,
                appearances=10,
                minutes=900,
                goals=4,
                is_youth=False,
                is_international=False,
                stats_synced_at=datetime(2026, 5, 19),
            )
        )
        fixture = Fixture(
            fixture_id_api=9001,
            season=2025,
            date_utc=datetime(2026, 5, 18),
            home_team_api_id=33,
            away_team_api_id=34,
            competition_name="Test League",
        )
        db.session.add(fixture)
        db.session.flush()
        db.session.add(
            FixturePlayerStats(
                fixture_id=fixture.id,
                player_api_id=990001,
                team_api_id=33,
                minutes=90,
                goals=1,
                assists=0,
                position="M",
            )
        )
        for source, status, goals in [("club", "club_confirmed", 2), ("self", "self_reported", 3)]:
            db.session.add(
                PlayerMatchEntry(
                    player_api_id=990001,
                    season=2025,
                    match_date=date(2026, 6, 1),
                    opponent="Test Opponent",
                    competition="Test League",
                    home_away="home",
                    reported_by_user_id=user.id,
                    source=source,
                    status=status,
                    minutes=60,
                    goals=goals,
                )
            )
        db.session.add(FollowList(user_account_id=user.id, name="Test List"))
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.mark.parametrize(
    "flag,module,name,gate",
    [
        (flag, module, name, gate)
        for flag in ("API_FOOTBALL_FROZEN", "NEWSLETTERS_FROZEN")
        for module, name, gate in route_gates()
        if flag == "API_FOOTBALL_FROZEN" or gate == "newsletters_enabled_route"
    ],
)
def test_launch_routes_refuse_before_work(frozen_app, monkeypatch, module, name, gate, flag):
    monkeypatch.setenv("API_FOOTBALL_FROZEN", "1" if flag == "API_FOOTBALL_FROZEN" else "0")
    monkeypatch.setenv("NEWSLETTERS_FROZEN", "1" if flag == "NEWSLETTERS_FROZEN" else "0")
    endpoint = f"{module}.{name}"
    fn = frozen_app.view_functions[endpoint]
    while fn.__code__.co_name != "guarded":
        fn = fn.__wrapped__
    frozen_app.view_functions[endpoint] = fn  # auth has its own existing tests
    rule = next(r for r in frozen_app.url_map.iter_rules() if r.endpoint == endpoint)
    url = frozen_app.url_map.bind("localhost").build(endpoint, {arg: 1 for arg in rule.arguments})
    method = next(m for m in rule.methods if m not in {"HEAD", "OPTIONS"})
    response = frozen_app.test_client().open(url, method=method, json={})
    assert response.status_code == 409
    assert response.json["code"] == "frozen"
    assert FixturePlayerStats.query.one().goals == 1


def test_cache_boundary_without_key_and_with_broken_db(frozen_app, monkeypatch):
    from src.api_football_client import APIFootballClient

    monkeypatch.delenv("API_FOOTBALL_KEY", raising=False)
    monkeypatch.delenv("SKIP_API_HANDSHAKE", raising=False)
    client = APIFootballClient()
    assert not client.use_stub
    assert client.handshake() is False
    cached = {"response": [{"player": {"id": 990001}}], "results": 1}
    APICache.set_cached("players", {"id": 990001}, cached, 300)
    assert client._make_request("players", {"id": 990001}, force_refresh=True) == cached
    assert client._make_request("players", {"id": 999999})["unavailable"]
    monkeypatch.setattr(APICache, "get_cached", Mock(side_effect=RuntimeError("cache down")))
    assert client._make_request("players", {})["unavailable"]


def test_db_reads_and_source_separation(frozen_app, monkeypatch):
    client = frozen_app.test_client()
    from src.services.season_rollup_service import refresh_player

    refresh_player(990001, season=2025)
    db.session.commit()
    for rollups in ("", "player_stats,season_stats"):
        monkeypatch.setenv("SEASON_ROLLUP_READS", rollups)
        response = client.get("/api/players/990001/stats?season=2025&force_sync=true")
        assert response.status_code == 200, response.json
        rows = response.json if isinstance(response.json, list) else response.json["matches"]
        assert rows[0]["goals"] == 1
        assert rows[0]["source_label"] == "public_match_data"
        response = client.get("/api/players/990001/season-stats?season=2025")
        assert response.status_code == 200, response.json
        data = response.json
        assert data["public_match_data"]["totals"]["goals"] == 4, data
        assert data["club_verified"]["totals"]["goals"] == 2
        assert data["self_reported"]["totals"]["goals"] == 3
        assert data["goals"] == 2
        assert data["as_of"].startswith("2026-05-20")
    for url in ["profile", "journey?sync=true", "journey/map?sync=true", "availability"]:
        response = client.get(f"/api/players/990001/{url}")
        assert response.status_code == 200, (url, response.json)
    assert client.get("/api/players/990001/availability").json["summary"]["total_absences"] is None
    from src.utils.team_resolver import resolve_team_name_and_logo

    assert resolve_team_name_and_logo(999999) == ("Team 999999", None)
    from src.services.radar_stats_service import get_radar_chart_data

    assert get_radar_chart_data(990001, [])["available"] is False
    assert FixturePlayerStats.query.one().goals == 1
    monkeypatch.setenv("API_FOOTBALL_FROZEN", "0")
    from src.services.public_data import separated_season_stats

    assert separated_season_stats(990001, 2025, {"goals": 4, "source": "season-rollup"})["goals"] == 4


def test_search_and_follow_existing_only(frozen_app):
    from src.auth import issue_user_token

    headers = {"Authorization": "Bearer " + issue_user_token("freeze@example.com")["token"]}
    client = frozen_app.test_client()
    response = client.get("/api/scout/player-search?q=Freeze", headers=headers)
    assert response.status_code == 200, response.json
    assert response.json["players"][0]["player_api_id"] == 990001
    assert response.json["create_profile_url"] == "/local-players/new"
    follow_list = FollowList.query.one()
    for pid, expected in [(990009, 409), (990001, 201)]:
        response = client.post(
            f"/api/scout/lists/{follow_list.id}/follows",
            headers=headers,
            json={"kind": "player", "selector": {"player_api_id": pid}, "seed": {"name": "Untrusted"}},
        )
        assert response.status_code == expected, response.json
    assert PlayerShadow.query.count() == 0


@pytest.mark.parametrize(
    "status,expected", [("free_agent", "direct"), ("contracted", "club_notified"), (None, "club_notified")]
)
def test_contract_attestation_wins(frozen_app, status, expected):
    from src.services.contact import has_status_contradiction, platform_contract_belief, routing_mode_for_claim

    assert platform_contract_belief(990001) == ("unknown", None)
    assert platform_contract_belief(-1) == ("unknown", None)
    claim = SimpleNamespace(player_api_id=990001, contract_status=status, club_program_id=None)
    assert routing_mode_for_claim(claim) == expected
    assert not has_status_contradiction(990001, status)


def test_gol_and_meta(frozen_app, monkeypatch):
    from src.services.gol_service import GolService, active_system_prompt, active_tool_schemas

    assert [t["function"]["name"] for t in active_tool_schemas()] == ["run_analysis"]
    assert "lookup_player" not in active_system_prompt()
    assert "search_web" not in active_system_prompt()
    gol = GolService.__new__(GolService)
    for tool in ("lookup_player", "search_web"):
        assert "frozen" in gol._execute_tool(tool, {})["error"]
    assert frozen_app.test_client().get("/api/meta/data-mode").json == {
        "api_football_frozen": True,
        "newsletters_frozen": True,
    }
    monkeypatch.setenv("API_FOOTBALL_FROZEN", "0")
    monkeypatch.delenv("NEWSLETTERS_FROZEN", raising=False)
    assert len(active_tool_schemas()) == 3
    assert frozen_app.test_client().get("/api/meta/data-mode").json == {
        "api_football_frozen": False,
        "newsletters_frozen": False,
    }


@pytest.mark.parametrize(
    "module,name,args",
    [
        ("services.journey_sync", "JourneySyncService.sync_player", [990001]),
        ("utils.rebuild_runner", "_run_full_rebuild", [1, {}]),
        ("services.scout_digest_service", "send_scout_digests", []),
        ("services.newsletter_deadline_service", "send_digest_emails", ["2026-W39"]),
        ("services.newsletter_deadline_service", "process_newsletter_deadline", []),
        ("jobs.run_full_rebuild", "run", []),
        ("jobs.run_transfer_window_heal", "run", []),
        ("jobs.run_status_refresh", "run", []),
        ("jobs.run_data_integrity_fix", "run", []),
        ("jobs.run_weekly_newsletters", "run_for_date", [date(2026, 9, 25)]),
        ("jobs.run_weekly_newsletters_mcp", "run_for_date", [date(2026, 9, 25)]),
        ("jobs.run_scout_digests", "run", []),
    ],
)
def test_direct_workers_refuse(frozen_app, module, name, args):
    obj = importlib.import_module("src." + module)
    if "." in name:
        cls, name = name.split(".")
        cls = getattr(obj, cls)
        obj = cls.__new__(cls)
    with pytest.raises(FrozenModeError, match="frozen"):
        getattr(obj, name)(*args)


@pytest.mark.parametrize("command", ["seed-teams", "sync-fixtures", "reclass-journeys"])
def test_cli_exits_nonzero(frozen_app, command):
    from src.main import app

    result = app.test_cli_runner().invoke(args=[command])
    assert result.exit_code != 0
    assert "frozen" in result.output


def test_local_claim_routing_unchanged(frozen_app, monkeypatch):
    from src.models.showcase import LocalPlayer, PlayerProfileClaim
    from src.services.contact import routing_mode_for_claim

    user = UserAccount.query.one()
    local = LocalPlayer(
        display_name="Local Test",
        normalized_name="local test",
        birth_date=date(2000, 1, 1),
        position="Midfielder",
        country="England",
        status="approved",
        created_by_user_id=user.id,
    )
    db.session.add(local)
    db.session.flush()
    local.api_player_id = -local.id
    db.session.add(
        PlayerShadow(
            player_api_id=-local.id,
            player_name=local.display_name,
            birth_date=date(2000, 1, 1),
            requested_by_user_id=user.id,
            is_active=True,
        )
    )
    claim = PlayerProfileClaim(
        user_account_id=user.id,
        local_player_id=local.id,
        relationship_type="player",
        contract_status="free_agent",
        status="approved",
    )
    db.session.add(claim)
    db.session.commit()
    for frozen in ("0", "1"):
        monkeypatch.setenv("API_FOOTBALL_FROZEN", frozen)
        assert routing_mode_for_claim(claim) == "direct"
        claim.contract_status = "unknown"
        assert routing_mode_for_claim(claim) == "club_notified"
        claim.contract_status = "free_agent"


def test_tracking_skips_seed_and_db_repair_still_works(frozen_app, monkeypatch):
    import src.routes.api as api
    from src.auth import issue_user_token

    def fail(*a, **kw):
        pytest.fail("Seed launched")

    monkeypatch.setattr(api, "_start_background_seed", fail)
    headers = {
        "Authorization": "Bearer " + issue_user_token("freeze@example.com", role="admin")["token"],
        "X-API-Key": "freeze-key",
    }
    client = frozen_app.test_client()
    team = Team.query.one()
    response = client.post(f"/api/admin/teams/{team.id}/tracking", headers=headers, json={"is_tracked": True})
    assert response.status_code == 200, response.json
    assert "seed_job_id" not in response.json
    response = client.post("/api/admin/players/backfill-names", headers=headers, json={"dry_run": True})
    assert response.status_code == 200, response.json
    response = client.post(
        "/api/admin/players/backfill-names", headers=headers, json={"fetch_missing": True, "dry_run": False}
    )
    assert response.status_code == 409


def test_newsletter_management_and_history_survive(frozen_app):
    import json
    from datetime import UTC, timedelta

    from src.models.league import EmailToken, UserSubscription

    team = Team.query.one()
    sub = UserSubscription(email="freeze@example.com", team_id=team.id, active=True, unsubscribe_token="freeze-unsub")
    manage = EmailToken(
        email=sub.email, token="freeze-manage", purpose="manage", expires_at=datetime.now(UTC) + timedelta(days=1)
    )
    confirm = EmailToken(
        email=sub.email,
        token="freeze-confirm",
        purpose="subscribe_confirm",
        expires_at=datetime.now(UTC) + timedelta(days=1),
        metadata_json=json.dumps({"team_ids": [team.id]}),
    )
    db.session.add_all([sub, manage, confirm])
    db.session.commit()
    client = frozen_app.test_client()
    assert client.get("/api/subscriptions/manage/freeze-manage").status_code == 200
    assert client.get("/api/newsletters").status_code == 200
    assert client.post("/api/verify/freeze-confirm").status_code == 409
    assert confirm.used_at is None
    response = client.post("/api/subscriptions/manage/freeze-manage", json={"team_ids": []})
    assert response.status_code == 200, response.json
    assert not sub.active
    response = client.post("/api/subscriptions/manage/freeze-manage", json={"team_ids": [team.id]})
    assert response.status_code == 409
    assert not sub.active


@pytest.mark.parametrize(
    "module,name,args",
    [
        ("agents.weekly_newsletter_agent", "generate_team_weekly_newsletter", [1, date(2026, 9, 25)]),
        ("agents.weekly_agent", "generate_weekly_newsletter_with_mcp_sync", [1, date(2026, 9, 25)]),
        ("routes.api", "_deliver_newsletter_via_webhook", [None]),
        ("routes.api", "_maybe_auto_send_on_publish", [None, True]),
        ("routes.api", "_maybe_post_to_reddit_on_publish", [[]]),
        ("services.reddit_service", "post_newsletter_to_reddit", [None, None, "title", "body"]),
    ],
)
def test_newsletter_services_refuse_direct_calls(frozen_app, monkeypatch, module, name, args):
    if module == "services.reddit_service":
        # The optional Reddit SDK is absent on Basecamp; construction must never
        # happen while frozen. The HTTP transport is independently forbidden.
        import sys

        class Reddit:
            def __init__(self, *a, **kw):
                pytest.fail("Reddit client constructed")

        monkeypatch.setitem(sys.modules, "praw", SimpleNamespace(Reddit=Reddit))
        monkeypatch.setitem(sys.modules, "prawcore.exceptions", SimpleNamespace(PrawcoreException=RuntimeError))
    with pytest.raises(FrozenModeError, match="frozen"):
        getattr(importlib.import_module("src." + module), name)(*args)


def test_club_correction_dispute_and_public_fallback(frozen_app):
    from src.services.season_rollup_service import refresh_player

    refresh_player(990001, season=2025)
    db.session.commit()
    club = PlayerMatchEntry.query.filter_by(source="club").one()
    club.goals = 5
    db.session.commit()
    client = frozen_app.test_client()
    result = client.get("/api/players/990001/season-stats?season=2025").json
    assert result["goals"] == 5
    assert result["public_match_data"]["totals"]["goals"] == 4
    club.status = "disputed"
    db.session.commit()
    result = client.get("/api/players/990001/season-stats?season=2025").json
    assert result["goals"] == 4
    assert not result["club_verified"]["available"]


def test_expired_cache_purge_remains_available(frozen_app):
    from datetime import UTC, timedelta

    APICache.set_cached("players", {"id": 990001}, {"response": []}, 100)
    row = APICache.query.one()
    row.expires_at = datetime.now(UTC) - timedelta(days=1)
    db.session.commit()
    assert APICache.get_cached("players", {"id": 990001}) is None
    db.session.expunge_all()  # Purge runs in its own session, not the reader identity map.
    assert APICache.cleanup_expired() == 1


def test_scout_compare_and_radar_route_do_not_fetch(frozen_app):
    client = frozen_app.test_client()
    response = client.get("/api/scout/players?search=Freeze")
    assert response.status_code == 200, response.json
    response = client.get("/api/scout/compare?ids=990001&include_availability=true")
    assert response.status_code == 200, response.json
    assert response.json["players"][0]["availability"] is None
    response = client.get("/api/journalists/chart-data?player_id=990001&chart_type=radar&date_range=season&season=2025")
    assert response.status_code == 200, response.json
    assert response.json["available"] is False


@pytest.mark.parametrize("rollups", ["", "player_stats,season_stats"])
@pytest.mark.parametrize(
    "path", ["season-stats?season=2025", "profile", "stats?season=2025", "journey", "academy-stats"]
)
def test_flag_off_golden_json_and_sql(frozen_app, monkeypatch, path, rollups):
    """Baseline = the same legacy handlers with F2 enrichment entirely removed.

    Disable both response hooks, bypass source separation, and replace academy
    metadata with a query-free stub whose keys are stripped at serialization.
    This isolates pre-F2 behavior without depending on git or a deployed DB.
    """
    from sqlalchemy import event
    from src.routes import academy
    from src.services import public_data
    from src.services.season_rollup_service import refresh_player

    refresh_player(990001, season=2025)
    db.session.commit()
    monkeypatch.setenv("API_FOOTBALL_FROZEN", "0")
    monkeypatch.setenv("NEWSLETTERS_FROZEN", "0")
    monkeypatch.setenv("SEASON_ROLLUP_READS", rollups)
    client = frozen_app.test_client()

    def measure():
        db.session.remove()
        statements = []

        def record(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        event.listen(db.engine, "before_cursor_execute", record)
        try:
            response = client.get(f"/api/players/990001/{path}")
            assert response.status_code == 200, response.json
            return response.data, response.json, statements
        finally:
            event.remove(db.engine, "before_cursor_execute", record)

    with monkeypatch.context() as baseline:
        baseline.setattr(public_data, "separated_season_stats", lambda pid, season, legacy: legacy)
        baseline.setitem(frozen_app.after_request_funcs, "players", [])
        baseline.setitem(frozen_app.after_request_funcs, "journey", [])
        baseline.setattr(
            public_data, "public_match_metadata", lambda *a, **kw: {"source": "public_match_data", "as_of": None}
        )
        original_jsonify = academy.jsonify

        def legacy_jsonify(payload):
            return original_jsonify(
                {
                    key: value
                    for key, value in payload.items()
                    if key not in {"public_match_data", "as_of", "source_label"}
                }
            )

        baseline.setattr(academy, "jsonify", legacy_jsonify)
        # Prime the existing API/team caches equally; no F2 enrichment runs here.
        client.get(f"/api/players/990001/{path}")
        expected_bytes, expected_json, expected_statements = measure()
    actual_bytes, actual_json, actual_statements = measure()
    assert actual_json == expected_json
    assert actual_bytes == expected_bytes
    assert len(actual_statements) == len(expected_statements)
    assert actual_statements == expected_statements
    print(f"OFF golden {path} rollups={rollups!r}: {len(actual_statements)} SQL statements")


def test_off_separation_never_loads_feeders(frozen_app, monkeypatch):
    from src.services.public_data import separated_season_stats

    monkeypatch.setenv("API_FOOTBALL_FROZEN", "0")
    monkeypatch.setattr(
        "src.services.public_data.public_match_metadata", Mock(side_effect=AssertionError("metadata loaded"))
    )
    monkeypatch.setattr(
        "src.services.season_rollup_service._FEEDERS", [Mock(side_effect=AssertionError("feeder loaded"))]
    )
    legacy = {"goals": 4, "clean_sheets": 1}
    assert separated_season_stats(990001, 2025, legacy) is legacy


@pytest.mark.parametrize("player_api_id", [None, 990009])
@pytest.mark.parametrize("existing_shadow", [False, True])
def test_frozen_local_approval_and_shadow_reactivation(frozen_app, player_api_id, existing_shadow):
    from src.models.showcase import LocalPlayer

    player = LocalPlayer(
        display_name="Approved Stored Player",
        status="pending",
        api_player_id=player_api_id,
        birth_date=date(2000, 1, 1),
        created_by_user_id=UserAccount.query.one().id,
    )
    db.session.add(player)
    db.session.flush()
    pid = player_api_id or -player.id
    if existing_shadow:
        if pid < 0:
            # A negative shadow belongs to an already approved local identity.
            player.status = "approved"
            player.api_player_id = pid
        db.session.add(PlayerShadow(player_api_id=pid, player_name="Existing", is_active=False))
    db.session.commit()
    response = frozen_app.test_client().post(
        f"/api/admin/local-players/{player.id}/review", json={"action": "approve"}, headers=_freeze_admin_headers()
    )
    assert response.status_code == 200, response.json
    assert db.session.get(LocalPlayer, player.id).status == "approved"
    shadow = PlayerShadow.query.filter_by(player_api_id=pid).one()
    assert shadow.is_active is True
    assert shadow.last_profile_sync_at is None
    assert shadow.last_stats_sync_at is None


def test_refollow_inactive_stored_shadow(frozen_app):
    from src.auth import issue_user_token

    db.session.add(PlayerShadow(player_api_id=990009, player_name="Stored Follow", is_active=False))
    db.session.commit()
    response = frozen_app.test_client().post(
        f"/api/scout/lists/{FollowList.query.one().id}/follows",
        headers={"Authorization": "Bearer " + issue_user_token("freeze@example.com")["token"]},
        json={"kind": "player", "selector": {"player_api_id": 990009}},
    )
    assert response.status_code == 201, response.json
    assert PlayerShadow.query.one().is_active is True


def test_frozen_clean_sheets_survive(frozen_app, monkeypatch):
    monkeypatch.setenv("SEASON_ROLLUP_READS", "")
    row = FixturePlayerStats.query.one()
    row.goals_conceded = 0
    row.position = "G"
    db.session.commit()
    response = frozen_app.test_client().get("/api/players/990001/season-stats?season=2025")
    assert response.status_code == 200, response.json
    assert response.json["clean_sheets"] == 1
    assert response.json["goals"] == 2


def test_frozen_limited_stats_use_db_compute(frozen_app, monkeypatch):
    monkeypatch.setenv("SEASON_ROLLUP_READS", "")
    player = TrackedPlayer.query.one()
    player.data_depth = "events_only"
    db.session.commit()
    original = TrackedPlayer.compute_stats
    calls = []

    def compute(self):
        calls.append(self.player_api_id)
        return original(self)

    monkeypatch.setattr(TrackedPlayer, "compute_stats", compute)
    response = frozen_app.test_client().get("/api/players/990001/season-stats")
    assert response.status_code == 200, response.json
    assert calls == [990001]


def test_frozen_cohort_db_repair(frozen_app):
    from src.models.cohort import AcademyCohort, CohortMember

    cohort = AcademyCohort(team_api_id=33, league_api_id=1, season=2025, total_players=99)
    db.session.add(cohort)
    db.session.flush()
    db.session.add(CohortMember(cohort_id=cohort.id, player_api_id=990001, current_status="first_team"))
    db.session.commit()
    response = frozen_app.test_client().post(
        f"/api/admin/cohorts/{cohort.id}/refresh-stats", headers=_freeze_admin_headers()
    )
    assert response.status_code == 200, response.json
    assert response.json["analytics"]["total_players"] == 1
    assert response.json["analytics"]["players_first_team"] == 1


@pytest.mark.parametrize(
    "module",
    [
        "jobs.run_" + name
        for name in [
            "weekly_newsletters",
            "weekly_newsletters_mcp",
            "full_rebuild",
            "status_refresh",
            "data_integrity_fix",
            "transfer_window_heal",
            "scout_digests",
        ]
    ]
    + ["scripts.enrich_newsletter_tweets"],
)
def test_frozen_job_entrypoints_exit_cleanly(frozen_app, monkeypatch, capsys, module):
    import runpy
    import sys

    monkeypatch.setattr(sys, "argv", [module])
    monkeypatch.delitem(sys.modules, "src." + module, raising=False)
    with pytest.raises(SystemExit) as exc:
        runpy.run_module("src." + module, run_name="__main__")
    assert exc.value.code == 1
    output = capsys.readouterr()
    assert "frozen" in output.err
    assert "Traceback" not in output.err + output.out


def test_nominatim_remains_independent_of_football_freeze(frozen_app, monkeypatch):
    from src.utils.geocoding import _nominatim_geocode

    request = Mock(return_value=Mock(json=lambda: [{"lat": "51.5", "lon": "-0.1"}]))
    monkeypatch.setattr("src.utils.geocoding.requests.get", request)
    assert _nominatim_geocode("Unknown City") == (51.5, -0.1)
    request.assert_called_once()


def _freeze_admin_headers():
    from src.auth import issue_user_token

    return {
        "X-API-Key": "freeze-key",
        "Authorization": "Bearer " + issue_user_token("freeze@example.com", role="admin")["token"],
    }
