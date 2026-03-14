from datetime import date

from src.models.league import db, Team, Newsletter, NewsletterCommentary


def _team(name="Team", api_id=33, season=2025):
    t = Team(team_id=api_id, name=name, country="England", season=season)
    db.session.add(t)
    db.session.commit()
    return t


def _newsletter(team, week_start, week_end, slug="weekly-test"):
    n = Newsletter(
        team_id=team.id,
        newsletter_type="weekly",
        title="Weekly",
        content="{}",
        structured_content="{}",
        public_slug=slug,
        week_start_date=week_start,
        week_end_date=week_end,
        issue_date=week_end,
        published=True,
    )
    db.session.add(n)
    db.session.commit()
    return n


def test_journalist_articles_include_resolved_newsletter(client):
    team = _team("Manchester United", api_id=33)
    week_start = date(2025, 11, 24)
    week_end = date(2025, 11, 30)
    newsletter = _newsletter(team, week_start, week_end, slug="man-utd-week")

    commentary = NewsletterCommentary(
        team_id=team.id,
        author_id=1,
        author_name="Reporter",
        commentary_type="intro",
        content="<p>Analysis</p>",
        week_start_date=week_start,
        week_end_date=week_end,
        is_active=True,
    )
    db.session.add(commentary)
    db.session.commit()

    resp = client.get(f"/api/journalists/{commentary.author_id}/articles")
    assert resp.status_code == 200
    body = resp.get_json()
    assert len(body) == 1
    article = body[0]
    assert article.get("newsletter_id") == newsletter.id
    assert article.get("newsletter_public_slug") == newsletter.public_slug
