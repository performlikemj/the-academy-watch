"""
Tests for API client stat aggregation logic, specifically to prevent double-counting.
"""
import pytest
from unittest.mock import Mock, MagicMock
from datetime import date, datetime, timezone

from src.api_football_client import APIFootballClient
from src.models.weekly import Fixture, FixturePlayerStats
from src.models.league import db


def test_no_double_counting_when_lineup_has_stats():
    """
    Test that when lineup endpoint provides goals/assists, we don't add event data on top.
    This prevents the bug where Sancho's assist was double-counted.
    """
    client = APIFootballClient()
    
    # Mock the lineup endpoint response with stats already included
    mock_lineup_response = {
        "response": [{
            "startXI": [{
                "player": {
                    "id": 12345,
                    "minutes": 90,
                    "goals": {"total": 0, "assists": 1},  # Already has 1 assist from lineup
                    "cards": {"yellow": 0, "red": 0}
                }
            }]
        }]
    }
    
    # Mock the events endpoint with the same assist
    mock_events_response = {
        "response": [
            {
                "type": "Goal",
                "player": {"id": 67890},  # Different player scored
                "assist": {"id": 12345}   # Our player assisted
            }
        ]
    }
    
    # Mock the API methods
    client.get_fixture_lineups = Mock(return_value=mock_lineup_response)
    client.get_fixture_events = Mock(return_value=mock_events_response)
    
    # Get player stats
    result = client._get_player_stats_from_lineups_and_events(12345, 999)
    
    # Verify assists count is 1, not 2 (no double-counting)
    stats = result.get("statistics", [{}])[0]
    goals_block = stats.get("goals", {})
    assists = goals_block.get("assists", 0)
    
    assert assists == 1, f"Expected 1 assist (from lineup), got {assists}. Double-counting detected!"


def test_use_events_when_lineup_missing_stats():
    """
    Test that when lineup endpoint has no stats (0), we use events endpoint data.
    """
    client = APIFootballClient()
    
    # Mock the lineup endpoint response WITHOUT stats
    mock_lineup_response = {
        "response": [{
            "startXI": [{
                "player": {
                    "id": 12345,
                    "minutes": 90,
                    "goals": {"total": 0, "assists": 0},  # No stats in lineup
                    "cards": {"yellow": 0, "red": 0}
                }
            }]
        }]
    }
    
    # Mock the events endpoint with actual assist
    mock_events_response = {
        "response": [
            {
                "type": "Goal",
                "player": {"id": 67890},
                "assist": {"id": 12345}
            }
        ]
    }
    
    # Mock the API methods
    client.get_fixture_lineups = Mock(return_value=mock_lineup_response)
    client.get_fixture_events = Mock(return_value=mock_events_response)
    
    # Get player stats
    result = client._get_player_stats_from_lineups_and_events(12345, 999)
    
    # Verify assists count is 1 from events
    stats = result.get("statistics", [{}])[0]
    goals_block = stats.get("goals", {})
    assists = goals_block.get("assists", 0)
    
    assert assists == 1, f"Expected 1 assist (from events), got {assists}"


def test_no_double_counting_goals():
    """
    Test that goals are not double-counted either.
    """
    client = APIFootballClient()
    
    # Mock the lineup with 1 goal
    mock_lineup_response = {
        "response": [{
            "startXI": [{
                "player": {
                    "id": 12345,
                    "minutes": 90,
                    "goals": {"total": 1, "assists": 0},
                    "cards": {"yellow": 0, "red": 0}
                }
            }]
        }]
    }
    
    # Mock the events with the same goal
    mock_events_response = {
        "response": [
            {
                "type": "Goal",
                "player": {"id": 12345}  # Same player's goal
            }
        ]
    }
    
    # Mock the API methods
    client.get_fixture_lineups = Mock(return_value=mock_lineup_response)
    client.get_fixture_events = Mock(return_value=mock_events_response)
    
    # Get player stats
    result = client._get_player_stats_from_lineups_and_events(12345, 999)
    
    # Verify goals count is 1, not 2
    stats = result.get("statistics", [{}])[0]
    goals_block = stats.get("goals", {})
    goals = goals_block.get("total", 0)
    
    assert goals == 1, f"Expected 1 goal (from lineup), got {goals}. Double-counting detected!"


def test_cards_added_from_events_when_lineup_missing():
    """
    Test that cards can be added from events if lineup doesn't have them.
    Cards are often missing from lineup data.
    """
    client = APIFootballClient()
    
    # Mock the lineup without card data
    mock_lineup_response = {
        "response": [{
            "startXI": [{
                "player": {
                    "id": 12345,
                    "minutes": 90,
                    "goals": {"total": 0, "assists": 0},
                    "cards": {"yellow": 0, "red": 0}  # No cards in lineup
                }
            }]
        }]
    }
    
    # Mock the events with a yellow card
    mock_events_response = {
        "response": [
            {
                "type": "Card",
                "detail": "Yellow Card",
                "player": {"id": 12345}
            }
        ]
    }
    
    # Mock the API methods
    client.get_fixture_lineups = Mock(return_value=mock_lineup_response)
    client.get_fixture_events = Mock(return_value=mock_events_response)
    
    # Get player stats
    result = client._get_player_stats_from_lineups_and_events(12345, 999)
    
    # Verify yellow card is counted from events
    stats = result.get("statistics", [{}])[0]
    cards = stats.get("cards", {})
    yellows = cards.get("yellow", 0)
    
    assert yellows == 1, f"Expected 1 yellow card (from events), got {yellows}"


def test_get_player_season_context_includes_same_day_fixtures(app):
    client = APIFootballClient()
    fixture = Fixture(
        fixture_id_api=1390921,
        date_utc=datetime(2025, 11, 2, 17, 30, tzinfo=timezone.utc),
        season=2025,
        competition_name='La Liga',
        home_team_api_id=1,
        away_team_api_id=2,
    )
    db.session.add(fixture)
    db.session.flush()

    player_stats = FixturePlayerStats(
        fixture_id=fixture.id,
        player_api_id=909,
        team_api_id=60,
        minutes=74,
        goals=1,
        assists=0,
    )
    db.session.add(player_stats)
    db.session.commit()

    season_context = client.get_player_season_context(
        player_id=909,
        loan_team_id=60,
        season=2025,
        up_to_date=date(2025, 11, 2),
        db_session=db.session,
    )

    stats = season_context['season_stats']
    assert stats['games_played'] == 1, 'Fixture on the cutoff date should be included'
    assert stats['goals'] == 1
    recent = season_context['recent_form']
    assert recent and recent[0]['date'] == fixture.date_utc.isoformat()


def test_get_player_season_context_overlays_api_appearances(app, monkeypatch):
    """
    Ensure season_context uses API-Football season totals when they exceed DB totals.
    """
    client = APIFootballClient()

    # Minimal DB data: 1 match, 74 minutes
    fixture = Fixture(
        fixture_id_api=222,
        date_utc=datetime(2025, 9, 1, 17, 30, tzinfo=timezone.utc),
        season=2025,
        competition_name='Premier League',
        home_team_api_id=60,
        away_team_api_id=101,
    )
    db.session.add(fixture)
    db.session.flush()

    player_stats = FixturePlayerStats(
        fixture_id=fixture.id,
        player_api_id=909,
        team_api_id=60,
        minutes=74,
        goals=1,
        assists=0,
    )
    db.session.add(player_stats)
    db.session.commit()

    # API shows 12 appearances and 800 minutes for the loan club in the season
    mock_api_response = {
        "response": [
            {
                "player": {"id": 909},
                "statistics": [
                    {
                        "team": {"id": 60},
                        "league": {"id": 39, "season": 2025},
                        "games": {"appearences": 12, "minutes": 800},
                        "goals": {"total": 3, "assists": 2},
                    }
                ],
            }
        ]
    }
    monkeypatch.setattr(client, "_make_request", Mock(return_value=mock_api_response))

    season_context = client.get_player_season_context(
        player_id=909,
        loan_team_id=60,
        season=2025,
        up_to_date=date(2025, 11, 2),
        db_session=db.session,
    )

    stats = season_context['season_stats']
    assert stats['games_played'] == 12, "API appearances should override DB total"
    assert stats['minutes'] == 800, "API minutes should override DB total"
    # Goals/assists also upgraded from API totals
    assert stats['goals'] == 3
    assert stats['assists'] == 2
