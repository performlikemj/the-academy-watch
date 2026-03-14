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
