# ruff: noqa: F811

"""Public transport authorizes current DB state before touching private storage."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import urlsplit

import pytest
from src.models.funding import ClubProgram
from src.models.league import db
from src.models.player_suppression import PlayerSuppression
from src.models.showcase import LocalPlayer
from src.models.tracked_player import TrackedPlayer
from src.services import showcase_media_storage as storage
from test_showcase_media import (  # noqa: F401
    PLAYER_ID,
    _approved_claim,
    _gps_jpeg,
    _seed_media,
    app,
    client,
)


@pytest.fixture
def photo(app):
    owner, _ = _approved_claim(PLAYER_ID, "media-owner@example.test")
    media = _seed_media(PLAYER_ID, owner.id)
    media.public_url = storage.publish(media.blob_path, _gps_jpeg())
    db.session.commit()
    return media


def url(photo):
    return f"{storage.PUBLIC_ROUTE_PREFIX}/{storage._published_blob_path(photo.blob_path)}"


def test_local_get_head_conditional_and_serializer(client, photo, monkeypatch):
    monkeypatch.setenv("PUBLIC_API_BASE_URL", "https://api.example.test/api/")
    public = client.get(f"/api/players/{PLAYER_ID}/showcase")
    assert public.json["photos"][0]["public_url"] == f"https://api.example.test{url(photo)}"
    response = client.get(url(photo))
    assert response.status_code == 200
    assert response.data == _gps_jpeg()
    assert response.content_type == "image/jpeg"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Cache-Control"] == "private, max-age=300, must-revalidate"
    etag = response.headers["ETag"]
    head = client.head(url(photo))
    assert head.status_code == 200 and not head.data
    assert head.headers["Content-Length"] == response.headers["Content-Length"]
    assert head.headers["ETag"] == etag
    cached = client.get(url(photo), headers={"If-None-Match": etag})
    assert cached.status_code == 304 and not cached.data
    assert cached.headers["X-Content-Type-Options"] == "nosniff"
    assert cached.headers["Cache-Control"] == "private, max-age=300, must-revalidate"
    assert client.get(url(photo), headers={"If-None-Match": '"other"'}).status_code == 200


@pytest.mark.parametrize("status", ["pending_upload", "pending", "rejected", "deleted"])
@pytest.mark.parametrize("method", ["get", "head"])
def test_media_revocation_precedes_cache_and_storage(client, photo, monkeypatch, status, method):
    path = url(photo)
    etag = client.get(path).headers["ETag"]
    if status == "deleted":
        db.session.delete(photo)
    else:
        photo.status = status
    db.session.commit()
    reader = Mock(side_effect=AssertionError("unauthorized storage access"))
    monkeypatch.setattr(storage, "published_response", reader)
    assert getattr(client, method)(path, headers={"If-None-Match": etag}).status_code == 404
    reader.assert_not_called()


def suppress(monkeypatch, **subject):
    monkeypatch.setenv("PLAYER_SUPPRESSION_ENCRYPTION_KEY", "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=")
    db.session.add(
        PlayerSuppression(
            **subject,
            status="active",
            reason_code="player_request",
            requester_role="player",
            requester_contact="synthetic@example.test",
            request_statement="Synthetic test",
        )
    )


@pytest.mark.parametrize(
    "gate", ["minor", "unknown_age", "suppressed", "club_bridge", "minor_bridge", "suppressed_bridge", "missing"]
)
def test_tracked_visibility(client, photo, monkeypatch, gate):
    player = TrackedPlayer.query.filter_by(player_api_id=PLAYER_ID).one()
    if gate in {"minor", "unknown_age"}:
        player.birth_date = date(2015, 1, 1) if gate == "minor" else None
        player.age = None
    elif gate == "missing":
        db.session.delete(player)
    elif gate == "suppressed":
        suppress(monkeypatch, player_api_id=PLAYER_ID)
    else:
        local = LocalPlayer(
            display_name="Synthetic Bridge", api_player_id=PLAYER_ID, status="approved", birth_year=2000
        )
        if gate == "club_bridge":
            local.provenance = "club"
        elif gate == "minor_bridge":
            local.birth_year = 2015
        db.session.add(local)
        db.session.flush()
        if gate == "suppressed_bridge":
            suppress(monkeypatch, local_player_id=local.id)
    db.session.commit()
    assert client.get(url(photo), headers={"If-None-Match": "*"}).status_code == 404


@pytest.mark.parametrize(
    "gate", ["adult", "minor", "unknown_age", "suppressed", "club", "pending", "rejected", "hidden", "merged"]
)
def test_local_visibility(client, photo, monkeypatch, gate):
    local = LocalPlayer(display_name="Synthetic Local", status="approved", birth_year=2000)
    db.session.add(local)
    db.session.flush()
    photo.player_api_id = None
    photo.local_player_id = local.id
    photo.blob_path = f"local-players/{local.id}/test.png"
    photo.public_url = storage.publish(photo.blob_path, _gps_jpeg())
    if gate == "minor":
        local.birth_year = 2015
    elif gate == "unknown_age":
        local.birth_year = None
    elif gate == "suppressed":
        suppress(monkeypatch, local_player_id=local.id)
    elif gate == "club":
        local.provenance = "club"
    elif gate in {"pending", "rejected", "hidden"}:
        local.status = gate
    elif gate == "merged":
        local.merged_into_local_player_id = local.id
    db.session.commit()
    assert client.get(url(photo)).status_code == (200 if gate == "adult" else 404)
    if gate == "adult":
        result = client.get(f"/api/local-players/{local.id}/showcase")
        assert result.json["photos"][0]["public_url"] == f"http://localhost{url(photo)}"


@pytest.mark.parametrize(
    "path",
    [
        "players/5001/arbitrary.jpg",
        "players/5001/../photo.jpg",
        "players/%2e%2e/photo.jpg",
        "players/5001/%252e%252e/photo.jpg",
        "players/5001/%5cphoto.jpg",
        "players/5001/%00photo.jpg",
        "club-player-photos/1/1/private.jpg",
        "published/players/5001/photo.jpg",
        "players/5001/photo.png",
    ],
)
def test_arbitrary_paths_fail_before_storage(client, photo, monkeypatch, path):
    reader = Mock(side_effect=AssertionError("unauthorized storage access"))
    monkeypatch.setattr(storage, "published_response", reader)
    assert client.get(f"{storage.PUBLIC_ROUTE_PREFIX}/{path}").status_code == 404
    reader.assert_not_called()


def test_dev_route_cannot_bypass_revocation_or_read_private_photos(client, photo):
    assert client.get(f"{storage.DEV_ROUTE_PREFIX}/published/{photo.public_url}").status_code == 404
    assert client.get(f"{storage.DEV_ROUTE_PREFIX}/club-player-photos/1/1/private.jpg").status_code == 404


def test_banner_only_current_path_even_if_old_file_survives(client, app, monkeypatch):
    monkeypatch.setenv("PUBLIC_API_BASE_URL", "https://api.example.test")
    old = storage.publish("club-banners/1/2/old.png", _gps_jpeg())
    new = storage.publish("club-banners/1/2/new.png", _gps_jpeg())
    club = ClubProgram(
        funding_league_id=1,
        name="Synthetic Club",
        legal_name="Synthetic Club",
        slug="synthetic-club",
        country="Japan",
        region="Test",
        banner_url=old,
    )
    db.session.add(club)
    db.session.commit()
    assert club.brand_dict()["banner_url"] == f"https://api.example.test{storage.PUBLIC_ROUTE_PREFIX}/{old}"
    old_url = urlsplit(club.brand_dict()["banner_url"]).path
    assert client.get(old_url).status_code == 200
    assert client.get(f"{storage.PUBLIC_ROUTE_PREFIX}/{new}").status_code == 404
    club.banner_url = new
    db.session.commit()
    assert storage.local_public_path(old).exists()
    assert client.get(old_url, headers={"If-None-Match": "*"}).status_code == 404
    assert client.get(urlsplit(club.brand_dict()["banner_url"]).path).status_code == 200
    db.session.delete(club)
    db.session.commit()
    assert client.get(f"{storage.PUBLIC_ROUTE_PREFIX}/{new}").status_code == 404


def azure(monkeypatch):
    sdk = Mock()
    blob = sdk.get_blob_client.return_value
    blob.get_blob_properties.return_value = SimpleNamespace(size=6, etag='"azure-etag"')
    blob.download_blob.return_value.chunks.return_value = iter([b"abc", b"def"])
    monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "synthetic-mocked-only")
    monkeypatch.setattr(storage, "_service_client", lambda: sdk)
    monkeypatch.setattr(storage, "_checked_containers", set())
    return sdk, blob


def test_azure_downloads_private_container_in_chunks(client, photo, monkeypatch):
    sdk, blob = azure(monkeypatch)
    response = client.get(url(photo))
    assert response.status_code == 200 and response.data == b"abcdef"
    assert response.content_type == "image/jpeg"
    assert response.headers["ETag"] == '"azure-etag"'
    sdk.get_blob_client.assert_called_once_with("showcase-media", photo.public_url)
    blob.download_blob.assert_called_once_with(offset=0, length=6, max_concurrency=1)
    blob.download_blob.return_value.readall.assert_not_called()
    sdk.get_container_client.return_value.create_container.assert_not_called()


@pytest.mark.parametrize(
    "method,headers,status", [("head", {}, 200), ("get", {"If-None-Match": 'W/"azure-etag"'}, 304)]
)
def test_azure_head_and_conditional_skip_download(client, photo, monkeypatch, method, headers, status):
    _, blob = azure(monkeypatch)
    response = getattr(client, method)(url(photo), headers=headers)
    assert response.status_code == status and not response.data
    blob.download_blob.assert_not_called()


def test_missing_or_oversized_azure_object(client, photo, monkeypatch):
    _, blob = azure(monkeypatch)
    blob.get_blob_properties.side_effect = storage.ResourceNotFoundError("missing")
    assert client.get(url(photo)).status_code == 404
    blob.get_blob_properties.side_effect = None
    blob.get_blob_properties.return_value.size = storage.max_photo_bytes() + 1
    assert client.get(url(photo)).status_code == 404
    blob.download_blob.assert_not_called()


@pytest.mark.parametrize("operation,container", [("publish", "showcase-media"), ("upload", "showcase-media-pending")])
def test_missing_container_logs_without_provisioning(app, monkeypatch, caplog, operation, container):
    sdk, blob = azure(monkeypatch)
    sdk.get_container_client.return_value.get_container_properties.side_effect = storage.ResourceNotFoundError(
        "missing"
    )
    monkeypatch.setattr(storage, "generate_blob_sas", lambda **kwargs: "synthetic-sas")
    if operation == "publish":
        assert storage.publish("players/1/2/a.png", b"jpeg") == "players/1/2/a.jpg"
    else:
        storage.mint_upload(1, 2, "image/jpeg")
    assert f"Required media container {container} is missing" in caplog.text
    sdk.get_container_client.return_value.create_container.assert_not_called()
    sdk.get_container_client.return_value.set_container_access_policy.assert_not_called()


@pytest.mark.parametrize(
    "base", ["https://api.example.test", "https://api.example.test/api/", "https://api.example.test/"]
)
def test_url_roundtrip_for_publication_and_cleanup(app, monkeypatch, base):
    monkeypatch.setenv("PUBLIC_API_BASE_URL", base)
    with app.test_request_context():
        path = storage.publish("players/1/2/unique.webp", b"jpeg")
        result = storage.published_url(path)
        assert result == "https://api.example.test/api/media/published/players/1/2/unique.jpg"
        assert storage.public_blob_path_from_reference(result) == path
        storage.delete_published(result)
        assert not storage.local_public_path(path).exists()


@pytest.mark.parametrize("method,conditional,status", [("get", False, 200), ("get", True, 304), ("head", False, 200)])
def test_private_cache_on_every_response(client, photo, method, conditional, status):
    etag = client.head(url(photo)).headers["ETag"]
    response = getattr(client, method)(url(photo), headers={"If-None-Match": etag} if conditional else {})
    assert response.status_code == status
    assert response.headers["Cache-Control"] == "private, max-age=300, must-revalidate"
    assert response.cache_control.private


@pytest.mark.parametrize(
    "headers,expected",
    [
        ({"CF-Connecting-IP": "203.0.113.7", "X-Forwarded-For": "10.0.0.1"}, "203.0.113.7"),
        ({"X-Forwarded-For": "203.0.113.8, 10.0.0.1"}, "203.0.113.8"),
        ({"X-Real-IP": "203.0.113.9"}, "203.0.113.9"),
        ({}, "127.0.0.1"),
    ],
)
def test_media_rate_limit_client_key(app, headers, expected):
    from src.auth import get_client_ip

    with app.test_request_context(headers=headers, environ_base={"REMOTE_ADDR": "127.0.0.1"}):
        assert get_client_ip() == expected


@pytest.mark.parametrize(
    "hidden,status,code",
    [(False, "pending", 200), (False, "approved", 200), (True, "approved", 404), (False, "suspended", 404)],
)
def test_club_takedown_gate(client, app, hidden, status, code):
    path = storage.publish("club-banners/1/test.jpg", _gps_jpeg())
    club = ClubProgram(
        funding_league_id=1,
        name="Synthetic",
        legal_name="Synthetic",
        slug="synthetic",
        country="Japan",
        region="Test",
        banner_url=path,
        platform_status=status,
        emergency_hidden=hidden,
    )
    db.session.add(club)
    db.session.commit()
    response = client.get(f"{storage.PUBLIC_ROUTE_PREFIX}/{path}")
    assert response.status_code == code
    if code == 404:
        assert client.get(f"{storage.PUBLIC_ROUTE_PREFIX}/{path}", headers={"If-None-Match": "*"}).status_code == 404


@pytest.mark.parametrize(
    "junk", ["https://[broken", "../../private.jpg", "https://unrecognized.test/arbitrary.jpg", 42]
)
def test_invalid_stored_url_logs_once_and_returns_none(app, monkeypatch, caplog, junk):
    monkeypatch.setattr(storage, "_logged_media_warnings", {})
    with app.test_request_context():
        assert storage.published_url(junk) is None
        assert storage.published_url(junk) is None
    assert caplog.text.count("Ignoring invalid stored published media reference") == 1


def test_corrupt_references_do_not_break_payloads(client, photo):
    from src.services.club_player_profile import prefetch_member_photos

    photo.public_url = "https://[broken"
    photo.blob_path = "../../junk.jpg"
    photo.is_primary = True
    db.session.commit()
    assert client.get(f"/api/players/{PLAYER_ID}/showcase").json["photos"][0]["public_url"] is None
    with client.application.test_request_context():
        club = ClubProgram(banner_url="https://[broken")
        assert club.brand_dict()["banner_url"] is None
        assert prefetch_member_photos([SimpleNamespace(local_player_id=None, player_api_id=PLAYER_ID)]) == {
            ("tracked", PLAYER_ID): None
        }


@pytest.mark.parametrize("error_type", ["HttpResponseError", "ServiceRequestError"])
@pytest.mark.parametrize("operation", ["get_blob_properties", "download_blob"])
def test_azure_errors_are_quiet_404(client, photo, monkeypatch, caplog, error_type, operation):
    from azure.core import exceptions

    _, blob = azure(monkeypatch)
    monkeypatch.setattr(storage, "_logged_media_warnings", {})
    getattr(blob, operation).side_effect = getattr(exceptions, error_type)("synthetic SDK failure")
    assert client.get(url(photo)).status_code == 404
    assert client.get(url(photo)).status_code == 404
    assert caplog.text.count("Published media storage read failed") == 1
    assert "Traceback" not in caplog.text


def test_azure_client_reused_with_bounded_download_configuration(monkeypatch):
    monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "synthetic")
    monkeypatch.setattr(storage, "_shared_client", None)
    monkeypatch.setattr(storage, "_shared_connection_string", None)
    factory = Mock()
    monkeypatch.setattr(storage.BlobServiceClient, "from_connection_string", factory)
    assert storage._service_client() is storage._service_client()
    factory.assert_called_once_with("synthetic", max_single_get_size=1024**2, max_chunk_get_size=1024**2)


@pytest.fixture
def minor_photo(photo):
    from src.models.showcase import PlayerProfileClaim

    local = LocalPlayer(display_name="Synthetic Minor", status="approved", birth_year=2015)
    db.session.add(local)
    db.session.flush()
    photo.player_api_id = None
    photo.local_player_id = local.id
    photo.blob_path = f"local-players/{local.id}/minor.png"
    photo.public_url = storage.publish(photo.blob_path, _gps_jpeg())
    db.session.add(
        PlayerProfileClaim(
            local_player_id=local.id,
            user_account_id=photo.uploaded_by_user_id,
            relationship_type="guardian",
            status="approved",
        )
    )
    db.session.commit()
    return photo


def test_minor_claimant_private_preview_and_revocation(client, minor_photo):
    from src.models.showcase import PlayerProfileClaim
    from test_showcase_media import _user_headers

    headers = _user_headers("media-owner@example.test")
    response = client.get(f"/api/local-players/{minor_photo.local_player_id}/showcase", headers=headers)
    payload = response.json["photos"][0]
    assert payload["public_url"] is None
    preview = payload["approved_preview_url"]
    assert client.get(url(minor_photo)).status_code == 404
    assert client.get(preview).status_code == 401
    assert client.get(preview, headers=_user_headers("stranger@example.test")).status_code == 404
    image = client.get(preview, headers=headers)
    assert image.status_code == 200 and image.data == _gps_jpeg()
    assert image.headers["Cache-Control"] == "private, no-store"
    assert client.head(preview, headers=headers).status_code == 200
    claim = PlayerProfileClaim.query.filter_by(local_player_id=minor_photo.local_player_id).one()
    claim.status = "revoked"
    db.session.commit()
    assert client.get(preview, headers={**headers, "If-None-Match": image.headers["ETag"]}).status_code == 404


def test_admin_minor_preview_requires_dual_auth(client, minor_photo):
    from test_showcase_media import _admin_headers

    headers = _admin_headers()
    listing = client.get("/api/admin/showcase/media?status=approved", headers=headers)
    payload = listing.json["media"][0]
    assert payload["public_url"] is None
    preview = payload["approved_preview_url"]
    assert preview.startswith("/api/admin/")
    assert client.get(preview, headers=headers).status_code == 200
    assert client.get(preview, headers={"Authorization": headers["Authorization"]}).status_code in (401, 403)
    assert client.get(preview, headers={"X-API-Key": headers["X-API-Key"]}).status_code == 401
    assert client.get(url(minor_photo), headers=headers).status_code == 404
    db.session.delete(minor_photo)
    db.session.commit()
    assert client.get(preview, headers=headers).status_code == 404


def test_recorded_manager_can_preview_but_other_club_cannot(client, minor_photo):
    from src.models.funding import ClubProgramClaim, ClubProgramManager
    from test_showcase_media import _make_user, _user_headers

    local = db.session.get(LocalPlayer, minor_photo.local_player_id)
    for index in (1, 2):
        user = _make_user(f"manager{index}@example.test")
        club = ClubProgram(
            funding_league_id=1,
            name=f"Synthetic {index}",
            legal_name="Synthetic",
            slug=f"synthetic-{index}",
            country="Japan",
            region="Test",
            platform_status="approved",
        )
        db.session.add(club)
        db.session.flush()
        claim = ClubProgramClaim(
            program_id=club.id, user_account_id=user.id, relationship_type="club_official", status="approved"
        )
        db.session.add(claim)
        db.session.flush()
        db.session.add(
            ClubProgramManager(
                program_id=club.id,
                user_account_id=user.id,
                source_claim_id=claim.id,
                status="active",
                granted_by="synthetic",
            )
        )
        if index == 1:
            local.origin_program_id = club.id
    db.session.commit()
    path = f"/api/showcase/media/{minor_photo.id}/preview"
    assert client.get(path, headers=_user_headers("manager1@example.test")).status_code == 200
    assert client.get(path, headers=_user_headers("manager2@example.test")).status_code == 404
    manager = ClubProgramManager.query.filter_by(program_id=local.origin_program_id).one()
    manager.status = "revoked"
    db.session.commit()
    assert client.get(path, headers=_user_headers("manager1@example.test")).status_code == 404


def test_limiter_separates_forwarded_clients(app, client, monkeypatch):
    from src.extensions import limiter

    app.config["RATELIMIT_ENABLED"] = True
    limiter.init_app(app)
    monkeypatch.setattr(limiter, "enabled", True)
    limiter.reset()
    path = f"{storage.PUBLIC_ROUTE_PREFIX}/arbitrary.jpg"
    for _ in range(300):
        assert client.get(path, headers={"CF-Connecting-IP": "203.0.113.1"}).status_code == 404
    rejected = client.get(path, headers={"CF-Connecting-IP": "203.0.113.1"})
    assert rejected.status_code == 429
    assert rejected.headers["Cache-Control"] == "private, no-store"
    assert client.get(path, headers={"CF-Connecting-IP": "203.0.113.2"}).status_code == 404


def test_azure_stream_failures_without_tracebacks(client, photo, monkeypatch, caplog):
    from azure.core.exceptions import ServiceRequestError

    _, blob = azure(monkeypatch)
    monkeypatch.setattr(storage, "_logged_media_warnings", {})

    def broken():
        yield b"abc"
        raise ServiceRequestError("synthetic interrupted stream")

    blob.download_blob.return_value.chunks.return_value = broken()
    response = client.get(url(photo))
    assert response.data == b"abc"
    assert int(response.headers["Content-Length"]) > len(response.data)
    assert caplog.text.count("Published media stream interrupted") == 1
    assert "Traceback" not in caplog.text


def test_azure_initial_chunk_error_is_404(client, photo, monkeypatch):
    from azure.core.exceptions import ServiceRequestError

    _, blob = azure(monkeypatch)

    def broken():
        raise ServiceRequestError("synthetic first chunk error")
        yield b"unreachable"

    blob.download_blob.return_value.chunks.return_value = broken()
    assert client.get(url(photo)).status_code == 404


@pytest.mark.parametrize("method", ["get", "head"])
@pytest.mark.parametrize("path", ["arbitrary.jpg", "players/5001/missing.jpg", ""])
def test_public_misses_are_never_cached(client, method, path):
    response = getattr(client, method)(f"{storage.PUBLIC_ROUTE_PREFIX}/{path}")
    assert response.status_code == 404
    assert response.headers["Cache-Control"] == "private, no-store"


def test_storage_warnings_repeat_after_five_minutes_per_category(monkeypatch, caplog):
    monkeypatch.setattr(storage, "_logged_media_warnings", {})
    clock = Mock(return_value=0)
    monkeypatch.setattr(storage, "monotonic", clock)
    storage.warn_once("read-failed", "Synthetic read warning")
    clock.return_value = 299
    storage.warn_once("read-failed", "Synthetic read warning")
    storage.warn_once("stream-failed", "Synthetic stream warning")
    assert caplog.text.count("Synthetic read warning") == 1
    assert caplog.text.count("Synthetic stream warning") == 1
    clock.return_value = 300
    storage.warn_once("read-failed", "Synthetic read warning")
    storage.warn_once("stream-failed", "Synthetic stream warning")
    assert caplog.text.count("Synthetic read warning") == 2
    assert caplog.text.count("Synthetic stream warning") == 1


@pytest.mark.parametrize("local_subject", [False, True])
@pytest.mark.parametrize("visible", [False, True])
def test_subject_query_count_constant_and_cache_request_scoped(app, photo, local_subject, visible):
    from sqlalchemy import event
    from src.routes.showcase import _media_dict

    if local_subject:
        local = LocalPlayer(display_name="Synthetic Cache", birth_year=2000, status="approved", api_player_id=PLAYER_ID)
        db.session.add(local)
        db.session.flush()
        photo.player_api_id = None
        photo.local_player_id = local.id
    player = TrackedPlayer.query.filter_by(player_api_id=PLAYER_ID).one()
    if not visible:
        player.birth_date = date(2015, 1, 1)
    rows = [photo]
    for index in range(12):
        row = _seed_media(PLAYER_ID, photo.uploaded_by_user_id, suffix=f"cache-{index}")
        row.player_api_id = photo.player_api_id
        row.local_player_id = photo.local_player_id
        rows.append(row)
    db.session.commit()
    # Load scalar fields before counting visibility queries.
    for row in rows:
        assert row.id
    counts = []
    queries = []

    def record(*args):
        queries.append(args[2])

    event.listen(db.engine, "before_cursor_execute", record)
    try:
        for selected in [rows[:1], rows]:
            db.session.expire_all()
            for row in rows:
                assert row.id
            queries.clear()
            with app.test_request_context():
                assert all(bool(_media_dict(row)["public_url"]) == visible for row in selected)
                # Per-row approval must never be memoized as part of subject visibility.
                rows[-1].status = "rejected"
                assert _media_dict(rows[-1])["public_url"] is None
                rows[-1].status = "approved"
            counts.append(len(queries))
        assert counts[0] > 0
        assert counts[0] == counts[1]
        # A new request must see a takedown, even with a surviving app context.
        player.birth_date = date(2015, 1, 1)
        db.session.commit()
        with app.test_request_context():
            assert _media_dict(photo)["public_url"] is None
    finally:
        event.remove(db.engine, "before_cursor_execute", record)


def test_admin_media_pagination(client, photo):
    from test_showcase_media import _admin_headers

    for index in range(104):
        _seed_media(PLAYER_ID, photo.uploaded_by_user_id, suffix=f"page-{index}")
    _seed_media(PLAYER_ID, photo.uploaded_by_user_id, suffix="excluded", status="rejected")
    db.session.commit()
    headers = _admin_headers()
    first = client.get("/api/admin/showcase/media?status=approved", headers=headers).json
    assert (first["total"], first["limit"], first["offset"], len(first["media"])) == (105, 50, 0, 50)
    second = client.get("/api/admin/showcase/media?status=approved&offset=50", headers=headers).json
    assert len(second["media"]) == 50
    assert not ({row["id"] for row in first["media"]} & {row["id"] for row in second["media"]})
    last = client.get("/api/admin/showcase/media?status=approved&offset=100", headers=headers).json
    assert len(last["media"]) == 5
    capped = client.get("/api/admin/showcase/media?limit=9999&offset=-1", headers=headers).json
    assert (capped["total"], capped["limit"], capped["offset"], len(capped["media"])) == (106, 100, 0, 100)
    assert client.get("/api/admin/showcase/media?offset=9999", headers=headers).json["media"] == []
    assert client.get("/api/admin/showcase/media?limit=invalid", headers=headers).status_code == 400
    assert client.get("/api/admin/showcase/media?offset=invalid", headers=headers).status_code == 400
