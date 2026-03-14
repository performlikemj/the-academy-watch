#!/usr/bin/env python3
"""
Diagnostic script to check raw transfer data from API-Football.

Run from loan-army-backend directory:
    python scripts/check_transfers.py [team_id]

Default team_id is 33 (Manchester United)
"""
import os
import sys
import json
from datetime import date

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from dotenv import load_dotenv
load_dotenv()

from api_football_client import APIFootballClient, is_new_loan_transfer
from data.transfer_windows import WINDOWS


def check_transfers(team_id: int = 33):
    """Check raw transfers for a team and show January 2026 loans."""

    print(f"\n{'='*60}")
    print(f"🔍 Checking transfers for team ID: {team_id}")
    print(f"{'='*60}\n")

    client = APIFootballClient()

    # Disable team filter for this check
    client.enable_team_filter = False

    # Get raw transfers
    print("📡 Fetching transfers from API-Football...")
    transfers = client.get_team_transfers(team_id)

    if not transfers:
        print("❌ No transfer data returned from API")
        return

    print(f"✅ Found {len(transfers)} player transfer blocks\n")

    # Define the January 2026 window bounds
    winter_start = date(2025, 12, 1)
    winter_end = date(2026, 2, 1)

    print(f"📅 Looking for transfers in 2025-26 WINTER window: {winter_start} to {winter_end}\n")

    january_loans = []
    all_recent_transfers = []

    for player_block in transfers:
        player_info = player_block.get('player', {})
        player_id = player_info.get('id')
        player_name = player_info.get('name', 'Unknown')

        for t in player_block.get('transfers', []):
            transfer_type = t.get('type', '').lower()
            transfer_date_str = t.get('date', '')

            if not transfer_date_str:
                continue

            try:
                transfer_date = date.fromisoformat(transfer_date_str)
            except ValueError:
                continue

            # Check if within January window
            if winter_start <= transfer_date <= winter_end:
                teams = t.get('teams', {})
                out_team = teams.get('out', {})
                in_team = teams.get('in', {})

                transfer_info = {
                    'player_id': player_id,
                    'player_name': player_name,
                    'date': transfer_date_str,
                    'type': t.get('type', 'Unknown'),
                    'from_team': out_team.get('name', 'Unknown'),
                    'from_team_id': out_team.get('id'),
                    'to_team': in_team.get('name', 'Unknown'),
                    'to_team_id': in_team.get('id'),
                    'is_new_loan': is_new_loan_transfer(transfer_type)
                }

                all_recent_transfers.append(transfer_info)

                if is_new_loan_transfer(transfer_type):
                    january_loans.append(transfer_info)

    # Print results
    print(f"📋 All transfers in January 2026 window ({len(all_recent_transfers)}):")
    print("-" * 60)

    if not all_recent_transfers:
        print("   (none found)")
    else:
        for t in sorted(all_recent_transfers, key=lambda x: x['date']):
            loan_marker = "🔄 LOAN" if t['is_new_loan'] else ""
            print(f"   {t['date']} | {t['player_name']}")
            print(f"            | {t['from_team']} → {t['to_team']}")
            print(f"            | Type: '{t['type']}' {loan_marker}")
            print()

    print(f"\n{'='*60}")
    print(f"📊 SUMMARY: {len(january_loans)} new loans detected in January 2026 window")
    print(f"{'='*60}\n")

    if january_loans:
        print("✅ New loans found:")
        for loan in january_loans:
            print(f"   - {loan['player_name']} → {loan['to_team']} ({loan['date']})")
    else:
        print("⚠️  No new loans found in API-Football data for this window.")
        print("    This could mean:")
        print("    1. API-Football hasn't updated their transfer data yet")
        print("    2. No outgoing loans have been registered for this team")
        print("\n💡 Try checking the API-Football website directly:")
        print(f"    https://www.api-football.com/")


if __name__ == '__main__':
    team_id = int(sys.argv[1]) if len(sys.argv) > 1 else 33
    check_transfers(team_id)
