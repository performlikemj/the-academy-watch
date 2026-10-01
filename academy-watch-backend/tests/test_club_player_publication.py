# ruff: noqa: F811
"""The club origin stays private unless every independent publication key is live."""

from datetime import date, datetime, timedelta

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
    from src.routes.api import api_bp

    club_app.register_blueprint(api_bp, url_prefix="/api")
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
    assert pid not in [r["player_id"] for r in results.get("players", [])]


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
        "shadow_minor",
        "birthday",
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
    elif which == "birthday":
        publication = ClubPlayerPublication.query.first()
        publication.adult_invited_at = datetime(2024, 1, 1)
        publication.consented_at = datetime(2024, 1, 1)
        local = db.session.get(LocalPlayer, env["local"])
        local.birth_date = date(date.today().year - 18, 1, 1)
    elif which == "shadow_minor":
        from src.models.follow import PlayerShadow

        PlayerShadow.query.filter_by(player_api_id=pid).first().birth_date = date(2015, 1, 1)
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


def surface_ids(client, env):
    import csv
    import io

    from src.models.follow import Follow, FollowList
    from src.services.follow_resolver import resolve_list
    from src.services.player_shadow_service import search_players
    from src.services.scout_digest_service import _player_state

    headers = _headers("scout")
    follow_list = FollowList.query.filter_by(name="C1 saved fixture").first()
    if follow_list is None:
        scout = UserAccount.query.filter_by(email="manager-scout@c2.example").one()
        follow_list = FollowList(user_account_id=scout.id, name="C1 saved fixture")
        db.session.add(follow_list)
        db.session.flush()
        db.session.commit()
    if public_adult_ids([-env["local"]]) and not follow_list.follows.first():
        db.session.add(
            Follow(
                list_id=follow_list.id, kind="player", selector={"player_api_id": -env["local"]}, label="Saved C1 adult"
            )
        )
        db.session.commit()
    pid = -env["local"]
    browse = client.get("/api/scout/players?search=C1").json
    compare = client.get(f"/api/scout/compare?ids={pid}")
    exported = client.get(f"/api/scout/export.csv?ids={pid}", headers=headers)
    global_search = client.get("/api/players/search?q=C1")
    embedded = client.get("/api/scout/lists", headers=headers)
    assert compare.status_code == exported.status_code == global_search.status_code == embedded.status_code == 200
    return {
        "browse": {r["player_id"] for r in browse["players"]},
        "compare": {r["profile"]["player_id"] for r in compare.json["players"]},
        "csv": {int(r["player_id"]) for r in csv.DictReader(io.StringIO(exported.get_data(as_text=True)))},
        "global_search": {r["player_api_id"] for r in global_search.json},
        "follow_search": {r["player_api_id"] for r in search_players("C1 adult")},
        "embedded": {r["selector"]["player_api_id"] for r in embedded.json["lists"][0]["follows"]},
        "resolved": {r["player_api_id"] for r in resolve_list(follow_list)},
        "digest": {pid} if _player_state(pid, {})["kind"] != "none" else set(),
    }


def test_all_public_surfaces_require_consent_and_remove_on_withdrawal(client, env, monkeypatch):
    # C1 admits club adults independently of the separate community inclusion flag.
    monkeypatch.setenv("SCOUT_INCLUDE_LOCAL_PLAYERS", "false")
    assert all(not ids for ids in surface_ids(client, env).values())
    row = published(client, env)
    pid = -env["local"]
    assert all(ids == {pid} for ids in surface_ids(client, env).values())
    assert (
        client.post(
            f"/api/me/player-publications/{row['id']}/withdraw",
            headers=env["ph"],
            json={"expected_version": row["version"]},
        ).status_code
        == 200
    )
    assert all(not ids for ids in surface_ids(client, env).values())


@pytest.mark.parametrize("case", ["expired", "not_self", "guardian", "duplicate", "namespace"])
def test_private_invite_fail_closed(client, env, case):
    from src.models.follow import PlayerShadow

    result = invite(client, env)
    row = ClubPlayerPublication.query.first()
    if case == "expired":
        row.invite_expires_at = service.now() - timedelta(seconds=1)
        db.session.commit()
    if case == "guardian":
        db.session.add(
            PlayerProfileClaim(
                local_player_id=env["local"],
                user_account_id=env["player"],
                relationship_type="guardian",
                status="approved",
            )
        )
        db.session.commit()
    response = client.post(
        "/api/me/player-publication-invites/accept",
        headers=env["ph"],
        json={"token": result["token"], "self_claim": case != "not_self"},
    )
    if case in {"expired", "not_self", "guardian"}:
        assert response.status_code == {"expired": 404, "not_self": 400, "guardian": 409}[case]
        assert not row.claimed_at
        return
    assert response.status_code == 200
    service.consent(
        row,
        env["player"],
        {"expected_version": row.version, "public_profile_consent": True, "consent_version": service.CONSENT_VERSION},
    )
    if case == "duplicate":
        local = db.session.get(LocalPlayer, env["local"])
        db.session.add(
            LocalPlayer(
                display_name=local.display_name,
                birth_date=local.birth_date,
                birth_year=local.birth_year,
                provenance="community",
            )
        )
    else:
        db.session.add(PlayerShadow(player_api_id=-env["local"], player_name="Conflicting legacy fixture"))
    db.session.commit()
    response = client.post(
        f"/api/admin/player-publications/{row.id}/review",
        headers=_admin_headers(),
        json={"action": "approve", "reason": "Review fixture", "expected_version": row.version},
    )
    assert response.status_code == 409
    assert not public_adult_ids([-env["local"]])


def test_export_erasure_and_introduction_notification_keys(client, env):
    from src.models.contact import ContactRequest
    from src.models.p2_foundation import NotificationOutbox
    from src.services.account import _SchemaView
    from src.services.club_player_publication_account import erase_publications, export_publications

    published(client, env)
    player = db.session.get(UserAccount, env["player"])
    schema = _SchemaView()
    exported = export_publications(player, schema)["club_player_publications"]
    assert "invite_token_hash" not in exported[0] and "recipient_email" not in exported[0]
    response = client.post(
        "/api/contact/requests",
        headers=_headers("scout"),
        json={"player_api_id": -env["local"], "message": "Test introduction"},
    )
    assert response.status_code == 201
    contact_id = response.json["contact_request"]["id"]
    notices = NotificationOutbox.query.filter_by(template="c1_introduction").all()
    assert notices and all(n.recipient_user_id != player.id and not n.payload for n in notices)
    assert (
        client.post(
            f"/api/contact/requests/{contact_id}/club-consent", headers=_headers("a"), json={"action": "grant"}
        ).status_code
        == 200
    )
    assert NotificationOutbox.query.filter_by(template="c1_introduction", recipient_user_id=player.id).count() == 1
    erase_publications(player.id, player.email, schema)
    db.session.commit()
    assert not ClubPlayerPublication.query.first()
    assert db.session.get(ContactRequest, contact_id).status == "withdrawn"
    assert not public_adult_ids([-env["local"]])


@pytest.mark.parametrize("spa", [False, True])
@pytest.mark.parametrize("method", ["GET", "HEAD", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
@pytest.mark.parametrize(
    "path",
    [
        "/api/me/player-publications",
        "/api/me/player-publication-invites/accept",
        "/api/club/1/players/1/publication-invite",
        "/api/admin/player-publications/1/review",
        "/api/contact/requests/fixture/revoke",
    ],
)
def test_c1_dark_routing_matches_unknown_real_app(monkeypatch, tmp_path, spa, method, path):
    from src.main import app

    monkeypatch.setenv("CLUB_PLAYER_PUBLICATION_ENABLED", "false")
    monkeypatch.setattr(app, "static_folder", str(tmp_path))
    if spa:
        (tmp_path / "index.html").write_text("SPA shell")
    client = app.test_client()
    unknown_path = "/api/contact/not-a-real-c1-path" if path.startswith("/api/contact/") else "/api/not-a-real-c1-path"
    unknown = client.open(unknown_path, method=method)
    response = client.open(path, method=method)
    assert (response.status_code, response.data, dict(response.headers)) == (
        unknown.status_code,
        unknown.data,
        dict(unknown.headers),
    )


def test_publication_permissions_stale_versions_and_token_rotation(client, env):
    path = f"/api/club/{env['pid']}/players/{env['local']}/publication-invite"
    assert client.post(path, json={"recipient_email": "adult@c1.example"}).status_code == 401
    assert client.post(path, headers=_headers("b"), json={"recipient_email": "adult@c1.example"}).status_code == 403
    first = invite(client, env)
    assert (
        client.post(
            path, headers=_headers("a"), json={"recipient_email": "adult@c1.example", "expected_version": 99}
        ).status_code
        == 409
    )
    rotated = client.post(
        path,
        headers=_headers("a"),
        json={"recipient_email": "adult@c1.example", "expected_version": first["publication"]["version"]},
    )
    assert rotated.status_code == 201
    assert (
        client.post(
            "/api/me/player-publication-invites/preview", headers=env["ph"], json={"token": first["token"]}
        ).status_code
        == 404
    )
    row = service.redeem(
        db.session.get(UserAccount, env["player"]), {"token": rotated.json["token"], "self_claim": True}
    )
    db.session.commit()
    assert (
        client.post(
            f"/api/admin/player-publications/{row.id}/review",
            headers=env["ph"],
            json={"action": "approve", "reason": "Fixture", "expected_version": row.version},
        ).status_code
        == 401
    )
    assert (
        client.post(
            f"/api/me/player-publications/{row.id}/withdraw", headers=env["ph"], json={"expected_version": 99}
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/api/club/{env['pid']}/players/99999999999999999999/publication-invite",
            headers=_headers("a"),
            json={"recipient_email": "adult@c1.example"},
        ).status_code
        == 400
    )


@pytest.mark.parametrize("change", ["withdraw", "positive_bridge", "shadow_minor"])
def test_cached_sitemap_rechecks_consent_and_all_identity_aliases(client, env, monkeypatch, change):
    import time

    from src.models.follow import PlayerShadow
    from src.services import sitemap_service

    monkeypatch.setenv("LEGACY_PUBLIC_PAGES", "true")
    row = published(client, env)
    url = f"https://theacademywatch.com/local-players/{env['local']}"
    xml = f'<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>{url}</loc></url></urlset>'.encode()
    monkeypatch.setattr(sitemap_service, "_cache", {"xml": xml, "built_at": time.monotonic()})
    assert url.encode() in client.get("/sitemap.xml").data
    if change == "withdraw":
        service.revoke(db.session.get(ClubPlayerPublication, row["id"]))
    elif change == "positive_bridge":
        db.session.get(LocalPlayer, env["local"]).api_player_id = 991122
    else:
        PlayerShadow.query.filter_by(player_api_id=-env["local"]).first().birth_date = date(2015, 1, 1)
    db.session.commit()
    assert url.encode() not in client.get("/sitemap.xml").data
    assert sitemap_service._cache["xml"] == xml
