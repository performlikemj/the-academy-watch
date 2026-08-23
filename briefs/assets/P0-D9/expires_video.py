    if match.expires_at is None:  # first completion stamps the deadline; a reattestation keeps the original one
        match.expires_at = datetime.now(UTC) + timedelta(days=RAW_RETENTION_DAYS)
