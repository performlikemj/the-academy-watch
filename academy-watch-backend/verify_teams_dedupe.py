import sys
import os
from datetime import datetime, timezone

# Mock objects

# Mock objects
class MockTeam:
    def __init__(self, id, team_id, name, season):
        self.id = id
        self.team_id = team_id
        self.name = name
        self.season = season

    def __repr__(self):
        return f"<Team {self.name} ({self.season})>"

def test_deduplication():
    print("🧪 Testing Team Deduplication Logic...")

    # Simulate database results with duplicates
    teams = [
        MockTeam(1, 33, "Manchester United", 2023),
        MockTeam(2, 33, "Manchester United", 2024), # Newer season
        MockTeam(3, 50, "Manchester City", 2023),
        MockTeam(4, 50, "Manchester City", 2024),   # Newer season
        MockTeam(5, 40, "Liverpool", 2024),         # Single entry
    ]

    print(f"📥 Input teams: {len(teams)}")
    for t in teams:
        print(f"  - {t.name} (ID: {t.team_id}, Season: {t.season})")

    # Apply deduplication logic (copied from api.py)
    deduped_teams = {}
    for team in teams:
        existing = deduped_teams.get(team.team_id)
        if not existing or team.season > existing.season:
            deduped_teams[team.team_id] = team
    
    final_teams = list(deduped_teams.values())
    final_teams.sort(key=lambda x: x.name)

    print(f"\n📤 Output teams: {len(final_teams)}")
    for t in final_teams:
        print(f"  - {t.name} (ID: {t.team_id}, Season: {t.season})")

    # Assertions
    assert len(final_teams) == 3, f"Expected 3 unique teams, got {len(final_teams)}"
    
    man_utd = next(t for t in final_teams if t.team_id == 33)
    assert man_utd.season == 2024, f"Expected Man Utd season 2024, got {man_utd.season}"
    
    man_city = next(t for t in final_teams if t.team_id == 50)
    assert man_city.season == 2024, f"Expected Man City season 2024, got {man_city.season}"

    print("\n✅ Deduplication logic verified successfully!")

if __name__ == "__main__":
    test_deduplication()
