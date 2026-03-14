from datetime import date
from unittest.mock import patch
from src.models.league import db, Team, Newsletter, NewsletterCommentary, UserAccount, JournalistSubscription
from src.routes.api import issue_user_token

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

def _make_user(email="test@example.com"):
    u = UserAccount(
        email=email, 
        display_name="Test User",
        display_name_lower="test user"
    )
    db.session.add(u)
    db.session.commit()
    return u

def test_journalist_filtering(app, client):
    team = _make_team()
    week_start = date(2025, 11, 3)
    week_end = date(2025, 11, 9)
    newsletter = _make_newsletter(team, week_start, week_end)

    # Journalist 1 commentary
    c1 = NewsletterCommentary(
        team_id=team.id,
        newsletter_id=newsletter.id,
        author_id=1,
        author_name="Journalist 1",
        commentary_type="analysis",
        content="<p>Analysis by J1</p>",
        week_start_date=week_start,
        week_end_date=week_end,
        is_active=True,
        is_premium=False
    )
    # Journalist 2 commentary
    c2 = NewsletterCommentary(
        team_id=team.id,
        newsletter_id=newsletter.id,
        author_id=2,
        author_name="Journalist 2",
        commentary_type="analysis",
        content="<p>Analysis by J2</p>",
        week_start_date=week_start,
        week_end_date=week_end,
        is_active=True,
        is_premium=False
    )
    db.session.add_all([c1, c2])
    db.session.commit()

    # Test filtering for Journalist 1
    resp = client.get(f"/api/newsletters/{newsletter.id}?journalist_id=1")
    assert resp.status_code == 200
    data = resp.get_json()
    commentaries = data.get('commentaries', [])
    assert len(commentaries) == 1
    assert commentaries[0]['author_id'] == 1
    assert commentaries[0]['content'] == "<p>Analysis by J1</p>"

    # Test filtering for Journalist 2
    resp = client.get(f"/api/newsletters/{newsletter.id}?journalist_id=2")
    assert resp.status_code == 200
    data = resp.get_json()
    commentaries = data.get('commentaries', [])
    assert len(commentaries) == 1
    assert commentaries[0]['author_id'] == 2

    # Test no filter
    resp = client.get(f"/api/newsletters/{newsletter.id}")
    assert resp.status_code == 200
    data = resp.get_json()
    commentaries = data.get('commentaries', [])
    assert len(commentaries) == 2

def test_premium_masking_unsubscribed(app, client):
    team = _make_team(api_id=44)
    week_start = date(2025, 11, 3)
    week_end = date(2025, 11, 9)
    newsletter = _make_newsletter(team, week_start, week_end)

    # Premium commentary by Journalist 1 (Long content to test truncation)
    long_content = "Secret " * 50
    c1 = NewsletterCommentary(
        team_id=team.id,
        newsletter_id=newsletter.id,
        author_id=1,
        author_name="Journalist 1",
        commentary_type="analysis",
        content=f"<p>{long_content}</p>",
        week_start_date=week_start,
        week_end_date=week_end,
        is_active=True,
        is_premium=True
    )
    db.session.add(c1)
    db.session.commit()

    # Request as anonymous user
    resp = client.get(f"/api/newsletters/{newsletter.id}?journalist_id=1")
    assert resp.status_code == 200
    data = resp.get_json()
    commentaries = data.get('commentaries', [])
    assert len(commentaries) == 1
    assert commentaries[0]['is_locked'] == True
    # Check that it is truncated
    assert len(commentaries[0]['content']) <= 203 # 200 + ...
    assert "..." in commentaries[0]['content']

    # Request as authenticated but unsubscribed user
    user = _make_user()
    token = issue_user_token(user.email)['token']
    resp = client.get(
        f"/api/newsletters/{newsletter.id}?journalist_id=1",
        headers={'Authorization': f'Bearer {token}'}
    )
    assert resp.status_code == 200
    data = resp.get_json()
    commentaries = data.get('commentaries', [])
    assert commentaries[0]['is_locked'] == True
    assert len(commentaries[0]['content']) <= 203

def test_premium_access_subscribed(app, client):
    team = _make_team(api_id=55)
    week_start = date(2025, 11, 3)
    week_end = date(2025, 11, 9)
    newsletter = _make_newsletter(team, week_start, week_end)

    # Premium commentary by Journalist 1
    c1 = NewsletterCommentary(
        team_id=team.id,
        newsletter_id=newsletter.id,
        author_id=1,
        author_name="Journalist 1",
        commentary_type="analysis",
        content="<p>Secret premium content</p>",
        week_start_date=week_start,
        week_end_date=week_end,
        is_active=True,
        is_premium=True
    )
    db.session.add(c1)
    
    # User subscribed to Journalist 1
    user = _make_user(email="sub@example.com")
    sub = JournalistSubscription(
        subscriber_user_id=user.id,
        journalist_user_id=1,
        is_active=True,
        created_at=date(2025, 1, 1) # Fix IntegrityError
    )
    db.session.add(sub)
    db.session.commit()

    token = issue_user_token(user.email)['token']
    resp = client.get(
        f"/api/newsletters/{newsletter.id}?journalist_id=1",
        headers={'Authorization': f'Bearer {token}'}
    )
    if resp.status_code != 200:
        print(f"DEBUG: {resp.data}")
    assert resp.status_code == 200
    data = resp.get_json()
    commentaries = data.get('commentaries', [])
    assert len(commentaries) == 1
    assert commentaries[0]['is_locked'] == False
    assert commentaries[0]['content'] == "<p>Secret premium content</p>"
