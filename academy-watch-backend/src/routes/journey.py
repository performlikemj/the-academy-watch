"""Player Journey API endpoints.

Handles player career journey retrieval for map visualization.

Primary data source: PlayerJourney + PlayerJourneyEntry (from API-Football sync).
Legacy fallback: AcademyPlayer records (for players not yet synced).
"""
from flask import Blueprint, request, jsonify
from src.models.league import db, AcademyPlayer, Team, TeamProfile
from src.models.journey import PlayerJourney, ClubLocation, YOUTH_LEVELS
from src.utils.geocoding import get_team_coordinates
from collections import defaultdict
import logging
import re

journey_bp = Blueprint('journey', __name__)
logger = logging.getLogger(__name__)


# =============================================================================
# Public Endpoints
# =============================================================================

@journey_bp.route('/players/<int:player_id>/journey', methods=['GET'])
def get_player_journey(player_id):
    """Get a player's career journey for map visualization.

    Tries PlayerJourney model first (full career data from API-Football),
    falls back to AcademyPlayer-based builder for unsynced players.

    Query params:
    - sync: bool - Trigger sync if journey doesn't exist (default: false)
    """
    should_sync = request.args.get('sync', 'false').lower() == 'true'

    # Try PlayerJourney first (the new, richer data source)
    journey = PlayerJourney.query.filter_by(player_api_id=player_id).first()

    # Re-sync if journey is missing, has a sync error, or has no entries
    needs_sync = (
        not journey
        or journey.sync_error is not None
        or not journey.entries.first()
    )
    if needs_sync and should_sync:
        try:
            from src.services.journey_sync import JourneySyncService
            service = JourneySyncService()
            journey = service.sync_player(player_id, force_full=bool(journey))
        except Exception as e:
            logger.warning(f"Journey sync failed for player {player_id}: {e}")

    if journey:
        journey_data = _build_journey_from_player_journey(journey)
        return jsonify({
            'player_id': player_id,
            'source': 'player_journey',
            **journey_data,
        })

    # Fallback: build from AcademyPlayer records
    sample_loan = AcademyPlayer.query.filter_by(player_id=player_id).first()
    primary_team_id = sample_loan.primary_team_id if sample_loan else None

    journey_data = _build_legacy_journey(player_id, primary_team_id)

    return jsonify({
        'player_id': player_id,
        'source': 'loaned_player',
        **journey_data,
    })


@journey_bp.route('/loans/<int:loaned_player_id>/journey', methods=['GET'])
def get_loan_journey(loaned_player_id):
    """Get journey for a specific AcademyPlayer record.

    Returns the complete journey for the player, including all loan stints
    across their career (not just the current loan).
    """
    loan = AcademyPlayer.query.get_or_404(loaned_player_id)

    # Try PlayerJourney first
    journey = PlayerJourney.query.filter_by(player_api_id=loan.player_id).first()
    if journey:
        journey_data = _build_journey_from_player_journey(journey)
    else:
        journey_data = _build_legacy_journey(loan.player_id, loan.primary_team_id)

    return jsonify({
        'loaned_player_id': loaned_player_id,
        'player_id': loan.player_id,
        'player_name': loan.player_name,
        **journey_data,
    })


# =============================================================================
# Helper: PlayerJourney-based (primary system)
# =============================================================================

def _build_journey_from_player_journey(journey: PlayerJourney) -> dict:
    """Build stint-format journey data from a PlayerJourney record.

    Converts the to_map_dict() stops into the stint format that the frontend
    expects, enriched with ClubLocation coordinates.
    """
    map_data = journey.to_map_dict()
    stops = map_data.get('stops', [])

    if not stops:
        return {
            'stints': [],
            'total_stints': 0,
            'countries': [],
            'is_multi_country': False,
            'moved_on': False,
        }

    # Fetch ClubLocation coordinates for all clubs in one query
    club_ids = [stop['club_id'] for stop in stops]
    locations = ClubLocation.query.filter(ClubLocation.club_api_id.in_(club_ids)).all()
    location_map = {loc.club_api_id: loc for loc in locations}

    stints = []
    country_counts = defaultdict(int)
    total = len(stops)

    for seq, stop in enumerate(stops, start=1):
        loc = location_map.get(stop['club_id'])

        # Determine stint_type from levels
        levels = stop.get('levels', [])
        if any(l in YOUTH_LEVELS for l in levels):
            stint_type = 'academy'
        else:
            stint_type = 'first_team'

        city = loc.city if loc else None
        country = loc.country if loc else None
        latitude = loc.latitude if loc else None
        longitude = loc.longitude if loc else None

        stint = {
            'id': f"j-{stop['club_id']}-{seq}",
            'team_api_id': stop['club_id'],
            'team_name': stop['club_name'],
            'team_logo': stop['club_logo'],
            'city': city,
            'country': country,
            'latitude': latitude,
            'longitude': longitude,
            'stint_type': stint_type,
            'level': levels[0] if levels else 'First Team',
            'levels': levels,
            'years': stop.get('years'),
            'is_current': seq == total,
            'sequence': seq,
            'stats': {
                'apps': stop.get('total_apps', 0),
                'goals': stop.get('total_goals', 0),
                'assists': stop.get('total_assists', 0),
            },
            'breakdown': stop.get('breakdown'),
            'competitions': stop.get('competitions'),
        }
        stints.append(stint)

        if country:
            country_counts[country] += 1

    countries = [
        {'name': name, 'stint_count': count}
        for name, count in sorted(country_counts.items())
    ]

    return {
        'stints': stints,
        'total_stints': len(stints),
        'countries': countries,
        'is_multi_country': len(country_counts) > 1,
        'moved_on': False,
    }


# =============================================================================
# Helper: AcademyPlayer-based (legacy fallback)
# =============================================================================

def _get_team_venue_info(team_api_id: int) -> dict:
    """Get venue info for a team from TeamProfile or Team."""
    profile = TeamProfile.query.filter_by(team_id=team_api_id).first()
    if profile:
        return {
            'city': profile.venue_city,
            'country': profile.country,
            'logo': profile.logo_url,
        }

    team = Team.query.filter_by(team_id=team_api_id).first()
    if team:
        return {
            'city': team.venue_city,
            'country': team.country,
            'logo': team.logo,
        }

    return {}


def _parse_window_key(window_key: str) -> tuple:
    """Parse window_key for chronological sorting."""
    if not window_key:
        return (0, 0)

    match = re.match(r'(\d{4})-\d{2}::(\w+)', window_key)
    if not match:
        return (0, 0)

    season_start = int(match.group(1))
    window_type = match.group(2).upper()
    window_order = {'SUMMER': 0, 'FULL': 1, 'WINTER': 2}.get(window_type, 1)

    return (season_start, window_order)


def _extract_season_from_window(window_key: str) -> str:
    """Extract season string from window_key."""
    if not window_key:
        return ''
    match = re.match(r'(\d{4}-\d{2})', window_key)
    return match.group(1) if match else ''


def _dedupe_loan_stints(loans: list) -> list:
    """Deduplicate loan records to one stint per (loan_team_id, season)."""
    seen = {}

    for loan in loans:
        season = _extract_season_from_window(loan.window_key)
        key = (loan.loan_team_id, season)

        if key not in seen:
            seen[key] = loan
        else:
            existing = seen[key]
            existing_order = _parse_window_key(existing.window_key)
            new_order = _parse_window_key(loan.window_key)

            if loan.is_active and not existing.is_active:
                seen[key] = loan
            elif new_order > existing_order:
                seen[key] = loan

    return list(seen.values())


def _build_legacy_journey(player_id: int, primary_team_id: int = None) -> dict:
    """Build journey from AcademyPlayer records (legacy fallback).

    Used when a player has no PlayerJourney record yet.
    """
    loans = AcademyPlayer.query.filter_by(player_id=player_id)\
        .order_by(AcademyPlayer.window_key).all()

    if not loans:
        return {
            'stints': [],
            'total_stints': 0,
            'countries': [],
            'is_multi_country': False,
            'moved_on': False,
        }

    first_loan = loans[0]
    parent_team_api_id = None
    if primary_team_id:
        parent_team = Team.query.get(primary_team_id)
        if parent_team:
            parent_team_api_id = parent_team.team_id
    elif first_loan.parent_team:
        parent_team_api_id = first_loan.parent_team.team_id

    parent_venue = _get_team_venue_info(parent_team_api_id) if parent_team_api_id else {}
    parent_coords = get_team_coordinates(parent_venue.get('city'), parent_venue.get('country'))

    stints = []
    sequence = 1
    country_counts = defaultdict(int)

    has_academy = any(l.pathway_status == 'academy' or l.current_level in ('U18', 'U21', 'U23') for l in loans)
    has_first_team = any(l.pathway_status == 'first_team' for l in loans)
    most_recent = max(loans, key=lambda l: _parse_window_key(l.window_key))

    if has_academy:
        stint = {
            'id': f'{player_id}-{sequence}',
            'team_api_id': parent_team_api_id or 0,
            'team_name': first_loan.primary_team_name,
            'team_logo': parent_venue.get('logo'),
            'city': parent_venue.get('city'),
            'country': parent_venue.get('country'),
            'latitude': parent_coords[0] if parent_coords else None,
            'longitude': parent_coords[1] if parent_coords else None,
            'stint_type': 'academy',
            'level': 'Academy',
            'is_current': False,
            'sequence': sequence,
        }
        stints.append(stint)
        if stint['country']:
            country_counts[stint['country']] += 1
        sequence += 1

    sorted_loans = sorted(loans, key=lambda l: _parse_window_key(l.window_key))
    deduped_loans = _dedupe_loan_stints(sorted_loans)
    deduped_loans = sorted(deduped_loans, key=lambda l: _parse_window_key(l.window_key))

    for loan in deduped_loans:
        if not loan.loan_team_id and not loan.loan_team_name:
            continue

        loan_team_api_id = None
        if loan.borrowing_team:
            loan_team_api_id = loan.borrowing_team.team_id

        loan_venue = _get_team_venue_info(loan_team_api_id) if loan_team_api_id else {}
        loan_coords = get_team_coordinates(loan_venue.get('city'), loan_venue.get('country'))
        is_current = loan.is_active and loan.id == most_recent.id

        stint = {
            'id': f'{player_id}-{sequence}',
            'team_api_id': loan_team_api_id or 0,
            'team_name': loan.loan_team_name,
            'team_logo': loan_venue.get('logo'),
            'city': loan_venue.get('city'),
            'country': loan_venue.get('country'),
            'latitude': loan_coords[0] if loan_coords else None,
            'longitude': loan_coords[1] if loan_coords else None,
            'stint_type': 'loan',
            'level': 'Senior',
            'is_current': is_current,
            'sequence': sequence,
            'window_key': loan.window_key,
        }
        stints.append(stint)
        if stint['country']:
            country_counts[stint['country']] += 1
        sequence += 1

    if has_first_team:
        stint = {
            'id': f'{player_id}-{sequence}',
            'team_api_id': parent_team_api_id or 0,
            'team_name': first_loan.primary_team_name,
            'team_logo': parent_venue.get('logo'),
            'city': parent_venue.get('city'),
            'country': parent_venue.get('country'),
            'latitude': parent_coords[0] if parent_coords else None,
            'longitude': parent_coords[1] if parent_coords else None,
            'stint_type': 'first_team',
            'level': 'Senior',
            'is_current': most_recent.pathway_status == 'first_team',
            'sequence': sequence,
        }
        stints.append(stint)
        if stint['country']:
            country_counts[stint['country']] += 1

    moved_on = (
        most_recent.pathway_status == 'released' or
        (not most_recent.is_active and not has_first_team and most_recent.pathway_status != 'academy')
    )

    countries = [
        {'name': name, 'stint_count': count}
        for name, count in sorted(country_counts.items())
    ]

    return {
        'stints': stints,
        'total_stints': len(stints),
        'countries': countries,
        'is_multi_country': len(country_counts) > 1,
        'moved_on': moved_on,
    }
