import pytest
import json
from datetime import date, timedelta
from src.models.league import db, UserAccount, Team, Newsletter, NewsletterCommentary, JournalistTeamAssignment
from itsdangerous import URLSafeTimedSerializer

def generate_token(app, email, role=None):
    secret = app.config['SECRET_KEY']
    s = URLSafeTimedSerializer(secret_key=secret, salt='user-auth')
    payload = {'email': email}
    if role:
        payload['role'] = role
    return s.dumps(payload)

def test_subscription_flow(client, app):
    # Setup
    with app.app_context():
        # Create subscriber
        sub = UserAccount(email="sub@example.com", display_name="Subscriber", display_name_lower="subscriber")
        db.session.add(sub)
        
        # Create journalist
        journo = UserAccount(email="journo@example.com", display_name="Journalist", display_name_lower="journalist", is_journalist=True)
        db.session.add(journo)
        db.session.commit()
        
        sub_id = sub.id
        journo_id = journo.id
        
        token = generate_token(app, "sub@example.com")

    # 1. Subscribe
    headers = {'Authorization': f'Bearer {token}'}
    resp = client.post(f'/api/journalists/{journo_id}/subscribe', headers=headers)
    assert resp.status_code == 201
    assert resp.json['message'] == 'Subscribed successfully'

    # 2. Verify Subscription
    resp = client.get('/api/my-subscriptions', headers=headers)
    assert resp.status_code == 200
    subs = resp.json
    assert len(subs) == 1
    assert subs[0]['id'] == journo_id

    # 3. Unsubscribe
    resp = client.post(f'/api/journalists/{journo_id}/unsubscribe', headers=headers)
    assert resp.status_code == 200
    assert resp.json['message'] == 'Unsubscribed successfully'

    # 4. Verify Unsubscription
    resp = client.get('/api/my-subscriptions', headers=headers)
    assert resp.status_code == 200
    assert len(resp.json) == 0

def test_cross_season_assignment(client, app):
    # Setup
    with app.app_context():
        # Create teams for different seasons with SAME API ID
        team2024 = Team(team_id=33, name="Man Utd", season=2024, country="England", is_active=False)
        team2025 = Team(team_id=33, name="Man Utd", season=2025, country="England", is_active=True)
        db.session.add_all([team2024, team2025])
        
        # Create journalist
        journo = UserAccount(email="journo@example.com", display_name="Journalist", display_name_lower="journalist", is_journalist=True)
        db.session.add(journo)
        db.session.commit()
        
        journo_id = journo.id
        team2024_id = team2024.id
        
        # Generate admin token
        admin_token = generate_token(app, "admin@example.com", role="admin")
        
    # Let's set the env var for the test
    import os
    os.environ['ADMIN_API_KEY'] = 'test-admin-key'
    
    headers = {
        'X-API-Key': 'test-admin-key',
        'Authorization': f'Bearer {admin_token}'
    }
    # Pass the DB ID of the 2024 team. The resolver should find the 2025 team (same API ID).
    payload = {'team_ids': [team2024_id]} 
    
    # Route is /api/journalists/<id>/assign-teams, NOT /api/admin/...
    resp = client.post(f'/api/journalists/{journo_id}/assign-teams', headers=headers, json=payload)
    assert resp.status_code == 200
    
    with app.app_context():
        # Verify assignment points to LATEST team (2025)
        assigns = JournalistTeamAssignment.query.filter_by(user_id=journo_id).all()
        assert len(assigns) == 1
        assert assigns[0].team.season == 2025
        assert assigns[0].team.team_id == 33

def test_commentary_visibility_in_preview(client, app):
    # Setup
    with app.app_context():
        # Create teams
        team2024 = Team(team_id=33, name="Man Utd", season=2024, country="England")
        team2025 = Team(team_id=33, name="Man Utd", season=2025, country="England")
        db.session.add_all([team2024, team2025])
        
        # Create journalist
        journo = UserAccount(email="journo@example.com", display_name="Journalist", display_name_lower="journalist", is_journalist=True)
        db.session.add(journo)
        db.session.commit()
        
        # Create Newsletter for 2025
        week_start = date(2025, 11, 3)
        week_end = date(2025, 11, 9)
        news = Newsletter(
            team_id=team2025.id, # Linked to 2025 team
            title="Man Utd Weekly",
            week_start_date=week_start,
            week_end_date=week_end,
            content="Content",
            public_slug="slug",
            published=False # Replaced status="draft"
        )
        db.session.add(news)
        db.session.commit()
        
        # Create Commentary linked to 2024 team (old season record)
        c1 = NewsletterCommentary(
            team_id=team2024.id, # Linked to 2024 team!
            author_id=journo.id,
            author_name="Journalist",
            commentary_type="intro",
            content="<p>Cross-season content</p>",
            week_start_date=week_start,
            week_end_date=week_end,
            is_active=True,
            position=0
        )
        db.session.add(c1)
        db.session.commit()
        
        news_id = news.id
        journo_id = journo.id
        
        # Verify newsletter exists
        assert Newsletter.query.get(news_id) is not None
        
        # Generate admin token for preview
        admin_token = generate_token(app, "admin@example.com", role="admin")

    # Test Preview
    headers = {
        'X-API-Key': 'test-admin-key',
        'Authorization': f'Bearer {admin_token}'
    }
    payload = {
        'journalist_ids': [journo_id], # Simulate selecting the journalist
        'render_mode': 'web'
    }
    
    resp = client.post(f'/api/newsletters/{news_id}/preview', headers=headers, json=payload)
    assert resp.status_code == 200
    
    html = resp.json['html']
    # Verify the content from the 2024-linked commentary appears in the 2025 newsletter preview
    assert "Cross-season content" in html
    assert "Journalist" in html
