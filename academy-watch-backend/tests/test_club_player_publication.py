# ruff: noqa: F811
"""The club origin stays private unless every independent publication key is live."""

from datetime import date, timedelta

import pytest
from src.auth import issue_user_token
from src.models.club_player_publication import ClubPlayerPublication
from src.models.funding import ClubProgram, ClubProgramManager, ClubRosterMember
from src.models.league import UserAccount, db
from src.models.showcase import LocalPlayer, PlayerProfileClaim
from src.models.trust import ScoutVerification
from src.routes.club_player_publication import publication_bp
from src.routes.contact import contact_bp
from src.routes.scout import scout_bp
from src.routes.share import share_bp
from src.services import club_player_publication as service
from src.services.player_subject import resolve_player_subject
from src.services.public_adult import public_adult_ids
from src.services.public_player_subject import resolve_public_adult_subject
from test_club_console import _admin_headers, _headers, client, club_app  # noqa: F401


@pytest.fixture
def env(club_app, client, monkeypatch):
    monkeypatch.setenv("CLUB_PLAYER_PUBLICATION_ENABLED", "true")
    monkeypatch.setenv("CONTACT_RAIL_ENABLED", "true")
    monkeypatch.setenv("SCOUT_INCLUDE_LOCAL_PLAYERS", "true")
    monkeypatch.setenv("P2_FOUNDATION_ENABLED", "true")
    monkeypatch.setenv("API_FOOTBALL_FROZEN", "true")
    monkeypatch.setenv("SCOUT_ENABLED", "true")
    from src.services.club_player_publication_account import register_publication_notifications

    register_publication_notifications()
    club_app.register_blueprint(publication_bp, url_prefix="/api")
    club_app.register_blueprint(contact_bp, url_prefix="/api")
    club_app.register_blueprint(scout_bp, url_prefix="/api")
    from pathlib import Path

    from jinja2 import FileSystemLoader

    club_app.jinja_loader = FileSystemLoader(str(Path(__file__).parents[1] / "src/templates"))
    club_app.register_blueprint(share_bp)
    from src.services import contact

    monkeypatch.setattr(contact, "send_club_consent_notice", lambda *args: None)
    import src.routes.contact as routes

    monkeypatch.setattr(routes, "send_club_consent_notice", lambda *args: None)
    pid = club_app.c2["program_a"]
    owner = club_app.c2["users"]["a"]
    player = UserAccount(email="adult@c1.example", display_name="Adult fixture", display_name_lower="adult fixture")
    db.session.add(player)
    local = LocalPlayer(
        display_name="C1 adult fixture",
        provenance="club",
        origin_program_id=pid,
        birth_date=date(2000, 1, 1),
        birth_year=2000,
        status="pending",
        club_name="Club A",
    )
    db.session.add(local)
    db.session.flush()
    local.api_player_id = -local.id
    db.session.add(ClubRosterMember(program_id=pid, local_player_id=local.id, added_by_user_id=owner))
    db.session.add(
        ScoutVerification(
            user_account_id=club_app.c2["users"]["scout"],
            full_name="Fixture scout",
            organization="Fixture recruitment",
            role_title="Scout",
            statement="Fixture verification",
            status="approved",
        )
    )
    db.session.commit()
    return {
        "pid": pid,
        "local": local.id,
        "player": player.id,
        "ph": {"Authorization": f"Bearer {issue_user_token(player.email)['token']}"},
    }


def invite(client, env):
    response = client.post(
        f"/api/club/{env['pid']}/players/{env['local']}/publication-invite",
        json={"recipient_email": "adult@c1.example"},
        headers=_headers("a"),
    )
    assert response.status_code == 201, response.json
    return response.json


def claimed(client, env):
    result = invite(client, env)
    response = client.post(
        "/api/me/player-publication-invites/accept",
        json={"token": result["token"], "self_claim": True},
        headers=env["ph"],
    )
    assert response.status_code == 200, response.json
    return response.json["publication"]


def consented(client, env):
    result = claimed(client, env)
    response = client.post(
        f"/api/me/player-publications/{result['id']}/consent",
        headers=env["ph"],
        json={
            "public_profile_consent": True,
            "consent_version": service.CONSENT_VERSION,
            "expected_version": result["version"],
        },
    )
    assert response.status_code == 200, response.json
    return response.json["publication"]


def published(client, env):
    result = consented(client, env)
    response = client.post(
        f"/api/admin/player-publications/{result['id']}/review",
        headers=_admin_headers(),
        json={
            "action": "approve",
            "reason": "Independent adult identity and consent checked",
            "expected_version": result["version"],
        },
    )
    assert response.status_code == 200, response.json
    assert response.json["publication"]["public"]
    return response.json["publication"]


def assert_private(client, env):
    pid = -env["local"]
    assert public_adult_ids([pid]) == set()
    assert resolve_player_subject(pid) is None
    assert resolve_public_adult_subject(pid) is None
    for path in [
        f"/api/local-players/{env['local']}",
        f"/api/local-players/{env['local']}/showcase",
        f"/api/players/{pid}/showcase",
        f"/p/{pid}",
        f"/p/{pid}/card.png",
    ]:
        assert client.get(path).status_code == 404, path
    assert (
        client.post("/api/scout/watchlist", json={"player_api_id": pid}, headers=_headers("scout")).status_code == 404
    )
    results = client.get("/api/scout/players?search=C1").json
    assert results is not None
    assert pid not in [r["player_api_id"] for r in results.get("players", [])]


@pytest.mark.parametrize("birth", [date(2010, 1, 1), date.today(), date.today() + timedelta(days=1), None])
def test_minor_or_unknown_never_invitable(client, env, birth):
    local = db.session.get(LocalPlayer, env["local"])
    local.birth_date = birth
    local.birth_year = None
    db.session.commit()
    response = client.post(
        f"/api/club/{env['pid']}/players/{env['local']}/publication-invite",
        json={"recipient_email": "adult@c1.example"},
        headers=_headers("a"),
    )
    assert response.status_code == 404
    assert ClubPlayerPublication.query.count() == 0


def test_claim_and_consent_are_independent(client, env):
    row = claimed(client, env)
    assert not row["consented"]
    assert_private(client, env)
    response = client.post(
        f"/api/admin/player-publications/{row['id']}/review",
        headers=_admin_headers(),
        json={"action": "approve", "reason": "Reviewed", "expected_version": row["version"]},
    )
    assert response.status_code == 409


def test_consent_waits_for_moderation(client, env):
    consented(client, env)
    assert_private(client, env)


def test_recipient_and_single_use_token(client, env):
    result = invite(client, env)
    for action in ("preview", "accept"):
        response = client.post(
            f"/api/me/player-publication-invites/{action}",
            json={"token": result["token"], "self_claim": True},
            headers=_headers("b"),
        )
        assert response.status_code == 404
    response = client.post(
        "/api/me/player-publication-invites/accept",
        json={"token": result["token"], "self_claim": True},
        headers=env["ph"],
    )
    assert response.status_code == 200
    assert (
        client.post(
            "/api/me/player-publication-invites/accept",
            json={"token": result["token"], "self_claim": True},
            headers=env["ph"],
        ).status_code
        == 404
    )
    assert ClubPlayerPublication.query.first().invite_token_hash is None


@pytest.mark.parametrize("key,value", [("public_profile_consent", False), ("consent_version", "old")])
def test_explicit_current_consent(client, env, key, value):
    row = claimed(client, env)
    data = {
        "public_profile_consent": True,
        "consent_version": service.CONSENT_VERSION,
        "expected_version": row["version"],
    }
    data[key] = value
    assert (
        client.post(f"/api/me/player-publications/{row['id']}/consent", headers=env["ph"], json=data).status_code == 400
    )


@pytest.mark.parametrize(
    "which",
    [
        "withdraw",
        "club_revoke",
        "flag_off",
        "hold",
        "manager_revoked",
        "claim_revoked",
        "minor",
        "roster_removed",
        "suspended",
    ],
)
def test_live_removal_from_all_reads(client, env, monkeypatch, which):
    row = published(client, env)
    pid = -env["local"]
    assert public_adult_ids([pid]) == {pid}
    assert client.get(f"/api/local-players/{env['local']}").status_code == 200
    assert client.get(f"/p/{pid}").status_code == 200
    assert client.post("/api/scout/watchlist", json={"player_api_id": pid}, headers=_headers("scout")).status_code in (
        200,
        201,
    )
    if which == "withdraw":
        assert (
            client.post(
                f"/api/me/player-publications/{row['id']}/withdraw",
                json={"expected_version": row["version"]},
                headers=env["ph"],
            ).status_code
            == 200
        )
    elif which == "club_revoke":
        assert (
            client.post(
                f"/api/club/{env['pid']}/player-publications/{row['id']}/revoke",
                json={"expected_version": row["version"]},
                headers=_headers("a"),
            ).status_code
            == 200
        )
    elif which == "flag_off":
        monkeypatch.setenv("CLUB_PLAYER_PUBLICATION_ENABLED", "false")
    elif which == "hold":
        db.session.get(ClubProgram, env["pid"]).emergency_hidden = True
    elif which == "manager_revoked":
        ClubProgramManager.query.filter_by(program_id=env["pid"]).first().status = "revoked"
    elif which == "claim_revoked":
        db.session.get(PlayerProfileClaim, ClubPlayerPublication.query.first().claim_id).status = "revoked"
    elif which == "minor":
        db.session.get(LocalPlayer, env["local"]).birth_date = date(2010, 1, 1)
    elif which == "roster_removed":
        ClubRosterMember.query.filter_by(local_player_id=env["local"]).delete()
    elif which == "suspended":
        db.session.get(UserAccount, env["player"]).account_status = "suspended"
    db.session.commit()
    assert_private(client, env)
    assert client.get("/api/scout/watchlist", headers=_headers("scout")).json["entries"] == []


def test_strict_club_first_even_when_claim_says_free_agent(client, env):
    row = published(client, env)
    claim = db.session.get(PlayerProfileClaim, ClubPlayerPublication.query.first().claim_id)
    claim.contract_status = "free_agent"
    db.session.commit()
    response = client.post(
        "/api/contact/requests",
        headers=_headers("scout"),
        json={"player_api_id": -env["local"], "message": "Please introduce us"},
    )
    assert response.status_code == 201, response.json
    contact = response.json["contact_request"]
    id_ = contact["id"]
    assert contact["routing_mode"] == "club_included" and contact["club_first"]
    assert client.get("/api/contact/requests?box=inbox", headers=env["ph"]).json["requests"] == []
    assert client.get(f"/api/contact/requests/{id_}/messages", headers=env["ph"]).status_code == 404
    assert client.post(f"/api/contact/requests/{id_}/accept", headers=env["ph"]).status_code == 404
    assert (
        client.post(
            f"/api/contact/requests/{id_}/club-consent", headers=_headers("a"), json={"action": "grant"}
        ).status_code
        == 200
    )
    assert len(client.get("/api/contact/requests?box=inbox", headers=env["ph"]).json["requests"]) == 1
    assert (
        client.post(
            f"/api/contact/requests/{id_}/messages", headers=_headers("scout"), json={"body": "Premature"}
        ).status_code
        == 409
    )
    assert client.post(f"/api/contact/requests/{id_}/accept", headers=env["ph"]).status_code == 200
    assert (
        client.post(
            f"/api/contact/requests/{id_}/messages", headers=_headers("scout"), json={"body": "Hello"}
        ).status_code
        == 201
    )
    assert client.post(f"/api/contact/requests/{id_}/revoke", headers=env["ph"]).status_code == 200
    assert (
        client.post(
            f"/api/contact/requests/{id_}/messages", headers=_headers("scout"), json={"body": "After revocation"}
        ).status_code
        == 409
    )
