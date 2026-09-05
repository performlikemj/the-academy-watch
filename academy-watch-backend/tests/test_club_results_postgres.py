"""Real PostgreSQL locking attacks for stable club-result writes."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from urllib.parse import urlparse
from uuid import uuid4

import pytest

# Import the broad C2 fixture module so db.metadata contains every application
# table before create_all. The test database is dedicated and disposable.
import test_club_console  # noqa: F401
from flask import Flask
from sqlalchemy import text
from src.auth import issue_user_token
from src.extensions import limiter
from src.models.funding import (
    ClubProgram,
    ClubProgramClaim,
    ClubProgramManager,
    ClubRosterMember,
    FundingLeague,
)
from src.models.league import League, Team, TeamProfile, UserAccount, db
from src.models.player_match_entry import ClubResult, PlayerMatchEntry
from src.models.season_rollup import PlayerSeasonCell, PlayerSeasonTotal
from src.models.showcase import PlayerClubAffiliation
from src.models.tracked_player import TrackedPlayer
from src.routes.club import club_bp
from src.services import season_rollup_service

POSTGRES_URL = os.getenv("PILOT_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="PILOT_TEST_POSTGRES_URL is absent")
PG14_INCOMPATIBLE_TABLES = {"player_transfer_events", "transfer_admin_events"}


def _validated_url() -> str:
    parsed = urlparse(POSTGRES_URL or "")
    assert parsed.scheme in {"postgres", "postgresql", "postgresql+psycopg"}, "PostgreSQL URL required"
    assert parsed.hostname in {None, "127.0.0.1", "localhost", "::1"}, (
        "PostgreSQL concurrency test refuses nonlocal hosts"
    )
    assert parsed.hostname is not None or not parsed.netloc, "PostgreSQL concurrency test refuses ambiguous hosts"
    database = parsed.path.removeprefix("/")
    assert database and any(marker in database.lower() for marker in ("test", "disposable")), (
        "PostgreSQL concurrency test refuses a database without test/disposable in its name"
    )
    return POSTGRES_URL


def _postgres_tables():
    # These unrelated transfer tables use PostgreSQL 15's NULLS NOT DISTINCT;
    # the contract's disposable server is PostgreSQL 14.
    return [table for table in db.metadata.sorted_tables if table.name not in PG14_INCOMPATIBLE_TABLES]


def _claim_manager(program_id: int, user_id: int) -> None:
    claim = ClubProgramClaim(
        program_id=program_id,
        user_account_id=user_id,
        relationship_type="club_official",
        status="approved",
    )
    db.session.add(claim)
    db.session.flush()
    db.session.add(
        ClubProgramManager(
            program_id=program_id,
            user_account_id=user_id,
            source_claim_id=claim.id,
            status="active",
            granted_by="p4-postgres-test",
        )
    )


@pytest.fixture(scope="session")
def postgres_app():
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SECRET_KEY="p4-postgres-fixture-secret",
        SQLALCHEMY_DATABASE_URI=_validated_url(),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        RATELIMIT_ENABLED=False,
    )
    db.init_app(app)
    limiter.init_app(app)
    app.register_blueprint(club_bp, url_prefix="/api")
    with app.app_context():
        # Connection/setup errors are deliberately allowed to fail the suite.
        db.session.execute(text("SELECT 1"))
        db.session.rollback()
        db.session.execute(text("DROP SCHEMA public CASCADE"))
        db.session.execute(text("CREATE SCHEMA public"))
        db.session.commit()
        db.metadata.create_all(db.engine, tables=_postgres_tables())
    yield app
    with app.app_context():
        db.session.remove()


@pytest.fixture
def pg_case(postgres_app):
    with postgres_app.app_context():
        db.session.remove()
        names = ", ".join(f'"{table.name}"' for table in reversed(_postgres_tables()))
        db.session.execute(text(f"TRUNCATE TABLE {names} RESTART IDENTITY CASCADE"))
        db.session.commit()

        league = League(league_id=9940, name="P4 PG League", country="Japan", season=2026)
        team_a = Team(team_id=9941, name="P4 PG A", country="Japan", season=2026, league=league)
        team_b = Team(team_id=9942, name="P4 PG B", country="Japan", season=2026, league=league)
        profiles = [
            TeamProfile(team_id=team_a.team_id, name=team_a.name, country="Japan"),
            TeamProfile(team_id=team_b.team_id, name=team_b.name, country="Japan"),
        ]
        funding = FundingLeague(
            name="P4 PostgreSQL League",
            country="Japan",
            region="Kanto",
            level="youth_regional",
            age_bands=["U18"],
            gender_program="both",
            season_calendar="calendar_year",
            data_tier="self_reported",
            registry_status="approved",
            admission_state="open",
        )
        db.session.add_all([league, team_a, team_b, *profiles, funding])
        db.session.flush()
        program_a = ClubProgram(
            funding_league_id=funding.id,
            name="Postgres Club A",
            legal_name="Postgres Club A Association",
            slug="p4-postgres-a",
            team_api_id=team_a.team_id,
            country="Japan",
            region="Kanto",
            platform_status="approved",
        )
        program_b = ClubProgram(
            funding_league_id=funding.id,
            name="Postgres Club B",
            legal_name="Postgres Club B Association",
            slug="p4-postgres-b",
            team_api_id=team_b.team_id,
            country="Japan",
            region="Kanto",
            platform_status="approved",
        )
        users = [
            UserAccount(email="pg-a@example.test", display_name="PG A", display_name_lower="pg a"),
            UserAccount(email="pg-a2@example.test", display_name="PG A2", display_name_lower="pg a2"),
            UserAccount(email="pg-b@example.test", display_name="PG B", display_name_lower="pg b"),
        ]
        db.session.add_all([program_a, program_b, *users])
        db.session.flush()
        _claim_manager(program_a.id, users[0].id)
        _claim_manager(program_a.id, users[1].id)
        _claim_manager(program_b.id, users[2].id)
        players = [
            TrackedPlayer(
                player_api_id=7041,
                player_name="Postgres Player One",
                birth_date="2001-01-01",
                position="Midfielder",
                team_id=team_a.id,
                current_club_api_id=team_a.team_id,
                status="academy",
                is_active=True,
            ),
            TrackedPlayer(
                player_api_id=7042,
                player_name="Postgres Player Two",
                birth_date="2000-01-01",
                position="Defender",
                team_id=team_a.id,
                current_club_api_id=team_a.team_id,
                status="academy",
                is_active=True,
            ),
        ]
        db.session.add_all(players)
        db.session.flush()
        members_a = [
            ClubRosterMember(program_id=program_a.id, player_api_id=player.player_api_id, added_by_user_id=users[0].id)
            for player in players
        ]
        member_b = ClubRosterMember(
            program_id=program_b.id,
            player_api_id=players[0].player_api_id,
            added_by_user_id=users[2].id,
        )
        db.session.add_all(
            [
                *members_a,
                member_b,
                PlayerClubAffiliation(
                    player_api_id=players[0].player_api_id,
                    team_api_id=team_b.team_id,
                    season="2025",
                    status="club_confirmed",
                ),
            ]
        )
        db.session.commit()
        tokens = {
            "a": issue_user_token(users[0].email)["token"],
            "a2": issue_user_token(users[1].email)["token"],
            "b": issue_user_token(users[2].email)["token"],
        }
        case = {
            "program_a": program_a.id,
            "program_b": program_b.id,
            "members_a": [member.id for member in members_a],
            "member_b": member_b.id,
            "tokens": tokens,
        }
    yield case
    with postgres_app.app_context():
        db.session.remove()


def _headers(case, actor="a"):
    return {"Authorization": f"Bearer {case['tokens'][actor]}"}


def _payload(member_ids, *, request_id=None, date="2025-09-01", opponent="Rivals FC", score=2):
    return {
        "client_request_id": request_id or str(uuid4()),
        "video_match_id": None,
        "match_date": date,
        "opponent": opponent,
        "competition": "County League",
        "home_away": "home",
        "result_for": score,
        "result_against": 1,
        "entries": [
            {
                "club_roster_member_id": member_id,
                "minutes": 90,
                "goals": 1,
                "assists": 0,
                "yellows": 0,
                "reds": 0,
                "saves": None,
                "goals_conceded": None,
                "note": None,
            }
            for member_id in member_ids
        ],
    }


def _correction(entry_ids, *, expected=1, date="2025-09-01", opponent="Rivals FC", score=3):
    return {
        "expected_version": expected,
        "video_match_id": None,
        "match_date": date,
        "opponent": opponent,
        "competition": "County League",
        "home_away": "home",
        "result_for": score,
        "result_against": 1,
        "entries": [
            {
                "entry_id": entry_id,
                "minutes": 90,
                "goals": 1,
                "assists": 0,
                "yellows": 0,
                "reds": 0,
                "saves": None,
                "goals_conceded": None,
                "note": None,
            }
            for entry_id in entry_ids
        ],
    }


def _parallel(app, functions):
    barrier = Barrier(len(functions))

    def invoke(function):
        with app.test_client() as client:
            barrier.wait(timeout=10)
            response = function(client)
            return response.status_code, response.get_json()

    with ThreadPoolExecutor(max_workers=len(functions)) as pool:
        futures = [pool.submit(invoke, function) for function in functions]
        return [future.result(timeout=30) for future in futures]


def _create(postgres_app, case, payload, actor="a", program="program_a"):
    with postgres_app.test_client() as client:
        return client.post(
            f"/api/club/{case[program]}/results",
            json=payload,
            headers=_headers(case, actor),
        )


def test_simultaneous_same_key_creates_one_header_and_lineup(postgres_app, pg_case):
    payload = _payload([pg_case["members_a"][0]], request_id=str(uuid4()))
    calls = [
        lambda client, actor=actor: client.post(
            f"/api/club/{pg_case['program_a']}/results", json=payload, headers=_headers(pg_case, actor)
        )
        for actor in ("a", "a2")
    ]
    outcomes = _parallel(postgres_app, calls)
    assert sorted(status for status, _ in outcomes) == [200, 201]
    with postgres_app.app_context():
        assert ClubResult.query.count() == 1
        assert PlayerMatchEntry.query.filter_by(source="club").count() == 1


def test_different_keys_in_one_fixture_slot_have_one_winner(postgres_app, pg_case):
    payloads = [_payload([pg_case["members_a"][0]]), _payload([pg_case["members_a"][0]])]
    outcomes = _parallel(
        postgres_app,
        [
            lambda client, payload=payload: client.post(
                f"/api/club/{pg_case['program_a']}/results", json=payload, headers=_headers(pg_case)
            )
            for payload in payloads
        ],
    )
    assert sorted(status for status, _ in outcomes) == [201, 409]
    assert [body["error"] for status, body in outcomes if status == 409] == ["result_already_exists"]


def test_same_version_corrections_have_one_winner(postgres_app, pg_case):
    created = _create(postgres_app, pg_case, _payload([pg_case["members_a"][0]]))
    result_id = created.json["result"]["id"]
    entry_id = created.json["matches"][0]["id"]
    calls = [
        lambda client, score=score, actor=actor: client.put(
            f"/api/club/{pg_case['program_a']}/results/{result_id}",
            json=_correction([entry_id], score=score),
            headers=_headers(pg_case, actor),
        )
        for score, actor in ((3, "a"), (4, "a2"))
    ]
    outcomes = _parallel(postgres_app, calls)
    assert sorted(status for status, _ in outcomes) == [200, 409]
    assert [body["error"] for status, body in outcomes if status == 409] == ["result_version_conflict"]


def test_correction_racing_deletion_never_resurrects(postgres_app, pg_case):
    created = _create(postgres_app, pg_case, _payload([pg_case["members_a"][0]]))
    result_id = created.json["result"]["id"]
    entry_id = created.json["matches"][0]["id"]
    outcomes = _parallel(
        postgres_app,
        [
            lambda client: client.put(
                f"/api/club/{pg_case['program_a']}/results/{result_id}",
                json=_correction([entry_id]),
                headers=_headers(pg_case),
            ),
            lambda client: client.delete(
                f"/api/club/{pg_case['program_a']}/results/{result_id}",
                json={"expected_version": 1},
                headers=_headers(pg_case, "a2"),
            ),
        ],
    )
    assert sorted(status for status, _ in outcomes) == [200, 409]
    with postgres_app.app_context():
        row = db.session.get(ClubResult, result_id)
        assert row.version == 2
        lines = PlayerMatchEntry.query.filter_by(club_result_id=result_id).all()
        assert (row.deleted_at is not None and lines == []) or (
            row.deleted_at is None and len(lines) == 1 and row.result_for == 3
        )


def test_two_programs_conflicting_player_fixture_have_one_winner(postgres_app, pg_case):
    outcomes = _parallel(
        postgres_app,
        [
            lambda client: client.post(
                f"/api/club/{pg_case['program_a']}/results",
                json=_payload([pg_case["members_a"][0]]),
                headers=_headers(pg_case),
            ),
            lambda client: client.post(
                f"/api/club/{pg_case['program_b']}/results",
                json=_payload([pg_case["member_b"]]),
                headers=_headers(pg_case, "b"),
            ),
        ],
    )
    assert sorted(status for status, _ in outcomes) == [201, 409]
    with postgres_app.app_context():
        assert PlayerMatchEntry.query.filter_by(source="club").count() == 1


def test_concurrent_results_sharing_player_keep_totals(postgres_app, pg_case):
    payloads = [
        _payload([pg_case["members_a"][0]], date="2025-09-02", opponent="North FC"),
        _payload([pg_case["members_a"][0]], date="2025-09-03", opponent="South FC"),
    ]
    outcomes = _parallel(
        postgres_app,
        [
            lambda client, payload=payload: client.post(
                f"/api/club/{pg_case['program_a']}/results", json=payload, headers=_headers(pg_case)
            )
            for payload in payloads
        ],
    )
    assert [status for status, _ in outcomes] == [201, 201]
    with postgres_app.app_context():
        total = PlayerSeasonTotal.query.filter_by(player_api_id=7041, season=2025, level_group="senior").one()
        assert (total.appearances, total.minutes) == (2, 180)


def test_opposite_lineup_order_uses_deterministic_locks(postgres_app, pg_case):
    first, second = pg_case["members_a"]
    outcomes = _parallel(
        postgres_app,
        [
            lambda client: client.post(
                f"/api/club/{pg_case['program_a']}/results",
                json=_payload([first, second], date="2025-09-04", opponent="East FC"),
                headers=_headers(pg_case),
            ),
            lambda client: client.post(
                f"/api/club/{pg_case['program_a']}/results",
                json=_payload([second, first], date="2025-09-05", opponent="West FC"),
                headers=_headers(pg_case, "a2"),
            ),
        ],
    )
    assert [status for status, _ in outcomes] == [201, 201]


def test_forced_mid_refresh_failure_rolls_back_both_seasons(postgres_app, pg_case, monkeypatch):
    created = _create(
        postgres_app,
        pg_case,
        _payload([pg_case["members_a"][0]], date="2025-07-31"),
    )
    result_id = created.json["result"]["id"]
    entry_id = created.json["matches"][0]["id"]
    with postgres_app.app_context():
        before_header = tuple(
            getattr(db.session.get(ClubResult, result_id), name) for name in ("version", "match_date")
        )
        before_entries = [
            tuple(getattr(row, column.name) for column in PlayerMatchEntry.__table__.columns)
            for row in PlayerMatchEntry.query.filter_by(club_result_id=result_id).all()
        ]
        before_cells = PlayerSeasonCell.query.filter_by(player_api_id=7041).count()
        before_totals = PlayerSeasonTotal.query.filter_by(player_api_id=7041).count()

    original = season_rollup_service.refresh_player
    calls = 0

    def fail_after_first(*args, **kwargs):
        nonlocal calls
        result = original(*args, **kwargs)
        calls += 1
        if calls == 1:
            raise RuntimeError("forced mid-refresh failure")
        return result

    monkeypatch.setattr(season_rollup_service, "refresh_player", fail_after_first)
    with postgres_app.test_client() as client:
        failed = client.put(
            f"/api/club/{pg_case['program_a']}/results/{result_id}",
            json=_correction([entry_id], date="2025-08-01", opponent="Moved FC"),
            headers=_headers(pg_case),
        )
    assert failed.status_code == 500
    assert failed.json == {"error": "result_operation_failed"}
    with postgres_app.app_context():
        row = db.session.get(ClubResult, result_id)
        assert tuple(getattr(row, name) for name in ("version", "match_date")) == before_header
        assert [
            tuple(getattr(entry, column.name) for column in PlayerMatchEntry.__table__.columns)
            for entry in PlayerMatchEntry.query.filter_by(club_result_id=result_id).all()
        ] == before_entries
        assert PlayerSeasonCell.query.filter_by(player_api_id=7041).count() == before_cells
        assert PlayerSeasonTotal.query.filter_by(player_api_id=7041).count() == before_totals
