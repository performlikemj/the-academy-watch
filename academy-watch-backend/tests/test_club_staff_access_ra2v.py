# ruff: noqa: F401, F811
"""RA2V regressions: the reviewer's probes with the defect assertions reversed (synthetic data only).

Recording coverage is monotonic: display-roster cleanup (direct removal; clear label -> remove ->
relabel; same-jersey replacement) must never reopen a recording for squad-scoped staff, in either
storage branch (local file / Azure SAS), and /roster film totals exclude forbidden matches.
"""

from datetime import datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from src.models.club_access import ClubAccessGrant, ClubAccessGrantSquad
from src.models.funding import ClubRosterMember
from src.models.league import db
from src.models.video import VideoMatch, VideoPlayerReport, VideoRosterEntry, VideoTracklet
from src.routes import club as routes
from src.services import club_access, video_storage
from test_club_console import _add_local_member, _local
from test_club_staff_access import _email, _h, _headers, _join, _match, client, club_app, env


def _put(client, env, mid, members):
    return client.put(
        f"{env['base']}/matches/{mid}/roster",
        json={"entries": [{"club_roster_member_id": m, "jersey_number": i + 7} for i, m in enumerate(members)]},
        headers=_headers("a"),
    )


def _move(client, env, member, squad):
    response = client.patch(f"{env['base']}/roster/{member}", json={"squad_id": squad}, headers=_headers("a"))
    assert response.status_code == 200, response.get_json()


def _ready(env, client, club_app, monkeypatch, role):
    minor = _local(club_app.c2["users"]["a"], name="PRIVATE RA2V minor", birth_year=2010)
    minor_id = minor.id
    member = _add_local_member(client, env["pid"], minor.id)
    _move(client, env, member, env["sa"])
    mid = _match(client, env, "sa")
    assert _put(client, env, mid, [env["m1"], member]).status_code == 200
    rows = VideoRosterEntry.query.filter_by(video_match_id=mid).order_by(VideoRosterEntry.jersey_number).all()
    track = VideoTracklet(
        video_match_id=mid,
        pipeline_key="ra2v-minor",
        kind="chain",
        roster_entry_id=rows[1].id,
        tag_source="human",
        first_s=0,
        last_s=10,
        visible_s=10,
        thumbnail_paths=["e1_1.jpg"],
    )
    db.session.add(track)
    db.session.add_all(
        [
            VideoPlayerReport(
                video_match_id=mid,
                roster_entry_id=rows[0].id,
                club_program_id_at_finalize=env["pid"],
                club_roster_member_id_at_finalize=env["m1"],
                club_player_api_id_at_finalize=7001,
                identity_confidence="human_confirmed",
                minutes_visible=23,
                model_version="ra2v",
            ),
            VideoPlayerReport(
                video_match_id=mid,
                roster_entry_id=rows[1].id,
                club_program_id_at_finalize=env["pid"],
                club_roster_member_id_at_finalize=member,
                club_local_player_id_at_finalize=minor_id,
                identity_confidence="human_confirmed",
                minutes_visible=16,
                model_version="ra2v",
            ),
        ]
    )
    match = db.session.get(VideoMatch, mid)
    match.status = "finalized"
    match.finalized_at = datetime(2026, 9, 30, 1, 2, 3)
    db.session.commit()
    tid = track.id
    _join(client, env, role, role, squads=[env["sa"]])
    h = _h(_email(role))
    monkeypatch.setattr(video_storage, "is_configured", lambda: True)
    monkeypatch.setattr(video_storage, "mint_media_read_sas", lambda path, **kw: "https://example.invalid/ra2v-footage")
    token = client.get(f"{env['base']}/matches/{mid}/media-token", headers=h).get_json()["token"]
    assert client.get(f"/api/admin/video/matches/{mid}/footage?token={token}").status_code == 302
    assert client.get(f"/api/admin/video/matches/{mid}/tracklets/{tid}/crops?token={token}").status_code == 200
    assert client.get(f"/api/admin/video/matches/{mid}/tracklets/{tid}/bbox-track?token={token}").status_code == 200
    return (mid, member, tid, h, token)


def _denied(client, env, mid, member, tid, h, token):
    for method in ("get", "head"):
        for suffix in ("", "/report", "/reel", "/media-token"):
            response = getattr(client, method)(f"{env['base']}/matches/{mid}{suffix}", headers=h)
            assert response.status_code == 404, (method, suffix, response.get_json() if method == "get" else "")
        for suffix in ("footage", "crops/e1_1.jpg", f"tracklets/{tid}/crops", f"tracklets/{tid}/bbox-track"):
            response = getattr(client, method)(f"/api/admin/video/matches/{mid}/{suffix}?token={token}")
            assert response.status_code == 404, (method, suffix)
            if method == "get":
                assert response.get_json()["error"] == "match not found"
    assert mid not in [m["id"] for m in client.get(f"{env['base']}/matches", headers=h).get_json()["matches"]]
    profile = client.get(f"{env['base']}/roster/{env['m1']}/profile", headers=h)
    assert profile.status_code == 200
    assert all(row["match"]["id"] != mid for row in profile.get_json().get("film", []))
    assert client.get(f"{env['base']}/matches/{mid}/report", headers=_headers("a")).status_code == 200


@pytest.mark.parametrize("role", ["coach", "analyst", "viewer"])
@pytest.mark.parametrize(
    "change",
    [
        "moved_minor",
        "unknown_row",
        "dangling_member",
        "cross_program_member",
        "unlabelled",
        "other_label",
        "scope_narrowed",
    ],
)
def test_all_paths_live_coverage(env, client, club_app, monkeypatch, role, change):
    mid, member, tid, h, token = _ready(env, client, club_app, monkeypatch, role)
    if change == "moved_minor":
        _move(client, env, member, env["sb"])
    elif change == "unknown_row":
        db.session.add(VideoRosterEntry(video_match_id=mid, jersey_number=20, player_name="Unidentified"))
    elif change == "dangling_member":
        VideoRosterEntry.query.filter_by(video_match_id=mid, club_roster_member_id=member).update(
            {"club_roster_member_id": 999999}
        )
    elif change == "cross_program_member":
        db.session.get(ClubRosterMember, member).program_id = club_app.c2["program_b"]
    elif change == "unlabelled":
        db.session.get(VideoMatch, mid).squad_id = None
    elif change == "other_label":
        db.session.get(VideoMatch, mid).squad_id = env["sb"]
    elif change == "scope_narrowed":
        grant = ClubAccessGrant.query.filter_by(program_id=env["pid"], user_account_id=env["users"][role]).one()
        result = client.patch(
            f"{env['base']}/access/{grant.id}", json={"squad_ids": [env["sb"]]}, headers=_headers("a")
        )
        assert result.status_code == 200
    db.session.commit()
    db.session.expire_all()
    if change == "scope_narrowed":
        assert client.get(f"{env['base']}/roster/{env['m1']}/profile", headers=h).status_code == 404
        for suffix in ("", "/report", "/reel", "/media-token"):
            assert client.get(f"{env['base']}/matches/{mid}{suffix}", headers=h).status_code == 404
        for suffix in ("footage", "crops/e1_1.jpg", f"tracklets/{tid}/crops", f"tracklets/{tid}/bbox-track"):
            assert client.get(f"/api/admin/video/matches/{mid}/{suffix}?token={token}").status_code == 404
    else:
        _denied(client, env, mid, member, tid, h, token)


@pytest.mark.parametrize("role", ["coach", "analyst", "viewer"])
def test_roster_summary_excludes_forbidden_match(env, client, club_app, monkeypatch, role):
    mid, member, tid, h, token = _ready(env, client, club_app, monkeypatch, role)
    _move(client, env, member, env["sb"])
    assert client.get(f"{env['base']}/matches/{mid}/report", headers=h).status_code == 404
    assert client.get(f"{env['base']}/roster/{env['m1']}/profile", headers=h).get_json().get("film", []) == []
    roster = client.get(f"{env['base']}/roster", headers=h).get_json()
    m1 = next(m for m in roster["members"] if m["id"] == env["m1"])
    assert "film" not in m1, m1
    manager = client.get(f"{env['base']}/roster", headers=_headers("a")).get_json()
    m1_manager = next(m for m in manager["members"] if m["id"] == env["m1"])
    assert m1_manager["film"] == {"report_count": 1, "on_camera_minutes": 23.0, "last_report_at": "2026-09-30T01:02:03"}


@pytest.mark.parametrize("role", ["coach", "analyst", "viewer"])
@pytest.mark.parametrize("storage_mode", ["local", "azure"])
@pytest.mark.parametrize("cleanup", ["direct_remove", "clear_remove_relabel", "replace_same_jersey"])
def test_roster_cleanup_never_reopens_recording(
    env, client, club_app, monkeypatch, role, tmp_path, storage_mode, cleanup
):
    mid = _match(client, env, "sa")
    minor = _local(club_app.c2["users"]["a"], name="PRIVATE RA2V minor", birth_year=2010)
    member = _add_local_member(client, env["pid"], minor.id)
    _move(client, env, member, env["sa"])
    assert _put(client, env, mid, [env["m1"], member]).status_code == 200
    recording = tmp_path / "recording.mp4"
    recording.write_bytes(b"FIXTURE: Squad A adult and PRIVATE RA2V minor in Squad B appear in this recording")
    match = db.session.get(VideoMatch, mid)
    match.capture_meta = {"local": {"footage": str(recording)}}
    db.session.commit()
    monkeypatch.setattr(video_storage, "is_configured", lambda: True)
    monkeypatch.setattr(
        video_storage,
        "verify_uploaded_blob",
        lambda path: {"ok": True, "etag": "ra2v-original-etag", "size_bytes": recording.stat().st_size},
    )
    uploaded = client.post(f"{env['base']}/matches/{mid}/upload-complete", json={"kickoff_s": 0}, headers=_headers("a"))
    assert uploaded.status_code == 200 and uploaded.get_json()["status"] == "uploaded"
    original_blob_path = match.blob_path
    _join(client, env, role, role, squads=[env["sa"]])
    h = _h(_email(role))
    monkeypatch.setattr(video_storage, "is_configured", lambda: storage_mode == "azure")
    signed_paths = []

    def sign(path, **kw):
        signed_paths.append(path)
        return "https://example.invalid/" + path

    monkeypatch.setattr(video_storage, "mint_media_read_sas", sign)
    # Scoped tokens can only be minted against verifiable storage; mint there, then test the branch.
    monkeypatch.setattr(video_storage, "is_configured", lambda: True)
    token = client.get(f"{env['base']}/matches/{mid}/media-token", headers=h).get_json()["token"]
    monkeypatch.setattr(video_storage, "is_configured", lambda: storage_mode == "azure")
    _move(client, env, member, env["sb"])
    url = f"/api/admin/video/matches/{mid}/footage?token={token}"
    assert client.get(url).status_code == 404
    if cleanup == "clear_remove_relabel":
        assert (
            client.patch(f"{env['base']}/matches/{mid}", json={"squad_id": None}, headers=_headers("a")).status_code
            == 200
        )
    if cleanup == "replace_same_jersey":
        result = client.put(
            f"{env['base']}/matches/{mid}/roster",
            json={"entries": [{"club_roster_member_id": env["m1"], "jersey_number": 8}]},
            headers=_headers("a"),
        )
        assert result.status_code == 200
    else:
        assert _put(client, env, mid, [env["m1"]]).status_code == 200
    if cleanup == "clear_remove_relabel":
        assert (
            client.patch(
                f"{env['base']}/matches/{mid}", json={"squad_id": env["sa"]}, headers=_headers("a")
            ).status_code
            == 200
        )
    assert client.get(f"{env['base']}/roster/{member}/profile", headers=h).status_code == 404
    opened = client.get(url)
    assert opened.status_code == 404 and opened.get_json()["error"] == "match not found"
    assert signed_paths == []
    unchanged = db.session.get(VideoMatch, mid)
    assert unchanged.blob_path == original_blob_path and unchanged.blob_etag == "ra2v-original-etag"
    for suffix in ("", "/report", "/reel", "/media-token"):
        assert client.get(f"{env['base']}/matches/{mid}{suffix}", headers=h).status_code == 404
    assert mid not in [m["id"] for m in client.get(f"{env['base']}/matches", headers=h).get_json()["matches"]]
    manager_token = client.get(f"{env['base']}/matches/{mid}/media-token", headers=_headers("a")).get_json()["token"]
    manager_view = client.get(f"/api/admin/video/matches/{mid}/footage?token={manager_token}")
    assert manager_view.status_code == (302 if storage_mode == "azure" else 200)


@pytest.mark.parametrize("order", ["relabel_then_roster", "roster_then_relabel"])
def test_write_interleaving_reads_fail_closed(env, client, club_app, monkeypatch, order):
    mid = _match(client, env, "sa")
    assert (
        client.patch(f"{env['base']}/matches/{mid}", json={"squad_id": None}, headers=_headers("a")).status_code == 200
    )
    assert _put(client, env, mid, [env["m1"]]).status_code == 200
    original = routes.roster_fits_squad
    fired = []

    def interleave(squad, members):
        result = original(squad, members)
        if result and (not fired):
            fired.append(True)
            if order == "relabel_then_roster":
                with db.engine.begin() as conn:
                    conn.execute(
                        sa.update(VideoRosterEntry)
                        .where(VideoRosterEntry.video_match_id == mid)
                        .values(club_roster_member_id=env["m2"])
                    )
            else:
                with db.engine.begin() as conn:
                    conn.execute(sa.update(VideoMatch).where(VideoMatch.id == mid).values(squad_id=env["sa"]))
        return result

    monkeypatch.setattr(routes, "roster_fits_squad", interleave)
    if order == "relabel_then_roster":
        response = client.patch(f"{env['base']}/matches/{mid}", json={"squad_id": env["sa"]}, headers=_headers("a"))
    else:
        response = _put(client, env, mid, [env["m2"]])
    assert response.status_code == 200 and fired
    db.session.expire_all()
    assert db.session.get(VideoMatch, mid).squad_id == env["sa"]
    assert VideoRosterEntry.query.filter_by(video_match_id=mid).one().club_roster_member_id == env["m2"]
    _join(client, env, "viewer", "viewer", squads=[env["sa"]])
    assert client.get(f"{env['base']}/matches/{mid}", headers=_h(_email("viewer"))).status_code == 404


def test_scope_rows_preserve_retained_ids_and_effective_permissions(env, client):
    _join(client, env, "coach", "coach", squads=[env["sa"], env["sb"]])
    grant = ClubAccessGrant.query.filter_by(program_id=env["pid"], user_account_id=env["users"]["coach"]).one()
    gid = grant.id
    old = {r.squad_id: r.id for r in grant.squads}
    for payload in (
        {"role": "viewer"},
        {"squad_ids": [env["sa"]]},
        {"squad_ids": [env["sa"]]},
        {"squad_ids": [env["sa"], env["sb"]]},
        {"all_squads": True},
        {"all_squads": False, "squad_ids": [env["sa"]]},
    ):
        response = client.patch(f"{env['base']}/access/{gid}", json=payload, headers=_headers("a"))
        assert response.status_code == 200, response.get_json()
        db.session.expire_all()
        rows = ClubAccessGrantSquad.query.filter_by(grant_id=gid).all()
        assert len({r.squad_id for r in rows}) == len(rows)
        if env["sa"] in [r.squad_id for r in rows] and (not payload.get("all_squads")):
            if "all_squads" not in payload:
                assert next(r for r in rows if r.squad_id == env["sa"]).id == old[env["sa"]]
        h = _h(_email("coach"))
        assert client.post(f"{env['base']}/matches", json={"squad_id": env["sa"]}, headers=h).status_code == 403
        assert client.get(f"{env['base']}/player-feedback", headers=h).status_code == 403


@pytest.mark.parametrize("role", ["coach", "analyst", "viewer"])
def test_feedback_suggestions_mixed_minor_and_reference_write(env, client, club_app, monkeypatch, role):
    from datetime import timedelta
    from uuid import uuid4

    from src.models.club_invitation import ClubInvitation, utcnow
    from src.models.showcase import PlayerProfileClaim

    mid, member, tid, h, token = _ready(env, client, club_app, monkeypatch, role)
    claim = PlayerProfileClaim(
        player_api_id=7001,
        user_account_id=club_app.c2["users"]["scout"],
        relationship_type="player",
        status="approved",
        reviewed_at=utcnow(),
    )
    db.session.add(claim)
    db.session.flush()
    inv = ClubInvitation(
        program_id=env["pid"],
        player_api_id=7001,
        claim_id=claim.id,
        recipient_user_id=claim.user_account_id,
        created_by_user_id=club_app.c2["users"]["a"],
        client_request_id=str(uuid4()),
        request_hash="ra2v",
        status="accepted",
        created_at=utcnow(),
        expires_at=utcnow() + timedelta(days=7),
        responded_at=utcnow(),
    )
    db.session.add(inv)
    db.session.flush()
    iid = inv.id
    entry = VideoRosterEntry.query.filter_by(video_match_id=mid, club_roster_member_id=env["m1"]).one()
    db.session.get(VideoMatch, mid).capture_meta = {
        "qwen_analysis": {
            "window_captions": [
                {
                    "roster_entry_id": entry.id,
                    "grounded": True,
                    "box_t": 5,
                    "caption": "PRIVATE mixed-minor match observation",
                }
            ]
        }
    }
    db.session.commit()
    url = f"{env['base']}/player-feedback/suggestions?invitation_id={iid}"
    before = client.get(url, headers=h)
    if role == "coach":
        assert before.get_json()["suggestions"][0]["text"] == "PRIVATE mixed-minor match observation"
    else:
        assert before.status_code == 403
    _move(client, env, member, env["sb"])
    after = client.get(url, headers=h)
    if role == "coach":
        assert after.status_code == 200 and after.get_json()["suggestions"] == []
    else:
        assert after.status_code == 403
    write = client.post(
        f"{env['base']}/player-feedback",
        json={
            "invitation_id": iid,
            "client_request_id": str(uuid4()),
            "title": "Synthetic feedback",
            "body": "Keep scanning before you receive.",
            "video_match_id": mid,
            "observation_refs": [],
        },
        headers=h,
    )
    assert write.status_code == (409 if role == "coach" else 403)
    if role == "coach":
        assert write.get_json()["error"] == "feedback_reference_unavailable"
