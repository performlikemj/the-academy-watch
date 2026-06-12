"""Player Journey API endpoints.

Handles player career journey retrieval for map visualization.

Primary data source: PlayerJourney + PlayerJourneyEntry (from API-Football sync).
Legacy fallback: TrackedPlayer records (for players not yet synced).
"""

import logging
from collections import defaultdict

from flask import Blueprint, jsonify, request
from src.auth import require_api_key
from src.models.journey import YOUTH_LEVELS, ClubLocation, PlayerJourney, PlayerJourneyEntry
from src.models.league import Team, TeamProfile, db
from src.models.tracked_player import TrackedPlayer
from src.utils.geocoding import get_team_coordinates
from src.utils.player_names import is_placeholder_name, resolve_player_profile

journey_bp = Blueprint("journey", __name__)
logger = logging.getLogger(__name__)


# =============================================================================
# Public Endpoints
# =============================================================================


@journey_bp.route("/players/<int:player_id>/journey", methods=["GET"])
def get_player_journey(player_id):
    """Get a player's career journey for map visualization.

    Tries PlayerJourney model first (full career data from API-Football),
    falls back to AcademyPlayer-based builder for unsynced players.

    Query params:
    - sync: bool - Trigger sync if journey doesn't exist (default: false)
    """
    should_sync = request.args.get("sync", "false").lower() == "true"

    # Try PlayerJourney first (the new, richer data source)
    journey = PlayerJourney.query.filter_by(player_api_id=player_id).first()

    # Re-sync if journey is missing, has a sync error, or has no entries
    needs_sync = not journey or journey.sync_error is not None or not journey.entries.first()
    if needs_sync and should_sync:
        try:
            from src.services.journey_sync import JourneySyncService

            service = JourneySyncService()
            journey = service.sync_player(player_id, force_full=bool(journey))
        except Exception as e:
            logger.warning(f"Journey sync failed for player {player_id}: {e}")

    if journey:
        journey_data = _build_journey_from_player_journey(journey)
        return jsonify(
            {
                "player_id": player_id,
                "source": "player_journey",
                **journey_data,
            }
        )

    # Fallback: build from TrackedPlayer records
    tp = TrackedPlayer.query.filter_by(player_api_id=player_id).first()
    primary_team_id = tp.team_id if tp else None

    journey_data = _build_legacy_journey(player_id, primary_team_id)

    return jsonify(
        {
            "player_id": player_id,
            "source": "tracked_player",
            **journey_data,
        }
    )


@journey_bp.route("/loans/<int:loaned_player_id>/journey", methods=["GET"])
def get_loan_journey(loaned_player_id):
    """Get journey for a specific TrackedPlayer record.

    Returns the complete journey for the player, including all loan stints
    across their career (not just the current loan).
    """
    tp = TrackedPlayer.query.get_or_404(loaned_player_id)

    # Try PlayerJourney first
    journey = PlayerJourney.query.filter_by(player_api_id=tp.player_api_id).first()
    if journey:
        journey_data = _build_journey_from_player_journey(journey)
    else:
        journey_data = _build_legacy_journey(tp.player_api_id, tp.team_id)

    return jsonify(
        {
            "loaned_player_id": loaned_player_id,
            "player_id": tp.player_api_id,
            "player_name": tp.player_name,
            **journey_data,
        }
    )


# =============================================================================
# Admin Repair Endpoints
# =============================================================================


@journey_bp.route("/admin/journeys/recompute-academy", methods=["POST"])
@require_api_key
def admin_recompute_academy():
    """Recompute academy_club_ids for journeys with entries, then deactivate
    TrackedPlayer rows that contradict academy provenance.

    Body: {"dry_run": bool (default true), "limit": int|null}

    A row contradicts provenance when:
    - its data_source is 'owning-club' (deprecated mechanism), OR
    - it is linked to a journey with entries whose recomputed
      academy_club_ids do not include the row's parent club.
    Pinned and manual rows are never touched.
    """
    from src.services.journey_sync import JourneySyncService

    data = request.get_json(silent=True) or {}
    dry_run = bool(data.get("dry_run", True))
    limit = data.get("limit")

    service = JourneySyncService()

    journeys_query = PlayerJourney.query.filter(
        PlayerJourney.id.in_(db.session.query(PlayerJourneyEntry.journey_id))
    ).order_by(PlayerJourney.id)
    if limit:
        journeys_query = journeys_query.limit(int(limit))
    journeys = journeys_query.all()

    journeys_processed = 0
    journeys_changed = 0
    deactivated_ids = set()
    examples = []
    recomputed = {}

    def _record_deactivation(tp, reason):
        deactivated_ids.add(tp.id)
        if len(examples) < 20:
            examples.append(
                {
                    "player_name": tp.player_name,
                    "parent_team": tp.team.name if tp.team else None,
                    "data_source": tp.data_source,
                    "reason": reason,
                }
            )

    for journey in journeys:
        old_ids = sorted(journey.academy_club_ids or [])
        before_active = TrackedPlayer.query.filter_by(
            player_api_id=journey.player_api_id,
            is_active=True,
        ).all()
        try:
            # Recomputes academy_club_ids AND runs the tracked-player upsert
            # (creates academy rows, deactivates non-academy rows). Nothing
            # in this path commits, so dry-run can roll back at the end.
            service._compute_academy_club_ids(journey)
        except Exception as exc:
            logger.warning("recompute-academy failed for journey %s: %s", journey.id, exc)
            continue
        journeys_processed += 1
        new_ids = sorted(journey.academy_club_ids or [])
        recomputed[journey.id] = set(new_ids)
        if old_ids != new_ids:
            journeys_changed += 1
        for tp in before_active:
            if tp.is_active is False and tp.id not in deactivated_ids:
                _record_deactivation(tp, "deactivated by journey upsert (parent is not an academy origin)")

    # ── Contradiction sweep across TrackedPlayer ──
    active_rows = TrackedPlayer.query.filter(TrackedPlayer.is_active.is_(True)).all()
    for tp in active_rows:
        if tp.pinned_parent or tp.data_source == "manual":
            continue
        reason = None
        if tp.data_source == "owning-club":
            reason = "owning-club rows are deprecated"
        elif tp.journey_id in recomputed:
            parent_api_id = tp.team.team_id if tp.team else None
            if parent_api_id is not None and parent_api_id not in recomputed[tp.journey_id]:
                reason = "parent club not in recomputed academy_club_ids"
        if reason:
            tp.is_active = False
            if tp.id not in deactivated_ids:
                _record_deactivation(tp, reason)

    response = {
        "journeys_processed": journeys_processed,
        "journeys_changed": journeys_changed,
        "rows_deactivated": len(deactivated_ids),
        "examples": examples,
        "dry_run": dry_run,
    }

    if dry_run:
        db.session.rollback()
    else:
        db.session.commit()

    return jsonify(response)


@journey_bp.route("/admin/players/backfill-names", methods=["POST"])
@require_api_key
def admin_backfill_player_names():
    """Backfill placeholder names ('Player NNNN') from local sources.

    Body: {"dry_run": bool (default true)}

    Fixes TrackedPlayer (active or not), the players table, and
    player_journeys. Names are resolved via CohortMember ->
    AcademyPlayerSeasonStats -> Player -> PlayerJourney; placeholder names
    never overwrite real ones.
    """
    from src.models.league import Player

    data = request.get_json(silent=True) or {}
    dry_run = bool(data.get("dry_run", True))

    examples = []
    unresolved = 0

    def _record(player_api_id, old, new):
        if len(examples) < 20:
            examples.append({"player_api_id": player_api_id, "old": old, "new": new})

    # TrackedPlayer rows (active or not)
    tracked_updated = 0
    for tp in TrackedPlayer.query.filter(TrackedPlayer.player_name.like("Player %")).all():
        if not is_placeholder_name(tp.player_name):
            continue
        profile = resolve_player_profile(tp.player_api_id)
        if not profile["name"]:
            unresolved += 1
            continue
        _record(tp.player_api_id, tp.player_name, profile["name"])
        tp.player_name = profile["name"]
        if tp.photo_url is None and profile["photo"]:
            tp.photo_url = profile["photo"]
        if tp.nationality is None and profile["nationality"]:
            tp.nationality = profile["nationality"]
        tracked_updated += 1

    # players table
    players_updated = 0
    for player in Player.query.filter(Player.name.like("Player %")).all():
        if not is_placeholder_name(player.name):
            continue
        profile = resolve_player_profile(player.player_id)
        if not profile["name"]:
            unresolved += 1
            continue
        _record(player.player_id, player.name, profile["name"])
        player.name = profile["name"]
        players_updated += 1

    # player_journeys
    journeys_updated = 0
    for journey in PlayerJourney.query.filter(PlayerJourney.player_name.like("Player %")).all():
        if not is_placeholder_name(journey.player_name):
            continue
        profile = resolve_player_profile(journey.player_api_id)
        if not profile["name"]:
            unresolved += 1
            continue
        _record(journey.player_api_id, journey.player_name, profile["name"])
        journey.player_name = profile["name"]
        journeys_updated += 1

    response = {
        "tracked_updated": tracked_updated,
        "players_updated": players_updated,
        "journeys_updated": journeys_updated,
        "unresolved": unresolved,
        "examples": examples,
        "dry_run": dry_run,
    }

    if dry_run:
        db.session.rollback()
    else:
        db.session.commit()

    return jsonify(response)


# =============================================================================
# Helper: PlayerJourney-based (primary system)
# =============================================================================


def _build_journey_from_player_journey(journey: PlayerJourney) -> dict:
    """Build stint-format journey data from a PlayerJourney record.

    Converts the to_map_dict() stops into the stint format that the frontend
    expects, enriched with ClubLocation coordinates.
    """
    map_data = journey.to_map_dict()
    stops = map_data.get("stops", [])

    if not stops:
        return {
            "stints": [],
            "total_stints": 0,
            "countries": [],
            "is_multi_country": False,
            "moved_on": False,
        }

    # Fetch ClubLocation coordinates for all clubs in one query
    club_ids = [stop["club_id"] for stop in stops]
    locations = ClubLocation.query.filter(ClubLocation.club_api_id.in_(club_ids)).all()
    location_map = {loc.club_api_id: loc for loc in locations}

    stints = []
    country_counts = defaultdict(int)
    total = len(stops)

    for seq, stop in enumerate(stops, start=1):
        loc = location_map.get(stop["club_id"])

        # Determine stint_type from levels
        levels = stop.get("levels", [])
        if any(l in YOUTH_LEVELS for l in levels):
            stint_type = "academy"
        else:
            stint_type = "first_team"

        city = loc.city if loc else None
        country = loc.country if loc else None
        latitude = loc.latitude if loc else None
        longitude = loc.longitude if loc else None

        stint = {
            "id": f"j-{stop['club_id']}-{seq}",
            "team_api_id": stop["club_id"],
            "team_name": stop["club_name"],
            "team_logo": stop["club_logo"],
            "city": city,
            "country": country,
            "latitude": latitude,
            "longitude": longitude,
            "stint_type": stint_type,
            "level": levels[0] if levels else "First Team",
            "levels": levels,
            "years": stop.get("years"),
            "is_current": seq == total,
            "sequence": seq,
            "stats": {
                "apps": stop.get("total_apps", 0),
                "goals": stop.get("total_goals", 0),
                "assists": stop.get("total_assists", 0),
            },
            "breakdown": stop.get("breakdown"),
            "competitions": stop.get("competitions"),
        }
        stints.append(stint)

        if country:
            country_counts[country] += 1

    countries = [{"name": name, "stint_count": count} for name, count in sorted(country_counts.items())]

    return {
        "stints": stints,
        "total_stints": len(stints),
        "countries": countries,
        "is_multi_country": len(country_counts) > 1,
        "moved_on": False,
    }


# =============================================================================
# Helpers
# =============================================================================


def _get_team_venue_info(team_api_id: int) -> dict:
    """Get venue info for a team from TeamProfile or Team."""
    profile = TeamProfile.query.filter_by(team_id=team_api_id).first()
    if profile:
        return {
            "city": profile.venue_city,
            "country": profile.country,
            "logo": profile.logo_url,
        }

    team = Team.query.filter_by(team_id=team_api_id).first()
    if team:
        return {
            "city": team.venue_city,
            "country": team.country,
            "logo": team.logo,
        }

    return {}


def _build_legacy_journey(player_id: int, primary_team_id: int = None) -> dict:
    """Build a minimal journey from TrackedPlayer records.

    Used when a player has no PlayerJourney record yet.
    """
    tracked = TrackedPlayer.query.filter_by(player_api_id=player_id).all()

    if not tracked:
        return {
            "stints": [],
            "total_stints": 0,
            "countries": [],
            "is_multi_country": False,
            "moved_on": False,
        }

    tp = tracked[0]
    parent_team_api_id = tp.team.team_id if tp.team else None

    parent_venue = _get_team_venue_info(parent_team_api_id) if parent_team_api_id else {}
    parent_coords = get_team_coordinates(parent_venue.get("city"), parent_venue.get("country"))

    stints = []
    sequence = 1
    country_counts = defaultdict(int)

    # Academy stint
    stint = {
        "id": f"{player_id}-{sequence}",
        "team_api_id": parent_team_api_id or 0,
        "team_name": tp.team.name if tp.team else "Unknown",
        "team_logo": parent_venue.get("logo"),
        "city": parent_venue.get("city"),
        "country": parent_venue.get("country"),
        "latitude": parent_coords[0] if parent_coords else None,
        "longitude": parent_coords[1] if parent_coords else None,
        "stint_type": "academy",
        "level": "Academy",
        "is_current": tp.status == "academy",
        "sequence": sequence,
    }
    stints.append(stint)
    if stint["country"]:
        country_counts[stint["country"]] += 1
    sequence += 1

    # Current club stint (if on loan or first team)
    if tp.status == "on_loan" and tp.current_club_api_id:
        loan_venue = _get_team_venue_info(tp.current_club_api_id)
        loan_coords = get_team_coordinates(loan_venue.get("city"), loan_venue.get("country"))
        stint = {
            "id": f"{player_id}-{sequence}",
            "team_api_id": tp.current_club_api_id,
            "team_name": tp.current_club_name or "Unknown",
            "team_logo": loan_venue.get("logo"),
            "city": loan_venue.get("city"),
            "country": loan_venue.get("country"),
            "latitude": loan_coords[0] if loan_coords else None,
            "longitude": loan_coords[1] if loan_coords else None,
            "stint_type": "loan",
            "level": "Senior",
            "is_current": True,
            "sequence": sequence,
        }
        stints.append(stint)
        if stint["country"]:
            country_counts[stint["country"]] += 1

    moved_on = tp.status in ("released", "sold")

    countries = [{"name": name, "stint_count": count} for name, count in sorted(country_counts.items())]

    return {
        "stints": stints,
        "total_stints": len(stints),
        "countries": countries,
        "is_multi_country": len(country_counts) > 1,
        "moved_on": moved_on,
    }
