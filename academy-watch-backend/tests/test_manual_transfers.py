"""FC-T1 manual transfer entry regressions.

The suite is deliberately hermetic: the HTTP endpoint and the equivalent
API-shaped fixtures both enter the durable chronological transfer resolver,
while any attempt to construct an API-Football client fails the test.
"""

from __future__ import annotations

import importlib
from copy import deepcopy
from datetime import date, timedelta

import pytest
import sqlalchemy as sa
from flask import Flask
from sqlalchemy.dialects import postgresql
from src.models.funding import ClubProgram, FundingLeague
from src.models.journey import PlayerJourney, PlayerJourneyEntry
from src.models.league import Team, TeamProfile, db
from src.models.player_suppression import PlayerSuppression
from src.models.tracked_player import TrackedPlayer
from src.models.transfer_event import PlayerTransferEvent, TransferAdminEvent
from src.services.journey_sync import JourneySyncService
from src.services.transfer_events import record_transfer_events
from src.utils.academy_window import current_academy_season

ADMIN_KEY = "manual-transfer-admin-key"
ADMIN_EMAIL = "transfer-operator@example.com"
FERNET_KEY = "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="
PARENT_API_ID = 81_001
DESTINATION_API_ID = 81_002
EFFECTIVE_DATE = date.today().isoformat()


@pytest.fixture
def manual_app(monkeypatch):
    monkeypatch.setenv("SKIP_API_HANDSHAKE", "1")
    monkeypatch.setenv("API_USE_STUB_DATA", "true")
    monkeypatch.setenv("ADMIN_API_KEY", ADMIN_KEY)
    monkeypatch.setenv("ADMIN_IP_WHITELIST", "")
    monkeypatch.setenv("PLAYER_SUPPRESSION_ENCRYPTION_KEY", FERNET_KEY)

    from src.routes.journey import journey_bp

    flask_app = Flask(__name__)
    flask_app.config.update(
        TESTING=True,
        SECRET_KEY="manual-transfer-test-secret",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(flask_app)
    flask_app.register_blueprint(journey_bp, url_prefix="/api")

    with flask_app.app_context():
        # These models are imported explicitly above so their tables exist even
        # if the production route keeps its service imports local.
        db.create_all()

        def reject_api_client(*_args, **_kwargs):
            raise AssertionError("manual transfer entry must not construct an API-Football client")

        monkeypatch.setattr("src.services.journey_sync.APIFootballClient", reject_api_client)
        yield flask_app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(manual_app):
    return manual_app.test_client()


@pytest.fixture
def admin_headers(manual_app):
    from src.auth import issue_user_token

    token = issue_user_token(ADMIN_EMAIL, role="admin")["token"]
    return {
        "Authorization": f"Bearer {token}",
        "X-API-Key": ADMIN_KEY,
    }


@pytest.fixture
def clubs(manual_app):
    parent = Team(
        team_id=PARENT_API_ID,
        name="Northbridge FC",
        country="England",
        season=current_academy_season(),
        is_active=True,
    )
    destination = Team(
        team_id=DESTINATION_API_ID,
        name="Southbank Athletic",
        country="England",
        season=current_academy_season(),
        is_active=True,
    )
    db.session.add_all([parent, destination])
    db.session.commit()
    return parent, destination


def _seed_player(player_api_id: int, parent: Team) -> tuple[PlayerJourney, TrackedPlayer]:
    academy_season = current_academy_season() - 1
    journey = PlayerJourney(
        player_api_id=player_api_id,
        player_name=f"Prospect {player_api_id}",
        birth_date=f"{academy_season - 17}-02-03",
        origin_club_api_id=parent.team_id,
        origin_club_name=parent.name,
        origin_year=academy_season,
        current_club_api_id=parent.team_id,
        current_club_name=parent.name,
        current_level="U21",
        academy_club_ids=[parent.team_id],
        academy_last_seasons={str(parent.team_id): academy_season},
        seasons_synced=[academy_season],
    )
    db.session.add(journey)
    db.session.flush()
    db.session.add(
        PlayerJourneyEntry(
            journey_id=journey.id,
            player_api_id=player_api_id,
            season=academy_season,
            club_api_id=parent.team_id,
            club_name=parent.name,
            league_api_id=699,
            league_name="Development League",
            league_country="England",
            level="U21",
            entry_type="academy",
            is_youth=True,
            is_international=False,
            appearances=12,
            goals=1,
            assists=2,
            minutes=900,
            sort_priority=30,
        )
    )
    tracked = TrackedPlayer(
        player_api_id=player_api_id,
        player_name=journey.player_name,
        birth_date=journey.birth_date,
        team_id=parent.id,
        journey_id=journey.id,
        status="academy",
        current_level="U21",
        current_club_api_id=parent.team_id,
        current_club_name=parent.name,
        data_source="journey-sync",
        data_depth="full_stats",
        last_academy_season=academy_season,
        is_active=True,
    )
    db.session.add(tracked)
    db.session.commit()
    return journey, tracked


def _manual_body(player_api_id: int, transfer_type: str, *, dry_run: bool = False) -> dict:
    body = {
        "player_api_id": player_api_id,
        "from_team_api_id": PARENT_API_ID,
        "transfer_type": transfer_type,
        "effective_date": EFFECTIVE_DATE,
        "source_note": f"Confirmed by club release for {player_api_id}",
        "dry_run": dry_run,
    }
    if transfer_type != "released":
        body["to_team_api_id"] = DESTINATION_API_ID
    if transfer_type == "signed":
        body["fee_text"] = "Undisclosed"
    elif transfer_type == "sold":
        body["fee_text"] = "£1m"
    return body


def _api_event(transfer_type: str) -> dict:
    raw_type = {
        "signed": "Undisclosed",
        "loan": "Loan",
        "released": "Free agent",
        "sold": "£1m",
    }[transfer_type]
    destination = {} if transfer_type == "released" else {"id": DESTINATION_API_ID, "name": "Southbank Athletic"}
    return {
        "date": EFFECTIVE_DATE,
        "type": raw_type,
        "teams": {
            "out": {"id": PARENT_API_ID, "name": "Northbridge FC"},
            "in": destination,
        },
    }


def _state(player_api_id: int) -> dict:
    tracked = TrackedPlayer.query.filter_by(player_api_id=player_api_id).one()
    journey = PlayerJourney.query.filter_by(player_api_id=player_api_id).one()
    return {
        "tracked": {
            "status": tracked.status,
            "current_club_api_id": tracked.current_club_api_id,
            "current_club_name": tracked.current_club_name,
            "sale_fee": tracked.sale_fee,
            "is_active": tracked.is_active,
        },
        "journey": {
            "current_club_api_id": journey.current_club_api_id,
            "current_club_name": journey.current_club_name,
            "current_status": journey.current_status,
            "current_owner_api_id": journey.current_owner_api_id,
            "current_owner_name": journey.current_owner_name,
        },
    }


@pytest.mark.parametrize(
    ("transfer_type", "expected_status"),
    [
        ("signed", "sold"),
        ("loan", "on_loan"),
        ("released", "released"),
        ("sold", "sold"),
    ],
)
def test_manual_transfer_matches_equivalent_api_fed_status(
    client,
    admin_headers,
    clubs,
    transfer_type,
    expected_status,
):
    parent, _destination = clubs
    manual_player_id = 820_000
    api_player_id = 820_001
    _seed_player(manual_player_id, parent)
    _seed_player(api_player_id, parent)

    api_transfer = _api_event(transfer_type)
    assert record_transfer_events(api_player_id, [api_transfer], db.session) == 1
    api_journey = PlayerJourney.query.filter_by(player_api_id=api_player_id).one()
    result = JourneySyncService(database_only=True).reclassify_from_durable_transfer_events(api_journey)
    assert result is not None
    db.session.commit()

    response = client.post(
        "/api/admin/transfers/manual",
        json=_manual_body(manual_player_id, transfer_type),
        headers=admin_headers,
    )

    assert response.status_code == 200, response.get_json()
    payload = response.get_json()
    assert payload["dry_run"] is False
    assert payload["idempotent"] is False
    assert payload["affected_rows"][0]["would_be_status"] == expected_status
    assert _state(manual_player_id) == _state(api_player_id)
    assert _state(manual_player_id)["tracked"]["status"] == expected_status


def test_dry_run_matches_commit_and_writes_nothing(client, admin_headers, clubs):
    parent, _destination = clubs
    player_api_id = 820_010
    _seed_player(player_api_id, parent)
    before = _state(player_api_id)
    dry_body = _manual_body(player_api_id, "loan", dry_run=True)

    preview_response = client.post(
        "/api/admin/transfers/manual",
        json=dry_body,
        headers=admin_headers,
    )

    assert preview_response.status_code == 200, preview_response.get_json()
    preview = preview_response.get_json()
    assert preview["dry_run"] is True
    assert "record_ids" not in preview
    assert len(preview["affected_rows"]) == 1
    preview_row = preview["affected_rows"][0]
    assert preview_row["old_status"] == "academy"
    assert preview_row["would_be_status"] == "on_loan"
    assert preview_row["journey_current_status"] == {"old": None, "new": "on_loan"}
    assert PlayerTransferEvent.query.count() == 0
    assert TransferAdminEvent.query.count() == 0
    assert _state(player_api_id) == before

    commit_body = deepcopy(dry_body)
    commit_body["dry_run"] = False
    commit_response = client.post(
        "/api/admin/transfers/manual",
        json=commit_body,
        headers=admin_headers,
    )

    assert commit_response.status_code == 200, commit_response.get_json()
    committed = commit_response.get_json()
    assert committed["dry_run"] is False
    assert committed["affected_rows"] == preview["affected_rows"]
    assert committed["transfer"] == preview["transfer"]
    assert committed["record_ids"]["transfer_event_id"]
    assert committed["record_ids"]["audit_event_id"]
    assert PlayerTransferEvent.query.count() == 1
    assert TransferAdminEvent.query.count() == 1


def test_semantic_resubmit_reuses_transfer_and_appends_audit(client, admin_headers, clubs):
    parent, _destination = clubs
    player_api_id = 820_020
    _seed_player(player_api_id, parent)
    body = _manual_body(player_api_id, "sold")

    first_response = client.post(
        "/api/admin/transfers/manual",
        json=body,
        headers=admin_headers,
    )
    corroborating_body = deepcopy(body)
    corroborating_body["source_note"] = "Second operator confirmation"
    corroborating_body["fee_text"] = "Updated report: £1.2m"
    corroborating_body["from_team_api_id"] = PARENT_API_ID + 99
    second_response = client.post(
        "/api/admin/transfers/manual",
        json=corroborating_body,
        headers=admin_headers,
    )

    assert first_response.status_code == second_response.status_code == 200
    first = first_response.get_json()
    second = second_response.get_json()
    assert first["idempotent"] is False
    assert second["idempotent"] is True
    assert second["record_ids"]["transfer_event_id"] == first["record_ids"]["transfer_event_id"]
    assert second["record_ids"]["audit_event_id"] != first["record_ids"]["audit_event_id"]
    assert PlayerTransferEvent.query.count() == 1
    assert TransferAdminEvent.query.count() == 2
    corroboration = TransferAdminEvent.query.order_by(TransferAdminEvent.id.desc()).first()
    assert corroboration.source_note == corroborating_body["source_note"]
    assert corroboration.event_metadata["submitted_from_team_api_id"] == PARENT_API_ID + 99


def test_manual_loan_return_closes_durable_active_loan(
    client,
    admin_headers,
    clubs,
):
    parent, destination = clubs
    player_api_id = 820_025
    journey, _tracked = _seed_player(player_api_id, parent)
    loan_date = (date.fromisoformat(EFFECTIVE_DATE) - timedelta(days=1)).isoformat()
    durable_loan = {
        "date": loan_date,
        "type": "Loan",
        "teams": {
            "out": {"id": parent.team_id, "name": parent.name},
            "in": {"id": destination.team_id, "name": destination.name},
        },
    }
    assert record_transfer_events(player_api_id, [durable_loan], db.session) == 1
    result = JourneySyncService(database_only=True).reclassify_from_durable_transfer_events(journey)
    assert result is not None
    db.session.commit()
    assert _state(player_api_id)["tracked"]["status"] == "on_loan"
    assert _state(player_api_id)["journey"]["current_status"] == "on_loan"

    response = client.post(
        "/api/admin/transfers/manual",
        json={
            "player_api_id": player_api_id,
            "to_team_api_id": parent.team_id,
            "transfer_type": "loan_return",
            "effective_date": EFFECTIVE_DATE,
            "source_note": "Loan return confirmed by both clubs",
            "dry_run": False,
        },
        headers=admin_headers,
    )

    assert response.status_code == 200, response.get_json()
    payload = response.get_json()
    assert payload["transfer"]["from_team"] == {
        "api_id": destination.team_id,
        "name": destination.name,
        "resolution": "durable_transfer.active_loan",
    }
    assert payload["transfer"]["to_team"] == {
        "api_id": parent.team_id,
        "name": parent.name,
    }
    assert payload["affected_rows"][0]["old_status"] == "on_loan"
    assert payload["affected_rows"][0]["would_be_status"] == "academy"
    assert payload["affected_rows"][0]["journey_current_status"] == {
        "old": "on_loan",
        "new": None,
    }
    assert _state(player_api_id)["tracked"]["status"] == "academy"
    assert _state(player_api_id)["journey"]["current_status"] is None
    assert PlayerTransferEvent.query.count() == 2
    manual_event = PlayerTransferEvent.query.order_by(PlayerTransferEvent.transfer_date.desc()).first()
    assert manual_event.raw["source"] == "manual"
    assert manual_event.raw["manual_transfer_type"] == "loan_return"


def test_destination_name_matches_team_case_insensitively_and_id_takes_precedence(
    client,
    admin_headers,
    clubs,
):
    parent, destination = clubs
    player_api_id = 820_026
    _seed_player(player_api_id, parent)
    name_body = _manual_body(player_api_id, "signed", dry_run=True)
    name_body.pop("to_team_api_id")
    name_body["to_team_name"] = "  sOuThBaNk AtHlEtIc  "

    name_response = client.post(
        "/api/admin/transfers/manual",
        json=name_body,
        headers=admin_headers,
    )

    assert name_response.status_code == 200, name_response.get_json()
    name_transfer = name_response.get_json()["transfer"]
    assert name_transfer["to_team"] == {
        "api_id": destination.team_id,
        "name": destination.name,
    }
    assert name_transfer["destination_resolution"] == "teams.name"

    id_body = deepcopy(name_body)
    id_body["to_team_api_id"] = destination.team_id
    id_body["to_team_name"] = "Conflicting Unresolvable Name"
    id_response = client.post(
        "/api/admin/transfers/manual",
        json=id_body,
        headers=admin_headers,
    )

    assert id_response.status_code == 200, id_response.get_json()
    id_transfer = id_response.get_json()["transfer"]
    assert id_transfer["to_team"] == {
        "api_id": destination.team_id,
        "name": destination.name,
    }
    assert id_transfer["destination_resolution"] == "teams.api_id"
    assert PlayerTransferEvent.query.count() == 0
    assert TransferAdminEvent.query.count() == 0


def test_destination_name_falls_through_team_profile_then_club_program(
    client,
    admin_headers,
    clubs,
):
    parent, _destination = clubs
    profile = TeamProfile(
        team_id=DESTINATION_API_ID + 1,
        name="Profile United",
        country="England",
    )
    league = FundingLeague(
        name="Community Development League",
        country="England",
        region="North",
        level="youth_regional",
        age_bands=["U18"],
        gender_program="both",
        season_calendar="aug_may",
        data_tier="self_reported",
    )
    db.session.add_all([profile, league])
    db.session.flush()
    program = ClubProgram(
        funding_league_id=league.id,
        name="Grassroots Rovers",
        legal_name="Grassroots Rovers CIC",
        slug="grassroots-rovers",
        country="England",
        region="North",
    )
    db.session.add(program)
    db.session.commit()

    profile_player_id = 820_027
    program_player_id = 820_028
    _seed_player(profile_player_id, parent)
    _seed_player(program_player_id, parent)

    resolutions = []
    for player_api_id, destination_name in (
        (profile_player_id, "profile united"),
        (program_player_id, "GRASSROOTS ROVERS"),
    ):
        body = _manual_body(player_api_id, "signed", dry_run=True)
        body.pop("to_team_api_id")
        body["to_team_name"] = destination_name
        response = client.post(
            "/api/admin/transfers/manual",
            json=body,
            headers=admin_headers,
        )
        assert response.status_code == 200, response.get_json()
        resolutions.append(response.get_json()["transfer"])

    assert resolutions[0]["to_team"] == {
        "api_id": profile.team_id,
        "name": profile.name,
    }
    assert resolutions[0]["destination_resolution"] == "team_profiles.name"
    assert resolutions[1]["to_team"] == {
        "api_id": None,
        "name": program.name,
    }
    assert resolutions[1]["destination_resolution"] == "club_programs.name"
    assert PlayerTransferEvent.query.count() == 0
    assert TransferAdminEvent.query.count() == 0


def test_permanent_fee_cannot_impersonate_a_resolver_movement_label(
    client,
    admin_headers,
    clubs,
):
    parent, _destination = clubs
    player_api_id = 820_029
    _seed_player(player_api_id, parent)
    body = _manual_body(player_api_id, "sold")
    body["fee_text"] = "  Loan  "

    response = client.post(
        "/api/admin/transfers/manual",
        json=body,
        headers=admin_headers,
    )

    assert response.status_code == 422
    assert "movement label" in response.get_json()["error"]
    assert PlayerTransferEvent.query.count() == 0
    assert TransferAdminEvent.query.count() == 0
    assert _state(player_api_id)["tracked"]["status"] == "academy"


def test_incompatible_nullable_natural_key_collision_is_422(
    client,
    admin_headers,
    clubs,
):
    parent, _destination = clubs
    league = FundingLeague(
        name="Name-only Transfer League",
        country="England",
        region="South",
        level="youth_regional",
        age_bands=["U18"],
        gender_program="both",
        season_calendar="aug_may",
        data_tier="self_reported",
    )
    db.session.add(league)
    db.session.flush()
    first_program = ClubProgram(
        funding_league_id=league.id,
        name="First Name-only Club",
        legal_name="First Name-only Club Ltd",
        slug="first-name-only-club",
        country="England",
        region="South",
    )
    second_program = ClubProgram(
        funding_league_id=league.id,
        name="Second Name-only Club",
        legal_name="Second Name-only Club Ltd",
        slug="second-name-only-club",
        country="England",
        region="South",
    )
    db.session.add_all([first_program, second_program])
    db.session.commit()
    player_api_id = 820_031
    _seed_player(player_api_id, parent)

    first = _manual_body(player_api_id, "sold")
    first.pop("to_team_api_id")
    first["to_team_name"] = "First Name-only Club"
    assert (
        client.post(
            "/api/admin/transfers/manual",
            json=first,
            headers=admin_headers,
        ).status_code
        == 200
    )

    first_program.name = "First Name-only Club Renamed"
    db.session.commit()
    renamed_destination = deepcopy(first)
    renamed_destination["to_team_name"] = first_program.name
    renamed_response = client.post(
        "/api/admin/transfers/manual",
        json=renamed_destination,
        headers=admin_headers,
    )
    assert renamed_response.status_code == 200
    assert renamed_response.get_json()["idempotent"] is True
    assert PlayerTransferEvent.query.count() == 1

    conflicting_destination = deepcopy(first)
    conflicting_destination["to_team_name"] = second_program.name
    destination_response = client.post(
        "/api/admin/transfers/manual",
        json=conflicting_destination,
        headers=admin_headers,
    )
    assert destination_response.status_code == 422
    assert "different destination" in destination_response.get_json()["error"]

    conflicting_type = _manual_body(player_api_id, "signed")
    conflicting_type.pop("to_team_api_id")
    conflicting_type["to_team_name"] = first_program.name
    conflicting_type["fee_text"] = first["fee_text"]
    type_response = client.post(
        "/api/admin/transfers/manual",
        json=conflicting_type,
        headers=admin_headers,
    )
    assert type_response.status_code == 422
    assert "different manual transfer_type" in type_response.get_json()["error"]

    linked_profile = TeamProfile(
        team_id=DESTINATION_API_ID + 10,
        name=first_program.name,
        country="England",
    )
    db.session.add(linked_profile)
    db.session.flush()
    first_program.team_api_id = linked_profile.team_id
    db.session.commit()
    linked_destination = deepcopy(first)
    linked_destination.pop("to_team_name")
    linked_destination["to_team_api_id"] = linked_profile.team_id
    linked_response = client.post(
        "/api/admin/transfers/manual",
        json=linked_destination,
        headers=admin_headers,
    )
    assert linked_response.status_code == 200
    assert linked_response.get_json()["idempotent"] is True
    assert PlayerTransferEvent.query.count() == 1
    assert TransferAdminEvent.query.count() == 3


def test_suppressed_player_is_refused_with_unknown_player_response(
    client,
    admin_headers,
    clubs,
):
    parent, _destination = clubs
    player_api_id = 820_030
    _seed_player(player_api_id, parent)
    db.session.add(
        PlayerSuppression(
            player_api_id=player_api_id,
            reason_code="player_request",
            requester_role="player",
            requester_contact="private@example.com",
            request_statement="Please remove this profile.",
            status="active",
            decided_by=ADMIN_EMAIL,
        )
    )
    db.session.commit()

    suppressed = client.post(
        "/api/admin/transfers/manual",
        json=_manual_body(player_api_id, "loan"),
        headers=admin_headers,
    )
    unknown = client.post(
        "/api/admin/transfers/manual",
        json=_manual_body(999_999_999, "loan"),
        headers=admin_headers,
    )

    assert suppressed.status_code == unknown.status_code == 404
    assert suppressed.get_json() == unknown.get_json() == {"error": "Player not found"}
    assert PlayerTransferEvent.query.count() == 0
    assert TransferAdminEvent.query.count() == 0


def test_recompute_academy_without_transfer_evidence_preserves_status(
    client,
    admin_headers,
    clubs,
):
    parent, _destination = clubs
    player_api_id = 820_040
    _journey, tracked = _seed_player(player_api_id, parent)
    tracked.status = "sold"
    tracked.current_club_api_id = DESTINATION_API_ID
    tracked.current_club_name = "Southbank Athletic"
    tracked.sale_fee = "£1m"
    db.session.commit()

    response = client.post(
        "/api/admin/journeys/recompute-academy",
        json={"dry_run": False, "limit": 10, "cursor": 0},
        headers=admin_headers,
    )

    assert response.status_code == 200, response.get_json()
    assert response.get_json()["errors"] == 0
    persisted = TrackedPlayer.query.filter_by(player_api_id=player_api_id).one()
    assert persisted.status == "sold"
    assert persisted.current_club_api_id == DESTINATION_API_ID
    assert persisted.current_club_name == "Southbank Athletic"
    assert persisted.sale_fee == "£1m"
    assert PlayerTransferEvent.query.count() == 0


def test_unresolvable_destination_name_is_422(client, admin_headers, clubs):
    parent, _destination = clubs
    player_api_id = 820_050
    _seed_player(player_api_id, parent)
    body = _manual_body(player_api_id, "signed")
    body.pop("to_team_api_id")
    body["to_team_name"] = "Club That Does Not Exist"

    response = client.post(
        "/api/admin/transfers/manual",
        json=body,
        headers=admin_headers,
    )

    assert response.status_code == 422
    error = response.get_json()["error"].casefold()
    assert "destination" in error or "club that does not exist" in error
    assert PlayerTransferEvent.query.count() == 0
    assert TransferAdminEvent.query.count() == 0


def test_ambiguous_destination_name_is_422(client, admin_headers, clubs):
    parent, _destination = clubs
    db.session.add_all(
        [
            Team(
                team_id=DESTINATION_API_ID + 20,
                name="Shared Club Name",
                country="England",
                season=current_academy_season(),
                is_active=True,
            ),
            Team(
                team_id=DESTINATION_API_ID + 21,
                name="Shared Club Name",
                country="England",
                season=current_academy_season(),
                is_active=True,
            ),
        ]
    )
    db.session.commit()
    player_api_id = 820_055
    _seed_player(player_api_id, parent)
    body = _manual_body(player_api_id, "signed")
    body.pop("to_team_api_id")
    body["to_team_name"] = "shared club name"

    response = client.post(
        "/api/admin/transfers/manual",
        json=body,
        headers=admin_headers,
    )

    assert response.status_code == 422
    assert "ambiguous" in response.get_json()["error"]
    assert PlayerTransferEvent.query.count() == 0
    assert TransferAdminEvent.query.count() == 0


def test_missing_source_note_is_422(client, admin_headers, clubs):
    parent, _destination = clubs
    player_api_id = 820_060
    _seed_player(player_api_id, parent)
    body = _manual_body(player_api_id, "loan")
    body.pop("source_note")

    response = client.post(
        "/api/admin/transfers/manual",
        json=body,
        headers=admin_headers,
    )

    assert response.status_code == 422
    assert "source_note" in response.get_json()["error"]
    assert PlayerTransferEvent.query.count() == 0
    assert TransferAdminEvent.query.count() == 0


def test_manual_transfer_persists_raw_provenance_and_admin_audit(
    client,
    admin_headers,
    clubs,
):
    parent, _destination = clubs
    player_api_id = 820_070
    _seed_player(player_api_id, parent)
    body = _manual_body(player_api_id, "sold")

    response = client.post(
        "/api/admin/transfers/manual",
        json=body,
        headers=admin_headers,
    )

    assert response.status_code == 200, response.get_json()
    payload = response.get_json()
    transfer = PlayerTransferEvent.query.one()
    audit = TransferAdminEvent.query.one()
    assert transfer.id == payload["record_ids"]["transfer_event_id"]
    assert transfer.raw["source"] == "manual"
    assert transfer.raw["source_note"] == body["source_note"]
    assert transfer.raw["manual_transfer_type"] == "sold"
    assert audit.id == payload["record_ids"]["audit_event_id"]
    assert audit.transfer_event_id == transfer.id
    assert audit.player_api_id == player_api_id
    assert audit.actor_email == ADMIN_EMAIL
    assert audit.source_note == body["source_note"]


def test_td01_migration_matches_audit_model_and_enables_rls(monkeypatch):
    migration = importlib.import_module("migrations.versions.td01_manual_transfer_audit")
    captured = {"indexes": [], "exists": False}

    def table_exists(_name):
        return captured["exists"]

    def capture_table(name, *elements):
        captured["table"] = sa.Table(name, sa.MetaData(), *elements)
        captured["exists"] = True

    def capture_index(name, table_name, columns, **kwargs):
        captured["indexes"].append((name, table_name, tuple(columns), kwargs))

    monkeypatch.setattr(migration, "table_exists", table_exists)
    monkeypatch.setattr(migration.op, "create_table", capture_table)
    monkeypatch.setattr(migration, "create_index_safe", capture_index)
    monkeypatch.setattr(migration.op, "execute", lambda statement: captured.setdefault("rls", str(statement)))

    migration.upgrade()

    migration_table = captured["table"]
    model_table = TransferAdminEvent.__table__
    dialect = postgresql.dialect()
    assert migration_table.name == model_table.name == "transfer_admin_events"
    assert list(migration_table.c.keys()) == list(model_table.c.keys())
    for name in migration_table.c.keys():
        migration_column = migration_table.c[name]
        model_column = model_table.c[name]
        assert migration_column.type.compile(dialect=dialect) == model_column.type.compile(dialect=dialect)
        assert migration_column.nullable == model_column.nullable
        assert migration_column.primary_key == model_column.primary_key

    model_indexes = {(index.name, tuple(column.name for column in index.columns)) for index in model_table.indexes}
    migration_indexes = {
        (name, columns)
        for name, table_name, columns, kwargs in captured["indexes"]
        if table_name == model_table.name and kwargs == {}
    }
    assert migration_indexes == model_indexes
    assert captured["rls"] == 'ALTER TABLE "transfer_admin_events" ENABLE ROW LEVEL SECURITY'
