# ruff: noqa: F401, F811
"""RA2V4 regressions: the reviewer's fix-4 boundary probes with every exposure reversed (synthetic data only).

N1a scoped footage is signed for the immutable verified snapshot (real SAS code, fake storage
client); N1b club re-attestation cannot change a completed recording; N3a admin CREATE strips
client local paths; N4a every scoped write response uses the readiness-aware DTO.
"""

from datetime import timedelta
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest
from src.models.club_invitation import ClubInvitation, utcnow
from src.models.league import db
from src.models.player_feedback import PlayerFeedback
from src.models.showcase import PlayerProfileClaim
from src.models.video import VideoMatch, VideoPlayerReport, VideoRosterEntry
from src.services import video_storage
from test_club_console import _admin_headers
from test_club_staff_access import _email, _h, _headers, _join, _match, client, club_app, env
from test_club_staff_access_coverage import _kinds, _put, _upload


def _ready(env, client, monkeypatch, role):
    monkeypatch.setattr(video_storage, "is_configured", lambda: True)
    monkeypatch.setattr(video_storage, "mint_upload_sas", lambda path: {"upload_url": "https://example.invalid/upload"})
    mid = _match(client, env, "sa", uploaded=False)
    assert _put(client, env, mid, [env["m1"]]).status_code == 200
    _upload(client, env, monkeypatch, mid, etag="old-verified-etag")
    _join(client, env, role, role, squads=[env["sa"]])
    h = _h(_email(role))
    token = client.get(f"{env['base']}/matches/{mid}/media-token", headers=h)
    assert token.status_code == 200, token.json
    return (mid, db.session.get(VideoMatch, mid), h, token.json["token"])


@pytest.mark.parametrize("role", ["coach", "analyst", "viewer"])
def test_scoped_footage_is_signed_for_the_immutable_snapshot(env, client, monkeypatch, role):
    mid, match, h, token = _ready(env, client, monkeypatch, role)
    storage = {"etag": "old-verified-etag", "bytes": b"OLD verified bytes"}
    events = []

    class Blob:
        def get_blob_properties(self):
            props = SimpleNamespace(size=len(storage["bytes"]), etag=storage["etag"])
            events.append(("properties_snapshot", props.etag))
            storage.update(etag="new-unverified-etag", bytes=b"NEW uncompleted synthetic replacement")
            events.append(("original_write_sas_overwrite", storage["etag"]))
            return props

    class Service:
        account_name = "syntheticreview"
        url = "https://syntheticreview.blob.core.windows.net/"
        credential = SimpleNamespace(account_key="c3ludGhldGljLXJldmlldy1rZXk=")

        def get_blob_client(self, container, path):
            assert path == match.blob_path
            return Blob()

    monkeypatch.setattr(video_storage, "verify_uploaded_blob", _real_verify)
    monkeypatch.setattr(video_storage, "_service_client", lambda: Service())
    r = client.get(f"/api/admin/video/matches/{mid}/footage?token={token}")
    assert r.status_code == 302, r.json
    query = parse_qs(urlsplit(r.headers["Location"]).query)
    assert match.scoped_snapshot == "snap-old-verified-etag"
    assert query["sp"] == ["r"] and query["sr"] == ["bs"] and (query["snapshot"] == [match.scoped_snapshot])
    assert urlsplit(r.headers["Location"]).path.endswith("/" + match.blob_path)
    assert match.blob_etag == "old-verified-etag" and storage["etag"] == "new-unverified-etag"
    r2 = client.get(f"/api/admin/video/matches/{mid}/footage?token={token}")
    assert r2.status_code == 404
    storage.update(etag="old-verified-etag")
    manager = client.get(f"{env['base']}/matches/{mid}/media-token", headers=_headers("a")).json["token"]
    base = client.get(f"/api/admin/video/matches/{mid}/footage?token={manager}")
    assert base.status_code == 302 and "snapshot" not in parse_qs(urlsplit(base.headers["Location"]).query)


_real_verify = video_storage.verify_uploaded_blob


@pytest.mark.parametrize("role", ["coach", "analyst", "viewer"])
def test_club_reattestation_cannot_change_a_completed_recording(env, client, monkeypatch, role):
    mid, match, h, token = _ready(env, client, monkeypatch, role)
    before = match.blob_path
    assert client.post(f"{env['base']}/matches/{mid}/sas", headers=_headers("a")).status_code == 409
    monkeypatch.setattr(
        video_storage, "verify_uploaded_blob", lambda path: {"ok": True, "etag": "replacement-etag", "size_bytes": 10}
    )
    assert client.get(f"{env['base']}/matches/{mid}/media-token", headers=h).status_code == 404
    actor = h if role != "viewer" else _headers("a")
    completed = client.post(f"{env['base']}/matches/{mid}/upload-complete", json={}, headers=actor)
    assert completed.status_code == 409 and completed.json == {"error": "recording_locked"}
    assert match.blob_path == before and match.blob_etag == match.scoped_ready_etag == "old-verified-etag"
    assert match.scoped_snapshot == "snap-old-verified-etag"
    assert client.get(f"{env['base']}/matches/{mid}/media-token", headers=h).status_code == 404
    signed = []
    monkeypatch.setattr(
        video_storage, "mint_media_read_sas", lambda path, **kw: signed.append(path) or "https://example.invalid/new"
    )
    assert client.get(f"/api/admin/video/matches/{mid}/footage?token={token}").status_code == 404 and signed == []
    monkeypatch.setattr(
        video_storage, "verify_uploaded_blob", lambda path: {"ok": True, "etag": "old-verified-etag", "size_bytes": 10}
    )
    retry = client.post(f"{env['base']}/matches/{mid}/upload-complete", json={}, headers=actor)
    assert retry.status_code == 200 and match.scoped_snapshot == "snap-old-verified-etag"
    assert client.get(f"{env['base']}/matches/{mid}/media-token", headers=h).status_code == 200
    monkeypatch.setattr(video_storage, "mint_upload_sas", lambda path: {"upload_url": "https://example.invalid/upload"})
    assert client.post(f"/api/admin/video/matches/{mid}/sas", headers=_admin_headers()).status_code == 200
    assert match.scoped_ready_etag == "replacing" and match.scoped_snapshot is None
    assert client.get(f"{env['base']}/matches/{mid}/media-token", headers=h).status_code == 404
    monkeypatch.setattr(
        video_storage, "verify_uploaded_blob", lambda path: {"ok": True, "etag": "replacement-etag", "size_bytes": 10}
    )
    replaced = client.post(f"{env['base']}/matches/{mid}/upload-complete", json={}, headers=actor)
    assert replaced.status_code == 200
    assert (
        match.blob_etag == match.scoped_ready_etag == "replacement-etag"
        and match.scoped_snapshot == "snap-replacement-etag"
    )
    assert client.get(f"{env['base']}/matches/{mid}/media-token", headers=h).status_code == 200
    monkeypatch.setenv("CLUB_STAFF_ACCESS_ENABLED", "false")
    monkeypatch.setattr(
        video_storage, "verify_uploaded_blob", lambda path: {"ok": True, "etag": "flag-off-etag", "size_bytes": 10}
    )
    assert (
        client.post(f"{env['base']}/matches/{mid}/upload-complete", json={}, headers=_headers("a")).status_code == 200
    )


@pytest.mark.parametrize("role", ["coach", "analyst"])
def test_scoped_write_responses_use_readiness_aware_dto(env, client, monkeypatch, role):
    mid, match, h, token = _ready(env, client, monkeypatch, role)
    match.capture_meta = {
        "qwen_analysis": {"window_captions": [{"box_t": 23, "caption": "SYNTHETIC retained derived caption"}]}
    }
    db.session.commit()
    assert client.post(f"/api/admin/video/matches/{mid}/sas", headers=_admin_headers()).status_code == 200
    assert match.scoped_ready_etag == "replacing"
    detail = client.get(f"{env['base']}/matches/{mid}", headers=h)
    assert detail.status_code == 200 and "capture_meta" not in detail.json
    assert client.get(f"{env['base']}/matches/{mid}/reel", headers=h).status_code == 404
    r = client.patch(f"{env['base']}/matches/{mid}", json={"opponent_name": "Renamed"}, headers=h)
    allowed = {"id", "club_program_id", "squad_id", "opponent_name", "match_date", "competition", "status"}
    assert r.status_code == 200 and set(r.json) <= allowed and (r.json["opponent_name"] == "Renamed")
    assert "SYNTHETIC retained derived caption" not in r.get_data(as_text=True)
    monkeypatch.setattr(
        video_storage, "verify_expected_blob", lambda path, etag: {"ok": True, "etag": etag, "size_bytes": 10}
    )
    match.kickoff_s = 0
    db.session.commit()
    queued = client.post(f"{env['base']}/matches/{mid}/process", json={}, headers=h)
    assert queued.status_code == 202 and set(queued.json["match"]) <= allowed
    done = client.post(f"{env['base']}/matches/{mid}/upload-complete", json={}, headers=h)
    assert done.status_code == 200 and "SYNTHETIC retained derived caption" in done.get_data(as_text=True)
    created = client.post(
        f"{env['base']}/matches",
        json={
            "opponent_name": "New",
            "squad_id": env["sa"],
            "capture_meta": {"qwen_analysis": {"caption": "client supplied"}},
        },
        headers=h,
    )
    assert created.status_code == 201 and set(created.json) <= allowed | {"upload", "upload_unavailable"}
    full = client.patch(f"{env['base']}/matches/{mid}", json={"opponent_name": "Renamed again"}, headers=_headers("a"))
    assert full.json["capture_meta"] == match.capture_meta


def test_admin_create_strips_client_local_artifact(env, client, club_app, monkeypatch, tmp_path):
    monkeypatch.setattr(video_storage, "is_configured", lambda: False)
    p = tmp_path / "synthetic.mp4"
    p.write_bytes(b"SYNTHETIC foreign-match bytes")
    r = client.post(
        "/api/admin/video/matches",
        json={"team_id": club_app.c2["team"], "capture_meta": {"local": {"footage": str(p)}}},
        headers=_admin_headers(),
    )
    assert r.status_code == 201 and "local" not in (r.json["capture_meta"] or {})
    mid = r.json["id"]
    assert _kinds(mid) == []
    assert "local" not in (db.session.get(VideoMatch, mid).capture_meta or {})
    t = client.get(f"/api/admin/video/matches/{mid}/media-token", headers=_admin_headers()).json["token"]
    served = client.get(f"/api/admin/video/matches/{mid}/footage?token={t}")
    assert served.status_code == 404 and served.data != p.read_bytes()
    db.session.get(VideoMatch, mid).capture_meta = {"local": {"footage": str(p)}}
    db.session.commit()
    assert client.get(f"/api/admin/video/matches/{mid}/footage?token={t}").data == p.read_bytes()


@pytest.mark.parametrize("scenario", ["moved_member", "admin_replacing", "deleted_match"])
def test_feedback_serializers_replay_revision_progress_redact(env, client, club_app, monkeypatch, scenario):
    from test_club_staff_access_ra2v2 import _minor

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
    ref = {"label": "SYNTHETIC PRIVATE evidence", "timestamp_s": 23}
    data = {
        "invitation_id": invite.id,
        "client_request_id": str(uuid4()),
        "title": "Coach title",
        "body": "Coach prose survives.",
        "video_match_id": mid,
        "observation_refs": [ref],
        "development_action": {"focus": "touch", "practice": "receive", "success": "three", "review_on": None},
    }
    r = client.post(f"{env['base']}/player-feedback", json=data, headers=_headers("a"))
    assert r.status_code == 201, r.json
    fid = r.json["feedback"]["id"]
    thread = r.json["feedback"]["thread_id"]
    _join(client, env, "coach", "coach", squads=[env["sa"]])
    h = _h(_email("coach"))
    if scenario == "moved_member":
        assert (
            client.patch(
                f"{env['base']}/roster/{minor}", json={"squad_id": env["sb"]}, headers=_headers("a")
            ).status_code
            == 200
        )
    elif scenario == "admin_replacing":
        match.status = "uploaded"
        db.session.commit()
        monkeypatch.setattr(video_storage, "is_configured", lambda: True)
        monkeypatch.setattr(
            video_storage, "mint_upload_sas", lambda path: {"upload_url": "https://example.invalid/upload"}
        )
        assert client.post(f"/api/admin/video/matches/{mid}/sas", headers=_admin_headers()).status_code == 200
    else:
        db.session.get(PlayerFeedback, fid).video_match_id = None
        db.session.commit()
    for method, url, body in [
        ("GET", f"{env['base']}/player-feedback/{fid}", None),
        ("GET", f"{env['base']}/player-feedback", None),
        ("GET", f"{env['base']}/roster/{env['m1']}/profile", None),
        ("POST", f"{env['base']}/player-feedback", data),
    ]:
        result = client.open(url, method=method, json=body, headers=h)
        assert result.status_code == 200, (method, url, result.status_code, result.json)
        assert "SYNTHETIC PRIVATE evidence" not in result.get_data(as_text=True)
    feedback = db.session.get(PlayerFeedback, fid)
    feedback.development_progress = {
        "version": 1,
        "status": "ready_for_review",
        "reflection": "Player text",
        "history": [],
    }
    db.session.commit()
    review = client.post(
        f"{env['base']}/player-feedback/{thread}/progress-review",
        json={"expected_revision": 1, "expected_version": 1, "status": "reviewed", "note": "Coach text"},
        headers=h,
    )
    assert review.status_code == 200 and review.json["feedback"]["observation_refs"] == [], review.json
    assert review.json["feedback"]["body"] == "Coach prose survives."
    assert client.get(f"{env['base']}/player-feedback/{fid}", headers=_headers("a")).json["feedback"][
        "observation_refs"
    ] == [ref]


@pytest.mark.parametrize("flag", ["true", "false"])
@pytest.mark.parametrize("endpoint", ["club", "admin"])
def test_capture_questionnaire_patch_cannot_add_or_replace_local(env, client, club_app, monkeypatch, flag, endpoint):
    monkeypatch.setenv("CLUB_STAFF_ACCESS_ENABLED", flag)
    monkeypatch.setattr(video_storage, "is_configured", lambda: False)
    url = f"{env['base']}/matches" if endpoint == "club" else "/api/admin/video/matches"
    headers = _headers("a") if endpoint == "club" else _admin_headers()
    data = {"squad_id": env["sa"]} if endpoint == "club" else {"team_id": club_app.c2["team"]}
    created = client.post(url, json=data, headers=headers)
    assert created.status_code == 201
    mid = created.json["id"]
    match = db.session.get(VideoMatch, mid)
    for value in [
        {"capture_meta": {"local": {"footage": "/tmp/client.mp4"}, "camera_view": "panoramic"}},
        {"local": {"footage": "/tmp/client.mp4"}, "camera_motion": "fixed"},
    ]:
        patched = client.patch(f"{url}/{mid}", json=value, headers=headers)
        assert patched.status_code == 200, patched.json
        assert "local" not in (match.capture_meta or {})
    match.capture_meta = {**(match.capture_meta or {}), "local": {"footage": "/tmp/server-only.mp4"}}
    db.session.commit()
    patched = client.patch(
        f"{url}/{mid}",
        json={"capture_meta": {"local": {"footage": "/tmp/client.mp4"}, "camera_view": "wide_fixed"}},
        headers=headers,
    )
    assert patched.status_code == 200 and match.capture_meta["local"] == {"footage": "/tmp/server-only.mp4"}


@pytest.mark.parametrize("role", ["coach", "analyst", "viewer"])
@pytest.mark.parametrize("state", ["unfinished", "replacing"])
def test_detail_list_workflow_dto_all_unready_states(env, client, monkeypatch, role, state):
    monkeypatch.setattr(video_storage, "is_configured", lambda: True)
    monkeypatch.setattr(video_storage, "mint_upload_sas", lambda path: {"upload_url": "https://example.invalid/upload"})
    mid = _match(client, env, "sa", uploaded=False)
    assert _put(client, env, mid, [env["m1"]]).status_code == 200
    if state == "replacing":
        _upload(client, env, monkeypatch, mid)
        assert client.post(f"/api/admin/video/matches/{mid}/sas", headers=_admin_headers()).status_code == 200
    match = db.session.get(VideoMatch, mid)
    match.capture_meta = {"qwen_analysis": {"caption": "SYNTHETIC hidden derived fields"}}
    db.session.commit()
    _join(client, env, role, role, squads=[env["sa"]])
    h = _h(_email(role))
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
    detail = client.get(f"{env['base']}/matches/{mid}", headers=h)
    listing = client.get(f"{env['base']}/matches", headers=h)
    assert detail.status_code == listing.status_code == 200
    assert set(detail.json) <= allowed
    row = next(m for m in listing.json["matches"] if m["id"] == mid)
    assert set(row) <= allowed
    assert "SYNTHETIC hidden derived fields" not in detail.get_data(as_text=True) + listing.get_data(as_text=True)
    assert all(e["club_roster_member_id"] == env["m1"] for e in detail.json["roster"])
