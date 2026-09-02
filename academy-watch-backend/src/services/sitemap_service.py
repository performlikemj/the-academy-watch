"""Public sitemap enumeration with a short in-process cache."""

from __future__ import annotations

import os
import time
import xml.etree.ElementTree as ET

import sqlalchemy as sa
from src.models.funding import ClubProgram, FundingLeague
from src.models.league import Newsletter, Team, TeamProfile, db
from src.models.showcase import LocalPlayer
from src.models.tracked_player import TrackedPlayer
from src.services.player_suppression import without_active_suppression
from src.services.public_player_subject import resolve_public_adult_subject

DEFAULT_PUBLIC_BASE_URL = "https://theacademywatch.com"
SITEMAP_CACHE_TTL_SECONDS = 60 * 60
SITEMAP_MAX_PLAYER_CANDIDATES = 2_000
SITEMAP_MAX_URLS = 5_000
SITEMAP_NAMESPACE = "http://www.sitemaps.org/schemas/sitemap/0.9"

_sitemap_cache: tuple[float, bytes] | None = None


def clear_sitemap_cache() -> None:
    """Discard the cached sitemap so the next request rebuilds it."""

    global _sitemap_cache
    _sitemap_cache = None


def _public_base_url() -> str:
    return (os.getenv("PUBLIC_BASE_URL") or DEFAULT_PUBLIC_BASE_URL).rstrip("/")


def _player_candidate_ids() -> list[int]:
    """Return the capped, distinct SQL-prefiltered signed player ids."""

    tracked_ids = sa.select(TrackedPlayer.player_api_id.label("player_api_id")).where(
        TrackedPlayer.is_active.is_(True),
        TrackedPlayer.data_source != "owning-club",
        without_active_suppression(TrackedPlayer.player_api_id),
    )
    local_ids = sa.select(LocalPlayer.api_player_id.label("player_api_id")).where(
        LocalPlayer.status == "approved",
        LocalPlayer.merged_into_local_player_id.is_(None),
        LocalPlayer.api_player_id < 0,
        LocalPlayer.api_player_id == -LocalPlayer.id,
        without_active_suppression(LocalPlayer.api_player_id),
    )
    candidates = tracked_ids.union(local_ids).subquery()
    statement = (
        sa.select(candidates.c.player_api_id)
        .order_by(candidates.c.player_api_id.asc())
        .limit(SITEMAP_MAX_PLAYER_CANDIDATES)
    )
    return [int(player_id) for player_id in db.session.execute(statement).scalars()]


def _team_slugs():
    matching_team = sa.exists().where(Team.team_id == TeamProfile.team_id)
    statement = (
        sa.select(TeamProfile.slug)
        .where(
            TeamProfile.slug.is_not(None),
            sa.func.length(sa.func.trim(TeamProfile.slug)) > 0,
            matching_team,
        )
        .distinct()
        .order_by(TeamProfile.slug.asc())
    )
    return db.session.execute(statement).scalars()


def _newsletter_slugs():
    statement = (
        sa.select(Newsletter.public_slug)
        .where(Newsletter.published.is_(True))
        .distinct()
        .order_by(Newsletter.public_slug.asc())
    )
    return db.session.execute(statement).scalars()


def _program_slugs():
    statement = (
        sa.select(ClubProgram.slug)
        .join(FundingLeague, ClubProgram.funding_league_id == FundingLeague.id)
        .where(
            ClubProgram.platform_status == "approved",
            ClubProgram.emergency_hidden.is_(False),
            FundingLeague.registry_status == "approved",
        )
        .distinct()
        .order_by(ClubProgram.slug.asc())
    )
    return db.session.execute(statement).scalars()


def _append_slug_urls(locations: list[str], base_url: str, prefix: str, slugs) -> None:
    for slug in slugs:
        if len(locations) >= SITEMAP_MAX_URLS:
            return
        cleaned_slug = str(slug or "").strip()
        if cleaned_slug:
            locations.append(f"{base_url}/{prefix}/{cleaned_slug}")


def _render_sitemap_xml() -> bytes:
    base_url = _public_base_url()
    locations = [f"{base_url}/"]

    for player_api_id in _player_candidate_ids():
        if len(locations) >= SITEMAP_MAX_URLS:
            break
        if resolve_public_adult_subject(player_api_id) is None:
            continue
        if player_api_id < 0:
            locations.append(f"{base_url}/local-players/{-player_api_id}")
        else:
            locations.append(f"{base_url}/players/{player_api_id}")

    if len(locations) < SITEMAP_MAX_URLS:
        _append_slug_urls(locations, base_url, "teams", _team_slugs())
    if len(locations) < SITEMAP_MAX_URLS:
        _append_slug_urls(locations, base_url, "newsletters", _newsletter_slugs())
    if len(locations) < SITEMAP_MAX_URLS:
        _append_slug_urls(locations, base_url, "programs", _program_slugs())

    ET.register_namespace("", SITEMAP_NAMESPACE)
    urlset = ET.Element(f"{{{SITEMAP_NAMESPACE}}}urlset")
    for location in locations:
        url = ET.SubElement(urlset, f"{{{SITEMAP_NAMESPACE}}}url")
        ET.SubElement(url, f"{{{SITEMAP_NAMESPACE}}}loc").text = location
    return ET.tostring(urlset, encoding="utf-8", xml_declaration=True)


def build_sitemap_xml() -> bytes:
    """Return sitemap XML, rebuilding it after the one-hour cache TTL."""

    global _sitemap_cache
    now = time.monotonic()
    if _sitemap_cache is not None and now - _sitemap_cache[0] < SITEMAP_CACHE_TTL_SECONDS:
        return _sitemap_cache[1]

    xml = _render_sitemap_xml()
    _sitemap_cache = (now, xml)
    return xml


__all__ = ["build_sitemap_xml", "clear_sitemap_cache"]
