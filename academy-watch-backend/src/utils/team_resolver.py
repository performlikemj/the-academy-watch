"""Team resolution utilities — single source of truth for team name lookups.

All surfaces (API endpoints, newsletter, GOL bot DB queries) should use
these functions to resolve API-Football team IDs to human-readable names.
"""

import logging

from flask import abort
from src.models.league import Team, TeamProfile, db

logger = logging.getLogger(__name__)


def resolve_team_name_and_logo(team_api_id: int, season: int = None) -> tuple[str, str | None]:
    """Resolve team name and logo from multiple sources with fallback chain.

    Returns (team_name, team_logo) tuple. Always returns a non-empty team_name.

    Fallback order:
    1. Team table (any season, prefer current)
    2. TeamProfile table (stores canonical team info)
    3. API Football client (fetch from API) — also caches to TeamProfile
    4. Final fallback: "Team {id}"
    """
    if not team_api_id:
        return "Unknown", None

    # 1. Try Team table
    if season:
        team = Team.query.filter_by(team_id=team_api_id, season=season).first()
    else:
        team = Team.query.filter_by(team_id=team_api_id).first()

    if team and team.name:
        return team.name, team.logo

    # 2. Try TeamProfile table (canonical, no season)
    try:
        profile = TeamProfile.query.filter_by(team_id=team_api_id).first()
        if profile and profile.name:
            return profile.name, profile.logo_url
    except Exception:
        pass

    # 3. Try API Football client as last resort
    try:
        from src.api_football_client import APIFootballClient

        client = APIFootballClient()
        team_name = client.get_team_name(team_api_id, season)
        if team_name and team_name != f"Team {team_api_id}":
            team_info = client._team_profile_cache.get(team_api_id) or {}
            team_logo = team_info.get("team", {}).get("logo")

            # Cache to TeamProfile for future lookups
            try:
                from src.utils.slug import generate_unique_team_slug

                existing = TeamProfile.query.filter_by(team_id=team_api_id).first()
                if not existing:
                    team_data = team_info.get("team", {})
                    venue_data = team_info.get("venue", {})
                    country = team_data.get("country")
                    existing_slugs = set(
                        row[0] for row in db.session.query(TeamProfile.slug).filter(TeamProfile.slug.isnot(None)).all()
                    )
                    slug = generate_unique_team_slug(team_name, country, team_api_id, existing_slugs)
                    new_profile = TeamProfile(
                        team_id=team_api_id,
                        name=team_name,
                        code=team_data.get("code"),
                        country=country,
                        founded=team_data.get("founded"),
                        is_national=team_data.get("national"),
                        logo_url=team_logo,
                        slug=slug,
                        venue_id=venue_data.get("id"),
                        venue_name=venue_data.get("name"),
                        venue_address=venue_data.get("address"),
                        venue_city=venue_data.get("city"),
                        venue_capacity=venue_data.get("capacity"),
                        venue_surface=venue_data.get("surface"),
                        venue_image=venue_data.get("image"),
                    )
                    db.session.add(new_profile)
                    db.session.commit()
                    logger.info("Cached team profile for %s (id=%d)", team_name, team_api_id)
            except Exception as cache_err:
                logger.warning("Failed to cache team profile for %d: %s", team_api_id, cache_err)
                try:
                    db.session.rollback()
                except Exception:
                    pass

            return team_name, team_logo
    except Exception as e:
        logger.warning("Failed to resolve team name from API for team_id=%d: %s", team_api_id, e)

    # 4. Final fallback
    return f"Team {team_api_id}", None


def resolve_team_name(team_api_id: int) -> str:
    """Single source of truth for team name from API-Football team ID."""
    name, _ = resolve_team_name_and_logo(team_api_id)
    return name


def _latest_for_api_team_id(api_team_id: int) -> int | None:
    """Return the DB primary key for the newest season row that matches an API team_id."""
    try:
        latest = Team.query.filter_by(team_id=api_team_id).order_by(Team.season.desc()).first()
        return latest.id if latest else None
    except Exception:
        return None


def resolve_latest_team_id(identifier: int, *, assume_api_id: bool = False) -> int | None:
    """Resolve a team identifier to the latest season's database row."""
    try:
        if assume_api_id:
            return _latest_for_api_team_id(int(identifier))

        team = db.session.get(Team, identifier)
        if team:
            latest = Team.query.filter_by(team_id=team.team_id).order_by(Team.season.desc()).first()
            return latest.id if latest else identifier

        return _latest_for_api_team_id(int(identifier))
    except Exception:
        return None


def is_placeholder_name(name: str | None) -> bool:
    """Return True if a player name looks like a placeholder (e.g. 'Player 12345', 'Unknown')."""
    if not name:
        return True
    s = str(name).strip()
    if not s:
        return True
    low = s.lower()
    return low.startswith("player ") or low.startswith("unknown")


def is_placeholder_team_name(name: str | None) -> bool:
    """Return True if a team name looks like a placeholder (e.g. 'Team 12345')."""
    if not name:
        return True
    s = str(name).strip()
    if not s:
        return True
    return s.lower().startswith("team ")


def update_team_name_if_missing(team_row, *, season: int, dry_run: bool = False) -> dict:
    """Update a Team row's name when it is a placeholder.

    Uses the centralized resolve_team_name_and_logo fallback chain
    (Team table → TeamProfile → API-Football → placeholder).
    Returns a dict with status and optional new_name/error for logging.
    """
    if not team_row:
        return {"status": "no_team_row"}

    current_name = getattr(team_row, "name", None)
    api_team_id = getattr(team_row, "team_id", None)

    if not is_placeholder_team_name(current_name):
        return {"status": "ok_existing", "name": current_name}

    if not api_team_id:
        return {"status": "missing_api_id"}

    try:
        new_name, _ = resolve_team_name_and_logo(api_team_id, season)
    except Exception as exc:
        return {"status": "error", "error": str(exc)}

    if not new_name or is_placeholder_team_name(new_name):
        return {"status": "no_name_found"}

    if dry_run:
        return {"status": "would_update", "new_name": new_name}

    team_row.name = new_name
    return {"status": "updated", "new_name": new_name}


def resolve_team_by_identifier(identifier: str):
    """Look up a Team by slug or numeric DB primary-key ID. Aborts with 404 if not found."""
    if identifier.isdigit():
        team = db.session.get(Team, int(identifier))
        if team:
            return team
        team = Team.query.filter_by(team_id=int(identifier), is_active=True).order_by(Team.season.desc()).first()
        if team:
            return team
        abort(404)

    profile = TeamProfile.query.filter_by(slug=identifier).first()
    if not profile:
        abort(404)

    team = Team.query.filter_by(team_id=profile.team_id, is_active=True).order_by(Team.season.desc()).first()
    if not team:
        team = Team.query.filter_by(team_id=profile.team_id).order_by(Team.season.desc()).first()
    if not team:
        abort(404)

    return team
