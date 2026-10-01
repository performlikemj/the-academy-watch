"""Backend source of truth for the hidden legacy public pages.

Keep the frontend route gate in src/lib/legacyRoutes.js aligned with this gate.
Newsletter delivery and data freezes are independent of public page visibility.
"""

LEGACY_PUBLIC_PAGES = False
LEGACY_PUBLIC_ROOTS = frozenset(
    {"dream-team", "academy", "teams", "newsletters", "journalists", "writeups", "submit-take"}
)


def legacy_public_url(url: str | None) -> str | None:
    """Omit a known legacy public URL while its page is hidden.

    Call only for legacy public destinations; player, settings and API links
    retain their existing URLs. Preserve the supplied URL verbatim when enabled.
    """
    return url if LEGACY_PUBLIC_PAGES else None
