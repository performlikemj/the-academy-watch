import pytest
from src.models.league import db, UserAccount, NewsletterCommentary, CommentaryApplause, Team, Newsletter
from datetime import date

def test_applaud_flow(client, app):
    # Setup
    with app.app_context():
        # Create team
        team = Team(team_id=33, name="Man Utd", season=2025, country="England")
        db.session.add(team)
        db.session.commit()
        
        # Create journalist
        journo = UserAccount(email="journo@example.com", display_name="Journalist", display_name_lower="journalist", is_journalist=True)
        db.session.add(journo)
        db.session.commit()
        
        # Create Newsletter
        news = Newsletter(
            team_id=team.id,
            title="Man Utd Weekly",
            content="Content",
            public_slug="slug"
        )
        db.session.add(news)
        db.session.commit()
        
        # Create Commentary
        c1 = NewsletterCommentary(
            team_id=team.id,
            author_id=journo.id,
            author_name="Journalist",
            commentary_type="intro",
            content="<p>Great analysis</p>",
            week_start_date=date(2025, 11, 3),
            week_end_date=date(2025, 11, 9),
            is_active=True,
            position=0
        )
        db.session.add(c1)
        db.session.commit()
        
        commentary_id = c1.id

    # 1. Applaud (Anonymous)
    resp = client.post(f'/api/commentaries/{commentary_id}/applaud')
    assert resp.status_code == 200
    assert resp.json['message'] == 'Applauded'
    assert resp.json['applause_count'] == 1
    
    # 2. Applaud again (Anonymous, different session maybe? or same)
    # The current implementation allows multiple claps
    resp = client.post(f'/api/commentaries/{commentary_id}/applaud')
    assert resp.status_code == 200
    assert resp.json['applause_count'] == 2
    
    # 3. Verify Persistence
    with app.app_context():
        c = NewsletterCommentary.query.get(commentary_id)
        assert c.applause.count() == 2
        assert CommentaryApplause.query.count() == 2

def test_applaud_404(client, app):
    resp = client.post('/api/commentaries/99999/applaud')
    assert resp.status_code == 404
