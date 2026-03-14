import json
import pytest

from src.models.league import db, RebuildConfig, RebuildConfigLog
from src.routes.api import issue_user_token
from src.routes.cohort import get_active_rebuild_config


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


def _seed_config(name='Test Config', config_dict=None, is_active=False):
    if config_dict is None:
        config_dict = {'seasons': [2023, 2024], 'team_ids': {'33': 'Man Utd'}}
    rc = RebuildConfig(
        name=name,
        is_active=is_active,
        config_json=json.dumps(config_dict),
        notes='seed note',
    )
    db.session.add(rc)
    db.session.commit()
    return rc


# -- List --

def test_list_configs_empty(client):
    resp = client.get('/api/admin/rebuild-configs', headers=_auth_headers())
    assert resp.status_code == 200
    assert resp.get_json() == []


# -- Create --

def test_create_config(client):
    resp = client.post('/api/admin/rebuild-configs', headers=_auth_headers(), json={
        'name': 'My Config',
        'config': {'seasons': [2024]},
        'notes': 'first preset',
    })
    assert resp.status_code == 201
    body = resp.get_json()
    assert body['name'] == 'My Config'
    assert body['config'] == {'seasons': [2024]}
    assert body['notes'] == 'first preset'
    assert body['is_active'] is False


def test_create_config_duplicate_name(client):
    _seed_config(name='Dupe')
    resp = client.post('/api/admin/rebuild-configs', headers=_auth_headers(), json={
        'name': 'Dupe',
    })
    assert resp.status_code == 409
    assert 'already exists' in resp.get_json()['error']


def test_create_config_missing_name(client):
    resp = client.post('/api/admin/rebuild-configs', headers=_auth_headers(), json={})
    assert resp.status_code == 400
    assert 'Name is required' in resp.get_json()['error']


def test_create_config_clone(client):
    source = _seed_config(name='Source', config_dict={'seasons': [2020, 2021]})
    resp = client.post('/api/admin/rebuild-configs', headers=_auth_headers(), json={
        'name': 'Cloned',
        'clone_from': source.id,
    })
    assert resp.status_code == 201
    body = resp.get_json()
    assert body['config']['seasons'] == [2020, 2021]


# -- Get --

def test_get_config(client):
    rc = _seed_config()
    resp = client.get(f'/api/admin/rebuild-configs/{rc.id}', headers=_auth_headers())
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['name'] == 'Test Config'
    assert 'history' in body


def test_get_config_not_found(client):
    resp = client.get('/api/admin/rebuild-configs/9999', headers=_auth_headers())
    assert resp.status_code == 404


# -- Update --

def test_update_config(client):
    rc = _seed_config(config_dict={'seasons': [2023]})
    resp = client.put(f'/api/admin/rebuild-configs/{rc.id}', headers=_auth_headers(), json={
        'name': 'Updated Name',
        'config': {'seasons': [2024, 2025]},
    })
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['name'] == 'Updated Name'
    assert body['config']['seasons'] == [2024, 2025]

    # Verify audit log captured diff with old/new values
    logs = RebuildConfigLog.query.filter_by(config_id=rc.id, action='updated').all()
    assert len(logs) >= 1
    diff = json.loads(logs[-1].diff_json)
    assert 'seasons' in diff
    assert diff['seasons']['old'] == [2023]
    assert diff['seasons']['new'] == [2024, 2025]


def test_update_config_name_conflict(client):
    _seed_config(name='Taken')
    rc2 = _seed_config(name='Other')
    resp = client.put(f'/api/admin/rebuild-configs/{rc2.id}', headers=_auth_headers(), json={
        'name': 'Taken',
    })
    assert resp.status_code == 409
    assert 'already exists' in resp.get_json()['error']


# -- Activate --

def test_activate_config(client):
    rc1 = _seed_config(name='Old Active', is_active=True)
    rc2 = _seed_config(name='New Active')

    resp = client.post(f'/api/admin/rebuild-configs/{rc2.id}/activate', headers=_auth_headers())
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['is_active'] is True

    # Previous config should be deactivated
    db.session.refresh(rc1)
    assert rc1.is_active is False


def test_activate_already_active(client):
    rc = _seed_config(name='Already', is_active=True)
    resp = client.post(f'/api/admin/rebuild-configs/{rc.id}/activate', headers=_auth_headers())
    assert resp.status_code == 200
    assert resp.get_json()['message'] == 'Already active'


# -- Delete --

def test_delete_config(client):
    rc = _seed_config()
    config_id = rc.id
    resp = client.delete(f'/api/admin/rebuild-configs/{config_id}', headers=_auth_headers())
    assert resp.status_code == 200
    assert 'deleted' in resp.get_json()['message']

    # Config and its logs should be gone
    assert RebuildConfig.query.get(config_id) is None
    assert RebuildConfigLog.query.filter_by(config_id=config_id).count() == 0


def test_delete_active_config_blocked(client):
    rc = _seed_config(is_active=True)
    resp = client.delete(f'/api/admin/rebuild-configs/{rc.id}', headers=_auth_headers())
    assert resp.status_code == 400
    assert 'Cannot delete' in resp.get_json()['error']


# -- History --

def test_config_history(client):
    rc = _seed_config()
    # The seed created a config but no log; create one via update
    client.put(f'/api/admin/rebuild-configs/{rc.id}', headers=_auth_headers(), json={
        'config': {'seasons': [2025]},
    })
    resp = client.get(f'/api/admin/rebuild-configs/{rc.id}/history', headers=_auth_headers())
    assert resp.status_code == 200
    history = resp.get_json()
    assert len(history) >= 1
    assert history[0]['action'] == 'updated'


# -- Defaults --

def test_defaults_endpoint(client):
    resp = client.get('/api/admin/rebuild-configs/defaults', headers=_auth_headers())
    assert resp.status_code == 200
    body = resp.get_json()
    assert 'team_ids' in body
    assert 'seasons' in body


# -- get_active_rebuild_config helper --

def test_get_active_rebuild_config_with_active(app):
    _seed_config(name='Active Preset', config_dict={'seasons': [2024]}, is_active=True)
    config_dict, config_id = get_active_rebuild_config()
    assert config_dict == {'seasons': [2024]}
    assert config_id is not None


def test_get_active_rebuild_config_fallback(app):
    # No active config exists, should return hardcoded defaults
    config_dict, config_id = get_active_rebuild_config()
    assert config_id is None
    assert 'team_ids' in config_dict
    assert 'seasons' in config_dict
