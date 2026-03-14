#!/usr/bin/env python3
"""
Test script to debug stat extraction and aggregation.
Run with: source ../.venv/bin/activate && python test_stats_debug.py
"""
from src.main import app
from src.api_football_client import APIFootballClient
from datetime import date
import json
import os

with app.app_context():
    # Create API client instance
    api_key = os.getenv('API_FOOTBALL_KEY')
    api_client = APIFootballClient(api_key=api_key)
    api_client.set_season_year(2025)
    
    # Test with Marcus Rashford at Barcelona (from newsletter)
    print('🔍 Testing Marcus Rashford (ID: 909) at Barcelona (ID: 529)')
    print('📅 Week: Oct 13-19, 2025')
    print('=' * 80)
    print()
    
    result = api_client.summarize_loanee_week(
        player_id=909,
        loan_team_id=529,
        season=2025,
        week_start=date(2025, 10, 13),
        week_end=date(2025, 10, 19),
        include_team_stats=False
    )
    
    print()
    print('=' * 80)
    print('📊 FINAL TOTALS:')
    print('=' * 80)
    totals = result['totals']
    print(f"Minutes: {totals['minutes']}")
    print(f"Goals: {totals['goals']}, Assists: {totals['assists']}")
    print(f"Position: {totals['position']}, Rating: {totals['rating']}")
    print()
    print(f"Shots total: {totals['shots_total']}, on target: {totals['shots_on']}")
    print(f"Passes total: {totals['passes_total']}, key: {totals['passes_key']}")
    print(f"Tackles total: {totals['tackles_total']}, interceptions: {totals['tackles_interceptions']}")
    print(f"Duels total: {totals['duels_total']}, won: {totals['duels_won']}")
    print()
    print('Full totals JSON:')
    print(json.dumps(totals, indent=2))

