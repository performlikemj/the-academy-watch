"""Global search adds community adults without exposing private identities."""

import os
from datetime import UTC, date, datetime

import pytest
import sqlalchemy as sa
from flask import Flask
from sqlalchemy import event
from src.models.league import Team, db
from src.models.player_suppression import PlayerSuppression
from src.models.showcase import LocalPlayer
from src.models.tracked_player import TrackedPlayer


def local_player(pid, **changes):
    row = LocalPlayer(
        id=pid,
        api_player_id=-pid,
        display_name=f"Test Reuben {pid}",
        normalized_name=f"test reuben {pid}",
        birth_date=date(2000, 1, 1),
        birth_year=2000,
        status="approved",
        provenance="user",
        position="Right winger",
        club_name="Test Club",
    )
    for key, value in changes.items():
        setattr(row, key, value)
    db.session.add(row)
    db.session.commit()
    return row


def test_global_search_includes_public_community_adult(app, client):
    local_player(71)
    results = client.get("/api/players/search?q=Reuben").get_json()
    assert results == [
        {
            "player_api_id": -71,
            "player_name": "Test Reuben 71",
            "photo_url": None,
            "position": "Right winger",
            "team_name": None,
            "current_club_name": "Test Club",
        }
    ]
    assert client.get("/api/players/search?q=R").get_json() == []


@pytest.mark.parametrize(
    "changes",
    [
        {"birth_date": date(datetime.now(UTC).year - 16, 1, 1)},
        {"birth_date": None, "birth_year": datetime.now(UTC).year - 18},
        {"birth_date": None, "birth_year": None},
        {"provenance": "club"},
        {"status": "pending"},
        {"status": "rejected"},
        {"merged_into_local_player_id": 72},
        {"api_player_id": None},
    ],
)
def test_global_search_never_exposes_private_or_uncertain_adult(app, client, changes):
    if changes.get("merged_into_local_player_id"):
        local_player(72, display_name="Merge Target")
    local_player(71, **changes)
    assert client.get("/api/players/search?q=Reuben").get_json() == []


def test_global_search_rechecks_suppression(app, client):
    local_player(71)
    db.session.add(
        PlayerSuppression(
            local_player_id=71,
            status="active",
            reason_code="player_request",
            requester_role="player",
            requester_contact="test@example.com",
            request_statement="Hide my profile",
        )
    )
    db.session.commit()
    assert client.get("/api/players/search?q=Reuben").get_json() == []


def test_global_search_hides_held_club_and_restores_after_lift(app, client):
    from src.models.funding import ClubProgram, FundingLeague

    league = FundingLeague(
        name="Test League",
        country="JP",
        region="Test",
        level="recreational",
        gender_program="both",
        season_calendar="calendar_year",
        data_tier="self_reported",
        registry_status="approved",
        admission_state="open",
    )
    db.session.add(league)
    db.session.flush()
    program = ClubProgram(
        funding_league_id=league.id,
        name="Test Club",
        legal_name="Test Club",
        slug="test-club",
        country="JP",
        region="Test",
        platform_status="approved",
        emergency_hidden=True,
    )
    db.session.add(program)
    db.session.flush()
    local_player(71, origin_program_id=program.id)
    assert client.get("/api/players/search?q=Reuben").get_json() == []
    program.emergency_hidden = False
    db.session.commit()
    assert client.get("/api/players/search?q=Reuben").get_json()[0]["player_api_id"] == -71


@pytest.fixture(autouse=True)
def community_discovery_on(monkeypatch):
    monkeypatch.setenv("SCOUT_INCLUDE_LOCAL_PLAYERS", "1")


@pytest.fixture(params=["sqlite", "postgres"])
def app(app, request):
    """Run the same public-search/privacy regressions on both database engines."""
    if request.param == "sqlite":
        yield app
        return
    uri = os.getenv("UXM1_TEST_DATABASE_URL")
    if not uri:
        pytest.skip("set UXM1_TEST_DATABASE_URL for isolated PostgreSQL search regressions")
    url = sa.engine.make_url(uri)
    assert url.database == "aw_uxm1f3" and url.host in {"localhost", "127.0.0.1"}
    pg = Flask(__name__)
    pg.config.update(SECRET_KEY="uxm1-test-only", TESTING=True, SQLALCHEMY_DATABASE_URI=uri, RATELIMIT_ENABLED=False)
    db.init_app(pg)
    from src.routes.api import api_bp

    pg.register_blueprint(api_bp, url_prefix="/api")
    with pg.app_context():
        db.create_all()
        try:
            yield pg
        finally:
            db.session.remove()
            db.drop_all()
            db.engine.dispose()


def capture_search(client):
    statements = []

    def capture(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(db.engine, "before_cursor_execute", capture)
    try:
        response = client.get("/api/players/search?q=Needle")
        assert response.status_code == 200
        return response.get_json(), statements
    finally:
        event.remove(db.engine, "before_cursor_execute", capture)


@pytest.mark.parametrize("hidden", ["minor", "suppressed", "held"])
def test_eligibility_precedes_cap_with_bounded_query_count(app, client, hidden):
    from src.models.funding import ClubProgram, FundingLeague

    program_id = None
    if hidden == "held":
        league = FundingLeague(
            name="Needle League",
            country="JP",
            region="Test",
            level="recreational",
            gender_program="both",
            season_calendar="calendar_year",
            data_tier="self_reported",
            registry_status="approved",
            admission_state="open",
        )
        db.session.add(league)
        db.session.flush()
        program = ClubProgram(
            funding_league_id=league.id,
            name="Needle Club",
            legal_name="Needle Club",
            slug="needle-club",
            country="JP",
            region="Test",
            platform_status="approved",
            emergency_hidden=True,
        )
        db.session.add(program)
        db.session.flush()
        program_id = program.id
    adult = local_player(1101, display_name="Needle 999")
    baseline, baseline_sql = capture_search(client)
    assert [r["player_api_id"] for r in baseline] == [adult.api_player_id]
    for pid in range(1000, 1101):
        local_player(
            pid,
            display_name=f"Needle {pid - 1000:03}",
            birth_date=date(2015, 1, 1) if hidden == "minor" else date(2000, 1, 1),
            origin_program_id=program_id,
        )
        if hidden == "suppressed":
            db.session.add(
                PlayerSuppression(
                    local_player_id=pid,
                    status="active",
                    reason_code="player_request",
                    requester_role="player",
                    requester_contact="test@example.com",
                    request_statement="Hide",
                )
            )
    db.session.commit()
    results, sql = capture_search(client)
    assert results == baseline
    assert len(sql) == len(baseline_sql)
    assert len(sql) <= 10


def seed_provider_names(names):
    team = Team(team_id=33, name="Needle Academy", country="England", season=2025)
    db.session.add(team)
    db.session.flush()
    for pid, name in enumerate(names, 1):
        db.session.add(
            TrackedPlayer(
                player_api_id=pid,
                player_name=name,
                birth_date="2000-01-01",
                team_id=team.id,
                is_active=True,
                position="Midfielder",
                current_club_name="Provider Club",
            )
        )
    db.session.commit()


def test_switch_off_preserves_provider_payload_order_and_query_work(app, client, monkeypatch):
    seed_provider_names(["Needle Zed", "Needle Álvaro", "Needle Arnold"])
    monkeypatch.delenv("SCOUT_INCLUDE_LOCAL_PLAYERS", raising=False)
    baseline, baseline_sql = capture_search(client)
    assert len(baseline) == 3
    local_player(71, display_name="Needle Community")
    results, sql = capture_search(client)
    assert results == baseline
    assert sql == baseline_sql
    # The policy helper can read existing bridges; no new community-name candidate scan when OFF.
    assert not any("local_players.display_name ILIKE" in s or "lower(local_players.display_name)" in s for s in sql)
    monkeypatch.setenv("SCOUT_INCLUDE_LOCAL_PLAYERS", "on")
    assert -71 in [r["player_api_id"] for r in capture_search(client)[0]]
    monkeypatch.setenv("SCOUT_INCLUDE_LOCAL_PLAYERS", "false")
    assert capture_search(client)[0] == baseline


def test_on_preserves_provider_relative_order_and_ranks_accents_in_community(app, client, monkeypatch):
    seed_provider_names(["Needle Zed", "Needle Álvaro", "Needle Arnold"])
    monkeypatch.setenv("SCOUT_INCLUDE_LOCAL_PLAYERS", "0")
    providers = capture_search(client)[0]
    for pid, name in enumerate(["Needle Zulu", "Needle Álvaro Community", "Needle Bravo"], 71):
        local_player(pid, display_name=name)
    monkeypatch.setenv("SCOUT_INCLUDE_LOCAL_PLAYERS", "1")
    results = capture_search(client)[0]
    assert [r for r in results if r["player_api_id"] > 0] == providers
    assert [r["player_name"] for r in results if r["player_api_id"] < 0] == [
        "Needle Álvaro Community",
        "Needle Bravo",
        "Needle Zulu",
    ]


def test_result_cap_is_eight_eligible_adults(app, client):
    for pid in range(1, 13):
        local_player(pid, display_name=f"Needle {pid:02}")
    results = capture_search(client)[0]
    assert [r["player_api_id"] for r in results] == list(range(-1, -9, -1))
