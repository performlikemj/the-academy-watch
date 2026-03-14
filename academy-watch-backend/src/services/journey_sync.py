"""
Journey Sync Service

Fetches and processes player career data from API-Football to build
complete journey records with academy, loan, and first team data.
"""

import logging
import re
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy.exc import IntegrityError

from src.models.league import db, Team, TeamProfile
from src.models.journey import (
    PlayerJourney, PlayerJourneyEntry, ClubLocation,
    LEVEL_PRIORITY, YOUTH_LEVELS
)
from src.api_football_client import APIFootballClient, is_new_loan_transfer, LOAN_RETURN_TYPES
from src.utils.geocoding import get_team_coordinates
from src.utils.academy_classifier import (
    YOUTH_SUFFIXES as _YOUTH_SUFFIXES_RE,
    INTERNATIONAL_PATTERNS as _INTERNATIONAL_PATTERNS,
    is_international_competition,
    is_national_team,
    strip_youth_suffix,
)

logger = logging.getLogger(__name__)


class JourneySyncService:
    """Service for syncing player journey data from API-Football"""
    
    # Delegate to shared utility (kept as class attr for backward compat)
    YOUTH_SUFFIXES = _YOUTH_SUFFIXES_RE

    # Patterns to detect youth/academy levels
    LEVEL_PATTERNS = {
        'U18': ['u18', 'under 18', 'under-18', 'youth cup'],
        'U19': ['u19', 'under 19', 'under-19', 'youth league'],
        'U21': ['u21', 'under 21', 'under-21'],
        'U23': ['u23', 'under 23', 'under-23', 'premier league 2', 'pl2',
                'development squad', 'development league', 'efl development'],
        'Reserve': ['reserve', 'b team', ' ii', ' b ', 'second team'],
    }
    
    # Top-flight leagues that indicate first team level
    TOP_LEAGUES = [
        'premier league', 'la liga', 'serie a', 'bundesliga', 'ligue 1',
        'eredivisie', 'primeira liga', 'scottish premiership',
        'fa cup', 'league cup', 'efl cup', 'carabao',
        'champions league', 'europa league', 'conference league',
        'copa del rey', 'coppa italia', 'dfb-pokal', 'coupe de france',
        'community shield', 'supercopa', 'super cup',
    ]
    
    # Delegate to shared utility
    INTERNATIONAL_PATTERNS = _INTERNATIONAL_PATTERNS
    
    def __init__(self, api_client: Optional[APIFootballClient] = None):
        """Initialize with optional API client"""
        self.api = api_client or APIFootballClient()
    
    def sync_player(self, player_api_id: int, force_full: bool = False, heartbeat_fn=None) -> Optional[PlayerJourney]:
        """
        Sync complete journey for a player.

        Args:
            player_api_id: API-Football player ID
            force_full: If True, re-sync all seasons even if already synced
            heartbeat_fn: Optional callable invoked between API stages to signal liveness

        Returns:
            PlayerJourney record or None if sync failed
        """
        logger.info(f"Starting journey sync for player {player_api_id}")
        
        try:
            # Get or create journey record (handle race conditions)
            journey = PlayerJourney.query.filter_by(player_api_id=player_api_id).first()
            if not journey:
                journey = PlayerJourney(player_api_id=player_api_id)
                db.session.add(journey)
                try:
                    db.session.flush()
                except IntegrityError:
                    db.session.rollback()
                    journey = PlayerJourney.query.filter_by(player_api_id=player_api_id).first()
                    if not journey:
                        raise
            
            # Get all seasons for this player
            seasons = self._get_player_seasons(player_api_id)
            if not seasons:
                journey.sync_error = "No seasons found for player"
                db.session.commit()
                return journey

            if heartbeat_fn:
                heartbeat_fn()

            logger.info(f"Found {len(seasons)} seasons for player {player_api_id}: {seasons}")

            # Determine which seasons to sync
            already_synced = set(journey.seasons_synced or [])
            if force_full:
                seasons_to_sync = seasons
            else:
                # Always sync current and previous season, plus any new ones
                current_year = datetime.now().year
                seasons_to_sync = [
                    s for s in seasons 
                    if s not in already_synced or s >= current_year - 1
                ]
            
            # Fetch transfer history for loan classification
            transfers = self._get_player_transfers(player_api_id)
            loan_timeline = self._build_transfer_timeline(transfers)

            if heartbeat_fn:
                heartbeat_fn()

            # Fetch and process each season
            all_entries = []
            player_info = None

            for season_idx, season in enumerate(sorted(seasons_to_sync)):
                try:
                    player_data = self._get_player_season_data(player_api_id, season)
                    if not player_data:
                        continue

                    # Extract player info from first successful response
                    if not player_info and 'player' in player_data:
                        player_info = player_data['player']

                    # Process statistics into entries
                    for stat in player_data.get('statistics', []):
                        if not self._is_official_competition(stat):
                            logger.debug(f"Skipping non-official competition: {stat.get('league', {}).get('name')}")
                            continue
                        entry = self._create_entry_from_stat(journey.id, season, stat)
                        if entry:
                            all_entries.append(entry)

                except Exception as e:
                    logger.warning(f"Failed to fetch season {season} for player {player_api_id}: {e}")
                    continue

                if heartbeat_fn and (season_idx + 1) % 3 == 0:
                    heartbeat_fn()

            # Deduplicate entries with identical stat fingerprints
            all_entries = self._deduplicate_entries(all_entries)

            # Classify loan entries based on transfer history
            self._apply_loan_classification(all_entries, loan_timeline)

            # Fill in transfer_date from permanent transfers for entries that
            # don't already have one (ensures current-club tiebreaker works)
            self._apply_permanent_transfer_dates(all_entries, transfers)

            # Reclassify youth entries as 'development' or 'integration'
            # based on first-team history, transfer records, and age
            self._apply_development_classification(
                all_entries, transfers=transfers,
                birth_date=(player_info or {}).get('birth', {}).get('date'),
            )

            # Update player info
            if player_info:
                journey.player_name = player_info.get('name')
                journey.player_photo = player_info.get('photo')
                birth = player_info.get('birth', {})
                journey.birth_date = birth.get('date')
                journey.birth_country = birth.get('country')
                journey.nationality = player_info.get('nationality')
            
            # Remove old entries for synced seasons and add new ones
            if all_entries:
                synced_seasons = set(e.season for e in all_entries)
                PlayerJourneyEntry.query.filter(
                    PlayerJourneyEntry.journey_id == journey.id,
                    PlayerJourneyEntry.season.in_(synced_seasons)
                ).delete(synchronize_session=False)
                
                for entry in all_entries:
                    entry.journey_id = journey.id
                    db.session.add(entry)
            
            # Update journey aggregates
            self._update_journey_aggregates(journey, transfers=transfers)

            # Auto-geocode missing club locations
            try:
                self._auto_geocode_clubs(journey)
            except Exception as e:
                logger.warning(f"_auto_geocode_clubs failed for player {player_api_id}: {e}")

            # Update sync tracking
            journey.seasons_synced = sorted(set((journey.seasons_synced or []) + seasons_to_sync))
            journey.last_synced_at = datetime.now(timezone.utc)
            journey.sync_error = None

            db.session.commit()
            logger.info(f"Successfully synced journey for player {player_api_id}: {len(all_entries)} entries")
            
            return journey
            
        except Exception as e:
            logger.error(f"Failed to sync journey for player {player_api_id}: {e}")
            db.session.rollback()

            # Try to save error state
            try:
                journey = PlayerJourney.query.filter_by(player_api_id=player_api_id).first()
                if journey:
                    journey.sync_error = str(e)
                    db.session.commit()
            except Exception as save_err:
                logger.error(f"Failed to save sync_error for player {player_api_id}: {save_err}")
                db.session.rollback()

            return None
    
    def _get_player_seasons(self, player_api_id: int) -> List[int]:
        """Get all seasons a player has data for"""
        try:
            response = self.api._make_request('players/seasons', {'player': player_api_id})
            seasons = response.get('response', [])
            return [int(s) for s in seasons if isinstance(s, (int, str)) and str(s).isdigit()]
        except Exception as e:
            logger.error(f"Failed to get seasons for player {player_api_id}: {e}")
            return []
    
    def _get_player_season_data(self, player_api_id: int, season: int) -> Optional[Dict]:
        """Get player data for a specific season"""
        try:
            response = self.api._make_request('players', {'id': player_api_id, 'season': season})
            data = response.get('response', [])
            return data[0] if data else None
        except Exception as e:
            logger.error(f"Failed to get player {player_api_id} season {season}: {e}")
            return None
    
    def _create_entry_from_stat(self, journey_id: int, season: int, stat: Dict) -> Optional[PlayerJourneyEntry]:
        """Create a journey entry from API-Football statistics block"""
        team = stat.get('team', {})
        league = stat.get('league', {})
        games = stat.get('games', {})
        goals = stat.get('goals', {})
        
        team_id = team.get('id')
        league_id = league.get('id')
        
        if not team_id:
            return None
        
        appearances = games.get('appearences') or games.get('appearances') or 0

        team_name = team.get('name', '')
        league_name = league.get('name', '')
        
        # Classify the entry
        level = self._classify_level(team_name, league_name)
        entry_type = self._classify_entry_type(level, league_name)
        is_youth = level in YOUTH_LEVELS
        is_international = self._is_international(league_name)
        
        entry = PlayerJourneyEntry(
            journey_id=journey_id,
            season=season,
            club_api_id=team_id,
            club_name=team_name,
            club_logo=team.get('logo'),
            league_api_id=league_id,
            league_name=league_name,
            league_country=league.get('country'),
            league_logo=league.get('logo'),
            level=level,
            entry_type=entry_type,
            is_youth=is_youth,
            is_international=is_international,
            appearances=appearances,
            goals=goals.get('total') or 0,
            assists=goals.get('assists') or 0,
            minutes=games.get('minutes') or 0,
            sort_priority=LEVEL_PRIORITY.get(level, 0),
        )
        
        return entry
    
    def _classify_level(self, team_name: str, league_name: str) -> str:
        """Determine the level (U18, U21, First Team, etc.) from team/league names"""
        team_lower = team_name.lower()
        league_lower = league_name.lower()
        combined = f"{team_lower} {league_lower}"
        
        # Check for youth levels
        for level, patterns in self.LEVEL_PATTERNS.items():
            for pattern in patterns:
                if pattern in combined:
                    return level
        
        # Check for international
        if self._is_international(league_name):
            # Check if it's youth international
            if any(x in league_lower for x in ['u17', 'u18', 'u19', 'u20', 'u21', 'u23', 'youth']):
                return 'International Youth'
            return 'International'
        
        # Check for top-flight leagues (first team)
        for top_league in self.TOP_LEAGUES:
            if top_league in league_lower:
                return 'First Team'
        
        # Default to first team for unrecognized leagues
        return 'First Team'
    
    def _classify_entry_type(self, level: str, league_name: str) -> str:
        """Classify entry type (academy, first_team, international, etc.)"""
        if 'International' in level:
            return 'international'
        if level in YOUTH_LEVELS:
            return 'academy'
        return 'first_team'
    
    def _is_international(self, league_name: str) -> bool:
        """Check if league is international"""
        return is_international_competition(league_name)

    def _is_official_competition(self, stat: Dict) -> bool:
        """
        Check if a stat block represents an official competition.

        Uses API-Football's league_id assignment as the allowlist:
        - Non-null league_id = API-Football recognizes it as official
        - Null league_id + youth team pattern = kept (youth cups sometimes lack IDs)
        - Null league_id + international = kept
        - Null league_id + none of the above = filtered (preseason/friendly)
        """
        league = stat.get('league', {})
        team = stat.get('team', {})
        league_id = league.get('id')

        # Non-null league_id = API-Football recognizes it as official
        if league_id is not None:
            return True

        # Null league_id: only keep if youth team or international
        team_name = (team.get('name') or '').lower()

        # Youth teams (FA Youth Cup etc. sometimes lack league IDs)
        for pattern in ['u15', 'u16', 'u17', 'u18', 'u19', 'u20', 'u21', 'u23']:
            if pattern in team_name:
                return True

        # International competitions
        if self._is_international(league.get('name', '')):
            return True

        return False

    def _get_player_transfers(self, player_api_id: int) -> list:
        """
        Get transfer records for a player.

        Calls the API client's cached get_player_transfers method.
        Returns a flat list of transfer dicts on success, [] on error.
        """
        try:
            data = self.api.get_player_transfers(player_api_id)
            # API returns list of player blocks, each with a 'transfers' list
            transfers = []
            for block in data:
                transfers.extend(block.get('transfers', []))
            return transfers
        except Exception as e:
            logger.warning(f"Failed to get transfers for player {player_api_id}: {e}")
            return []

    def _build_transfer_timeline(self, transfers: list) -> list:
        """
        Build a list of loan periods from transfer records.

        Returns list of dicts:
            [{club_id, club_name, parent_club_id, start_date, end_date}, ...]

        Loan starts are identified by is_new_loan_transfer().
        Loan ends are identified by LOAN_RETURN_TYPES.
        """
        loan_periods = []

        for transfer in transfers:
            transfer_type = (transfer.get('type') or '').strip().lower()
            transfer_date = transfer.get('date')
            teams = transfer.get('teams', {})
            team_in = teams.get('in', {})
            team_out = teams.get('out', {})

            if is_new_loan_transfer(transfer_type):
                # New loan: player goes OUT from parent → IN to loan club
                loan_periods.append({
                    'club_id': team_in.get('id'),
                    'club_name': team_in.get('name'),
                    'parent_club_id': team_out.get('id'),
                    'start_date': transfer_date,
                    'end_date': None,  # open-ended until we find a return
                })
            elif transfer_type in LOAN_RETURN_TYPES:
                # Loan return: close the most recent open loan for this parent club
                return_parent_id = team_in.get('id')
                for period in reversed(loan_periods):
                    if period['parent_club_id'] == return_parent_id and period['end_date'] is None:
                        period['end_date'] = transfer_date
                        break

        return loan_periods

    def _loan_overlaps_season(self, loan: Dict, season: int) -> bool:
        """
        Check if a loan period overlaps a football season.

        A season (e.g. 2023) runs roughly July 2023 to June 2024.
        """
        season_start = f"{season}-07-01"
        season_end = f"{season + 1}-06-30"

        loan_start = loan.get('start_date') or ''
        loan_end = loan.get('end_date')

        if not loan_start:
            return False

        # Loan must start before season ends
        if loan_start > season_end:
            return False

        # If loan has an end date, it must end after season starts
        if loan_end and loan_end < season_start:
            return False

        return True

    def _deduplicate_entries(self, entries: list) -> list:
        """
        Remove duplicate entries based on stat fingerprint.

        Fingerprint: (season, appearances, minutes, goals, assists)

        When duplicates found:
        - Prefer youth entries (is_youth=True) over senior
        - If no youth entry, prefer lowest sort_priority
        """
        from collections import defaultdict

        groups = defaultdict(list)
        for entry in entries:
            fingerprint = (
                entry.season,
                entry.appearances,
                entry.minutes,
                entry.goals,
                entry.assists,
            )
            groups[fingerprint].append(entry)

        result = []
        for fingerprint, group in groups.items():
            if len(group) == 1:
                result.append(group[0])
                continue

            # Multiple entries with same fingerprint — pick the best one
            youth_entries = [e for e in group if e.is_youth]
            if youth_entries:
                # Prefer youth entry (stats often duplicated UP from youth to senior)
                winner = min(youth_entries, key=lambda e: e.sort_priority)
            else:
                winner = min(group, key=lambda e: e.sort_priority)

            removed = [e for e in group if e is not winner]
            for e in removed:
                logger.debug(
                    f"Dedup: removed {e.club_name}/{e.league_name} season {e.season} "
                    f"(dup of {winner.club_name}/{winner.league_name})"
                )

            result.append(winner)

        return result

    def _apply_loan_classification(self, entries: list, loan_timeline: list):
        """
        Set entry_type='loan' and transfer_date for entries at loan clubs.

        For each non-international entry, if club_api_id matches a loan period
        overlapping that season, classify it as a loan and record the
        transfer start date for ordering purposes.
        """
        if not loan_timeline:
            return

        for entry in entries:
            if entry.is_international:
                continue

            for loan in loan_timeline:
                if (entry.club_api_id == loan.get('club_id') and
                        self._loan_overlaps_season(loan, entry.season)):
                    entry.entry_type = 'loan'
                    entry.transfer_date = loan.get('start_date')
                    break

    def _apply_permanent_transfer_dates(self, entries: list, transfers: list):
        """
        Fill in transfer_date from permanent transfers for entries that don't
        already have one (loan entries keep their existing dates from
        _apply_loan_classification).

        This ensures the current-club tiebreaker in _update_journey_aggregates
        correctly picks the most recent club when multiple First Team entries
        share the same season and sort_priority.

        For each entry without a transfer_date, find the most recent transfer
        where team_in.id matches the entry's club_api_id and the transfer date
        falls within or before that season.
        """
        if not transfers:
            return

        # Build list of (date, destination_club_id) from ALL transfers
        all_moves = []
        for transfer in transfers:
            transfer_date = transfer.get('date')
            teams = transfer.get('teams', {})
            team_in = teams.get('in', {})
            dest_id = team_in.get('id')
            if transfer_date and dest_id:
                all_moves.append((transfer_date, dest_id))

        if not all_moves:
            return

        # Sort by date ascending so we can find the best match
        all_moves.sort(key=lambda x: x[0])

        for entry in entries:
            if entry.transfer_date:
                continue  # Already set by loan classification
            if entry.is_international:
                continue

            # Find the most recent transfer TO this club up to the end of
            # the summer transfer window after the season.  API-Football
            # sometimes records mid-season moves with a summer date (e.g.
            # Elanga: Forest→Newcastle recorded as 2025-07-10 but played for
            # Newcastle in the 2024 season), so we extend to Sep 30.
            window_end = f"{entry.season + 1}-09-30"
            best_date = None
            for move_date, dest_id in all_moves:
                if dest_id == entry.club_api_id and move_date <= window_end:
                    best_date = move_date  # Keep updating — last match wins (latest)

            if best_date:
                entry.transfer_date = best_date
                logger.debug(
                    f"Set transfer_date={best_date} for {entry.club_name} "
                    f"season {entry.season} (from permanent transfer)"
                )

    def _apply_development_classification(self, entries: list, transfers=None,
                                          birth_date=None):
        """
        Reclassify youth 'academy' entries based on the player's career context.

        Three youth categories:
        - 'academy': genuine academy product with no prior first-team
          experience anywhere (e.g. Rashford at Man Utd U19).
        - 'development': player had first-team apps at the SAME parent club
          in a prior season — senior player sent to youth for game time.
          Same-season entries (breakthrough year) stay as 'academy'.
        - 'integration': player had first-team apps at a DIFFERENT club
          before this youth entry — bought player being integrated
          (e.g. Diallo playing Man Utd U23 after Atalanta first team).

        Enhanced detection uses three signals:
        1. Journey entries (original): first-team at another club in data
        2. Transfer records: permanent transfer TO this club = not academy
        3. Age at entry: first appearance at club aged 21+ = not academy
        """
        # Build lookup: parent_base_name -> earliest first-team season
        first_team_debut_by_club = {}
        for entry in entries:
            if entry.level == 'First Team' and not entry.is_international:
                base_name = self._strip_youth_suffix(entry.club_name)
                existing = first_team_debut_by_club.get(base_name)
                if existing is None or entry.season < existing:
                    first_team_debut_by_club[base_name] = entry.season

        # Build set of clubs the player was permanently transferred TO.
        # A permanent transfer TO a club means the player is NOT an academy
        # product of that club — academy products don't need to be transferred in.
        permanent_transfer_dest_ids = set()
        if transfers:
            for transfer in transfers:
                transfer_type = (transfer.get('type') or '').strip().lower()
                # Skip loans — loan moves don't disqualify academy status
                if not transfer_type or is_new_loan_transfer(transfer_type):
                    continue
                if transfer_type in LOAN_RETURN_TYPES:
                    continue
                # This is a permanent transfer (bought, free agent, swap, etc.)
                teams = transfer.get('teams', {})
                dest = teams.get('in', {})
                dest_id = dest.get('id')
                if dest_id:
                    permanent_transfer_dest_ids.add(dest_id)

        # Parse birth year for age-at-entry validation
        birth_year = None
        if birth_date:
            try:
                birth_year = int(str(birth_date)[:4])
            except (ValueError, TypeError):
                pass

        # Track earliest season per club for age-based checks
        earliest_season_at_club = {}
        for entry in entries:
            if entry.is_youth and not entry.is_international:
                base = self._strip_youth_suffix(entry.club_name)
                existing = earliest_season_at_club.get(base)
                if existing is None or entry.season < existing:
                    earliest_season_at_club[base] = entry.season

        # Pass 1: journey-entry-based classification (original logic)
        if first_team_debut_by_club:
            for entry in entries:
                if entry.entry_type != 'academy' or entry.is_international:
                    continue

                parent_name = self._strip_youth_suffix(entry.club_name)
                same_club_debut = first_team_debut_by_club.get(parent_name)

                # Development: same parent club had first-team in a prior season
                if same_club_debut is not None and entry.season > same_club_debut:
                    entry.entry_type = 'development'
                    logger.debug(
                        f"Reclassified {entry.club_name} season {entry.season} as "
                        f"development (first-team debut at {parent_name} in {same_club_debut})"
                    )
                    continue

                # Integration: first-team at a DIFFERENT club before or during
                # this youth season (player was bought with senior experience)
                for club_name, debut in first_team_debut_by_club.items():
                    if club_name != parent_name and debut <= entry.season:
                        entry.entry_type = 'integration'
                        logger.debug(
                            f"Reclassified {entry.club_name} season {entry.season} as "
                            f"integration (first-team at {club_name} in {debut})"
                        )
                        break

        # Pass 2: transfer-based integration detection
        # If a player was permanently transferred TO a club, any youth entries
        # at that club are integration, not academy.
        if permanent_transfer_dest_ids:
            for entry in entries:
                if entry.entry_type != 'academy' or entry.is_international:
                    continue
                if entry.club_api_id in permanent_transfer_dest_ids:
                    entry.entry_type = 'integration'
                    logger.debug(
                        f"Reclassified {entry.club_name} season {entry.season} as "
                        f"integration (permanent transfer destination)"
                    )

        # Pass 3: age-at-entry validation
        # If a player's FIRST appearance at a club's youth system was at age 21+,
        # they are not an academy product — they were bought as a senior player.
        # Players who joined younger and continue playing U23 at 21-22 are fine.
        if birth_year:
            for entry in entries:
                if entry.entry_type != 'academy' or entry.is_international:
                    continue
                parent_name = self._strip_youth_suffix(entry.club_name)
                first_season = earliest_season_at_club.get(parent_name)
                if first_season is not None:
                    age_at_first = first_season - birth_year
                    if age_at_first >= 21:
                        entry.entry_type = 'integration'
                        logger.debug(
                            f"Reclassified {entry.club_name} season {entry.season} as "
                            f"integration (age {age_at_first} at first youth appearance, "
                            f"season {first_season})"
                        )

    def _update_journey_aggregates(self, journey: PlayerJourney, transfers=None):
        """Update aggregate stats on the journey record"""
        entries = PlayerJourneyEntry.query.filter_by(journey_id=journey.id).all()
        
        if not entries:
            return
        
        # Helper: exclude international entries (call-ups are not club moves)
        def _is_domestic(e):
            if e.is_international:
                return False
            if e.entry_type == 'international':
                return False
            if 'International' in (e.level or ''):
                return False
            if is_national_team(e.club_name):
                return False
            return True

        # Find origin (earliest domestic entry)
        domestic_entries = [e for e in entries if _is_domestic(e)]
        origin_entries = domestic_entries if domestic_entries else entries
        earliest = min(origin_entries, key=lambda e: (e.season, -e.sort_priority))

        if earliest.is_youth:
            # Resolve youth/reserve team to parent club
            base_name = self._strip_youth_suffix(earliest.club_name)
            resolved_id = self._resolve_parent_club_id(base_name, entries)
            if resolved_id:
                journey.origin_club_api_id = resolved_id
                journey.origin_club_name = base_name
            else:
                journey.origin_club_api_id = earliest.club_api_id
                journey.origin_club_name = base_name  # still strip suffix for display
        else:
            journey.origin_club_api_id = earliest.club_api_id
            journey.origin_club_name = earliest.club_name
        journey.origin_year = earliest.season

        # Find current club: latest season, highest priority, most recent transfer
        if domestic_entries:
            latest_season = max(e.season for e in domestic_entries)
            latest_entries = [e for e in domestic_entries if e.season == latest_season]
            current = max(latest_entries, key=lambda e: (e.sort_priority, e.transfer_date or ''))
            journey.current_club_api_id = current.club_api_id
            journey.current_club_name = current.club_name
            journey.current_level = current.level
        else:
            # Only international entries exist — use them as fallback
            latest_season = max(e.season for e in entries)
            latest_entries = [e for e in entries if e.season == latest_season]
            current = max(latest_entries, key=lambda e: (e.sort_priority, e.transfer_date or ''))
            journey.current_club_api_id = current.club_api_id
            journey.current_club_name = current.club_name
            journey.current_level = current.level
        
        # Find first team debut
        first_team_entries = [e for e in entries if e.level == 'First Team' and not e.is_international]
        if first_team_entries:
            debut = min(first_team_entries, key=lambda e: e.season)
            journey.first_team_debut_season = debut.season
            journey.first_team_debut_club_id = debut.club_api_id
            journey.first_team_debut_club = debut.club_name
            journey.first_team_debut_competition = debut.league_name
            debut.is_first_team_debut = True
        
        # Calculate totals
        unique_clubs = set(e.club_api_id for e in entries if not e.is_international)
        journey.total_clubs = len(unique_clubs)
        
        journey.total_first_team_apps = sum(
            e.appearances for e in entries 
            if e.level == 'First Team' and not e.is_international
        )
        journey.total_youth_apps = sum(
            e.appearances for e in entries if e.is_youth
        )
        journey.total_loan_apps = sum(
            e.appearances for e in entries if e.entry_type == 'loan'
        )
        journey.total_goals = sum(e.goals for e in entries)
        journey.total_assists = sum(e.assists for e in entries)

        # Compute academy connections from youth entries
        self._compute_academy_club_ids(journey, entries, transfers=transfers)

    def _strip_youth_suffix(self, club_name: str) -> str:
        """Strip youth team suffix to get parent club base name."""
        return strip_youth_suffix(club_name)

    def _resolve_parent_club_id(self, base_name: str, entries: list) -> int | None:
        """Resolve a youth/reserve team base name to the parent club's API ID.

        Resolution order:
        1. Senior entries in the same journey with matching club name
        2. TeamProfile exact name match
        3. Team table exact name match
        """
        # Check senior entries in the same journey
        for e in entries:
            if not e.is_youth and not e.is_international and e.club_name == base_name:
                return e.club_api_id

        # Fallback: TeamProfile exact name
        profile = TeamProfile.query.filter(TeamProfile.name == base_name).first()
        if profile:
            return profile.team_id

        # Fallback: Team table exact name
        team = Team.query.filter(Team.name == base_name).first()
        if team:
            return team.team_id

        return None

    def _compute_academy_club_ids(self, journey: PlayerJourney, entries: list | None = None, transfers=None):
        """
        Derive academy parent club IDs from youth journey entries.

        Algorithm:
        1. Collect all youth entries (is_youth=True, excluding internationals)
        2. Strip youth suffix from club name to get parent base name
        3. Resolve parent club API ID:
           - First: check non-youth entries in same journey for matching club name
           - Fallback: query TeamProfile for matching name
        4. Deduplicate and store as JSON array
        """
        if entries is None:
            entries = PlayerJourneyEntry.query.filter_by(journey_id=journey.id).all()

        youth_entries = [
            e for e in entries
            if e.is_youth and not e.is_international
            and e.entry_type in ('academy', 'development')
            and not is_national_team(e.club_name)
        ]
        if not youth_entries:
            journey.academy_club_ids = []
            # Deactivate any stale tracked-player rows from prior runs
            self._upsert_tracked_players(journey, set(), transfers=transfers)
            return

        # ── Minimum youth appearances threshold ──
        # Clubs below threshold are excluded to filter noise / data errors.
        MIN_ACADEMY_APPEARANCES = 1
        club_youth_apps = {}
        for e in youth_entries:
            base = self._strip_youth_suffix(e.club_name)
            club_youth_apps[base] = club_youth_apps.get(base, 0) + (e.appearances or 0)

        youth_entries = [
            e for e in youth_entries
            if club_youth_apps.get(self._strip_youth_suffix(e.club_name), 0)
            >= MIN_ACADEMY_APPEARANCES
        ]
        if not youth_entries:
            journey.academy_club_ids = []
            # Deactivate any stale tracked-player rows from prior runs
            self._upsert_tracked_players(journey, set(), transfers=transfers)
            return

        # Build lookup: base_name -> api_id from non-youth, non-international entries
        senior_name_to_id = {}
        for e in entries:
            if not e.is_youth and not e.is_international:
                senior_name_to_id[e.club_name] = e.club_api_id

        # Collect league_country per base_name for country-aware fallback matching
        club_country = {}
        for e in youth_entries:
            base = self._strip_youth_suffix(e.club_name)
            if e.league_country and base not in club_country:
                club_country[base] = e.league_country

        academy_ids = set()
        unresolved = []

        for entry in youth_entries:
            base_name = self._strip_youth_suffix(entry.club_name)
            entry_country = club_country.get(base_name)

            # Try matching a senior entry first
            if base_name in senior_name_to_id:
                academy_ids.add(senior_name_to_id[base_name])
                continue

            # Fallback 1: query TeamProfile (exact name)
            profile = TeamProfile.query.filter(
                TeamProfile.name == base_name
            ).first()
            if profile:
                academy_ids.add(profile.team_id)
                continue

            # Fallback 2: query Team table (exact name, broader coverage)
            team = Team.query.filter(Team.name == base_name).first()
            if team:
                academy_ids.add(team.team_id)
                continue

            # Fallback 3: TeamProfile name is a substring of base_name
            # Handles "Tottenham Hotspur" containing "Tottenham", etc.
            # Country filter prevents cross-contamination between similarly
            # named clubs in different countries.
            fb3_query = TeamProfile.query.filter(
                db.func.strpos(base_name, TeamProfile.name) > 0,
                db.func.length(TeamProfile.name) >= 5,
            )
            if entry_country:
                fb3_query = fb3_query.filter(TeamProfile.country == entry_country)
            profile = fb3_query.order_by(
                db.func.length(TeamProfile.name).desc()
            ).first()
            if profile:
                academy_ids.add(profile.team_id)
                continue

            # Fallback 4: Team name is a substring of base_name
            fb4_query = Team.query.filter(
                db.func.strpos(base_name, Team.name) > 0,
                db.func.length(Team.name) >= 5,
            )
            if entry_country:
                fb4_query = fb4_query.filter(Team.country == entry_country)
            team = fb4_query.order_by(
                db.func.length(Team.name).desc()
            ).first()
            if team:
                academy_ids.add(team.team_id)
                continue

            unresolved.append(base_name)

        if unresolved:
            logger.warning(
                f"Could not resolve academy parent club for player "
                f"{journey.player_api_id}: {set(unresolved)}"
            )

        journey.academy_club_ids = sorted(academy_ids)

        # Auto-upsert TrackedPlayer rows for each academy connection
        try:
            self._upsert_tracked_players(journey, academy_ids, transfers=transfers)
        except Exception as e:
            logger.error(f"_upsert_tracked_players failed for player {journey.player_api_id}: {e}")
            db.session.rollback()

    def _upsert_tracked_players(self, journey: PlayerJourney, academy_ids: set, transfers=None):
        """Create or update TrackedPlayer rows for discovered academy connections."""
        from src.models.tracked_player import TrackedPlayer
        from src.utils.academy_classifier import classify_tracked_player, _get_latest_season

        # Deactivate journey-sync rows whose academy connection no longer holds
        stale_rows = TrackedPlayer.query.filter_by(
            player_api_id=journey.player_api_id,
            data_source='journey-sync',
            is_active=True,
        ).all()
        for tp in stale_rows:
            if tp.team and tp.team.team_id not in academy_ids:
                tp.is_active = False

        if not academy_ids:
            return

        for academy_api_id in academy_ids:
            team = Team.query.filter_by(team_id=academy_api_id, is_active=True)\
                .order_by(Team.season.desc()).first()
            if not team:
                continue

            existing = TrackedPlayer.query.filter_by(
                player_api_id=journey.player_api_id,
                team_id=team.id,
            ).first()

            status, loan_club_api_id, loan_club_name = classify_tracked_player(
                current_club_api_id=journey.current_club_api_id,
                current_club_name=journey.current_club_name,
                current_level=journey.current_level,
                parent_api_id=academy_api_id,
                parent_club_name=team.name,
                transfers=transfers or [],
                latest_season=_get_latest_season(journey.id, parent_api_id=academy_api_id, parent_club_name=team.name),
            )

            if not existing:
                tp = TrackedPlayer(
                    player_api_id=journey.player_api_id,
                    player_name=journey.player_name or f'Player {journey.player_api_id}',
                    photo_url=journey.player_photo,
                    nationality=journey.nationality,
                    birth_date=journey.birth_date,
                    team_id=team.id,
                    journey_id=journey.id,
                    data_source='journey-sync',
                    data_depth='full_stats',
                    status=status,
                    loan_club_api_id=loan_club_api_id,
                    loan_club_name=loan_club_name,
                )
                db.session.add(tp)
            else:
                # Update status and journey link if stale
                existing.journey_id = journey.id
                existing.status = status
                existing.loan_club_api_id = loan_club_api_id
                existing.loan_club_name = loan_club_name

    @staticmethod
    def _get_latest_departure_type(transfers, parent_api_id):
        """Find the type of the most recent transfer away from a parent club."""
        departures = [
            t for t in transfers
            if (t.get('teams', {}).get('out', {}).get('id') == parent_api_id)
        ]
        if not departures:
            return None
        departures.sort(key=lambda t: t.get('date', ''), reverse=True)
        return (departures[0].get('type') or '').strip().lower()

    def _auto_geocode_clubs(self, journey: PlayerJourney):
        """Create ClubLocation rows for clubs that don't have one yet.

        Uses TeamProfile city/country when available, falls back to
        league_country from entries, and geocodes via get_team_coordinates().
        """
        entries = PlayerJourneyEntry.query.filter_by(journey_id=journey.id).all()
        if not entries:
            return

        # Collect unique club IDs (skip international entries)
        club_ids = set(e.club_api_id for e in entries if not e.is_international)
        if not club_ids:
            return

        # Find which clubs already have locations
        existing = set(
            loc.club_api_id for loc in
            ClubLocation.query.filter(ClubLocation.club_api_id.in_(club_ids)).all()
        )
        missing_ids = club_ids - existing
        if not missing_ids:
            return

        # Build lookup: club_id -> (name, country) from entries
        club_info = {}
        for entry in entries:
            if entry.club_api_id in missing_ids and entry.club_api_id not in club_info:
                club_info[entry.club_api_id] = {
                    'name': entry.club_name,
                    'country': entry.league_country,
                }

        added = 0
        for club_id in missing_ids:
            info = club_info.get(club_id, {})
            club_name = info.get('name', '')
            country = info.get('country')

            # Try TeamProfile for city/country
            city = None
            profile = TeamProfile.query.filter_by(team_id=club_id).first()
            if profile:
                city = profile.venue_city
                country = profile.country or country

            # Only geocode if we have an actual city name — using just a
            # country name produces wildly wrong results (e.g. "Scotland"
            # resolves to Virginia, USA).
            if not city:
                continue

            coords = get_team_coordinates(city, country)
            if not coords:
                continue

            location = ClubLocation(
                club_api_id=club_id,
                club_name=club_name,
                city=city,
                country=country,
                latitude=coords[0],
                longitude=coords[1],
                geocode_source='auto',
                geocode_confidence=0.7,
            )
            db.session.add(location)
            added += 1

        if added:
            logger.info(f"Auto-geocoded {added} club locations for player {journey.player_api_id}")


def seed_club_locations():
    """Seed initial club locations for major clubs"""
    
    MAJOR_CLUBS = [
        # Premier League
        {'api_id': 33, 'name': 'Manchester United', 'city': 'Manchester', 'country': 'England', 'code': 'GB', 'lat': 53.4631, 'lng': -2.2913},
        {'api_id': 40, 'name': 'Liverpool', 'city': 'Liverpool', 'country': 'England', 'code': 'GB', 'lat': 53.4308, 'lng': -2.9608},
        {'api_id': 42, 'name': 'Arsenal', 'city': 'London', 'country': 'England', 'code': 'GB', 'lat': 51.5549, 'lng': -0.1084},
        {'api_id': 49, 'name': 'Chelsea', 'city': 'London', 'country': 'England', 'code': 'GB', 'lat': 51.4817, 'lng': -0.1910},
        {'api_id': 50, 'name': 'Manchester City', 'city': 'Manchester', 'country': 'England', 'code': 'GB', 'lat': 53.4831, 'lng': -2.2004},
        {'api_id': 47, 'name': 'Tottenham', 'city': 'London', 'country': 'England', 'code': 'GB', 'lat': 51.6042, 'lng': -0.0662},
        {'api_id': 34, 'name': 'Newcastle', 'city': 'Newcastle', 'country': 'England', 'code': 'GB', 'lat': 54.9756, 'lng': -1.6217},
        {'api_id': 66, 'name': 'Aston Villa', 'city': 'Birmingham', 'country': 'England', 'code': 'GB', 'lat': 52.5092, 'lng': -1.8847},
        {'api_id': 48, 'name': 'West Ham', 'city': 'London', 'country': 'England', 'code': 'GB', 'lat': 51.5386, 'lng': -0.0166},
        {'api_id': 35, 'name': 'Brighton', 'city': 'Brighton', 'country': 'England', 'code': 'GB', 'lat': 50.8619, 'lng': -0.0839},
        {'api_id': 45, 'name': 'Everton', 'city': 'Liverpool', 'country': 'England', 'code': 'GB', 'lat': 53.4387, 'lng': -2.9664},
        {'api_id': 36, 'name': 'Fulham', 'city': 'London', 'country': 'England', 'code': 'GB', 'lat': 51.4750, 'lng': -0.2217},
        {'api_id': 52, 'name': 'Crystal Palace', 'city': 'London', 'country': 'England', 'code': 'GB', 'lat': 51.3983, 'lng': -0.0855},
        {'api_id': 55, 'name': 'Brentford', 'city': 'London', 'country': 'England', 'code': 'GB', 'lat': 51.4907, 'lng': -0.2886},
        {'api_id': 39, 'name': 'Wolves', 'city': 'Wolverhampton', 'country': 'England', 'code': 'GB', 'lat': 52.5903, 'lng': -2.1306},
        {'api_id': 65, 'name': 'Nottingham Forest', 'city': 'Nottingham', 'country': 'England', 'code': 'GB', 'lat': 52.9399, 'lng': -1.1328},
        {'api_id': 51, 'name': 'Bournemouth', 'city': 'Bournemouth', 'country': 'England', 'code': 'GB', 'lat': 50.7352, 'lng': -1.8383},
        {'api_id': 46, 'name': 'Leicester', 'city': 'Leicester', 'country': 'England', 'code': 'GB', 'lat': 52.6204, 'lng': -1.1421},
        {'api_id': 41, 'name': 'Southampton', 'city': 'Southampton', 'country': 'England', 'code': 'GB', 'lat': 50.9058, 'lng': -1.3910},
        {'api_id': 57, 'name': 'Ipswich', 'city': 'Ipswich', 'country': 'England', 'code': 'GB', 'lat': 52.0547, 'lng': 1.1447},
        
        # La Liga
        {'api_id': 541, 'name': 'Real Madrid', 'city': 'Madrid', 'country': 'Spain', 'code': 'ES', 'lat': 40.4531, 'lng': -3.6883},
        {'api_id': 529, 'name': 'Barcelona', 'city': 'Barcelona', 'country': 'Spain', 'code': 'ES', 'lat': 41.3809, 'lng': 2.1228},
        {'api_id': 530, 'name': 'Atletico Madrid', 'city': 'Madrid', 'country': 'Spain', 'code': 'ES', 'lat': 40.4362, 'lng': -3.5995},
        {'api_id': 536, 'name': 'Sevilla', 'city': 'Sevilla', 'country': 'Spain', 'code': 'ES', 'lat': 37.3840, 'lng': -5.9705},
        {'api_id': 532, 'name': 'Valencia', 'city': 'Valencia', 'country': 'Spain', 'code': 'ES', 'lat': 39.4747, 'lng': -0.3583},
        {'api_id': 533, 'name': 'Villarreal', 'city': 'Villarreal', 'country': 'Spain', 'code': 'ES', 'lat': 39.9441, 'lng': -0.1036},
        {'api_id': 548, 'name': 'Real Sociedad', 'city': 'San Sebastian', 'country': 'Spain', 'code': 'ES', 'lat': 43.3013, 'lng': -1.9737},
        {'api_id': 531, 'name': 'Athletic Bilbao', 'city': 'Bilbao', 'country': 'Spain', 'code': 'ES', 'lat': 43.2641, 'lng': -2.9494},
        {'api_id': 543, 'name': 'Real Betis', 'city': 'Sevilla', 'country': 'Spain', 'code': 'ES', 'lat': 37.3567, 'lng': -5.9817},
        
        # Serie A
        {'api_id': 489, 'name': 'AC Milan', 'city': 'Milan', 'country': 'Italy', 'code': 'IT', 'lat': 45.4781, 'lng': 9.1240},
        {'api_id': 505, 'name': 'Inter', 'city': 'Milan', 'country': 'Italy', 'code': 'IT', 'lat': 45.4781, 'lng': 9.1240},
        {'api_id': 496, 'name': 'Juventus', 'city': 'Turin', 'country': 'Italy', 'code': 'IT', 'lat': 45.1096, 'lng': 7.6413},
        {'api_id': 492, 'name': 'Napoli', 'city': 'Naples', 'country': 'Italy', 'code': 'IT', 'lat': 40.8280, 'lng': 14.1930},
        {'api_id': 487, 'name': 'Roma', 'city': 'Rome', 'country': 'Italy', 'code': 'IT', 'lat': 41.9341, 'lng': 12.4547},
        {'api_id': 488, 'name': 'Lazio', 'city': 'Rome', 'country': 'Italy', 'code': 'IT', 'lat': 41.9341, 'lng': 12.4547},
        {'api_id': 499, 'name': 'Atalanta', 'city': 'Bergamo', 'country': 'Italy', 'code': 'IT', 'lat': 45.7089, 'lng': 9.6808},
        {'api_id': 502, 'name': 'Fiorentina', 'city': 'Florence', 'country': 'Italy', 'code': 'IT', 'lat': 43.7810, 'lng': 11.2822},
        
        # Bundesliga
        {'api_id': 157, 'name': 'Bayern Munich', 'city': 'Munich', 'country': 'Germany', 'code': 'DE', 'lat': 48.2188, 'lng': 11.6247},
        {'api_id': 165, 'name': 'Borussia Dortmund', 'city': 'Dortmund', 'country': 'Germany', 'code': 'DE', 'lat': 51.4926, 'lng': 7.4519},
        {'api_id': 173, 'name': 'RB Leipzig', 'city': 'Leipzig', 'country': 'Germany', 'code': 'DE', 'lat': 51.3459, 'lng': 12.3483},
        {'api_id': 168, 'name': 'Bayer Leverkusen', 'city': 'Leverkusen', 'country': 'Germany', 'code': 'DE', 'lat': 51.0383, 'lng': 7.0022},
        {'api_id': 169, 'name': 'Eintracht Frankfurt', 'city': 'Frankfurt', 'country': 'Germany', 'code': 'DE', 'lat': 50.0686, 'lng': 8.6455},
        {'api_id': 172, 'name': 'VfB Stuttgart', 'city': 'Stuttgart', 'country': 'Germany', 'code': 'DE', 'lat': 48.7922, 'lng': 9.2320},
        
        # Ligue 1
        {'api_id': 85, 'name': 'Paris Saint Germain', 'city': 'Paris', 'country': 'France', 'code': 'FR', 'lat': 48.8414, 'lng': 2.2530},
        {'api_id': 91, 'name': 'Monaco', 'city': 'Monaco', 'country': 'Monaco', 'code': 'MC', 'lat': 43.7277, 'lng': 7.4156},
        {'api_id': 81, 'name': 'Marseille', 'city': 'Marseille', 'country': 'France', 'code': 'FR', 'lat': 43.2696, 'lng': 5.3958},
        {'api_id': 80, 'name': 'Lyon', 'city': 'Lyon', 'country': 'France', 'code': 'FR', 'lat': 45.7652, 'lng': 4.9822},
        {'api_id': 82, 'name': 'Lille', 'city': 'Lille', 'country': 'France', 'code': 'FR', 'lat': 50.6119, 'lng': 3.1305},
        
        # Other notable clubs
        {'api_id': 211, 'name': 'Benfica', 'city': 'Lisbon', 'country': 'Portugal', 'code': 'PT', 'lat': 38.7528, 'lng': -9.1847},
        {'api_id': 212, 'name': 'Porto', 'city': 'Porto', 'country': 'Portugal', 'code': 'PT', 'lat': 41.1618, 'lng': -8.5836},
        {'api_id': 194, 'name': 'Ajax', 'city': 'Amsterdam', 'country': 'Netherlands', 'code': 'NL', 'lat': 52.3142, 'lng': 4.9419},
        {'api_id': 197, 'name': 'PSV', 'city': 'Eindhoven', 'country': 'Netherlands', 'code': 'NL', 'lat': 51.4417, 'lng': 5.4675},
        {'api_id': 233, 'name': 'Sporting CP', 'city': 'Lisbon', 'country': 'Portugal', 'code': 'PT', 'lat': 38.7614, 'lng': -9.1608},
    ]
    
    added = 0
    for club in MAJOR_CLUBS:
        existing = ClubLocation.query.filter_by(club_api_id=club['api_id']).first()
        if not existing:
            location = ClubLocation(
                club_api_id=club['api_id'],
                club_name=club['name'],
                city=club['city'],
                country=club['country'],
                country_code=club['code'],
                latitude=club['lat'],
                longitude=club['lng'],
                geocode_source='manual',
                geocode_confidence=1.0,
            )
            db.session.add(location)
            added += 1
    
    db.session.commit()
    logger.info(f"Seeded {added} club locations")
    return added
