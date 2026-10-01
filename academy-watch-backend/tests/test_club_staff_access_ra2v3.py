# ruff: noqa: F401, F811
"""RA2V3 regressions: the reviewer's rule attacks with every exposure reversed (synthetic data only).

N1 replacement bytes are unreadable until a verified completion (club re-grant locked, admin
re-grant unpublishes, live ETag verified on every scoped token/byte request); N2 stored feedback
evidence follows live match scope; N3 capture_meta.local is not client-writable; N4 scoped
detail/list fall back to a workflow-only DTO. Admin-created/imported matches stay legacy.
"""

from datetime import timedelta
from uuid import uuid4

import pytest
from src.models.club_invitation import ClubInvitation, utcnow
from src.models.league import db
from src.models.showcase import PlayerProfileClaim
from src.models.video import VideoMatch, VideoPlayerReport, VideoRosterEntry
from src.services import video_storage
from test_club_console import _admin_headers
from test_club_staff_access import _email, _h, _headers, _join, _match, client, club_app, env
from test_club_staff_access_coverage import _kinds, _make_legacy, _put, _upload
from test_club_staff_access_ra2v2 import _minor, _store


@pytest.mark.parametrize("role", ["coach", "analyst", "viewer"])
@pytest.mark.parametrize("grant_route", ["club", "admin", "original"])
def test_replacement_bytes_unreadable_until_verified_completion(
    env, client, club_app, monkeypatch, tmp_path, role, grant_route
):
    monkeypatch.setattr(video_storage, "is_configured", lambda: True)
    monkeypatch.setattr(
        video_storage,
        "mint_upload_sas",
        lambda path: {"upload_url": "https://example.invalid/upload", "blob_path": path},
    )
    mid = _match(client, env, "sa", uploaded=False)
    assert _put(client, env, mid, [env["m1"]]).status_code == 200
    _upload(client, env, monkeypatch, mid, etag="old-verified-etag")
    match = db.session.get(VideoMatch, mid)
    stamp = match.uploaded_at
    blob = match.blob_path
    _join(client, env, role, role, squads=[env["sa"]])
    h = _h(_email(role))
    old_token = client.get(f"{env['base']}/matches/{mid}/media-token", headers=h).json["token"]
    monkeypatch.setattr(
        video_storage,
        "mint_upload_sas",
        lambda path: {"upload_url": "https://example.invalid/upload", "blob_path": path},
    )
    url = f"{env['base']}/matches/{mid}/sas" if grant_route == "club" else f"/api/admin/video/matches/{mid}/sas"
    if grant_route == "club":
        locked = client.post(url, headers=_headers("a"))
        assert locked.status_code == 409 and locked.json == {"error": "recording_locked"}
    elif grant_route == "admin":
        assert client.post(url, headers=_admin_headers()).status_code == 200
        assert db.session.get(VideoMatch, mid).scoped_ready_etag is None
    current = {"etag": "new-unverified-etag", "bytes": b"SYNTHETIC replacement footage, not completed"}
    checks = []

    def verify(path):
        checks.append(path)
        return {"ok": True, "etag": current["etag"], "size_bytes": len(current["bytes"])}

    monkeypatch.setattr(video_storage, "verify_uploaded_blob", verify)
    signed = []
    monkeypatch.setattr(
        video_storage,
        "mint_media_read_sas",
        lambda path, **kw: signed.append((path, current["etag"])) or "https://example.invalid/replacement",
    )
    assert client.get(f"{env['base']}/matches/{mid}/media-token", headers=h).status_code == 404
    blocked = client.get(f"/api/admin/video/matches/{mid}/footage?token={old_token}")
    assert blocked.status_code == 404 and blocked.json["error"] == "match not found"
    for suffix in ["crops/e1_1.jpg", "tracklets/999/crops", "tracklets/999/bbox-track"]:
        assert client.get(f"/api/admin/video/matches/{mid}/{suffix}?token={old_token}").status_code == 404
    assert signed == []
    assert checks or grant_route == "admin"  # admin re-grant is refused before storage is consulted
    assert match.blob_etag == "old-verified-etag" and match.uploaded_at == stamp and (match.status == "uploaded")
    manager_tok = client.get(f"{env['base']}/matches/{mid}/media-token", headers=_headers("a")).json["token"]
    assert client.get(f"/api/admin/video/matches/{mid}/footage?token={manager_tok}").status_code == 302
    f = tmp_path / "replacement.mp4"
    f.write_bytes(current["bytes"])
    match.capture_meta = {"local": {"footage": str(f)}}
    db.session.commit()
    monkeypatch.setattr(video_storage, "is_configured", lambda: False)
    assert client.get(f"/api/admin/video/matches/{mid}/footage?token={old_token}").status_code == 404
    assert client.get(f"{env['base']}/matches/{mid}/media-token", headers=h).status_code == 404
    monkeypatch.setattr(video_storage, "is_configured", lambda: True)
    done = client.post(f"/api/admin/video/matches/{mid}/upload-complete", json={}, headers=_admin_headers())
    assert done.status_code == 200 and db.session.get(VideoMatch, mid).scoped_ready_etag == "new-unverified-etag"
    assert client.get(f"{env['base']}/matches/{mid}/media-token", headers=h).status_code == 200


@pytest.mark.parametrize("role", ["coach", "analyst", "viewer"])
def test_local_artifact_path_is_not_client_writable(env, client, club_app, monkeypatch, tmp_path, role):
    legacy = _match(client, env, "sb")
    assert _put(client, env, legacy, [env["m2"]]).status_code == 200
    _make_legacy(legacy)
    p, signed = _store(legacy, tmp_path, monkeypatch, "local")
    _join(client, env, role, role, squads=[env["sa"]])
    h = _h(_email(role))
    assert client.get(f"{env['base']}/matches/{legacy}/media-token", headers=h).status_code == 404
    creator = h if role != "viewer" else _headers("a")
    r = client.post(
        f"{env['base']}/matches",
        json={"squad_id": env["sa"], "capture_meta": {"local": {"footage": str(p)}}},
        headers=creator,
    )
    assert r.status_code == 201
    r = r.json
    clone = r["id"]
    assert ("origin", None) in _kinds(clone)
    assert "local" not in (r.get("capture_meta") or {})
    assert "local" not in (db.session.get(VideoMatch, clone).capture_meta or {})
    assert _put(client, env, clone, [env["m1"]]).status_code == 200
    assert (
        client.patch(
            f"{env['base']}/matches/{clone}",
            json={"capture_meta": {"local": {"footage": str(p)}}},
            headers=_headers("a"),
        ).status_code
        == 200
    )
    assert "local" not in (db.session.get(VideoMatch, clone).capture_meta or {})
    _upload(client, env, monkeypatch, clone)
    monkeypatch.setattr(video_storage, "is_configured", lambda: False)
    assert client.get(f"{env['base']}/matches/{clone}/media-token", headers=h).status_code == 404
    manager_tok = client.get(f"{env['base']}/matches/{clone}/media-token", headers=_headers("a")).json["token"]
    opened = client.get(f"/api/admin/video/matches/{clone}/footage?token={manager_tok}")
    assert opened.status_code == 404 and opened.data != p.read_bytes()
    assert db.session.get(VideoMatch, clone).blob_path != db.session.get(VideoMatch, legacy).blob_path
    assert _kinds(legacy) == []


@pytest.mark.parametrize("scope_change", ["member_move", "grant_narrow"])
def test_existing_feedback_evidence_follows_live_match_scope(env, client, club_app, monkeypatch, scope_change):
    mid = _match(client, env, "sa")
    _, minor = _minor(env, client, club_app)
    assert _put(client, env, mid, [env["m1"], minor]).status_code == 200
    match = db.session.get(VideoMatch, mid)
    match.status = "finalized"
    entry = VideoRosterEntry.query.filter_by(video_match_id=mid, club_roster_member_id=env["m1"]).one()
    db.session.add(
        VideoPlayerReport(
            video_match_id=mid,
            roster_entry_id=entry.id,
            club_program_id_at_finalize=env["pid"],
            club_player_api_id_at_finalize=7001,
            identity_confidence="human_confirmed",
            model_version="synthetic",
        )
    )
    claim = PlayerProfileClaim(
        player_api_id=7001,
        user_account_id=club_app.c2["users"]["scout"],
        relationship_type="player",
        status="approved",
        reviewed_at=utcnow(),
    )
    db.session.add(claim)
    db.session.flush()
    invite = ClubInvitation(
        program_id=env["pid"],
        player_api_id=7001,
        claim_id=claim.id,
        recipient_user_id=claim.user_account_id,
        created_by_user_id=club_app.c2["users"]["a"],
        client_request_id=str(uuid4()),
        request_hash="synthetic",
        status="accepted",
        created_at=utcnow(),
        expires_at=utcnow() + timedelta(days=7),
        responded_at=utcnow(),
    )
    db.session.add(invite)
    db.session.commit()
    ref = {"label": "PRIVATE footage evidence from mixed recording", "timestamp_s": 23}
    data = {
        "invitation_id": invite.id,
        "client_request_id": str(uuid4()),
        "title": "Synthetic coach review",
        "body": "Practice receiving with an open body.",
        "video_match_id": mid,
        "observation_refs": [ref],
    }
    published = client.post(f"{env['base']}/player-feedback", json=data, headers=_headers("a"))
    assert published.status_code == 201, published.json
    fid = published.json["feedback"]["id"]
    _join(
        client, env, "coach", "coach", squads=[env["sa"], env["sb"]] if scope_change == "grant_narrow" else [env["sa"]]
    )
    h = _h(_email("coach"))
    assert (
        client.patch(f"{env['base']}/roster/{minor}", json={"squad_id": env["sb"]}, headers=_headers("a")).status_code
        == 200
    )
    if scope_change == "grant_narrow":
        from src.models.club_access import ClubAccessGrant

        grant = ClubAccessGrant.query.filter_by(program_id=env["pid"], user_account_id=env["users"]["coach"]).one()
        assert (
            client.patch(
                f"{env['base']}/access/{grant.id}", json={"squad_ids": [env["sa"]]}, headers=_headers("a")
            ).status_code
            == 200
        )
    for suffix in ["", "/report", "/reel", "/media-token"]:
        assert client.get(f"{env['base']}/matches/{mid}{suffix}", headers=h).status_code == 404
    assert (
        client.get(f"{env['base']}/player-feedback/suggestions?invitation_id={invite.id}", headers=h).json[
            "suggestions"
        ]
        == []
    )
    r = client.get(f"{env['base']}/player-feedback/{fid}", headers=h)
    assert r.status_code == 200 and r.json["feedback"]["observation_refs"] == []
    assert r.json["feedback"]["body"] == "Practice receiving with an open body."
    assert "PRIVATE footage evidence" not in r.get_data(as_text=True)
    p = client.get(f"{env['base']}/roster/{env['m1']}/profile", headers=h)
    assert p.status_code == 200 and p.json.get("film", []) == []
    assert p.json["development"][0]["observation_refs"] == []
    assert "PRIVATE footage evidence" not in p.get_data(as_text=True)
    listing = client.get(f"{env['base']}/player-feedback", headers=h)
    assert listing.status_code == 200 and "PRIVATE footage evidence" not in listing.get_data(as_text=True)
    assert client.get(f"{env['base']}/player-feedback/{fid}", headers=_headers("a")).json["feedback"][
        "observation_refs"
    ] == [ref]


@pytest.mark.parametrize("role", ["coach", "analyst", "viewer"])
def test_admin_created_match_cannot_be_converted(env, client, club_app, monkeypatch, role):
    monkeypatch.setattr(video_storage, "is_configured", lambda: False)
    r = client.post(
        "/api/admin/video/matches",
        json={"team_id": club_app.c2["team"], "club_program_id": env["pid"], "squad_id": env["sa"]},
        headers=_admin_headers(),
    )
    assert r.status_code == 201, r.json
    mid = r.json["id"]
    assert r.json["club_program_id"] is None and _kinds(mid) == []
    assert (
        client.patch(
            f"/api/admin/video/matches/{mid}",
            json={"club_program_id": env["pid"], "squad_id": env["sa"]},
            headers=_admin_headers(),
        ).status_code
        == 200
    )
    assert db.session.get(VideoMatch, mid).club_program_id is None
    _join(client, env, role, role, squads=[env["sa"]])
    h = _h(_email(role))
    for suffix in ["", "/media-token", "/reel", "/report"]:
        assert client.get(f"{env['base']}/matches/{mid}{suffix}", headers=h).status_code == 404
    for rule in club_app.url_map.iter_rules():
        if not str(rule).startswith("/api/admin/video/"):
            continue
        if str(rule).endswith("/footage") or "/crops/" in str(rule):
            continue
        path = (
            str(rule)
            .replace("<int:match_id>", str(mid))
            .replace("<int:team_id>", str(club_app.c2["team"]))
            .replace("<int:tracklet_id>", "999")
        )
        for method in rule.methods - {"OPTIONS", "HEAD"}:
            response = client.open(path, method=method, json={}, headers={**h, "X-API-Key": "test-admin-key"})
            assert response.status_code in [401, 403], (method, path, response.status_code)


@pytest.mark.parametrize("role", ["coach", "analyst", "viewer"])
def test_expired_detail_is_workflow_only_for_scoped(env, client, club_app, monkeypatch, role):
    from datetime import datetime

    from src.services import video_retention

    mid = _match(client, env, "sa", uploaded=False)
    assert _put(client, env, mid, [env["m1"]]).status_code == 200
    _upload(client, env, monkeypatch, mid)
    monkeypatch.setattr(video_storage, "is_configured", lambda: True)
    match = db.session.get(VideoMatch, mid)
    match.capture_meta = {
        "qwen_analysis": {
            "window_captions": [
                {"roster_entry_id": 1, "box_t": 23, "caption": "SYNTHETIC retained footage-derived observation"}
            ]
        }
    }
    match.status = "finalized"
    db.session.commit()
    _join(client, env, role, role, squads=[env["sa"]])
    h = _h(_email(role))
    assert client.get(f"{env['base']}/matches/{mid}/media-token", headers=h).status_code == 200
    monkeypatch.setattr(video_storage, "delete_blob", lambda path: True)
    assert video_retention.expire_raw_footage(now=match.expires_at + timedelta(hours=2))["expired"] == 1
    assert match.blob_etag is None and match.status == "expired"
    for suffix in ["/media-token", "/report", "/reel"]:
        assert client.get(f"{env['base']}/matches/{mid}{suffix}", headers=h).status_code == 404
    for verb in ["get", "head"]:
        assert getattr(client, verb)(f"{env['base']}/matches/{mid}", headers=h).status_code == 200
    detail = client.get(f"{env['base']}/matches/{mid}", headers=h)
    listing = client.get(f"{env['base']}/matches", headers=h)
    allowed = {
        "id",
        "club_program_id",
        "squad_id",
        "opponent_name",
        "match_date",
        "competition",
        "status",
        "roster",
        "processing_request_status",
    }
    assert set(detail.json) <= allowed and "capture_meta" not in detail.json and ("job" not in detail.json)
    row = next(m for m in listing.json["matches"] if m["id"] == mid)
    assert set(row) <= allowed and "capture_meta" not in row
    for body in (detail.get_data(as_text=True), listing.get_data(as_text=True)):
        assert "SYNTHETIC retained footage-derived observation" not in body
    assert client.get(f"{env['base']}/matches/{mid}", headers=_headers("a")).json["capture_meta"] == match.capture_meta


@pytest.mark.parametrize("role", ["coach", "analyst", "viewer"])
def test_supported_admin_import_stays_legacy(env, client, club_app, monkeypatch, role):
    from scripts.dev.bridge_match_to_club import bridge_match_to_club
    from src.models.funding import ClubProgram

    monkeypatch.setattr(video_storage, "is_configured", lambda: False)
    r = client.post("/api/admin/video/matches", json={"team_id": club_app.c2["team"]}, headers=_admin_headers())
    assert r.status_code == 201
    mid = r.json["id"]
    base = f"/api/admin/video/matches/{mid}"
    assert (
        client.put(
            base + "/roster",
            json={"entries": [{"player_name": "Synthetic imported player", "jersey_number": 7}]},
            headers=_admin_headers(),
        ).status_code
        == 200
    )
    out = bridge_match_to_club(
        match_id=mid, manager_email="manager-a@c2.example", program_name=db.session.get(ClubProgram, env["pid"]).name
    )
    db.session.commit()
    assert out["program_id"] == env["pid"]
    assert _kinds(mid) == []
    member = out["members"][0]["club_roster_member_id"]
    assert (
        client.patch(f"{env['base']}/roster/{member}", json={"squad_id": env["sa"]}, headers=_headers("a")).status_code
        == 200
    )
    assert (
        client.patch(f"{env['base']}/matches/{mid}", json={"squad_id": env["sa"]}, headers=_headers("a")).status_code
        == 200
    )
    _join(client, env, role, role, squads=[env["sa"]])
    h = _h(_email(role))
    monkeypatch.setattr(video_storage, "is_configured", lambda: True)
    monkeypatch.setattr(video_storage, "mint_upload_sas", lambda path: {"upload_url": "https://example.invalid/upload"})
    monkeypatch.setattr(
        video_storage, "verify_uploaded_blob", lambda path: {"ok": True, "etag": "import-etag", "size_bytes": 10}
    )
    for flag in ["false", "true"]:
        monkeypatch.setenv("CLUB_STAFF_ACCESS_ENABLED", flag)
        for prefix, headers in [(base, _admin_headers()), (f"{env['base']}/matches/{mid}", _headers("a"))]:
            locked = flag == "true" and prefix != base
            assert client.post(prefix + "/sas", headers=headers).status_code == (409 if locked else 200)
            assert client.post(prefix + "/upload-complete", json={}, headers=headers).status_code == 200
        assert _kinds(mid) == []
    for suffix in ["", "/media-token", "/reel", "/report"]:
        assert client.get(f"{env['base']}/matches/{mid}{suffix}", headers=h).status_code == 404
