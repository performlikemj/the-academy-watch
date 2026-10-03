#!/usr/bin/env python3
"""
Test script to debug stat extraction and aggregation.
Run with: source ../.venv/bin/activate && python test_stats_debug.py
"""

import json
import os
from datetime import date

from src.api_football_client import APIFootballClient
from src.main import app
from src.utils.log_privacy import log_metadata

with app.app_context():
    # Create API client instance
    api_key = os.getenv("API_FOOTBALL_KEY")
    api_client = APIFootballClient(api_key=api_key)
    api_client.set_season_year(2025)

    # Test with Marcus Rashford at Barcelona (from newsletter)
    print("🔍 Testing Marcus Rashford (ID: 909) at Barcelona (ID: 529)")
    print("📅 Week: Oct 13-19, 2025")
    print(log_metadata("=" * 80))
    print()

    result = api_client.summarize_loanee_week(
        player_id=909,
        loan_team_id=529,
        season=2025,
        week_start=date(2025, 10, 13),
        week_end=date(2025, 10, 19),
        include_team_stats=False,
    )

    print()
    print(log_metadata("=" * 80))
    print("📊 FINAL TOTALS:")
    print(log_metadata("=" * 80))
    totals = result["totals"]
    print(f"Minutes: {log_metadata(totals['minutes'])}")
    print(f"Goals: {log_metadata(totals['goals'])}, Assists: {log_metadata(totals['assists'])}")
    print(f"Position: {log_metadata(totals['position'])}, Rating: {log_metadata(totals['rating'])}")
    print()
    print(f"Shots total: {log_metadata(totals['shots_total'])}, on target: {log_metadata(totals['shots_on'])}")
    print(f"Passes total: {log_metadata(totals['passes_total'])}, key: {log_metadata(totals['passes_key'])}")
    print(
        f"Tackles total: {log_metadata(totals['tackles_total'])}, interceptions: {log_metadata(totals['tackles_interceptions'])}"
    )
    print(f"Duels total: {log_metadata(totals['duels_total'])}, won: {log_metadata(totals['duels_won'])}")
    print()
    print("Full totals JSON:")
    print(json.dumps(log_metadata(totals), indent=2))
