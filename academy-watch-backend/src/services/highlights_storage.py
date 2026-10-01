"""Private storage adapter. App reads only bounded standalone outputs; worker owns source access."""

import time
from pathlib import Path

from src.services import video_storage

MAX_OUTPUT_BYTES = 30 * 1024 * 1024
MAX_SOURCE_BYTES = 12 * 1024**3


def download_source(blob_path, snapshot, etag, destination):
    if not snapshot or not etag:
        raise ValueError("immutable_source_required")
    from azure.core import MatchConditions

    blob = video_storage._service_client().get_blob_client(video_storage._container(), blob_path, snapshot=snapshot)
    properties = blob.get_blob_properties(timeout=30)
    if properties.etag != etag or not 0 < properties.size <= MAX_SOURCE_BYTES:
        raise ValueError("source_changed")
    stream = blob.download_blob(etag=etag, match_condition=MatchConditions.IfNotModified, max_concurrency=1, timeout=30)
    total = 0
    deadline = time.monotonic() + 300
    with Path(destination).open("wb") as output:
        for chunk in stream.chunks():
            total += len(chunk)
            if total > MAX_SOURCE_BYTES or time.monotonic() > deadline:
                raise ValueError("source_limit_exceeded")
            output.write(chunk)


def upload_output(blob_path, file_path):
    from azure.storage.blob import ContentSettings

    size = Path(file_path).stat().st_size
    if not 0 < size <= MAX_OUTPUT_BYTES:
        raise ValueError("output_limit_exceeded")
    blob = video_storage._service_client().get_blob_client(video_storage._container(), blob_path)
    with Path(file_path).open("rb") as content:
        result = blob.upload_blob(
            content,
            overwrite=False,
            timeout=30,
            content_settings=ContentSettings(content_type="video/mp4", cache_control="private, no-store"),
        )
    return result["etag"], size


def output_read_url(blob_path, etag, *, expires_at):
    """One immutable attempt blob, read only, 60 seconds. Never a raw/container grant."""
    import re

    if not etag or not re.fullmatch(r"highlights/[a-f0-9-]{36}/[a-f0-9-]{36}\.mp4", blob_path):
        raise ValueError("invalid_output")
    client = video_storage._service_client().get_blob_client(video_storage._container(), blob_path)
    if client.get_blob_properties(timeout=5).etag != etag:
        raise ValueError("output_changed")
    return video_storage.mint_media_read_sas(blob_path, seconds=60, expires_at=expires_at)
