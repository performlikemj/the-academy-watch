import json
from datetime import date, datetime, timezone

from src.models.league import db, Team, Newsletter, UserAccount, NewsletterDigestQueue
from src.services.newsletter_deadline_service import _send_single_digest


class _DummyResponse:
    ok = True
    status_code = 200
    text = 'ok'


def test_send_single_digest_loads_content_without_enriched_content(app, monkeypatch):
    monkeypatch.setenv('N8N_EMAIL_WEBHOOK_URL', 'https://example.com/webhook')
    monkeypatch.setenv('PUBLIC_BASE_URL', 'https://example.com')

    team = Team(team_id=10, name='Digest Team', country='England', season=2025)
    db.session.add(team)
    db.session.commit()

    content_payload = {
        'title': 'Digest Title',
        'summary': 'Digest summary',
        'sections': [],
    }
    newsletter = Newsletter(
        team_id=team.id,
        title='Digest Title',
        content=json.dumps(content_payload),
        structured_content=json.dumps(content_payload),
        issue_date=date(2025, 1, 8),
        week_start_date=date(2025, 1, 6),
        week_end_date=date(2025, 1, 12),
        public_slug='digest-title-slug',
        published=True,
    )
    db.session.add(newsletter)

    user = UserAccount(
        email='digest-user@example.com',
        display_name='Digest User',
        display_name_lower='digest user',
    )
    db.session.add(user)
    db.session.flush()

    queue_entry = NewsletterDigestQueue(
        user_id=user.id,
        newsletter_id=newsletter.id,
        week_key='2025-W01',
        queued_at=datetime.now(timezone.utc),
        sent=False,
    )
    db.session.add(queue_entry)
    db.session.commit()

    monkeypatch.setattr('requests.post', lambda *args, **kwargs: _DummyResponse())

    result = _send_single_digest(user.id, '2025-W01')
    assert result['success'] is True
    assert result['newsletter_count'] == 1

    refreshed = NewsletterDigestQueue.query.get(queue_entry.id)
    assert refreshed.sent is True
