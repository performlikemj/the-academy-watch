# ruff: noqa: F811

"""RA2 security regressions for club staff access (from the reviewer's probes, assertions reversed).

All data fictional.
"""

from datetime import timedelta
from uuid import uuid4

import pytest
from src.models.club_access import ClubAccessGrant, ClubAccessGrantSquad
from src.models.funding import ClubProgram, ClubRosterMember
from src.models.league import db
from src.models.video import VideoMatch, VideoPlayerReport, VideoRosterEntry, VideoTracklet
from src.services import video_storage
from test_club_console import _add_api_member, _add_local_member, _local
from test_club_staff_access import _email, _h, _headers, _join, _match, client, club_app, env  # noqa: F401

PRIVATE_NOTE = "PRIVATE safeguarding and coaching note"


def _fake_storage(monkeypatch):
    monkeypatch.setattr(video_storage, "is_configured", lambda: True)
    monkeypatch.setattr(video_storage, "mint_media_read_sas", lambda path, **kw: "https://example.invalid/footage")


def _grant_id(env, key):
    return ClubAccessGrant.query.filter_by(program_id=env["pid"], user_account_id=env["users"][key]).one().id


def _minor_in_squad_b(client, club_app, env):
    minor_id = _local(club_app.c2["users"]["a"], name="PRIVATE Squad B minor", birth_year=2010).id
    member = _add_local_member(client, env["pid"], minor_id)
    assert (
        client.patch(f"{env['base']}/roster/{member}", json={"squad_id": env["sb"]}, headers=_headers("a")).status_code
        == 200
    )
    return member, minor_id


# ---------------------------------------------------------------------------
# 1. HIGH — a squad label never grants access to out-of-squad players
# ---------------------------------------------------------------------------


def test_labelled_match_rejects_out_of_squad_roster(env, client):
    mid = _match(client, env, "sa")
    # Even the owner cannot put a Squad B player into a match labelled Squad A.
    resp = client.put(
        f"{env['base']}/matches/{mid}/roster",
        json={"entries": [{"club_roster_member_id": env["m2"], "jersey_number": 7}]},
        headers=_headers("a"),
    )
    assert resp.status_code == 400 and "squad" in resp.get_json()["error"]
    # Mixed-squad matches stay whole-club: clear the label, then any club player may be added.
    assert (
        client.patch(f"{env['base']}/matches/{mid}", json={"squad_id": None}, headers=_headers("a")).status_code == 200
    )
    ok = client.put(
        f"{env['base']}/matches/{mid}/roster",
        json={
            "entries": [
                {"club_roster_member_id": env["m1"], "jersey_number": 7},
                {"club_roster_member_id": env["m2"], "jersey_number": 8},
            ]
        },
        headers=_headers("a"),
    )
    assert ok.status_code == 200
    # Relabelling a mixed match to one squad is refused.
    relabel = client.patch(f"{env['base']}/matches/{mid}", json={"squad_id": env["sa"]}, headers=_headers("a"))
    assert relabel.status_code == 400


def test_squad_a_cannot_read_minor_in_mixed_squad_match(env, client, club_app, monkeypatch):
    minor_member, minor_id = _minor_in_squad_b(client, club_app, env)
    mid = _match(client, env, "sa")
    # Legitimate path to a mixed state: roster is set while the minor is in Squad A, then they move squads.
    client.patch(f"{env['base']}/roster/{minor_member}", json={"squad_id": env["sa"]}, headers=_headers("a"))
    resp = client.put(
        f"{env['base']}/matches/{mid}/roster",
        json={"entries": [{"club_roster_member_id": minor_member, "jersey_number": 7}]},
        headers=_headers("a"),
    )
    assert resp.status_code == 200
    client.patch(f"{env['base']}/roster/{minor_member}", json={"squad_id": env["sb"]}, headers=_headers("a"))
    entry = VideoRosterEntry.query.filter_by(video_match_id=mid).one()
    db.session.get(VideoMatch, mid).status = "finalized"
    db.session.add(
        VideoTracklet(
            video_match_id=mid,
            pipeline_key="minor-chain",
            kind="chain",
            roster_entry_id=entry.id,
            tag_source="human",
            first_s=0,
            last_s=10,
            visible_s=10,
        )
    )
    db.session.add(
        VideoPlayerReport(
            video_match_id=mid,
            roster_entry_id=entry.id,
            club_program_id_at_finalize=env["pid"],
            club_roster_member_id_at_finalize=minor_member,
            club_local_player_id_at_finalize=minor_id,
            identity_confidence="human_confirmed",
            minutes_visible=15,
            model_version="ra2-test",
        )
    )
    db.session.commit()
    _join(client, env, "coach", "coach", squads=[env["sa"]])
    h = _h(_email("coach"))
    assert client.get(f"{env['base']}/roster/{minor_member}/profile", headers=h).status_code == 404
    for path in (f"matches/{mid}", f"matches/{mid}/report", f"matches/{mid}/reel", f"matches/{mid}/media-token"):
        resp = client.get(f"{env['base']}/{path}", headers=h)
        assert resp.status_code == 404, path
        assert "PRIVATE Squad B minor" not in resp.get_data(as_text=True)
    listed = client.get(f"{env['base']}/matches", headers=h).get_json()["matches"]
    assert mid not in [m["id"] for m in listed]
    # A token minted while the roster was in scope stops working once it isn't.
    _fake_storage(monkeypatch)
    client.patch(f"{env['base']}/roster/{minor_member}", json={"squad_id": env["sa"]}, headers=_headers("a"))
    token = client.get(f"{env['base']}/matches/{mid}/media-token", headers=h).get_json()["token"]
    assert client.get(f"/api/admin/video/matches/{mid}/footage?token={token}").status_code == 302
    client.patch(f"{env['base']}/roster/{minor_member}", json={"squad_id": env["sb"]}, headers=_headers("a"))
    blocked = client.get(f"/api/admin/video/matches/{mid}/footage?token={token}")
    assert blocked.status_code == 404 and blocked.get_json()["error"] == "match not found"
    tracklet = VideoTracklet.query.filter_by(video_match_id=mid).one().id
    for path in (f"tracklets/{tracklet}/crops", f"tracklets/{tracklet}/bbox-track"):
        assert client.get(f"/api/admin/video/matches/{mid}/{path}?token={token}").status_code == 404
    # Whole-club roles keep operational access to the mixed match.
    assert client.get(f"{env['base']}/matches/{mid}/report", headers=_headers("a")).status_code == 200


def test_unidentifiable_roster_row_refuses_scoped_access(env, client):
    mid = _match(client, env, "sa")
    db.session.add(VideoRosterEntry(video_match_id=mid, jersey_number=4, player_name="Name only row"))
    db.session.commit()
    _join(client, env, "viewer", "viewer", squads=[env["sa"]])
    assert client.get(f"{env['base']}/matches/{mid}", headers=_h(_email("viewer"))).status_code == 404


# ---------------------------------------------------------------------------
# 2. MED — profile film + feedback evidence respect match scope
# ---------------------------------------------------------------------------


def _mixed_match_with_m1(client, env):
    """A Squad B-labelled match that m1 (now Squad A) played in, set up the legitimate way."""
    client.patch(f"{env['base']}/roster/{env['m1']}", json={"squad_id": env["sb"]}, headers=_headers("a"))
    mid = _match(client, env, "sb")
    resp = client.put(
        f"{env['base']}/matches/{mid}/roster",
        json={"entries": [{"club_roster_member_id": env["m1"], "jersey_number": 7}]},
        headers=_headers("a"),
    )
    assert resp.status_code == 200
    client.patch(f"{env['base']}/roster/{env['m1']}", json={"squad_id": env["sa"]}, headers=_headers("a"))
    return mid


def test_profile_hides_out_of_scope_match_and_uses_narrow_dto(env, client):
    mid = _mixed_match_with_m1(client, env)
    db.session.get(VideoMatch, mid).capture_meta = {
        "qwen_analysis": {"window_captions": [{"roster_entry_id": 999, "caption": "PRIVATE Squad B observation"}]}
    }
    db.session.commit()
    _join(client, env, "coach", "coach", squads=[env["sa"]])
    h = _h(_email("coach"))
    assert client.get(f"{env['base']}/matches/{mid}", headers=h).status_code == 404
    body = client.get(f"{env['base']}/roster/{env['m1']}/profile", headers=h).get_data(as_text=True)
    assert "PRIVATE Squad B observation" not in body and f'"id": {mid}' not in body
    # An in-scope match appears, but only as the narrow DTO.
    own = _match(client, env, "sa")
    client.put(
        f"{env['base']}/matches/{own}/roster",
        json={"entries": [{"club_roster_member_id": env["m1"], "jersey_number": 7}]},
        headers=_headers("a"),
    )
    film = client.get(f"{env['base']}/roster/{env['m1']}/profile", headers=h).get_json()["film"]
    assert [row["match"]["id"] for row in film] == [own]
    assert "capture_meta" not in film[0]["match"] and "blob_path" not in film[0]["match"]
    # Managers keep the legacy full payload.
    manager_film = client.get(f"{env['base']}/roster/{env['m1']}/profile", headers=_headers("a")).get_json()["film"]
    assert {row["match"]["id"] for row in manager_film} == {mid, own} and "capture_meta" in manager_film[0]["match"]


def test_feedback_suggestions_and_writes_respect_match_scope(env, client, club_app):
    from src.models.club_invitation import ClubInvitation, utcnow
    from src.models.showcase import PlayerProfileClaim

    mid = _mixed_match_with_m1(client, env)
    claim = PlayerProfileClaim(
        player_api_id=7001,
        user_account_id=club_app.c2["users"]["scout"],
        relationship_type="player",
        status="approved",
        reviewed_at=utcnow(),
    )
    db.session.add(claim)
    db.session.flush()
    invitation = ClubInvitation(
        program_id=env["pid"],
        player_api_id=7001,
        claim_id=claim.id,
        recipient_user_id=claim.user_account_id,
        created_by_user_id=club_app.c2["users"]["a"],
        client_request_id=str(uuid4()),
        request_hash="test",
        status="accepted",
        created_at=utcnow(),
        expires_at=utcnow() + timedelta(days=7),
        responded_at=utcnow(),
    )
    db.session.add(invitation)
    db.session.flush()
    iid = invitation.id
    match = db.session.get(VideoMatch, mid)
    match.status = "finalized"
    entry = VideoRosterEntry.query.filter_by(video_match_id=mid).one()
    match.capture_meta = {
        "qwen_analysis": {
            "window_captions": [
                {
                    "roster_entry_id": entry.id,
                    "grounded": True,
                    "box_t": 5,
                    "caption": "PRIVATE out-of-scope observation",
                }
            ]
        }
    }
    db.session.add(
        VideoPlayerReport(
            video_match_id=mid,
            roster_entry_id=entry.id,
            club_program_id_at_finalize=env["pid"],
            club_player_api_id_at_finalize=7001,
            identity_confidence="human_confirmed",
            model_version="ra2-test",
        )
    )
    db.session.commit()
    _join(client, env, "coach", "coach", squads=[env["sa"]])
    h = _h(_email("coach"))
    resp = client.get(f"{env['base']}/player-feedback/suggestions?invitation_id={iid}", headers=h)
    assert resp.status_code == 200 and resp.get_json()["suggestions"] == []
    # The manager still sees the grounded observation (legacy behaviour).
    manager = client.get(f"{env['base']}/player-feedback/suggestions?invitation_id={iid}", headers=_headers("a"))
    assert manager.get_json()["suggestions"][0]["text"] == "PRIVATE out-of-scope observation"
    # Writes use the same rule: the coach can't cite the forbidden match.
    write = client.post(
        f"{env['base']}/player-feedback",
        json={
            "invitation_id": iid,
            "client_request_id": str(uuid4()),
            "title": "Fictional feedback",
            "body": "Keep scanning before you receive.",
            "video_match_id": mid,
            "observation_refs": [],
        },
        headers=h,
    )
    assert write.status_code == 409 and write.get_json()["error"] == "feedback_reference_unavailable"


# ---------------------------------------------------------------------------
# 3. MED — grant squad rows reconcile by squad id
# ---------------------------------------------------------------------------


def _patch(client, env, gid, body):
    return client.patch(f"{env['base']}/access/{gid}", json=body, headers=_headers("a"))


def _me(client, key, env):
    return client.get(f"{env['base']}/access/me", headers=_h(_email(key))).get_json()["access"]


def test_demote_coach_to_viewer_same_squad(env, client):
    _join(client, env, "coach", "coach", squads=[env["sa"]])
    resp = _patch(client, env, _grant_id(env, "coach"), {"role": "viewer"})
    assert resp.status_code == 200
    me = _me(client, "coach", env)
    assert me["role"] == "viewer" and me["squad_ids"] == [env["sa"]]
    assert {"feedback", "matches.upload"}.isdisjoint(me["capabilities"])


def test_unchanged_scope_patch(env, client):
    _join(client, env, "coach", "coach", squads=[env["sa"]])
    resp = _patch(client, env, _grant_id(env, "coach"), {"role": "coach", "squad_ids": [env["sa"]]})
    assert resp.status_code == 200
    assert _me(client, "coach", env)["squad_ids"] == [env["sa"]]
    assert ClubAccessGrantSquad.query.filter_by(grant_id=_grant_id(env, "coach")).count() == 1


def test_overlapping_narrowing(env, client):
    _join(client, env, "coach", "coach", squads=[env["sa"], env["sb"]])
    assert _me(client, "coach", env)["squad_ids"] == sorted([env["sa"], env["sb"]])
    resp = _patch(client, env, _grant_id(env, "coach"), {"squad_ids": [env["sa"]]})
    assert resp.status_code == 200
    assert _me(client, "coach", env)["squad_ids"] == [env["sa"]]
    assert client.get(f"{env['base']}/roster/{env['m2']}/profile", headers=_h(_email("coach"))).status_code == 404
    # Widen again with overlap, then narrow to the other squad.
    assert _patch(client, env, _grant_id(env, "coach"), {"squad_ids": [env["sa"], env["sb"]]}).status_code == 200
    assert _patch(client, env, _grant_id(env, "coach"), {"squad_ids": [env["sb"]]}).status_code == 200
    assert _me(client, "coach", env)["squad_ids"] == [env["sb"]]


# ---------------------------------------------------------------------------
# 4. MED — viewers never receive private notes (allowlist serializers)
# ---------------------------------------------------------------------------


def test_viewer_never_receives_private_notes(env, client):
    db.session.get(ClubRosterMember, env["m1"]).note = PRIVATE_NOTE
    db.session.commit()
    for role in ("viewer", "coach", "analyst"):
        _join(client, env, role, role, squads=[env["sa"]])
        h = _h(_email(role))
        for path in ("roster", f"roster?squad_id={env['sa']}", f"roster/{env['m1']}/profile"):
            assert PRIVATE_NOTE not in client.get(f"{env['base']}/{path}", headers=h).get_data(as_text=True), (
                role,
                path,
            )
    # Managers still see it.
    assert client.get(f"{env['base']}/roster", headers=_headers("a")).get_json()["members"][0]["note"] == PRIVATE_NOTE


# ---------------------------------------------------------------------------
# 5. MED — HEAD requests
# ---------------------------------------------------------------------------

HEAD_PATHS = ["squads", "staff", "map", "available-local-players", "roster/{member}/profile", "roster/{member}/photo"]


def _legacy_head_status(path):
    """Measured on origin/main (RA2 baseline): anonymous 401; manager 422/422/200/200/200/503."""
    return 503 if path.endswith("/photo") else 422 if path in {"squads", "staff"} else 200


@pytest.mark.parametrize("path", HEAD_PATHS)
def test_flag_off_head_matches_origin_main(club_app, client, monkeypatch, path):
    monkeypatch.delenv("CLUB_STAFF_ACCESS_ENABLED", raising=False)
    pid = club_app.c2["program_a"]
    member = _add_api_member(client, pid)
    url = f"/api/club/{pid}/{path.format(member=member)}"
    assert client.head(url).status_code == 401
    assert client.head(url, headers=_headers("a")).status_code == _legacy_head_status(path)
    assert client.head(url, headers=_headers("b")).status_code == 403


@pytest.mark.parametrize("path", HEAD_PATHS)
def test_flag_on_head_requires_every_view_capability(env, client, path):
    url = f"{env['base']}/{path.format(member=env['m1'])}"
    assert client.head(url).status_code == 401
    assert client.head(url, headers=_headers("a")).status_code == _legacy_head_status(path)
    _join(client, env, "viewer", "viewer", squads=[env["sa"]])
    # GET-only views the viewer may read answer HEAD like GET; multi-method or manager views refuse.
    expected = 200 if path in {"map", "roster/{member}/profile"} else 403
    assert client.head(url, headers=_h(_email("viewer"))).status_code == expected


def test_viewer_head_cannot_create_squads(env, client):
    _join(client, env, "viewer", "viewer", squads=[env["sa"]])
    from src.models.funding import ClubSquad

    count = ClubSquad.query.count()
    client.open(
        f"{env['base']}/squads", method="HEAD", json={"name": "Sneaky", "kind": "other"}, headers=_h(_email("viewer"))
    )
    assert ClubSquad.query.count() == count


# ---------------------------------------------------------------------------
# Live revocation (reviewer's passing probe, kept as a regression)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("change", ["removed_grant", "hidden_program", "suspended_program"])
def test_live_revocation_covers_removal_and_program_standing(env, client, monkeypatch, change):
    mid = _match(client, env, "sa")
    _join(client, env, "coach", "coach", squads=[env["sa"]])
    h = _h(_email("coach"))
    token = client.get(f"{env['base']}/matches/{mid}/media-token", headers=h).get_json()["token"]
    _fake_storage(monkeypatch)
    assert client.get(f"/api/admin/video/matches/{mid}/footage?token={token}").status_code == 302
    if change == "removed_grant":
        db.session.delete(
            ClubAccessGrant.query.filter_by(program_id=env["pid"], user_account_id=env["users"]["coach"]).one()
        )
    elif change == "hidden_program":
        db.session.get(ClubProgram, env["pid"]).emergency_hidden = True
    else:
        db.session.get(ClubProgram, env["pid"]).platform_status = "suspended"
    db.session.commit()
    db.session.expire_all()
    assert client.get(f"{env['base']}/roster", headers=h).status_code == 403
    assert client.get(f"/api/admin/video/matches/{mid}/footage?token={token}").get_json()["error"] == "match not found"
