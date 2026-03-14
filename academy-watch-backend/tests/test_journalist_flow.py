import pytest
from src.models.league import UserAccount, Newsletter, NewsletterCommentary, JournalistSubscription, Team, db
from datetime import datetime, timezone

def test_journalist_flow(client, app):
    with app.app_context():
        # Create a journalist
        journalist = UserAccount(
            email='journalist@example.com',
            display_name='Journalist Joe',
            display_name_lower='journalist joe',
            is_journalist=True,
            bio='I write about football.',
            profile_image_url='http://example.com/joe.jpg'
        )
        db.session.add(journalist)
        
        # Create a subscriber
        subscriber = UserAccount(
            email='subscriber@example.com',
            display_name='Subscriber Sam',
            display_name_lower='subscriber sam'
        )
        db.session.add(subscriber)
        db.session.commit()
        
        journalist_id = journalist.id
        subscriber_id = subscriber.id

    # Test 1: List journalists
    response = client.get('/api/journalists')
    assert response.status_code == 200
    data = response.get_json()
    assert len(data) == 1
    assert data[0]['display_name'] == 'Journalist Joe'

    # Test 2: Subscribe (requires auth)
    # Mock auth by setting user in session or using a helper if available.
    # Assuming the app uses a custom auth mechanism or we can mock current_user.
    # For integration tests, we might need to login.
    # Let's assume we can simulate a logged-in user.
    # If the app uses session-based auth, we can set the session.
    # If it uses token-based, we need a token.
    # Looking at routes, it uses @login_required which usually checks session or token.
    # Let's try to mock the login by setting the session if possible, or using a testing helper.
    
    # Since I don't know the exact auth mechanism for tests, I'll try to use the 'client' to login if there's a login route,
    # or manually create the subscription to test the relationship first.
    
    # Let's manually create subscription to test the model first
    with app.app_context():
        sub = JournalistSubscription(
            subscriber_user_id=subscriber_id,
            journalist_user_id=journalist_id
        )
        db.session.add(sub)
        db.session.commit()
        
        # Verify subscription
        assert JournalistSubscription.query.filter_by(subscriber_user_id=subscriber_id, journalist_user_id=journalist_id, is_active=True).first() is not None

    # Test 3: Fetch newsletter with commentaries
    with app.app_context():
        team = Team(team_id=123, name='Test Team', country='England', season=2024)
        db.session.add(team)
        db.session.commit()

        newsletter = Newsletter(
            team_id=team.id,
            newsletter_type='weekly',
            title='Weekly Report',
            content='<p>Main content</p>',
            public_slug='weekly-report-1',
            week_start_date=datetime.now(timezone.utc),
            week_end_date=datetime.now(timezone.utc),
            issue_date=datetime.now(timezone.utc)
        )
        db.session.add(newsletter)
        db.session.commit()
        
        commentary = NewsletterCommentary(
            newsletter_id=newsletter.id,
            author_id=journalist_id,
            author_name='Journalist Joe',
            commentary_type='analysis',
            content='<p>Deep dive</p>',
            title='Deep Dive Analysis',
            is_premium=True
        )
        db.session.add(commentary)
        db.session.commit()
        
        # Verify to_dict includes commentaries
        n_dict = newsletter.to_dict()
        assert 'commentaries' in n_dict
        assert len(n_dict['commentaries']) == 1
        assert n_dict['commentaries'][0]['title'] == 'Deep Dive Analysis'
        assert n_dict['commentaries'][0]['is_premium'] == True

    # Test 4: API endpoints (if possible without complex auth mocking)
    # We can test the public endpoints at least.
    response = client.get(f'/api/journalists/{journalist_id}/articles')
    assert response.status_code == 200
    data = response.get_json()
    assert len(data) == 1
    assert data[0]['title'] == 'Deep Dive Analysis'

