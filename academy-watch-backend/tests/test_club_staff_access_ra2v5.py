# ruff: noqa: F401, F811
"""RA2V5 regressions: "all squads" on a coach/analyst/viewer is a squad list, never whole-club (synthetic data only).

An all-squads scoped grant resolves to the club's CURRENT squads per request and runs every scoped
gate: no unassigned players, no legacy / unlabelled / mixed-with-unassigned recordings, footage
signed for the verified snapshot only, workflow-only DTOs, viewer redaction. Owner/manager are
unchanged (whole-club).
"""

from urllib.parse import parse_qs, urlsplit

import pytest
from flask import g
from src.models.funding import ClubSquad
from src.models.league import db
from src.models.video import VideoMatch
from src.services import club_access as access_service
from src.services import video_storage
from test_club_console import _add_local_member, _local
from test_club_staff_access import _email, _h, _headers, _join, _match, client, club_app, env
from test_club_staff_access_coverage import _make_legacy, _move, _put

SCOPED = ["coach", "analyst", "viewer"]
WORKFLOW = {"id", "club_program_id", "squad_id", "opponent_name", "match_date", "competition", "status"}


def _local_member(env, client, club_app, name, squad_key=None):
    local = _local(club_app.c2["users"]["a"], name=name, birth_year=2004, status="approved")
    member = _add_local_member(client, env["pid"], local.id)
    if squad_key is not None:
        _move(client, env, member, squad_key)
    return member, -local.id


def _unlabelled(client, env):
    resp = client.post(f"{env['base']}/matches", json={"opponent_name": "Fictional Mixed XI"}, headers=_headers("a"))
    assert resp.status_code == 201, resp.get_json()
    from test_club_staff_access import _complete_upload

    _complete_upload(resp.get_json()["id"])
    return resp.get_json()["id"]


def _world(env, client, club_app, monkeypatch):
    """Two good squad recordings plus the three kinds an all-squads scoped role must never open."""
    monkeypatch.setattr(video_storage, "is_configured", lambda: True)
    monkeypatch.setattr(video_storage, "mint_upload_sas", lambda path: {"upload_url": "https://example.invalid/upload"})
    unassigned, unassigned_signed = _local_member(env, client, club_app, "SYNTHETIC unassigned player")
    leaver, _ = _local_member(env, client, club_app, "SYNTHETIC leaver", "sa")
    good_a = _match(client, env, "sa")
    good_b = _match(client, env, "sb")
    legacy = _match(client, env, "sa")
    mixed = _match(client, env, "sa")
    for mid, members in ((good_a, ["m1"]), (good_b, ["m2"]), (legacy, ["m1"])):
        assert _put(client, env, mid, [env[m] for m in members]).status_code == 200
    assert _put(client, env, mixed, [env["m1"], leaver]).status_code == 200
    _make_legacy(legacy)
    # The leaver drops out of every squad: the recording now covers an unassigned player.
    resp = client.patch(f"{env['base']}/roster/{leaver}", json={"squad_id": None}, headers=_headers("a"))
    assert resp.status_code == 200, resp.get_json()
    return {
        "unassigned": unassigned,
        "unassigned_signed": unassigned_signed,
        "leaver": leaver,
        "good": {good_a, good_b},
        "good_a": good_a,
        "closed": {"legacy": legacy, "unlabelled": _unlabelled(client, env), "mixed": mixed},
    }


def _signer(monkeypatch):
    signed = []

    def sign(path, **kw):
        signed.append(kw.get("snapshot"))
        suffix = f"?snapshot={kw['snapshot']}" if kw.get("snapshot") else ""
        return f"https://example.invalid/{path}{suffix}"

    monkeypatch.setattr(video_storage, "mint_media_read_sas", sign)
    return signed


@pytest.mark.parametrize("role", SCOPED)
def test_all_squads_scoped_role_is_never_whole_club(env, client, club_app, monkeypatch, role):
    world = _world(env, client, club_app, monkeypatch)
    joined = _join(client, env, role, role, all_squads=True)["access"]
    assert joined["whole_club"] is False and joined["all_squads"] is True
    assert joined["squad_ids"] == sorted([env["sa"], env["sb"]])
    h = _h(_email(role))
    base = env["base"]
    me = client.get(f"{base}/access/me", headers=h).json["access"]
    assert me["whole_club"] is False and me["all_squads"] is True and me["squad_ids"] == joined["squad_ids"]

    # Players: every squad's players, never the unassigned ones.
    roster = client.get(f"{base}/roster", headers=h).json
    assert {m["id"] for m in roster["members"]} == {env["m1"], env["m2"]}
    assert client.get(f"{base}/roster?squad_id=none", headers=h).json["members"] == []
    for hidden in (world["unassigned"], world["leaver"]):
        assert client.get(f"{base}/roster/{hidden}/profile", headers=h).status_code == 404
    for squad_key, member in (("sa", "m1"), ("sb", "m2")):
        listed = client.get(f"{base}/roster?squad_id={env[squad_key]}", headers=h).json["members"]
        assert [m["id"] for m in listed] == [env[member]]
        assert client.get(f"{base}/roster/{env[member]}/profile", headers=h).status_code == 200
    home = client.get(f"{base}/map", headers=h).json
    assert home["unassigned_count"] == 0 and {s["id"] for s in home["squads"]} == {env["sa"], env["sb"]}
    assert {s["id"] for s in client.get(f"{base}/squads", headers=h).json["squads"]} == {env["sa"], env["sb"]}
    # Viewer redaction still applies (private coaching briefs stay with staff who coach).
    assert all(("brief" in m) == (role != "viewer") for m in roster["members"])
    if role == "viewer":
        assert not roster["system_brief"]["body"]

    # Recordings: both squads' covered recordings, none of the managers-only kinds.
    listing = client.get(f"{base}/matches", headers=h).json["matches"]
    assert {m["id"] for m in listing} == world["good"]
    signed = _signer(monkeypatch)
    for mid in world["good"]:
        assert client.get(f"{base}/matches/{mid}", headers=h).status_code == 200
        token = client.get(f"{base}/matches/{mid}/media-token", headers=h)
        assert token.status_code == 200, token.json
        footage = client.get(f"/api/admin/video/matches/{mid}/footage?token={token.json['token']}")
        assert footage.status_code == 302
        # Snapshot-only signing: never the mutable base blob.
        assert parse_qs(urlsplit(footage.headers["Location"]).query)["snapshot"] == ["snap-fixture-etag"]
    assert signed == ["snap-fixture-etag", "snap-fixture-etag"]
    for kind, mid in world["closed"].items():
        for suffix in ("", "/media-token", "/reel", "/report"):
            resp = client.get(f"{base}/matches/{mid}{suffix}", headers=h)
            assert resp.status_code == 404, (kind, suffix, resp.status_code)

    # Writes stay inside the scoped rules: a squad label is required, unassigned players are refused.
    if role != "viewer":
        assert client.post(f"{base}/matches", json={"opponent_name": "No squad"}, headers=h).status_code == 400
        created = client.post(f"{base}/matches", json={"opponent_name": "New", "squad_id": env["sb"]}, headers=h)
        assert created.status_code == 201 and set(created.json) <= WORKFLOW | {"upload", "upload_unavailable"}
        new = created.json["id"]
        entries = [{"club_roster_member_id": world["unassigned"], "jersey_number": 9}]
        refused = client.put(f"{base}/matches/{new}/roster", json={"entries": entries}, headers=h)
        assert refused.status_code in (400, 404, 422), refused.json
        # In progress: workflow DTO only, and no footage-derived data.
        detail = client.get(f"{base}/matches/{new}", headers=h)
        assert set(detail.json) <= WORKFLOW | {"roster", "processing_request_status"}
        assert client.get(f"{base}/matches/{new}/media-token", headers=h).status_code == 404
    else:
        assert client.post(f"{base}/matches", json={"squad_id": env["sa"]}, headers=h).status_code == 403

    # Service-level actor re-check: squad players yes, unassigned players no.
    with club_app.test_request_context():
        g.user_id = env["users"][role]
        allowed = access_service.club_actor_allowed
        assert allowed(db.session, env["pid"], g.user_id, "players.view", subject_signed_id=7001)
        assert allowed(db.session, env["pid"], g.user_id, "players.view", subject_signed_id=7002)
        assert not allowed(
            db.session, env["pid"], g.user_id, "players.view", subject_signed_id=world["unassigned_signed"]
        )


@pytest.mark.parametrize("role", SCOPED)
def test_all_squads_token_dies_when_recording_leaves_the_scoped_rule(env, client, club_app, monkeypatch, role):
    """A token minted while the recording was open never yields a base-blob SAS once it is managers-only."""
    world = _world(env, client, club_app, monkeypatch)
    _join(client, env, role, role, all_squads=True)
    h = _h(_email(role))
    mid = world["good_a"]
    token = client.get(f"{env['base']}/matches/{mid}/media-token", headers=h).json["token"]
    signed = _signer(monkeypatch)
    _make_legacy(mid)
    assert client.get(f"/api/admin/video/matches/{mid}/footage?token={token}").status_code == 404
    for suffix in ("crops/e1_1.jpg", "tracklets/999/crops", "tracklets/999/bbox-track"):
        assert client.get(f"/api/admin/video/matches/{mid}/{suffix}?token={token}").status_code == 404
    assert signed == []
    assert client.get(f"{env['base']}/matches/{mid}/media-token", headers=h).status_code == 404


@pytest.mark.parametrize("role", SCOPED)
def test_squad_created_after_the_grant_is_in_scope(env, client, club_app, monkeypatch, role):
    world = _world(env, client, club_app, monkeypatch)
    _join(client, env, role, role, all_squads=True)
    h = _h(_email(role))
    base = env["base"]
    made = client.post(f"{base}/squads", json={"name": "Squad C", "kind": "other"}, headers=_headers("a"))
    assert made.status_code == 201, made.json
    env["sc"] = made.json["squad"]["id"]
    _move(client, env, world["unassigned"], "sc")
    late = _match(client, env, "sc")
    assert _put(client, env, late, [world["unassigned"]]).status_code == 200

    assert env["sc"] in client.get(f"{base}/access/me", headers=h).json["access"]["squad_ids"]
    assert world["unassigned"] in {m["id"] for m in client.get(f"{base}/roster", headers=h).json["members"]}
    assert client.get(f"{base}/roster/{world['unassigned']}/profile", headers=h).status_code == 200
    assert env["sc"] in {s["id"] for s in client.get(f"{base}/squads", headers=h).json["squads"]}
    assert {m["id"] for m in client.get(f"{base}/matches", headers=h).json["matches"]} == world["good"] | {late}
    assert client.get(f"{base}/matches/{late}/media-token", headers=h).status_code == 200
    # Still not whole-club afterwards.
    for mid in world["closed"].values():
        assert client.get(f"{base}/matches/{mid}", headers=h).status_code == 404


def test_all_squads_grant_in_a_club_without_squads_sees_nothing(env, client, club_app):
    _join(client, env, "coach", "coach", all_squads=True)
    for member in (env["m1"], env["m2"]):
        resp = client.patch(f"{env['base']}/roster/{member}", json={"squad_id": None}, headers=_headers("a"))
        assert resp.status_code == 200, resp.get_json()
    ClubSquad.query.filter_by(program_id=env["pid"]).delete()
    db.session.commit()
    h = _h(_email("coach"))
    assert client.get(f"{env['base']}/access/me", headers=h).json["access"]["squad_ids"] == []
    assert client.get(f"{env['base']}/roster", headers=h).json["members"] == []
    assert client.get(f"{env['base']}/map", headers=h).json["unassigned_count"] == 0


@pytest.mark.parametrize("who", ["owner", "invited_manager"])
def test_owner_and_manager_stay_whole_club(env, client, club_app, monkeypatch, who):
    world = _world(env, client, club_app, monkeypatch)
    if who == "owner":
        h = _headers("a")
    else:
        _join(client, env, "invmgr", "manager")
        h = _h(_email("invmgr"))
    base = env["base"]
    me = client.get(f"{base}/access/me", headers=h).json["access"]
    assert me["whole_club"] is True and me["all_squads"] is True and me["squad_ids"] == []
    members = {m["id"] for m in client.get(f"{base}/roster", headers=h).json["members"]}
    assert members == {env["m1"], env["m2"], world["unassigned"], world["leaver"]}
    assert client.get(f"{base}/map", headers=h).json["unassigned_count"] == 2
    listed = {m["id"] for m in client.get(f"{base}/matches", headers=h).json["matches"]}
    assert listed == world["good"] | set(world["closed"].values())
    signed = _signer(monkeypatch)
    for mid in sorted(listed):
        token = client.get(f"{base}/matches/{mid}/media-token", headers=h)
        assert token.status_code == 200, (mid, token.json)
        footage = client.get(f"/api/admin/video/matches/{mid}/footage?token={token.json['token']}")
        assert footage.status_code == 302 and "snapshot" not in footage.headers["Location"]
    assert signed == [None] * len(listed)
    assert client.post(f"{base}/matches", json={"opponent_name": "Whole club"}, headers=h).status_code == 201
