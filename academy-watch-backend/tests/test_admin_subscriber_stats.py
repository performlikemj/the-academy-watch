import pytest

from src.models.league import db, Team, UserSubscription
from src.routes.api import issue_user_token

ADMIN_KEY = 'test-admin-key'


def _auth_headers(email='admin@example.com'):
    token = issue_user_token(email, role='admin')['token']
    return {
        'Authorization': f'Bearer {token}',
        'X-API-Key': ADMIN_KEY,
    }


@pytest.fixture(autouse=True)
def _set_admin_key(monkeypatch):
    monkeypatch.setenv('ADMIN_API_KEY', ADMIN_KEY)


def test_admin_subscriber_stats_returns_request_id_header(client):
    team = Team(team_id=101, name='Debug FC', season=2024, country='England')
    db.session.add(team)
    db.session.commit()

    subscription = UserSubscription(team_id=team.id, email='fan@example.com', active=True)
    db.session.add(subscription)
    db.session.commit()

    resp = client.get('/admin/subscriber-stats', headers=_auth_headers())

    assert resp.status_code == 200
    request_id = resp.headers.get('X-Request-ID')
    assert request_id

    payload = resp.get_json()
    assert payload['request_id'] == request_id
    assert payload['total_subscribers'] == 1
    assert payload['teams'][0]['subscriber_count'] == 1
