"""add player journey tables

Revision ID: x2y3z4a5b6c7
Revises: w2x3y4z5a6b7
Create Date: 2026-02-05 15:40:00.000000

Creates tables for tracking player career journeys:
- player_journeys: Master record for each player's journey
- player_journey_entries: Individual season/club/competition entries
- club_locations: Geographic coordinates for map visualization
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'x2y3z4a5b6c7'
down_revision = 'w2x3y4z5a6b7'
branch_labels = None
depends_on = None


def upgrade():
    # Create player_journeys table
    op.create_table(
        'player_journeys',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('player_api_id', sa.Integer(), nullable=False),
        sa.Column('player_name', sa.String(length=200), nullable=True),
        sa.Column('player_photo', sa.String(length=500), nullable=True),
        sa.Column('birth_date', sa.String(length=20), nullable=True),
        sa.Column('birth_country', sa.String(length=100), nullable=True),
        sa.Column('nationality', sa.String(length=100), nullable=True),
        
        # Origin club
        sa.Column('origin_club_api_id', sa.Integer(), nullable=True),
        sa.Column('origin_club_name', sa.String(length=200), nullable=True),
        sa.Column('origin_year', sa.Integer(), nullable=True),
        
        # Current status
        sa.Column('current_club_api_id', sa.Integer(), nullable=True),
        sa.Column('current_club_name', sa.String(length=200), nullable=True),
        sa.Column('current_level', sa.String(length=30), nullable=True),
        
        # First team debut
        sa.Column('first_team_debut_season', sa.Integer(), nullable=True),
        sa.Column('first_team_debut_club_id', sa.Integer(), nullable=True),
        sa.Column('first_team_debut_club', sa.String(length=200), nullable=True),
        sa.Column('first_team_debut_competition', sa.String(length=200), nullable=True),
        
        # Aggregates
        sa.Column('total_clubs', sa.Integer(), default=0),
        sa.Column('total_first_team_apps', sa.Integer(), default=0),
        sa.Column('total_youth_apps', sa.Integer(), default=0),
        sa.Column('total_loan_apps', sa.Integer(), default=0),
        sa.Column('total_goals', sa.Integer(), default=0),
        sa.Column('total_assists', sa.Integer(), default=0),
        
        # Sync tracking
        sa.Column('seasons_synced', sa.JSON(), nullable=True),
        sa.Column('last_synced_at', sa.DateTime(), nullable=True),
        sa.Column('sync_error', sa.Text(), nullable=True),
        
        # Timestamps
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_player_journeys_player_api_id', 'player_journeys', ['player_api_id'], unique=True)
    
    # Create player_journey_entries table
    op.create_table(
        'player_journey_entries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('journey_id', sa.Integer(), nullable=False),
        sa.Column('season', sa.Integer(), nullable=False),
        
        # Club info
        sa.Column('club_api_id', sa.Integer(), nullable=False),
        sa.Column('club_name', sa.String(length=200), nullable=True),
        sa.Column('club_logo', sa.String(length=500), nullable=True),
        
        # League info
        sa.Column('league_api_id', sa.Integer(), nullable=True),
        sa.Column('league_name', sa.String(length=200), nullable=True),
        sa.Column('league_country', sa.String(length=100), nullable=True),
        sa.Column('league_logo', sa.String(length=500), nullable=True),
        
        # Classification
        sa.Column('level', sa.String(length=30), nullable=True),
        sa.Column('entry_type', sa.String(length=30), nullable=True),
        sa.Column('is_youth', sa.Boolean(), default=False),
        sa.Column('is_international', sa.Boolean(), default=False),
        sa.Column('is_first_team_debut', sa.Boolean(), default=False),
        
        # Stats
        sa.Column('appearances', sa.Integer(), default=0),
        sa.Column('goals', sa.Integer(), default=0),
        sa.Column('assists', sa.Integer(), default=0),
        sa.Column('minutes', sa.Integer(), default=0),
        
        # Sort priority
        sa.Column('sort_priority', sa.Integer(), default=0),
        
        # Timestamp
        sa.Column('created_at', sa.DateTime(), nullable=True),
        
        sa.ForeignKeyConstraint(['journey_id'], ['player_journeys.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_journey_entry_journey_id', 'player_journey_entries', ['journey_id'])
    op.create_index('ix_journey_entry_lookup', 'player_journey_entries', 
                    ['journey_id', 'season', 'club_api_id', 'league_api_id'])
    
    # Create club_locations table
    op.create_table(
        'club_locations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('club_api_id', sa.Integer(), nullable=False),
        sa.Column('club_name', sa.String(length=200), nullable=True),
        
        # Location
        sa.Column('city', sa.String(length=100), nullable=True),
        sa.Column('country', sa.String(length=100), nullable=True),
        sa.Column('country_code', sa.String(length=5), nullable=True),
        sa.Column('latitude', sa.Float(), nullable=True),
        sa.Column('longitude', sa.Float(), nullable=True),
        
        # Source tracking
        sa.Column('geocode_source', sa.String(length=50), nullable=True),
        sa.Column('geocode_confidence', sa.Float(), nullable=True),
        
        # Timestamps
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_club_locations_club_api_id', 'club_locations', ['club_api_id'], unique=True)


def downgrade():
    op.drop_index('ix_club_locations_club_api_id', table_name='club_locations')
    op.drop_table('club_locations')
    
    op.drop_index('ix_journey_entry_lookup', table_name='player_journey_entries')
    op.drop_index('ix_journey_entry_journey_id', table_name='player_journey_entries')
    op.drop_table('player_journey_entries')
    
    op.drop_index('ix_player_journeys_player_api_id', table_name='player_journeys')
    op.drop_table('player_journeys')
