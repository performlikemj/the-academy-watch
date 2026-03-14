
from datetime import datetime, timedelta, timezone

from src.models.league import db, LoanedPlayer, Team


def test_teams_endpoint_dedupes_active_loans(client):
    parent = Team(
        team_id=33,
        name='Manchester United',
        country='England',
        season=2024,
    )
    borrower = Team(
        team_id=44,
        name='Nottingham Forest',
        country='England',
        season=2024,
    )
    db.session.add_all([parent, borrower])
    db.session.commit()

    base_time = datetime(2024, 8, 1, tzinfo=timezone.utc)

    loan_a = LoanedPlayer(
        player_id=101,
        player_name='Loan Star',
        primary_team_id=parent.id,
        primary_team_name=parent.name,
        loan_team_id=borrower.id,
        loan_team_name=borrower.name,
        window_key='2024-25::INITIAL',
        is_active=True,
        data_source='test',
        created_at=base_time,
        updated_at=base_time,
    )
    loan_b = LoanedPlayer(
        player_id=101,
        player_name='Loan Star',
        primary_team_id=parent.id,
        primary_team_name=parent.name,
        loan_team_id=borrower.id,
        loan_team_name=borrower.name,
        window_key='2024-25::WINTER',
        is_active=True,
        data_source='test',
        created_at=base_time + timedelta(days=30),
        updated_at=base_time + timedelta(days=30),
    )
    db.session.add_all([loan_a, loan_b])
    db.session.commit()

    resp = client.get('/api/teams')
    assert resp.status_code == 200
    payload = resp.get_json()
    manu = next(item for item in payload if item['team_id'] == parent.team_id)
    assert manu['current_loaned_out_count'] == 1

    detail_resp = client.get(f'/api/teams/{parent.id}')
    assert detail_resp.status_code == 200
    detail = detail_resp.get_json()
    assert len(detail['active_loans']) == 1
    assert detail['active_loans'][0]['window_key'] == '2024-25::WINTER'


def test_team_loans_endpoint_dedupes_active_rows_by_default(client):
    parent = Team(
        team_id=33,
        name='Manchester United',
        country='England',
        season=2024,
    )
    borrower = Team(
        team_id=44,
        name='Nottingham Forest',
        country='England',
        season=2024,
    )
    db.session.add_all([parent, borrower])
    db.session.commit()

    base_time = datetime(2024, 8, 1, tzinfo=timezone.utc)

    older = LoanedPlayer(
        player_id=101,
        player_name='Loan Star',
        primary_team_id=parent.id,
        primary_team_name=parent.name,
        loan_team_id=borrower.id,
        loan_team_name=borrower.name,
        window_key='2024-25::INITIAL',
        is_active=True,
        data_source='test',
        created_at=base_time,
        updated_at=base_time,
    )
    newer = LoanedPlayer(
        player_id=101,
        player_name='Loan Star',
        primary_team_id=parent.id,
        primary_team_name=parent.name,
        loan_team_id=borrower.id,
        loan_team_name=borrower.name,
        window_key='2024-25::WINTER',
        is_active=True,
        data_source='test',
        created_at=base_time + timedelta(days=30),
        updated_at=base_time + timedelta(days=30),
    )
    db.session.add_all([older, newer])
    db.session.commit()

    resp = client.get(f'/api/teams/{parent.id}/loans')
    assert resp.status_code == 200
    payload = resp.get_json()
    assert isinstance(payload, list)
    assert len(payload) == 1
    assert payload[0]['window_key'] == '2024-25::WINTER'

    # Allow turning dedupe off for diagnostics.
    resp = client.get(f'/api/teams/{parent.id}/loans?active_only=false&dedupe=false')
    assert resp.status_code == 200
    payload = resp.get_json()
    assert isinstance(payload, list)
    assert len(payload) == 2
