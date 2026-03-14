from flask import g, jsonify

from src.models.league import db
from src.routes.api import require_user_auth, issue_user_token, _ensure_user_account


def test_require_user_auth_sets_user(app, client):
    with app.app_context():
        _ensure_user_account('user@example.com')
        db.session.commit()

    token = issue_user_token('user@example.com')['token']

    def _handler():
        return jsonify({
            'user_email': getattr(g, 'user_email', None),
            'user_id': getattr(g, 'user_id', None),
            'has_user': getattr(g, 'user', None) is not None,
        })

    app.add_url_rule('/api/test-user-auth', 'test_user_auth', require_user_auth(_handler))

    res = client.get('/api/test-user-auth', headers={'Authorization': f'Bearer {token}'})

    assert res.status_code == 200
    payload = res.get_json()
    assert payload['user_email'] == 'user@example.com'
    assert payload['has_user'] is True
