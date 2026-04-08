from datetime import date

import src.agents.weekly_newsletter_agent as agent


def test_multi_match_minutes_not_tied_to_single_score(monkeypatch):
    # Disable LLM to keep output deterministic
    monkeypatch.setattr(agent, "ENV_ENABLE_GROQ_SUMMARIES", False)

    loanee = {
        "player_name": "Marcus Rashford",
        "loan_team_name": "Barcelona",
        "can_fetch_stats": True,
        "totals": {"minutes": 171, "goals": 1, "assists": 0},
        "matches": [
            {
                "opponent": "Celta Vigo",
                "result": "W",
                "score": {"home": 2, "away": 4},
                "competition": "La Liga",
                "played": True,
            },
            {
                "opponent": "Athletic Club",
                "result": "D",
                "score": {"home": 1, "away": 1},
                "competition": "La Liga",
                "played": True,
            },
        ],
    }

    item = agent._build_player_report_item(
        loanee, hits=[], week_start=date(2025, 11, 3), week_end=date(2025, 11, 9)
    )
    summary = item["week_summary"].lower()

    assert "across 2 matches" in summary
    assert "in win" not in summary
    assert "{'home':" not in summary


def test_match_result_phrase_formats_dict_score():
    loanee = {
        "matches": [
            {
                "opponent": "Oxford United",
                "result": "W",
                "score": {"home": 2, "away": 1},
                "competition": "League One",
                "played": True,
            }
        ]
    }

    phrase = agent._match_result_phrase(loanee)

    assert phrase == "win 2-1 over Oxford United in League One"


def test_ensure_period_strips_trailing_comma():
    assert agent._ensure_period("concede a solitary goal,") == "concede a solitary goal."
    assert agent._ensure_period("suggesting a;") == "suggesting a."


def test_untracked_duplicate_dropped_when_tracked_exists():
    content = {
        "sections": [
            {
                "title": "Active Loans",
                "items": [
                    {
                        "player_id": 10,
                        "player_name": "Radek Vitek",
                        "can_fetch_stats": True,
                        "stats": {"minutes": 90},
                    },
                    {
                        "player_id": 10,
                        "player_name": "Radek Vitek",
                        "can_fetch_stats": False,
                        "stats": {},
                    },
                ],
            }
        ]
    }

    meta_by_pid = {10: {"can_fetch_stats": True}}
    meta_by_key = {"radekvitek": {"can_fetch_stats": True}}

    result = agent._enforce_loanee_metadata(content, meta_by_pid, meta_by_key)

    sections = result.get("sections", [])
    assert len(sections) == 1
    items = sections[0].get("items", [])
    assert len(items) == 1
    assert sections[0]["title"] == "Active Loans"


def test_upcoming_fixtures_carried_into_player_item(monkeypatch):
    # Disable LLM for deterministic output
    monkeypatch.setattr(agent, "ENV_ENABLE_GROQ_SUMMARIES", False)

    upcoming = [
        {
            "date": "2025-11-22T15:00:00Z",
            "opponent": "Lyon",
            "competition": "Ligue 1",
            "is_home": True,
        }
    ]

    loanee = {
        "player_name": "Hannibal Mejbri",
        "loan_team_name": "Marseille",
        "can_fetch_stats": True,
        "totals": {"minutes": 90, "goals": 0, "assists": 1},
        "matches": [],
        "upcoming_fixtures": upcoming,
    }

    item = agent._build_player_report_item(
        loanee, hits=[], week_start=date(2025, 11, 3), week_end=date(2025, 11, 9)
    )

    assert item.get("upcoming_fixtures") == upcoming


def test_llm_too_short_falls_back_to_template(monkeypatch):
    # Force LLM path but return an unusably short string
    monkeypatch.setattr(agent, "ENV_ENABLE_GROQ_SUMMARIES", True)
    monkeypatch.setattr(agent, "_summarize_player_with_groq", lambda *args, **kwargs: "H.")

    loanee = {
        "player_name": "Harry Amass",
        "loan_team_name": "Sheffield Wednesday",
        "can_fetch_stats": True,
        "totals": {
            "minutes": 90,
            "goals": 0,
            "assists": 0,
            "passes_total": 42,
            "tackles_total": 4,
            "duels_total": 22,
            "duels_won": 9,
            "rating": 6.3,
        },
        "matches": [
            {
                "opponent": "Sheffield Utd",
                "result": "L",
                "score": {"home": 0, "away": 3},
                "competition": "Championship",
                "played": True,
            }
        ],
        "season_context": {
            "season_stats": {"minutes": 630, "goals": 1, "assists": 0, "games_played": 7},
            "trends": {"duels_win_rate": 48.6},
        },
    }

    item = agent._build_player_report_item(
        loanee, hits=[], week_start=date(2025, 11, 17), week_end=date(2025, 11, 23)
    )

    summary = item["week_summary"]
    assert len(summary) > 40  # not just "H."
    assert "logged 90 minutes" in summary


def test_limited_coverage_minutes_estimation():
    """Players with goals/assists but minutes=0 (limited-coverage leagues) should
    show estimated minutes (45) rather than 0 in the newsletter."""
    import types
    from unittest.mock import MagicMock, patch
    from datetime import date as _date

    # Simulate a FixturePlayerStats row with 0 minutes but goals
    mock_row = MagicMock()
    mock_row.minutes = 0
    mock_row.goals = 1
    mock_row.assists = 0
    mock_row.yellows = 0
    mock_row.reds = 0
    mock_row.saves = 0
    mock_row.position = 'F'
    mock_row.rating = None
    mock_row.shots_total = None
    mock_row.shots_on = None
    mock_row.passes_total = None
    mock_row.passes_key = None
    mock_row.tackles_total = None
    mock_row.tackles_interceptions = None
    mock_row.duels_total = None
    mock_row.duels_won = None
    mock_row.dribbles_attempts = None
    mock_row.dribbles_success = None
    mock_row.fouls_drawn = None
    mock_row.fouls_committed = None
    mock_row.offsides = None

    mock_fixture = MagicMock()
    mock_fixture.home_team_api_id = 999
    mock_fixture.away_team_api_id = 1234
    mock_fixture.home_goals = 2
    mock_fixture.away_goals = 0
    mock_fixture.competition_name = 'National League'
    mock_fixture.date_utc = None

    mock_tp = MagicMock()
    mock_tp.player_api_id = 42
    mock_tp.player_name = 'Test Player'
    mock_tp.loan_club_api_id = 999

    player_dict = {}

    with patch('src.agents.weekly_newsletter_agent.db') as mock_db, \
         patch('src.agents.weekly_newsletter_agent.Team') as mock_team_model:
        # Set up query chain — the filter comparison needs to return a truthy mock
        mock_query = MagicMock()
        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [(mock_row, mock_fixture)]
        mock_db.session.query.return_value = mock_query
        # Make db.func.date(...) >= start return a MagicMock (truthy) so filter works
        mock_date_expr = MagicMock()
        mock_date_expr.__ge__ = MagicMock(return_value=True)
        mock_date_expr.__le__ = MagicMock(return_value=True)
        mock_db.func.date.return_value = mock_date_expr
        mock_db.or_ = MagicMock()

        mock_team_instance = MagicMock()
        mock_team_instance.name = 'Loan Club'
        mock_team_model.query.filter_by.return_value.first.return_value = mock_team_instance

        agent._enrich_on_loan_stats(
            player_dict, mock_tp,
            start=_date(2025, 4, 1),
            end=_date(2025, 4, 7),
            season=2024,
        )

    # Should have estimated 45 minutes due to limited coverage
    assert player_dict['totals']['minutes'] == 45, \
        f"Expected 45 estimated minutes, got {player_dict['totals']['minutes']}"
    assert player_dict['totals']['goals'] == 1
    # Match played flag should be True
    assert len(player_dict['matches']) == 1
    assert player_dict['matches'][0]['played'] is True
    # Result should be calculated (home team 999 = loan club, scored 2-0)
    assert player_dict['matches'][0]['result'] == 'W'
