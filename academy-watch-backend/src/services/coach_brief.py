"""Shared normalization and limits for private coach's-brief input."""

import hashlib

MAX_BRIEF_CHARS = 2000
MAX_BRIEF_LINES = 8
MAX_BRIEF_LINE_CHARS = 240


def brief_payload(body: str | None, *, max_lines: int = MAX_BRIEF_LINES) -> dict | None:
    """Return the worker-compatible normalized lines and content hash."""
    if not isinstance(body, str):
        return None
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    if not lines or len(lines) > max_lines:
        return None
    normalized_body = "\n".join(lines)
    return {
        "lines": lines,
        "hash": hashlib.sha256(normalized_body.encode("utf-8")).hexdigest(),
    }
