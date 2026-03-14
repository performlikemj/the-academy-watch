"""Shared slugification helpers for team URLs and other human-readable identifiers."""

from __future__ import annotations

import re
import unicodedata
from typing import Optional

from flask import abort


def slugify_label(value: Optional[str]) -> str:
    """Convert a string to a URL-safe slug."""
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_value)
    return cleaned.strip("-").lower()


def generate_unique_team_slug(
    name: str,
    country: Optional[str],
    team_id: int,
    existing_slugs: set[str],
) -> str:
    """Generate a unique slug for a team, appending country or ID on collision."""
    base = slugify_label(name)
    if not base:
        base = f"team-{team_id}"

    # Try base slug first
    if base not in existing_slugs:
        return base

    # Append country
    if country:
        with_country = f"{base}-{slugify_label(country)}"
        if with_country not in existing_slugs:
            return with_country

    # Append API team ID as last resort
    return f"{base}-{team_id}"


def resolve_team_by_identifier(identifier: str):
    """Look up a Team by slug or numeric DB primary-key ID.

    Returns the Team ORM object or aborts with 404.
    """
    from src.models.league import Team, TeamProfile

    # Numeric → look up by DB primary key (backward compat)
    if identifier.isdigit():
        team = Team.query.get(int(identifier))
        if team:
            return team
        # Also try as an API team_id for robustness
        team = (
            Team.query.filter_by(team_id=int(identifier), is_active=True)
            .order_by(Team.season.desc())
            .first()
        )
        if team:
            return team
        abort(404)

    # Slug → look up TeamProfile, then find latest-season Team
    profile = TeamProfile.query.filter_by(slug=identifier).first()
    if not profile:
        abort(404)

    team = (
        Team.query.filter_by(team_id=profile.team_id, is_active=True)
        .order_by(Team.season.desc())
        .first()
    )
    if not team:
        # Fallback: any season
        team = (
            Team.query.filter_by(team_id=profile.team_id)
            .order_by(Team.season.desc())
            .first()
        )
    if not team:
        abort(404)

    return team
