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
    assert response.headers["Cache-Control"] == "public, max-age=86400"
    etag = response.headers["ETag"]
    head = client.head(url(photo))
    assert head.status_code == 200 and not head.data
    assert head.headers["Content-Length"] == response.headers["Content-Length"]
    assert head.headers["ETag"] == etag
    cached = client.get(url(photo), headers={"If-None-Match": etag})
    assert cached.status_code == 304 and not cached.data
    assert cached.headers["X-Content-Type-Options"] == "nosniff"
    assert cached.headers["Cache-Control"] == "public, max-age=86400"
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
