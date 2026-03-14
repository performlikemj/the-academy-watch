from datetime import datetime, timezone

from src.models.league import (
    db,
    Team,
    UserAccount,
    LoanedPlayer,
    JournalistTeamAssignment,
    JournalistLoanTeamAssignment,
    WriterCoverageRequest,
)
from src.routes.api import issue_user_token


def _writer_headers(email: str):
    token = issue_user_token(email)['token']
    return {'Authorization': f'Bearer {token}'}


def _admin_headers():
    token = issue_user_token('admin@example.com', role='admin')['token']
    return {
        'Authorization': f'Bearer {token}',
        'X-API-Key': 'test-admin-key',
        'X-Admin-Key': 'test-admin-key',
    }


def _make_writer(email: str):
    user = UserAccount(
        email=email,
        display_name='Writer',
        display_name_lower='writer',
        is_journalist=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.session.add(user)
    db.session.commit()
    return user


def _make_loaned_player(*, player_id, primary_team, loan_team=None, loan_team_name=None, window_key='2025-26::FULL'):
    loan = LoanedPlayer(
        player_id=player_id,
        player_name=f'Player {player_id}',
        primary_team_id=primary_team.id if primary_team else None,
        primary_team_name=primary_team.name if primary_team else 'Unknown',
        loan_team_id=loan_team.id if loan_team else None,
        loan_team_name=loan_team_name or (loan_team.name if loan_team else 'Custom Loan Team'),
        window_key=window_key,
        is_active=True,
        stats_coverage='limited',
    )
    db.session.add(loan)
    db.session.commit()
    return loan


def test_writer_loan_destination_coverage_workflow(client, app, monkeypatch):
    monkeypatch.setenv('ADMIN_API_KEY', 'test-admin-key')

    parent = Team(team_id=100, name='Man United', country='England', season=2025)
    loan_team = Team(team_id=200, name='Falkirk', country='Scotland', season=2025)
    db.session.add_all([parent, loan_team])
    db.session.commit()

    writer = _make_writer('loan-writer@example.com')
    loan = _make_loaned_player(player_id=1001, primary_team=parent, loan_team=loan_team)

    resp = client.post(
        '/api/writer/coverage-requests',
        headers=_writer_headers(writer.email),
        json={
            'coverage_type': 'loan_team',
            'team_id': loan_team.id,
            'team_name': loan_team.name,
        },
    )
    assert resp.status_code == 201
    request_id = resp.get_json()['request']['id']

    resp = client.post(
        f'/api/admin/coverage-requests/{request_id}/approve',
        headers=_admin_headers(),
    )
    assert resp.status_code == 200

    assignment = JournalistLoanTeamAssignment.query.filter_by(user_id=writer.id, loan_team_id=loan_team.id).first()
    assert assignment is not None

    resp = client.get('/api/writer/teams', headers=_writer_headers(writer.email))
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload['loan_team_assignments']
    assert payload['loan_team_assignments'][0]['loan_team_name'] == loan_team.name

    resp = client.get('/api/writer/available-players', headers=_writer_headers(writer.email))
    assert resp.status_code == 200
    players = resp.get_json()
    assert any(p['player_id'] == loan.player_id for p in players['players'])
    assert loan_team.name in players['by_loan_team']


def test_writer_parent_club_coverage_workflow(client, app, monkeypatch):
    monkeypatch.setenv('ADMIN_API_KEY', 'test-admin-key')

    parent = Team(team_id=300, name='Celtic', country='Scotland', season=2025)
    loan_team = Team(team_id=400, name='Sunderland', country='England', season=2025)
    db.session.add_all([parent, loan_team])
    db.session.commit()

    writer = _make_writer('parent-writer@example.com')
    loan = _make_loaned_player(player_id=2001, primary_team=parent, loan_team=loan_team, window_key='2025-26::ALT')

    resp = client.post(
        '/api/writer/coverage-requests',
        headers=_writer_headers(writer.email),
        json={
            'coverage_type': 'parent_club',
            'team_id': parent.id,
            'team_name': parent.name,
        },
    )
    assert resp.status_code == 201
    request_id = resp.get_json()['request']['id']

    resp = client.post(
        f'/api/admin/coverage-requests/{request_id}/approve',
        headers=_admin_headers(),
    )
    assert resp.status_code == 200

    assignment = JournalistTeamAssignment.query.filter_by(user_id=writer.id, team_id=parent.id).first()
    assert assignment is not None

    resp = client.get('/api/writer/teams', headers=_writer_headers(writer.email))
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload['parent_club_assignments']
    assert payload['parent_club_assignments'][0]['team_name'] == parent.name

    resp = client.get('/api/writer/available-players', headers=_writer_headers(writer.email))
    assert resp.status_code == 200
    players = resp.get_json()
    assert any(p['player_id'] == loan.player_id for p in players['players'])
    assert parent.name in players['by_parent_club']


def test_writer_coverage_request_cancel_and_deny(client, app, monkeypatch):
    monkeypatch.setenv('ADMIN_API_KEY', 'test-admin-key')

    loan_team = Team(team_id=500, name='Custom Town', country='England', season=2025)
    db.session.add(loan_team)
    db.session.commit()

    writer = _make_writer('cancel-writer@example.com')

    resp = client.post(
        '/api/writer/coverage-requests',
        headers=_writer_headers(writer.email),
        json={
            'coverage_type': 'loan_team',
            'team_id': loan_team.id,
            'team_name': loan_team.name,
        },
    )
    assert resp.status_code == 201
    request_id = resp.get_json()['request']['id']

    resp = client.delete(
        f'/api/writer/coverage-requests/{request_id}',
        headers=_writer_headers(writer.email),
    )
    assert resp.status_code == 200
    assert WriterCoverageRequest.query.get(request_id) is None

    resp = client.post(
        '/api/writer/coverage-requests',
        headers=_writer_headers(writer.email),
        json={
            'coverage_type': 'loan_team',
            'team_name': 'Made Up FC',
        },
    )
    assert resp.status_code == 201
    request_id = resp.get_json()['request']['id']

    resp = client.post(
        f'/api/admin/coverage-requests/{request_id}/deny',
        headers=_admin_headers(),
        json={'reason': 'Not enough activity'},
    )
    assert resp.status_code == 200
    denied = WriterCoverageRequest.query.get(request_id)
    assert denied.status == 'denied'
    assert denied.denial_reason == 'Not enough activity'

    # Denied requests should not create assignments
    assert JournalistLoanTeamAssignment.query.filter_by(user_id=writer.id, loan_team_name='Made Up FC').first() is None


def test_commentary_access_parent_club_allows_intro_and_player(client, app, monkeypatch):
    parent = Team(team_id=600, name='Parent FC', country='England', season=2025)
    loan_team = Team(team_id=700, name='Loan Town', country='England', season=2025)
    db.session.add_all([parent, loan_team])
    db.session.commit()

    writer = _make_writer('parent-commentary@example.com')
    db.session.add(JournalistTeamAssignment(user_id=writer.id, team_id=parent.id))
    db.session.commit()

    loan = _make_loaned_player(player_id=3001, primary_team=parent, loan_team=loan_team)

    resp = client.post(
        '/api/writer/commentaries',
        headers=_writer_headers(writer.email),
        json={
            'team_id': parent.id,
            'commentary_type': 'intro',
            'content': '<p>Intro</p>',
        },
    )
    assert resp.status_code == 201

    resp = client.post(
        '/api/writer/commentaries',
        headers=_writer_headers(writer.email),
        json={
            'team_id': parent.id,
            'commentary_type': 'player',
            'player_id': loan.player_id,
            'content': '<p>Player notes</p>',
        },
    )
    assert resp.status_code == 201


def test_commentary_access_loan_team_allows_player_only(client, app, monkeypatch):
    parent = Team(team_id=800, name='Primary FC', country='Scotland', season=2025)
    loan_team = Team(team_id=900, name='Destination FC', country='Scotland', season=2025)
    db.session.add_all([parent, loan_team])
    db.session.commit()

    writer = _make_writer('loan-commentary@example.com')
    db.session.add(JournalistLoanTeamAssignment(user_id=writer.id, loan_team_id=loan_team.id, loan_team_name=loan_team.name))
    db.session.commit()

    loan = _make_loaned_player(player_id=4001, primary_team=parent, loan_team=loan_team)

    resp = client.post(
        '/api/writer/commentaries',
        headers=_writer_headers(writer.email),
        json={
            'team_id': parent.id,
            'commentary_type': 'player',
            'player_id': loan.player_id,
            'content': '<p>Loan team coverage</p>',
        },
    )
    assert resp.status_code == 201

    resp = client.post(
        '/api/writer/commentaries',
        headers=_writer_headers(writer.email),
        json={
            'team_id': parent.id,
            'commentary_type': 'summary',
            'content': '<p>Summary</p>',
        },
    )
    assert resp.status_code == 403


def test_commentary_invalid_type_returns_400(client, app):
    team = Team(team_id=1000, name='Type FC', country='England', season=2025)
    db.session.add(team)
    db.session.commit()

    writer = _make_writer('invalid-type@example.com')
    db.session.add(JournalistTeamAssignment(user_id=writer.id, team_id=team.id))
    db.session.commit()

    resp = client.post(
        '/api/writer/commentaries',
        headers=_writer_headers(writer.email),
        json={
            'team_id': team.id,
            'commentary_type': 'invalid',
            'content': '<p>Bad type</p>',
        },
    )
    assert resp.status_code == 400


def test_commentary_missing_player_id_returns_400(client, app):
    team = Team(team_id=1001, name='Missing Player FC', country='England', season=2025)
    db.session.add(team)
    db.session.commit()

    writer = _make_writer('missing-player@example.com')
    db.session.add(JournalistTeamAssignment(user_id=writer.id, team_id=team.id))
    db.session.commit()

    resp = client.post(
        '/api/writer/commentaries',
        headers=_writer_headers(writer.email),
        json={
            'team_id': team.id,
            'commentary_type': 'player',
            'content': '<p>No player</p>',
        },
    )
    assert resp.status_code == 400


def test_commentary_requires_journalist_role(client, app):
    team = Team(team_id=1002, name='Auth FC', country='England', season=2025)
    db.session.add(team)
    db.session.commit()

    user = UserAccount(
        email='not-writer@example.com',
        display_name='Not Writer',
        display_name_lower='not writer',
        is_journalist=False,
    )
    db.session.add(user)
    db.session.commit()

    resp = client.post(
        '/api/writer/commentaries',
        headers=_writer_headers(user.email),
        json={
            'team_id': team.id,
            'commentary_type': 'summary',
            'content': '<p>No access</p>',
        },
    )
    assert resp.status_code == 403
