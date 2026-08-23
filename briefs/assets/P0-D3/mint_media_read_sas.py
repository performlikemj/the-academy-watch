def mint_media_read_sas(blob_path: str, *, seconds: int = MEDIA_READ_SAS_MINUTES * 60) -> str:
    """Short read-only SAS for the browser footage redirect — never longer than the media token, and never
    longer than the token's REMAINING life when the caller passes it (``seconds``)."""
    ttl = max(1, min(int(seconds), MEDIA_READ_SAS_MINUTES * 60))
    expiry = datetime.now(UTC) + timedelta(seconds=ttl)
    sas = _mint_sas(blob_path, BlobSasPermissions(read=True), expiry)
    client = _service_client()
    return f"{client.url}{_container()}/{blob_path}?{sas}"
