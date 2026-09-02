"""Public sitemap enumeration with background stale-while-revalidate caching."""

from __future__ import annotations

import logging
import math
import os
import threading
import time
import xml.etree.ElementTree as ET

import sqlalchemy as sa
from flask import current_app, make_response
from src.models.funding import ClubProgram, FundingLeague
from src.models.league import Newsletter, Team, TeamProfile, db
from src.models.showcase import LocalPlayer
from src.models.tracked_player import TrackedPlayer
from src.services.player_suppression import without_active_suppression
from src.services.public_player_subject import resolve_public_adult_subject

logger = logging.getLogger(__name__)

DEFAULT_PUBLIC_BASE_URL = "https://theacademywatch.com"
SITEMAP_TTL_SECONDS = 3_600.0
SITEMAP_MAX_PLAYER_CANDIDATES = 500
SITEMAP_BUILD_BUDGET_SECONDS = 240.0
SITEMAP_MAX_URLS = 5_000
SITEMAP_NAMESPACE = "http://www.sitemaps.org/schemas/sitemap/0.9"

_cache: dict[str, bytes | float | None] = {"xml": None, "built_at": None}
_cache_generation = 0
_build_lock = threading.Lock()
_building = False
_build_thread: threading.Thread | None = None


def clear_sitemap_cache() -> None:
    """Discard cached XML after any active background build finishes."""

    global _cache_generation
    with _build_lock:
        _cache.update(xml=None, built_at=None)
        _cache_generation += 1


def wait_for_build(timeout: float | None = 5.0) -> bool:
    """Wait for the current background build; intended for deterministic tests."""

    thread = _build_thread
    if thread is None:
        return True
    thread.join(timeout)
    return not thread.is_alive()


def _env_nonnegative_int(name: str, default: int) -> int:
    raw_value = (os.getenv(name) or "").strip()
    if not raw_value:
        return default
    try:
        value = int(raw_value)
    except ValueError:
        logger.warning("Ignoring invalid %s value %r", name, raw_value)
        return default
    if value < 0:
        logger.warning("Ignoring negative %s value %r", name, raw_value)
        return default
    return value


def _env_nonnegative_float(name: str, default: float) -> float:
    raw_value = (os.getenv(name) or "").strip()
    if not raw_value:
        return default
    try:
        value = float(raw_value)
    except ValueError:
        logger.warning("Ignoring invalid %s value %r", name, raw_value)
        return default
    if not math.isfinite(value) or value < 0:
        logger.warning("Ignoring invalid %s value %r", name, raw_value)
        return default
    return value


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
        .limit(_env_nonnegative_int("SITEMAP_MAX_PLAYER_CANDIDATES", SITEMAP_MAX_PLAYER_CANDIDATES))
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
    build_started_at = time.monotonic()
    build_budget_seconds = _env_nonnegative_float(
        "SITEMAP_BUILD_BUDGET_SECONDS",
        SITEMAP_BUILD_BUDGET_SECONDS,
    )
    base_url = _public_base_url()
    locations = [f"{base_url}/"]
    candidates_checked = 0
    players_emitted = 0

    for player_api_id in _player_candidate_ids():
        if len(locations) >= SITEMAP_MAX_URLS:
            break
        if time.monotonic() - build_started_at >= build_budget_seconds:
            logger.warning(
                "Sitemap player build budget reached after checking %d candidates and emitting %d players",
                candidates_checked,
                players_emitted,
            )
            break
        candidates_checked += 1
        if resolve_public_adult_subject(player_api_id) is None:
            continue
        if player_api_id < 0:
            locations.append(f"{base_url}/local-players/{-player_api_id}")
        else:
            locations.append(f"{base_url}/players/{player_api_id}")
        players_emitted += 1

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
    """Synchronously build uncached sitemap XML."""

    return _render_sitemap_xml()


def _run_background_build(app) -> None:
    global _building, _build_thread, _cache_generation

    try:
        with app.app_context():
            xml = build_sitemap_xml()
        _cache.update(xml=xml, built_at=time.monotonic())
        _cache_generation += 1
    except Exception:
        logger.exception("Background sitemap build failed")
    finally:
        _building = False
        _build_thread = None
        _build_lock.release()


def _start_background_build(app, expected_generation: int) -> bool:
    """Start one daemon build without waiting for the long-held build lock."""

    global _building, _build_thread
    if _building:
        return False
    if not _build_lock.acquire(blocking=False):
        return False
    if _building or _cache_generation != expected_generation:
        _build_lock.release()
        return False

    _building = True
    try:
        thread = threading.Thread(target=_run_background_build, args=(app,), daemon=True)
        _build_thread = thread
        thread.start()
    except Exception:
        logger.exception("Could not start background sitemap build")
        _building = False
        _build_thread = None
        _build_lock.release()
        return False
    return True


def _sitemap_response(body: bytes | str, status: int, mimetype: str):
    response = make_response(body, status)
    response.mimetype = mimetype
    response.headers["Cache-Control"] = "no-store"
    return response


def get_sitemap_response():
    """Serve cached XML immediately and refresh stale or missing XML off-request."""

    now = time.monotonic()
    cache_generation = _cache_generation
    cached_xml = _cache["xml"]
    built_at = _cache["built_at"]
    app = current_app._get_current_object()

    if isinstance(cached_xml, bytes):
        ttl_seconds = _env_nonnegative_float("SITEMAP_TTL_SECONDS", SITEMAP_TTL_SECONDS)
        if not isinstance(built_at, (int, float)) or now - built_at >= ttl_seconds:
            _start_background_build(app, cache_generation)
        return _sitemap_response(cached_xml, 200, "application/xml")

    _start_background_build(app, cache_generation)
    response = _sitemap_response("Sitemap is being generated", 503, "text/plain")
    response.headers["Retry-After"] = "60"
    return response


__all__ = ["build_sitemap_xml", "clear_sitemap_cache", "get_sitemap_response", "wait_for_build"]
