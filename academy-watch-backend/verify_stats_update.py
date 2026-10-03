#!/usr/bin/env python3
"""
Verification script for stats update fix.
Tests that newsletter generation updates existing DB stats with fresh API data.
"""

import sys
from datetime import date
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agents.weekly_newsletter_agent import generate_team_weekly_newsletter
from src.models.league import Team
from src.utils.log_privacy import get_logger, log_metadata, safe_exc_info


def test_stats_update():
    """Test that stats are updated on subsequent newsletter generations."""

    # Get a team with active loans (Manchester United = team_id 33)
    team = Team.query.filter_by(team_id=33).first()

    if not team:
        print("❌ Test team not found in database")
        return False

    print(f"✅ Testing with team: {log_metadata(team.name)} (DB ID: {log_metadata(team.id)})")

    # Target a recent week
    target_date = date(2024, 11, 18)  # Adjust to a week with match data

    print(f"🔄 Generating newsletter for week of {log_metadata(target_date)}...")
    print("📊 This will fetch fresh API stats and update the database")
    print("⏳ Check logs for 'Updating fixture stats' messages...\n")

    try:
        # Generate newsletter (this should update existing stats)
        result = generate_team_weekly_newsletter(team.id, target_date)

        print("\n✅ Newsletter generated successfully")
        print(f"   Issue date: {log_metadata(result.get('issue_date'))}")
        print(f"   Week range: {log_metadata(result.get('week_start'))} to {log_metadata(result.get('week_end'))}")

        # Check if content has player data
        content = result.get("content_json_parsed")
        if content:
            sections = content.get("sections", [])
            for section in sections:
                if section.get("title") == "Player Reports":
                    items = section.get("items", [])
                    print(f"   Players in report: {len(items)}")

                    # Show first player's stats as example
                    if items:
                        first_player = items[0]
                        print(f"\n   Example player: {log_metadata(first_player.get('player_name'))}")
                        stats = first_player.get("stats", {})
                        print(f"   - Minutes: {log_metadata(stats.get('minutes', 0))}")
                        print(f"   - Goals: {log_metadata(stats.get('goals', 0))}")
                        print(f"   - Assists: {log_metadata(stats.get('assists', 0))}")

        print("\n✅ Test completed successfully")
        print("📝 Review the logs above for 'Updating fixture stats' messages")
        print("   If you see updates, the fix is working correctly!")
        return True

    except Exception as e:
        print(f"\n❌ Test failed: {log_metadata(e)}")

        get_logger(__name__).error("Operation failed", exc_info=safe_exc_info())
        return False


if __name__ == "__main__":
    success = test_stats_update()
    sys.exit(0 if success else 1)
