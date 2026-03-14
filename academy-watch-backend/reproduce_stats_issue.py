import os
import sys
import logging
from datetime import date

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add src to path
sys.path.append(os.getcwd())

# Load env vars
from dotenv import load_dotenv
load_dotenv()

from src.api_football_client import APIFootballClient

def main():
    try:
        client = APIFootballClient()
    except Exception as e:
        print(f"Failed to init client: {e}")
        return

    print(f"API Key present: {bool(client.api_key)}")
    print(f"Groq Key present: {bool(os.getenv('GROQ_API_KEY'))}")
    print(f"Brave Key present: {bool(os.getenv('BRAVE_API_KEY'))}")

    # 1. Get a National League team (ID 42)
    print("Fetching National League teams...")
    # National League ID is 42. Using 2023 season.
    teams = client.get_league_teams(42, 2023) 
    
    if not teams:
        print("No teams found for National League.")
        return

    # Pick a team, e.g., Barnet
    target_team = None
    for t in teams:
        if 'Barnet' in t['team']['name']:
            target_team = t['team']
            break
    
    if not target_team:
        target_team = teams[0]['team']
        print(f"Barnet not found, using {target_team['name']}")
    else:
        print(f"Found team: {target_team['name']} (ID: {target_team['id']})")

    # 2. Get fixtures for this team
    print(f"Fetching fixtures for {target_team['name']}...")
    fixtures = client.get_fixtures_for_team(target_team['id'], 2023, "2023-08-01", "2023-09-01")
    
    if not fixtures:
        print("No fixtures found.")
        return

    fixture = fixtures[0]
    fixture_id = fixture['fixture']['id']
    print(f"Checking fixture: {fixture['fixture']['date']} vs {fixture['teams']['away']['name']} (ID: {fixture_id})")

    # 3. Check /fixtures/players endpoint directly (should be empty/sparse)
    print("Fetching raw /fixtures/players response...")
    players_response = client.get_fixture_players(fixture_id)
    
    if not players_response:
        print("❌ No player stats returned from /fixtures/players endpoint (Expected for this league).")
        
        # 4. Try to find a player and use the fallback (which should now trigger external search)
        print("\nAttempting fallback via lineups + external search...")
        lineups = client._make_request('fixtures/lineups', {'fixture': fixture_id})
        if lineups.get('response'):
            start_xi = lineups['response'][0]['startXI']
            if start_xi:
                player = start_xi[0]['player']
                print(f"Found player in lineup: {player['name']} (ID: {player['id']})")
                
                # Pass fixture object to enable external search context
                print(f"Calling get_player_stats_for_fixture for {player['name']}...")
                stats = client.get_player_stats_for_fixture(player['id'], 2023, fixture_id, fixture_obj=fixture)
                
                print("Stats returned:")
                print(stats)
                
                # Check if we have detailed stats
                if stats and stats.get('statistics'):
                    s = stats['statistics'][0]
                    shots = s.get('shots', {}).get('total')
                    rating = s.get('rating')
                    print(f"\nDetailed Stats Check:")
                    print(f"  Shots: {shots}")
                    print(f"  Rating: {rating}")
                    
                    if shots is not None or rating is not None:
                        print("✅ SUCCESS: Detailed stats found (likely via external search)!")
                    else:
                        print("⚠️ WARNING: Still no detailed stats. External search might have failed or found nothing.")
                else:
                    print("❌ No stats returned.")
            else:
                print("No startXI found in lineups.")
        else:
            print("No lineups found.")
            
    else:
        print("✅ Player stats FOUND in /fixtures/players endpoint! (Unexpected but good)")
        print("   Sample data:", players_response[0]['players'][0]['statistics'][0])

if __name__ == "__main__":
    main()
