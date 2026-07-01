"""Utility helpers to sanitize user-provided text before storage or rendering."""

from __future__ import annotations

from urllib.parse import urlparse

import bleach

# Allow only very basic formatting; expand if richer markup is desired later.
_COMMENT_ALLOWED_TAGS: list[str] = []
_COMMENT_ALLOWED_ATTRS: dict[str, list[str]] = {}

# Commentary allows richer formatting for newsletter authors
_COMMENTARY_ALLOWED_TAGS: list[str] = ["p", "br", "strong", "em", "a", "ul", "ol", "li", "blockquote"]
_COMMENTARY_ALLOWED_ATTRS: dict[str, list[str]] = {
    "a": ["href", "title"],
}
_COMMENTARY_ALLOWED_PROTOCOLS: list[str] = ["http", "https"]
_COMMENTARY_MAX_LENGTH: int = 5000


def sanitize_comment_body(value: str) -> str:
    """Strip dangerous HTML from comment bodies while preserving whitespace."""
    return bleach.clean(value, tags=_COMMENT_ALLOWED_TAGS, attributes=_COMMENT_ALLOWED_ATTRS, strip=True)


def sanitize_plain_text(value: str) -> str:
    """Remove HTML tags from simple text fields such as author names."""
    return bleach.clean(value, tags=[], attributes={}, strip=True)


def sanitize_commentary_html(value: str) -> str:
    """
    Sanitize HTML for newsletter commentary with strict whitelist.

    Allows rich formatting (bold, italic, links, lists, paragraphs) while
    preventing XSS attacks by stripping scripts, event handlers, and
    dangerous protocols.

    Args:
        value: The HTML content to sanitize

    Returns:
        Sanitized HTML string with only allowed tags and attributes

    Raises:
        ValueError: If content exceeds maximum length
    """
    if not value:
        return ""

    # Enforce maximum length
    if len(value) > _COMMENTARY_MAX_LENGTH:
        raise ValueError(f"Commentary content exceeds maximum length of {_COMMENTARY_MAX_LENGTH} characters")

    # Sanitize HTML with strict whitelist
    cleaned = bleach.clean(
        value,
        tags=_COMMENTARY_ALLOWED_TAGS,
        attributes=_COMMENTARY_ALLOWED_ATTRS,
        protocols=_COMMENTARY_ALLOWED_PROTOCOLS,
        strip=True,
    )

    # Add rel="noopener noreferrer" to all links for security
    cleaned = bleach.linkify(
        cleaned,
        callbacks=[
            lambda attrs, new: attrs if attrs.get((None, "href"), "").startswith(("http://", "https://")) else None
        ],
        parse_email=False,
    )

    return cleaned


def is_safe_https_url(value: str) -> bool:
    """True only for a well-formed absolute ``https://`` URL.

    Rejects ``javascript:``, ``data:``, ``mailto:`` and every non-https scheme
    outright. User-submitted URLs are rendered as link ``href``s; React does not
    neutralise ``javascript:`` hrefs, so an unvalidated URL is a stored
    XSS-on-click vector. A single shared check keeps player links and showcase
    reel items on the same allow-list.
    """
    if not value or not isinstance(value, str):
        return False
    try:
        parsed = urlparse(value.strip())
    except (ValueError, TypeError):
        return False
    return parsed.scheme == "https" and bool(parsed.netloc)


__all__ = [
    "sanitize_comment_body",
    "sanitize_plain_text",
    "sanitize_commentary_html",
    "is_safe_https_url",
]
