from datetime import datetime, timezone

from src.admin.sandbox_tasks import run_task as sandbox_run_task, SandboxContext
from src.models.league import db, Team, LoanedPlayer, Player, SupplementalLoan


def _create_team(team_id: int, name: str) -> Team:
    team = Team(
        team_id=team_id,
        name=name,
        country='England',
        season=2025,
    )
    db.session.add(team)
    db.session.commit()
    return team


def _create_loan(player_id: int, player_name: str, parent: Team, loan_team: Team) -> LoanedPlayer:
    loan = LoanedPlayer(
        player_id=player_id,
        player_name=player_name,
        primary_team_id=parent.id,
        primary_team_name=parent.name,
        loan_team_id=loan_team.id,
        loan_team_name=loan_team.name,
        team_ids=f"{parent.team_id},{loan_team.team_id}",
        window_key='2025-26::FULL',
        is_active=True,
    )
    db.session.add(loan)
    db.session.commit()
    return loan


def test_sandbox_sofascore_tasks_list_and_update(app):
    with app.app_context():
        parent = _create_team(100, 'Manchester United')
        loan_team = _create_team(200, 'Newport County')
        _create_loan(777, 'Harrison Ogunneye', parent, loan_team)

        context = SandboxContext(db_session=db.session, api_client=None)

        first = sandbox_run_task('list-missing-sofascore-ids', {}, context)
        assert first['status'] == 'ok'
        payload = first['payload']
        players = payload.get('players') or []
        assert any(p['player_id'] == 777 for p in players), 'Expected player without Sofascore id to appear'

        update = sandbox_run_task(
            'update-player-sofascore-id',
            {'player_id': 777, 'sofascore_id': 1101989},
            context,
        )
        assert update['status'] == 'ok'

        record = Player.query.filter_by(player_id=777).one()
        assert record.sofascore_id == 1101989

        follow_up = sandbox_run_task('list-missing-sofascore-ids', {}, context)
        assert follow_up['status'] == 'ok'
        ids = [p['player_id'] for p in follow_up['payload'].get('players') or []]
        assert 777 not in ids, 'Player should no longer be reported missing after assignment'


def test_update_sofascore_for_supplemental_without_api_id(app):
    with app.app_context():
        parent = _create_team(300, 'Parent FC')
        loan_team = _create_team(301, 'Loan FC')

        supplemental = SupplementalLoan(
            player_name='Jordan Loan',
            parent_team_id=parent.id,
            parent_team_name=parent.name,
            loan_team_id=loan_team.id,
            loan_team_name=loan_team.name,
            season_year=2025,
            sofascore_player_id=None,
        )
        db.session.add(supplemental)
        db.session.commit()

        context = SandboxContext(db_session=db.session, api_client=None)

        listed = sandbox_run_task('list-missing-sofascore-ids', {}, context)
        supp_rows = [row for row in listed['payload'].get('players') or [] if row.get('is_supplemental')]
        assert any(row.get('supplemental_id') == supplemental.id for row in supp_rows)

        result = sandbox_run_task(
            'update-player-sofascore-id',
            {'supplemental_id': supplemental.id, 'sofascore_id': 1101989},
            context,
        )
        assert result['status'] == 'ok'

        refreshed = SupplementalLoan.query.get(supplemental.id)
        assert refreshed.sofascore_player_id == 1101989
