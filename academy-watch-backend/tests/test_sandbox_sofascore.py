from src.admin.sandbox_tasks import SandboxContext
from src.admin.sandbox_tasks import run_task as sandbox_run_task
from src.models.league import Player, Team, db
from src.models.tracked_player import TrackedPlayer


def _create_team(team_id: int, name: str) -> Team:
    team = Team(
        team_id=team_id,
        name=name,
        country="England",
        season=2025,
    )
    db.session.add(team)
    db.session.commit()
    return team


def _create_loan(player_id: int, player_name: str, parent: Team, loan_team: Team) -> TrackedPlayer:
    loan = TrackedPlayer(
        status="on_loan",
        player_api_id=player_id,
        player_name=player_name,
        team_id=parent.id,
        current_club_db_id=loan_team.id,
        current_club_name=loan_team.name,
        is_active=True,
    )
    db.session.add(loan)
    db.session.commit()
    return loan


def test_sandbox_sofascore_tasks_list_and_update(app):
    with app.app_context():
        parent = _create_team(100, "Manchester United")
        loan_team = _create_team(200, "Newport County")
        _create_loan(777, "Harrison Ogunneye", parent, loan_team)

        context = SandboxContext(db_session=db.session, api_client=None)

        first = sandbox_run_task("list-missing-sofascore-ids", {}, context)
        assert first["status"] == "ok"
        payload = first["payload"]
        players = payload.get("players") or []
        assert any(p["player_id"] == 777 for p in players), "Expected player without Sofascore id to appear"

        update = sandbox_run_task(
            "update-player-sofascore-id",
            {"player_id": 777, "sofascore_id": 1101989},
            context,
        )
        assert update["status"] == "ok"

        record = Player.query.filter_by(player_id=777).one()
        assert record.sofascore_id == 1101989

        follow_up = sandbox_run_task("list-missing-sofascore-ids", {}, context)
        assert follow_up["status"] == "ok"
        ids = [p["player_id"] for p in follow_up["payload"].get("players") or []]
        assert 777 not in ids, "Player should no longer be reported missing after assignment"
