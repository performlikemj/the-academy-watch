"""Tests for the admin Operations endpoints.

Covers:
- GET /api/admin/ops/overview — response shape and aggregate counts
- the 410 tombstone on the retired single-transaction
  POST /api/admin/tracked-players/recompute-academy-ids
"""

import uuid

import pytest
from flask import Flask
from src.models.api_cache import APIUsageDaily
from src.models.journey import PlayerJourney, PlayerJourneyEntry
from src.models.league import AdminSetting, BackgroundJob, League, Team, db
from src.models.tracked_player import TrackedPlayer

ADMIN_KEY = "test-admin-key"


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("SKIP_API_HANDSHAKE", "1")
    monkeypatch.setenv("API_USE_STUB_DATA", "true")
    monkeypatch.setenv("ADMIN_API_KEY", ADMIN_KEY)
    monkeypatch.setenv("ADMIN_IP_WHITELIST", "")
    # Pin the league footprint to defaults so crawl assertions are stable
    monkeypatch.delenv("SUPPORTED_LEAGUE_IDS", raising=False)
    monkeypatch.delenv("CRAWL_LEAGUE_IDS", raising=False)

    from src.routes.api import api_bp
    from src.routes.ops import ops_bp

    flask_app = Flask(__name__)
    flask_app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret-key",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )

    db.init_app(flask_app)
    flask_app.register_blueprint(ops_bp, url_prefix="/api")
    flask_app.register_blueprint(api_bp, url_prefix="/api")

    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def admin_headers(app):
    from src.auth import issue_user_token

    token = issue_user_token("admin@test.com", role="admin")["token"]
    return {"Authorization": f"Bearer {token}", "X-API-Key": ADMIN_KEY}


def _seed_team():
    league = League(league_id=39, name="Premier League", country="England", season=2025)
    db.session.add(league)
    db.session.flush()
    team = Team(
        team_id=33, name="Manchester United", country="England", season=2025, league_id=league.id, is_active=True
    )
    db.session.add(team)
    db.session.flush()
    return team


def _tracked(team, player_api_id, name, **kwargs):
    tp = TrackedPlayer(
        player_api_id=player_api_id,
        player_name=name,
        team_id=team.id,
        status=kwargs.pop("status", "academy"),
        data_source=kwargs.pop("data_source", "journey-sync"),
        is_active=kwargs.pop("is_active", True),
        **kwargs,
    )
    db.session.add(tp)
    db.session.flush()
    return tp


def _journey(player_api_id, with_entry):
    journey = PlayerJourney(player_api_id=player_api_id, player_name=f"Journey {player_api_id}")
    db.session.add(journey)
    db.session.flush()
    if with_entry:
        entry = PlayerJourneyEntry(
            journey_id=journey.id,
            season=2024,
            club_api_id=33,
            club_name="Manchester United",
            league_api_id=39,
            league_name="Premier League",
            league_country="England",
            level="First Team",
            entry_type="first_team",
            is_youth=False,
            is_international=False,
            appearances=10,
            goals=0,
            assists=0,
            minutes=900,
        )
        db.session.add(entry)
        db.session.flush()
    return journey


class TestOpsOverview:
    def test_requires_auth(self, client):
        res = client.get("/api/admin/ops/overview")
        assert res.status_code == 401

    def test_response_shape_empty_db(self, client, admin_headers):
        res = client.get("/api/admin/ops/overview", headers=admin_headers)
        assert res.status_code == 200
        data = res.get_json()

        assert set(data.keys()) == {"tracked", "journeys", "crawl", "jobs", "runs_paused", "api_usage_today"}
        assert data["tracked"] == {
            "active": 0,
            "inactive": 0,
            "placeholder_names": 0,
            "null_position": 0,
            "null_birth_date": 0,
            "null_age": 0,
            "owning_club_active": 0,
        }
        assert data["journeys"] == {"total": 0, "with_entries": 0}
        assert data["jobs"] == {"active": 0}
        assert data["runs_paused"] is False
        # APIUsageDaily table exists in this app, so usage is an int (0)
        assert data["api_usage_today"] == 0

    def test_crawl_section(self, client, admin_headers):
        res = client.get("/api/admin/ops/overview", headers=admin_headers)
        data = res.get_json()

        crawl = data["crawl"]
        assert crawl["crawl_league_ids"] == [39, 140, 135, 78, 61]
        leagues = crawl["supported_leagues"]
        assert {"id": 39, "name": "Premier League", "region": "Europe"} in leagues
        assert all(set(entry.keys()) == {"id", "name", "region"} for entry in leagues)
        # The supported footprint is wider than the crawl footprint
        assert len(leagues) > len(crawl["crawl_league_ids"])

    def test_tracked_journey_and_job_counts(self, client, admin_headers):
        team = _seed_team()
        # Active, fully-populated row
        _tracked(
            team,
            1001,
            "Kobbie Mainoo",
            position="Midfielder",
            birth_date="2005-04-19",
            age=21,
        )
        # Inactive row — never counted in the hygiene columns
        _tracked(team, 1002, "Player 1002", is_active=False)
        # Active placeholder with NULL position/birth_date/age
        _tracked(team, 1003, "Player 1003")
        # Active deprecated owning-club row, fully populated
        _tracked(
            team,
            1004,
            "Tyrell Malacia",
            data_source="owning-club",
            position="Defender",
            birth_date="1999-08-17",
            age=26,
        )

        _journey(1001, with_entry=True)
        _journey(1003, with_entry=False)

        db.session.add(BackgroundJob(id=str(uuid.uuid4()), job_type="seed_top5", status="running"))
        db.session.add(BackgroundJob(id=str(uuid.uuid4()), job_type="seed_top5", status="completed"))
        db.session.commit()

        res = client.get("/api/admin/ops/overview", headers=admin_headers)
        assert res.status_code == 200
        data = res.get_json()

        assert data["tracked"] == {
            "active": 3,
            "inactive": 1,
            "placeholder_names": 1,
            "null_position": 1,
            "null_birth_date": 1,
            "null_age": 1,
            "owning_club_active": 1,
        }
        assert data["journeys"] == {"total": 2, "with_entries": 1}
        assert data["jobs"] == {"active": 1}

    def test_runs_paused_reflects_admin_setting(self, client, admin_headers):
        db.session.add(AdminSetting(key="runs_paused", value_json="true"))
        db.session.commit()

        res = client.get("/api/admin/ops/overview", headers=admin_headers)
        assert res.get_json()["runs_paused"] is True

    def test_api_usage_today_counts_calls(self, client, admin_headers):
        APIUsageDaily.increment("players")
        APIUsageDaily.increment("players")
        APIUsageDaily.increment("fixtures")

        res = client.get("/api/admin/ops/overview", headers=admin_headers)
        assert res.get_json()["api_usage_today"] == 3


class TestLegacyRecomputeTombstone:
    def test_legacy_recompute_academy_ids_is_410(self, client, admin_headers):
        res = client.post(
            "/api/admin/tracked-players/recompute-academy-ids",
            json={"dry_run": True},
            headers=admin_headers,
        )
        assert res.status_code == 410
        data = res.get_json()
        assert data["use"] == "/api/admin/journeys/recompute-academy"
        assert "error" in data

    def test_legacy_recompute_academy_ids_still_requires_auth(self, client):
        res = client.post("/api/admin/tracked-players/recompute-academy-ids", json={})
        assert res.status_code == 401
