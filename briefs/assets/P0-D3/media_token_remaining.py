

def media_token_remaining_seconds(token: str, match_id: int, max_age: int = MEDIA_TOKEN_TTL) -> int:
    """Seconds the media token has left (0 when missing/invalid/expired/for another match). Lets the footage
    redirect mint a SAS that dies WITH the token instead of outliving it by up to max_age."""
    if not token:
        return 0
    try:
        data, issued_at = _media_serializer().loads(token, max_age=max_age, return_timestamp=True)
    except Exception:  # bad signature, expired, malformed — all mean "deny"
        return 0
    if data.get("scope") != "media" or int(data.get("match_id", -1)) != int(match_id):
        return 0
    age = time.time() - issued_at.timestamp()
    return max(0, int(max_age - age))
