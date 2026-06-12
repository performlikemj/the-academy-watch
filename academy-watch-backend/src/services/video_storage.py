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

import logging
import os
from datetime import UTC, datetime, timedelta

logger = logging.getLogger(__name__)

try:
    from azure.storage.blob import (
        BlobSasPermissions,
        BlobServiceClient,
        generate_blob_sas,
    )

    _AZURE_AVAILABLE = True
except ImportError:  # keep the app importable without the optional dependency
    _AZURE_AVAILABLE = False

UPLOAD_SAS_MINUTES = 60  # re-mint endpoint exists because 6GB at club uplink speeds outlives this
READ_SAS_HOURS = 6


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


def _mint_sas(blob_path: str, permission: "BlobSasPermissions", expiry: datetime) -> str:
    client = _service_client()
    return generate_blob_sas(
        account_name=client.account_name,
        container_name=_container(),
        blob_name=blob_path,
        account_key=client.credential.account_key,
        permission=permission,
        expiry=expiry,
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
