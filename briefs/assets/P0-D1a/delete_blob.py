

def delete_blob(blob_path: str) -> bool:
    """Delete one raw-footage blob. True when it is gone afterwards (deleted now, or already absent)."""
    try:
        blob = _service_client().get_blob_client(_container(), blob_path)
        blob.delete_blob()
        return True
    except Exception as e:  # auth, network — all mean "not gone"; a 404 means it was already gone
        if getattr(e, "status_code", None) == 404:
            return True
        logger.warning("video blob delete failed for %s: %s", blob_path, e)
        return False
