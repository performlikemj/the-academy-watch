import os
import sys
import pytest
from types import SimpleNamespace

from src.agents.weekly_agent import lint_and_enrich, _display_name, _render_variants, _canonicalize_name


@pytest.fixture(autouse=True)
def stub_api_client(monkeypatch):
    stub = SimpleNamespace()

    def default_get_player_by_id(player_id, season=None):
        return {"player": {"id": player_id, "photo": None}}

    def default_get_team_by_id(team_id, season=None):
        return {
            "team": {
                "id": team_id,
                "name": f"Team {team_id}",
                "logo": None,
                "code": None,
                "country": "",
                "founded": None,
                "national": False,
            },
            "venue": {},
        }

    stub.get_player_by_id = default_get_player_by_id
    stub.get_team_by_id = default_get_team_by_id
    monkeypatch.setattr("src.agents.weekly_agent.api_client", stub)
    monkeypatch.setattr("src.agents.weekly_agent._PLAYER_PHOTO_CACHE", {}, raising=False)
    monkeypatch.setattr("src.agents.weekly_agent._TEAM_LOGO_CACHE", {}, raising=False)
    return stub


def _fake_newsletter():
    return {
        "title": "Test",
        "range": ["2022-10-03", "2022-10-09"],
        "sections": [{
            "title": "Active Loans",
            "items": [
                {
                    "player_name": "\tCharlie Gerard Richard Wellens\n",
                    "loan_team": "Oldham",
                    "week_summary": "Used as substitute in two National League draws.",
                    "stats": {"minutes": 0, "goals": 0, "assists": 0, "yellows": 0, "reds": 0},
                    "match_notes": ["Came on in 2-2 draw"],
                    "links": []
                },
                {
                    "player_name": "\u00c1lvaro Fern\u00e1ndez",
                    "loan_team": "Preston",
                    "week_summary": "Started both matches, two assists.",
                    "stats": {"minutes": 180, "goals": 0, "assists": 2, "yellows": 1, "reds": 0},
                    "match_notes": ["Assist vs West Brom", "Assist at Norwich"],
                    "links": []
                },
                {
                    "player_name": "E. Galbraith",
                    "loan_team": "Salford City",
                    "week_summary": "Scored winner at Northampton.",
                    "stats": {"minutes": 90, "goals": 1, "assists": 0, "yellows": 0, "reds": 0},
                    "match_notes": ["1-0 away win"],
                    "links": []
                }
            ]
        }]
    }


def test_display_name_strips_middle_names():
    assert _display_name("Charlie Gerard Richard Wellens") == "C. Wellens"


def test_lint_rewrites_unused_substitute_and_builds_highlights():
    news = lint_and_enrich(_fake_newsletter())

    # Minutes==0 wording
    items = news["sections"][0]["items"]
    wellens = next(i for i in items if "Wellens" in i["player_name"])
    assert "Unused substitute" in wellens["week_summary"] or "unused substitute" in wellens["week_summary"].lower()
    assert any("Unused substitute" in n or "unused substitute" in n.lower() for n in wellens["match_notes"]) 

    # Highlights choose top performers (Fernandez should be first with 2A, 180')
    assert news["highlights"][0].startswith("Á. Fernández")

    # By-numbers present and sensible
    assert news["by_numbers"]["minutes_leaders"][0]["minutes"] == 180
    ga_agg = news["by_numbers"]["ga_leaders"][0]
    assert ga_agg["g"] + ga_agg["a"] >= 2



def test_render_variants_omits_stats_for_link_only_section():
    news = {
        "title": "Rendered",
        "range": ["2024-08-12", "2024-08-18"],
        "sections": [
            {
                "title": "Active Loans",
                "items": [
                    {
                        "player_name": "A. Example",
                        "loan_team": "Loan FC",
                        "week_summary": "Started and scored.",
                        "stats": {"minutes": 90, "goals": 1, "assists": 0, "yellows": 0, "reds": 0},
                        "match_notes": ["Opened the scoring."],
                        "links": ["https://example.com/match-report"],
                    }
                ],
            },
            {
                "title": "What the Internet is Saying",
                "items": [
                    {
                        "player_name": "J. Sancho",
                        "links": ["https://example.com/opinion"],
                    }
                ],
            },
        ],
    }

    variants = _render_variants(news, team_name="Manchester United")
    web_html = variants["web_html"]
    email_html = variants["email_html"]

    assert web_html.count('class="stats"') == 1
    assert email_html.count('class="stats"') == 1
    assert "J. Sancho" in web_html
    assert "J. Sancho" in email_html


def test_render_variants_shows_upcoming_fixtures_in_web_html():
    news = _fake_newsletter()
    first_item = news["sections"][0]["items"][0]
    first_item["upcoming_fixtures"] = [
        {
            "date": "2025-11-30T14:00:00+00:00",
            "opponent": "Rangers",
            "competition": "Premiership",
            "is_home": False,
        }
    ]

    variants = _render_variants(news, team_name="Manchester United")

    # Web HTML should render the Upcoming Fixtures block with opponent name and follow-up note
    assert "Upcoming Fixtures" in variants["web_html"]
    assert "Rangers" in variants["web_html"]
    assert "will be covered in next week's newsletter" in variants["web_html"]


def test_lint_and_enrich_populates_player_photos(stub_api_client):
    def fake_get_player_by_id(player_id, season=None):
        return {
            "player": {
                "id": player_id,
                "photo": f"https://media.example.com/players/{player_id}.png",
            }
        }

    stub_api_client.get_player_by_id = fake_get_player_by_id

    news = {
        "sections": [
            {
                "title": "Active Loans",
                "items": [
                    {
                        "player_id": 101,
                        "player_name": "A. Example",
                        "loan_team": "Loan FC",
                        "stats": {"minutes": 90, "goals": 0, "assists": 0, "yellows": 0, "reds": 0},
                    }
                ],
            }
        ]
    }

    enriched = lint_and_enrich(news)
    item = enriched["sections"][0]["items"][0]
    assert item["player_photo"] == "https://media.example.com/players/101.png"


def test_render_variants_renders_player_photos():
    news = {
        "title": "Rendered",
        "range": ["2024-08-12", "2024-08-18"],
        "sections": [
            {
                "title": "Active Loans",
                "items": [
                    {
                        "player_name": "A. Example",
                        "player_photo": "https://media.example.com/players/101.png",
                        "loan_team": "Loan FC",
                        "week_summary": "Started and scored.",
                        "stats": {"minutes": 90, "goals": 1, "assists": 0, "yellows": 0, "reds": 0},
                        "match_notes": ["Opened the scoring."],
                        "links": ["https://example.com/match-report"],
                    }
                ],
            }
        ],
    }

    variants = _render_variants(news, team_name="Manchester United")
    assert "https://media.example.com/players/101.png" in variants["web_html"]
    assert "https://media.example.com/players/101.png" in variants["email_html"]


def test_lint_and_enrich_persists_player_profile(app, stub_api_client):
    from src.models.league import db  # noqa: F401 (ensures model metadata is loaded)

    captured = {}

    def fake_get_player_by_id(player_id, season=None):
        captured['called'] = True
        return {
            "player": {
                "id": player_id,
                "name": "A. Example",
                "firstname": "Alice",
                "lastname": "Example",
                "nationality": "Exampleland",
                "age": 24,
                "photo": f"https://media.example.com/players/{player_id}.png",
                "height": "170 cm",
                "weight": "65 kg",
                "position": "Midfielder",
            }
        }

    stub_api_client.get_player_by_id = fake_get_player_by_id

    news = {
        "sections": [
            {
                "title": "Active Loans",
                "items": [
                    {
                        "player_id": 101,
                        "player_name": "A. Example",
                        "loan_team": "Loan FC",
                        "stats": {"minutes": 90, "goals": 0, "assists": 0, "yellows": 0, "reds": 0},
                    }
                ],
            }
        ]
    }

    lint_and_enrich(news)

    from src.models.league import Player  # noqa: E402

    stored = Player.query.filter_by(player_id=101).first()
    assert stored is not None
    assert stored.photo_url == "https://media.example.com/players/101.png"
    assert stored.name == "A. Example"


def test_lint_and_enrich_uses_cached_player_profile(app, stub_api_client):
    from src.models.league import db, Player  # noqa: E402

    player = Player(
        player_id=202,
        name="B. Example",
        firstname="Bob",
        lastname="Example",
        nationality="Exampleland",
        position="Defender",
        age=26,
        photo_url="https://media.example.com/players/202.png",
    )
    db.session.add(player)
    db.session.commit()

    def fail_get_player_by_id(*args, **kwargs):
        raise AssertionError("should use cached profile")

    stub_api_client.get_player_by_id = fail_get_player_by_id

    news = {
        "sections": [
            {
                "title": "Active Loans",
                "items": [
                    {
                        "player_id": 202,
                        "player_name": "B. Example",
                        "loan_team": "Loan FC",
                        "stats": {"minutes": 90, "goals": 0, "assists": 0, "yellows": 0, "reds": 0},
                    }
                ],
            }
        ]
    }

    enriched = lint_and_enrich(news)
    item = enriched["sections"][0]["items"][0]
    assert item["player_photo"] == "https://media.example.com/players/202.png"


def test_lint_and_enrich_persists_team_profile(app, stub_api_client):
    from src.models.league import db, Team, LoanedPlayer, TeamProfile

    parent_team = Team(team_id=1, name="Parent FC", country="England", season=2024, is_active=True)
    loan_team = Team(team_id=500, name="Loan FC", country="England", season=2024, is_active=True)
    db.session.add_all([parent_team, loan_team])
    db.session.commit()

    loaned = LoanedPlayer(
        player_id=303,
        player_name="C. Example",
        primary_team_id=parent_team.id,
        primary_team_name=parent_team.name,
        loan_team_id=loan_team.id,
        loan_team_name=loan_team.name,
        is_active=True,
        window_key="2024-25::FULL",
    )
    db.session.add(loaned)
    db.session.commit()

    def fake_get_team_by_id(team_id, season=None):
        return {
            "team": {
                "id": team_id,
                "name": "Loan FC",
                "code": "LFC",
                "country": "England",
                "founded": 1900,
                "national": False,
                "logo": f"https://media.example.com/teams/{team_id}.png",
            },
            "venue": {
                "id": 900,
                "name": "Loan Venue",
                "city": "Loan City",
                "capacity": 10000,
                "surface": "grass",
                "image": f"https://media.example.com/venues/900.png",
            },
        }

    stub_api_client.get_team_by_id = fake_get_team_by_id

    news = {
        "sections": [
            {
                "title": "Active Loans",
                "items": [
                    {
                        "player_id": 303,
                        "player_name": "C. Example",
                        "loan_team": "Loan FC",
                        "stats": {"minutes": 90, "goals": 0, "assists": 0, "yellows": 0, "reds": 0},
                    }
                ],
            }
        ]
    }

    enriched = lint_and_enrich(news)
    item = enriched["sections"][0]["items"][0]
    assert item["loan_team_logo"] == "https://media.example.com/teams/500.png"

    stored = TeamProfile.query.filter_by(team_id=loan_team.team_id).first()
    assert stored is not None
    assert stored.logo_url == "https://media.example.com/teams/500.png"
    assert stored.venue_image == "https://media.example.com/venues/900.png"


def test_lint_and_enrich_uses_cached_team_profile(app, stub_api_client):
    from src.models.league import db, Team, LoanedPlayer, TeamProfile

    parent_team = Team(team_id=2, name="Parent Two", country="England", season=2024, is_active=True)
    loan_team = Team(team_id=600, name="Loan Cached", country="England", season=2024, is_active=True)
    db.session.add_all([parent_team, loan_team])
    db.session.commit()

    loaned = LoanedPlayer(
        player_id=404,
        player_name="D. Example",
        primary_team_id=parent_team.id,
        primary_team_name=parent_team.name,
        loan_team_id=loan_team.id,
        loan_team_name=loan_team.name,
        is_active=True,
        window_key="2024-25::FULL",
    )
    profile = TeamProfile(
        team_id=loan_team.team_id,
        name=loan_team.name,
        code="LCF",
        country="England",
        founded=1901,
        logo_url="https://media.example.com/teams/600.png",
    )
    db.session.add_all([loaned, profile])
    db.session.commit()

    def fail_get_team_by_id(*args, **kwargs):
        raise AssertionError("should use cached team profile")

    stub_api_client.get_team_by_id = fail_get_team_by_id

    news = {
        "sections": [
            {
                "title": "Active Loans",
                "items": [
                    {
                        "player_id": 404,
                        "player_name": "D. Example",
                        "loan_team": "Loan Cached",
                        "stats": {"minutes": 90, "goals": 0, "assists": 0, "yellows": 0, "reds": 0},
                    }
                ],
            }
        ]
    }

    enriched = lint_and_enrich(news)
    item = enriched["sections"][0]["items"][0]
    assert item["loan_team_logo"] == "https://media.example.com/teams/600.png"


def test_canonicalize_name_fixes_harry_amass():
    """Test that 'Hakeem Amass' is correctly canonicalized to 'Harry Amass'"""
    assert _canonicalize_name("Hakeem Amass") == "Harry Amass"
    assert _canonicalize_name("Harry Amass") == "Harry Amass"


def test_canonicalize_name_fixes_hannibal_mejbri():
    """Test that 'Harry Mejbri' is correctly canonicalized to 'Hannibal Mejbri'"""
    assert _canonicalize_name("Harry Mejbri") == "Hannibal Mejbri"
    assert _canonicalize_name("Hannibal Mejbri") == "Hannibal Mejbri"


def test_canonicalize_name_fixes_ethan_galbraith():
    """Test that 'Ellis Galbraith' is correctly canonicalized to 'Ethan Galbraith'"""
    assert _canonicalize_name("Ellis Galbraith") == "Ethan Galbraith"
    assert _canonicalize_name("Ethan Galbraith") == "Ethan Galbraith"


def test_canonicalize_name_preserves_unknown_names():
    """Test that unknown names are returned unchanged"""
    assert _canonicalize_name("John Doe") == "John Doe"
    assert _canonicalize_name("Jane Smith") == "Jane Smith"


def test_match_notes_with_explicit_attribution():
    """Test that match_notes provide explicit attribution for goals and assists"""
    news = {
        "title": "Test",
        "range": ["2024-10-21", "2024-10-27"],
        "sections": [{
            "title": "Active Loans",
            "items": [
                {
                    "player_name": "J. Sancho",
                    "loan_team": "Chelsea",
                    "week_summary": "Scored and assisted in victory over Arsenal.",
                    "stats": {"minutes": 90, "goals": 1, "assists": 1, "yellows": 0, "reds": 0},
                    "match_notes": ["1 goal vs Arsenal", "1 assist vs Arsenal"],
                    "links": []
                },
            ]
        }]
    }
    
    enriched = lint_and_enrich(news)
    item = enriched["sections"][0]["items"][0]
    
    # Verify match_notes contain explicit opponent attribution
    match_notes = item.get("match_notes", [])
    assert len(match_notes) >= 2
    assert any("Arsenal" in note for note in match_notes)
    assert any("goal" in note.lower() for note in match_notes)
    assert any("assist" in note.lower() for note in match_notes)


def test_match_notes_prevent_misattribution():
    """Test that having match_notes with explicit opponents helps prevent misattribution"""
    news = {
        "title": "Test",
        "range": ["2024-10-21", "2024-10-27"],
        "sections": [{
            "title": "Active Loans",
            "items": [
                {
                    "player_name": "H. Amass",
                    "loan_team": "QPR", 
                    "week_summary": "Played two matches this week.",
                    "stats": {"minutes": 180, "goals": 0, "assists": 1, "yellows": 0, "reds": 0},
                    # This should clearly show the assist was vs West Brom, not vs Man City
                    "match_notes": ["90 minutes vs West Brom", "1 assist vs West Brom", "90 minutes vs Man City"],
                    "links": []
                },
            ]
        }]
    }
    
    enriched = lint_and_enrich(news)
    item = enriched["sections"][0]["items"][0]
    
    # Verify the assist is clearly attributed to West Brom
    match_notes = item.get("match_notes", [])
    assist_note = next((note for note in match_notes if "assist" in note.lower()), None)
    assert assist_note is not None
    assert "West Brom" in assist_note
    assert "Man City" not in assist_note  # Should NOT attribute assist to Man City


def test_comprehensive_match_notes_format():
    """Test that match_notes can contain comprehensive stats per game"""
    news = {
        "title": "Test",
        "range": ["2024-10-21", "2024-10-27"],
        "sections": [{
            "title": "Active Loans",
            "items": [
                {
                    "player_name": "M. Mount",
                    "loan_team": "Brighton",
                    "week_summary": "Outstanding week with goal and assist.",
                    "stats": {"minutes": 90, "goals": 1, "assists": 1, "yellows": 0, "reds": 0},
                    # Comprehensive match notes with all performance details
                    "match_notes": [
                        "1 goal vs Liverpool",
                        "1 assist vs Liverpool", 
                        "vs Liverpool: 1G, 1A, Rating: 8.5, 3/5 shots on target, 4 key passes, 7/10 dribbles, 5 tackles"
                    ],
                    "links": []
                },
            ]
        }]
    }
    
    enriched = lint_and_enrich(news)
    item = enriched["sections"][0]["items"][0]
    
    # Verify comprehensive match notes are preserved
    match_notes = item.get("match_notes", [])
    assert len(match_notes) >= 1
    
    # Find the comprehensive summary note
    comprehensive_note = next((note for note in match_notes if "Rating:" in note), None)
    assert comprehensive_note is not None
    assert "Liverpool" in comprehensive_note
    assert "shots on target" in comprehensive_note or "key passes" in comprehensive_note


def test_season_context_structure():
    """Test that season_context has the expected structure when included"""
    news = {
        "title": "Test",
        "range": ["2024-10-21", "2024-10-27"],
        "sections": [{
            "title": "Active Loans",
            "items": [
                {
                    "player_name": "A. Player",
                    "loan_team": "Test FC",
                    "week_summary": "Good performance.",
                    "stats": {"minutes": 90, "goals": 1, "assists": 0, "yellows": 0, "reds": 0},
                    "match_notes": ["1 goal vs Opponent"],
                    # Season context data structure
                    "season_context": {
                        "season_stats": {
                            "games_played": 12,
                            "minutes": 1020,
                            "goals": 5,
                            "assists": 3,
                            "avg_rating": 7.2,
                            "clean_sheets": 4
                        },
                        "recent_form": [
                            {"goals": 1, "assists": 0, "minutes": 90},
                            {"goals": 0, "assists": 1, "minutes": 90},
                            {"goals": 1, "assists": 0, "minutes": 75},
                        ],
                        "trends": {
                            "goals_per_90": 0.44,
                            "assists_per_90": 0.26,
                            "goals_last_5": 3,
                            "g_a_last_5": 5
                        }
                    },
                    "links": []
                },
            ]
        }]
    }
    
    enriched = lint_and_enrich(news)
    item = enriched["sections"][0]["items"][0]
    
    # Verify season context is preserved
    season_context = item.get("season_context")
    assert season_context is not None
    
    # Check structure
    assert "season_stats" in season_context
    assert "recent_form" in season_context
    assert "trends" in season_context
    
    # Check season stats
    season_stats = season_context["season_stats"]
    assert season_stats["games_played"] == 12
    assert season_stats["goals"] == 5
    assert season_stats["assists"] == 3
    
    # Check trends
    trends = season_context["trends"]
    assert "goals_per_90" in trends
    assert "goals_last_5" in trends
