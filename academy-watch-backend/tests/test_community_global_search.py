"""Global search adds community adults without exposing private identities."""

from datetime import UTC, date, datetime

import pytest
from src.models.league import db
from src.models.player_suppression import PlayerSuppression
from src.models.showcase import LocalPlayer


def local_player(pid, **changes):
    row = LocalPlayer(
        id=pid,
        api_player_id=-pid,
        display_name=f"Test Reuben {pid}",
        normalized_name=f"test reuben {pid}",
        birth_date=date(2000, 1, 1),
        birth_year=2000,
        status="approved",
        provenance="user",
        position="Right winger",
        club_name="Test Club",
    )
    for key, value in changes.items():
        setattr(row, key, value)
    db.session.add(row)
    db.session.commit()
    return row


def test_global_search_includes_public_community_adult(app, client):
    local_player(71)
    results = client.get("/api/players/search?q=Reuben").get_json()
    assert results == [
        {
            "player_api_id": -71,
            "player_name": "Test Reuben 71",
            "photo_url": None,
            "position": "Right winger",
            "team_name": None,
            "current_club_name": "Test Club",
        }
    ]
    assert client.get("/api/players/search?q=R").get_json() == []


@pytest.mark.parametrize(
    "changes",
    [
        {"birth_date": date(datetime.now(UTC).year - 16, 1, 1)},
        {"birth_date": None, "birth_year": datetime.now(UTC).year - 18},
        {"birth_date": None, "birth_year": None},
        {"provenance": "club"},
        {"status": "pending"},
        {"status": "rejected"},
        {"merged_into_local_player_id": 72},
        {"api_player_id": None},
    ],
)
def test_global_search_never_exposes_private_or_uncertain_adult(app, client, changes):
    local_player(71, **changes)
    assert client.get("/api/players/search?q=Reuben").get_json() == []


def test_global_search_rechecks_suppression(app, client):
    local_player(71)
    db.session.add(
        PlayerSuppression(
            local_player_id=71,
            status="active",
            reason_code="player_request",
            requester_role="player",
            requester_contact="test@example.com",
            request_statement="Hide my profile",
        )
    )
    db.session.commit()
    assert client.get("/api/players/search?q=Reuben").get_json() == []


def test_global_search_hides_held_club_and_restores_after_lift(app, client):
    from src.models.funding import ClubProgram, FundingLeague

    league = FundingLeague(
        name="Test League",
        country="JP",
        region="Test",
        level="recreational",
        gender_program="both",
        season_calendar="calendar_year",
        data_tier="self_reported",
        registry_status="approved",
        admission_state="open",
    )
    db.session.add(league)
    db.session.flush()
    program = ClubProgram(
        funding_league_id=league.id,
        name="Test Club",
        legal_name="Test Club",
        slug="test-club",
        country="JP",
        region="Test",
        platform_status="approved",
        emergency_hidden=True,
    )
    db.session.add(program)
    db.session.flush()
    local_player(71, origin_program_id=program.id)
    assert client.get("/api/players/search?q=Reuben").get_json() == []
    program.emergency_hidden = False
    db.session.commit()
    assert client.get("/api/players/search?q=Reuben").get_json()[0]["player_api_id"] == -71
