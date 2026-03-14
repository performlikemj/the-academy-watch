import pytest
from datetime import date
from unittest.mock import MagicMock
from src.models.league import db, Team, NewsletterCommentary
import src.agents.weekly_newsletter_agent as agent
import json

def test_compose_newsletter_with_writeups(app, monkeypatch):
    # Setup DB
    team = Team(team_id=1, name="Test Team", logo="logo.png", country="England", season=2025)
    db.session.add(team)
    db.session.commit()

    week_start = date(2025, 11, 3)
    week_end = date(2025, 11, 9)

    # Add commentaries
    c1 = NewsletterCommentary(
        team_id=team.id,
        author_id=1,
        author_name="Scout 1",
        commentary_type="intro",
        content="<p>Intro content</p>",
        week_start_date=week_start,
        week_end_date=week_end,
        is_active=True,
        position=0
    )
    c2 = NewsletterCommentary(
        team_id=team.id,
        author_id=1,
        author_name="Scout 1",
        commentary_type="summary",
        content="<p>Summary content</p>",
        week_start_date=week_start,
        week_end_date=week_end,
        is_active=True,
        position=0
    )
    c3 = NewsletterCommentary(
        team_id=team.id,
        author_id=1,
        author_name="Scout 1",
        commentary_type="player",
        player_id=123,
        content="<p>Player content</p>",
        week_start_date=week_start,
        week_end_date=week_end,
        is_active=True,
        position=0
    )
    db.session.add_all([c1, c2, c3])
    db.session.commit()

    # Mock fetch_weekly_report_tool
    mock_report = {
        "parent_team": {"name": "Test Team"},
        "season": 2025,
        "range": [week_start.isoformat(), week_end.isoformat()],
        "loanees": [
            {
                "player_id": 123,
                "player_name": "Test Player",
                "loan_team": "Loan Team",
                "can_fetch_stats": True,
                "totals": {"minutes": 90},
                "matches": []
            }
        ]
    }
    monkeypatch.setattr(agent, "fetch_weekly_report_tool", lambda *args: mock_report)
    
    # Mock brave context to avoid network calls
    monkeypatch.setattr(agent, "brave_context_for_team_and_loans", lambda *args, **kwargs: {})
    
    # Mock LLM to avoid calls
    monkeypatch.setattr(agent, "ENV_ENABLE_GROQ_SUMMARIES", False)

    # Mock api_client methods called
    monkeypatch.setattr(agent.api_client, "clear_stats_cache", lambda *args: None)
    monkeypatch.setattr(agent.api_client, "set_season_year", lambda *args: None)
    monkeypatch.setattr(agent.api_client, "_prime_team_cache", lambda *args: None)

    # Call compose
    # Use a date within the week
    target_date = date(2025, 11, 5)
    
    # Ensure _monday_range returns the expected week
    # 2025-11-03 is a Monday.
    # If agent._monday_range is correct, passing 2025-11-05 (Wednesday) should return (2025-11-03, 2025-11-09)
    
    result = agent.compose_team_weekly_newsletter(team.id, target_date)
    
    content = json.loads(result["content_json"])
    
    # Assertions
    assert "intro_commentary" in content
    assert len(content["intro_commentary"]) == 1
    assert content["intro_commentary"][0]["content"] == "<p>Intro content</p>"
    
    assert "summary_commentary" in content
    assert len(content["summary_commentary"]) == 1
    assert content["summary_commentary"][0]["content"] == "<p>Summary content</p>"
    
    assert "player_commentary_map" in content
    # JSON keys are strings, so "123"
    assert "123" in content["player_commentary_map"]
    assert content["player_commentary_map"]["123"][0]["content"] == "<p>Player content</p>"
    
    # Assert Internet section is gone
    section_titles = [s["title"] for s in content["sections"]]
    assert "What the Internet is Saying" not in section_titles
