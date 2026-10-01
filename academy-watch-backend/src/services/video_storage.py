"""
Blob storage for match-video uploads (Phase A).

Browser uploads go DIRECTLY to Azure Blob via short-lived write SAS — video
never transits the Flask app. The app only mints SAS tokens, verifies the blob
after upload-complete (size cap + ETag capture for the job-start TOCTOU check),
and mints read SAS for the worker and for report assets.

Env:
  AZURE_STORAGE_CONNECTION_STRING   account with the video container
  VIDEO_BLOB_CONTAINER              default "video-matches"
  VIDEO_MAX_UPLOAD_GB               server-side size cap, default 12
"""

import json
import logging
import os
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

logger = logging.getLogger(__name__)

try:
    from azure.core import MatchConditions
    from azure.storage.blob import (
        BlobSasPermissions,
        BlobServiceClient,
        ContentSettings,
        generate_blob_sas,
    )

    _AZURE_AVAILABLE = True
except ImportError:  # keep the app importable without the optional dependency
    _AZURE_AVAILABLE = False

UPLOAD_SAS_MINUTES = 60  # re-mint endpoint exists because 6GB at club uplink speeds outlives this
READ_SAS_HOURS = 6
MEDIA_READ_SAS_MINUTES = 30  # browser footage redirect; matches src.auth.MEDIA_TOKEN_TTL


def _container() -> str:
    return os.getenv("VIDEO_BLOB_CONTAINER", "video-matches")


def _max_upload_bytes() -> int:
    return int(float(os.getenv("VIDEO_MAX_UPLOAD_GB", "12")) * 1024**3)


def is_configured() -> bool:
    return _AZURE_AVAILABLE and bool(os.getenv("AZURE_STORAGE_CONNECTION_STRING"))


def _service_client() -> "BlobServiceClient":
    if not _AZURE_AVAILABLE:
        raise RuntimeError("azure-storage-blob is not installed")
    conn = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    if not conn:
        raise RuntimeError("AZURE_STORAGE_CONNECTION_STRING is not configured")
    return BlobServiceClient.from_connection_string(conn)


def _mint_sas(blob_path: str, permission: "BlobSasPermissions", expiry: datetime, snapshot: str | None = None) -> str:
    client = _service_client()
    extra = {"snapshot": snapshot} if snapshot else {}
    return generate_blob_sas(
        account_name=client.account_name,
        container_name=_container(),
        blob_name=blob_path,
        account_key=client.credential.account_key,
        permission=permission,
        expiry=expiry,
        **extra,
    )


def mint_upload_sas(blob_path: str) -> dict:
    """Write-only SAS for the browser's direct-to-blob upload."""
    expiry = datetime.now(UTC) + timedelta(minutes=UPLOAD_SAS_MINUTES)
    sas = _mint_sas(blob_path, BlobSasPermissions(write=True, create=True), expiry)
    client = _service_client()
    return {
        "upload_url": f"{client.url}{_container()}/{blob_path}?{sas}",
        "blob_path": blob_path,
        "expires_at": expiry.isoformat(),
        "max_bytes": _max_upload_bytes(),
    }


def mint_read_sas(blob_path: str, hours: int = READ_SAS_HOURS) -> str:
    """Read-only SAS URL (worker footage pull, report thumbnails)."""
    expiry = datetime.now(UTC) + timedelta(hours=hours)
    sas = _mint_sas(blob_path, BlobSasPermissions(read=True), expiry)
    client = _service_client()
    return f"{client.url}{_container()}/{blob_path}?{sas}"


def mint_media_read_sas(
    blob_path: str, *, seconds: int = MEDIA_READ_SAS_MINUTES * 60, snapshot: str | None = None
) -> str:
    """Short read-only SAS for the browser footage redirect — never longer than the media token, and never
    longer than the token's REMAINING life when the caller passes it (``seconds``).

    With ``snapshot`` the SAS is signed for, and the URL addresses, that immutable blob snapshot only
    (club staff access: scoped staff never get a capability on the mutable base blob)."""
    ttl = max(1, min(int(seconds), MEDIA_READ_SAS_MINUTES * 60))
    expiry = datetime.now(UTC) + timedelta(seconds=ttl)
    if snapshot:
        sas = _mint_sas(blob_path, BlobSasPermissions(read=True), expiry, snapshot=snapshot)
    else:
        sas = _mint_sas(blob_path, BlobSasPermissions(read=True), expiry)
    client = _service_client()
    if snapshot:
        return f"{client.url}{_container()}/{blob_path}?snapshot={quote(snapshot, safe='')}&{sas}"
    return f"{client.url}{_container()}/{blob_path}?{sas}"


def create_verified_snapshot(blob_path: str, expected_etag: str | None) -> str | None:
    """Snapshot exactly the verified generation of a recording; returns the snapshot id or None.

    The snapshot is conditional on ``expected_etag`` (If-Match), so a write that lands between
    verification and this call yields no snapshot rather than a snapshot of unverified bytes.
    Snapshots are read-only: no upload SAS (write/create on the base blob) can alter them."""
    if not blob_path or not expected_etag:
        return None
    try:
        blob = _service_client().get_blob_client(_container(), blob_path)
        result = blob.create_snapshot(etag=expected_etag, match_condition=MatchConditions.IfNotModified)
        return (result or {}).get("snapshot") or None
    except Exception as e:  # changed since verification, auth, network — all mean "no immutable generation"
        logger.warning("video blob snapshot failed for %s: %s", blob_path, e)
        return None


def verify_uploaded_blob(blob_path: str) -> dict:
    """Post-upload verification: blob exists and is within the size cap.
    Returns {ok, size_bytes, etag} or {ok: False, error}."""
    try:
        blob = _service_client().get_blob_client(_container(), blob_path)
        props = blob.get_blob_properties()
    except Exception as e:  # missing blob, auth, network — all mean "not verified"
        logger.warning("video blob verify failed for %s: %s", blob_path, e)
        return {"ok": False, "error": "blob not found or unreadable"}
    if props.size > _max_upload_bytes():
        return {
            "ok": False,
            "error": f"file exceeds {_max_upload_bytes() // 1024**3}GB cap",
            "size_bytes": props.size,
        }
    return {"ok": True, "size_bytes": props.size, "etag": props.etag}


def verify_expected_blob(blob_path: str, expected_etag: str | None) -> dict:
    """Re-check size/existence and, when recorded, the upload-complete ETag.

    Legacy matches can have a null ETag because their upload predates ETag
    stamping. They still receive the basic existence and size verification.
    """
    check = verify_uploaded_blob(blob_path)
    if not check["ok"]:
        return check
    if expected_etag is not None and check.get("etag") != expected_etag:
        return {
            "ok": False,
            "error": "footage blob changed since upload-complete (ETag mismatch)",
        }
    return check


def upload_json(blob_path: str, obj) -> None:
    """Upload a JSON object to the video container, replacing any prior blob."""
    payload = json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    blob = _service_client().get_blob_client(_container(), blob_path)
    blob.upload_blob(
        payload,
        overwrite=True,
        content_settings=ContentSettings(content_type="application/json"),
    )


def download_json(blob_path: str):
    """Download and decode one JSON blob from the video container."""
    blob = _service_client().get_blob_client(_container(), blob_path)
    return json.loads(blob.download_blob().readall())


def delete_blob(blob_path: str) -> bool:
    """Delete one raw-footage blob. True when it is gone afterwards (deleted now, or already absent)."""
    try:
        blob = _service_client().get_blob_client(_container(), blob_path)
        # Recordings carry verified-generation snapshots (club staff access); retention removes them too.
        blob.delete_blob(delete_snapshots="include")
        return True
    except Exception as e:  # auth, network — all mean "not gone"; a 404 means it was already gone
        if getattr(e, "status_code", None) == 404:
            return True
        logger.warning("video blob delete failed for %s: %s", blob_path, e)
        return False
