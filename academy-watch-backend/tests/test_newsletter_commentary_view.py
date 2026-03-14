from datetime import date

from src.models.league import db, Team, Newsletter, NewsletterCommentary


def _make_team(name="Team", api_id=33, season=2025):
    t = Team(team_id=api_id, name=name, country="England", season=season)
    db.session.add(t)
    db.session.commit()
    return t


def _make_newsletter(team, week_start, week_end):
    n = Newsletter(
        team_id=team.id,
        newsletter_type="weekly",
        title="Weekly Update",
        content="{}",
        public_slug="weekly-update",
        week_start_date=week_start,
        week_end_date=week_end,
        issue_date=week_end,
        published=True,
    )
    db.session.add(n)
    db.session.commit()
    return n


def test_newsletter_view_includes_week_scoped_commentary_even_without_newsletter_id(app, client):
    team = _make_team()
    week_start = date(2025, 11, 3)
    week_end = date(2025, 11, 9)
    newsletter = _make_newsletter(team, week_start, week_end)

    commentary = NewsletterCommentary(
        team_id=team.id,
        author_id=1,
        author_name="Scout 1",
        commentary_type="intro",
        content="<p>Hello world</p>",
        week_start_date=week_start,
        week_end_date=week_end,
        is_active=True,
    )
    db.session.add(commentary)
    db.session.commit()

    resp = client.get(f"/api/newsletters/{newsletter.id}")
    assert resp.status_code == 200
    body = resp.get_json()
    ids = {c["id"] for c in body.get("commentaries", [])}
    assert commentary.id in ids


def test_newsletter_view_dedupes_commentary_from_week_and_direct_links(app, client):
    team = _make_team(api_id=44)
    week_start = date(2025, 10, 6)
    week_end = date(2025, 10, 12)
    newsletter = _make_newsletter(team, week_start, week_end)

    # Commentary saved without newsletter_id
    c1 = NewsletterCommentary(
        team_id=team.id,
        author_id=2,
        author_name="Writer",
        commentary_type="summary",
        content="<p>Week summary</p>",
        week_start_date=week_start,
        week_end_date=week_end,
        is_active=True,
    )
    # Commentary saved with newsletter_id
    c2 = NewsletterCommentary(
        team_id=team.id,
        newsletter_id=newsletter.id,
        author_id=2,
        author_name="Writer",
        commentary_type="summary",
        content="<p>Direct link</p>",
        week_start_date=week_start,
        week_end_date=week_end,
        is_active=True,
    )

    db.session.add_all([c1, c2])
    db.session.commit()

    resp = client.get(f"/api/newsletters/{newsletter.id}")
    assert resp.status_code == 200
    body = resp.get_json()
    commentaries = body.get("commentaries", [])
    assert len(commentaries) == 2
    contents = {c["content"] for c in commentaries}
    assert "<p>Week summary</p>" in contents
    assert "<p>Direct link</p>" in contents
