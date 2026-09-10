"""The writer editor consumes public player IDs and parent-club database IDs."""

import pytest
from src.auth import issue_user_token
from src.models.league import JournalistLoanTeamAssignment, JournalistTeamAssignment, Team, UserAccount, db
from src.models.tracked_player import TrackedPlayer


@pytest.mark.parametrize("coverage", ["parent", "destination", "custom", "both"])
def test_available_players_preserves_writer_editor_contract(client, coverage):
    parent = Team(team_id=3300, name="Parent FC", country="England", season=2026)
    destination = Team(team_id=4400, name="Destination FC", country="England", season=2026)
    writer = UserAccount(
        email="coverage@example.test", display_name="Writer", display_name_lower="writer", is_journalist=True
    )
    db.session.add_all([parent, destination, writer])
    db.session.flush()
    player = TrackedPlayer(
        player_api_id=5500,
        player_name="Example Player",
        team_id=parent.id,
        current_club_db_id=None if coverage == "custom" else destination.id,
        current_club_name=destination.name,
        status="on_loan",
        is_active=True,
    )
    excluded = TrackedPlayer(
        player_api_id=6600,
        player_name="Inactive Player",
        team_id=parent.id,
        current_club_db_id=destination.id,
        current_club_name=destination.name,
        status="on_loan",
        is_active=False,
    )
    db.session.add_all([player, excluded])
    if coverage in {"parent", "both"}:
        db.session.add(JournalistTeamAssignment(user_id=writer.id, team_id=parent.id))
    if coverage in {"destination", "custom", "both"}:
        db.session.add(
            JournalistLoanTeamAssignment(
                user_id=writer.id,
                loan_team_id=None if coverage == "custom" else destination.id,
                loan_team_name=destination.name,
            )
        )
    db.session.commit()
    token = issue_user_token(writer.email)["token"]
    response = client.get("/api/writer/available-players", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    payload = response.get_json()
    assert set(payload) == {"players", "by_parent_club", "by_loan_team"}
    assert len(payload["players"]) == 1
    public = payload["players"][0]
    assert public["player_id"] == 5500
    assert public["player_name"] == "Example Player"
    assert public["primary_team_id"] == parent.id
    assert public["primary_team_api_id"] == 3300
    assert public["primary_team_name"] == parent.name
    assert public["loan_team_name"] == destination.name
    assert payload["by_parent_club"] == ({parent.name: [public]} if coverage in {"parent", "both"} else {})
    assert payload["by_loan_team"] == ({destination.name: [public]} if coverage != "parent" else {})
