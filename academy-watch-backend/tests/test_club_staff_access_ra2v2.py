# ruff: noqa: F401, F811
"""RA2V2 regressions: the reviewer's coverage-boundary probes with every exposure reversed.

Variant A (legacy re-attestation, 24 + 6 flag-transition cases) and variant B (bytes before
completion, 18 cleanup cases) must stay denied; admin unknown-row cleanup (6) and other
maintenance mutations (24) must never shrink coverage. Synthetic data only.
"""

from datetime import datetime, timedelta

import pytest
from src.models.funding import ClubProgramClaim, ClubProgramManager, ClubRosterMember
from src.models.league import db
from src.models.showcase import LocalPlayer
from src.models.video import VideoMatch, VideoRosterEntry, VideoTracklet
from src.services import video_storage
from test_club_console import _add_local_member, _admin_headers, _local
from test_club_staff_access import _email, _h, _headers, _join, _match, client, club_app, env
from test_club_staff_access_coverage import _kinds, _make_legacy, _put, _upload


def _minor(env, client, club_app):
    minor = _local(club_app.c2["users"]["a"], name="PRIVATE historical minor", birth_year=2010)
    member = _add_local_member(client, env["pid"], minor.id)
    assert (
        client.patch(f"{env['base']}/roster/{member}", json={"squad_id": env["sa"]}, headers=_headers("a")).status_code
        == 200
    )
    return (minor.id, member)


def _store(mid, tmp_path, monkeypatch, mode):
    p = tmp_path / "recording.mp4"
    p.write_bytes(b"SYNTHETIC: adult A and PRIVATE historical minor B")
    match = db.session.get(VideoMatch, mid)
    match.capture_meta = {"local": {"footage": str(p)}}
    db.session.commit()
    monkeypatch.setattr(video_storage, "is_configured", lambda: mode == "azure")
    signed = []
    monkeypatch.setattr(
        video_storage,
        "mint_media_read_sas",
        lambda path, **kw: signed.append(path) or "https://example.invalid/" + path,
    )
    return (p, signed)


@pytest.mark.parametrize("role", ["coach", "analyst", "viewer"])
@pytest.mark.parametrize("completion", ["club", "admin"])
@pytest.mark.parametrize("etag", ["legacy-original-etag", "replacement-etag"])
@pytest.mark.parametrize("mode", ["local", "azure"])
def test_legacy_reattestation_never_creates_origin(
    env, client, club_app, monkeypatch, tmp_path, role, completion, etag, mode
):
    mid = _match(client, env, "sa", uploaded=False)
    _, member = _minor(env, client, club_app)
    assert _put(client, env, mid, [env["m1"], member]).status_code == 200
    _make_legacy(mid)
    p, signed = _store(mid, tmp_path, monkeypatch, mode)
    match = db.session.get(VideoMatch, mid)
    blob = match.blob_path
    match.uploaded_at = datetime.now()
    match.status = "uploaded"
    match.blob_etag = "legacy-original-etag"
    db.session.get(ClubRosterMember, member).squad_id = env["sb"]
    VideoRosterEntry.query.filter_by(video_match_id=mid, club_roster_member_id=member).delete(synchronize_session=False)
    db.session.commit()
    assert _kinds(mid) == []
    _join(client, env, role, role, squads=[env["sa"]])
    h = _h(_email(role))
    assert client.get(f"{env['base']}/matches/{mid}", headers=h).status_code == 404
    assert client.get(f"{env['base']}/matches/{mid}/media-token", headers=h).status_code == 404
    monkeypatch.setattr(video_storage, "is_configured", lambda: True)
    verified = []
    monkeypatch.setattr(
        video_storage,
        "verify_uploaded_blob",
        lambda path: verified.append(path) or {"ok": True, "etag": etag, "size_bytes": p.stat().st_size},
    )
    url = (
        f"{env['base']}/matches/{mid}/upload-complete"
        if completion == "club"
        else f"/api/admin/video/matches/{mid}/upload-complete"
    )
    r = client.post(url, json={"kickoff_s": 0}, headers=_headers("a") if completion == "club" else _admin_headers())
    assert r.status_code == 200, r.get_json()
    assert verified == [blob]
    assert _kinds(mid) == []
    monkeypatch.setattr(video_storage, "is_configured", lambda: mode == "azure")
    for verb in ["get", "head"]:
        for suffix in ["", "/report", "/reel", "/media-token"]:
            assert getattr(client, verb)(f"{env['base']}/matches/{mid}{suffix}", headers=h).status_code == 404
    manager_tok = client.get(f"{env['base']}/matches/{mid}/media-token", headers=_headers("a")).get_json()["token"]
    assert client.get(f"/api/admin/video/matches/{mid}/footage?token={manager_tok}").status_code == (
        200 if mode == "local" else 302
    )
    assert client.get(f"{env['base']}/roster/{member}/profile", headers=h).status_code == 404
    assert db.session.get(VideoMatch, mid).blob_path == blob


@pytest.mark.parametrize("role", ["coach", "analyst", "viewer"])
@pytest.mark.parametrize("completion", ["club", "admin"])
def test_admin_unknown_cleanup_and_new_etag_remain_denied(env, client, club_app, monkeypatch, role, completion):
    mid = _match(client, env, "sa")
    assert _put(client, env, mid, [env["m1"]]).status_code == 200
    _upload(client, env, monkeypatch, mid)
    _join(client, env, role, role, squads=[env["sa"]])
    h = _h(_email(role))
    token = client.get(f"{env['base']}/matches/{mid}/media-token", headers=h).get_json()["token"]
    admin = f"/api/admin/video/matches/{mid}"
    r = client.put(
        admin + "/roster",
        json={"entries": [{"player_name": "Unidentified trialist", "jersey_number": 30}]},
        headers=_admin_headers(),
    )
    assert r.status_code == 200, r.get_json()
    assert ("uncertain", None) in _kinds(mid)
    before = set(_kinds(mid))
    assert _put(client, env, mid, [env["m1"]]).status_code == 200
    monkeypatch.setattr(
        video_storage, "verify_uploaded_blob", lambda path: {"ok": True, "etag": "different-etag", "size_bytes": 10}
    )
    url = f"{env['base']}/matches/{mid}/upload-complete" if completion == "club" else admin + "/upload-complete"
    assert (
        client.post(url, json={}, headers=_headers("a") if completion == "club" else _admin_headers()).status_code
        == 200
    )
    assert set(_kinds(mid)) == before
    for verb in ["get", "head"]:
        for suffix in ["", "/report", "/reel", "/media-token"]:
            assert getattr(client, verb)(f"{env['base']}/matches/{mid}{suffix}", headers=h).status_code == 404
        for suffix in ["footage", "crops/e1_1.jpg", "tracklets/999/crops", "tracklets/999/bbox-track"]:
            assert getattr(client, verb)(f"{admin}/{suffix}?token={token}").status_code == 404


@pytest.mark.parametrize("role", ["coach", "analyst", "viewer"])
@pytest.mark.parametrize(
    "operation",
    [
        "admin_replace",
        "member_delete",
        "member_readd",
        "local_merge",
        "api_merge",
        "program_owner_transfer",
        "match_program_transfer",
        "delete_recreate",
    ],
)
def test_other_mutations_do_not_shrink_coverage(env, client, club_app, monkeypatch, role, operation):
    mid = _match(client, env, "sa")
    lp, member = _minor(env, client, club_app)
    assert _put(client, env, mid, [env["m1"], member]).status_code == 200
    _upload(client, env, monkeypatch, mid)
    before = set(_kinds(mid))
    _join(client, env, role, role, squads=[env["sa"]])
    h = _h(_email(role))
    token = client.get(f"{env['base']}/matches/{mid}/media-token", headers=h).get_json()["token"]
    assert (
        client.patch(f"{env['base']}/roster/{member}", json={"squad_id": env["sb"]}, headers=_headers("a")).status_code
        == 200
    )
    if operation == "admin_replace":
        r = client.put(
            f"/api/admin/video/matches/{mid}/roster",
            json={"entries": [{"player_name": "Adult A", "jersey_number": 7}]},
            headers=_admin_headers(),
        )
        assert r.status_code == 200
    elif operation in ["member_delete", "member_readd"]:
        assert client.delete(f"{env['base']}/roster/{member}", headers=_headers("a")).status_code in (200, 204)
        if operation == "member_readd":
            again = _add_local_member(client, env["pid"], lp)
            assert (
                client.patch(
                    f"{env['base']}/roster/{again}", json={"squad_id": env["sa"]}, headers=_headers("a")
                ).status_code
                == 200
            )
    elif operation == "local_merge":
        target = _local(club_app.c2["users"]["a"], name="Canonical duplicate", birth_year=2010)
        r = client.post(
            f"/api/admin/local-players/{lp}/merge", json={"into_local_player_id": target.id}, headers=_admin_headers()
        )
        assert r.status_code == 200, r.get_json()
    elif operation == "api_merge":
        db.session.get(LocalPlayer, lp).status = "approved"
        db.session.commit()
        r = client.post(
            f"/api/admin/local-players/{lp}/link-api", json={"player_api_id": 7001}, headers=_admin_headers()
        )
        assert r.status_code == 200, r.get_json()
        assert db.session.get(ClubRosterMember, member) is None
    elif operation == "program_owner_transfer":
        claim = ClubProgramClaim(
            program_id=env["pid"],
            user_account_id=club_app.c2["users"]["b"],
            relationship_type="club_official",
            status="approved",
        )
        db.session.add(claim)
        db.session.flush()
        db.session.add(
            ClubProgramManager(
                program_id=env["pid"],
                user_account_id=club_app.c2["users"]["b"],
                source_claim_id=claim.id,
                status="active",
                granted_by="synthetic fixture",
            )
        )
        db.session.commit()
        r = client.post(
            f"/api/admin/programs/{env['pid']}/owner",
            json={"user_account_id": club_app.c2["users"]["b"], "reason": "Synthetic transfer"},
            headers=_admin_headers(),
        )
        assert r.status_code == 200, r.get_json()
    elif operation == "match_program_transfer":
        for url in [f"/api/admin/video/matches/{mid}", f"{env['base']}/matches/{mid}"]:
            r = client.patch(
                url,
                json={"club_program_id": club_app.c2["program_b"], "uploaded_at": None, "blob_etag": None},
                headers=_admin_headers() if "/admin/" in url else _headers("a"),
            )
            assert r.status_code == 200
        assert db.session.get(VideoMatch, mid).club_program_id == env["pid"]
    elif operation == "delete_recreate":
        blob = db.session.get(VideoMatch, mid).blob_path
        for url in [f"/api/admin/video/matches/{mid}", f"{env['base']}/matches/{mid}"]:
            assert (
                client.delete(url, headers=_admin_headers() if "/admin/" in url else _headers("a")).status_code == 405
            )
        monkeypatch.setattr(video_storage, "is_configured", lambda: False)
        fresh = _match(client, env, "sa")
        assert db.session.get(VideoMatch, fresh).blob_path != blob
    assert set(_kinds(mid)) >= before
    assert client.get(f"{env['base']}/matches/{mid}/media-token", headers=h).status_code == 404
    assert client.get(f"/api/admin/video/matches/{mid}/footage?token={token}").status_code == 404


@pytest.mark.parametrize("role", ["coach", "analyst", "viewer"])
@pytest.mark.parametrize("mode", ["local", "azure"])
@pytest.mark.parametrize("cleanup", ["direct_remove", "clear_remove_relabel", "replace_same_jersey"])
def test_bytes_before_completion_stay_closed(env, client, club_app, monkeypatch, tmp_path, role, mode, cleanup):
    mid = _match(client, env, "sa", uploaded=False)
    _, member = _minor(env, client, club_app)
    assert _put(client, env, mid, [env["m1"], member]).status_code == 200
    p, signed = _store(mid, tmp_path, monkeypatch, mode)
    _join(client, env, role, role, squads=[env["sa"]])
    h = _h(_email(role))
    original_blob = db.session.get(VideoMatch, mid).blob_path
    assert client.get(f"{env['base']}/matches/{mid}/media-token", headers=h).status_code == 404
    manager_tok = client.get(f"{env['base']}/matches/{mid}/media-token", headers=_headers("a")).get_json()["token"]
    assert (
        client.patch(f"{env['base']}/roster/{member}", json={"squad_id": env["sb"]}, headers=_headers("a")).status_code
        == 200
    )
    if cleanup == "clear_remove_relabel":
        assert (
            client.patch(f"{env['base']}/matches/{mid}", json={"squad_id": None}, headers=_headers("a")).status_code
            == 200
        )
    if cleanup == "replace_same_jersey":
        assert (
            client.put(
                f"{env['base']}/matches/{mid}/roster",
                json={"entries": [{"club_roster_member_id": env["m1"], "jersey_number": 8}]},
                headers=_headers("a"),
            ).status_code
            == 200
        )
    else:
        assert _put(client, env, mid, [env["m1"]]).status_code == 200
    if cleanup == "clear_remove_relabel":
        assert (
            client.patch(
                f"{env['base']}/matches/{mid}", json={"squad_id": env["sa"]}, headers=_headers("a")
            ).status_code
            == 200
        )
    assert ("member", member) in _kinds(mid) and ("origin", None) in _kinds(mid)
    match = db.session.get(VideoMatch, mid)
    assert (
        match.status == "created"
        and match.uploaded_at is None
        and (match.blob_etag is None)
        and (match.blob_path == original_blob)
    )
    assert client.get(f"{env['base']}/matches/{mid}/media-token", headers=h).status_code == 404
    _upload(client, env, monkeypatch, mid)
    assert ("member", member) in _kinds(mid)
    monkeypatch.setattr(video_storage, "is_configured", lambda: mode == "azure")
    for verb in ["get", "head"]:
        for suffix in ["", "/report", "/reel", "/media-token"]:
            assert getattr(client, verb)(f"{env['base']}/matches/{mid}{suffix}", headers=h).status_code == 404
    assert signed == []
    assert client.get(f"/api/admin/video/matches/{mid}/footage?token={manager_tok}").status_code == (
        200 if mode == "local" else 302
    )


@pytest.mark.parametrize("role", ["coach", "analyst", "viewer"])
@pytest.mark.parametrize("flag_at_reattest", ["on", "off"])
def test_legacy_unknown_history_stays_legacy(env, client, club_app, monkeypatch, role, flag_at_reattest):
    mid = _match(client, env, "sa", uploaded=False)
    assert _put(client, env, mid, [env["m1"]]).status_code == 200
    _make_legacy(mid)
    unknown = VideoRosterEntry(video_match_id=mid, jersey_number=30, player_name="Pre-migration unidentified child")
    db.session.add(unknown)
    db.session.flush()
    match = db.session.get(VideoMatch, mid)
    match.uploaded_at = datetime.now()
    match.blob_etag = "same-unknown-etag"
    match.status = "uploaded"
    db.session.commit()
    db.session.delete(unknown)
    db.session.commit()
    assert _kinds(mid) == []
    _join(client, env, role, role, squads=[env["sa"]])
    h = _h(_email(role))
    assert client.get(f"{env['base']}/matches/{mid}/media-token", headers=h).status_code == 404
    monkeypatch.setenv("CLUB_STAFF_ACCESS_ENABLED", "true" if flag_at_reattest == "on" else "false")
    _upload(client, env, monkeypatch, mid)
    monkeypatch.setenv("CLUB_STAFF_ACCESS_ENABLED", "true")
    assert _kinds(mid) == []
    for suffix in ["", "/report", "/reel", "/media-token"]:
        assert client.get(f"{env['base']}/matches/{mid}{suffix}", headers=h).status_code == 404
