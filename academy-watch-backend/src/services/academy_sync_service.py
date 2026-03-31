"""Academy Fixture Sync Service.

Fetches fixtures from configured academy leagues and extracts
player appearances, goals, assists from lineups and events data.
"""
import logging
from datetime import datetime, date, timedelta, timezone
from typing import List, Dict, Any, Optional, Set
from src.models.league import db, AcademyLeague, AcademyAppearance
from src.models.tracked_player import TrackedPlayer
from src.api_football_client import APIFootballClient

logger = logging.getLogger(__name__)


class AcademySyncService:
    """Service for syncing academy/youth league fixtures and player appearances."""

    def __init__(self, api_client: Optional[APIFootballClient] = None):
        self.api_client = api_client or APIFootballClient()

    def sync_league(
        self,
        league: AcademyLeague,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        season: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Sync fixtures for a single academy league.

        Args:
            league: AcademyLeague to sync
            date_from: Start date (default: 7 days ago)
            date_to: End date (default: today)
            season: Season year (default: league.season or current year)

        Returns:
            Dict with sync results: fixtures_processed, appearances_created, errors
        """
        if not league.sync_enabled:
            logger.info(f"Sync disabled for league {league.name}")
            return {'status': 'skipped', 'reason': 'sync_disabled'}

        # Default date range: last 7 days
        if date_from is None:
            date_from = date.today() - timedelta(days=7)
        if date_to is None:
            date_to = date.today()

        season = season or league.season or date.today().year

        logger.info(f"Syncing {league.name} ({league.api_league_id}) from {date_from} to {date_to}")

        results = {
            'league_id': league.id,
            'league_name': league.name,
            'fixtures_processed': 0,
            'appearances_created': 0,
            'appearances_updated': 0,
            'errors': [],
        }

        try:
            # Fetch fixtures for the league
            fixtures = self._fetch_fixtures(
                league_id=league.api_league_id,
                season=season,
                date_from=date_from,
                date_to=date_to,
            )

            if not fixtures:
                logger.info(f"No fixtures found for {league.name}")
                return results

            # Get tracked player IDs for matching
            tracked_player_ids = self._get_tracked_player_ids()

            for fixture in fixtures:
                try:
                    fixture_results = self._process_fixture(
                        fixture=fixture,
                        league=league,
                        tracked_player_ids=tracked_player_ids,
                    )
                    results['fixtures_processed'] += 1
                    results['appearances_created'] += fixture_results.get('created', 0)
                    results['appearances_updated'] += fixture_results.get('updated', 0)
                except Exception as e:
                    error_msg = f"Error processing fixture {fixture.get('fixture', {}).get('id')}: {str(e)}"
                    logger.error(error_msg)
                    results['errors'].append(error_msg)

            # Update last synced timestamp
            league.last_synced_at = datetime.now(timezone.utc)
            db.session.commit()

        except Exception as e:
            error_msg = f"Error syncing league {league.name}: {str(e)}"
            logger.exception(error_msg)
            results['errors'].append(error_msg)

        return results

    def sync_all_active_leagues(
        self,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        """Sync all active academy leagues."""
        leagues = AcademyLeague.query.filter_by(is_active=True, sync_enabled=True).all()
        results = []

        for league in leagues:
            result = self.sync_league(league, date_from=date_from, date_to=date_to)
            results.append(result)

        return results

    def _fetch_fixtures(
        self,
        league_id: int,
        season: int,
        date_from: date,
        date_to: date,
    ) -> List[Dict[str, Any]]:
        """Fetch fixtures from API-Football for a league and date range."""
        try:
            resp = self.api_client._make_request('fixtures', {
                'league': league_id,
                'season': season,
                'from': date_from.isoformat(),
                'to': date_to.isoformat(),
                'status': 'FT',  # Only completed fixtures
            })
            return resp.get('response', [])
        except Exception as e:
            logger.error(f"Error fetching fixtures for league {league_id}: {e}")
            return []

    def _get_tracked_player_ids(self) -> Dict[int, int]:
        """
        Get mapping of API player IDs to TrackedPlayer IDs for matching.

        Returns:
            Dict mapping player_api_id -> tracked_player.id
        """
        players = TrackedPlayer.query.filter(
            TrackedPlayer.is_active == True,
        ).all()
        return {p.player_api_id: p.id for p in players}

    def _process_fixture(
        self,
        fixture: Dict[str, Any],
        league: AcademyLeague,
        tracked_player_ids: Dict[int, int],
    ) -> Dict[str, int]:
        """
        Process a single fixture: fetch lineups/events and create appearances.

        Returns:
            Dict with 'created' and 'updated' counts
        """
        fixture_info = fixture.get('fixture', {})
        fixture_id = fixture_info.get('id')
        fixture_date_str = fixture_info.get('date', '')[:10]

        if not fixture_id:
            return {'created': 0, 'updated': 0}

        try:
            fixture_date = date.fromisoformat(fixture_date_str)
        except ValueError:
            logger.warning(f"Invalid fixture date: {fixture_date_str}")
            return {'created': 0, 'updated': 0}

        teams = fixture.get('teams', {})
        home_team = teams.get('home', {}).get('name', 'Unknown')
        away_team = teams.get('away', {}).get('name', 'Unknown')

        league_info = fixture.get('league', {})
        competition = league_info.get('name', league.name)

        # Fetch lineups and events
        lineups_data = self.api_client.get_fixture_lineups(fixture_id)
        events_data = self.api_client.get_fixture_events(fixture_id)

        lineups = lineups_data.get('response', [])
        events = events_data.get('response', [])

        # Extract players from lineups
        players = self._extract_players_from_lineups(lineups)

        # Enrich with events (goals, assists, cards)
        player_events = self._extract_player_events(events)

        created = 0
        updated = 0

        for player_id, player_info in players.items():
            # Check if appearance already exists
            existing = AcademyAppearance.query.filter_by(
                player_id=player_id,
                fixture_id=fixture_id,
            ).first()

            # Get events for this player
            p_events = player_events.get(player_id, {})

            if existing:
                # Update existing appearance
                existing.goals = p_events.get('goals', 0)
                existing.assists = p_events.get('assists', 0)
                existing.yellow_cards = p_events.get('yellow_cards', 0)
                existing.red_cards = p_events.get('red_cards', 0)
                updated += 1
            else:
                # Create new appearance
                appearance = AcademyAppearance(
                    player_id=player_id,
                    player_name=player_info.get('name', f'Player {player_id}'),
                    fixture_id=fixture_id,
                    fixture_date=fixture_date,
                    home_team=home_team,
                    away_team=away_team,
                    competition=competition,
                    academy_league_id=league.id,
                    loaned_player_id=tracked_player_ids.get(player_id),
                    started=player_info.get('started', False),
                    minutes_played=player_info.get('minutes'),
                    goals=p_events.get('goals', 0),
                    assists=p_events.get('assists', 0),
                    yellow_cards=p_events.get('yellow_cards', 0),
                    red_cards=p_events.get('red_cards', 0),
                    lineup_data=player_info.get('raw'),
                    events_data=p_events.get('raw'),
                )
                db.session.add(appearance)
                created += 1

        db.session.commit()
        return {'created': created, 'updated': updated}

    def _extract_players_from_lineups(
        self,
        lineups: List[Dict[str, Any]],
    ) -> Dict[int, Dict[str, Any]]:
        """
        Extract player info from lineups data.

        Returns:
            Dict mapping player_id -> {'name', 'started', 'minutes', 'raw'}
        """
        players = {}

        for team_lineup in lineups:
            # Starting XI
            for player in team_lineup.get('startXI', []):
                p = player.get('player', {})
                player_id = p.get('id')
                if player_id:
                    players[player_id] = {
                        'name': p.get('name', ''),
                        'started': True,
                        'minutes': None,  # Not always available
                        'raw': player,
                    }

            # Substitutes who came on
            for player in team_lineup.get('substitutes', []):
                p = player.get('player', {})
                player_id = p.get('id')
                # Only include subs who actually played (would need event data)
                # For now, we'll just track that they were in the squad
                if player_id and player_id not in players:
                    players[player_id] = {
                        'name': p.get('name', ''),
                        'started': False,
                        'minutes': None,
                        'raw': player,
                    }

        return players

    def _extract_player_events(
        self,
        events: List[Dict[str, Any]],
    ) -> Dict[int, Dict[str, Any]]:
        """
        Extract goals, assists, cards from events data.

        Returns:
            Dict mapping player_id -> {'goals', 'assists', 'yellow_cards', 'red_cards', 'raw'}
        """
        player_events: Dict[int, Dict[str, Any]] = {}

        for event in events:
            event_type = event.get('type', '').lower()
            event_detail = event.get('detail', '').lower()
            player = event.get('player', {})
            player_id = player.get('id')
            assist = event.get('assist', {})
            assist_id = assist.get('id') if assist else None

            if not player_id:
                continue

            if player_id not in player_events:
                player_events[player_id] = {
                    'goals': 0,
                    'assists': 0,
                    'yellow_cards': 0,
                    'red_cards': 0,
                    'raw': [],
                }

            player_events[player_id]['raw'].append(event)

            if event_type == 'goal':
                # Own goals don't count
                if 'own goal' not in event_detail:
                    player_events[player_id]['goals'] += 1

                # Track assist
                if assist_id:
                    if assist_id not in player_events:
                        player_events[assist_id] = {
                            'goals': 0,
                            'assists': 0,
                            'yellow_cards': 0,
                            'red_cards': 0,
                            'raw': [],
                        }
                    player_events[assist_id]['assists'] += 1
                    player_events[assist_id]['raw'].append(event)

            elif event_type == 'card':
                if 'yellow' in event_detail:
                    player_events[player_id]['yellow_cards'] += 1
                elif 'red' in event_detail:
                    player_events[player_id]['red_cards'] += 1

        return player_events

    def get_player_academy_stats(
        self,
        player_id: int,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
    ) -> Dict[str, Any]:
        """
        Get aggregated academy stats for a player.

        Args:
            player_id: API-Football player ID
            date_from: Optional start date filter
            date_to: Optional end date filter

        Returns:
            Dict with appearances, starts, goals, assists, etc.
        """
        query = AcademyAppearance.query.filter_by(player_id=player_id)

        if date_from:
            query = query.filter(AcademyAppearance.fixture_date >= date_from)
        if date_to:
            query = query.filter(AcademyAppearance.fixture_date <= date_to)

        appearances = query.order_by(AcademyAppearance.fixture_date.desc()).all()

        if not appearances:
            return {
                'player_id': player_id,
                'appearances': 0,
                'starts': 0,
                'goals': 0,
                'assists': 0,
                'yellow_cards': 0,
                'red_cards': 0,
                'matches': [],
            }

        return {
            'player_id': player_id,
            'player_name': appearances[0].player_name if appearances else None,
            'appearances': len(appearances),
            'starts': sum(1 for a in appearances if a.started),
            'goals': sum(a.goals for a in appearances),
            'assists': sum(a.assists for a in appearances),
            'yellow_cards': sum(a.yellow_cards for a in appearances),
            'red_cards': sum(a.red_cards for a in appearances),
            'matches': [a.to_dict() for a in appearances[:10]],  # Last 10 matches
        }


# Singleton instance
academy_sync_service = AcademySyncService()
