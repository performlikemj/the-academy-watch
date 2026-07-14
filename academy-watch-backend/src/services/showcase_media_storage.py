"""Storage abstraction for pre-moderated player showcase photos.

In Azure, browsers upload directly to the private pending container with a
short-lived write SAS. The Flask app only verifies and moderates that upload;
approved, EXIF-stripped bytes are written to the public container.

When Azure is not configured, non-production environments use a local
filesystem backend with the same contract. Production and staging never fall
back to local storage.

Env:
  AZURE_STORAGE_CONNECTION_STRING  Azure storage account connection string
  SHOWCASE_MEDIA_PENDING_CONTAINER private pending container (default
                                   ``showcase-media-pending``)
  SHOWCASE_MEDIA_CONTAINER         public approved container (default
                                   ``showcase-media``)
  SHOWCASE_PHOTO_MAX_MB            upload cap in MiB (default ``8``)
  SHOWCASE_MEDIA_LOCAL_DIR         local-dev root (default under ``/tmp``)
"""

import logging
import math
import os
import re
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote, unquote, urlparse
from uuid import uuid4

logger = logging.getLogger(__name__)

try:
    from azure.core.exceptions import ResourceNotFoundError
    from azure.storage.blob import (
        BlobSasPermissions,
        BlobServiceClient,
        ContentSettings,
        generate_blob_sas,
    )

    _AZURE_AVAILABLE = True
except ImportError:  # keep the app and local tests importable without Azure
    ResourceNotFoundError = None
    _AZURE_AVAILABLE = False

UPLOAD_SAS_MINUTES = 15
PREVIEW_SAS_MINUTES = 15
DEFAULT_MAX_PHOTO_MB = 8
DEV_ROUTE_PREFIX = "/api/dev/showcase-media"

_CONTENT_TYPE_EXTENSIONS = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}
_SAFE_PATH_PART = re.compile(r"[A-Za-z0-9._-]+")
_PRODUCTION_ENVS = {"prod", "production", "stage", "staging"}
_LOCAL_DEV_ENVS = {"dev", "development", "local", "test", "testing"}


class StorageNotConfiguredError(RuntimeError):
    """Raised when neither Azure nor the local-dev backend may be used."""


class InvalidBlobPathError(ValueError):
    """Raised when a blob path could escape the configured storage root."""


class StoredMediaError(RuntimeError):
    """Raised when stored media cannot safely be read or published."""


def _pending_container() -> str:
    return os.getenv("SHOWCASE_MEDIA_PENDING_CONTAINER", "showcase-media-pending")


def _public_container() -> str:
    return os.getenv("SHOWCASE_MEDIA_CONTAINER", "showcase-media")


def max_photo_bytes() -> int:
    """Configured photo upload cap in bytes."""
    raw_value = os.getenv("SHOWCASE_PHOTO_MAX_MB", str(DEFAULT_MAX_PHOTO_MB))
    try:
        megabytes = float(raw_value)
    except (TypeError, ValueError):
        logger.warning("invalid SHOWCASE_PHOTO_MAX_MB=%r; using %s", raw_value, DEFAULT_MAX_PHOTO_MB)
        megabytes = DEFAULT_MAX_PHOTO_MB
    if not math.isfinite(megabytes) or megabytes <= 0:
        logger.warning("invalid/non-positive SHOWCASE_PHOTO_MAX_MB=%r; using %s", raw_value, DEFAULT_MAX_PHOTO_MB)
        megabytes = DEFAULT_MAX_PHOTO_MB
    return int(megabytes * 1024**2)


def _environment_markers() -> set[str]:
    return {
        value.strip().lower()
        for value in (os.getenv("ENV"), os.getenv("FLASK_ENV"), os.getenv("APP_ENV"))
        if value and value.strip()
    }


def is_azure_configured() -> bool:
    """Whether the Azure SDK and connection string are both available."""
    return _AZURE_AVAILABLE and bool(os.getenv("AZURE_STORAGE_CONNECTION_STRING"))


def is_local_dev_enabled() -> bool:
    """Whether the local fallback is allowed for this process.

    This mirrors the Film Room development posture (local artifacts only when
    Azure is absent) while adding an explicit production/staging fail-closed
    gate for user-uploaded media.
    """
    if is_azure_configured():
        return False
    markers = _environment_markers()
    if markers & _PRODUCTION_ENVS:
        return False
    # Fail closed when deployment markers are absent/unknown. An explicitly
    # configured local root is also a deliberate test/dev opt-in.
    return bool(markers & _LOCAL_DEV_ENVS) or (not markers and bool(os.getenv("SHOWCASE_MEDIA_LOCAL_DIR")))


def is_configured() -> bool:
    """Whether uploads can be served by Azure or the local-dev backend."""
    return is_azure_configured() or is_local_dev_enabled()


def _require_configured() -> None:
    if not is_configured():
        raise StorageNotConfiguredError("showcase media storage is not configured")


def _service_client() -> "BlobServiceClient":
    if not _AZURE_AVAILABLE:
        raise StorageNotConfiguredError("azure-storage-blob is not installed")
    connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    if not connection_string:
        raise StorageNotConfiguredError("AZURE_STORAGE_CONNECTION_STRING is not configured")
    return BlobServiceClient.from_connection_string(connection_string)


def _account_key(client: "BlobServiceClient") -> str:
    key = getattr(getattr(client, "credential", None), "account_key", None)
    if not key:
        raise StorageNotConfiguredError("Azure connection string must include an account key")
    return key


def _mint_sas(container: str, blob_path: str, permission: "BlobSasPermissions", expiry: datetime) -> str:
    client = _service_client()
    return generate_blob_sas(
        account_name=client.account_name,
        container_name=container,
        blob_name=blob_path,
        account_key=_account_key(client),
        permission=permission,
        expiry=expiry,
    )


def _validate_blob_path(blob_path: str) -> str:
    if not isinstance(blob_path, str) or not blob_path or "\\" in blob_path or "\x00" in blob_path:
        raise InvalidBlobPathError("invalid showcase media blob path")
    if blob_path.startswith("/"):
        raise InvalidBlobPathError("showcase media blob path must be relative")
    parts = blob_path.split("/")
    if any(not part or part in {".", ".."} or not _SAFE_PATH_PART.fullmatch(part) for part in parts):
        raise InvalidBlobPathError("invalid showcase media blob path")
    return "/".join(parts)


def _extension_for(content_type: str) -> str:
    try:
        return _CONTENT_TYPE_EXTENSIONS[content_type]
    except KeyError:
        raise ValueError("unsupported showcase photo content type")


def _pending_blob_path(player_api_id: int, media_id: int, content_type: str) -> str:
    if player_api_id <= 0 or media_id <= 0:
        raise ValueError("player_api_id and media_id must be positive")
    extension = _extension_for(content_type)
    return f"players/{player_api_id}/{media_id}/{uuid4().hex}.{extension}"


def _published_blob_path(blob_path: str) -> str:
    safe_path = _validate_blob_path(blob_path)
    stem, separator, _extension = safe_path.rpartition(".")
    return f"{stem}.jpg" if separator else f"{safe_path}.jpg"


def _quoted_dev_url(route_blob_path: str) -> str:
    return f"{DEV_ROUTE_PREFIX}/{quote(route_blob_path, safe='/')}"


def mint_upload(player_api_id: int, media_id: int, content_type: str) -> dict:
    """Mint a direct single-shot BlockBlob PUT for a new pending photo."""
    _require_configured()
    blob_path = _pending_blob_path(player_api_id, media_id, content_type)
    expiry = datetime.now(UTC) + timedelta(minutes=UPLOAD_SAS_MINUTES)
    headers = {"x-ms-blob-type": "BlockBlob", "Content-Type": content_type}

    if is_azure_configured():
        sas = _mint_sas(
            _pending_container(),
            blob_path,
            # A single-shot upload only needs create permission. Omitting
            # ``write`` prevents the same SAS from overwriting the blob after
            # /complete or after an admin has previewed it.
            BlobSasPermissions(create=True),
            expiry,
        )
        blob = _service_client().get_blob_client(_pending_container(), blob_path)
        url = f"{blob.url}?{sas}"
    else:
        url = _quoted_dev_url(blob_path)

    return {
        "blob_path": blob_path,
        "url": url,
        "method": "PUT",
        "headers": headers,
        "expires_at": expiry.isoformat(),
    }


def verify_pending(blob_path: str) -> dict:
    """Verify that a pending upload exists, is non-empty, and is within cap."""
    _require_configured()
    blob_path = _validate_blob_path(blob_path)
    try:
        if is_azure_configured():
            blob = _service_client().get_blob_client(_pending_container(), blob_path)
            size_bytes = int(blob.get_blob_properties().size)
        else:
            path = local_pending_path(blob_path)
            if not path.is_file():
                return {"ok": False, "error": "pending upload not found"}
            size_bytes = path.stat().st_size
    except Exception as exc:  # missing blob, network, or auth all mean unverified
        logger.warning("showcase pending blob verify failed for %s: %s", blob_path, exc)
        return {"ok": False, "error": "pending upload not found or unreadable"}

    if size_bytes <= 0:
        return {"ok": False, "error": "uploaded photo is empty", "size_bytes": size_bytes}
    if size_bytes > max_photo_bytes():
        return {
            "ok": False,
            "error": f"uploaded photo exceeds {max_photo_bytes() // 1024**2}MB cap",
            "size_bytes": size_bytes,
        }
    return {"ok": True, "size_bytes": size_bytes}


def read_pending_bytes(blob_path: str) -> bytes:
    """Read a verified-size pending upload for the moderation processor."""
    check = verify_pending(blob_path)
    if not check["ok"]:
        raise StoredMediaError(check["error"])
    blob_path = _validate_blob_path(blob_path)

    if is_azure_configured():
        blob = _service_client().get_blob_client(_pending_container(), blob_path)
        # Keep memory bounded even if external state changes after verification.
        raw = blob.download_blob(offset=0, length=max_photo_bytes() + 1, max_concurrency=1).readall()
    else:
        raw = local_pending_path(blob_path).read_bytes()

    # Defend against a blob swap or local-file growth between verify and read.
    if not raw or len(raw) > max_photo_bytes():
        raise StoredMediaError("pending upload changed during moderation")
    return raw


def publish(blob_path: str, processed_bytes: bytes, content_type: str = "image/jpeg") -> str:
    """Write processed bytes to the public container and return its public URL."""
    _require_configured()
    if content_type != "image/jpeg":
        raise ValueError("approved showcase photos must be JPEG")
    if not processed_bytes:
        raise StoredMediaError("processed photo is empty")

    public_blob_path = _published_blob_path(blob_path)
    if is_azure_configured():
        blob = _service_client().get_blob_client(_public_container(), public_blob_path)
        blob.upload_blob(
            processed_bytes,
            overwrite=True,
            content_settings=ContentSettings(content_type=content_type),
        )
        return blob.url

    path = local_public_path(public_blob_path, create_parent=True)
    temporary_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary_path.write_bytes(processed_bytes)
        os.replace(temporary_path, path)
    finally:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass
    return _quoted_dev_url(f"published/{public_blob_path}")


def delete_pending(blob_path: str) -> None:
    """Idempotently delete a pending upload."""
    _require_configured()
    blob_path = _validate_blob_path(blob_path)
    if is_azure_configured():
        blob = _service_client().get_blob_client(_pending_container(), blob_path)
        try:
            blob.delete_blob(delete_snapshots="include")
        except Exception as exc:
            if ResourceNotFoundError is not None and isinstance(exc, ResourceNotFoundError):
                return
            raise
        return
    try:
        local_pending_path(blob_path).unlink()
    except FileNotFoundError:
        pass


def _public_blob_path_from_reference(public_url_or_blob_path: str) -> str:
    if not isinstance(public_url_or_blob_path, str) or not public_url_or_blob_path:
        raise InvalidBlobPathError("invalid published media reference")

    parsed = urlparse(public_url_or_blob_path)
    path = unquote(parsed.path)
    dev_prefix = f"{DEV_ROUTE_PREFIX}/published/"
    if path.startswith(dev_prefix):
        return _validate_blob_path(path[len(dev_prefix) :])

    public_prefix = f"/{_public_container()}/"
    if path.startswith(public_prefix):
        return _validate_blob_path(path[len(public_prefix) :])

    plain_path = public_url_or_blob_path
    if plain_path.startswith("published/"):
        plain_path = plain_path[len("published/") :]
    safe_path = _validate_blob_path(plain_path)
    return _published_blob_path(safe_path)


def delete_published(public_url_or_blob_path: str) -> None:
    """Idempotently delete an approved blob by its public URL or source path."""
    _require_configured()
    public_blob_path = _public_blob_path_from_reference(public_url_or_blob_path)
    if is_azure_configured():
        blob = _service_client().get_blob_client(_public_container(), public_blob_path)
        try:
            blob.delete_blob(delete_snapshots="include")
        except Exception as exc:
            if ResourceNotFoundError is not None and isinstance(exc, ResourceNotFoundError):
                return
            raise
        return
    try:
        local_public_path(public_blob_path).unlink()
    except FileNotFoundError:
        pass


def pending_preview_url(blob_path: str) -> str:
    """Return a short-lived read URL for a non-public pending upload."""
    _require_configured()
    blob_path = _validate_blob_path(blob_path)
    if not is_azure_configured():
        return _quoted_dev_url(blob_path)

    expiry = datetime.now(UTC) + timedelta(minutes=PREVIEW_SAS_MINUTES)
    sas = _mint_sas(
        _pending_container(),
        blob_path,
        BlobSasPermissions(read=True),
        expiry,
    )
    blob = _service_client().get_blob_client(_pending_container(), blob_path)
    return f"{blob.url}?{sas}"


def _local_root() -> Path:
    configured = os.getenv("SHOWCASE_MEDIA_LOCAL_DIR")
    root = Path(configured) if configured else Path(tempfile.gettempdir()) / "academy-watch-showcase-media"
    return root.expanduser().resolve()


def _local_path(base: Path, blob_path: str, create_parent: bool) -> Path:
    _require_configured()
    if not is_local_dev_enabled():
        raise StorageNotConfiguredError("local showcase media storage is disabled")
    blob_path = _validate_blob_path(blob_path)
    resolved_base = base.resolve()
    path = (resolved_base / Path(*blob_path.split("/"))).resolve()
    if path != resolved_base and resolved_base not in path.parents:
        raise InvalidBlobPathError("showcase media path escapes local storage root")
    if create_parent:
        path.parent.mkdir(parents=True, exist_ok=True)
    return path


def local_pending_path(blob_path: str, create_parent: bool = False) -> Path:
    """Resolve a pending blob within the local-dev root."""
    return _local_path(_local_root() / "pending", blob_path, create_parent)


def local_public_path(blob_path: str, create_parent: bool = False) -> Path:
    """Resolve an approved blob within the local-dev root."""
    return _local_path(_local_root() / "public", blob_path, create_parent)


def local_serving_path(route_blob_path: str) -> Path:
    """Resolve a dev GET route path to pending or approved local storage.

    ``published/`` is a route-only namespace. PUT handlers should use
    :func:`local_pending_path` so an upload can never write to the public area.
    """
    if route_blob_path.startswith("published/"):
        return local_public_path(route_blob_path[len("published/") :])
    return local_pending_path(route_blob_path)
