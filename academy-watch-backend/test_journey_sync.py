#!/usr/bin/env python3
"""
Test script for journey sync service.
Run from loan-army-backend directory with API key:
    API_FOOTBALL_KEY=xxx python test_journey_sync.py
"""

import os
import sys
sys.path.insert(0, os.path.dirname(__file__))

# Try to load dotenv if available, otherwise skip
try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv())
except ImportError:
    pass  # dotenv not available, rely on env vars

from src.api_football_client import APIFootballClient
from src.services.journey_sync import JourneySyncService

def test_api_connection():
    """Test that API connection works"""
    print("Testing API connection...")
    client = APIFootballClient()
    print(f"✅ API connected, mode: {client.mode}")
    return client

def test_get_player_seasons(client, player_id=284324):
    """Test getting player seasons"""
    print(f"\nTesting get player seasons for player {player_id} (Garnacho)...")
    
    response = client._make_request('players/seasons', {'player': player_id})
    seasons = response.get('response', [])
    
    print(f"✅ Found {len(seasons)} seasons: {seasons}")
    return seasons

def test_get_player_season_data(client, player_id=284324, season=2021):
    """Test getting player data for a season"""
    print(f"\nTesting get player data for season {season}...")
    
    response = client._make_request('players', {'id': player_id, 'season': season})
    data = response.get('response', [])
    
    if data:
        player_data = data[0]
        player = player_data.get('player', {})
        stats = player_data.get('statistics', [])
        
        print(f"✅ Player: {player.get('name')}")
        print(f"   Stats entries: {len(stats)}")
        
        for stat in stats:
            team = stat.get('team', {}).get('name', 'Unknown')
            league = stat.get('league', {}).get('name', 'Unknown')
            apps = stat.get('games', {}).get('appearences', 0)
            goals = stat.get('goals', {}).get('total', 0)
            print(f"   - {team} | {league} | {apps} apps | {goals} goals")
        
        return player_data
    else:
        print("❌ No data found")
        return None

def test_classification(service):
    """Test level classification"""
    print("\nTesting level classification...")
    
    test_cases = [
        ("Manchester United U18", "FA Youth Cup", "U18"),
        ("Manchester United U21", "Premier League 2 Division One", "U23"),  # PL2 = U23 level
        ("Manchester United", "Premier League", "First Team"),
        ("Argentina", "World Cup - Qualification South America", "International"),
        ("Argentina U20", "Tournoi Maurice Revello", "International Youth"),
    ]
    
    for team, league, expected in test_cases:
        result = service._classify_level(team, league)
        status = "✅" if result == expected else "❌"
        print(f"   {status} {team} / {league} → {result} (expected: {expected})")

def main():
    print("=" * 60)
    print("Journey Sync Service Test")
    print("=" * 60)
    
    # Test API
    client = test_api_connection()
    
    # Test getting seasons
    seasons = test_get_player_seasons(client)
    
    # Test getting season data
    if seasons:
        # Get an early season to see academy data
        test_season = min(seasons) if seasons else 2021
        test_get_player_season_data(client, season=test_season)
    
    # Test classification
    service = JourneySyncService(client)
    test_classification(service)
    
    print("\n" + "=" * 60)
    print("All tests completed!")
    print("=" * 60)

if __name__ == '__main__':
    main()
