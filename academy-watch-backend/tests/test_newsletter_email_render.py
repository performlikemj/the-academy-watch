"""Tests for the rebuilt newsletter email presentation layer.

Covers the new `_newsletter_render_context` keys (featured_items,
featured_overflow, squad_watch, week_numbers, academy_watch, postal_address)
and the rewritten `newsletter_email.html` template (table-based, no base64
charts, < 95KB).

Week dates are derived from "today" because injury lookups are intentionally
skipped for archived newsletters (week_end older than 45 days) — a fixed
fixture week would silently flip behavior as the calendar advances.
"""

import json
from datetime import date, timedelta
from uuid import uuid4

import pytest
import src.routes.api as api_module
from flask import render_template
from src.models.league import AcademyPlayerSeasonStats, League, Newsletter, Team, db
from src.models.tracked_player import TrackedPlayer

WEEK_END = date.today() - timedelta(days=4)
WEEK_START = WEEK_END - timedelta(days=6)
FORM_DATE_NEWEST = WEEK_END - timedelta(days=1)
FORM_DATE_MID = WEEK_END - timedelta(days=8)
FORM_DATE_OLDEST = WEEK_END - timedelta(days=15)
INJURY_IN_WINDOW = WEEK_START + timedelta(days=3)
INJURY_OUT_OF_WINDOW = WEEK_START - timedelta(days=90)
# European seasons start in July — mirrors the derivation in _build_squad_watch
EXPECTED_SEASON = WEEK_START.year if WEEK_START.month >= 7 else WEEK_START.year - 1


def _structured_content() -> dict:
    return {
        "title": "Manchester United Loan Watch",
        "summary": "A big week for the loan army.",
        "season": EXPECTED_SEASON,
        "range": [WEEK_START.isoformat(), WEEK_END.isoformat()],
        "highlights": ["Alfie Striker scored twice"],
        "by_numbers": {
            "minutes_leaders": [{"player": "Alfie Striker", "minutes": 178}],
            "ga_leaders": [{"player": "Alfie Striker", "g": 1, "a": 1}],
        },
        "sections": [
            {
                "title": "Player Reports",
                "items": [
                    {
                        # Rich featured player: rating, recent_form, W and L matches
                        "player_id": 9001,
                        "player_api_id": 9001,
                        "player_name": "Alfie Striker",
                        "player_photo": "https://media.example/players/9001.png",
                        "loan_team": "Walsall",
                        "loan_team_name": "Walsall FC",
                        "loan_team_logo": "https://media.example/teams/901.png",
                        "current_level": "U21",
                        "can_fetch_stats": True,
                        "stats": {
                            "minutes": 178,
                            "goals": 1,
                            "assists": 1,
                            "rating": 7.8,
                            "position": "F",
                            "passes_key": 4,
                            "duels_total": 11,
                            "duels_won": 7,
                            "tackles_total": 3,
                            "dribbles_attempts": 5,
                            "dribbles_success": 2,
                            "shots_total": 4,
                            "shots_on": 2,
                            "yellows": 0,
                            "reds": 0,
                        },
                        "week_summary": "Alfie Striker scored and assisted across two matches.",
                        "matches": [
                            {
                                "opponent": "Walsall",
                                "opponent_logo": "https://media.example/teams/700.png",
                                "competition": "League Two",
                                "home": True,
                                "score": {"home": 2, "away": 1},
                                "result": "W",
                            },
                            {
                                "opponent": "Hull City",
                                "competition": "Championship",
                                "home": False,
                                "score": {"home": 0, "away": 2},
                                "result": "L",
                            },
                        ],
                        # newest-first, as produced by the weekly agent
                        "recent_form": [
                            {
                                "date": f"{FORM_DATE_NEWEST.isoformat()}T15:00:00",
                                "minutes": 90,
                                "goals": 1,
                                "assists": 1,
                                "rating": 7.8,
                            },
                            {
                                "date": f"{FORM_DATE_MID.isoformat()}T15:00:00",
                                "minutes": 0,
                                "goals": 0,
                                "assists": 0,
                            },
                            {
                                "date": f"{FORM_DATE_OLDEST.isoformat()}T15:00:00",
                                "minutes": 88,
                                "goals": 0,
                                "assists": 0,
                                "rating": 6.9,
                            },
                        ],
                        # base64 chart must NOT be inlined in the email
                        "trend_chart_url": "data:image/png;base64,QUFBQQ==",
                        "upcoming_fixtures": [],
                    },
                    {
                        # Minimal featured player: no rating / form / matches
                        "player_api_id": 9002,
                        "player_name": "Billy Minimal",
                        "loan_team": "Salford City",
                        "stats": {"minutes": 45, "goals": 0, "assists": 0},
                    },
                    {
                        # Zero minutes, 'unused substitute' heuristic
                        "player_api_id": 9003,
                        "player_name": "Charlie Unused",
                        "loan_team_name": "Barnet",
                        "stats": {"minutes": 0, "goals": 0, "assists": 0},
                        "week_summary": "Charlie Unused was an unused substitute for Barnet during defeat 1-3.",
                    },
                    {
                        # Zero minutes, no summary text -> injury lookup path
                        "player_api_id": 9004,
                        "player_name": "Danny Bare",
                        "loan_team_name": "Newport County",
                        "stats": {"minutes": 0, "goals": 0, "assists": 0},
                        "week_summary": "",
                    },
                ],
            }
        ],
    }


class _StubAPIClient:
    """Stands in for src.routes.api.api_client during tests."""

    def __init__(self, injuries_by_player=None):
        self.injuries_by_player = injuries_by_player or {}
        self.calls = []
        self.season_calls = []

    def get_player_injuries(self, player_id, season=None):
        self.calls.append(int(player_id))
        self.season_calls.append(season)
        return self.injuries_by_player.get(int(player_id), [])


@pytest.fixture
def stub_api_client(monkeypatch):
    stub = _StubAPIClient(
        injuries_by_player={
            # In-window injury (window: week_start - 7d .. week_end + 1d)
            9004: [
                {
                    "player": {"id": 9004, "name": "Danny Bare", "reason": "Knee Injury", "type": "Missing Fixture"},
                    "fixture": {"id": 1, "date": f"{INJURY_IN_WINDOW.isoformat()}T15:00:00+00:00"},
                },
                {
                    # Older record outside the window — must be ignored
                    "player": {"id": 9004, "name": "Danny Bare", "reason": "Ankle Injury", "type": "Missing Fixture"},
                    "fixture": {"id": 2, "date": f"{INJURY_OUT_OF_WINDOW.isoformat()}T15:00:00+00:00"},
                },
            ],
            # Out-of-window record only -> falls back to text heuristic
            9003: [
                {
                    "player": {
                        "id": 9003,
                        "name": "Charlie Unused",
                        "reason": "Thigh Injury",
                        "type": "Missing Fixture",
                    },
                    "fixture": {"id": 3, "date": f"{INJURY_OUT_OF_WINDOW.isoformat()}T15:00:00+00:00"},
                }
            ],
        }
    )
    monkeypatch.setattr(api_module, "api_client", stub)
    # Keep renders offline + filesystem-clean
    monkeypatch.setattr(api_module, "_ensure_newsletter_cover_image", lambda n, *, team_logo: None)
    return stub


def _seed_team(api_id=33, name="Manchester United"):
    league = League(league_id=1000 + api_id, name=f"League {api_id}", country="England", season=2025)
    db.session.add(league)
    db.session.flush()
    team = Team(team_id=api_id, name=name, country="England", season=2025, league_id=league.id, is_active=True)
    db.session.add(team)
    db.session.flush()
    return team


def _seed_newsletter(content, team, *, week_start=WEEK_START, week_end=WEEK_END):
    n = Newsletter(
        team_id=team.id,
        newsletter_type="weekly",
        title=content.get("title") or "Test Issue",
        content=json.dumps(content),
        structured_content=json.dumps(content),
        public_slug=f"test-issue-{uuid4().hex[:10]}",
        week_start_date=week_start,
        week_end_date=week_end,
        issue_date=week_end,
        published=True,
    )
    db.session.add(n)
    db.session.commit()
    return n


@pytest.fixture
def newsletter(app):
    league = League(league_id=39, name="Premier League", country="England", season=2025)
    db.session.add(league)
    db.session.flush()

    parent = Team(
        team_id=33, name="Manchester United", country="England", season=2025, league_id=league.id, is_active=True
    )
    db.session.add(parent)
    db.session.flush()

    # Academy players (status='academy') with season stats
    young_gun = TrackedPlayer(
        player_api_id=9101,
        player_name="Young Gun",
        team_id=parent.id,
        status="academy",
        current_level="U18",
        is_active=True,
    )
    tall_keeper = TrackedPlayer(
        player_api_id=9102,
        player_name="Tall Keeper",
        team_id=parent.id,
        status="academy",
        current_level="U21",
        is_active=True,
    )
    # On-loan player must be excluded from academy_watch
    loanee = TrackedPlayer(
        player_api_id=9001,
        player_name="Alfie Striker",
        team_id=parent.id,
        status="on_loan",
        is_active=True,
    )
    db.session.add_all([young_gun, tall_keeper, loanee])
    db.session.flush()

    db.session.add_all(
        [
            # Latest season — linked via tracked_player_id
            AcademyPlayerSeasonStats(
                player_api_id=9101,
                player_name="Young Gun",
                league_api_id=701,
                league_name="U18 Premier League",
                team_api_id=33,
                season=2025,
                appearances=12,
                lineups=11,
                minutes=940,
                rating=7.43,
                goals=5,
                assists=3,
                tracked_player_id=young_gun.id,
            ),
            # Older season for the same player — must be filtered out
            AcademyPlayerSeasonStats(
                player_api_id=9101,
                player_name="Young Gun",
                league_api_id=701,
                league_name="U18 Premier League",
                team_api_id=33,
                season=2024,
                appearances=20,
                minutes=1500,
                rating=6.9,
                goals=2,
                assists=1,
                tracked_player_id=young_gun.id,
            ),
            # Linked only by player_api_id (no tracked_player_id FK)
            AcademyPlayerSeasonStats(
                player_api_id=9102,
                player_name="Tall Keeper",
                league_api_id=702,
                league_name="Premier League 2",
                team_api_id=33,
                season=2025,
                appearances=6,
                minutes=450,
                rating=6.4,
                goals=0,
                assists=0,
            ),
            # Belongs to the on_loan player — excluded by status filter
            AcademyPlayerSeasonStats(
                player_api_id=9001,
                player_name="Alfie Striker",
                league_api_id=702,
                league_name="Premier League 2",
                team_api_id=33,
                season=2025,
                appearances=9,
                minutes=800,
                rating=7.9,
                goals=6,
                assists=2,
                tracked_player_id=loanee.id,
            ),
        ]
    )

    content = _structured_content()
    n = Newsletter(
        team_id=parent.id,
        newsletter_type="weekly",
        title=content["title"],
        content=json.dumps(content),
        structured_content=json.dumps(content),
        public_slug="manchester-united-weekly-2025-12-21-test",
        week_start_date=WEEK_START,
        week_end_date=WEEK_END,
        issue_date=WEEK_END,
        published=True,
    )
    db.session.add(n)
    db.session.commit()
    return n


# ---------------------------------------------------------------------------
# Context builder
# ---------------------------------------------------------------------------


def test_featured_items_order_and_form_glyphs(app, newsletter, stub_api_client):
    ctx = api_module._newsletter_render_context(newsletter)

    featured = ctx["featured_items"]
    # lint_and_enrich normalizes display names to "A. Striker" form
    assert [it["player_name"] for it in featured] == ["A. Striker", "B. Minimal"]
    assert ctx["featured_overflow"] == []

    # Glyphs: oldest -> newest (played 88', benched 0', contributed 90' 1G1A)
    glyphs = featured[0]["form_glyphs"]
    assert [g["state"] for g in glyphs] == ["played", "bench", "contrib"]
    assert glyphs[0]["title"].startswith(FORM_DATE_OLDEST.isoformat())
    assert "1G 1A" in glyphs[-1]["title"]

    # Minimal player has no recent_form -> empty glyph list, never crashes
    assert featured[1]["form_glyphs"] == []


def test_week_numbers(app, newsletter, stub_api_client):
    ctx = api_module._newsletter_render_context(newsletter)
    wn = ctx["week_numbers"]
    assert wn["minutes_leader"] == {"player": "A. Striker", "value": 178}
    assert wn["ga_leader"] == {"player": "A. Striker", "value": 2}
    assert wn["best_rating"] == {"player": "A. Striker", "value": 7.8}
    assert wn["max_minutes"] == 178


def test_squad_watch_reasons(app, newsletter, stub_api_client):
    ctx = api_module._newsletter_render_context(newsletter)
    rows = {row["player_name"]: row for row in ctx["squad_watch"]}
    assert set(rows) == {"C. Unused", "D. Bare"}

    # 'unused substitute' text heuristic (its only injury record is out-of-window)
    charlie = rows["C. Unused"]
    assert charlie["reason_kind"] == "unused"
    assert charlie["reason"] == "Unused sub"
    assert charlie["loan_team_name"] == "Barnet"

    # In-window injury record wins over heuristics
    danny = rows["D. Bare"]
    assert danny["reason_kind"] == "injury"
    assert danny["reason"] == "Knee Injury"
    assert danny["player_api_id"] == 9004

    # Injury lookups are capped per render and carry the derived season
    assert len(stub_api_client.calls) <= 12
    assert all(season == EXPECTED_SEASON for season in stub_api_client.season_calls)


def test_squad_watch_reason_heuristics_widened(app):
    cases = {
        "He was an unused substitute again.": ("Unused sub", "unused"),
        "Left out: not in the matchday squad for both games.": ("Not in squad", "omitted"),
        "Not in matchday squad this weekend.": ("Not in squad", "omitted"),
        "He was not selected for the trip to Hull.": ("Not in squad", "omitted"),
        "Surprisingly not in the squad at Barnsley.": ("Not in squad", "omitted"),
        "Remained unavailable for selection.": ("Unavailable", "omitted"),
        "Out injured with a hamstring problem.": ("Injured", "injury"),
        "An ankle injury kept him out.": ("Injured", "injury"),
        "": ("No minutes", "none"),
    }
    for summary, expected in cases.items():
        assert api_module._squad_watch_reason_from_summary(summary) == expected, summary


def test_academy_watch_latest_season_only(app, newsletter, stub_api_client):
    ctx = api_module._newsletter_render_context(newsletter)
    rows = ctx["academy_watch"]

    assert [r["player_name"] for r in rows] == ["Young Gun", "Tall Keeper"]
    assert all(r["player_api_id"] != 9001 for r in rows)  # on_loan excluded

    young = rows[0]
    assert young["level"] == "U18"
    assert young["competition"] == "U18 Premier League"
    assert young["apps"] == 12
    assert young["goals"] == 5
    assert young["assists"] == 3
    assert young["minutes"] == 940  # 2024 season row (1500') filtered out
    assert young["rating"] == 7.4

    keeper = rows[1]
    assert keeper["level"] == "U21"
    assert keeper["competition"] == "Premier League 2"
    assert keeper["minutes"] == 450


def test_academy_watch_latest_season_per_player(app, newsletter, stub_api_client):
    """Latest season is chosen per player: a player whose stats stop at an
    earlier season still appears alongside players with current-season rows."""
    old_hand = TrackedPlayer(
        player_api_id=9103,
        player_name="Old Hand",
        team_id=newsletter.team_id,
        status="academy",
        current_level="U21",
        is_active=True,
    )
    db.session.add(old_hand)
    db.session.flush()
    db.session.add(
        AcademyPlayerSeasonStats(
            player_api_id=9103,
            player_name="Old Hand",
            league_api_id=702,
            league_name="Premier League 2",
            team_api_id=33,
            season=2024,
            appearances=10,
            minutes=600,
            rating=6.8,
            goals=1,
            assists=0,
            tracked_player_id=old_hand.id,
        )
    )
    db.session.commit()

    rows = api_module._newsletter_render_context(newsletter)["academy_watch"]
    by_name = {r["player_name"]: r for r in rows}

    # Player with only a 2024 season is still present...
    assert by_name["Old Hand"]["minutes"] == 600
    # ...while players with a newer season keep their latest-season row
    assert by_name["Young Gun"]["minutes"] == 940
    assert by_name["Tall Keeper"]["minutes"] == 450


def test_squad_watch_without_week_dates_skips_injury_lookup(app, newsletter, stub_api_client):
    newsletter.week_start_date = None
    newsletter.week_end_date = None
    ctx = api_module._newsletter_render_context(newsletter)
    rows = {row["player_name"]: row for row in ctx["squad_watch"]}
    assert rows["D. Bare"]["reason_kind"] == "none"
    assert stub_api_client.calls == []


def test_stats_less_items_excluded_and_consume_no_injury_lookups(app, stub_api_client):
    """'What the Internet is Saying' items (player_name + links only) and
    agent-emitted Academy Watch items (no stats dict) must appear in neither
    featured_items nor squad_watch, and never burn injury lookups."""
    content = {
        "title": "Stats-less Issue",
        "summary": "Quiet week.",
        "range": [WEEK_START.isoformat(), WEEK_END.isoformat()],
        "sections": [
            {
                "title": "What the Internet is Saying",
                "items": [
                    {"player_name": "Linked Lad", "links": ["https://example.com/post"]},
                ],
            },
            {
                "title": "Academy Watch",
                "items": [
                    {
                        "player_id": 5001,
                        "player_name": "Young Star",
                        "current_level": "U21",
                        "week_summary": "Started 12 of 15 games for the U21s.",
                    },
                ],
            },
        ],
    }
    team = _seed_team(api_id=101, name="Statless FC")
    n = _seed_newsletter(content, team)

    ctx = api_module._newsletter_render_context(n)
    assert ctx["featured_items"] == []
    assert ctx["featured_overflow"] == []
    assert ctx["squad_watch"] == []
    assert stub_api_client.calls == []


def test_featured_cap_and_overflow(app, stub_api_client):
    items = []
    for i in range(13):
        pid = 8000 + i
        items.append(
            {
                "player_id": pid,
                "player_api_id": pid,
                "player_name": f"Player Number{i:02d}",
                "loan_team_name": f"Club {i}",
                "stats": {"minutes": 90, "goals": 1, "assists": 0, "rating": (80 - i) / 10},
                "week_summary": f"Player Number{i:02d} played the full match.",
            }
        )
    content = {
        "title": "Busy Week",
        "summary": "Thirteen players saw minutes.",
        "range": [WEEK_START.isoformat(), WEEK_END.isoformat()],
        "sections": [{"title": "Player Reports", "items": items}],
    }
    team = _seed_team(api_id=102, name="Busy FC")
    n = _seed_newsletter(content, team)

    ctx = api_module._newsletter_render_context(n)
    assert len(ctx["featured_items"]) == 10
    overflow = ctx["featured_overflow"]
    assert len(overflow) == 3
    # Lowest-rated players spill into the overflow, keeping sort order
    assert [o["player_api_id"] for o in overflow] == [8010, 8011, 8012]
    assert all(o["line"] == "90' · 1G 0A" for o in overflow)
    assert all(o["loan_team_name"] for o in overflow)

    html = render_template("newsletter_email.html", **ctx)
    assert "ALSO ON THE PITCH" in html


def test_size_budget_with_busy_week(app, stub_api_client):
    """25 featured-shaped players + 15 squad rows + 10 academy rows must stay
    under Gmail's clip limit thanks to the featured/squad/academy caps."""
    items = []
    for i in range(25):
        pid = 7000 + i
        items.append(
            {
                "player_id": pid,
                "player_api_id": pid,
                "player_name": f"Featured Player{i:02d}",
                "loan_team": f"Loan Club {i}",
                "loan_team_name": f"Loan Club {i} FC",
                "current_level": "U21",
                "stats": {
                    "minutes": 90,
                    "goals": i % 3,
                    "assists": i % 2,
                    "rating": round(6.5 + (i % 20) * 0.05, 2),
                    "yellows": 0,
                    "reds": 0,
                },
                "week_summary": (
                    f"Featured Player{i:02d} put in a solid shift across two fixtures this week, "
                    "covering ground well and linking play between the lines."
                ),
                "matches": [
                    {
                        "opponent": "Opposition Town",
                        "competition": "League One",
                        "home": True,
                        "score": {"home": 2, "away": 1},
                        "result": "W",
                    },
                ],
                "recent_form": [
                    {
                        "date": f"{FORM_DATE_NEWEST.isoformat()}T15:00:00",
                        "minutes": 90,
                        "goals": 1,
                        "assists": 0,
                        "rating": 7.1,
                    },
                    {
                        "date": f"{FORM_DATE_MID.isoformat()}T15:00:00",
                        "minutes": 78,
                        "goals": 0,
                        "assists": 1,
                        "rating": 6.9,
                    },
                    {
                        "date": f"{FORM_DATE_OLDEST.isoformat()}T15:00:00",
                        "minutes": 0,
                        "goals": 0,
                        "assists": 0,
                    },
                ],
                "upcoming_fixtures": [],
            }
        )
    for i in range(15):
        pid = 7600 + i
        items.append(
            {
                "player_api_id": pid,
                "player_name": f"Benched Player{i:02d}",
                "loan_team_name": f"Bench Club {i}",
                "stats": {"minutes": 0, "goals": 0, "assists": 0},
                "week_summary": f"Benched Player{i:02d} was an unused substitute this week.",
            }
        )
    content = {
        "title": "Maximum Week",
        "summary": "Everyone played or nearly did.",
        "range": [WEEK_START.isoformat(), WEEK_END.isoformat()],
        "sections": [{"title": "Player Reports", "items": items}],
    }
    team = _seed_team(api_id=103, name="Maximal FC")
    for i in range(10):
        api_id = 7800 + i
        tp = TrackedPlayer(
            player_api_id=api_id,
            player_name=f"Academy Kid {i}",
            team_id=team.id,
            status="academy",
            current_level="U18",
            is_active=True,
        )
        db.session.add(tp)
        db.session.flush()
        db.session.add(
            AcademyPlayerSeasonStats(
                player_api_id=api_id,
                player_name=f"Academy Kid {i}",
                league_api_id=701,
                league_name="U18 Premier League",
                team_api_id=103,
                season=2025,
                appearances=10 + i,
                minutes=500 + 50 * i,
                rating=6.5 + 0.1 * i,
                goals=i,
                assists=1,
                tracked_player_id=tp.id,
            )
        )
    n = _seed_newsletter(content, team)

    ctx = api_module._newsletter_render_context(n)
    html = render_template(
        "newsletter_email.html",
        **ctx,
        unsubscribe_url="https://example.com/unsubscribe/tok",
        manage_url="https://example.com/manage",
    )
    assert "ALSO ON THE PITCH" in html
    assert len(html.encode("utf-8")) < 95_000


def test_mixed_naive_and_aware_recent_form_dates(app):
    """One aware date + one naive date must not raise — naive datetimes are
    normalized to UTC before sorting."""
    items = [
        {
            "player_name": "Mixed Dates",
            "player_api_id": 4242,
            "loan_team_name": "Tz FC",
            "stats": {"minutes": 90, "goals": 0, "assists": 0},
            "recent_form": [
                {"date": "2025-12-20T15:00:00+00:00", "minutes": 90, "goals": 0, "assists": 0},
                {"date": "2025-12-13T15:00:00", "minutes": 45, "goals": 1, "assists": 0},
            ],
        }
    ]
    featured, overflow = api_module._build_featured_items(items)
    assert len(featured) == 1
    assert overflow == []
    # Glyphs derived (not the try/except [] fallback), ordered oldest -> newest
    assert [g["state"] for g in featured[0]["form_glyphs"]] == ["contrib", "played"]


def test_injury_lookup_passes_derived_season_for_january_week(app, stub_api_client, monkeypatch):
    """A January week belongs to the season that started the previous July —
    the derived season (week_start.year - 1) is passed to the API client."""

    class _FrozenDate(date):
        @classmethod
        def today(cls):
            return date(2026, 1, 20)

    monkeypatch.setattr(api_module, "date", _FrozenDate)

    seasons_seen = []

    class _SeasonStub:
        def get_player_injuries(self, player_id, season=None):
            seasons_seen.append(season)
            return []

    monkeypatch.setattr(api_module, "api_client", _SeasonStub())

    week_start, week_end = date(2026, 1, 12), date(2026, 1, 18)
    content = {
        "title": "January Issue",
        "summary": "Cold week.",
        "range": [week_start.isoformat(), week_end.isoformat()],
        "sections": [
            {
                "title": "Player Reports",
                "items": [
                    {
                        "player_api_id": 9404,
                        "player_name": "Winter Watchman",
                        "loan_team_name": "Frostbite FC",
                        "stats": {"minutes": 0, "goals": 0, "assists": 0},
                        "week_summary": "",
                    }
                ],
            }
        ],
    }
    team = _seed_team(api_id=104, name="January FC")
    n = _seed_newsletter(content, team, week_start=week_start, week_end=week_end)

    api_module._newsletter_render_context(n)
    assert seasons_seen == [2025]


def test_archived_newsletter_performs_zero_injury_lookups(app, stub_api_client):
    """Newsletters whose week ended > 45 days ago never hit the injuries API;
    reasons fall back to the text heuristics."""
    week_end = date.today() - timedelta(days=60)
    week_start = week_end - timedelta(days=6)
    content = {
        "title": "Archived Issue",
        "summary": "Long ago.",
        "range": [week_start.isoformat(), week_end.isoformat()],
        "sections": [
            {
                "title": "Player Reports",
                "items": [
                    {
                        "player_api_id": 9004,
                        "player_name": "Danny Bare",
                        "loan_team_name": "Newport County",
                        "stats": {"minutes": 0, "goals": 0, "assists": 0},
                        "week_summary": "Danny Bare was an unused substitute.",
                    }
                ],
            }
        ],
    }
    team = _seed_team(api_id=105, name="Archive FC")
    n = _seed_newsletter(content, team, week_start=week_start, week_end=week_end)

    ctx = api_module._newsletter_render_context(n)
    assert stub_api_client.calls == []
    rows = ctx["squad_watch"]
    assert len(rows) == 1
    assert rows[0]["reason_kind"] == "unused"  # heuristic fallback, no API


# ---------------------------------------------------------------------------
# Template render
# ---------------------------------------------------------------------------


def _render_email(newsletter) -> str:
    ctx = api_module._newsletter_render_context(newsletter)
    return render_template(
        "newsletter_email.html",
        **ctx,
        unsubscribe_url="https://example.com/unsubscribe/tok",
        manage_url="https://example.com/manage",
    )


def test_template_renders_full_newsletter(app, newsletter, stub_api_client):
    html = _render_email(newsletter)

    # Players (lint_and_enrich abbreviates display names)
    assert "A. Striker" in html
    assert "B. Minimal" in html
    assert "C. Unused" in html
    assert "D. Bare" in html

    # Result chips (W/L) with scores
    assert "W 2-1" in html
    assert "L 0-2" in html

    # Sections
    assert "THE WEEK IN NUMBERS" in html
    assert "THIS WEEK&#39;S LOAN ARMY" in html or "THIS WEEK'S LOAN ARMY" in html
    assert "SQUAD WATCH" in html
    assert "ACADEMY WATCH" in html
    assert "Season to date in youth competitions" in html

    # Form glyphs (contrib green present, with per-glyph titles)
    assert "#4ade80" in html
    assert FORM_DATE_NEWEST.isoformat() in html

    # Squad watch reasons
    assert "Knee Injury" in html
    assert "Unused sub" in html

    # Academy watch season line + rating badge
    assert "Young Gun" in html
    assert "12 apps" in html
    assert "7.4" in html

    # Footer links
    assert "View on web" in html
    assert "https://example.com/unsubscribe/tok" in html
    assert "https://example.com/manage" in html
    assert "buymeacoffee.com/TheAcademyWatch" in html
    assert "Report a data correction" in html
    assert "Got a take?" in html


def test_template_never_inlines_base64_charts(app, newsletter, stub_api_client):
    html = _render_email(newsletter)
    assert "data:image" not in html
    # Chart-bearing players link out to the web version instead
    assert "Full charts on the web version" in html


def test_template_email_size_under_gmail_clip_limit(app, newsletter, stub_api_client):
    html = _render_email(newsletter)
    assert len(html.encode("utf-8")) < 95_000


def test_template_omits_filler_and_empty_sections(app, newsletter, stub_api_client):
    html = _render_email(newsletter)
    assert "No fixtures scheduled" not in html
    # No community/twitter content seeded -> sections omitted
    assert "AROUND THE SQUAD" not in html
    assert "COMMUNITY TAKES" not in html
    assert "FAN PULSE" not in html
    # No overflow players -> compact list omitted
    assert "ALSO ON THE PITCH" not in html


def test_template_postal_address_rendered_when_env_set(app, newsletter, stub_api_client, monkeypatch):
    monkeypatch.setenv("EMAIL_POSTAL_ADDRESS", "The Academy Watch, 123 Carrington Lane, Manchester M31 4BH")
    html = _render_email(newsletter)
    assert "123 Carrington Lane" in html


def test_template_postal_address_omitted_when_env_unset(app, newsletter, stub_api_client, monkeypatch):
    monkeypatch.delenv("EMAIL_POSTAL_ADDRESS", raising=False)
    html = _render_email(newsletter)
    assert "Carrington Lane" not in html


def test_template_renders_with_minimal_context(app):
    """Preview path (weekly_agent) renders without the new context keys."""
    html = render_template(
        "newsletter_email.html",
        title="Minimal Issue",
        team_name="Test FC",
        range=("2025-12-15", "2025-12-21"),
        summary="Quiet week.",
        highlights=[],
        sections=[],
        by_numbers={},
        meta={},
    )
    assert "Minimal Issue" in html
    assert "Quiet week." in html
    # Empty derived sections are omitted entirely
    assert "SQUAD WATCH" not in html
    assert "ACADEMY WATCH" not in html
    assert "LOAN ARMY" not in html
    assert "data:image" not in html


def test_template_fallback_derives_featured_and_squad_from_sections(app):
    """Without featured_items/squad_watch keys the template derives both
    from sections (preview path via weekly_agent._build_template_context)."""
    content = _structured_content()
    html = render_template(
        "newsletter_email.html",
        title=content["title"],
        team_name="Manchester United",
        range=content["range"],
        summary=content["summary"],
        highlights=content["highlights"],
        sections=content["sections"],
        by_numbers=content["by_numbers"],
        meta={},
    )
    assert "Alfie Striker" in html
    assert "SQUAD WATCH" in html
    assert "Unused sub" in html
    assert "W 2-1" in html
    # by_numbers fallback feeds the week-in-numbers strip
    assert "THE WEEK IN NUMBERS" in html
    assert "data:image" not in html


def test_template_fallback_skips_stats_less_items(app):
    """In-template fallback derivations apply the same non-empty-stats guard
    as the context builder: link-only and academy items never become featured
    cards or squad-watch rows."""
    sections = [
        {
            "title": "What the Internet is Saying",
            "items": [{"player_name": "Linked Lad", "links": ["https://example.com/post"]}],
        },
        {
            "title": "Academy Watch",
            "items": [
                {
                    "player_id": 5001,
                    "player_name": "Young Star",
                    "current_level": "U21",
                    "week_summary": "Started 12 of 15 games for the U21s.",
                }
            ],
        },
    ]
    html = render_template(
        "newsletter_email.html",
        title="Fallback Issue",
        team_name="Test FC",
        range=(WEEK_START.isoformat(), WEEK_END.isoformat()),
        summary="Quiet.",
        highlights=[],
        sections=sections,
        by_numbers={},
        meta={},
    )
    assert "LOAN ARMY" not in html
    assert "SQUAD WATCH" not in html
