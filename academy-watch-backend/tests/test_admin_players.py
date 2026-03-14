import pytest

from src.models.league import db, LoanedPlayer, Team
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


def _create_team(name: str, api_team_id: int, season: int = 2024):
    team = Team(
        team_id=api_team_id,
        name=name,
        country='England',
        season=season,
    )
    db.session.add(team)
    db.session.commit()
    return team


def _seed_loan(player_id: int, player_name: str, parent_team: Team, loan_team: Team, window_key: str):
    loan = LoanedPlayer(
        player_id=player_id,
        player_name=player_name,
        primary_team_id=parent_team.id,
        primary_team_name=parent_team.name,
        loan_team_id=loan_team.id,
        loan_team_name=loan_team.name,
        window_key=window_key,
        data_source='api-football',
        can_fetch_stats=True,
    )
    db.session.add(loan)
    db.session.commit()
    return loan


def test_admin_player_update_propagates_name_to_loans_and_listing(client):
    parent = _create_team('Manchester United', 33)
    loan_a = _create_team('West Brom', 90)
    loan_b = _create_team('Sunderland', 91)

    _seed_loan(18, 'Player 18', parent, loan_a, '2024-25::FULL')
    _seed_loan(18, 'Player 18', parent, loan_b, '2023-24::FULL')

    resp = client.put('/admin/players/18', headers=_auth_headers(), json={'name': 'Kobbie Mainoo'})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['player']['name'] == 'Kobbie Mainoo'

    loans = LoanedPlayer.query.filter_by(player_id=18).order_by(LoanedPlayer.id.asc()).all()
    assert len(loans) == 2
    for loan in loans:
        assert loan.player_name == 'Kobbie Mainoo'

    listing = client.get('/admin/players', headers=_auth_headers())
    assert listing.status_code == 200
    payload = listing.get_json()
    assert len(payload['items']) == 1
    assert payload['items'][0]['player_name'] == 'Kobbie Mainoo'
