import sqlalchemy as sa
from datetime import datetime, timezone

from src.models.league import db, Team, Newsletter, NewsletterDigestQueue, UserAccount
from src.routes.api import _user_serializer


def _admin_headers():
    token = _user_serializer().dumps({'email': 'admin@example.com', 'role': 'admin'})
    return {
        'Authorization': f'Bearer {token}',
        'X-API-Key': 'test-admin-key',
        'X-Admin-Key': 'test-admin-key',
    }


def test_delete_newsletter_without_reddit_posts_table(client, monkeypatch):
    monkeypatch.setenv('ADMIN_API_KEY', 'test-admin-key')

    team = Team(team_id=1, name='Test Team', country='Test', season=2024)
    db.session.add(team)
    db.session.flush()

    newsletter = Newsletter(
        team_id=team.id,
        newsletter_type='weekly',
        title='Test Newsletter',
        content='',
        public_slug='test-newsletter-slug',
    )
    db.session.add(newsletter)
    db.session.commit()

    db.session.execute(sa.text('DROP TABLE reddit_posts'))
    db.session.commit()

    response = client.delete(f'/api/newsletters/{newsletter.id}', headers=_admin_headers())
    assert response.status_code == 200


def test_delete_newsletter_with_digest_queue_entries(client, monkeypatch):
    monkeypatch.setenv('ADMIN_API_KEY', 'test-admin-key')

    team = Team(team_id=2, name='Digest FC', country='Test', season=2024)
    db.session.add(team)
    db.session.flush()

    newsletter = Newsletter(
        team_id=team.id,
        newsletter_type='weekly',
        title='Digest Newsletter',
        content='{}',
        public_slug='digest-newsletter-slug',
    )
    db.session.add(newsletter)

    user = UserAccount(
        email='digest@example.com',
        display_name='Digest User',
        display_name_lower='digest user',
    )
    db.session.add(user)
    db.session.flush()

    queue = NewsletterDigestQueue(
        user_id=user.id,
        newsletter_id=newsletter.id,
        week_key='2025-W01',
        queued_at=datetime.now(timezone.utc),
        sent=False,
    )
    db.session.add(queue)
    db.session.commit()

    newsletter_id = newsletter.id
    response = client.delete(f'/api/newsletters/{newsletter.id}', headers=_admin_headers())
    assert response.status_code == 200
    assert NewsletterDigestQueue.query.filter_by(newsletter_id=newsletter_id).count() == 0
