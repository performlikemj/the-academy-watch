

def mint_media_read_sas(blob_path: str, minutes: int = MEDIA_READ_SAS_MINUTES) -> str:
    """Short read-only SAS for the browser footage redirect — never longer than the media token."""
    expiry = datetime.now(UTC) + timedelta(minutes=minutes)
    sas = _mint_sas(blob_path, BlobSasPermissions(read=True), expiry)
    client = _service_client()
    return f"{client.url}{_container()}/{blob_path}?{sas}"
