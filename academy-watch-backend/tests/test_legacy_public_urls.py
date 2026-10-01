"""Legacy public URL emitters share the page gate, independent of delivery freezes."""

import pytest
from src.utils import legacy_pages
from src.utils.newsletter_markdown import convert_newsletter_to_markdown


@pytest.mark.parametrize("legacy_visible", [False, True])
@pytest.mark.parametrize("root", sorted(legacy_pages.LEGACY_PUBLIC_ROOTS))
def test_legacy_public_url_preserves_enabled_urls(monkeypatch, legacy_visible, root):
    monkeypatch.setattr(legacy_pages, "LEGACY_PUBLIC_PAGES", legacy_visible)
    for url in (f"/{root}", f"https://example.com/{root}/fixture?view=full#detail"):
        assert legacy_pages.legacy_public_url(url) == (url if legacy_visible else None)
    assert legacy_pages.legacy_public_url(None) is None


@pytest.mark.parametrize("legacy_visible", [False, True])
def test_reddit_markdown_omits_hidden_newsletter_cta(monkeypatch, legacy_visible):
    monkeypatch.setattr(legacy_pages, "LEGACY_PUBLIC_PAGES", legacy_visible)
    url = "https://theacademywatch.com/newsletters/fixture-issue"
    markdown = convert_newsletter_to_markdown(
        {"title": "Fixture newsletter", "summary": "Fixture summary"}, web_url=url
    )
    assert (url in markdown) is legacy_visible
    assert ("View full newsletter with interactive stats" in markdown) is legacy_visible
    assert "Fixture summary" in markdown
    assert "[The Academy Watch](https://theacademywatch.com)" in markdown
    assert "]()" not in markdown


@pytest.mark.parametrize("legacy_visible", [False, True])
def test_public_program_omits_hidden_team_page_but_keeps_roster_api(app, monkeypatch, legacy_visible):
    from src.models.funding import ClubProgram, FundingLeague
    from src.models.league import TeamProfile, db
    from src.routes.funding import funding_bp

    monkeypatch.setattr(legacy_pages, "LEGACY_PUBLIC_PAGES", legacy_visible)
    app.register_blueprint(funding_bp, url_prefix="/api")
    league = FundingLeague(
        name="Fixture League",
        country="England",
        region="Fixture Region",
        level="youth_regional",
        registry_status="approved",
        admission_state="open",
        age_bands=["adult"],
        gender_program="both",
        season_calendar="fall_spring",
        data_tier="self_reported",
    )
    profile = TeamProfile(team_id=1001, name="Fixture FC", slug="fixture-fc")
    db.session.add_all([league, profile])
    db.session.flush()
    program = ClubProgram(
        name="Fixture FC",
        legal_name="Fixture FC Ltd",
        slug="fixture-program",
        country="England",
        region="Fixture Region",
        funding_league_id=league.id,
        team_api_id=profile.team_id,
        platform_status="approved",
        provenance_tier="self_reported",
        emergency_hidden=False,
    )
    db.session.add(program)
    db.session.commit()
    response = app.test_client().get("/api/programs/fixture-program")
    assert response.status_code == 200
    links = response.get_json()["program"]["roster_links"]
    assert links["team_page"] == ("/teams/fixture-fc" if legacy_visible else None)
    assert links["academy_roster_api"] == "/teams/1001/players?academy_only=true"


@pytest.mark.parametrize("legacy_visible", [False, True])
@pytest.mark.parametrize("emitter", ["publish", "admin"])
def test_reddit_emitters_gate_legacy_urls_without_changing_posts(app, monkeypatch, legacy_visible, emitter):
    import sys
    from types import SimpleNamespace

    from src.models.league import Newsletter, Team, TeamSubreddit, db
    from src.routes.api import _maybe_post_to_reddit_on_publish, issue_user_token

    monkeypatch.setattr(legacy_pages, "LEGACY_PUBLIC_PAGES", legacy_visible)
    monkeypatch.setenv("ADMIN_API_KEY", "fixture-key")
    team = Team(team_id=1001, name="Fixture FC", country="England", season=2026)
    db.session.add(team)
    db.session.flush()
    newsletter = Newsletter(
        team_id=team.id,
        title="Fixture newsletter",
        content="Fixture content",
        structured_content='{"title":"Fixture newsletter","summary":"Fixture summary","sections":[]}',
        public_slug="fixture-issue",
        published=True,
    )
    subreddit = TeamSubreddit(team_id=team.id, subreddit_name="fixture", post_format="full", is_active=True)
    db.session.add_all([newsletter, subreddit])
    db.session.commit()
    posts = []

    def fake_post(**kwargs):
        posts.append(kwargs)
        return {"status": "success"}

    monkeypatch.setitem(
        sys.modules,
        "src.services.reddit_service",
        SimpleNamespace(
            RedditService=SimpleNamespace(get_instance=lambda: SimpleNamespace(is_configured=lambda: True)),
            RedditServiceError=RuntimeError,
            post_newsletter_to_reddit=fake_post,
        ),
    )
    if emitter == "publish":
        result = _maybe_post_to_reddit_on_publish([newsletter])
        assert result[0]["success_count"] == 1
    else:
        token = issue_user_token("fixture-admin@example.com", role="admin")["token"]
        response = app.test_client().post(
            f"/api/admin/newsletters/{newsletter.id}/post-to-reddit",
            json={},
            headers={"Authorization": f"Bearer {token}", "X-API-Key": "fixture-key"},
        )
        assert response.status_code == 200
    assert len(posts) == 1
    assert posts[0]["newsletter_id"] == newsletter.id
    assert posts[0]["team_subreddit_id"] == subreddit.id
    markdown = posts[0]["markdown_content"]
    assert ("https://theacademywatch.com/newsletters/fixture-issue" in markdown) is legacy_visible
    assert "Fixture summary" in markdown


@pytest.mark.parametrize("legacy_visible", [False, True])
def test_gol_export_template_omits_generated_team_link_but_keeps_player(app, monkeypatch, legacy_visible):
    from flask import render_template
    from src.services.pdf_renderer import _normalize_gol_messages

    monkeypatch.setattr(legacy_pages, "LEGACY_PUBLIC_PAGES", legacy_visible)
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.com")
    messages = _normalize_gol_messages(
        [
            {
                "role": "assistant",
                "content": "Fixture analysis",
                "dataCards": [
                    {
                        "payload": {
                            "result_type": "table",
                            "columns": ["player_name", "player_api_id", "team_name", "team_api_id"],
                            "rows": [["Fixture Player", 9001, "Fixture FC", 1001]],
                        }
                    }
                ],
            }
        ]
    )
    html = render_template(
        "gol_chat_export.html", messages=messages, exported_date="fixture", site_url="https://example.com"
    )
    assert 'href="https://example.com/players/9001"' in html
    assert ('href="https://example.com/teams/1001"' in html) is legacy_visible
    assert "Fixture analysis" in html
    assert "Fixture FC" in html
    assert 'href=""' not in html
    assert 'href="None"' not in html
