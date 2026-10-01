# ruff: noqa: F811
"""RC2 probes reversed into regression checks (real source verifier; storage only stubbed)."""

from datetime import timedelta
from unittest.mock import Mock
from uuid import uuid4

import pytest
import sqlalchemy as sa
from src.auth import _user_serializer
from src.models.club_access import ClubAccessGrant
from src.models.funding import ClubProgramClaim, ClubProgramManager
from src.models.highlights import (
    HighlightConsentEvent,
    HighlightFootageReview,
    HighlightRenderJob,
    PlayerHighlight,
    now,
)
from src.models.league import db
from src.services import highlights, highlights_storage, video_storage
from src.services.account import _SchemaView
from src.services.highlights_account import erase_highlights
from src.services.highlights_retention import sweep_highlights
from src.workers import highlight_worker as worker
from test_highlights import approve, headers, pick, ready, world  # noqa: F401


def club_base(w):
    return f"/api/club/{w['program'].id}/matches/{w['match'].id}"


def assert_hidden(w, row):
    client = w["app"].test_client()
    for method in ("get", "head"):
        assert getattr(client, method)(f"/api/highlights/{row.id}/clip").status_code == 404
    assert client.get(f"/api/players/{row.signed_id}/highlights").json == {"highlights": []}
    assert client.get("/api/programs/test-fc/highlights").json == {"highlights": []}
    assert client.get(f"/api/me/highlight-requests/{row.id}/preview", headers=headers(w["player"])).status_code == 404
    assert client.get(f"{club_base(w)}/highlights/{row.id}/preview", headers=headers(w["manager"])).status_code == 404


@pytest.mark.parametrize("expired", [False, True])
@pytest.mark.parametrize("action", ["club", "private", "player", "admin"])
def test_f1_takedown_survives_missing_or_expired_raw(world, monkeypatch, expired, action):
    row = ready(world)
    assert approve(world, row).status_code == 200
    output = row.output_blob_path
    if expired:
        from src.services.video_retention import expire_raw_footage

        world["match"].expires_at = now() - timedelta(days=1)
        db.session.commit()
        monkeypatch.setattr(video_storage, "delete_blob", lambda path: True)
        assert expire_raw_footage()["expired"] == 1
    # Do not patch scoped_recording_intact: verify_expected_blob is the real boundary.
    monkeypatch.setattr(video_storage, "verify_expected_blob", Mock(side_effect=RuntimeError("storage offline")))
    monkeypatch.setattr(
        highlights_storage, "output_read_url", lambda *args, **kwargs: "https://clips.example.test/standalone"
    )
    client = world["app"].test_client()
    assert client.get(f"/api/highlights/{row.id}/clip").status_code == 302
    listing = client.get(f"{club_base(world)}/highlights", headers=headers(world["manager"]))
    assert listing.status_code == 200 and listing.json["candidates"] == []
    assert listing.json["highlights"][0]["id"] == row.id
    if action == "club":
        result = client.delete(f"{club_base(world)}/highlights/{row.id}", headers=headers(world["manager"]))
    elif action == "private":
        result = client.post(
            f"{club_base(world)}/highlight-review",
            json={"classification": "private"},
            headers=headers(world["manager"]),
        )
    elif action == "player":
        result = client.post(f"/api/me/highlight-requests/{row.id}/revoke", headers=headers(world["player"]))
    else:
        monkeypatch.setenv("ADMIN_API_KEY", "c2-test-key")
        token = _user_serializer().dumps({"email": world["manager"].email, "role": "admin"})
        auth = {"Authorization": "Bearer " + token, "X-API-Key": "c2-test-key"}
        assert (
            client.post(f"/api/admin/highlights/{row.id}/takedown", headers=headers(world["manager"])).status_code
            == 401
        )
        assert (
            client.post(
                f"/api/admin/highlights/{row.id}/takedown", headers={"Authorization": "Bearer " + token}
            ).status_code
            == 401
        )
        result = client.post(f"/api/admin/highlights/{row.id}/takedown", headers=auth)
    assert result.status_code == 200, result.json
    assert_hidden(world, row)
    cleanup = HighlightRenderJob.query.filter_by(kind="highlight_delete").all()
    assert output in {job.blob_path for job in cleanup}
    for job in cleanup:
        job.created_at = now() - timedelta(seconds=1)
    db.session.commit()
    removed = []
    monkeypatch.setenv("HIGHLIGHTS_ENABLED", "0")
    monkeypatch.setattr(video_storage, "delete_blob", lambda path: removed.append(path) or True)
    claimed = worker.claim_next()
    assert claimed and worker.run_one(*claimed)
    assert output in removed


@pytest.mark.parametrize(
    "name",
    ["U16s", "U-16", "Under 16s", "Academy U17s", "u18", "u9s", "Youth", "Juniors", "Colts", "Minis", "Under-15 Girls"],
)
def test_f2_youth_names_always_private(world, name):
    world["squad"].name = name
    db.session.commit()
    assert pick(world).status_code == 422
    response = (
        world["app"]
        .test_client()
        .post(
            f"{club_base(world)}/highlight-review",
            json={"classification": "adult_only", "all_visible_people_adults": True, "squad_adult_attested": True},
            headers=headers(world["manager"]),
        )
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "kind,age,allowed",
    [
        ("age_group", None, False),
        ("age_group", 18, False),
        ("age_group", 19, False),
        ("other", None, False),
        ("reserves", None, True),
    ],
)
def test_f2_structured_squad_data_first(world, kind, age, allowed):
    world["squad"].kind, world["squad"].age_limit = kind, age
    db.session.commit()
    assert (pick(world).status_code == 201) == allowed


def test_f2_unknown_senior_requires_separate_whole_club_attestation(world):
    world["squad"].kind = "other"
    db.session.commit()
    client = world["app"].test_client()
    body = {"classification": "adult_only", "all_visible_people_adults": True}
    path = f"{club_base(world)}/highlight-review"
    assert client.post(path, json=body, headers=headers(world["manager"])).status_code == 422
    body["squad_adult_attested"] = True
    assert client.post(path, json=body, headers=headers(world["manager"])).status_code == 200
    assert pick(world).status_code == 201


def clone_highlights(row, count):
    data = {column.name: getattr(row, column.name) for column in PlayerHighlight.__table__.columns}
    for _ in range(count - 1):
        hid = str(uuid4())
        values = dict(data, id=hid, pick_key=uuid4().hex, output_blob_path=f"highlights/{hid}/{uuid4()}.mp4")
        db.session.add(PlayerHighlight(**values))
    db.session.commit()


@pytest.mark.parametrize("count", [1, 25, 100])
def test_f3_queries_bounded_for_every_list(world, count):
    row = ready(world)
    assert approve(world, row).status_code == 200
    clone_highlights(row, count)
    client = world["app"].test_client()
    auth = {"player": headers(world["player"]), "manager": headers(world["manager"])}
    paths = [
        (f"/api/players/{row.signed_id}/highlights", {}, min(count, 100), 12),
        ("/api/programs/test-fc/highlights", {}, min(count, 100), 12),
        ("/api/me/highlight-requests", auth["player"], min(count, 30), 14),
        (f"{club_base(world)}/highlights", auth["manager"], count, 15),
    ]
    for path, header, expected, maximum in paths:
        statements = []

        def executed(*args):
            statements.append(args[2])

        db.session.remove()  # No warm ORM identities conceal N+1 work.
        sa.event.listen(db.engine, "before_cursor_execute", executed)
        try:
            response = client.get(path, headers=header)
        finally:
            sa.event.remove(db.engine, "before_cursor_execute", executed)
        assert response.status_code == 200, response.json
        assert len(response.json["highlights"]) == expected
        print(f"RC2 F3 {path}: clips={count}, SQL={len(statements)}")
        assert len(statements) <= maximum, (path, len(statements), statements)


def test_f4_short_read_only_blob_scoped_capability(world, monkeypatch):
    row = ready(world)
    client = Mock()
    client.get_blob_properties.return_value.etag = row.output_etag
    service = Mock()
    service.get_blob_client.return_value = client
    monkeypatch.setattr(video_storage, "_service_client", lambda: service)
    mint = Mock(return_value="https://clips.example.test/standalone")
    monkeypatch.setattr(video_storage, "mint_media_read_sas", mint)
    expiry = now().replace(tzinfo=__import__("datetime").UTC) + timedelta(seconds=60)
    assert (
        highlights_storage.output_read_url(row.output_blob_path, row.output_etag, expires_at=expiry)
        == mint.return_value
    )
    mint.assert_called_once_with(row.output_blob_path, seconds=60, expires_at=expiry)
    service.get_blob_client.assert_called_once_with(video_storage._container(), row.output_blob_path)
    client.download_blob.assert_not_called()
    assert "matches/" not in mint.call_args.args[0]
    with pytest.raises(ValueError):
        highlights_storage.output_read_url(world["match"].blob_path, row.output_etag, expires_at=expiry)
    client.get_blob_properties.return_value.etag = "changed"
    with pytest.raises(ValueError):
        highlights_storage.output_read_url(row.output_blob_path, row.output_etag, expires_at=expiry)


def test_f5_decline_fences_worker_deletes_preview_and_requires_new_preview(world):
    row = ready(world)
    path = row.output_blob_path
    client = world["app"].test_client()
    response = client.post(
        f"/api/me/highlight-requests/{row.id}/decision",
        json={"decision": "private", "version": row.version},
        headers=headers(world["player"]),
    )
    assert response.status_code == 200
    db.session.refresh(row)
    assert row.render_status == "stale" and row.output_blob_path is None
    assert HighlightRenderJob.query.filter_by(kind="highlight_delete", blob_path=path).count() == 1
    assert approve(world, row).status_code == 422
    assert (
        client.get(f"/api/me/highlight-requests/{row.id}/preview", headers=headers(world["player"])).status_code == 404
    )
    assert (
        client.post(f"/api/me/highlight-requests/{row.id}/retry", headers=headers(world["player"])).status_code == 202
    )
    assert approve(world, row).status_code == 422
    claimed = worker.claim_next()
    # Immediate declined-output cleanup precedes the fresh cut.
    assert claimed and db.session.get(HighlightRenderJob, claimed[0]).kind == "highlight_delete"
    assert worker.finish(*claimed)
    claimed = worker.claim_next()
    assert claimed and worker.finish(*claimed, output_etag="recut", output_size=20)
    assert approve(world, row).status_code == 200


@pytest.mark.parametrize("raw_expired", [False, True])
def test_f5_pending_retention_dark_and_bounded(world, monkeypatch, raw_expired):
    row = ready(world)
    path = row.output_blob_path
    if raw_expired:
        assert world["match"].status == "finalized"
        world["match"].status, world["match"].blob_path, world["match"].blob_etag = "expired", None, None
    else:
        world["match"].expires_at = now() - timedelta(seconds=1)
    db.session.commit()
    monkeypatch.setenv("HIGHLIGHTS_ENABLED", "0")
    assert sweep_highlights(limit=1)["expired"] == 1
    assert HighlightRenderJob.query.filter_by(kind="highlight_delete", blob_path=path).count() == 1
    db.session.refresh(row)
    row.revoked_at = now() - timedelta(days=91)
    world["review"].reviewed_at = now() - timedelta(days=91)
    for event in HighlightConsentEvent.query.all():
        event.created_at = now() - timedelta(days=91)
    for job in HighlightRenderJob.query.filter_by(kind="highlight_cut"):
        job.created_at = job.completed_at = now() - timedelta(days=91)
    db.session.commit()
    result = sweep_highlights(limit=10)
    assert result["highlights"] == 1 and PlayerHighlight.query.count() == 0
    assert HighlightConsentEvent.query.count() == 0 and HighlightFootageReview.query.count() == 0
    assert HighlightRenderJob.query.filter_by(kind="highlight_cut").count() == 0
    assert HighlightRenderJob.query.filter_by(kind="highlight_delete").count() > 0


def test_f6_no_blind_approval(world):
    assert pick(world).status_code == 201
    row = PlayerHighlight.query.one()
    assert approve(world, row).status_code == 422
    dto = (
        world["app"]
        .test_client()
        .get("/api/me/highlight-requests", headers=headers(world["player"]))
        .json["highlights"][0]
    )
    assert dto["can_approve"] is False and dto["preview_url"] is None
    claimed = worker.claim_next()
    assert worker.finish(*claimed, output_etag="preview", output_size=20)
    assert row.player_decision == "pending" and not highlights.public(row)
    assert approve(world, row).status_code == 200


def test_f8_second_manager_same_source_preserves_consent(world):
    row = ready(world)
    assert approve(world, row).status_code == 200
    claim = ClubProgramClaim(program_id=world["program"].id, user_account_id=world["stranger"].id, status="approved")
    db.session.add(claim)
    db.session.flush()
    db.session.add(
        ClubProgramManager(
            program_id=world["program"].id,
            user_account_id=world["stranger"].id,
            source_claim_id=claim.id,
            status="active",
            granted_by="test-admin",
        )
    )
    db.session.commit()
    before = (row.version, row.source_version, world["review"].reviewed_at, world["review"].reviewer_user_id)
    result = (
        world["app"]
        .test_client()
        .post(
            f"{club_base(world)}/highlight-review",
            json={"classification": "adult_only", "all_visible_people_adults": True},
            headers=headers(world["stranger"]),
        )
    )
    assert result.status_code == 200
    db.session.refresh(row)
    db.session.refresh(world["review"])
    assert (row.version, row.source_version, world["review"].reviewed_at, world["review"].reviewer_user_id) == before
    assert highlights.public(row)
    assert HighlightRenderJob.query.filter_by(kind="highlight_delete").count() == 0


def test_f9_removed_picks_do_not_consume_live_cap(world):
    row = ready(world)
    clone_highlights(row, 100)
    for removed in PlayerHighlight.query.all():
        highlights.revoke(removed, world["manager"].id, "club_remove")
    db.session.commit()
    response = pick(world, title="new live pick")
    assert response.status_code == 201
    assert PlayerHighlight.query.filter(PlayerHighlight.revoked_at.is_(None)).count() == 1


def test_f10_recording_date_after_upload_cannot_age_up_childhood(world):
    world["match"].uploaded_at = now() - timedelta(days=900)
    world["local"].birth_date = now().date().replace(year=now().year - 19)
    world["local"].birth_year = world["local"].birth_date.year
    db.session.commit()
    assert pick(world).status_code == 422
    response = (
        world["app"]
        .test_client()
        .post(
            f"{club_base(world)}/highlight-review",
            json={"classification": "adult_only", "all_visible_people_adults": True, "squad_adult_attested": True},
            headers=headers(world["manager"]),
        )
    )
    assert response.status_code == 422 and response.json["error"] == "recording_date_after_upload"


@pytest.mark.parametrize("bad", ["%00", "not-a-uuid", "x" * 36])
def test_f11_invalid_ids_are_400_without_db_lookup(world, bad):
    client = world["app"].test_client()
    assert client.get(f"/api/highlights/{bad}/clip").status_code == 400
    assert (
        client.post(
            f"/api/me/highlight-requests/{bad}/decision",
            headers=headers(world["player"]),
            json={"decision": "approve", "version": 1},
        ).status_code
        == 400
    )
    assert client.get(f"/api/me/highlight-requests/{bad}/preview", headers=headers(world["player"])).status_code == 400


def test_f12_exhausted_attempt_cleanup_and_next_healthy_job(world):
    assert pick(world).status_code == 201
    first = worker.claim_next()
    job = db.session.get(HighlightRenderJob, first[0])
    final_path = job.blob_path
    job.attempt = worker.MAX_ATTEMPTS
    job.lease_expires_at = now() - timedelta(seconds=1)
    healthy = HighlightRenderJob(
        kind="highlight_cut", highlight_id=job.highlight_id, source_version=job.source_version, created_at=now()
    )
    db.session.add(healthy)
    db.session.commit()
    claimed = worker.claim_next()
    assert claimed and claimed[0] == healthy.id
    db.session.refresh(job)
    assert job.status == "failed"
    assert HighlightRenderJob.query.filter_by(kind="highlight_delete", blob_path=final_path).count() == 1


def test_f12_batch_reuses_frozen_source_and_replaces_changed_generation(world, monkeypatch, tmp_path):
    download = Mock()
    monkeypatch.setattr(highlights_storage, "download_source", download)
    batch = worker.SourceBatch(tmp_path)
    for _ in range(25):
        assert batch.get("private/match.mp4", "snapshot", "etag") == tmp_path / "source.mp4"
    assert download.call_count == 1
    batch.get("private/match.mp4", "new-snapshot", "new-etag")
    assert download.call_count == 2


@pytest.mark.parametrize("sqlstate", ["40P01", "40001"])
def test_f13_conflict_maps_to_retry_409(world, monkeypatch, sqlstate):
    from sqlalchemy.exc import OperationalError

    row = ready(world)

    class Error(Exception):
        pass

    error = Error("concurrent writer")
    error.sqlstate = sqlstate
    monkeypatch.setattr(highlights, "decide", Mock(side_effect=OperationalError("", {}, error)))
    response = approve(world, row)
    assert response.status_code == 409 and response.json["error"] == "version_conflict"


def test_f15_staff_erasure_preserves_others_institutional_keys(world):
    row = ready(world)
    assert approve(world, row).status_code == 200
    world["manager"].account_status = "suspended"
    db.session.commit()
    assert highlights.public(row)
    assert erase_highlights(world["manager"].id, _SchemaView()) == {}
    db.session.commit()
    db.session.refresh(row)
    db.session.refresh(world["review"])
    assert row.picker_user_id is None and world["review"].reviewer_user_id is None
    assert highlights.public(row)
    assert HighlightRenderJob.query.filter_by(kind="highlight_delete").count() == 0
    assert HighlightConsentEvent.query.filter_by(action="club_pick").one().actor_user_id is None


@pytest.mark.parametrize("role", ["manager", "coach", "analyst", "viewer"])
def test_f16_unverified_staff_cannot_use_club_key(world, role):
    db.session.add(
        ClubAccessGrant(
            program_id=world["program"].id,
            user_account_id=world["stranger"].id,
            role=role,
            status="active",
            all_squads=True,
        )
    )
    db.session.commit()
    client = world["app"].test_client()
    auth = headers(world["stranger"])
    assert client.get(f"{club_base(world)}/highlights", headers=auth).status_code == 403
    assert client.post(f"{club_base(world)}/highlights", json={}, headers=auth).status_code == 403
    assert (
        client.post(
            f"{club_base(world)}/highlight-review",
            json={"classification": "adult_only", "all_visible_people_adults": True},
            headers=auth,
        ).status_code
        == 403
    )
    row = ready(world)
    assert client.delete(f"{club_base(world)}/highlights/{row.id}", headers=auth).status_code == 403


def test_f12_failed_generation_download_is_not_repeated_per_clip(world, monkeypatch, tmp_path):
    download = Mock(side_effect=RuntimeError("slow source"))
    monkeypatch.setattr(highlights_storage, "download_source", download)
    batch = worker.SourceBatch(tmp_path)
    for _ in range(25):
        with pytest.raises((ValueError, RuntimeError)):
            batch.get("private/match.mp4", "snapshot", "etag")
    assert download.call_count == 1
