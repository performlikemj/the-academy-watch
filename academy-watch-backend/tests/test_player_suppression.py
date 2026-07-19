"""FC-TF2 player takedown intake and cross-surface suppression tests.

The suite is intentionally offline: API clients and the one card-generation
call are faked, while every suppression assertion exercises the real database
predicate or HTTP serializer.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory
from flask import Flask
from sqlalchemy import event
from src.api_football_client import APIFootballClient, _academy_watch_for_team
from src.auth import _ensure_user_account, issue_user_token
from src.extensions import limiter
from src.models.contact import ContactRequest
from src.models.follow import Follow, FollowList, PlayerShadow
from src.models.league import (
    AcademyPlayerSeasonStats,
    CommunityTake,
    League,
    Player,
    Team,
    UserAccount,
    db,
)
from src.models.player_suppression import PlayerSuppression
from src.models.pulse import PlayerCardCache, PlayerPulse
from src.models.scout_watchlist import ScoutWatchlistEntry
from src.models.showcase import PlayerProfileClaim, PlayerShowcaseProfile
from src.models.tracked_player import TrackedPlayer
from src.models.trust import ScoutVerification
from src.models.weekly import Fixture, FixturePlayerStats
from src.services.contact import utcnow
from src.services.player_suppression import PlayerSuppressedError

VISIBLE_ID = 910_001
SUPPRESSED_ID = 910_002
SHADOW_ONLY_ID = 910_003
UNKNOWN_ID = 999_991
WINDOW_END = date(2025, 9, 8)
ADMIN_KEY = "tf2-admin-test-key"
FERNET_KEY = "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="
NEUTRAL_NOT_FOUND = {"error": "Player not found"}


@pytest.fixture
def suppression_app(monkeypatch):
    """App containing every FC-TF2 surface, backed by isolated SQLite."""

    monkeypatch.setenv("SKIP_API_HANDSHAKE", "1")
    monkeypatch.setenv("API_USE_STUB_DATA", "true")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.com")
    monkeypatch.setenv("ADMIN_API_KEY", ADMIN_KEY)
    monkeypatch.setenv("ADMIN_IP_WHITELIST", "")
    monkeypatch.setenv("CONTACT_RAIL_ENABLED", "true")
    monkeypatch.setenv("PLAYER_SUPPRESSION_ENCRYPTION_KEY", FERNET_KEY)

    from src.routes.academy import academy_bp
    from src.routes.api import api_bp
    from src.routes.community_takes import community_takes_bp
    from src.routes.contact import contact_bp
    from src.routes.journey import journey_bp
    from src.routes.player_suppression import player_suppression_bp
    from src.routes.players import players_bp
    from src.routes.scout import scout_bp
    from src.routes.showcase import showcase_bp
    from src.routes.teams import teams_bp

    root = Path(__file__).resolve().parent.parent
    app = Flask(__name__, template_folder=str(root / "src" / "templates"))
    app.config.update(
        TESTING=True,
        SECRET_KEY="tf2-test-secret",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        RATELIMIT_ENABLED=True,
    )
    db.init_app(app)
    limiter.init_app(app)
    app.register_blueprint(journey_bp, url_prefix="/api")
    app.register_blueprint(players_bp, url_prefix="/api")
    app.register_blueprint(scout_bp, url_prefix="/api")
    app.register_blueprint(showcase_bp, url_prefix="/api")
    app.register_blueprint(contact_bp, url_prefix="/api")
    app.register_blueprint(player_suppression_bp, url_prefix="/api")
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(community_takes_bp, url_prefix="/api")
    app.register_blueprint(academy_bp, url_prefix="/api")
    app.register_blueprint(teams_bp, url_prefix="/api")

    with app.app_context():
        limiter.reset()
        db.create_all()
        yield app
        limiter.reset()
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(suppression_app):
    return suppression_app.test_client()


@pytest.fixture
def seeded_players(suppression_app):
    """Two equivalent tracked prospects: one remains visible, one is suppressed."""

    league = League(
        league_id=39,
        name="Premier League",
        country="England",
        season=2025,
        is_european_top_league=True,
    )
    db.session.add(league)
    db.session.flush()
    parent = Team(
        team_id=33,
        name="Parent Academy",
        country="England",
        season=2025,
        league_id=league.id,
        is_active=True,
    )
    loan_club = Team(
        team_id=901,
        name="Loan Club",
        country="England",
        season=2025,
        league_id=league.id,
        is_active=True,
    )
    db.session.add_all([parent, loan_club])
    db.session.flush()

    db.session.add_all(
        [
            Player(
                player_id=VISIBLE_ID,
                name="Visible Prospect",
                nationality="England",
                age=22,
                position="Attacker",
            ),
            Player(
                player_id=SUPPRESSED_ID,
                name="Suppressed Prospect",
                nationality="England",
                age=22,
                position="Midfielder",
            ),
        ]
    )
    visible = TrackedPlayer(
        player_api_id=VISIBLE_ID,
        player_name="Visible Prospect",
        position="Attacker",
        nationality="England",
        age=22,
        team_id=parent.id,
        status="on_loan",
        current_club_api_id=loan_club.team_id,
        current_club_name=loan_club.name,
        current_club_db_id=loan_club.id,
        data_depth="full_stats",
        is_active=True,
    )
    hidden = TrackedPlayer(
        player_api_id=SUPPRESSED_ID,
        player_name="Suppressed Prospect",
        position="Midfielder",
        nationality="England",
        age=22,
        team_id=parent.id,
        status="on_loan",
        current_club_api_id=loan_club.team_id,
        current_club_name=loan_club.name,
        current_club_db_id=loan_club.id,
        data_depth="full_stats",
        is_active=True,
    )
    db.session.add_all([visible, hidden])
    db.session.flush()

    fixtures = [
        Fixture(
            fixture_id_api=991_001,
            season=2025,
            home_team_api_id=loan_club.team_id,
            away_team_api_id=902,
            date_utc=datetime(2025, 9, 3),
        ),
        Fixture(
            fixture_id_api=991_002,
            season=2025,
            home_team_api_id=loan_club.team_id,
            away_team_api_id=903,
            date_utc=datetime(2025, 9, 6),
        ),
    ]
    db.session.add_all(fixtures)
    db.session.flush()
    db.session.add_all(
        [
            FixturePlayerStats(
                fixture_id=fixtures[0].id,
                player_api_id=VISIBLE_ID,
                team_api_id=loan_club.team_id,
                position="F",
                minutes=90,
                goals=2,
                assists=1,
                rating=8.2,
                shots_total=4,
                shots_on=3,
                passes_total=30,
                passes_key=2,
                tackles_total=1,
                duels_total=6,
                duels_won=4,
            ),
            FixturePlayerStats(
                fixture_id=fixtures[1].id,
                player_api_id=VISIBLE_ID,
                team_api_id=loan_club.team_id,
                position="F",
                minutes=80,
                goals=1,
                assists=0,
                rating=7.4,
                shots_total=2,
                shots_on=1,
                passes_total=25,
                passes_key=1,
                tackles_total=0,
                duels_total=4,
                duels_won=2,
            ),
            FixturePlayerStats(
                fixture_id=fixtures[0].id,
                player_api_id=SUPPRESSED_ID,
                team_api_id=loan_club.team_id,
                position="M",
                minutes=90,
                goals=1,
                assists=2,
                rating=7.8,
                shots_total=2,
                shots_on=1,
                passes_total=70,
                passes_key=4,
                tackles_total=3,
                duels_total=8,
                duels_won=5,
            ),
        ]
    )
    for player_id, player_name, tracked_id, minutes in (
        (VISIBLE_ID, "Visible Prospect", visible.id, 900),
        (SUPPRESSED_ID, "Suppressed Prospect", hidden.id, 1_100),
    ):
        db.session.add(
            AcademyPlayerSeasonStats(
                player_api_id=player_id,
                player_name=player_name,
                league_api_id=999,
                league_name="Premier League 2",
                season=2025,
                appearances=12,
                minutes=minutes,
                goals=4,
                assists=3,
                tracked_player_id=tracked_id,
            )
        )
    db.session.add_all(
        [
            PlayerShowcaseProfile(
                player_api_id=VISIBLE_ID,
                bio="Visible biography",
                status="approved",
            ),
            PlayerShowcaseProfile(
                player_api_id=SUPPRESSED_ID,
                bio="Suppressed private biography",
                status="approved",
            ),
            PlayerShadow(
                player_api_id=SUPPRESSED_ID,
                player_name="Suppressed Prospect",
                position="Midfielder",
                current_club_name="Loan Club",
                is_active=True,
            ),
            CommunityTake(
                source_type="editor",
                source_author="Editor",
                content="Visible editorial note",
                player_id=VISIBLE_ID,
                player_name="Visible Prospect",
                status="approved",
            ),
            CommunityTake(
                source_type="editor",
                source_author="Editor",
                content="Suppressed editorial note",
                player_id=SUPPRESSED_ID,
                player_name="Suppressed Prospect",
                status="approved",
            ),
        ]
    )
    db.session.commit()
    return {"parent": parent, "loan_club": loan_club, "visible": visible, "hidden": hidden}


def _user_headers(email: str):
    user = UserAccount.query.filter_by(email=email).first()
    if user is None:
        user = _ensure_user_account(email)
        db.session.commit()
    token = issue_user_token(email)["token"]
    return user, {"Authorization": f"Bearer {token}"}


def _admin_headers():
    token = issue_user_token("tf2-admin@example.com", role="admin")["token"]
    return {"Authorization": f"Bearer {token}", "X-API-Key": ADMIN_KEY}


def _verified_scout(email: str):
    user, headers = _user_headers(email)
    db.session.add(
        ScoutVerification(
            user_account_id=user.id,
            full_name="Alex Scout",
            organization="Fixture Recruitment",
            role_title="Scout",
            statement="I recruit adult academy players.",
            evidence_urls=["https://example.com/scout"],
            status="approved",
            reviewed_at=utcnow(),
        )
    )
    db.session.commit()
    return user, headers


def _approved_player_claim(email: str, player_api_id: int):
    user, headers = _user_headers(email)
    claim = PlayerProfileClaim(
        user_account_id=user.id,
        player_api_id=player_api_id,
        relationship_type="player",
        contract_status="free_agent",
        status="approved",
        reviewed_at=utcnow(),
    )
    db.session.add(claim)
    db.session.commit()
    return user, headers, claim


def _add_suppression(player_api_id: int, *, status: str = "active") -> PlayerSuppression:
    now = datetime.now(UTC)
    row = PlayerSuppression(
        player_api_id=player_api_id,
        reason_code="guardian_request",
        requester_role="guardian",
        requester_contact="guardian@example.com",
        request_statement="Please remove this player.",
        status=status,
        decided_at=now if status != "requested" else None,
        decided_by="tf2-admin@example.com" if status != "requested" else None,
    )
    db.session.add(row)
    db.session.commit()
    return row


def _intake_payload(*, contact="Guardian@Example.com", statement=None):
    return {
        "requester_role": "guardian",
        "contact_email": contact,
        "statement": statement or "<b>Please remove this profile</b><script>alert(1)</script>",
    }


def test_public_intake_is_neutral_sanitized_encrypted_and_not_contact_gated(client, seeded_players, monkeypatch):
    monkeypatch.setenv("CONTACT_RAIL_ENABLED", "false")
    known = client.post(
        f"/api/players/{SUPPRESSED_ID}/takedown-request",
        json=_intake_payload(),
        environ_overrides={"REMOTE_ADDR": "198.51.100.10"},
    )
    unknown = client.post(
        f"/api/players/{UNKNOWN_ID}/takedown-request",
        json=_intake_payload(),
        environ_overrides={"REMOTE_ADDR": "198.51.100.11"},
    )

    assert known.status_code == unknown.status_code == 202
    assert (
        known.get_json()
        == unknown.get_json()
        == {"message": "Your takedown request has been received and will be reviewed."}
    )
    known_row = PlayerSuppression.query.filter_by(player_api_id=SUPPRESSED_ID).one()
    assert known_row.status == "requested"
    assert known_row.reason_code == "guardian_request"
    assert known_row.requester_contact == "guardian@example.com"
    assert "<" not in known_row.request_statement

    raw = db.session.execute(
        sa.text("SELECT requester_contact, request_statement FROM player_suppressions WHERE id = :suppression_id"),
        {"suppression_id": known_row.id},
    ).one()
    assert raw.requester_contact.startswith("fernet:v1:")
    assert raw.request_statement.startswith("fernet:v1:")
    assert "guardian@example.com" not in raw.requester_contact
    assert "Please remove" not in raw.request_statement

    attached = client.post(
        f"/api/players/{SUPPRESSED_ID}/takedown-request",
        json=_intake_payload(contact="new@example.com", statement="Updated request"),
        environ_overrides={"REMOTE_ADDR": "198.51.100.12"},
    )
    assert attached.status_code == 202
    assert PlayerSuppression.query.filter_by(player_api_id=SUPPRESSED_ID).count() == 1
    db.session.refresh(known_row)
    assert known_row.requester_contact == "new@example.com"
    assert known_row.request_statement == "Updated request"

    known_row.status = "active"
    db.session.commit()
    duplicate_active = client.post(
        f"/api/players/{SUPPRESSED_ID}/takedown-request",
        json=_intake_payload(contact="attacker@example.com", statement="Replace the evidence"),
        environ_overrides={"REMOTE_ADDR": "198.51.100.13"},
    )
    assert duplicate_active.status_code == 202
    db.session.refresh(known_row)
    assert known_row.requester_contact == "new@example.com"
    assert known_row.request_statement == "Updated request"


def test_public_intake_rate_limit_keys_on_remote_addr_not_spoofed_xff(client):
    from src.routes.player_suppression import INTAKE_RATE_LIMIT_PER_MINUTE

    per_minute = int(re.match(r"\d+", INTAKE_RATE_LIMIT_PER_MINUTE).group())
    remote_addr = "203.0.113.40"
    for index in range(per_minute):
        response = client.post(
            f"/api/players/{800_000 + index}/takedown-request",
            json=_intake_payload(contact=f"guardian{index}@example.com"),
            headers={"X-Forwarded-For": f"192.0.2.{index + 1}"},
            environ_overrides={"REMOTE_ADDR": remote_addr},
        )
        assert response.status_code == 202

    blocked = client.post(
        "/api/players/899999/takedown-request",
        json=_intake_payload(contact="blocked@example.com"),
        headers={"X-Forwarded-For": "192.0.2.250"},
        environ_overrides={"REMOTE_ADDR": remote_addr},
    )
    assert blocked.status_code == 429

    independent_ip = client.post(
        "/api/players/899998/takedown-request",
        json=_intake_payload(contact="other@example.com"),
        headers={"X-Forwarded-For": "192.0.2.250"},
        environ_overrides={"REMOTE_ADDR": "203.0.113.41"},
    )
    assert independent_ip.status_code == 202


def test_admin_queue_activate_reject_lift_and_shadow_lifecycle(client, seeded_players):
    intake = client.post(
        f"/api/players/{SUPPRESSED_ID}/takedown-request",
        json=_intake_payload(),
        environ_overrides={"REMOTE_ADDR": "198.51.100.20"},
    )
    assert intake.status_code == 202
    suppression = PlayerSuppression.query.filter_by(player_api_id=SUPPRESSED_ID).one()

    assert client.get("/api/admin/suppressions").status_code == 401
    queue = client.get("/api/admin/suppressions?status=requested", headers=_admin_headers())
    assert queue.status_code == 200
    assert queue.get_json()["total"] == 1
    assert queue.get_json()["suppressions"][0]["requester_contact"] == "guardian@example.com"

    missing_notes = client.post(
        f"/api/admin/suppressions/{suppression.id}/activate",
        json={},
        headers=_admin_headers(),
    )
    assert missing_notes.status_code == 400

    activated = client.post(
        f"/api/admin/suppressions/{suppression.id}/activate",
        json={"notes": "<b>Guardian evidence confirmed</b>"},
        headers=_admin_headers(),
    )
    assert activated.status_code == 200
    assert activated.get_json()["suppression"]["status"] == "active"
    assert "<" not in activated.get_json()["suppression"]["notes"]
    db.session.expire_all()
    suppression = db.session.get(PlayerSuppression, suppression.id)
    assert suppression.decided_at is not None
    assert suppression.decided_by == "tf2-admin@example.com"
    assert PlayerShadow.query.filter_by(player_api_id=SUPPRESSED_ID).one().is_active is False
    assert client.get(f"/api/players/{SUPPRESSED_ID}/profile").get_json() == NEUTRAL_NOT_FOUND

    raw_notes = db.session.execute(
        sa.text("SELECT notes FROM player_suppressions WHERE id = :suppression_id"),
        {"suppression_id": suppression.id},
    ).scalar_one()
    assert raw_notes.startswith("fernet:v1:")
    assert "Guardian evidence" not in raw_notes
    assert (
        client.post(
            f"/api/admin/suppressions/{suppression.id}/reject",
            json={"notes": "Wrong transition"},
            headers=_admin_headers(),
        ).status_code
        == 409
    )

    lifted = client.post(
        f"/api/admin/suppressions/{suppression.id}/lift",
        json={"notes": "Identity confirmed; restore publication"},
        headers=_admin_headers(),
    )
    assert lifted.status_code == 200
    assert lifted.get_json()["suppression"]["status"] == "lifted"
    db.session.expire_all()
    assert PlayerShadow.query.filter_by(player_api_id=SUPPRESSED_ID).one().is_active is True
    assert client.get(f"/api/players/{SUPPRESSED_ID}/profile").status_code == 200

    rejected_id = UNKNOWN_ID - 1
    assert (
        client.post(
            f"/api/players/{rejected_id}/takedown-request",
            json=_intake_payload(contact="reject@example.com"),
            environ_overrides={"REMOTE_ADDR": "198.51.100.21"},
        ).status_code
        == 202
    )
    rejected = PlayerSuppression.query.filter_by(player_api_id=rejected_id).one()
    decision = client.post(
        f"/api/admin/suppressions/{rejected.id}/reject",
        json={"notes": "Request could not be verified"},
        headers=_admin_headers(),
    )
    assert decision.status_code == 200
    rejected_queue = client.get("/api/admin/suppressions?status=rejected", headers=_admin_headers())
    assert [row["id"] for row in rejected_queue.get_json()["suppressions"]] == [rejected.id]


def test_scout_queries_exclude_suppressed_players_at_sql_level(client, suppression_app, seeded_players, monkeypatch):
    _add_suppression(SUPPRESSED_ID)

    from src.routes.scout import _base_scout_query

    with suppression_app.test_request_context("/api/scout/players"):
        query, _ = _base_scout_query()
        sql = str(query.statement.compile(compile_kwargs={"literal_binds": True})).lower()
    assert "player_suppressions" in sql
    assert "not (exists" in sql or "not exists" in sql

    browse = client.get("/api/scout/players?sort=name")
    assert browse.status_code == 200
    assert [row["player_id"] for row in browse.get_json()["players"]] == [VISIBLE_ID]
    assert browse.get_json()["players"][0]["goals"] == 3
    assert client.get("/api/scout/players?search=Suppressed").get_json()["total"] == 0

    leaderboards = client.get("/api/scout/leaderboards?limit=10")
    assert leaderboards.status_code == 200
    board_ids = {row["player_id"] for board in leaderboards.get_json()["leaderboards"].values() for row in board}
    assert SUPPRESSED_ID not in board_ids
    assert VISIBLE_ID in board_ids

    statements = []

    def capture_statement(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement.lower())

    event.listen(db.engine, "before_cursor_execute", capture_statement)
    try:
        compared = client.get(f"/api/scout/compare?ids={VISIBLE_ID},{SUPPRESSED_ID}")
    finally:
        event.remove(db.engine, "before_cursor_execute", capture_statement)
    assert compared.status_code == 200
    assert [row["profile"]["player_id"] for row in compared.get_json()["players"]] == [VISIBLE_ID]
    assert compared.get_json()["missing_ids"] == [SUPPRESSED_ID]
    assert any(
        "tracked_players" in statement and "player_suppressions" in statement and "exists" in statement
        for statement in statements
    )

    class SearchClient:
        def search_player_profiles_global(self, _query):
            return [
                {"player": {"id": VISIBLE_ID, "name": "Visible Prospect"}, "statistics": []},
                {
                    "player": {"id": SUPPRESSED_ID, "name": "Suppressed Prospect"},
                    "statistics": [],
                },
            ]

    _, headers = _user_headers("search-scout@example.com")
    monkeypatch.setattr("src.routes.scout._get_api_client", lambda: SearchClient())
    searched = client.get("/api/scout/player-search?q=Prospect", headers=headers)
    assert searched.status_code == 200
    assert [row["player_api_id"] for row in searched.get_json()["players"]] == [VISIBLE_ID]
    assert "Suppressed Prospect" not in searched.get_data(as_text=True)


def test_public_player_showcase_and_new_claim_are_neutral_then_restore_on_lift(client, seeded_players):
    suppression = _add_suppression(SUPPRESSED_ID)
    for path in (
        f"/api/players/{SUPPRESSED_ID}/stats",
        f"/api/players/{SUPPRESSED_ID}/profile",
        f"/api/players/{SUPPRESSED_ID}/season-stats",
        f"/api/players/{SUPPRESSED_ID}/availability",
        f"/api/players/{SUPPRESSED_ID}/commentaries",
        f"/api/players/{SUPPRESSED_ID}/showcase",
        f"/api/players/{SUPPRESSED_ID}/comments",
        f"/api/players/{SUPPRESSED_ID}/links",
        f"/api/players/{SUPPRESSED_ID}/journey",
        f"/api/players/{SUPPRESSED_ID}/journey/map",
        f"/api/players/{SUPPRESSED_ID}/academy-stats",
        f"/api/loans/{seeded_players['hidden'].id}/journey",
    ):
        response = client.get(path)
        assert response.status_code == 404, path
        assert response.get_json() == NEUTRAL_NOT_FOUND, path
        assert "Suppressed Prospect" not in response.get_data(as_text=True)

    assert client.get(f"/api/players/{VISIBLE_ID}/profile").status_code == 200
    assert client.get(f"/api/players/{VISIBLE_ID}/showcase").status_code == 200
    assert client.get("/api/players/search?q=Suppressed").get_json() == []

    team_id = seeded_players["parent"].id
    team_players = client.get(f"/api/teams/{team_id}/players").get_json()
    team_loans = client.get(f"/api/teams/{team_id}/loans").get_json()
    team_detail = client.get(f"/api/teams/{team_id}").get_json()
    assert [row["player_id"] for row in team_players["players"]] == [VISIBLE_ID]
    assert [row["player_id"] for row in team_loans] == [VISIBLE_ID]
    assert [row["player_api_id"] for row in team_detail["active_loans"]] == [VISIBLE_ID]
    takes = client.get("/api/community-takes").get_json()["takes"]
    assert [row["player_id"] for row in takes] == [VISIBLE_ID]
    _, headers = _user_headers("guardian-claim@example.com")
    blocked_claim = client.post(
        f"/api/players/{SUPPRESSED_ID}/claim",
        json={"relationship_type": "guardian", "message": "Guardian claim"},
        headers=headers,
    )
    assert blocked_claim.status_code == 404
    assert blocked_claim.get_json() == NEUTRAL_NOT_FOUND
    assert PlayerProfileClaim.query.filter_by(player_api_id=SUPPRESSED_ID).count() == 0

    suppression.status = "lifted"
    db.session.commit()
    restored_profile = client.get(f"/api/players/{SUPPRESSED_ID}/profile")
    restored_showcase = client.get(f"/api/players/{SUPPRESSED_ID}/showcase")
    assert restored_profile.status_code == restored_showcase.status_code == 200
    assert restored_profile.get_json()["name"] == "Suppressed Prospect"
    assert restored_showcase.get_json()["profile"]["bio"] == "Suppressed private biography"
    restored_claim = client.post(
        f"/api/players/{SUPPRESSED_ID}/claim",
        json={"relationship_type": "guardian", "message": "Guardian claim"},
        headers=headers,
    )
    assert restored_claim.status_code == 201


def test_watchlist_and_follow_lists_render_inert_removable_entries_and_restore(client, seeded_players):
    user, headers = _user_headers("list-owner@example.com")
    follow_list = FollowList(
        user_account_id=user.id,
        name="Private prospects",
        is_default=False,
        is_active=True,
    )
    db.session.add(follow_list)
    db.session.flush()
    follow = Follow(
        list_id=follow_list.id,
        kind="player",
        selector={"player_api_id": SUPPRESSED_ID},
        label="Suppressed Prospect",
        note="Review later",
    )
    db.session.add_all(
        [
            follow,
            ScoutWatchlistEntry(
                user_account_id=user.id,
                player_api_id=SUPPRESSED_ID,
                note="Review later",
            ),
        ]
    )
    db.session.commit()
    follow_id = follow.id
    list_id = follow_list.id
    suppression = _add_suppression(SUPPRESSED_ID)

    watchlist = client.get("/api/scout/watchlist", headers=headers)
    assert watchlist.status_code == 200
    watch_entry = watchlist.get_json()["entries"][0]
    assert watch_entry["unavailable"] is True
    assert watch_entry["player"] is None
    assert "Suppressed Prospect" not in watchlist.get_data(as_text=True)

    lists = client.get("/api/scout/lists", headers=headers)
    assert lists.status_code == 200
    inert_follow = lists.get_json()["lists"][0]["follows"][0]
    assert inert_follow["unavailable"] is True
    assert inert_follow["label"] == "Unavailable"
    assert "Suppressed Prospect" not in lists.get_data(as_text=True)

    existing_add = client.post(
        "/api/scout/watchlist",
        json={"player_api_id": SUPPRESSED_ID},
        headers=headers,
    )
    assert existing_add.status_code == 200
    assert existing_add.get_json()["entry"]["unavailable"] is True
    assert (
        client.post(
            f"/api/scout/lists/{list_id}/follows",
            json={"kind": "player", "selector": {"player_api_id": SUPPRESSED_ID}},
            headers=headers,
        ).status_code
        == 404
    )

    suppression.status = "lifted"
    db.session.commit()
    restored_watch = client.get("/api/scout/watchlist", headers=headers).get_json()["entries"][0]
    restored_follow = client.get("/api/scout/lists", headers=headers).get_json()["lists"][0]["follows"][0]
    assert restored_watch.get("unavailable", False) is False
    assert restored_watch["player"]["player_name"] == "Suppressed Prospect"
    assert restored_follow.get("unavailable", False) is False
    assert restored_follow["label"] == "Suppressed Prospect"

    suppression.status = "active"
    db.session.commit()
    removed_watch = client.delete(f"/api/scout/watchlist/{SUPPRESSED_ID}", headers=headers)
    removed_follow = client.delete(
        f"/api/scout/lists/{list_id}/follows/{follow_id}",
        headers=headers,
    )
    assert removed_watch.get_json() == {"removed": True}
    assert removed_follow.get_json() == {"removed": True}
    assert ScoutWatchlistEntry.query.count() == Follow.query.count() == 0


def test_shadow_remint_is_blocked_before_upstream_call_and_lift_restores(suppression_app):
    from src.services.player_shadow_service import mint_shadow

    suppression = _add_suppression(SHADOW_ONLY_ID)

    class CountingClient:
        calls = 0

        def get_player_profile(self, player_api_id):
            self.calls += 1
            return {"player": {"id": player_api_id, "name": "Worldwide Prospect"}}

    api_client = CountingClient()
    with pytest.raises(PlayerSuppressedError):
        mint_shadow(SHADOW_ONLY_ID, api_client=api_client)
    assert api_client.calls == 0
    assert PlayerShadow.query.filter_by(player_api_id=SHADOW_ONLY_ID).first() is None

    suppression.status = "lifted"
    db.session.commit()
    shadow = mint_shadow(SHADOW_ONLY_ID, api_client=api_client)
    db.session.commit()
    assert api_client.calls == 1
    assert shadow.player_name == "Worldwide Prospect"
    assert shadow.is_active is True


def test_weekly_builders_scout_digest_pulse_and_cards_exclude_suppressed_players(
    suppression_app, seeded_players, monkeypatch
):
    _add_suppression(SUPPRESSED_ID)
    visible = seeded_players["visible"]
    hidden = seeded_players["hidden"]
    parent = seeded_players["parent"]

    visible.status = hidden.status = "academy"
    db.session.commit()
    weekly = _academy_watch_for_team(parent.id, db.session)
    assert [row["player_api_id"] for row in weekly["academy_watch"]] == [VISIBLE_ID]
    assert "Suppressed Prospect" not in json.dumps(weekly)

    # Primary weekly composer path (the legacy APIFootballClient path below is
    # still live for older jobs). Keep it offline and assert the report query,
    # not a later Python filter, owns the suppression boundary.
    from src.agents import weekly_newsletter_agent as modern_weekly

    monkeypatch.setattr(modern_weekly.api_client, "set_season_year", lambda _season: None)
    monkeypatch.setattr(modern_weekly.api_client, "_prime_team_cache", lambda _season: None)
    monkeypatch.setattr(modern_weekly, "_detect_recent_loan_returns", lambda **_kwargs: [])
    monkeypatch.setattr("src.services.transfer_heal_service.refresh_and_heal", lambda **_kwargs: {})
    monkeypatch.setattr("src.utils.academy_classifier.is_academy_product", lambda *_args, **_kwargs: True)
    modern = modern_weekly.fetch_pipeline_report_tool(
        parent.id,
        2025,
        date(2025, 9, 2),
        WINDOW_END,
    )
    assert [row["player_api_id"] for row in modern["groups"]["academy"]] == [VISIBLE_ID]
    assert "Suppressed Prospect" not in json.dumps(modern)

    visible.status = hidden.status = "on_loan"
    visible.data_depth = hidden.data_depth = "profile_only"
    db.session.commit()
    legacy_client = APIFootballClient.__new__(APIFootballClient)
    monkeypatch.setattr(APIFootballClient, "get_team_name", lambda self, *_args, **_kwargs: "Parent Academy")
    legacy = legacy_client.summarize_parent_loans_week(
        parent_team_db_id=parent.id,
        parent_team_api_id=parent.team_id,
        season=2025,
        week_start=date(2025, 9, 2),
        week_end=WINDOW_END,
        db_session=db.session,
    )
    assert [row["player_api_id"] for row in legacy["loanees"]] == [VISIBLE_ID]
    assert "Suppressed Prospect" not in json.dumps(legacy)

    user, _ = _user_headers("digest-owner@example.com")
    entries = [
        ScoutWatchlistEntry(user_account_id=user.id, player_api_id=VISIBLE_ID),
        ScoutWatchlistEntry(user_account_id=user.id, player_api_id=SUPPRESSED_ID),
    ]
    db.session.add_all(entries)
    db.session.commit()
    from src.services.scout_digest_service import build_user_digest

    digest = build_user_digest(user, entries, api_client=None)
    assert digest is not None
    assert digest["players"] == 1
    assert "Visible Prospect" in digest["text"]
    assert "Suppressed Prospect" not in digest["text"]
    assert "Suppressed Prospect" not in digest["html"]

    from src.services import player_card_service as cards
    from src.services import player_pulse_service as pulse

    pulse_result = pulse.compute_pulse(WINDOW_END, player_api_ids=[VISIBLE_ID, SUPPRESSED_ID])
    assert pulse_result["players_considered"] == 1
    assert [row.player_api_id for row in PlayerPulse.query.order_by(PlayerPulse.player_api_id)] == [VISIBLE_ID]

    db.session.add(
        PlayerPulse(
            player_api_id=SUPPRESSED_ID,
            window_end=WINDOW_END,
            score=99.0,
            delta_json={
                "window_start": "2025-09-02",
                "window_end": WINDOW_END.isoformat(),
                "signals": {},
                "window_totals": {},
                "context": {"name": "Suppressed Prospect"},
                "score": 99.0,
            },
        )
    )
    db.session.commit()
    llm_calls = []

    def fake_card(payload, _model):
        llm_calls.append(payload)
        return "Verified visible-player update."

    monkeypatch.setattr(cards, "_generate_card_text", fake_card)
    generated = cards.generate_cards(WINDOW_END, threshold=0, limit=10)
    assert generated["generated"] == 1
    assert generated["candidates"] == [
        {
            "player_api_id": VISIBLE_ID,
            "score": PlayerPulse.query.filter_by(player_api_id=VISIBLE_ID, window_end=WINDOW_END).one().score,
        }
    ]
    assert len(llm_calls) == 1
    assert {row.player_api_id for row in PlayerCardCache.query.all()} == {VISIBLE_ID}

    db.session.add(
        PlayerCardCache(
            player_api_id=SUPPRESSED_ID,
            window_end=WINDOW_END,
            card_html="<p>Suppressed private card</p>",
            card_text="Suppressed private card",
            model="fixture",
        )
    )
    db.session.commit()
    assert set(cards.get_cards_for_window(WINDOW_END)) == {VISIBLE_ID}


def test_contact_creation_is_blocked_but_existing_participant_thread_remains_available(client, seeded_players):
    _, first_scout_headers = _verified_scout("first-scout@example.com")
    _, owner_headers, _ = _approved_player_claim("player-owner@example.com", SUPPRESSED_ID)
    created = client.post(
        "/api/contact/requests",
        json={"player_api_id": SUPPRESSED_ID, "message": "Can we arrange a call?"},
        headers=first_scout_headers,
    )
    assert created.status_code == 201, created.get_json()
    request_id = created.get_json()["contact_request"]["id"]

    _add_suppression(SUPPRESSED_ID)
    _, second_scout_headers = _verified_scout("second-scout@example.com")
    blocked = client.post(
        "/api/contact/requests",
        json={"player_api_id": SUPPRESSED_ID, "message": "A new approach"},
        headers=second_scout_headers,
    )
    assert blocked.status_code == 403
    assert blocked.get_json() == {
        "error": "Player is not available for contact",
        "code": "player_not_claimable",
    }
    assert "Suppressed Prospect" not in blocked.get_data(as_text=True)
    assert ContactRequest.query.count() == 1

    accepted = client.post(f"/api/contact/requests/{request_id}/accept", headers=owner_headers)
    assert accepted.status_code == 200
    sent = client.post(
        f"/api/contact/requests/{request_id}/messages",
        json={"body": "The existing thread still works."},
        headers=first_scout_headers,
    )
    assert sent.status_code == 201
    thread = client.get(f"/api/contact/requests/{request_id}/messages", headers=owner_headers)
    assert thread.status_code == 200
    assert thread.get_json()["total"] == 1
    inbox = client.get("/api/contact/requests?box=inbox", headers=owner_headers)
    assert inbox.status_code == 200
    assert inbox.get_json()["total"] == 1


def test_tf02_migration_is_guarded_rls_enabled_and_single_head():
    repo_root = Path(__file__).resolve().parent.parent
    migration_path = repo_root / "migrations" / "versions" / "tf02_player_suppressions.py"
    source = migration_path.read_text()
    assert 'revision = "tf02"' in source
    assert 'down_revision = "tf01"' in source
    assert "PR #636" in source
    assert "table_exists(TABLE)" in source
    assert "create_index_safe(" in source
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "downgrade refused: player suppression history exists" in source

    cfg = Config(str(repo_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(repo_root / "migrations"))
    assert ScriptDirectory.from_config(cfg).get_heads() == ["tf02"]
