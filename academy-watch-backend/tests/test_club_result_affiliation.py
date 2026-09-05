"""Club result authority is checked atomically at entry time, never at rebuild."""

from datetime import UTC, date, datetime
from unittest.mock import patch

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session
from src.models.funding import ClubProgram
from src.models.league import Team, db
from src.models.player_match_entry import PlayerMatchEntry
from src.models.season_rollup import PlayerSeasonCell, PlayerSeasonTotal
from src.models.showcase import PlayerClubAffiliation, PlayerProfileClaim
from src.models.tracked_player import TrackedPlayer
from src.routes import club as club_routes
from src.services import season_rollup_service
from src.services.club_player_authority import club_authorized_player_ids, club_has_authority_over_player
from src.utils.academy_window import current_stats_season
from test_club_console import (
    _active_suppression,
    _add_api_member,
    _add_local_member,
    _admin_headers,
    _grant_program_manager,
    _headers,
    _local,
    _result_payload,
)
from test_club_console import client as client
from test_club_console import club_app as club_app


def _unrelated_player(club_app, player_api_id=7100):
    team = Team.query.filter_by(team_id=9922).first()
    if team is None:
        team = Team(team_id=9922, name="Other Academy", country="Japan", season=2026)
        db.session.add(team)
        db.session.flush()
    player = TrackedPlayer(
        player_api_id=player_api_id,
        player_name=f"Affiliation Test Player {player_api_id}",
        birth_date="2000-01-01",
        team_id=team.id,
        current_club_api_id=team.team_id,
    )
    db.session.add(player)
    db.session.commit()
    assert team.id != team.team_id
    return player


def _post(client, program_id, member_ids, **header):
    return client.post(
        f"/api/club/{program_id}/results",
        json=_result_payload(member_ids, **header),
        headers=_headers("a"),
    )


def _snapshot(model):
    return [
        {column.name: getattr(row, column.name) for column in model.__table__.columns}
        for row in model.query.order_by(model.id).all()
    ]


def test_private_attachment_cannot_publish_any_part_of_mixed_lineup(club_app, client):
    program_id = club_app.c2["program_a"]
    valid = _add_api_member(client, program_id)
    offenders = [_unrelated_player(club_app, player_id) for player_id in (7102, 7101)]
    member_ids = []
    for player in offenders:
        response = client.post(
            f"/api/club/{program_id}/roster",
            json={"player_api_id": player.player_api_id},
            headers=_headers("a"),
        )
        assert response.status_code == 201
        assert response.json["member"]["public_stats_allowed"] is False
        member_ids.append(response.json["member"]["id"])
    roster = client.get(f"/api/club/{program_id}/roster", headers=_headers("a"))
    assert roster.status_code == 200
    assert {row["player_api_id"]: row["public_stats_allowed"] for row in roster.json["members"]} == {
        7001: True,
        7101: False,
        7102: False,
    }
    with patch.object(season_rollup_service, "refresh_player") as refresh:
        response = _post(client, program_id, [valid, *member_ids])
    assert response.status_code == 422
    assert response.json == {"error": "player_not_affiliated", "player_api_ids": [7101, 7102]}
    refresh.assert_not_called()
    assert PlayerMatchEntry.query.count() == 0
    for player in offenders:
        season_rollup_service.refresh_player(player.player_api_id, 2025, session=db.session)
    assert PlayerSeasonCell.query.filter_by(source="club").count() == 0
    assert PlayerSeasonTotal.query.count() == 0


@pytest.mark.parametrize("authority", ["current", "second-academy-row"])
def test_provider_authority_uses_provider_ids_and_all_tracked_rows(club_app, client, authority):
    program_id = club_app.c2["program_a"]
    program = db.session.get(ClubProgram, program_id)
    player = _unrelated_player(club_app)
    assert player.team_id != program.team_api_id
    if authority == "current":
        player.current_club_api_id = program.team_api_id
    else:
        db.session.add(
            TrackedPlayer(
                player_api_id=player.player_api_id,
                player_name=player.player_name,
                birth_date=player.birth_date,
                team_id=club_app.c2["team"],
                current_club_api_id=9922,
                is_active=False,
            )
        )
    db.session.commit()
    member_id = _add_api_member(client, program_id, player.player_api_id)
    response = _post(client, program_id, [member_id])
    assert response.status_code == 201
    entry = PlayerMatchEntry.query.one()
    assert (entry.player_api_id, entry.source, entry.status, entry.club_program_id) == (
        player.player_api_id,
        "club",
        "club_confirmed",
        program_id,
    )


@pytest.mark.parametrize("status", ["self_reported", "club_confirmed", "pending", "rejected", "approved"])
@pytest.mark.parametrize("season", [None, "2025", "2025/26", "2024/25"])
def test_only_accepted_player_affiliations_for_result_season_authorize(club_app, client, status, season):
    program_id = club_app.c2["program_a"]
    program = db.session.get(ClubProgram, program_id)
    player = _unrelated_player(club_app)
    db.session.add(
        PlayerClubAffiliation(
            player_api_id=player.player_api_id,
            team_api_id=program.team_api_id,
            status=status,
            season=season,
        )
    )
    db.session.commit()
    member_id = _add_api_member(client, program_id, player.player_api_id)
    response = _post(client, program_id, [member_id])
    allowed = status in {"self_reported", "club_confirmed"} and season in {None, "2025", "2025/26"}
    assert response.status_code == (201 if allowed else 422)
    assert PlayerMatchEntry.query.count() == int(allowed)
    if not allowed:
        assert response.json == {"error": "player_not_affiliated", "player_api_ids": [player.player_api_id]}


@pytest.mark.parametrize("mismatch", ["player", "club", "database-id", "missing-program-team"])
def test_manager_claim_and_unrelated_affiliations_do_not_authorize(club_app, client, mismatch):
    program_id = club_app.c2["program_a"]
    program = db.session.get(ClubProgram, program_id)
    player = _unrelated_player(club_app)
    if mismatch == "database-id":
        program.team_api_id = player.team_id
    elif mismatch == "missing-program-team":
        program.team_api_id = None
    db.session.add(
        PlayerClubAffiliation(
            player_api_id=7001 if mismatch == "player" else player.player_api_id,
            team_api_id=program.team_api_id if mismatch == "player" else 9999,
            status="club_confirmed",
        )
    )
    db.session.commit()
    member_id = _add_api_member(client, program_id, player.player_api_id)
    response = _post(client, program_id, [member_id])
    assert response.status_code == 422
    assert PlayerMatchEntry.query.count() == 0


@pytest.mark.parametrize("include_transferred", [False, True], ids=["omitted", "submitted"])
def test_confirmed_fixture_remains_correctable_after_transfer(club_app, client, include_transferred):
    program_id = club_app.c2["program_a"]
    program = db.session.get(ClubProgram, program_id)
    player = _unrelated_player(club_app)
    player.current_club_api_id = program.team_api_id
    db.session.commit()
    valid = _add_api_member(client, program_id)
    omitted = _add_api_member(client, program_id, player.player_api_id)
    assert _post(client, program_id, [valid, omitted]).status_code == 201
    player.current_club_api_id = 9922
    db.session.commit()
    before = _snapshot(PlayerMatchEntry)
    lineup = [valid, omitted] if include_transferred else [valid]
    response = _post(client, program_id, lineup, result_for=5)
    assert response.status_code == 200
    after = _snapshot(PlayerMatchEntry)
    assert len(after) == len(before) == 2
    for original, corrected in zip(before, after, strict=True):
        assert corrected["result_for"] == 5
        assert {key: value for key, value in corrected.items() if key not in {"result_for", "updated_at"}} == {
            key: value for key, value in original.items() if key not in {"result_for", "updated_at"}
        }

    # The grandfathered player does not authorize a new unrelated teammate.
    newcomer = _unrelated_player(club_app, 7101)
    new_member = _add_api_member(client, program_id, newcomer.player_api_id)
    models = (PlayerMatchEntry, PlayerSeasonCell, PlayerSeasonTotal)
    before_rejection = [_snapshot(model) for model in models]
    with patch.object(season_rollup_service, "refresh_player") as refresh:
        response = _post(client, program_id, [*lineup, new_member], result_for=6, competition="Corrected League")
    assert response.status_code == 422
    assert response.json == {"error": "player_not_affiliated", "player_api_ids": [newcomer.player_api_id]}
    refresh.assert_not_called()
    assert [_snapshot(model) for model in models] == before_rejection

    # The same transferred player still needs authority for a different fixture.
    response = _post(client, program_id, [omitted], opponent="Another Fixture")
    assert response.status_code == 422
    assert response.json == {"error": "player_not_affiliated", "player_api_ids": [player.player_api_id]}
    assert [_snapshot(model) for model in models] == before_rejection


def test_transfer_does_not_revoke_historical_rollup(club_app, client):
    program_id = club_app.c2["program_a"]
    program = db.session.get(ClubProgram, program_id)
    player = _unrelated_player(club_app)
    player.current_club_api_id = program.team_api_id
    db.session.commit()
    member_id = _add_api_member(client, program_id, player.player_api_id)
    assert _post(client, program_id, [member_id]).status_code == 201
    player.current_club_api_id = 9922
    db.session.commit()
    assert not club_has_authority_over_player(program, player.player_api_id, season=2025, session=db.session)
    season_rollup_service.refresh_player(player.player_api_id, 2025, session=db.session)
    db.session.commit()
    total = PlayerSeasonTotal.query.filter_by(player_api_id=player.player_api_id, season=2025).one()
    assert (total.primary_source, total.appearances, total.minutes, total.goals) == ("club", 1, 90, 1)
    assert PlayerSeasonCell.query.filter_by(player_api_id=player.player_api_id, source="club").count() == 1


def test_local_creator_attachment_and_second_manager_result_access_unchanged(club_app, client):
    program_id = club_app.c2["program_a"]
    local = _local(club_app.c2["users"]["a"], birth_year=2000, status="approved")
    local.api_player_id = -local.id
    db.session.commit()
    _grant_program_manager(program_id, club_app.c2["users"]["b"])
    foreign_attach = client.post(
        f"/api/club/{program_id}/roster", json={"local_player_id": local.id}, headers=_headers("b")
    )
    assert foreign_attach.status_code == 404
    member_id = _add_local_member(client, program_id, local.id)
    roster = client.get(f"/api/club/{program_id}/roster", headers=_headers("b"))
    assert roster.json["members"][0]["public_stats_allowed"] is True
    assert _post(client, program_id, [member_id]).status_code == 201
    response = client.post(
        f"/api/club/{program_id}/results",
        json=_result_payload([member_id], result_for=4),
        headers=_headers("b"),
    )
    assert response.status_code == 200
    entry = PlayerMatchEntry.query.one()
    assert (entry.player_api_id, entry.status, entry.result_for) == (-local.id, "club_confirmed", 4)


@pytest.mark.parametrize("kind", ["minor-tracked", "minor-local", "pending-local", "suppressed", "missing"])
def test_roster_public_stats_flag_is_false_for_unavailable_or_private_members(club_app, client, kind):
    program_id = club_app.c2["program_a"]
    if kind in {"minor-local", "pending-local"}:
        local = _local(
            club_app.c2["users"]["a"],
            birth_year=datetime.now(UTC).year - 15 if kind == "minor-local" else 2000,
            status="approved" if kind == "minor-local" else "pending",
        )
        if kind == "minor-local":
            local.api_player_id = -local.id
            db.session.commit()
        _add_local_member(client, program_id, local.id)
    else:
        _add_api_member(client, program_id)
        player = TrackedPlayer.query.filter_by(player_api_id=7001).one()
        if kind == "minor-tracked":
            player.birth_date = f"{datetime.now(UTC).year - 15}-01-01"
        elif kind == "suppressed":
            _active_suppression(player_api_id=7001)
        else:
            db.session.delete(player)
        db.session.commit()
    response = client.get(f"/api/club/{program_id}/roster", headers=_headers("a"))
    assert response.status_code == 200
    assert response.json["members"][0]["public_stats_allowed"] is False
    assert response.json["members"][0]["available"] is (kind not in {"suppressed", "missing"})


def test_roster_affiliation_flag_uses_current_season_and_helper_accepts_plain_session(club_app, client):
    program_id = club_app.c2["program_a"]
    player = _unrelated_player(club_app)
    affiliation = PlayerClubAffiliation(
        player_api_id=player.player_api_id, team_api_id=9911, status="self_reported", season=str(current_stats_season())
    )
    db.session.add(affiliation)
    db.session.commit()
    _add_api_member(client, program_id, player.player_api_id)
    roster = client.get(f"/api/club/{program_id}/roster", headers=_headers("a"))
    assert roster.json["members"][0]["public_stats_allowed"] is True
    with Session(db.engine) as session:
        program = session.get(ClubProgram, program_id)
        assert club_has_authority_over_player(
            program, player.player_api_id, season=current_stats_season(), session=session
        )
    affiliation.season = str(current_stats_season() - 1)
    db.session.commit()
    roster = client.get(f"/api/club/{program_id}/roster", headers=_headers("a"))
    assert roster.json["members"][0]["public_stats_allowed"] is False


def test_owner_submitted_real_format_affiliation_authorizes_after_approval(club_app, client):
    program_id = club_app.c2["program_a"]
    player = _unrelated_player(club_app)
    db.session.add(
        PlayerProfileClaim(
            player_api_id=player.player_api_id,
            user_account_id=club_app.c2["users"]["a"],
            relationship_type="player",
            status="approved",
        )
    )
    db.session.commit()
    member_id = _add_api_member(client, program_id, player.player_api_id)
    submitted = client.post(
        f"/api/players/{player.player_api_id}/showcase/affiliations",
        json={"team_api_id": 9911, "season": " <b>2025/26</b> "},
        headers=_headers("a"),
    )
    assert submitted.status_code == 201
    affiliation = submitted.json["affiliation"]
    assert (affiliation["season"], affiliation["status"]) == ("2025/26", "pending")
    assert _post(client, program_id, [member_id]).status_code == 422
    approved = client.post(
        f"/api/admin/showcase/affiliations/{affiliation['id']}/review",
        json={"action": "approve"},
        headers=_admin_headers(),
    )
    assert approved.status_code == 200
    assert approved.json["affiliation"]["season"] == "2025/26"
    assert approved.json["affiliation"]["status"] == "self_reported"
    assert _post(client, program_id, [member_id]).status_code == 201
    assert PlayerMatchEntry.query.one().status == "club_confirmed"


@pytest.mark.parametrize(
    ("season", "allowed"),
    [
        ("2024", False),
        ("2025/2026", True),
        ("2025-26", True),
        ("2025-2026", True),
        ("2025/27", False),
        ("2025/1926", False),
        ("2025/2027", False),
        ("2025/26 extra", False),
        ("", False),
        ("unknown", False),
    ],
)
def test_affiliation_year_ranges_fail_closed_for_invalid_seasons(club_app, client, season, allowed):
    program_id = club_app.c2["program_a"]
    player = _unrelated_player(club_app)
    db.session.add(
        PlayerClubAffiliation(
            player_api_id=player.player_api_id, team_api_id=9911, status="self_reported", season=season
        )
    )
    db.session.commit()
    member_id = _add_api_member(client, program_id, player.player_api_id)
    response = _post(client, program_id, [member_id])
    assert response.status_code == (201 if allowed else 422)
    assert PlayerMatchEntry.query.count() == int(allowed)


def test_unconfirmed_existing_fixture_player_is_not_grandfathered(club_app, client):
    program_id = club_app.c2["program_a"]
    player = _unrelated_player(club_app)
    player.current_club_api_id = 9911
    db.session.commit()
    valid = _add_api_member(client, program_id)
    omitted = _add_api_member(client, program_id, player.player_api_id)
    assert _post(client, program_id, [valid, omitted]).status_code == 201
    PlayerMatchEntry.query.filter_by(player_api_id=player.player_api_id).one().status = "disputed"
    player.current_club_api_id = 9922
    db.session.commit()
    models = (PlayerMatchEntry, PlayerSeasonCell, PlayerSeasonTotal)
    before = [_snapshot(model) for model in models]
    with patch.object(season_rollup_service, "refresh_player") as refresh:
        response = _post(client, program_id, [valid], result_for=5)
    assert response.status_code == 422
    assert response.json == {"error": "player_not_affiliated", "player_api_ids": [player.player_api_id]}
    refresh.assert_not_called()
    assert [_snapshot(model) for model in models] == before


@pytest.mark.parametrize("today", [date(2026, 7, 31), date(2026, 8, 1)])
def test_roster_authority_is_batched_and_shares_entry_season_basis(club_app, client, today):
    program_id = club_app.c2["program_a"]
    program = db.session.get(ClubProgram, program_id)
    affiliated = _unrelated_player(club_app, 7101)
    unrelated = _unrelated_player(club_app, 7102)
    db.session.add(
        PlayerClubAffiliation(
            player_api_id=affiliated.player_api_id, team_api_id=9911, status="self_reported", season="2025/26"
        )
    )
    db.session.commit()
    members = {
        player_id: _add_api_member(client, program_id, player_id)
        for player_id in (7001, affiliated.player_api_id, unrelated.player_api_id)
    }
    queries = []

    def record_query(_conn, _cursor, statement, _parameters, _context, _executemany):
        queries.append(statement)

    event.listen(db.engine, "before_cursor_execute", record_query)
    try:
        authorized = club_authorized_player_ids(
            program, members, season=current_stats_season(today), session=db.session
        )
    finally:
        event.remove(db.engine, "before_cursor_execute", record_query)
    assert len(queries) == 2
    assert "tracked_players" in queries[0] and "JOIN teams" in queries[0]
    assert "player_club_affiliations" in queries[1]
    assert authorized == ({7001, 7101} if today.month == 7 else {7001})

    with (
        patch.object(
            club_routes, "current_stats_season", side_effect=lambda value=None: current_stats_season(value or today)
        ),
        patch.object(club_routes, "club_authorized_player_ids", wraps=club_authorized_player_ids) as batch,
        patch.object(club_routes, "club_has_authority_over_player", side_effect=AssertionError("per-member lookup")),
    ):
        roster = client.get(f"/api/club/{program_id}/roster", headers=_headers("a"))
        assert roster.status_code == 200
        batch.assert_called_once_with(program, set(members), season=current_stats_season(today), session=db.session)
        assert {row["player_api_id"] for row in roster.json["members"] if row["public_stats_allowed"]} == authorized
        response = _post(client, program_id, [members[7101]], match_date=today.isoformat())
    assert response.status_code == (201 if 7101 in authorized else 422)
