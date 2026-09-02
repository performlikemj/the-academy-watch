"""Adversarial coverage for the verified club-manager console (C2)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from flask import Flask
from src.auth import issue_user_token, media_token_claims
from src.extensions import limiter
from src.models.follow import PlayerShadow
from src.models.funding import (
    ClubProgram,
    ClubProgramClaim,
    ClubProgramManager,
    ClubRosterMember,
    FundingLeague,
)
from src.models.league import League, Team, UserAccount, db
from src.models.player_match_entry import PlayerMatchEntry
from src.models.player_suppression import PlayerSuppression
from src.models.season_rollup import PlayerSeasonCell, PlayerSeasonTotal
from src.models.showcase import LocalPlayer, PlayerProfileClaim
from src.models.tracked_player import TrackedPlayer
from src.models.video import VideoAnalysisJob, VideoMatch, VideoPlayerReport, VideoRosterEntry, VideoTracklet
from src.models.weekly import Fixture, FixturePlayerStats
from src.routes import club as club_routes
from src.routes.club import club_bp
from src.routes.player_matches import player_matches_bp
from src.routes.player_suppression import player_suppression_bp
from src.routes.showcase import showcase_bp
from src.routes.video import video_bp
from src.services import season_rollup_service, video_storage
from src.services.contact import routing_mode_for_claim

ADMIN_KEY = "club-console-admin-key"
FERNET_KEY = "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="


@pytest.fixture
def club_app(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", ADMIN_KEY)
    monkeypatch.setenv("ADMIN_IP_WHITELIST", "")
    monkeypatch.setenv("PLAYER_SUPPRESSION_ENCRYPTION_KEY", FERNET_KEY)
    monkeypatch.setenv("CLUB_MATCH_QUOTA_DEFAULT", "3")
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SECRET_KEY="club-console-fixture-secret",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        RATELIMIT_ENABLED=False,
    )
    db.init_app(app)
    limiter.init_app(app)
    app.register_blueprint(showcase_bp, url_prefix="/api")
    app.register_blueprint(player_suppression_bp, url_prefix="/api")
    app.register_blueprint(player_matches_bp, url_prefix="/api")
    app.register_blueprint(club_bp, url_prefix="/api")
    app.register_blueprint(video_bp, url_prefix="/api")

    with app.app_context():
        db.create_all()
        league = League(league_id=9910, name="C2 League", country="Japan", season=2026)
        team = Team(team_id=9911, name="C2 Academy", country="Japan", season=2026, league=league)
        funding_league = FundingLeague(
            name="C2 Funding League",
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
        db.session.add_all([league, team, funding_league])
        db.session.flush()
        program_a = ClubProgram(
            funding_league_id=funding_league.id,
            name="Club A",
            legal_name="Club A Association",
            slug="club-a-c2",
            country="Japan",
            region="Kanto",
            platform_status="approved",
        )
        program_b = ClubProgram(
            funding_league_id=funding_league.id,
            name="Club B",
            legal_name="Club B Association",
            slug="club-b-c2",
            country="Japan",
            region="Kansai",
            platform_status="approved",
        )
        db.session.add_all([program_a, program_b])
        db.session.flush()

        users = {}
        for key in ("a", "b", "pending", "revoked", "removed", "scout"):
            user = UserAccount(
                email=f"manager-{key}@c2.example",
                display_name=f"Manager {key}",
                display_name_lower=f"manager {key}",
            )
            db.session.add(user)
            users[key] = user
        db.session.flush()

        def claim_and_manager(user, program, *, manager_status="active"):
            claim = ClubProgramClaim(
                program_id=program.id,
                user_account_id=user.id,
                relationship_type="club_official",
                status="approved",
            )
            db.session.add(claim)
            db.session.flush()
            db.session.add(
                ClubProgramManager(
                    program_id=program.id,
                    user_account_id=user.id,
                    source_claim_id=claim.id,
                    status=manager_status,
                    granted_by="c2-fixture",
                )
            )

        claim_and_manager(users["a"], program_a)
        claim_and_manager(users["b"], program_b)
        claim_and_manager(users["revoked"], program_a, manager_status="revoked")
        db.session.add(
            ClubProgramClaim(
                program_id=program_a.id,
                user_account_id=users["pending"].id,
                relationship_type="club_official",
                status="pending",
            )
        )
        tracked = TrackedPlayer(
            player_api_id=7001,
            player_name="Known Academy Player",
            birth_date="2005-04-03",
            position="Midfielder",
            team_id=team.id,
            status="academy",
            is_active=True,
        )
        tracked_two = TrackedPlayer(
            player_api_id=7002,
            player_name="Second Academy Player",
            birth_date="2004-02-01",
            position="Defender",
            team_id=team.id,
            status="academy",
            is_active=True,
        )
        db.session.add_all([tracked, tracked_two])
        db.session.commit()
        app.c2 = {
            "program_a": program_a.id,
            "program_b": program_b.id,
            "team": team.id,
            "users": {key: user.id for key, user in users.items()},
        }
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(club_app):
    return club_app.test_client()


def _headers(key: str) -> dict:
    email = f"manager-{key}@c2.example"
    return {"Authorization": f"Bearer {issue_user_token(email)['token']}"}


def _grant_program_manager(program_id: int, user_id: int) -> None:
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
            granted_by="club-console-test",
        )
    )
    db.session.commit()


def _admin_headers() -> dict:
    return {
        "Authorization": f"Bearer {issue_user_token('c2-admin@example.com', role='admin')['token']}",
        "X-API-Key": ADMIN_KEY,
    }


def _local(user_id: int, *, name="Club Local Player", birth_year=2009, status="pending") -> LocalPlayer:
    row = LocalPlayer(
        display_name=name,
        birth_year=birth_year,
        position="Forward",
        country="Japan",
        status=status,
        provenance="user",
        created_by_user_id=user_id,
    )
    db.session.add(row)
    db.session.commit()
    return row


def _add_api_member(client, program_id: int, player_api_id=7001, key="a") -> int:
    response = client.post(
        f"/api/club/{program_id}/roster",
        json={"player_api_id": player_api_id},
        headers=_headers(key),
    )
    assert response.status_code == 201, response.get_json()
    return response.get_json()["member"]["id"]


def _add_local_member(client, program_id: int, local_player_id: int, key="a") -> int:
    response = client.post(
        f"/api/club/{program_id}/roster",
        json={"local_player_id": local_player_id},
        headers=_headers(key),
    )
    assert response.status_code == 201, response.get_json()
    return response.get_json()["member"]["id"]


def _match(program_id: int, *, status="uploaded", kickoff_s=0) -> VideoMatch:
    row = VideoMatch(
        club_program_id=program_id,
        status=status,
        kickoff_s=kickoff_s,
        blob_path=f"matches/test-{program_id}.mp4",
        blob_etag="etag-c2",
    )
    db.session.add(row)
    db.session.commit()
    return row


def _result_payload(member_ids: list[int], **overrides) -> dict:
    payload = {
        "video_match_id": None,
        "match_date": "2025-09-01",
        "opponent": "Rivals FC",
        "competition": "County League",
        "home_away": "home",
        "result_for": 2,
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
                "note": "Full match",
            }
            for member_id in member_ids
        ],
    }
    payload.update(overrides)
    return payload


def _active_suppression(*, player_api_id=None, local_player_id=None) -> PlayerSuppression:
    row = PlayerSuppression(
        player_api_id=player_api_id,
        local_player_id=local_player_id,
        reason_code="player_request",
        requester_role="player",
        requester_contact="privacy@c2.example",
        request_statement="Please remove this identity.",
        status="active",
    )
    db.session.add(row)
    db.session.commit()
    return row


def test_require_club_manager_denies_cross_program_pending_revoked_and_removed(club_app, client):
    a = club_app.c2["program_a"]
    b = club_app.c2["program_b"]
    assert client.get(f"/api/club/{a}/roster", headers=_headers("a")).status_code == 200
    assert client.get(f"/api/club/{b}/roster", headers=_headers("a")).status_code == 403
    for key in ("pending", "revoked", "removed"):
        response = client.get(f"/api/club/{a}/roster", headers=_headers(key))
        assert response.status_code == 403
        assert response.get_json() == {"error": "Club manager access denied"}


def test_require_club_manager_denies_active_manager_when_program_or_claim_not_approved(club_app, client):
    program_id = club_app.c2["program_a"]
    program = db.session.get(ClubProgram, program_id)
    program.platform_status = "suspended"
    db.session.commit()

    suspended = client.get(f"/api/club/{program_id}/roster", headers=_headers("a"))
    assert suspended.status_code == 403
    assert suspended.get_json() == {"error": "Club manager access denied"}

    program.platform_status = "approved"
    claim = ClubProgramClaim.query.filter_by(
        program_id=program_id,
        user_account_id=club_app.c2["users"]["a"],
    ).one()
    claim.status = "revoked"
    db.session.commit()

    revoked_claim = client.get(f"/api/club/{program_id}/roster", headers=_headers("a"))
    assert revoked_claim.status_code == 403
    assert revoked_claim.get_json() == {"error": "Club manager access denied"}


def test_require_club_manager_honors_emergency_hidden_kill_switch(club_app, client):
    program_id = club_app.c2["program_a"]
    program = db.session.get(ClubProgram, program_id)
    program.emergency_hidden = True
    db.session.commit()

    hidden = client.get(f"/api/club/{program_id}/roster", headers=_headers("a"))
    assert hidden.status_code == 403
    assert hidden.get_json() == {"error": "Club manager access denied"}

    program.emergency_hidden = False
    db.session.commit()
    assert client.get(f"/api/club/{program_id}/roster", headers=_headers("a")).status_code == 200


def test_every_club_console_route_is_manager_gated_before_resource_access(club_app, client):
    b = club_app.c2["program_b"]
    member = _add_api_member(client, b, 7002, "b")
    match = _match(b, status="finalized")
    attacks = (
        ("GET", f"/api/club/{b}/roster", None),
        ("GET", f"/api/club/{b}/matches", None),
        ("GET", f"/api/club/{b}/results", None),
        ("POST", f"/api/club/{b}/roster", {"player_api_id": 7001}),
        ("DELETE", f"/api/club/{b}/roster/{member}", None),
        ("POST", f"/api/club/{b}/matches", {}),
        ("POST", f"/api/club/{b}/results", {}),
        ("POST", f"/api/club/{b}/matches/{match.id}/sas", None),
        ("POST", f"/api/club/{b}/matches/{match.id}/upload-complete", {}),
        ("PATCH", f"/api/club/{b}/matches/{match.id}", {"competition": "IDOR"}),
        ("GET", f"/api/club/{b}/matches/{match.id}", None),
        ("PUT", f"/api/club/{b}/matches/{match.id}/roster", {"entries": []}),
        ("POST", f"/api/club/{b}/matches/{match.id}/process", None),
        ("GET", f"/api/club/{b}/matches/{match.id}/report", None),
    )
    for method, path, body in attacks:
        response = client.open(path, method=method, json=body, headers=_headers("a"))
        assert response.status_code == 403, (method, path, response.get_json())
        assert response.get_json() == {"error": "Club manager access denied"}
    assert client.get(f"/api/club/{b}/roster").status_code == 401


def test_active_manager_cannot_address_foreign_child_ids_through_own_program(club_app, client):
    a = club_app.c2["program_a"]
    b = club_app.c2["program_b"]
    foreign_member = _add_api_member(client, b, 7002, "b")
    foreign_match = _match(b, status="finalized")
    attacks = (
        ("DELETE", f"/api/club/{a}/roster/{foreign_member}", None),
        ("POST", f"/api/club/{a}/matches/{foreign_match.id}/sas", None),
        ("POST", f"/api/club/{a}/matches/{foreign_match.id}/upload-complete", {}),
        ("PATCH", f"/api/club/{a}/matches/{foreign_match.id}", {"competition": "IDOR"}),
        ("GET", f"/api/club/{a}/matches/{foreign_match.id}", None),
        ("PUT", f"/api/club/{a}/matches/{foreign_match.id}/roster", {"entries": []}),
        ("POST", f"/api/club/{a}/matches/{foreign_match.id}/process", None),
        ("GET", f"/api/club/{a}/matches/{foreign_match.id}/report", None),
    )
    for method, path, body in attacks:
        response = client.open(path, method=method, json=body, headers=_headers("a"))
        assert response.status_code == 404, (method, path, response.get_json())


def test_coach_and_system_briefs_are_scoped_written_read_and_cleared(club_app, client):
    a = club_app.c2["program_a"]
    b = club_app.c2["program_b"]
    member_id = _add_api_member(client, a)
    foreign_member_id = _add_api_member(client, b, 7002, "b")

    member_response = client.put(
        f"/api/club/{a}/roster/{member_id}/brief",
        json={"body": "  Hold width before receiving  \n\n Scan before turning "},
        headers=_headers("a"),
    )
    assert member_response.status_code == 200
    member_brief = member_response.get_json()["member"]["brief"]
    assert member_brief["body"] == "Hold width before receiving\nScan before turning"
    assert member_brief["updated_at"] is not None

    system_response = client.put(
        f"/api/club/{a}/system-brief",
        json={"body": "  Stay compact across phases  "},
        headers=_headers("a"),
    )
    assert system_response.status_code == 200
    system_brief = system_response.get_json()["system_brief"]
    assert system_brief["body"] == "Stay compact across phases"
    assert system_brief["updated_at"] is not None

    roster = client.get(f"/api/club/{a}/roster", headers=_headers("a"))
    assert roster.status_code == 200
    body = roster.get_json()
    assert body["system_brief"] == system_brief
    assert body["members"][0]["brief"] == member_brief

    member = db.session.get(ClubRosterMember, member_id)
    program = db.session.get(ClubProgram, a)
    assert member.brief_updated_by_user_id == club_app.c2["users"]["a"]
    assert program.system_brief_updated_by_user_id == club_app.c2["users"]["a"]

    for path in (
        f"/api/club/{b}/roster/{foreign_member_id}/brief",
        f"/api/club/{b}/system-brief",
    ):
        denied = client.put(path, json={"body": "Keep the back line connected"}, headers=_headers("a"))
        assert denied.status_code == 403
        assert denied.get_json() == {"error": "Club manager access denied"}

    foreign = client.put(
        f"/api/club/{a}/roster/{foreign_member_id}/brief",
        json={"body": "Keep the back line connected"},
        headers=_headers("a"),
    )
    assert foreign.status_code == 404
    assert foreign.get_json() == {"error": "Member not found"}

    cleared_member = client.put(
        f"/api/club/{a}/roster/{member_id}/brief",
        json={"body": "  \n\t "},
        headers=_headers("a"),
    )
    cleared_system = client.put(
        f"/api/club/{a}/system-brief",
        json={"body": ""},
        headers=_headers("a"),
    )
    assert cleared_member.get_json()["member"]["brief"] == {"body": None, "updated_at": None}
    assert cleared_system.get_json()["system_brief"] == {"body": None, "updated_at": None}
    db.session.refresh(member)
    db.session.refresh(program)
    assert (member.coach_brief_body, member.brief_updated_at, member.brief_updated_by_user_id) == (None, None, None)
    assert (
        program.system_brief_body,
        program.system_brief_updated_at,
        program.system_brief_updated_by_user_id,
    ) == (None, None, None)


def test_brief_name_screening_covers_short_latin_non_latin_and_match_rosters(club_app, client):
    program_id = club_app.c2["program_a"]
    local_players = [
        _local(club_app.c2["users"]["a"], name=name, birth_year=2000 + index, status="approved")
        for index, name in enumerate(("Mika Tanaka", "Alex Li", "Kai Ng", "José Silva", "田中 太郎"))
    ]
    member_id = _add_local_member(client, program_id, local_players[0].id)
    for local in local_players[1:]:
        _add_local_member(client, program_id, local.id)
    match = _match(program_id)
    db.session.add(
        VideoRosterEntry(
            video_match_id=match.id,
            player_name="Guest Striker",
            jersey_number=17,
        )
    )
    db.session.commit()

    local_name = client.put(
        f"/api/club/{program_id}/roster/{member_id}/brief",
        json={"body": "Hold the line\n\nAsk mIKA to receive between the lines"},
        headers=_headers("a"),
    )
    assert local_name.status_code == 400
    assert local_name.get_json() == {
        "error": 'Briefs describe behaviours, not people — remove the name "Mika" from line 3.'
    }

    for brief, token in (
        ("Li must stay wide", "Li"),
        ("Recover behind Ng", "Ng"),
        ("Alexに任せる", "Alex"),
        ("ask jose to turn", "José"),
        ("JOSÉ must turn", "José"),
        ("田中に前を向かせる", "田中"),
    ):
        short_name = client.put(
            f"/api/club/{program_id}/system-brief",
            json={"body": brief},
            headers=_headers("a"),
        )
        assert short_name.status_code == 400
        assert short_name.get_json() == {
            "error": f'Briefs describe behaviours, not people — remove the name "{token}" from line 1.'
        }

    match_name = client.put(
        f"/api/club/{program_id}/system-brief",
        json={"body": "Press GUEST after turnovers"},
        headers=_headers("a"),
    )
    assert match_name.status_code == 400
    assert match_name.get_json() == {
        "error": 'Briefs describe behaviours, not people — remove the name "Guest" from line 1.'
    }

    unrelated = client.put(
        f"/api/club/{program_id}/system-brief",
        json={"body": "Move to receive in the line"},
        headers=_headers("a"),
    )
    assert unrelated.status_code == 200
    assert unrelated.get_json()["system_brief"]["body"] == "Move to receive in the line"

    latin_prefix = client.put(
        f"/api/club/{program_id}/system-brief",
        json={"body": "Ask Mikael to receive between the lines"},
        headers=_headers("a"),
    )
    assert latin_prefix.status_code == 200
    assert latin_prefix.get_json()["system_brief"]["body"] == "Ask Mikael to receive between the lines"

    original_line_number = client.put(
        f"/api/club/{program_id}/system-brief",
        json={"body": "\n\nAsk Mika to turn"},
        headers=_headers("a"),
    )
    assert original_line_number.status_code == 400
    assert original_line_number.get_json() == {
        "error": 'Briefs describe behaviours, not people — remove the name "Mika" from line 3.'
    }


def test_empty_brief_clears_before_building_roster_name_tokens(club_app, client, monkeypatch):
    program_id = club_app.c2["program_a"]
    program = db.session.get(ClubProgram, program_id)
    program.system_brief_body = "Stay compact"
    db.session.commit()

    monkeypatch.setattr(
        club_routes,
        "_brief_name_tokens",
        lambda _program: pytest.fail("empty briefs must not query roster name tokens"),
    )
    response = client.put(
        f"/api/club/{program_id}/system-brief",
        json={"body": " \n\t "},
        headers=_headers("a"),
    )

    assert response.status_code == 200
    assert response.get_json()["system_brief"] == {"body": None, "updated_at": None}


@pytest.mark.parametrize(
    ("body", "message"),
    (
        ("x" * 2001, "Brief must be at most 2000 characters"),
        ("\n".join(f"movement {number}" for number in range(13)), "Brief must contain at most 12 non-empty lines"),
        ("x" * 241, "Brief lines must be at most 240 characters"),
    ),
)
def test_brief_bounds_are_enforced(club_app, client, body, message):
    response = client.put(
        f"/api/club/{club_app.c2['program_a']}/system-brief",
        json={"body": body},
        headers=_headers("a"),
    )
    assert response.status_code == 400
    assert response.get_json() == {"error": message}


def test_club_manager_records_result_with_forced_provenance_and_one_commit(club_app, client, monkeypatch):
    program_id = club_app.c2["program_a"]
    manager_id = club_app.c2["users"]["a"]
    api_member_id = _add_api_member(client, program_id)
    local = _local(manager_id, birth_year=2000, status="approved")
    local.api_player_id = -local.id
    db.session.commit()
    local_member_id = _add_local_member(client, program_id, local.id)
    refreshes = []
    commits = []
    real_refresh = season_rollup_service.refresh_player
    real_commit = db.session.commit

    def recording_refresh(player_api_id, season=None, session=None):
        stored = PlayerMatchEntry.query.filter_by(player_api_id=player_api_id).one()
        refreshes.append((player_api_id, season, session is db.session, stored.source, stored.status))
        return real_refresh(player_api_id, season, session=session)

    def counting_commit():
        commits.append("commit")
        return real_commit()

    monkeypatch.setattr(season_rollup_service, "refresh_player", recording_refresh)
    monkeypatch.setattr(db.session, "commit", counting_commit)
    payload = _result_payload([api_member_id, local_member_id])
    payload.update(
        {
            "source": "self",
            "status": "disputed",
            "club_program_id": club_app.c2["program_b"],
            "reported_by_user_id": club_app.c2["users"]["b"],
        }
    )

    with (
        patch.object(club_routes, "_lock_program_quota") as program_lock,
        patch.object(club_routes, "_lock_result_players") as player_lock,
    ):
        response = client.post(f"/api/club/{program_id}/results", json=payload, headers=_headers("a"))

    assert response.status_code == 201
    body = response.get_json()
    assert body["result"] == {
        "video_match_id": None,
        "match_date": "2025-09-01",
        "opponent": "Rivals FC",
        "competition": "County League",
        "home_away": "home",
        "result_for": 2,
        "result_against": 1,
    }
    matches_by_member = {row["club_roster_member_id"]: row for row in body["matches"]}
    assert matches_by_member[api_member_id]["player_api_id"] == 7001
    assert matches_by_member[local_member_id]["player_api_id"] == -local.id
    assert all(row["source"] == "club" and row["status"] == "club_confirmed" for row in body["matches"])
    stats_by_player = body["season_stats_by_player"]
    assert set(stats_by_player) == {"7001", str(-local.id)}
    assert stats_by_player["7001"]["club_roster_member_id"] == api_member_id
    assert stats_by_player[str(-local.id)]["club_roster_member_id"] == local_member_id
    assert stats_by_player["7001"]["player_name"] == "Known Academy Player"
    assert stats_by_player[str(-local.id)]["player_name"] == "Club Local Player"
    assert all(
        (row["source"], row["season"], row["appearances"], row["minutes"], row["goals"]) == ("club", 2025, 1, 90, 1)
        for row in stats_by_player.values()
    )
    assert set(refreshes) == {
        (7001, 2025, True, "club", "club_confirmed"),
        (-local.id, 2025, True, "club", "club_confirmed"),
    }
    assert commits == ["commit"]
    program_lock.assert_called_once_with(program_id)
    player_lock.assert_called_once_with({7001, -local.id})
    assert VideoMatch.query.filter_by(club_program_id=program_id).count() == 0
    stored = PlayerMatchEntry.query.order_by(PlayerMatchEntry.player_api_id.desc()).all()
    assert {(row.player_api_id, row.club_program_id, row.reported_by_user_id) for row in stored} == {
        (7001, program_id, manager_id),
        (-local.id, program_id, manager_id),
    }


def test_club_result_repost_updates_idempotently_and_refreshes_rollup(club_app, client):
    program_id = club_app.c2["program_a"]
    member_id = _add_api_member(client, program_id)
    video_match = _match(program_id, status="created")
    fixture = Fixture(
        fixture_id_api=997001,
        season=2025,
        competition_name="County League",
    )
    db.session.add(fixture)
    db.session.flush()
    db.session.add(
        FixturePlayerStats(
            fixture_id=fixture.id,
            player_api_id=7001,
            team_api_id=9911,
            minutes=900,
            goals=9,
            assists=4,
            yellows=2,
            reds=1,
        )
    )
    db.session.commit()
    first = client.post(
        f"/api/club/{program_id}/results",
        json=_result_payload([member_id], video_match_id=video_match.id),
        headers=_headers("a"),
    )
    updated_payload = _result_payload([member_id], video_match_id=video_match.id, result_for=3)
    updated_payload["entries"][0].update({"goals": 3, "note": "Corrected"})
    repeated = client.post(
        f"/api/club/{program_id}/results",
        json=updated_payload,
        headers=_headers("a"),
    )

    assert first.status_code == 201
    assert repeated.status_code == 200
    assert repeated.get_json()["result"]["video_match_id"] == video_match.id
    assert repeated.get_json()["matches"][0]["id"] == first.get_json()["matches"][0]["id"]
    assert repeated.get_json()["matches"][0]["goals"] == 3
    assert repeated.get_json()["season_stats_by_player"] == {
        "7001": {
            "club_roster_member_id": member_id,
            "player_name": "Known Academy Player",
            "season": 2025,
            "level_group": "senior",
            "source": "club",
            "appearances": 1,
            "minutes": 90,
            "goals": 3,
            "assists": 0,
            "yellows": 0,
            "reds": 0,
            "saves": None,
            "goals_conceded": None,
        }
    }
    assert PlayerMatchEntry.query.filter_by(player_api_id=7001, source="club").count() == 1
    entry = PlayerMatchEntry.query.filter_by(player_api_id=7001, source="club").one()
    assert (entry.result_for, entry.note) == (3, "Corrected")
    total = PlayerSeasonTotal.query.filter_by(player_api_id=7001, season=2025, level_group="senior").one()
    assert (total.primary_source, total.appearances, total.minutes, total.goals) == ("fixtures", 1, 900, 9)
    assert (total.source_breakdown["club"]["minutes"], total.source_breakdown["club"]["goals"]) == (90, 3)
    history = client.get(f"/api/club/{program_id}/results?season=2025", headers=_headers("a"))
    assert history.status_code == 200
    assert history.get_json()["results"][0]["result"]["video_match_id"] is None


def test_program_managers_share_one_fixture_identity_and_history_group(club_app, client):
    program_id = club_app.c2["program_a"]
    manager_a_id = club_app.c2["users"]["a"]
    manager_b_id = club_app.c2["users"]["b"]
    member_one = _add_api_member(client, program_id, 7001)
    member_two = _add_api_member(client, program_id, 7002)
    _grant_program_manager(program_id, manager_b_id)

    first = client.post(
        f"/api/club/{program_id}/results",
        json=_result_payload([member_one]),
        headers=_headers("a"),
    )
    corrected_payload = _result_payload([member_one], result_for=5)
    corrected_payload["entries"][0]["goals"] = 2
    corrected = client.post(
        f"/api/club/{program_id}/results",
        json=corrected_payload,
        headers=_headers("b"),
    )

    assert first.status_code == 201
    assert corrected.status_code == 200
    assert corrected.get_json()["matches"][0]["id"] == first.get_json()["matches"][0]["id"]
    rows = PlayerMatchEntry.query.filter_by(
        player_api_id=7001,
        match_date=date(2025, 9, 1),
        opponent="Rivals FC",
        source="club",
        club_program_id=program_id,
    ).all()
    assert len(rows) == 1
    assert (rows[0].reported_by_user_id, rows[0].result_for, rows[0].goals) == (manager_a_id, 5, 2)
    total = PlayerSeasonTotal.query.filter_by(player_api_id=7001, season=2025, level_group="senior").one()
    assert total.source_breakdown["club"]["appearances"] == 1
    assert total.source_breakdown["club"]["minutes"] == 90
    assert total.source_breakdown["club"]["goals"] == 2
    db.session.expunge(total)

    added = client.post(
        f"/api/club/{program_id}/results",
        json=_result_payload([member_two], result_for=6),
        headers=_headers("b"),
    )
    history = client.get(f"/api/club/{program_id}/results?season=2025", headers=_headers("a"))

    assert added.status_code == 201
    assert PlayerMatchEntry.query.filter_by(club_program_id=program_id, source="club").count() == 2
    reporters = {
        row.player_api_id: row.reported_by_user_id
        for row in PlayerMatchEntry.query.filter_by(club_program_id=program_id, source="club").all()
    }
    assert reporters == {7001: manager_a_id, 7002: manager_b_id}
    assert history.status_code == 200
    assert history.get_json()["total"] == 1
    assert history.get_json()["results"][0]["result"]["result_for"] == 6
    assert {row["club_roster_member_id"] for row in history.get_json()["results"][0]["matches"]} == {
        member_one,
        member_two,
    }


@pytest.mark.parametrize("second_manager_key", ["b", "a"], ids=["different-manager", "same-manager"])
def test_matching_player_fixture_is_rejected_in_another_program(club_app, client, second_manager_key):
    program_a = club_app.c2["program_a"]
    program_b = club_app.c2["program_b"]
    member_a = _add_api_member(client, program_a, 7001, "a")
    member_b = _add_api_member(client, program_b, 7001, "b")
    if second_manager_key == "a":
        _grant_program_manager(program_b, club_app.c2["users"]["a"])

    first = client.post(
        f"/api/club/{program_a}/results",
        json=_result_payload([member_a]),
        headers=_headers("a"),
    )
    conflict = client.post(
        f"/api/club/{program_b}/results",
        json=_result_payload([member_b]),
        headers=_headers(second_manager_key),
    )

    assert first.status_code == 201
    assert conflict.status_code == 409
    assert conflict.get_json() == {"error": "A matching result entry already belongs to another club program"}
    assert PlayerMatchEntry.query.filter_by(player_api_id=7001, source="club").count() == 1
    total = PlayerSeasonTotal.query.filter_by(player_api_id=7001, season=2025, level_group="senior").one()
    assert (total.source_breakdown["club"]["appearances"], total.source_breakdown["club"]["minutes"]) == (1, 90)


def test_club_result_rejects_foreign_roster_member_atomically(club_app, client, monkeypatch):
    program_a = club_app.c2["program_a"]
    own_member = _add_api_member(client, program_a)
    foreign_member = _add_api_member(client, club_app.c2["program_b"], 7002, "b")
    monkeypatch.setattr(
        season_rollup_service,
        "refresh_player",
        lambda *args, **kwargs: pytest.fail("invalid roster must not refresh rollups"),
    )

    response = client.post(
        f"/api/club/{program_a}/results",
        json=_result_payload([own_member, foreign_member]),
        headers=_headers("a"),
    )

    assert response.status_code == 409
    assert response.get_json() == {"error": "Every result player must belong to this club program"}
    assert PlayerMatchEntry.query.count() == 0


def test_club_result_rejects_foreign_or_noneditable_video_match(club_app, client):
    program_a = club_app.c2["program_a"]
    member_id = _add_api_member(client, program_a)
    foreign_match = _match(club_app.c2["program_b"], status="created")
    own_finalized = _match(program_a, status="finalized")

    foreign = client.post(
        f"/api/club/{program_a}/results",
        json=_result_payload([member_id], video_match_id=foreign_match.id),
        headers=_headers("a"),
    )
    noneditable = client.post(
        f"/api/club/{program_a}/results",
        json=_result_payload([member_id], video_match_id=own_finalized.id),
        headers=_headers("a"),
    )

    assert foreign.status_code == 409
    assert foreign.get_json() == {"error": "Video match must belong to this club program and remain editable"}
    assert noneditable.status_code == 409
    assert noneditable.get_json() == {"error": "Video match must belong to this club program and remain editable"}
    assert PlayerMatchEntry.query.count() == 0


def test_club_result_rejects_local_member_without_approved_synthetic_id(club_app, client):
    program_id = club_app.c2["program_a"]
    local = _local(club_app.c2["users"]["a"], birth_year=2000, status="approved")
    member_id = _add_local_member(client, program_id, local.id)

    response = client.post(
        f"/api/club/{program_id}/results",
        json=_result_payload([member_id]),
        headers=_headers("a"),
    )

    assert response.status_code == 409
    assert response.get_json() == {
        "error": "Local roster members need an approved local player identity before stats can be recorded"
    }
    assert PlayerMatchEntry.query.count() == 0


def test_positive_minor_roster_and_result_use_rollup_age_rule(club_app, client):
    program_id = club_app.c2["program_a"]
    minor = TrackedPlayer(
        player_api_id=7003,
        player_name="Youth Academy Player",
        birth_date=f"{datetime.now(UTC).year - 15}-04-03",
        position="Forward",
        team_id=club_app.c2["team"],
        status="academy",
        is_active=True,
    )
    db.session.add(minor)
    db.session.commit()
    member_id = _add_api_member(client, program_id, minor.player_api_id)

    roster = client.get(f"/api/club/{program_id}/roster", headers=_headers("a"))
    response = client.post(
        f"/api/club/{program_id}/results",
        json=_result_payload([member_id]),
        headers=_headers("a"),
    )
    public_history = client.get(f"/api/players/{minor.player_api_id}/matches")
    private_history = client.get(
        f"/api/players/{minor.player_api_id}/matches",
        headers=_headers("a"),
    )

    assert roster.status_code == 200
    roster_member = next(row for row in roster.get_json()["members"] if row["id"] == member_id)
    assert roster_member["is_minor"] is True
    assert response.status_code == 201
    assert public_history.status_code == 404
    assert private_history.status_code == 200
    assert private_history.get_json()["total"] == 1
    assert PlayerMatchEntry.query.filter_by(player_api_id=minor.player_api_id, source="club").count() == 1
    assert PlayerSeasonCell.query.filter_by(player_api_id=minor.player_api_id, source="club").count() == 0
    assert PlayerSeasonTotal.query.filter_by(player_api_id=minor.player_api_id, season=2025).count() == 0
    assert response.get_json()["season_stats_by_player"] == {
        "7003": {
            "club_roster_member_id": member_id,
            "player_name": "Youth Academy Player",
            "season": 2025,
            "level_group": "senior",
            "source": "club",
            "withheld": "minor",
        }
    }


def test_list_club_results_groups_entries_and_filters_by_season(club_app, client):
    program_a = club_app.c2["program_a"]
    member_one = _add_api_member(client, program_a, 7001)
    member_two = _add_api_member(client, program_a, 7002)
    foreign_member = _add_api_member(client, club_app.c2["program_b"], 7001, "b")
    created = client.post(
        f"/api/club/{program_a}/results",
        json=_result_payload([member_one, member_two]),
        headers=_headers("a"),
    )
    assert created.status_code == 201
    corrected = client.post(
        f"/api/club/{program_a}/results",
        json=_result_payload(
            [member_one],
            competition="U21 County League",
            result_for=3,
        ),
        headers=_headers("a"),
    )
    assert corrected.status_code == 200
    assert corrected.get_json()["season_stats_by_player"]["7001"]["level_group"] == "youth"
    assert (
        client.post(
            f"/api/club/{program_a}/results",
            json=_result_payload([member_one], match_date="2024-09-01", opponent="Older FC"),
            headers=_headers("a"),
        ).status_code
        == 201
    )
    assert (
        client.post(
            f"/api/club/{club_app.c2['program_b']}/results",
            json=_result_payload([foreign_member], opponent="Foreign FC"),
            headers=_headers("b"),
        ).status_code
        == 201
    )

    filtered = client.get(f"/api/club/{program_a}/results?season=2025", headers=_headers("a"))
    all_results = client.get(f"/api/club/{program_a}/results", headers=_headers("a"))
    invalid = client.get(f"/api/club/{program_a}/results?season=not-a-season", headers=_headers("a"))

    assert filtered.status_code == 200
    assert filtered.get_json()["total"] == 1
    group = filtered.get_json()["results"][0]
    assert group["result"] == {
        "video_match_id": None,
        "match_date": "2025-09-01",
        "opponent": "Rivals FC",
        "competition": "U21 County League",
        "home_away": "home",
        "result_for": 3,
        "result_against": 1,
    }
    assert {row["club_roster_member_id"] for row in group["matches"]} == {member_one, member_two}
    assert {row["competition"] for row in group["matches"]} == {"U21 County League"}
    assert {row["result_for"] for row in group["matches"]} == {3}
    assert PlayerSeasonTotal.query.filter_by(
        player_api_id=7002,
        season=2025,
        level_group="youth",
    ).one()
    assert (
        PlayerSeasonTotal.query.filter_by(
            player_api_id=7002,
            season=2025,
            level_group="senior",
        ).one_or_none()
        is None
    )
    assert all_results.status_code == 200
    assert [row["result"]["match_date"] for row in all_results.get_json()["results"]] == [
        "2025-09-01",
        "2024-09-01",
    ]
    assert invalid.status_code == 400
    assert invalid.get_json() == {"error": "season must be an integer"}


def test_shadow_only_positive_roster_member_remains_available(club_app, client):
    program_id = club_app.c2["program_a"]
    shadow = PlayerShadow(
        player_api_id=7999,
        player_name="Graduated Shadow Player",
        position="Defender",
        birth_date=date(2000, 1, 1),
        is_active=True,
    )
    db.session.add(shadow)
    db.session.flush()
    member = ClubRosterMember(
        program_id=program_id,
        player_api_id=shadow.player_api_id,
        added_by_user_id=club_app.c2["users"]["a"],
    )
    db.session.add(member)
    db.session.commit()

    response = client.get(f"/api/club/{program_id}/roster", headers=_headers("a"))

    assert response.status_code == 200
    assert response.get_json()["members"] == [
        {
            "id": member.id,
            "program_id": program_id,
            "role": None,
            "note": None,
            "brief": {"body": None, "updated_at": None},
            "created_at": response.get_json()["members"][0]["created_at"],
            "available": True,
            "subject_type": "tracked",
            "player_api_id": 7999,
            "local_player_id": None,
            "display_name": "Graduated Shadow Player",
            "position": "Defender",
            "is_minor": False,
        }
    ]


def test_roster_crud_is_program_scoped_and_local_must_be_manager_created(club_app, client):
    a = club_app.c2["program_a"]
    b = club_app.c2["program_b"]
    member_id = _add_api_member(client, a)
    assert client.post(f"/api/club/{a}/roster", json={"player_api_id": 7001}, headers=_headers("a")).status_code == 409
    assert client.delete(f"/api/club/{b}/roster/{member_id}", headers=_headers("a")).status_code == 403
    assert client.delete(f"/api/club/{a}/roster/{member_id + 999}", headers=_headers("a")).status_code == 404

    foreign_local = _local(club_app.c2["users"]["b"])
    response = client.post(
        f"/api/club/{a}/roster",
        json={"local_player_id": foreign_local.id},
        headers=_headers("a"),
    )
    assert response.status_code == 404
    assert client.delete(f"/api/club/{a}/roster/{member_id}", headers=_headers("a")).status_code == 204


def test_minor_local_player_is_flagged_private_and_hidden_from_public_and_scout(club_app, client):
    a = club_app.c2["program_a"]
    local = _local(club_app.c2["users"]["a"], birth_year=datetime.now(UTC).year - 16, status="approved")
    db.session.add(
        PlayerProfileClaim(
            local_player_id=local.id,
            user_account_id=club_app.c2["users"]["a"],
            relationship_type="guardian",
            status="approved",
        )
    )
    db.session.commit()
    added = client.post(
        f"/api/club/{a}/roster",
        json={"local_player_id": local.id},
        headers=_headers("a"),
    )
    assert added.status_code == 201
    assert added.get_json()["member"]["is_minor"] is True
    assert client.get(f"/api/local-players/{local.id}").status_code == 404
    assert client.get(f"/api/local-players/{local.id}", headers=_headers("scout")).status_code == 404
    owner = client.get(f"/api/local-players/{local.id}", headers=_headers("a"))
    assert owner.status_code == 200


def test_local_identity_cannot_duplicate_real_or_suppressed_tracked_player(club_app, client):
    _active_suppression(player_api_id=7001)
    response = client.post(
        "/api/local-players",
        json={
            "display_name": "Known Academy Player",
            "birth_year": 2005,
            "relationship_type": "guardian",
        },
        headers=_headers("a"),
    )
    assert response.status_code == 409
    assert response.get_json() == {"error": "An existing player identity needs review"}


def test_suppressed_retained_shadow_cannot_be_recreated_or_attached_as_local(club_app, client):
    program_id = club_app.c2["program_a"]
    user_id = club_app.c2["users"]["a"]
    shadow_api_id = 8_801
    birth_year = datetime.now(UTC).year - 20
    db.session.add(
        PlayerShadow(
            player_api_id=shadow_api_id,
            player_name="Retained Shadow Player",
            birth_date=date(birth_year, 6, 1),
            is_active=False,
        )
    )
    db.session.commit()
    _active_suppression(player_api_id=shadow_api_id)

    recreated = client.post(
        "/api/local-players",
        json={
            "display_name": "  RETAINED   shadow player ",
            "birth_year": birth_year,
            "relationship_type": "guardian",
        },
        headers=_headers("a"),
    )
    assert recreated.status_code == 409
    assert recreated.get_json() == {"error": "An existing player identity needs review"}

    name_alias = _local(
        user_id,
        name="Retained Shadow Player",
        birth_year=birth_year,
        status="approved",
    )
    api_alias = _local(
        user_id,
        name="Different Local Name",
        birth_year=birth_year - 1,
        status="approved",
    )
    api_alias.api_player_id = shadow_api_id
    db.session.commit()

    for alias in (name_alias, api_alias):
        attached = client.post(
            f"/api/club/{program_id}/roster",
            json={"local_player_id": alias.id},
            headers=_headers("a"),
        )
        assert attached.status_code == 409
        assert attached.get_json() == {"error": "An existing player identity needs review"}


def test_sas_and_upload_complete_are_program_scoped_and_expiry_bounded(club_app, client):
    a = club_app.c2["program_a"]
    b = club_app.c2["program_b"]
    match = _match(a, status="created", kickoff_s=None)
    expiry = datetime.now(UTC) + timedelta(minutes=60)
    sas = {
        "upload_url": "https://blob.invalid/write-only",
        "blob_path": match.blob_path,
        "expires_at": expiry.isoformat(),
        "max_bytes": 12 * 1024**3,
    }
    with (
        patch("src.routes.club.video_storage.is_configured", return_value=True),
        patch("src.routes.club.video_storage.mint_upload_sas", return_value=sas) as mint,
        patch(
            "src.routes.club.video_storage.verify_uploaded_blob",
            return_value={"ok": True, "etag": "verified-etag", "size_bytes": 2048},
        ) as verify,
    ):
        assert client.post(f"/api/club/{b}/matches/{match.id}/sas", headers=_headers("a")).status_code == 403
        assert client.post(f"/api/club/{a}/matches/{match.id + 999}/sas", headers=_headers("a")).status_code == 404
        own = client.post(f"/api/club/{a}/matches/{match.id}/sas", headers=_headers("a"))
        assert own.status_code == 200
        assert datetime.fromisoformat(own.get_json()["expires_at"]) <= datetime.now(UTC) + timedelta(minutes=61)
        mint.assert_called_once_with(match.blob_path)
        assert (
            client.post(
                f"/api/club/{b}/matches/{match.id}/upload-complete",
                json={"kickoff_s": 0},
                headers=_headers("a"),
            ).status_code
            == 403
        )
        completed = client.post(
            f"/api/club/{a}/matches/{match.id}/upload-complete",
            json={"kickoff_s": 0, "duration_s": 5400},
            headers=_headers("a"),
        )
        assert completed.status_code == 200
        verify.assert_called_once_with(match.blob_path)


def test_reused_upload_sas_is_write_only_path_scoped_and_one_hour_bounded():
    class FakePermissions:
        def __init__(self, *, read=False, write=False, create=False):
            self.read = read
            self.write = write
            self.create = create

    before = datetime.now(UTC)
    with (
        patch.object(video_storage, "BlobSasPermissions", FakePermissions, create=True),
        patch.object(video_storage, "_mint_sas", return_value="fixture-signature") as mint,
        patch.object(
            video_storage,
            "_service_client",
            return_value=SimpleNamespace(url="https://storage.example/"),
        ),
    ):
        result = video_storage.mint_upload_sas("matches/42/random.mp4")
    after = datetime.now(UTC)
    blob_path, permissions, expiry = mint.call_args.args
    assert blob_path == "matches/42/random.mp4"
    assert permissions.write is True
    assert permissions.create is True
    assert permissions.read is False
    assert before + timedelta(minutes=59) <= expiry <= after + timedelta(minutes=61)
    assert result["blob_path"] == blob_path
    assert result["expires_at"] == expiry.isoformat()


def test_match_quota_uses_serialized_count_and_returns_429(club_app, client, monkeypatch):
    a = club_app.c2["program_a"]
    monkeypatch.setenv("CLUB_MATCH_QUOTA_DEFAULT", "1")
    with patch("src.routes.club._lock_program_quota") as lock:
        first = client.post(f"/api/club/{a}/matches", json={"opponent_name": "One"}, headers=_headers("a"))
        second = client.post(f"/api/club/{a}/matches", json={"opponent_name": "Two"}, headers=_headers("a"))
    assert first.status_code == 201
    assert second.status_code == 429
    assert "quota reached" in second.get_json()["error"].lower()
    assert lock.call_count == 2


@pytest.mark.parametrize(
    "capture_meta",
    [
        {"notes": "x" * (8 * 1024)},
        {"one": {"two": {"three": {"four": {"five": "too deep"}}}}},
        {f"key_{index}": index for index in range(51)},
    ],
    ids=("serialized-size", "nesting-depth", "key-count"),
)
def test_capture_meta_bounds_are_enforced_on_create_and_update(club_app, client, capture_meta):
    program_id = club_app.c2["program_a"]
    created = client.post(
        f"/api/club/{program_id}/matches",
        json={"capture_meta": capture_meta},
        headers=_headers("a"),
    )
    assert created.status_code == 400
    assert "capture_meta" in created.get_json()["error"]

    match = _match(program_id, status="created")
    updated = client.patch(
        f"/api/club/{program_id}/matches/{match.id}",
        json={"capture_meta": capture_meta},
        headers=_headers("a"),
    )
    assert updated.status_code == 400
    assert "capture_meta" in updated.get_json()["error"]


@pytest.mark.parametrize("timeline_value", [True, 6 * 60 * 60 + 1], ids=("boolean", "over-six-hours"))
def test_timeline_rejects_boolean_and_pathological_values_on_complete_and_update(club_app, client, timeline_value):
    program_id = club_app.c2["program_a"]
    match = _match(program_id, status="created", kickoff_s=None)
    with (
        patch("src.routes.club.video_storage.is_configured", return_value=True),
        patch(
            "src.routes.club.video_storage.verify_uploaded_blob",
            return_value={"ok": True, "etag": "etag-c2", "size_bytes": 2048},
        ),
    ):
        completed = client.post(
            f"/api/club/{program_id}/matches/{match.id}/upload-complete",
            json={"kickoff_s": timeline_value},
            headers=_headers("a"),
        )
    assert completed.status_code == 400
    assert "kickoff_s" in completed.get_json()["error"]

    updated = client.patch(
        f"/api/club/{program_id}/matches/{match.id}",
        json={"duration_s": timeline_value},
        headers=_headers("a"),
    )
    assert updated.status_code == 400
    assert "duration_s" in updated.get_json()["error"]


def test_club_match_roster_rejects_foreign_and_departed_members(club_app, client):
    a = club_app.c2["program_a"]
    b = club_app.c2["program_b"]
    member_a = _add_api_member(client, a, 7001, "a")
    member_b = _add_api_member(client, b, 7002, "b")
    match = _match(a)
    foreign = client.put(
        f"/api/club/{a}/matches/{match.id}/roster",
        json={"entries": [{"club_roster_member_id": member_b, "jersey_number": 4}]},
        headers=_headers("a"),
    )
    assert foreign.status_code == 400
    own = client.put(
        f"/api/club/{a}/matches/{match.id}/roster",
        json={"entries": [{"club_roster_member_id": member_a, "jersey_number": 8}]},
        headers=_headers("a"),
    )
    assert own.status_code == 200
    entry_id = own.get_json()["roster"][0]["id"]
    assert client.delete(f"/api/club/{a}/roster/{member_a}", headers=_headers("a")).status_code == 204
    assert db.session.get(VideoRosterEntry, entry_id).club_roster_member_id is None
    departed = client.put(
        f"/api/club/{a}/matches/{match.id}/roster",
        json={"entries": [{"club_roster_member_id": member_a, "jersey_number": 8}]},
        headers=_headers("a"),
    )
    assert departed.status_code == 400


def test_processing_request_never_enqueues_and_admin_pipeline_remains_concierge(club_app, client):
    a = club_app.c2["program_a"]
    match = _match(a)
    with (
        patch(
            "src.services.video_storage.verify_uploaded_blob",
            return_value={"ok": True, "etag": "etag-c2", "size_bytes": 2048},
        ) as verify,
        patch("src.routes.video.video_queue.enqueue", return_value="fixture") as enqueue,
    ):
        requested = client.post(
            f"/api/club/{a}/matches/{match.id}/process",
            headers=_headers("a"),
        )
        assert requested.status_code == 202
        assert requested.get_json()["processing_request_status"] == "requested"
        assert db.session.get(VideoMatch, match.id).status == "uploaded"
        assert VideoAnalysisJob.query.filter_by(video_match_id=match.id).count() == 0
        enqueue.assert_not_called()

        processed = client.post(f"/api/admin/video/matches/{match.id}/process", headers=_admin_headers())
        assert processed.status_code == 202
        assert VideoAnalysisJob.query.filter_by(video_match_id=match.id).count() == 1
        enqueue.assert_called_once()
        assert verify.call_count == 2

        assert (
            client.patch(
                f"/api/club/{a}/matches/{match.id}",
                json={"competition": "tampered after queue"},
                headers=_headers("a"),
            ).status_code
            == 400
        )
        assert (
            client.put(
                f"/api/club/{a}/matches/{match.id}/roster",
                json={"entries": [{"club_roster_member_id": 1, "jersey_number": 1}]},
                headers=_headers("a"),
            ).status_code
            == 400
        )

    for path in ("tracklets", "tags", "finalize", "requeue"):
        response = client.post(f"/api/club/{a}/matches/{match.id}/{path}", headers=_headers("a"))
        assert response.status_code == 404


def test_changed_blob_etag_blocks_club_request_and_admin_enqueue(club_app, client):
    program_id = club_app.c2["program_a"]
    match = _match(program_id)
    changed = {"ok": True, "etag": "swapped-etag", "size_bytes": 2048}
    with patch("src.services.video_storage.verify_uploaded_blob", return_value=changed):
        club_response = client.post(
            f"/api/club/{program_id}/matches/{match.id}/process",
            headers=_headers("a"),
        )
    assert club_response.status_code == 422
    assert "ETag mismatch" in club_response.get_json()["error"]
    assert db.session.get(VideoMatch, match.id).processing_requested_at is None

    match.processing_requested_at = datetime.now(UTC)
    match.processing_requested_by_user_id = club_app.c2["users"]["a"]
    db.session.commit()
    with (
        patch("src.services.video_storage.verify_uploaded_blob", return_value=changed),
        patch("src.routes.video.video_queue.enqueue") as enqueue,
    ):
        admin_response = client.post(f"/api/admin/video/matches/{match.id}/process", headers=_admin_headers())
    assert admin_response.status_code == 422
    assert "ETag mismatch" in admin_response.get_json()["error"]
    assert VideoAnalysisJob.query.filter_by(video_match_id=match.id).count() == 0
    enqueue.assert_not_called()

    match.status = "failed"
    db.session.add(VideoAnalysisJob(video_match_id=match.id, status="failed", pipeline_version="c2-test"))
    db.session.commit()
    with (
        patch("src.services.video_storage.verify_uploaded_blob", return_value=changed),
        patch("src.routes.video.video_queue.enqueue") as requeue_enqueue,
    ):
        requeue_response = client.post(
            f"/api/admin/video/matches/{match.id}/requeue",
            headers=_admin_headers(),
        )
    assert requeue_response.status_code == 422
    assert "ETag mismatch" in requeue_response.get_json()["error"]
    assert VideoAnalysisJob.query.filter_by(video_match_id=match.id).count() == 1
    requeue_enqueue.assert_not_called()


def test_null_etag_allows_club_admin_process_and_failed_job_requeue(club_app, client):
    program_id = club_app.c2["program_a"]
    match = _match(program_id)
    match.blob_etag = None
    db.session.commit()
    current = {"ok": True, "etag": "legacy-current-etag", "size_bytes": 2048}

    with (
        patch("src.services.video_storage.verify_uploaded_blob", return_value=current) as verify,
        patch("src.routes.video.video_queue.enqueue", return_value="fixture") as enqueue,
    ):
        club_response = client.post(
            f"/api/club/{program_id}/matches/{match.id}/process",
            headers=_headers("a"),
        )
        assert club_response.status_code == 202

        admin_response = client.post(
            f"/api/admin/video/matches/{match.id}/process",
            headers=_admin_headers(),
        )
        assert admin_response.status_code == 202

        job = VideoAnalysisJob.query.filter_by(video_match_id=match.id).one()
        job.status = "failed"
        match.status = "failed"
        db.session.commit()

        requeue_response = client.post(
            f"/api/admin/video/matches/{match.id}/requeue",
            headers=_admin_headers(),
        )
        assert requeue_response.status_code == 202

    assert verify.call_count == 3
    assert enqueue.call_count == 2
    assert VideoAnalysisJob.query.filter_by(video_match_id=match.id).count() == 2


def test_upload_complete_reattestation_clears_processing_request_for_club_and_admin(club_app, client):
    program_id = club_app.c2["program_a"]
    manager_id = club_app.c2["users"]["a"]
    match = _match(program_id)
    match.processing_requested_at = datetime.now(UTC)
    match.processing_requested_by_user_id = manager_id
    db.session.commit()
    verified = {"ok": True, "etag": "reattested-etag", "size_bytes": 2048}

    with (
        patch("src.services.video_storage.is_configured", return_value=True),
        patch("src.services.video_storage.verify_uploaded_blob", return_value=verified),
    ):
        club_response = client.post(
            f"/api/club/{program_id}/matches/{match.id}/upload-complete",
            json={},
            headers=_headers("a"),
        )
        assert club_response.status_code == 200
        refreshed = db.session.get(VideoMatch, match.id)
        assert refreshed.processing_requested_at is None
        assert refreshed.processing_requested_by_user_id is None

        refreshed.processing_requested_at = datetime.now(UTC)
        refreshed.processing_requested_by_user_id = manager_id
        db.session.commit()
        admin_response = client.post(
            f"/api/admin/video/matches/{match.id}/upload-complete",
            json={},
            headers=_admin_headers(),
        )
        assert admin_response.status_code == 200

    refreshed = db.session.get(VideoMatch, match.id)
    assert refreshed.processing_requested_at is None
    assert refreshed.processing_requested_by_user_id is None


def test_finalize_snapshot_excludes_departed_and_never_rostered_players(club_app, client):
    a = club_app.c2["program_a"]
    included = _add_api_member(client, a, 7001)
    departed = _add_api_member(client, a, 7002)
    match = _match(a, status="needs_tagging")
    rows = [
        VideoRosterEntry(
            video_match_id=match.id,
            player_name="Known Academy Player",
            jersey_number=8,
            tracked_player_id=TrackedPlayer.query.filter_by(player_api_id=7001).first().id,
            club_roster_member_id=included,
        ),
        VideoRosterEntry(
            video_match_id=match.id,
            player_name="Departed Player",
            jersey_number=9,
            tracked_player_id=TrackedPlayer.query.filter_by(player_api_id=7002).first().id,
            club_roster_member_id=departed,
        ),
        VideoRosterEntry(
            video_match_id=match.id,
            player_name="Never Rostered",
            jersey_number=10,
            club_roster_member_id=None,
        ),
    ]
    db.session.add_all(rows)
    db.session.commit()
    assert client.delete(f"/api/club/{a}/roster/{departed}", headers=_headers("a")).status_code == 204
    finalized = client.post(f"/api/admin/video/matches/{match.id}/finalize", headers=_admin_headers())
    assert finalized.status_code == 200, finalized.get_json()
    report = client.get(f"/api/club/{a}/matches/{match.id}/report", headers=_headers("a"))
    assert report.status_code == 200
    assert [row["subject"]["player_api_id"] for row in report.get_json()["reports"]] == [7001]


def test_report_denies_cross_club_and_hides_suppressed_or_merged_identity(club_app, client):
    a = club_app.c2["program_a"]
    b = club_app.c2["program_b"]
    match = _match(a, status="finalized")
    entry = VideoRosterEntry(video_match_id=match.id, player_name="Known", jersey_number=8)
    db.session.add(entry)
    db.session.flush()
    report = VideoPlayerReport(
        video_match_id=match.id,
        roster_entry_id=entry.id,
        tracked_player_id=None,
        club_program_id_at_finalize=a,
        club_roster_member_id_at_finalize=123,
        club_player_api_id_at_finalize=7001,
        minutes_visible=20,
        model_version="c2-test",
    )
    db.session.add(report)
    db.session.commit()
    assert client.get(f"/api/club/{b}/matches/{match.id}/report", headers=_headers("a")).status_code == 403
    assert client.get(f"/api/club/{a}/matches/{match.id + 100}/report", headers=_headers("a")).status_code == 404
    assert len(client.get(f"/api/club/{a}/matches/{match.id}/report", headers=_headers("a")).get_json()["reports"]) == 1
    _active_suppression(player_api_id=7001)
    hidden = client.get(f"/api/club/{a}/matches/{match.id}/report", headers=_headers("a"))
    assert hidden.get_json()["reports"] == []


def test_report_hides_local_identity_merged_after_finalize(club_app, client):
    a = club_app.c2["program_a"]
    local = _local(club_app.c2["users"]["a"], birth_year=2000, status="approved")
    target = _local(club_app.c2["users"]["a"], name="Merged Target", birth_year=2000, status="approved")
    match = _match(a, status="finalized")
    entry = VideoRosterEntry(video_match_id=match.id, player_name=local.display_name, jersey_number=5)
    db.session.add(entry)
    db.session.flush()
    db.session.add(
        VideoPlayerReport(
            video_match_id=match.id,
            roster_entry_id=entry.id,
            club_program_id_at_finalize=a,
            club_roster_member_id_at_finalize=987,
            club_local_player_id_at_finalize=local.id,
            model_version="c2-test",
        )
    )
    db.session.commit()
    before = client.get(f"/api/club/{a}/matches/{match.id}/report", headers=_headers("a"))
    assert len(before.get_json()["reports"]) == 1
    local.status = "merged"
    local.merged_into_local_player_id = target.id
    db.session.commit()
    after = client.get(f"/api/club/{a}/matches/{match.id}/report", headers=_headers("a"))
    assert after.get_json()["reports"] == []


def test_roster_membership_does_not_change_contact_routing(club_app, client):
    a = club_app.c2["program_a"]
    claim = PlayerProfileClaim(
        player_api_id=7001,
        user_account_id=club_app.c2["users"]["scout"],
        relationship_type="player",
        contract_status="free_agent",
        status="approved",
    )
    db.session.add(claim)
    db.session.commit()
    before = routing_mode_for_claim(claim, platform_belief="free_agent")
    _add_api_member(client, a, 7001)
    db.session.refresh(claim)
    after = routing_mode_for_claim(claim, platform_belief="free_agent")
    assert before == after == "direct"
    assert claim.club_program_id is None


def test_local_takedown_hides_public_roster_and_finalized_report(club_app, client):
    a = club_app.c2["program_a"]
    local = _local(club_app.c2["users"]["a"], birth_year=2000, status="approved")
    member = client.post(
        f"/api/club/{a}/roster",
        json={"local_player_id": local.id},
        headers=_headers("a"),
    ).get_json()["member"]
    match = _match(a, status="finalized")
    entry = VideoRosterEntry(
        video_match_id=match.id,
        player_name=local.display_name,
        jersey_number=11,
        club_roster_member_id=member["id"],
    )
    db.session.add(entry)
    db.session.flush()
    db.session.add(
        VideoPlayerReport(
            video_match_id=match.id,
            roster_entry_id=entry.id,
            club_program_id_at_finalize=a,
            club_roster_member_id_at_finalize=member["id"],
            club_local_player_id_at_finalize=local.id,
            model_version="c2-test",
        )
    )
    db.session.commit()
    request_response = client.post(
        f"/api/local-players/{local.id}/takedown-request",
        json={
            "requester_role": "player",
            "contact_email": "local-player@c2.example",
            "statement": "Please remove my local profile.",
        },
    )
    assert request_response.status_code == 202
    suppression = PlayerSuppression.query.filter_by(local_player_id=local.id).one()
    activated = client.post(
        f"/api/admin/suppressions/{suppression.id}/activate",
        json={"notes": "Identity verified for C2 test"},
        headers=_admin_headers(),
    )
    assert activated.status_code == 200
    assert client.get(f"/api/local-players/{local.id}").status_code == 404
    roster = client.get(f"/api/club/{a}/roster", headers=_headers("a")).get_json()["members"]
    assert roster == [
        {
            "available": False,
            "brief": {"body": None, "updated_at": None},
            "created_at": roster[0]["created_at"],
            "id": member["id"],
            "note": None,
            "program_id": a,
            "role": None,
        }
    ]
    assert client.get(f"/api/club/{a}/matches/{match.id}/report", headers=_headers("a")).get_json()["reports"] == []


def test_migration_chains_from_ob01_guards_rls_xor_and_downgrade_data(club_app):
    source = (Path(__file__).resolve().parents[1] / "migrations/versions/c201_club_console_backend.py").read_text()
    assert 'revision = "c201"' in source
    assert 'down_revision = "ob01"' in source
    assert "table_exists(ROSTER_TABLE)" in source
    assert "ck_club_roster_member_subject_xor" in source
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "pg_advisory_xact_lock" not in source
    assert "downgrade refused: club roster membership exists" in source
    assert "downgrade refused: club-owned video matches exist" in source
    assert "downgrade refused: local-player suppression history exists" in source


def test_list_club_matches_is_program_scoped_and_newest_first(club_app, client):
    a = club_app.c2["program_a"]
    b = club_app.c2["program_b"]
    first = _match(a, status="uploaded")
    second = _match(a, status="finalized")
    other = _match(b, status="uploaded")

    response = client.get(f"/api/club/{a}/matches", headers=_headers("a"))
    assert response.status_code == 200, response.get_json()
    body = response.get_json()
    assert body["total"] == 2
    assert [row["id"] for row in body["matches"]] == [second.id, first.id]
    assert body["matches"][0]["status"] == "finalized"
    assert body["matches"][0]["processing_request_status"] is None
    assert "job" in body["matches"][0]
    assert "roster" not in body["matches"][0]
    assert other.id not in [row["id"] for row in body["matches"]]

    response_b = client.get(f"/api/club/{b}/matches", headers=_headers("b"))
    assert response_b.status_code == 200
    assert [row["id"] for row in response_b.get_json()["matches"]] == [other.id]

    assert client.get(f"/api/club/{a}/matches").status_code == 401


def _reel_evidence(program_id: int, member_id: int) -> tuple[VideoMatch, VideoRosterEntry, VideoTracklet]:
    match = _match(program_id, status="finalized")
    entry = VideoRosterEntry(
        video_match_id=match.id,
        player_name="Known Academy Player",
        jersey_number=8,
        position="Midfielder",
        club_roster_member_id=member_id,
    )
    db.session.add(entry)
    db.session.flush()
    tracklet = VideoTracklet(
        video_match_id=match.id,
        kind="chain",
        pipeline_key="T0#8",
        team_cluster=0,
        confidence="high",
        first_s=10,
        last_s=16,
        visible_s=6,
        roster_entry_id=entry.id,
        thumbnail_paths=["crop-8.jpg"],
    )
    db.session.add(tracklet)
    db.session.commit()
    return match, entry, tracklet


def test_club_manager_gets_scoped_media_token_and_filtered_reel(club_app, client):
    a = club_app.c2["program_a"]
    b = club_app.c2["program_b"]
    member_id = _add_api_member(client, a)
    match, _entry, _tracklet = _reel_evidence(a, member_id)

    token_response = client.get(f"/api/club/{a}/matches/{match.id}/media-token", headers=_headers("a"))
    assert token_response.status_code == 200
    token = token_response.get_json()["token"]
    claims = media_token_claims(token, match.id)
    assert claims["club_program_id"] == a
    assert claims["email"] == "manager-a@c2.example"

    reel = client.get(f"/api/club/{a}/matches/{match.id}/reel", headers=_headers("a"))
    assert reel.status_code == 200
    assert [(row["player_name"], row["jersey_number"]) for row in reel.get_json()["players"]] == [
        ("Known Academy Player", 8)
    ]

    for path in ("media-token", "reel"):
        foreign = client.get(f"/api/club/{b}/matches/{match.id}/{path}", headers=_headers("b"))
        assert foreign.status_code == 404
        assert foreign.get_json() == {"error": "Match not found"}

    _active_suppression(player_api_id=7001)
    hidden = client.get(f"/api/club/{a}/matches/{match.id}/reel", headers=_headers("a"))
    assert hidden.status_code == 200
    assert hidden.get_json()["players"] == []


def test_coach_brief_sentinel_never_leaks_into_match_or_learning_payloads(club_app, client, monkeypatch):
    from src.routes import video as video_routes

    sentinel = "SENTINEL_BRIEF_7f3a"
    program_id = club_app.c2["program_a"]
    member_id = _add_api_member(client, program_id)
    match, _entry, _tracklet = _reel_evidence(program_id, member_id)
    monkeypatch.setattr(video_routes.video_dev_artifacts, "local_artifacts", lambda loaded: None)

    member_write = client.put(
        f"/api/club/{program_id}/roster/{member_id}/brief",
        json={"body": sentinel},
        headers=_headers("a"),
    )
    system_write = client.put(
        f"/api/club/{program_id}/system-brief",
        json={"body": sentinel},
        headers=_headers("a"),
    )
    assert member_write.status_code == 200
    assert system_write.status_code == 200

    responses = {
        "admin match": client.get(f"/api/admin/video/matches/{match.id}", headers=_admin_headers()),
        "feedback export": client.get(
            f"/api/admin/video/matches/{match.id}/feedback-export",
            headers=_admin_headers(),
        ),
        "training manifest": client.get(
            f"/api/admin/video/matches/{match.id}/training-manifest",
            headers=_admin_headers(),
        ),
        "admin report": client.get(f"/api/admin/video/matches/{match.id}/report", headers=_admin_headers()),
        "club match": client.get(
            f"/api/club/{program_id}/matches/{match.id}",
            headers=_headers("a"),
        ),
        "club match list": client.get(f"/api/club/{program_id}/matches", headers=_headers("a")),
        "club report": client.get(
            f"/api/club/{program_id}/matches/{match.id}/report",
            headers=_headers("a"),
        ),
        "club reel": client.get(
            f"/api/club/{program_id}/matches/{match.id}/reel",
            headers=_headers("a"),
        ),
        "admin reel": client.get(
            f"/api/admin/video/matches/{match.id}/reel",
            headers=_admin_headers(),
        ),
    }
    for label, response in responses.items():
        assert response.status_code == 200, (label, response.get_data(as_text=True))
        assert sentinel not in response.get_data(as_text=True), label


def test_club_media_token_streams_owned_footage_and_bbox_then_fails_closed_after_reassignment(
    club_app, client, monkeypatch, tmp_path
):
    from src.routes import video as video_routes

    a = club_app.c2["program_a"]
    b = club_app.c2["program_b"]
    member_id = _add_api_member(client, a)
    match, _entry, tracklet = _reel_evidence(a, member_id)
    other = _match(b, status="finalized")
    footage = tmp_path / "owned-match.mp4"
    footage.write_bytes(b"test-video-bytes")
    monkeypatch.setattr(video_routes.video_dev_artifacts, "local_artifacts", lambda loaded: {"footage": str(footage)})
    monkeypatch.setattr(
        video_routes.video_dev_artifacts,
        "tracklet_bbox_track",
        lambda loaded_tracklet, _art: [[10.0, 1.0, 2.0, 3.0, 4.0]],
    )

    token = client.get(
        f"/api/club/{a}/matches/{match.id}/media-token",
        headers=_headers("a"),
    ).get_json()["token"]

    footage_response = client.get(f"/api/admin/video/matches/{match.id}/footage", query_string={"token": token})
    assert footage_response.status_code == 200
    bbox_response = client.get(
        f"/api/admin/video/matches/{match.id}/tracklets/{tracklet.id}/bbox-track",
        query_string={"token": token},
    )
    assert bbox_response.status_code == 200
    assert bbox_response.get_json() == {"available": True, "boxes": [[10.0, 1.0, 2.0, 3.0, 4.0]]}

    assert (
        client.get(
            f"/api/admin/video/matches/{other.id}/footage",
            query_string={"token": token},
        ).status_code
        == 403
    )

    match.club_program_id = b
    db.session.commit()
    for path in (
        f"/api/admin/video/matches/{match.id}/footage",
        f"/api/admin/video/matches/{match.id}/tracklets/{tracklet.id}/bbox-track",
    ):
        denied = client.get(path, query_string={"token": token})
        assert denied.status_code == 404
        assert denied.get_json() == {"error": "match not found"}


def test_admin_media_and_reel_paths_remain_dual_auth_gated(club_app, client, monkeypatch):
    from src.routes import video as video_routes

    a = club_app.c2["program_a"]
    member_id = _add_api_member(client, a)
    match, _entry, tracklet = _reel_evidence(a, member_id)
    monkeypatch.setattr(video_routes.video_dev_artifacts, "local_artifacts", lambda loaded: None)

    token_response = client.get(f"/api/admin/video/matches/{match.id}/media-token", headers=_admin_headers())
    assert token_response.status_code == 200
    assert "club_program_id" not in media_token_claims(token_response.get_json()["token"], match.id)
    assert client.get(f"/api/admin/video/matches/{match.id}/reel", headers=_admin_headers()).status_code == 200
    assert (
        client.get(
            f"/api/admin/video/matches/{match.id}/tracklets/{tracklet.id}/crops",
            headers=_admin_headers(),
        ).status_code
        == 200
    )
    assert (
        client.get(
            f"/api/admin/video/matches/{match.id}/tracklets/{tracklet.id}/bbox-track",
            headers=_admin_headers(),
        ).status_code
        == 200
    )
    assert client.get(f"/api/admin/video/matches/{match.id}/reel").status_code == 401
