    if match.expires_at is None:  # first completion stamps the deadline; a reattestation keeps the original one
        match.expires_at = now + timedelta(days=RAW_RETENTION_DAYS)
