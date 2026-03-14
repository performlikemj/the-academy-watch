"""
Player Journey Models

Tracks a player's complete career journey from academy through first team,
including all clubs, levels, and statistics.
"""

from datetime import datetime, timezone
from sqlalchemy.dialects.postgresql import JSONB
from src.models.league import db


class PlayerJourney(db.Model):
    """Master record for a player's career journey"""
    __tablename__ = 'player_journeys'
    
    id = db.Column(db.Integer, primary_key=True)
    player_api_id = db.Column(db.Integer, nullable=False, unique=True, index=True)
    player_name = db.Column(db.String(200))
    player_photo = db.Column(db.String(500))
    
    # Birth info (for age calculations)
    birth_date = db.Column(db.String(20))  # YYYY-MM-DD
    birth_country = db.Column(db.String(100))
    nationality = db.Column(db.String(100))
    
    # Origin (first club in journey)
    origin_club_api_id = db.Column(db.Integer)
    origin_club_name = db.Column(db.String(200))
    origin_year = db.Column(db.Integer)
    
    # Current status
    current_club_api_id = db.Column(db.Integer)
    current_club_name = db.Column(db.String(200))
    current_level = db.Column(db.String(30))  # 'U18', 'U21', 'First Team', 'On Loan'
    
    # First team debut milestone
    first_team_debut_season = db.Column(db.Integer)  # e.g., 2021
    first_team_debut_club_id = db.Column(db.Integer)
    first_team_debut_club = db.Column(db.String(200))
    first_team_debut_competition = db.Column(db.String(200))
    
    # Career aggregates
    total_clubs = db.Column(db.Integer, default=0)
    total_first_team_apps = db.Column(db.Integer, default=0)
    total_youth_apps = db.Column(db.Integer, default=0)
    total_loan_apps = db.Column(db.Integer, default=0)
    total_goals = db.Column(db.Integer, default=0)
    total_assists = db.Column(db.Integer, default=0)
    
    # Academy connections (derived from is_youth entries)
    academy_club_ids = db.Column(JSONB, default=list)  # [33, 62] = parent API IDs

    # Sync tracking
    seasons_synced = db.Column(db.JSON)  # [2019, 2020, 2021, ...]
    last_synced_at = db.Column(db.DateTime)
    sync_error = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), 
                          onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationships
    entries = db.relationship('PlayerJourneyEntry', backref='journey', lazy='dynamic',
                              order_by='desc(PlayerJourneyEntry.season), desc(PlayerJourneyEntry.sort_priority)',
                              cascade='all, delete-orphan')
    
    def to_dict(self, include_entries=False):
        """Convert to dictionary for API response"""
        data = {
            'id': self.id,
            'player_api_id': self.player_api_id,
            'player_name': self.player_name,
            'player_photo': self.player_photo,
            'birth_date': self.birth_date,
            'birth_country': self.birth_country,
            'nationality': self.nationality,
            'origin': {
                'club_id': self.origin_club_api_id,
                'club_name': self.origin_club_name,
                'year': self.origin_year,
            } if self.origin_club_api_id else None,
            'current': {
                'club_id': self.current_club_api_id,
                'club_name': self.current_club_name,
                'level': self.current_level,
            } if self.current_club_api_id else None,
            'first_team_debut': {
                'season': self.first_team_debut_season,
                'club_id': self.first_team_debut_club_id,
                'club': self.first_team_debut_club,
                'competition': self.first_team_debut_competition,
            } if self.first_team_debut_season else None,
            'totals': {
                'clubs': self.total_clubs,
                'first_team_apps': self.total_first_team_apps,
                'youth_apps': self.total_youth_apps,
                'loan_apps': self.total_loan_apps,
                'goals': self.total_goals,
                'assists': self.total_assists,
            },
            'academy_club_ids': self.academy_club_ids or [],
            'seasons_synced': self.seasons_synced,
            'last_synced_at': self.last_synced_at.isoformat() if self.last_synced_at else None,
            'sync_error': self.sync_error,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
        
        if include_entries:
            data['entries'] = [e.to_dict() for e in self.entries.all()]
        
        return data
    
    def to_map_dict(self):
        """Convert to map-optimized format (grouped by club)"""
        entries = self.entries.all()
        
        # Group entries by club
        clubs_map = {}
        for entry in entries:
            club_id = entry.club_api_id
            if club_id not in clubs_map:
                clubs_map[club_id] = {
                    'club_id': club_id,
                    'club_name': entry.club_name,
                    'club_logo': entry.club_logo,
                    'seasons': [],
                    'levels': set(),
                    'entry_types': set(),
                    'total_apps': 0,
                    'total_goals': 0,
                    'total_assists': 0,
                    'breakdown': {},
                    'competitions': [],
                }
            
            club = clubs_map[club_id]
            club['seasons'].append(entry.season)
            club['levels'].add(entry.level)
            club['entry_types'].add(entry.entry_type)
            club['total_apps'] += entry.appearances or 0
            club['total_goals'] += entry.goals or 0
            club['total_assists'] += entry.assists or 0
            # Track latest transfer date for sorting tiebreaker
            td = getattr(entry, 'transfer_date', None) or ''
            if td > club.get('_max_transfer_date', ''):
                club['_max_transfer_date'] = td
            
            # Add to level breakdown
            level = entry.level
            if level not in club['breakdown']:
                club['breakdown'][level] = {'apps': 0, 'goals': 0, 'assists': 0}
            club['breakdown'][level]['apps'] += entry.appearances or 0
            club['breakdown'][level]['goals'] += entry.goals or 0
            club['breakdown'][level]['assists'] += entry.assists or 0
            
            # Add competition detail
            club['competitions'].append({
                'season': entry.season,
                'league': entry.league_name,
                'apps': entry.appearances,
                'goals': entry.goals,
                'assists': entry.assists,
            })
        
        # Convert to list and format
        stops = []
        for club in clubs_map.values():
            seasons = sorted(club['seasons'])
            if len(seasons) == 1:
                years = str(seasons[0])
            else:
                years = f"{seasons[0]}-{seasons[-1]}"
            
            stops.append({
                'club_id': club['club_id'],
                'club_name': club['club_name'],
                'club_logo': club['club_logo'],
                'years': years,
                'levels': sorted(list(club['levels']), key=lambda x: LEVEL_PRIORITY.get(x, 0), reverse=True),
                'entry_types': sorted(club['entry_types']),
                'total_apps': club['total_apps'],
                'total_goals': club['total_goals'],
                'total_assists': club['total_assists'],
                'breakdown': club['breakdown'],
                'competitions': sorted(club['competitions'], key=lambda x: x['season'], reverse=True),
            })
        
        # Sort by:
        #  1. Earliest season
        #  2. Integration stops last within the same year (player arrived
        #     from another club, so the previous club's stop comes first)
        #  3. Level priority — youth before senior so academy progression
        #     reads as promotion not demotion
        #  4. Latest transfer date (most recent club within same season
        #     comes last → "Current" badge)
        stops.sort(key=lambda x: (
            int(x['years'].split('-')[0]),
            1 if 'integration' in x.get('entry_types', []) else 0,
            max(LEVEL_PRIORITY.get(l, 0) for l in x.get('levels', ['First Team'])),
            x.get('_max_transfer_date', ''),
        ))

        # Remove internal sort key from API response
        for stop in stops:
            stop.pop('_max_transfer_date', None)

        return {
            'player_api_id': self.player_api_id,
            'player_name': self.player_name,
            'player_photo': self.player_photo,
            'stops': stops,
        }


class PlayerJourneyEntry(db.Model):
    """Individual season/club/competition entry in a player's journey"""
    __tablename__ = 'player_journey_entries'
    
    id = db.Column(db.Integer, primary_key=True)
    journey_id = db.Column(db.Integer, db.ForeignKey('player_journeys.id'), nullable=False, index=True)
    
    # Season
    season = db.Column(db.Integer, nullable=False)  # e.g., 2021
    
    # Club info
    club_api_id = db.Column(db.Integer, nullable=False)
    club_name = db.Column(db.String(200))
    club_logo = db.Column(db.String(500))
    
    # League/Competition info
    league_api_id = db.Column(db.Integer)
    league_name = db.Column(db.String(200))
    league_country = db.Column(db.String(100))
    league_logo = db.Column(db.String(500))
    
    # Classification
    level = db.Column(db.String(30))  # 'U18', 'U19', 'U21', 'U23', 'Reserve', 'First Team'
    entry_type = db.Column(db.String(30))  # 'academy', 'first_team', 'loan', 'permanent', 'international'
    is_youth = db.Column(db.Boolean, default=False)
    is_international = db.Column(db.Boolean, default=False)
    is_first_team_debut = db.Column(db.Boolean, default=False)
    
    # Stats
    appearances = db.Column(db.Integer, default=0)
    goals = db.Column(db.Integer, default=0)
    assists = db.Column(db.Integer, default=0)
    minutes = db.Column(db.Integer, default=0)
    
    # Transfer date (YYYY-MM-DD) — when the player moved to this club
    # Populated from transfer API for loan entries; used as tiebreaker
    # when multiple clubs share the same season and sort_priority.
    transfer_date = db.Column(db.String(20))

    # Sorting priority (higher = more prominent display)
    sort_priority = db.Column(db.Integer, default=0)
    
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    __table_args__ = (
        db.Index('ix_journey_entry_lookup', 'journey_id', 'season', 'club_api_id', 'league_api_id'),
        db.UniqueConstraint('journey_id', 'season', 'club_api_id', 'league_api_id', 
                           name='uq_journey_entry'),
    )
    
    def to_dict(self):
        """Convert to dictionary for API response"""
        return {
            'id': self.id,
            'season': self.season,
            'club': {
                'id': self.club_api_id,
                'name': self.club_name,
                'logo': self.club_logo,
            },
            'league': {
                'id': self.league_api_id,
                'name': self.league_name,
                'country': self.league_country,
                'logo': self.league_logo,
            },
            'level': self.level,
            'entry_type': self.entry_type,
            'is_youth': self.is_youth,
            'is_international': self.is_international,
            'is_first_team_debut': self.is_first_team_debut,
            'stats': {
                'appearances': self.appearances,
                'goals': self.goals,
                'assists': self.assists,
                'minutes': self.minutes,
            },
        }


class ClubLocation(db.Model):
    """Geographic coordinates for clubs (for map visualization)"""
    __tablename__ = 'club_locations'
    
    id = db.Column(db.Integer, primary_key=True)
    club_api_id = db.Column(db.Integer, unique=True, nullable=False, index=True)
    club_name = db.Column(db.String(200))
    
    # Location
    city = db.Column(db.String(100))
    country = db.Column(db.String(100))
    country_code = db.Column(db.String(5))
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    
    # Source tracking
    geocode_source = db.Column(db.String(50))  # 'manual', 'mapbox', 'google', 'osm'
    geocode_confidence = db.Column(db.Float)  # 0-1
    
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                          onupdate=lambda: datetime.now(timezone.utc))
    
    def to_dict(self):
        """Convert to dictionary for API response"""
        return {
            'club_api_id': self.club_api_id,
            'club_name': self.club_name,
            'city': self.city,
            'country': self.country,
            'country_code': self.country_code,
            'lat': self.latitude,
            'lng': self.longitude,
            'geocode_source': self.geocode_source,
        }


def derive_journey_context(journey_id: int, current_status: str) -> str | None:
    """Derive a human-readable progression sentence from a player's journey.

    Returns a short sentence like "Promoted from U21 to first team this season"
    or None if no meaningful progression can be determined.
    """
    if not journey_id:
        return None

    journey = PlayerJourney.query.get(journey_id)
    if not journey:
        return None

    entries = journey.entries.all()
    if not entries:
        return None

    # Sort by season desc, then by sort_priority desc
    entries.sort(key=lambda e: (e.season, e.sort_priority or 0), reverse=True)

    # Get the most recent season
    latest_season = entries[0].season
    latest_entries = [e for e in entries if e.season == latest_season and not e.is_international]
    prior_entries = [e for e in entries if e.season < latest_season and not e.is_international]

    latest_types = {e.entry_type for e in latest_entries}
    latest_levels = {e.level for e in latest_entries}
    prior_types = {e.entry_type for e in prior_entries}
    prior_levels = {e.level for e in prior_entries}

    # Detect first team promotion from academy
    if current_status == 'first_team':
        if 'first_team' in latest_types and prior_types & {'academy', 'development'}:
            prior_youth = sorted(
                [e for e in prior_entries if e.is_youth],
                key=lambda e: e.season, reverse=True,
            )
            if prior_youth:
                return f"Promoted from {prior_youth[0].level or 'academy'} to first team this season"
        if 'first_team' in latest_types and 'loan' in prior_types:
            prior_loans = [e for e in prior_entries if e.entry_type == 'loan']
            if prior_loans:
                return f"Recalled from loan at {prior_loans[0].club_name} into the first team"

    # Detect first loan from academy
    if current_status == 'on_loan':
        prior_loan_count = len([e for e in prior_entries if e.entry_type == 'loan'])
        if prior_loan_count == 0 and prior_types & {'academy', 'development'}:
            return "Out on first senior loan after progressing through the academy"
        if prior_loan_count >= 1:
            prior_loans = sorted(
                [e for e in prior_entries if e.entry_type == 'loan'],
                key=lambda e: e.season, reverse=True,
            )
            return f"On loan spell #{prior_loan_count + 1} — previously at {prior_loans[0].club_name}"

    # Detect academy level progression (e.g. U18 → U21)
    if current_status == 'academy':
        if prior_levels and latest_levels:
            youth_order = ['U18', 'U19', 'U21', 'U23', 'Reserve']
            latest_highest = max(
                (youth_order.index(l) for l in latest_levels if l in youth_order),
                default=-1,
            )
            prior_highest = max(
                (youth_order.index(l) for l in prior_levels if l in youth_order),
                default=-1,
            )
            if latest_highest > prior_highest >= 0:
                return f"Progressed from {youth_order[prior_highest]} to {youth_order[latest_highest]} this season"

    return None


# Priority mapping for level sorting
LEVEL_PRIORITY = {
    'First Team': 100,
    'International': 90,
    'International Youth': 85,
    'U23': 50,
    'Reserve': 45,
    'U21': 40,
    'U19': 30,
    'U18': 20,
}

# Youth levels for classification
YOUTH_LEVELS = {'U18', 'U19', 'U21', 'U23', 'Reserve', 'International Youth'}
