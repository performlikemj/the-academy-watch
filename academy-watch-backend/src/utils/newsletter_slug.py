"""Helpers for generating stable newsletter slugs."""

from __future__ import annotations

from datetime import date

from src.utils.slug import slugify_label as _slugify_label

__all__ = ["compose_newsletter_public_slug"]


def compose_newsletter_public_slug(
    *,
    team_name: str | None,
    newsletter_type: str | None,
    week_start: date | None,
    week_end: date | None,
    issue_date: date | None,
    identifier: int | None,
) -> str:
    """Generate a deterministic slug for newsletter URLs.

    The slug incorporates the team name, newsletter type, relevant date, and the
    newsletter's identifier to ensure uniqueness and readability.
    """

    date_value = week_end or issue_date or week_start
    segments: list[str] = []

    team_slug = _slugify_label(team_name)
    if team_slug:
        segments.append(team_slug)

    type_slug = _slugify_label(newsletter_type)
    if type_slug:
        segments.append(type_slug)

    if date_value:
        segments.append(date_value.isoformat())

    if identifier:
        segments.append(str(identifier))

    if not segments:
        base = "newsletter"
        if identifier:
            return f"{base}-{identifier}"[:200]
        return base

    slug = "-".join(segments)
    return slug[:200]
