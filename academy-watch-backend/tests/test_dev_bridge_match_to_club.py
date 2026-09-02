"""SQLite coverage for the development-only match-to-club fixture bridge."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from flask import Flask
from scripts.dev.bridge_match_to_club import (
    ALLOW_ENV,
    DEV_LEAGUE_NAME,
    BridgeRefused,
    execute_bridge,
    guard_database_target,
    guard_runtime_environment,
)
from src.auth import issue_user_token
from src.extensions import limiter
from src.models.funding import (
    ClubProgram,
    ClubProgramClaim,
    ClubProgramManager,
    ClubRosterMember,
    FundingLeague,
)
from src.models.league import League, Team, UserAccount, db
from src.models.showcase import LocalPlayer
from src.models.video import VideoMatch, VideoRosterEntry, VideoTracklet
from src.routes.club import club_bp
from src.routes.funding import funding_bp
from src.routes.video import video_bp

MANAGER_EMAIL = "fixture-manager@example.com"


@pytest.fixture
def bridge_app(monkeypatch):
    monkeypatch.setenv(ALLOW_ENV, "1")
    monkeypatch.setenv("FLASK_ENV", "development")
    monkeypatch.delenv("APP_ENV", raising=False)

    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SECRET_KEY="dev-fixture-bridge-test-secret",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        RATELIMIT_ENABLED=False,
    )
    db.init_app(app)
    limiter.init_app(app)
    app.register_blueprint(funding_bp, url_prefix="/api")
    app.register_blueprint(club_bp, url_prefix="/api")
    app.register_blueprint(video_bp, url_prefix="/api")

    ctx = app.app_context()
    ctx.push()
    db.create_all()

    source_league = League(league_id=4401, name="Fixture source league", country="England", season=2026)
    source_team = Team(
        team_id=4402,
        name="AFC Yorkies",
        country="England",
        season=2026,
        league=source_league,
    )
    manager = UserAccount(
        email=MANAGER_EMAIL,
        display_name="Fixture Manager",
        display_name_lower="fixture manager",
    )
    db.session.add_all([source_league, source_team, manager])
    db.session.flush()
    match = VideoMatch(
        team_id=source_team.id,
        opponent_name="Development United",
        status="finalized",
        our_team_cluster=0,
        finalized_at=datetime.now(UTC),
    )
    db.session.add(match)
    db.session.flush()
    for number in range(1, 19):
        entry = VideoRosterEntry(
            video_match_id=match.id,
            player_name=f"Fixture Player {number}",
            jersey_number=number,
            position="Goalkeeper" if number == 1 else "Outfield",
        )
        db.session.add(entry)
        db.session.flush()
        db.session.add(
            VideoTracklet(
                video_match_id=match.id,
                roster_entry_id=entry.id,
                kind="chain",
                pipeline_key=f"T0#{number}",
                team_cluster=0,
                suggested_number=number,
                confidence="high",
                first_s=float(number * 10),
                last_s=float(number * 10 + 4),
                visible_s=4.0,
            )
        )
    db.session.commit()
    app.bridge = {"match_id": match.id, "manager_id": manager.id}

    yield app

    db.session.remove()
    db.drop_all()
    ctx.pop()


def _run(app, **overrides):
    values = {
        "match_id": app.bridge["match_id"],
        "manager_email": MANAGER_EMAIL,
    }
    values.update(overrides)
    return execute_bridge(app, **values)


def _manager_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_user_token(MANAGER_EMAIL)['token']}"}


def _row_counts() -> dict[str, int]:
    return {
        "funding_leagues": FundingLeague.query.count(),
        "club_programs": ClubProgram.query.count(),
        "program_claims": ClubProgramClaim.query.count(),
        "program_managers": ClubProgramManager.query.count(),
        "local_players": LocalPlayer.query.count(),
        "roster_members": ClubRosterMember.query.count(),
    }


def test_bridge_refuses_without_explicit_opt_in(monkeypatch):
    monkeypatch.delenv(ALLOW_ENV, raising=False)
    monkeypatch.setenv("FLASK_ENV", "development")
    monkeypatch.delenv("APP_ENV", raising=False)

    with pytest.raises(BridgeRefused, match="set ALLOW_FIXTURE_BRIDGE=1"):
        guard_runtime_environment()


@pytest.mark.parametrize(
    ("env_name", "env_value"),
    [("FLASK_ENV", "production"), ("APP_ENV", "prod-eu"), ("APP_ENV", "staging")],
)
def test_bridge_refuses_production_like_environments(monkeypatch, env_name, env_value):
    monkeypatch.setenv(ALLOW_ENV, "1")
    monkeypatch.setenv("FLASK_ENV", "development")
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv(env_name, env_value)

    with pytest.raises(BridgeRefused, match="looks like production"):
        guard_runtime_environment()


@pytest.mark.parametrize(
    "database_uri",
    [
        "postgresql+psycopg://dev:secret@db.example.supabase.co/dev",
        "postgresql+psycopg://dev:secret@aws-1-us-west-1.pooler.example/dev",
    ],
)
def test_bridge_refuses_supabase_and_pooler_hosts(database_uri):
    with pytest.raises(BridgeRefused, match="not an allowed dev target"):
        guard_database_target(database_uri)


def test_bridge_refuses_match_already_assigned_to_different_program(bridge_app):
    other_league = FundingLeague(
        name="Other league",
        country="England",
        region="Yorkshire",
        level="recreational",
        age_bands=[],
        gender_program="both",
        season_calendar="fall_spring",
        data_tier="film_room",
        registry_status="approved",
        admission_state="open",
    )
    db.session.add(other_league)
    db.session.flush()
    other_program = ClubProgram(
        funding_league_id=other_league.id,
        name="Other Club",
        legal_name="Other Club",
        slug="other-club-existing-fixture",
        country="England",
        region="Yorkshire",
        platform_status="approved",
    )
    db.session.add(other_program)
    db.session.flush()
    match = db.session.get(VideoMatch, bridge_app.bridge["match_id"])
    match.club_program_id = other_program.id
    db.session.commit()

    with pytest.raises(BridgeRefused, match="already has different club_program_id"):
        _run(bridge_app)

    assert FundingLeague.query.filter_by(name=DEV_LEAGUE_NAME).count() == 0
    assert match.club_program_id == other_program.id
    assert LocalPlayer.query.count() == 0


def test_full_bridge_activates_console_and_exposes_all_reel_players(bridge_app):
    summary = _run(bridge_app)

    assert summary["dry_run"] is False
    assert summary["my_club_path"] == "/my-club"
    assert summary["counts"] == {
        "funding_leagues": {"created": 1, "existing": 0},
        "club_programs": {"created": 1, "existing": 0},
        "program_claims": {"created": 1, "existing": 0},
        "program_managers": {"created": 1, "existing": 0},
        "local_players": {"created": 18, "existing": 0},
        "roster_members": {"created": 18, "existing": 0},
        "roster_entry_links": {"created": 18, "existing": 0},
    }

    match = db.session.get(VideoMatch, bridge_app.bridge["match_id"])
    assert match.club_program_id == summary["program_id"]
    assert match.roster_entries.filter(VideoRosterEntry.club_roster_member_id.is_(None)).count() == 0

    league = FundingLeague.query.filter_by(name=DEV_LEAGUE_NAME).one()
    program = db.session.get(ClubProgram, summary["program_id"])
    claim = ClubProgramClaim.query.filter_by(
        program_id=program.id,
        user_account_id=bridge_app.bridge["manager_id"],
    ).one()
    grant = ClubProgramManager.query.filter_by(
        program_id=program.id,
        user_account_id=bridge_app.bridge["manager_id"],
    ).one()
    assert (league.registry_status, league.admission_state) == ("approved", "open")
    assert program.name == "AFC Yorkies"
    assert program.platform_status == "approved"
    assert program.emergency_hidden is False
    assert claim.status == "approved"
    assert grant.status == "active"
    assert grant.source_claim_id == claim.id

    local_players = LocalPlayer.query.order_by(LocalPlayer.id).all()
    assert len(local_players) == 18
    assert all(player.status == "approved" for player in local_players)
    assert all(player.created_by_user_id == bridge_app.bridge["manager_id"] for player in local_players)

    client = bridge_app.test_client()
    roster = client.get(f"/api/club/{program.id}/roster", headers=_manager_headers())
    assert roster.status_code == 200
    roster_body = roster.get_json()
    assert roster_body["count"] == 18
    assert len(roster_body["members"]) == 18
    if hasattr(ClubRosterMember, "coach_brief_body"):
        assert all("brief" in member for member in roster_body["members"])
    else:
        assert all("brief" not in member for member in roster_body["members"])

    claims = client.get("/api/funding/claims/me", headers=_manager_headers())
    assert claims.status_code == 200
    assert claims.get_json()["claims"][0]["status"] == "approved"
    assert claims.get_json()["claims"][0]["program"]["platform_status"] == "approved"

    reel = client.get(f"/api/club/{program.id}/matches/{match.id}/reel", headers=_manager_headers())
    assert reel.status_code == 200
    players = reel.get_json()["players"]
    assert len(players) == 18
    assert [player["jersey_number"] for player in players] == list(range(1, 19))


def test_bridge_is_idempotent_and_second_run_creates_no_rows(bridge_app):
    first = _run(bridge_app, program_name="AFC Yorkies")
    counts_after_first = _row_counts()
    member_ids = [row["club_roster_member_id"] for row in first["members"]]

    second = _run(bridge_app, program_name="AFC Yorkies")

    assert _row_counts() == counts_after_first
    assert all(values["created"] == 0 for values in second["counts"].values())
    assert second["counts"]["local_players"]["existing"] == 18
    assert second["counts"]["roster_members"]["existing"] == 18
    assert second["counts"]["roster_entry_links"]["existing"] == 18
    assert [row["club_roster_member_id"] for row in second["members"]] == member_ids


def test_dry_run_rolls_back_fixture_rows_and_links(bridge_app):
    summary = _run(bridge_app, dry_run=True)

    assert summary["dry_run"] is True
    assert summary["counts"]["local_players"]["created"] == 18
    assert _row_counts() == {
        "funding_leagues": 0,
        "club_programs": 0,
        "program_claims": 0,
        "program_managers": 0,
        "local_players": 0,
        "roster_members": 0,
    }
    match = db.session.get(VideoMatch, bridge_app.bridge["match_id"])
    assert match.club_program_id is None
    assert match.roster_entries.filter(VideoRosterEntry.club_roster_member_id.is_not(None)).count() == 0
