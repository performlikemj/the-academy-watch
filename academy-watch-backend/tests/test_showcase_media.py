"""Tests for Talent Showcase photo media and enriched profile fields.

Covers the direct-upload lifecycle, EXIF/GPS stripping, owner and public
visibility, gallery curation, profile validation/privacy, moderation rejection,
and production storage degradation.
"""

import struct
import zlib
from io import BytesIO
from urllib.parse import urlsplit

import pytest
from flask import Flask
from PIL import ExifTags, Image, TiffImagePlugin
from src.auth import _ensure_user_account, issue_user_token
from src.models.league import db
from src.models.showcase import PlayerProfileClaim, PlayerShowcaseMedia

ADMIN_KEY = "test-admin-key"
PLAYER_ID = 5001


@pytest.fixture
def app(monkeypatch, tmp_path):
    monkeypatch.setenv("SKIP_API_HANDSHAKE", "1")
    monkeypatch.setenv("API_USE_STUB_DATA", "true")
    monkeypatch.setenv("ADMIN_API_KEY", ADMIN_KEY)
    monkeypatch.setenv("ADMIN_IP_WHITELIST", "")
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("FLASK_ENV", "development")
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("SHOWCASE_MEDIA_LOCAL_DIR", str(tmp_path / "showcase-media"))
    monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)

    from src.routes.showcase import showcase_bp

    flask_app = Flask(__name__)
    flask_app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret-key",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        RATELIMIT_ENABLED=False,
    )

    db.init_app(flask_app)
    flask_app.register_blueprint(showcase_bp, url_prefix="/api")

    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _user_headers(email):
    _ensure_user_account(email)
    db.session.commit()
    token = issue_user_token(email)["token"]
    return {"Authorization": f"Bearer {token}"}


def _admin_headers():
    token = issue_user_token("admin@test.com", role="admin")["token"]
    return {"Authorization": f"Bearer {token}", "X-API-Key": ADMIN_KEY}


def _make_user(email):
    user = _ensure_user_account(email)
    db.session.commit()
    return user


def _approved_claim(player_api_id, email):
    user = _make_user(email)
    claim = PlayerProfileClaim(
        player_api_id=player_api_id,
        user_account_id=user.id,
        relationship_type="player",
        status="approved",
    )
    db.session.add(claim)
    db.session.commit()
    return user, claim


def _gps_jpeg() -> bytes:
    """A valid large JPEG carrying both generic EXIF and GPS coordinates."""
    image = Image.new("RGB", (1800, 900), "#8fbc8f")
    exif = Image.Exif()
    exif[ExifTags.Base.ImageDescription] = "Safeguarding test location"
    exif[ExifTags.Base.GPSInfo] = {
        ExifTags.GPS.GPSLatitudeRef: "N",
        ExifTags.GPS.GPSLatitude: (
            TiffImagePlugin.IFDRational(51, 1),
            TiffImagePlugin.IFDRational(30, 1),
            TiffImagePlugin.IFDRational(0, 1),
        ),
        ExifTags.GPS.GPSLongitudeRef: "W",
        ExifTags.GPS.GPSLongitude: (
            TiffImagePlugin.IFDRational(0, 1),
            TiffImagePlugin.IFDRational(7, 1),
            TiffImagePlugin.IFDRational(0, 1),
        ),
    }
    output = BytesIO()
    image.save(output, "JPEG", quality=92, exif=exif, comment=b"GPS:51.5007,-0.1246")
    raw = output.getvalue()

    with Image.open(BytesIO(raw)) as source:
        assert source.getexif().get_ifd(ExifTags.IFD.GPSInfo)
        assert source.info["comment"] == b"GPS:51.5007,-0.1246"
    return raw


def _oversized_dimension_png() -> bytes:
    """Tiny PNG container whose declared dimensions exceed the pixel cap."""

    def chunk(kind, payload):
        checksum = zlib.crc32(kind + payload) & 0xFFFFFFFF
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", checksum)

    ihdr = struct.pack(">IIBBBBB", 8000, 5001, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IEND", b"")


def _url_path(url):
    parsed = urlsplit(url)
    return parsed.path or url


def _create_photo(client, headers, raw, *, content_type="image/jpeg"):
    response = client.post(
        f"/api/players/{PLAYER_ID}/showcase/photos",
        json={"content_type": content_type, "size_bytes": len(raw)},
        headers=headers,
    )
    assert response.status_code == 201, response.get_json()
    return response.get_json()


def _upload_photo(client, upload, raw, *, content_type="image/jpeg"):
    assert upload["method"] == "PUT"
    assert upload["headers"] == {"x-ms-blob-type": "BlockBlob", "Content-Type": content_type}
    response = client.put(_url_path(upload["url"]), data=raw, headers=upload["headers"])
    assert response.status_code in (200, 201, 204), response.get_json(silent=True)


def _create_upload_complete(client, headers, raw):
    created = _create_photo(client, headers, raw)
    _upload_photo(client, created["upload"], raw)
    media_id = created["media"]["id"]
    completed = client.post(
        f"/api/players/{PLAYER_ID}/showcase/photos/{media_id}/complete",
        headers=headers,
    )
    assert completed.status_code == 200, completed.get_json()
    assert completed.get_json()["media"]["status"] == "pending"
    return created, completed.get_json()["media"]


def _seed_media(player_api_id, user_id, *, status="approved", sort_order=0, suffix="photo"):
    media = PlayerShowcaseMedia(
        player_api_id=player_api_id,
        kind="photo",
        blob_path=f"players/{player_api_id}/{suffix}.jpg",
        public_url=f"/api/dev/showcase-media/published/players/{player_api_id}/{suffix}.jpg",
        content_type="image/jpeg",
        size_bytes=1024,
        status=status,
        sort_order=sort_order,
        uploaded_by_user_id=user_id,
    )
    db.session.add(media)
    db.session.flush()
    return media


# --------------------------------------------------------------------------- #
# Upload + moderation lifecycle
# --------------------------------------------------------------------------- #


class TestPhotoLifecycle:
    def test_complete_rejects_oversized_dimensions_and_deletes_pending_blob(self, app, client):
        raw = _oversized_dimension_png()
        with app.app_context():
            _approved_claim(PLAYER_ID, "owner@example.com")
        headers = _user_headers("owner@example.com")

        created = _create_photo(client, headers, raw, content_type="image/png")
        _upload_photo(client, created["upload"], raw, content_type="image/png")
        pending_path = _url_path(created["upload"]["url"])
        media_id = created["media"]["id"]
        assert len(raw) < 1024
        assert client.get(pending_path).status_code == 200

        completed = client.post(
            f"/api/players/{PLAYER_ID}/showcase/photos/{media_id}/complete",
            headers=headers,
        )

        assert completed.status_code == 422
        assert client.get(pending_path).status_code == 404
        with app.app_context():
            row = db.session.get(PlayerShowcaseMedia, media_id)
            assert row is None or row.status != "pending"

    def test_failed_size_verification_deletes_pending_blob(self, app, client, monkeypatch):
        from src.services import showcase_media_storage

        raw = _gps_jpeg()
        with app.app_context():
            _approved_claim(PLAYER_ID, "owner@example.com")
        headers = _user_headers("owner@example.com")

        created = _create_photo(client, headers, raw)
        _upload_photo(client, created["upload"], raw)
        pending_path = _url_path(created["upload"]["url"])
        media_id = created["media"]["id"]
        monkeypatch.setattr(showcase_media_storage, "max_photo_bytes", lambda: len(raw) - 1)

        completed = client.post(
            f"/api/players/{PLAYER_ID}/showcase/photos/{media_id}/complete",
            headers=headers,
        )

        assert completed.status_code == 400
        assert client.get(pending_path).status_code == 404
        with app.app_context():
            row = db.session.get(PlayerShowcaseMedia, media_id)
            assert row is None or row.status != "pending"

    def test_invalid_completion_cleanup_failure_is_best_effort(self, app, client, monkeypatch):
        from src.services import showcase_media_storage

        raw = _oversized_dimension_png()
        with app.app_context():
            _approved_claim(PLAYER_ID, "owner@example.com")
        headers = _user_headers("owner@example.com")

        created = _create_photo(client, headers, raw, content_type="image/png")
        _upload_photo(client, created["upload"], raw, content_type="image/png")
        media_id = created["media"]["id"]
        with app.app_context():
            expected_blob_path = db.session.get(PlayerShowcaseMedia, media_id).blob_path
        cleanup_attempts = []

        def fail_cleanup(blob_path):
            cleanup_attempts.append(blob_path)
            raise OSError("simulated cleanup failure")

        monkeypatch.setattr(showcase_media_storage, "delete_pending", fail_cleanup)
        completed = client.post(
            f"/api/players/{PLAYER_ID}/showcase/photos/{media_id}/complete",
            headers=headers,
        )

        assert completed.status_code == 422
        assert cleanup_attempts == [expected_blob_path]
        with app.app_context():
            row = db.session.get(PlayerShowcaseMedia, media_id)
            assert row is None or row.status != "pending"

    def test_create_complete_approve_strips_gps_and_all_exif(self, app, client):
        raw = _gps_jpeg()
        with app.app_context():
            _approved_claim(PLAYER_ID, "owner@example.com")
        headers = _user_headers("owner@example.com")

        created, pending = _create_upload_complete(client, headers, raw)
        assert created["media"]["status"] == "pending_upload"
        assert pending["size_bytes"] == len(raw)
        assert client.get(f"/api/players/{PLAYER_ID}/showcase").get_json()["photos"] == []
        owner_pending = client.get(f"/api/players/{PLAYER_ID}/showcase", headers=headers).get_json()["photos"]
        assert [(item["id"], item["status"]) for item in owner_pending] == [(pending["id"], "pending")]

        # The dev transport mirrors create-only SAS semantics: completion cannot
        # be followed by an overwrite that bypasses the admin's preview.
        overwrite = client.put(_url_path(created["upload"]["url"]), data=raw, headers=created["upload"]["headers"])
        assert overwrite.status_code == 409

        queue = client.get("/api/admin/showcase/media?status=pending", headers=_admin_headers())
        assert queue.status_code == 200
        assert [item["id"] for item in queue.get_json()["media"]] == [pending["id"]]

        reviewed = client.post(
            f"/api/admin/showcase/media/{pending['id']}/review",
            json={"action": "approve", "note": "Safe to publish"},
            headers=_admin_headers(),
        )
        assert reviewed.status_code == 200, reviewed.get_json()
        media = reviewed.get_json()["media"]
        assert media["status"] == "approved"
        assert media["content_type"] == "image/jpeg"
        assert media["public_url"]
        assert media["review_note"] == "Safe to publish"
        assert client.get(_url_path(created["upload"]["url"])).status_code == 404

        published = client.get(_url_path(media["public_url"]))
        assert published.status_code == 200
        with Image.open(BytesIO(published.data)) as processed:
            assert processed.format == "JPEG"
            assert max(processed.size) == 1600
            assert not processed.getexif()
            assert not processed.getexif().get_ifd(ExifTags.IFD.GPSInfo)
            assert "comment" not in processed.info
            assert b"GPS:51.5007,-0.1246" not in published.data

        public = client.get(f"/api/players/{PLAYER_ID}/showcase").get_json()
        assert [photo["id"] for photo in public["photos"]] == [pending["id"]]

    def test_reject_deletes_pending_blob_but_keeps_row_and_note(self, app, client):
        raw = _gps_jpeg()
        with app.app_context():
            _approved_claim(PLAYER_ID, "owner@example.com")
        headers = _user_headers("owner@example.com")
        created, pending = _create_upload_complete(client, headers, raw)
        pending_path = _url_path(created["upload"]["url"])
        assert client.get(pending_path).status_code == 200

        reviewed = client.post(
            f"/api/admin/showcase/media/{pending['id']}/review",
            json={"action": "reject", "note": "Contains private contact details"},
            headers=_admin_headers(),
        )
        assert reviewed.status_code == 200
        media = reviewed.get_json()["media"]
        assert media["status"] == "rejected"
        assert media["review_note"] == "Contains private contact details"
        assert media["pending_preview_url"] is None
        assert client.get(pending_path).status_code == 404

        with app.app_context():
            row = db.session.get(PlayerShowcaseMedia, pending["id"])
            assert row is not None
            assert row.status == "rejected"

        assert client.get(f"/api/players/{PLAYER_ID}/showcase").get_json()["photos"] == []
        owner = client.get(f"/api/players/{PLAYER_ID}/showcase", headers=headers).get_json()
        assert [(item["id"], item["status"]) for item in owner["photos"]] == [(pending["id"], "rejected")]

    def test_invalid_bytes_fail_completion_and_delete_pending_blob(self, app, client):
        raw = b"not actually a jpeg"
        with app.app_context():
            _approved_claim(PLAYER_ID, "owner@example.com")
        headers = _user_headers("owner@example.com")
        created = _create_photo(client, headers, raw)
        _upload_photo(client, created["upload"], raw)
        media_id = created["media"]["id"]
        pending_path = _url_path(created["upload"]["url"])
        assert client.get(pending_path).status_code == 200

        completed = client.post(
            f"/api/players/{PLAYER_ID}/showcase/photos/{media_id}/complete",
            headers=headers,
        )

        assert completed.status_code == 422
        assert client.get(pending_path).status_code == 404
        with app.app_context():
            row = db.session.get(PlayerShowcaseMedia, media_id)
            assert row is not None
            assert row.status == "pending_upload"
            assert row.status not in {"pending", "approved"}
            assert row.public_url is None

    def test_delete_removes_approved_row_and_public_blob(self, app, client):
        raw = _gps_jpeg()
        with app.app_context():
            _approved_claim(PLAYER_ID, "owner@example.com")
        headers = _user_headers("owner@example.com")
        _, pending = _create_upload_complete(client, headers, raw)
        approved = client.post(
            f"/api/admin/showcase/media/{pending['id']}/review",
            json={"action": "approve"},
            headers=_admin_headers(),
        ).get_json()["media"]
        public_path = _url_path(approved["public_url"])
        assert client.get(public_path).status_code == 200

        deleted = client.delete(
            f"/api/players/{PLAYER_ID}/showcase/photos/{pending['id']}",
            headers=headers,
        )
        assert deleted.status_code == 200
        assert client.get(public_path).status_code == 404
        with app.app_context():
            assert db.session.get(PlayerShowcaseMedia, pending["id"]) is None


# --------------------------------------------------------------------------- #
# Owner gate, cap, and visibility
# --------------------------------------------------------------------------- #


class TestPhotoPermissionsAndVisibility:
    def test_non_owner_cannot_create_photo(self, app, client):
        with app.app_context():
            _approved_claim(PLAYER_ID, "owner@example.com")
        response = client.post(
            f"/api/players/{PLAYER_ID}/showcase/photos",
            json={"content_type": "image/jpeg", "size_bytes": 100},
            headers=_user_headers("stranger@example.com"),
        )
        assert response.status_code == 403

    def test_eight_non_rejected_photos_enforces_cap(self, app, client):
        with app.app_context():
            owner, _ = _approved_claim(PLAYER_ID, "owner@example.com")
            for index in range(8):
                _seed_media(PLAYER_ID, owner.id, status="pending", sort_order=index, suffix=f"cap-{index}")
            db.session.commit()

        response = client.post(
            f"/api/players/{PLAYER_ID}/showcase/photos",
            json={"content_type": "image/jpeg", "size_bytes": 100},
            headers=_user_headers("owner@example.com"),
        )
        assert response.status_code == 409

    def test_public_sees_approved_owner_also_sees_pending(self, app, client):
        with app.app_context():
            owner, _ = _approved_claim(PLAYER_ID, "owner@example.com")
            approved = _seed_media(PLAYER_ID, owner.id, suffix="approved")
            db.session.commit()
            approved_id = approved.id

        headers = _user_headers("owner@example.com")
        pending = _create_photo(client, headers, _gps_jpeg())["media"]

        public = client.get(f"/api/players/{PLAYER_ID}/showcase").get_json()["photos"]
        assert [item["id"] for item in public] == [approved_id]
        assert all(item["status"] == "approved" for item in public)

        owner_view = client.get(f"/api/players/{PLAYER_ID}/showcase", headers=headers).get_json()["photos"]
        by_id = {item["id"]: item for item in owner_view}
        assert set(by_id) == {approved_id, pending["id"]}
        assert by_id[pending["id"]]["status"] == "pending_upload"
        assert by_id[pending["id"]]["pending_preview_url"]

        stranger = client.get(
            f"/api/players/{PLAYER_ID}/showcase", headers=_user_headers("stranger@example.com")
        ).get_json()["photos"]
        assert [item["id"] for item in stranger] == [approved_id]


# --------------------------------------------------------------------------- #
# Gallery curation
# --------------------------------------------------------------------------- #


class TestPhotoCuration:
    def test_reorder_and_set_primary_on_approved_photos(self, app, client):
        with app.app_context():
            owner, _ = _approved_claim(PLAYER_ID, "owner@example.com")
            first = _seed_media(PLAYER_ID, owner.id, sort_order=0, suffix="first")
            second = _seed_media(PLAYER_ID, owner.id, sort_order=1, suffix="second")
            third = _seed_media(PLAYER_ID, owner.id, sort_order=2, suffix="third")
            db.session.commit()
            first_id, second_id, third_id = first.id, second.id, third.id

        headers = _user_headers("owner@example.com")
        reordered = client.patch(
            f"/api/players/{PLAYER_ID}/showcase/photos/order",
            json={"ordered_ids": [third_id, first_id, second_id]},
            headers=headers,
        )
        assert reordered.status_code == 200, reordered.get_json()
        assert [item["id"] for item in reordered.get_json()["photos"]] == [third_id, first_id, second_id]

        primary = client.patch(
            f"/api/players/{PLAYER_ID}/showcase/photos/{first_id}",
            json={"is_primary": True},
            headers=headers,
        )
        assert primary.status_code == 200, primary.get_json()
        assert primary.get_json()["media"]["is_primary"] is True

        with app.app_context():
            rows = PlayerShowcaseMedia.query.filter_by(player_api_id=PLAYER_ID).all()
            assert {row.id: row.sort_order for row in rows} == {
                third_id: 0,
                first_id: 1,
                second_id: 2,
            }
            assert [row.id for row in rows if row.is_primary] == [first_id]


# --------------------------------------------------------------------------- #
# Enriched profile fields
# --------------------------------------------------------------------------- #


class TestEnrichedProfile:
    @pytest.mark.parametrize(
        "payload",
        [
            {"contract_status": "retired"},
            {"availability": "maybe"},
            {"contract_until": "2026-02-30"},
            {"agent_contact_email": "not-an-email"},
        ],
    )
    def test_invalid_new_profile_fields_return_400(self, app, client, payload):
        with app.app_context():
            _approved_claim(PLAYER_ID, "owner@example.com")
        response = client.put(
            f"/api/players/{PLAYER_ID}/showcase/profile",
            json=payload,
            headers=_user_headers("owner@example.com"),
        )
        assert response.status_code == 400, (payload, response.get_json())

    def test_valid_fields_round_trip_and_agent_email_requires_auth(self, app, client):
        with app.app_context():
            _approved_claim(PLAYER_ID, "owner@example.com")
            _make_user("scout@example.com")

        payload = {
            "contract_status": "under_contract",
            "contract_until": "2027-06-30",
            "availability": "open_to_moves",
            "agent_name": "Alex Agent",
            "agent_contact_email": "alex.agent@example.com",
            "nationality_secondary": "Irish",
            "languages": "English, Spanish",
        }
        saved = client.put(
            f"/api/players/{PLAYER_ID}/showcase/profile",
            json=payload,
            headers=_user_headers("owner@example.com"),
        )
        assert saved.status_code == 200, saved.get_json()
        assert saved.get_json()["profile"]["status"] == "pending"

        approved = client.post(
            f"/api/admin/showcase/profiles/{PLAYER_ID}/review",
            json={"action": "approve"},
            headers=_admin_headers(),
        )
        assert approved.status_code == 200

        anonymous = client.get(f"/api/players/{PLAYER_ID}/showcase").get_json()["profile"]
        assert anonymous["agent_name"] == "Alex Agent"
        assert anonymous["contract_until"] == "2027-06-30"
        assert "agent_contact_email" not in anonymous

        authenticated = client.get(
            f"/api/players/{PLAYER_ID}/showcase", headers=_user_headers("scout@example.com")
        ).get_json()["profile"]
        assert authenticated["agent_contact_email"] == "alex.agent@example.com"

    def test_non_object_json_uses_validation_envelopes(self, app, client):
        with app.app_context():
            owner, _ = _approved_claim(PLAYER_ID, "owner@example.com")
            pending = _seed_media(PLAYER_ID, owner.id, status="pending", suffix="bad-action")
            db.session.commit()
            pending_id = pending.id
        headers = _user_headers("owner@example.com")

        profile = client.put(f"/api/players/{PLAYER_ID}/showcase/profile", json=["bad"], headers=headers)
        assert profile.status_code == 400
        null_profile = client.put(
            f"/api/players/{PLAYER_ID}/showcase/profile",
            data="null",
            headers={**headers, "Content-Type": "application/json"},
        )
        assert null_profile.status_code == 400
        create = client.post(f"/api/players/{PLAYER_ID}/showcase/photos", json=["bad"], headers=headers)
        assert create.status_code == 400
        review = client.post(
            f"/api/admin/showcase/media/{pending_id}/review",
            json={"action": 1},
            headers=_admin_headers(),
        )
        assert review.status_code == 400


# --------------------------------------------------------------------------- #
# Graceful production degradation
# --------------------------------------------------------------------------- #


def test_prod_without_azure_returns_503(app, client, monkeypatch):
    with app.app_context():
        owner, _ = _approved_claim(PLAYER_ID, "owner@example.com")
        pending = _seed_media(PLAYER_ID, owner.id, status="pending", suffix="prod-pending")
        db.session.commit()
        pending_id = pending.id

    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("FLASK_ENV", "production")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)

    response = client.post(
        f"/api/players/{PLAYER_ID}/showcase/photos",
        json={"content_type": "image/jpeg", "size_bytes": 100},
        headers=_user_headers("owner@example.com"),
    )
    assert response.status_code == 503
    assert "storage" in response.get_json()["error"].lower()

    review = client.post(
        f"/api/admin/showcase/media/{pending_id}/review",
        json={"action": "reject"},
        headers=_admin_headers(),
    )
    assert review.status_code == 503
    with app.app_context():
        assert db.session.get(PlayerShowcaseMedia, pending_id).status == "pending"


def test_local_storage_gate_fails_closed(app, monkeypatch, tmp_path):
    from src.services import showcase_media_storage

    monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)
    for name in ("ENV", "FLASK_ENV", "APP_ENV", "SHOWCASE_MEDIA_LOCAL_DIR"):
        monkeypatch.delenv(name, raising=False)
    assert showcase_media_storage.is_local_dev_enabled() is False

    monkeypatch.setenv("SHOWCASE_MEDIA_LOCAL_DIR", str(tmp_path / "explicit-local"))
    assert showcase_media_storage.is_local_dev_enabled() is True

    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("FLASK_ENV", "production")
    assert showcase_media_storage.is_local_dev_enabled() is False

    for value in ("nan", "inf", "-1"):
        monkeypatch.setenv("SHOWCASE_PHOTO_MAX_MB", value)
        assert showcase_media_storage.max_photo_bytes() == 8 * 1024**2
