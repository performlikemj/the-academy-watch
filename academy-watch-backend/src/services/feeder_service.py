"""
Feeder Service

Provides the "squad origins" view — given a team in a competition (e.g. Champions League),
shows which academies produced the players in that squad.
"""

import logging
from collections import defaultdict
from typing import Optional, Dict, Any, List

from src.models.league import db, Team, TeamProfile
from src.models.journey import PlayerJourney
from src.api_football_client import APIFootballClient
from src.services.journey_sync import JourneySyncService
from src.utils.academy_classifier import strip_youth_suffix, is_national_team

logger = logging.getLogger(__name__)

# Competitions available for browsing
SUPPORTED_COMPETITIONS = [
    {
        'league_api_id': 2,
        'name': 'Champions League',
        'logo': 'https://media.api-sports.io/football/leagues/2.png',
        'type': 'cup',
    },
]


class FeederService:
    """Service for discovering which academies feed a club's squad."""

    def __init__(self, api_client: Optional[APIFootballClient] = None):
        self.api = api_client or APIFootballClient()
        self.journey_sync = JourneySyncService(api_client=self.api)

    def get_competitions(self) -> List[Dict[str, Any]]:
        return SUPPORTED_COMPETITIONS

    def get_competition_teams(self, league_api_id: int, season: int) -> List[Dict[str, Any]]:
        """Fetch teams from competition standings (excludes qualifier-only teams)."""
        response = self.api._make_request('standings', {
            'league': league_api_id,
            'season': season,
        })

        teams = []
        seen = set()
        for league_data in response.get('response', []):
            for standings_group in league_data.get('league', {}).get('standings', []):
                for entry in standings_group:
                    team = entry.get('team', {})
                    tid = team.get('id')
                    if tid and tid not in seen:
                        seen.add(tid)
                        teams.append({
                            'team_api_id': tid,
                            'name': team.get('name'),
                            'logo': team.get('logo'),
                            'country': None,
                        })

        # Backfill country from TeamProfile
        if teams:
            profiles = {tp.team_id: tp for tp in TeamProfile.query.filter(
                TeamProfile.team_id.in_([t['team_api_id'] for t in teams])
            ).all()}
            for t in teams:
                profile = profiles.get(t['team_api_id'])
                if profile:
                    t['country'] = profile.country

        teams.sort(key=lambda t: (t.get('name') or ''))
        return teams

    def get_squad_origins(
        self,
        team_api_id: int,
        league_api_id: Optional[int] = None,
        season: Optional[int] = None,
        auto_sync: bool = True,
    ) -> Dict[str, Any]:
        """
        Get the academy breakdown for a team's current squad.

        Returns players grouped by their academy origin club.
        If auto_sync is True, syncs journeys for players without journey data.
        league_api_id is optional — when omitted, fetches the full squad
        regardless of competition.
        """
        if season is None:
            season = self.api.current_season_start_year

        # Fetch squad from API-Football (paginated)
        squad_players = self._fetch_squad(team_api_id, season, league_api_id=league_api_id)

        if not squad_players:
            return {
                'team': {'api_id': team_api_id},
                'squad_size': 0,
                'academy_breakdown': [],
                'unknown_origin': [],
                'homegrown_count': 0,
                'homegrown_pct': 0,
            }

        player_api_ids = [p['player_api_id'] for p in squad_players]

        # Look up existing journeys
        journeys_by_player = {}
        existing_journeys = PlayerJourney.query.filter(
            PlayerJourney.player_api_id.in_(player_api_ids)
        ).all()
        for j in existing_journeys:
            journeys_by_player[j.player_api_id] = j

        # Auto-sync missing journeys (capped to prevent timeouts)
        MAX_AUTO_SYNC = 10
        missing_ids = [pid for pid in player_api_ids if pid not in journeys_by_player]
        if auto_sync and missing_ids:
            sync_batch = missing_ids[:MAX_AUTO_SYNC]
            logger.info(
                f"Auto-syncing {len(sync_batch)}/{len(missing_ids)} missing journeys "
                f"for team {team_api_id}"
            )
            for pid in sync_batch:
                try:
                    journey = self.journey_sync.sync_player(pid)
                    if journey:
                        journeys_by_player[pid] = journey
                except Exception as e:
                    logger.warning(f"Failed to sync journey for player {pid}: {e}")

        # Filter to current squad: exclude players who left mid-season
        # (sold, loaned out, etc.) by checking journey's current_club
        active_squad = []
        for player in squad_players:
            journey = journeys_by_player.get(player['player_api_id'])
            if not journey or not journey.current_club_api_id:
                active_squad.append(player)  # No journey data — keep
                continue
            if journey.current_club_api_id == team_api_id:
                active_squad.append(player)  # Still at the club
                continue
            # Check youth team variant (e.g. currently at "Man United U21")
            resolved = self._resolve_parent_id(
                strip_youth_suffix(journey.current_club_name or '')
            )
            if resolved == team_api_id:
                active_squad.append(player)
                continue
            # Player is at a different club — exclude
        squad_players = active_squad

        # Group players by academy origin
        academy_groups = defaultdict(list)
        unknown_origin = []

        for player in squad_players:
            pid = player['player_api_id']
            journey = journeys_by_player.get(pid)

            if journey and journey.origin_club_api_id:
                origin_key = journey.origin_club_api_id
                academy_groups[origin_key].append({
                    **player,
                    'academy_club_id': journey.origin_club_api_id,
                    'academy_club_name': journey.origin_club_name,
                    'academy_club_ids': journey.academy_club_ids or [],
                })
            else:
                unknown_origin.append(player)

        # Filter out national team origins (e.g. "Norway U17")
        national_keys = [k for k, players in academy_groups.items()
                         if is_national_team(players[0]['academy_club_name'])]
        for k in national_keys:
            unknown_origin.extend(academy_groups.pop(k))

        # Merge youth/reserve team groups into their parent club group
        # e.g. "Brann II" and "Brann U19" merge into "Brann"
        for academy_id in list(academy_groups.keys()):
            if academy_id not in academy_groups:
                continue  # already merged
            players = academy_groups[academy_id]
            name = players[0]['academy_club_name']
            base = strip_youth_suffix(name)
            if base == name:
                continue  # not a youth team name

            # Resolve parent club API ID
            canonical_id = self._resolve_parent_id(base)
            if not canonical_id:
                # Can't resolve — just update the display name
                for p in players:
                    p['academy_club_name'] = base
                continue

            if canonical_id == academy_id:
                continue  # already correct

            # Merge into existing parent group or re-key
            for p in players:
                p['academy_club_name'] = base
                p['academy_club_id'] = canonical_id
            if canonical_id in academy_groups:
                academy_groups[canonical_id].extend(players)
            else:
                academy_groups[canonical_id] = players
            del academy_groups[academy_id]

        # Second merge pass: resolve every group to a canonical API ID and
        # merge duplicates. Handles name variants (e.g. "Manchester Utd" vs
        # "Manchester United") that the suffix-strip pass can't catch, plus
        # youth teams whose names were pre-stripped during journey sync.
        canonical_map: Dict[int, int] = {}  # academy_id -> canonical_id
        for academy_id in list(academy_groups.keys()):
            if academy_id not in academy_groups:
                continue
            display_name = strip_youth_suffix(
                academy_groups[academy_id][0]['academy_club_name']
            )
            # Resolve canonical ID: prefer viewed team, then DB lookup
            if academy_id == team_api_id:
                canonical = academy_id
            else:
                resolved = self._resolve_parent_id(display_name)
                canonical = resolved if resolved else academy_id
            canonical_map[academy_id] = canonical

        # Merge groups that resolved to the same canonical ID
        merged: Dict[int, list] = {}
        canonical_names: Dict[int, str] = {}
        for academy_id in list(academy_groups.keys()):
            canonical = canonical_map.get(academy_id, academy_id)
            display_name = strip_youth_suffix(
                academy_groups[academy_id][0]['academy_club_name']
            )
            for p in academy_groups[academy_id]:
                p['academy_club_id'] = canonical
                p['academy_club_name'] = display_name
            if canonical in merged:
                merged[canonical].extend(academy_groups[academy_id])
            else:
                merged[canonical] = list(academy_groups[academy_id])
                canonical_names[canonical] = display_name
        academy_groups = merged

        # Normalize display names: prefer the name from TeamProfile/Team
        for canonical_id in academy_groups:
            profile = TeamProfile.query.filter_by(team_id=canonical_id).first()
            if profile:
                for p in academy_groups[canonical_id]:
                    p['academy_club_name'] = profile.name
            elif canonical_id == team_api_id:
                # Use the viewed team's known name
                team_row = Team.query.filter_by(team_id=team_api_id).first()
                if team_row:
                    for p in academy_groups[canonical_id]:
                        p['academy_club_name'] = team_row.name

        # Build breakdown with academy logos
        breakdown = []
        for academy_id, players in academy_groups.items():
            academy_name = players[0]['academy_club_name']
            academy_logo = self._get_team_logo(academy_id)

            breakdown.append({
                'academy': {
                    'api_id': academy_id,
                    'name': academy_name,
                    'logo': academy_logo,
                },
                'players': sorted(players, key=lambda p: p.get('player_name', '')),
                'count': len(players),
                'is_homegrown': academy_id == team_api_id,
            })

        breakdown.sort(key=lambda g: (-g['count'], g['academy']['name']))

        homegrown_count = sum(g['count'] for g in breakdown if g['is_homegrown'])
        total = len(squad_players)

        # Get team info from first player's data
        team_info = {
            'api_id': team_api_id,
            'name': squad_players[0].get('team_name') if squad_players else None,
            'logo': squad_players[0].get('team_logo') if squad_players else None,
        }

        return {
            'team': team_info,
            'squad_size': total,
            'academy_breakdown': breakdown,
            'unknown_origin': unknown_origin,
            'homegrown_count': homegrown_count,
            'homegrown_pct': round(homegrown_count / total * 100) if total > 0 else 0,
            'resolved_count': total - len(unknown_origin),
        }

    def _fetch_squad(self, team_api_id: int, season: int,
                     league_api_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Fetch all squad players for a team from API-Football.

        When league_api_id is provided, filters to that competition.
        When omitted, returns the full registered squad for the season.
        """
        players = []
        page = 1
        total_pages = 1

        while page <= total_pages:
            params = {
                'team': team_api_id,
                'season': season,
                'page': page,
            }
            if league_api_id:
                params['league'] = league_api_id

            response = self.api._make_request('players', params)

            paging = response.get('paging', {})
            total_pages = paging.get('total', 1)

            for player_data in response.get('response', []):
                player = player_data.get('player', {})
                stats_list = player_data.get('statistics', [])

                player_api_id = player.get('id')
                if not player_api_id:
                    continue

                # Aggregate stats across all competitions
                appearances = 0
                goals = 0
                assists = 0
                position = None
                team_name = None
                team_logo = None
                for stat in (stats_list or []):
                    games = stat.get('games', {})
                    goals_data = stat.get('goals', {})
                    appearances += (games.get('appearences') or games.get('appearances') or 0)
                    goals += (goals_data.get('total') or 0)
                    assists += (goals_data.get('assists') or 0)
                    if not position:
                        position = games.get('position')
                    if not team_name:
                        team_info = stat.get('team', {})
                        team_name = team_info.get('name')
                        team_logo = team_info.get('logo')

                players.append({
                    'player_api_id': player_api_id,
                    'player_name': player.get('name'),
                    'photo': player.get('photo'),
                    'age': player.get('age'),
                    'nationality': player.get('nationality'),
                    'position': position,
                    'appearances': appearances,
                    'goals': goals,
                    'assists': assists,
                    'team_name': team_name,
                    'team_logo': team_logo,
                })

            page += 1

        return players

    def _resolve_parent_id(self, base_name: str) -> Optional[int]:
        """Resolve a club name to the canonical parent club API ID.

        Uses exact match first, then substring matching to handle
        abbreviations like 'Manchester Utd' vs 'Manchester United'.
        """
        # Exact match: TeamProfile
        profile = TeamProfile.query.filter(TeamProfile.name == base_name).first()
        if profile:
            return profile.team_id
        # Exact match: Team
        team = Team.query.filter(Team.name == base_name).first()
        if team:
            return team.team_id
        # Substring match: base_name contains profile name or vice versa
        profile = TeamProfile.query.filter(
            db.or_(
                db.func.strpos(base_name, TeamProfile.name) > 0,
                db.func.strpos(TeamProfile.name, base_name) > 0,
            ),
            db.func.length(TeamProfile.name) >= 5,
        ).order_by(db.func.length(TeamProfile.name).desc()).first()
        if profile:
            return profile.team_id
        return None

    def _get_team_logo(self, team_api_id: int) -> Optional[str]:
        """Get team logo from TeamProfile cache."""
        profile = TeamProfile.query.filter_by(team_id=team_api_id).first()
        if profile:
            return profile.logo_url
        return f"https://media.api-sports.io/football/teams/{team_api_id}.png"
