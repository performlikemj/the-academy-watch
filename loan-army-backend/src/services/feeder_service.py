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
        league_api_id: int,
        season: int,
        auto_sync: bool = True,
    ) -> Dict[str, Any]:
        """
        Get the academy breakdown for a team's squad in a competition/season.

        Returns players grouped by their academy origin club.
        If auto_sync is True, syncs journeys for players without journey data.
        """
        # Fetch squad from API-Football (paginated)
        squad_players = self._fetch_squad(team_api_id, league_api_id, season)

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

        # Auto-sync missing journeys
        missing_ids = [pid for pid in player_api_ids if pid not in journeys_by_player]
        if auto_sync and missing_ids:
            logger.info(f"Auto-syncing {len(missing_ids)} missing journeys for team {team_api_id}")
            for pid in missing_ids:
                try:
                    journey = self.journey_sync.sync_player(pid)
                    if journey:
                        journeys_by_player[pid] = journey
                except Exception as e:
                    logger.warning(f"Failed to sync journey for player {pid}: {e}")

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
                'is_homegrown': academy_id == team_api_id or any(
                    team_api_id in (p.get('academy_club_ids') or []) for p in players
                ),
            })

        breakdown.sort(key=lambda g: (-g['count'], g['academy']['name']))

        homegrown = next((g for g in breakdown if g['is_homegrown']), None)
        homegrown_count = homegrown['count'] if homegrown else 0
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

    def _fetch_squad(self, team_api_id: int, league_api_id: int, season: int) -> List[Dict[str, Any]]:
        """Fetch all squad players for a team in a league/season from API-Football."""
        players = []
        page = 1
        total_pages = 1

        while page <= total_pages:
            response = self.api._make_request('players', {
                'team': team_api_id,
                'league': league_api_id,
                'season': season,
                'page': page,
            })

            paging = response.get('paging', {})
            total_pages = paging.get('total', 1)

            for player_data in response.get('response', []):
                player = player_data.get('player', {})
                stats_list = player_data.get('statistics', [])

                player_api_id = player.get('id')
                if not player_api_id:
                    continue

                # Extract stats from first statistics entry
                appearances = 0
                goals = 0
                assists = 0
                position = None
                team_name = None
                team_logo = None
                if stats_list:
                    stat = stats_list[0]
                    games = stat.get('games', {})
                    goals_data = stat.get('goals', {})
                    appearances = games.get('appearences') or games.get('appearances') or 0
                    goals = goals_data.get('total') or 0
                    assists = goals_data.get('assists') or 0
                    position = games.get('position')
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
        """Resolve a youth team base name to the parent club's API ID."""
        profile = TeamProfile.query.filter(TeamProfile.name == base_name).first()
        if profile:
            return profile.team_id
        team = Team.query.filter(Team.name == base_name).first()
        if team:
            return team.team_id
        return None

    def _get_team_logo(self, team_api_id: int) -> Optional[str]:
        """Get team logo from TeamProfile cache."""
        profile = TeamProfile.query.filter_by(team_id=team_api_id).first()
        if profile:
            return profile.logo_url
        return f"https://media.api-sports.io/football/teams/{team_api_id}.png"
