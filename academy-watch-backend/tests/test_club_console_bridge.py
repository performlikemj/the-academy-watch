"""Coverage for the showcase-claim to club-console bridge."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from flask import Flask
from src.auth import issue_user_token
from src.extensions import limiter
from src.models.funding import (
    ClubConnectAccount,
    ClubProgram,
    ClubProgramClaim,
    ClubProgramManager,
    FundingAdminEvent,
    FundingLeague,
)
from src.models.league import League, Team, TeamProfile, UserAccount, db
from src.models.showcase import ClubOfficialClaim, LocalClub
from src.routes.club import club_bp
from src.routes.funding import funding_bp
from src.routes.showcase import showcase_bp
from src.services.club_console_bridge import CONSOLE_LEAGUE_NAME, grant_console_for_official_claim

ADMIN_KEY = "club-console-bridge-admin-key"
TEAM_API_ID = 88001
TEAM_EMAIL = "team-official@bridge.example"
LOCAL_EMAIL = "local-official@bridge.example"


@pytest.fixture
def bridge_app(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", ADMIN_KEY)
    monkeypatch.setenv("ADMIN_IP_WHITELIST", "")
    monkeypatch.setenv("SKIP_API_HANDSHAKE", "1")
    monkeypatch.setattr(
        "src.services.email_service.email_service.send_email",
        lambda **_kwargs: SimpleNamespace(success=True, provider="stub", message_id="bridge-test"),
    )

    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SECRET_KEY="club-console-bridge-fixture-secret",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        RATELIMIT_ENABLED=False,
    )
    db.init_app(app)
    limiter.init_app(app)
    app.register_blueprint(showcase_bp, url_prefix="/api")
    app.register_blueprint(funding_bp, url_prefix="/api")
    app.register_blueprint(club_bp, url_prefix="/api")

    with app.app_context():
        db.create_all()
        league = League(league_id=88000, name="Bridge League", country="Japan", season=2026)
        team = Team(
            team_id=TEAM_API_ID,
            name="Bridge Academy",
            country="Japan",
            venue_city="Yokohama",
            logo="https://images.example/bridge-academy.png",
            season=2026,
            league=league,
        )
        team_user = UserAccount(
            email=TEAM_EMAIL,
            display_name="Team Official",
            display_name_lower="team official bridge",
        )
        local_user = UserAccount(
            email=LOCAL_EMAIL,
            display_name="Local Official",
            display_name_lower="local official bridge",
        )
        db.session.add_all([league, team, team_user, local_user])
        db.session.flush()
        local_club = LocalClub(
            name="Harbour Juniors",
            normalized_name="harbour juniors",
            country="Japan",
            city="Kobe",
            level="youth",
            status="verified",
            provenance="user",
            created_by_user_id=local_user.id,
        )
        db.session.add(local_club)
        db.session.commit()
        app.bridge = {"local_club_id": local_club.id}
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(bridge_app):
    return bridge_app.test_client()


def _user_headers(email: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_user_token(email)['token']}"}


def _admin_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {issue_user_token('bridge-admin@example.com', role='admin')['token']}",
        "X-API-Key": ADMIN_KEY,
    }


def _submit_claim(client, email: str, identity: dict[str, int]) -> ClubOfficialClaim:
    response = client.post(
        "/api/clubs/claim",
        json={**identity, "role_title": "Academy Director", "message": "I represent this club."},
        headers=_user_headers(email),
    )
    assert response.status_code == 201, response.get_json()
    claim = db.session.get(ClubOfficialClaim, response.get_json()["claim"]["id"])
    claim.verification_proof_url = "https://www.youtube.com/@bridge-academy"
    claim.verification_status = "code_found"
    db.session.commit()
    return claim


def _review(client, claim_id: int, action: str):
    response = client.post(
        f"/api/admin/club-claims/{claim_id}/review",
        json={"action": action, "note": f"Bridge test: {action}"},
        headers=_admin_headers(),
    )
    assert response.status_code == 200, response.get_json()
    return response


def _bridge_rows(official_claim: ClubOfficialClaim):
    manager = ClubProgramManager.query.filter_by(user_account_id=official_claim.user_account_id).one()
    program_claim = db.session.get(ClubProgramClaim, manager.source_claim_id)
    program = db.session.get(ClubProgram, manager.program_id)
    return program, program_claim, manager


def _seed_team_program(
    *,
    slug: str,
    platform_status: str,
    donations_enabled: bool = False,
    emergency_hidden: bool = False,
) -> tuple[FundingLeague, ClubProgram]:
    public_league = FundingLeague(
        name=f"Public league for {slug}",
        country="Japan",
        region="Kanto",
        level="youth_regional",
        age_bands=["U18"],
        gender_program="both",
        season_calendar="calendar_year",
        data_tier="self_reported",
        registry_status="approved",
        admission_state="open",
    )
    profile = TeamProfile(team_id=TEAM_API_ID, name="Bridge Academy", country="Japan")
    db.session.add_all([public_league, profile])
    db.session.flush()
    program = ClubProgram(
        funding_league_id=public_league.id,
        team_api_id=TEAM_API_ID,
        name="Bridge Academy",
        legal_name="Bridge Academy",
        slug=slug,
        country="Japan",
        region="Kanto",
        platform_status=platform_status,
        donations_enabled=donations_enabled,
        emergency_hidden=emergency_hidden,
    )
    db.session.add(program)
    db.session.commit()
    return public_league, program


def test_team_claim_grants_discoverable_console_idempotently_and_stays_private(bridge_app, client):
    official_claim = _submit_claim(client, TEAM_EMAIL, {"team_api_id": TEAM_API_ID})
    _review(client, official_claim.id, "approve")

    program, program_claim, manager = _bridge_rows(official_claim)
    original_ids = (program.id, program_claim.id, manager.id)
    assert program.team_api_id == TEAM_API_ID
    assert program.platform_status == "approved"
    assert program.donations_enabled is False
    assert program.public_dict()["is_fundable"] is False
    assert program.league.name == CONSOLE_LEAGUE_NAME
    assert program.league.registry_status != "approved"
    assert program.league.admission_state == "closed"
    assert program_claim.status == "approved"
    assert f"ClubOfficialClaim #{official_claim.id}" in program_claim.applicant_message
    assert official_claim.verification_proof_url in program_claim.applicant_message
    assert official_claim.verification_code in program_claim.applicant_message
    assert manager.status == "active"
    assert manager.source_claim_id == program_claim.id
    assert TeamProfile.query.filter_by(team_id=TEAM_API_ID).one().name == "Bridge Academy"
    assert ClubConnectAccount.query.count() == 0
    assert FundingAdminEvent.query.filter_by(action="claim.console_bridge_granted").count() == 1

    roster = client.get(f"/api/club/{program.id}/roster", headers=_user_headers(TEAM_EMAIL))
    assert roster.status_code == 200, roster.get_json()
    assert roster.get_json() == {"members": [], "count": 0}

    discovery = client.get("/api/funding/claims/me", headers=_user_headers(TEAM_EMAIL))
    assert discovery.status_code == 200, discovery.get_json()
    discovered_claims = discovery.get_json()["claims"]
    assert [(row["id"], row["program"]["id"]) for row in discovered_claims] == [(program_claim.id, program.id)]
    assert discovered_claims[0]["status"] == "approved"
    assert discovered_claims[0]["program"]["platform_status"] == "approved"

    # The bridge itself is retry-safe even though the admin lifecycle keeps a
    # second approve of an already-approved official claim as a 409.
    grant_console_for_official_claim(
        official_claim,
        actor="bridge-admin@example.com",
        now=datetime.now(UTC),
    )
    db.session.commit()
    assert ClubProgram.query.count() == 1
    assert ClubProgramClaim.query.count() == 1
    assert ClubProgramManager.query.count() == 1
    assert _bridge_rows(official_claim)[0].id == original_ids[0]
    assert _bridge_rows(official_claim)[1].id == original_ids[1]
    assert _bridge_rows(official_claim)[2].id == original_ids[2]

    duplicate_approval = client.post(
        f"/api/admin/club-claims/{official_claim.id}/review",
        json={"action": "approve"},
        headers=_admin_headers(),
    )
    assert duplicate_approval.status_code == 409, duplicate_approval.get_json()
    assert ClubProgram.query.count() == 1
    assert ClubProgramClaim.query.count() == 1
    assert ClubProgramManager.query.count() == 1

    assert client.get(f"/api/programs/{program.slug}").status_code == 404
    assert (
        client.post(
            f"/api/programs/{program.slug}/save",
            json={"notify_when_fundable": True},
            headers=_user_headers(TEAM_EMAIL),
        ).status_code
        == 404
    )
    public_leagues = client.get("/api/funding/leagues")
    assert public_leagues.status_code == 200
    assert all(row["name"] != CONSOLE_LEAGUE_NAME for row in public_leagues.get_json()["leagues"])


def test_reused_pending_team_program_stays_unlisted_after_revoke(client):
    _, existing_program = _seed_team_program(
        slug="bridge-academy-pending",
        platform_status="pending",
    )
    existing_program_id = existing_program.id

    official_claim = _submit_claim(client, TEAM_EMAIL, {"team_api_id": TEAM_API_ID})
    _review(client, official_claim.id, "approve")

    program, _, _ = _bridge_rows(official_claim)
    assert program.id == existing_program_id
    assert program.league.name == CONSOLE_LEAGUE_NAME
    assert program.league.registry_status != "approved"
    assert program.donations_enabled is False
    assert program.public_dict()["is_fundable"] is False
    assert client.get(f"/api/programs/{program.slug}").status_code == 404

    _review(client, official_claim.id, "revoke")
    db.session.refresh(program)
    assert program.platform_status == "approved"
    assert program.league.name == CONSOLE_LEAGUE_NAME
    assert program.donations_enabled is False
    assert client.get(f"/api/club/{program.id}/roster", headers=_user_headers(TEAM_EMAIL)).status_code == 403


def test_independent_manager_grant_is_not_overwritten(client):
    public_league, program = _seed_team_program(
        slug="bridge-academy-independently-managed",
        platform_status="approved",
        donations_enabled=True,
    )
    user = UserAccount.query.filter_by(email=TEAM_EMAIL).one()
    existing_claim = ClubProgramClaim(
        program_id=program.id,
        user_account_id=user.id,
        relationship_type="finance_director",
        status="approved",
        applicant_message="Independent funding evidence",
        reviewed_by="funding-admin@example.com",
    )
    db.session.add(existing_claim)
    db.session.flush()
    existing_manager = ClubProgramManager(
        program_id=program.id,
        user_account_id=user.id,
        source_claim_id=existing_claim.id,
        status="active",
        granted_by="funding-admin@example.com",
    )
    db.session.add(existing_manager)
    db.session.commit()

    official_claim = _submit_claim(client, TEAM_EMAIL, {"team_api_id": TEAM_API_ID})
    response = client.post(
        f"/api/admin/club-claims/{official_claim.id}/review",
        json={"action": "approve"},
        headers=_admin_headers(),
    )

    assert response.status_code == 409, response.get_json()
    db.session.expire_all()
    assert db.session.get(ClubOfficialClaim, official_claim.id).status == "pending"
    assert db.session.get(ClubProgram, program.id).funding_league_id == public_league.id
    assert db.session.get(ClubProgram, program.id).donations_enabled is True
    assert db.session.get(ClubProgramClaim, existing_claim.id).applicant_message == "Independent funding evidence"
    assert db.session.get(ClubProgramManager, existing_manager.id).status == "active"
    assert FundingAdminEvent.query.count() == 0


def test_emergency_hidden_program_blocks_approval_and_rolls_back_claim(client):
    _, program = _seed_team_program(
        slug="bridge-academy-emergency-hidden",
        platform_status="approved",
        emergency_hidden=True,
    )
    official_claim = _submit_claim(client, TEAM_EMAIL, {"team_api_id": TEAM_API_ID})

    response = client.post(
        f"/api/admin/club-claims/{official_claim.id}/review",
        json={"action": "approve"},
        headers=_admin_headers(),
    )

    assert response.status_code == 409, response.get_json()
    assert "emergency-hidden" in response.get_json()["error"]
    db.session.expire_all()
    assert db.session.get(ClubOfficialClaim, official_claim.id).status == "pending"
    assert db.session.get(ClubProgram, program.id).emergency_hidden is True
    assert ClubProgramClaim.query.count() == 0
    assert ClubProgramManager.query.count() == 0
    assert FundingAdminEvent.query.count() == 0


def test_reserved_local_slug_without_bridge_audit_is_not_adopted(bridge_app, client):
    local_club_id = bridge_app.bridge["local_club_id"]
    attacker_league = FundingLeague(
        name=CONSOLE_LEAGUE_NAME,
        country="Japan",
        region="User proposed",
        level="recreational",
        age_bands=["U18"],
        gender_program="both",
        season_calendar="calendar_year",
        data_tier="self_reported",
        registry_status="proposed",
        admission_state="closed",
    )
    db.session.add(attacker_league)
    db.session.flush()
    poisoned_program = ClubProgram(
        funding_league_id=attacker_league.id,
        name="Spoofed Harbour Juniors",
        legal_name="Spoofed Harbour Juniors LLC",
        slug=f"console-local-club-{local_club_id}",
        country="Japan",
        region="User proposed",
        platform_status="pending",
    )
    db.session.add(poisoned_program)
    db.session.commit()

    official_claim = _submit_claim(client, LOCAL_EMAIL, {"local_club_id": local_club_id})
    response = client.post(
        f"/api/admin/club-claims/{official_claim.id}/review",
        json={"action": "approve"},
        headers=_admin_headers(),
    )

    assert response.status_code == 409, response.get_json()
    db.session.expire_all()
    assert db.session.get(ClubOfficialClaim, official_claim.id).status == "pending"
    assert db.session.get(ClubProgram, poisoned_program.id).platform_status == "pending"
    assert ClubProgramClaim.query.count() == 0
    assert ClubProgramManager.query.count() == 0
    assert FundingAdminEvent.query.count() == 0


def test_revoked_historical_claim_cannot_replace_current_approved_claim(client):
    first_claim = _submit_claim(client, TEAM_EMAIL, {"team_api_id": TEAM_API_ID})
    _review(client, first_claim.id, "approve")
    _review(client, first_claim.id, "revoke")

    user = UserAccount.query.filter_by(email=TEAM_EMAIL).one()
    current_claim = ClubOfficialClaim(
        user_account_id=user.id,
        team_api_id=TEAM_API_ID,
        role_title="Academy Director",
        status="pending",
        verification_code="AW-CURRENTBRIDGE",
        verification_proof_url="https://www.youtube.com/@bridge-academy",
        verification_status="code_found",
    )
    db.session.add(current_claim)
    db.session.commit()
    _review(client, current_claim.id, "approve")

    program, program_claim, manager = _bridge_rows(current_claim)
    assert f"ClubOfficialClaim #{current_claim.id}" in program_claim.applicant_message
    assert manager.status == "active"

    response = client.post(
        f"/api/admin/club-claims/{first_claim.id}/review",
        json={"action": "approve"},
        headers=_admin_headers(),
    )

    assert response.status_code == 409, response.get_json()
    db.session.expire_all()
    assert db.session.get(ClubOfficialClaim, first_claim.id).status == "revoked"
    assert db.session.get(ClubOfficialClaim, current_claim.id).status == "approved"
    assert (
        f"ClubOfficialClaim #{current_claim.id}" in db.session.get(ClubProgramClaim, program_claim.id).applicant_message
    )
    assert client.get(f"/api/club/{program.id}/roster", headers=_user_headers(TEAM_EMAIL)).status_code == 200


def test_two_officials_share_program_and_revoke_only_their_own_grant(client):
    first_claim = _submit_claim(client, TEAM_EMAIL, {"team_api_id": TEAM_API_ID})
    second_claim = _submit_claim(client, LOCAL_EMAIL, {"team_api_id": TEAM_API_ID})
    _review(client, first_claim.id, "approve")
    _review(client, second_claim.id, "approve")

    program, first_program_claim, first_manager = _bridge_rows(first_claim)
    second_program, second_program_claim, second_manager = _bridge_rows(second_claim)
    assert second_program.id == program.id
    assert first_program_claim.id != second_program_claim.id
    assert first_manager.id != second_manager.id
    assert client.get(f"/api/club/{program.id}/roster", headers=_user_headers(TEAM_EMAIL)).status_code == 200
    assert client.get(f"/api/club/{program.id}/roster", headers=_user_headers(LOCAL_EMAIL)).status_code == 200

    _review(client, first_claim.id, "revoke")
    db.session.refresh(program)
    db.session.refresh(first_program_claim)
    db.session.refresh(first_manager)
    db.session.refresh(second_program_claim)
    db.session.refresh(second_manager)
    assert program.platform_status == "approved"
    assert program.league.name == CONSOLE_LEAGUE_NAME
    assert program.donations_enabled is False
    assert first_program_claim.status == "revoked"
    assert first_manager.status == "revoked"
    assert second_program_claim.status == "approved"
    assert second_manager.status == "active"
    assert client.get(f"/api/club/{program.id}/roster", headers=_user_headers(TEAM_EMAIL)).status_code == 403
    assert client.get(f"/api/club/{program.id}/roster", headers=_user_headers(LOCAL_EMAIL)).status_code == 200


def test_local_claim_revoke_and_reapprove_reuses_rows_and_system_league(bridge_app, client):
    official_claim = _submit_claim(
        client,
        LOCAL_EMAIL,
        {"local_club_id": bridge_app.bridge["local_club_id"]},
    )
    _review(client, official_claim.id, "approve")
    program, program_claim, manager = _bridge_rows(official_claim)
    original_ids = (program.id, program_claim.id, manager.id)
    assert program.slug == f"console-local-club-{bridge_app.bridge['local_club_id']}"
    assert program.name == "Harbour Juniors"
    assert client.get(f"/api/club/{program.id}/roster", headers=_user_headers(LOCAL_EMAIL)).status_code == 200

    _review(client, official_claim.id, "revoke")
    db.session.refresh(program_claim)
    db.session.refresh(manager)
    assert program_claim.status == "revoked"
    assert manager.status == "revoked"
    assert manager.revoked_by == "bridge-admin@example.com"
    assert client.get(f"/api/club/{program.id}/roster", headers=_user_headers(LOCAL_EMAIL)).status_code == 403
    assert FundingAdminEvent.query.filter_by(action="claim.console_bridge_revoked").count() == 1

    _review(client, official_claim.id, "approve")
    restored_program, restored_claim, restored_manager = _bridge_rows(official_claim)
    assert (restored_program.id, restored_claim.id, restored_manager.id) == original_ids
    assert restored_claim.status == "approved"
    assert restored_manager.status == "active"
    assert restored_manager.revoked_by is None
    assert restored_manager.revoked_reason is None
    assert restored_manager.revoked_at is None
    assert client.get(f"/api/club/{program.id}/roster", headers=_user_headers(LOCAL_EMAIL)).status_code == 200

    team_claim = _submit_claim(client, TEAM_EMAIL, {"team_api_id": TEAM_API_ID})
    _review(client, team_claim.id, "approve")
    team_program, _, _ = _bridge_rows(team_claim)
    assert team_program.funding_league_id == restored_program.funding_league_id
    assert FundingLeague.query.filter_by(name=CONSOLE_LEAGUE_NAME).count() == 1
    assert ClubConnectAccount.query.count() == 0
    assert client.get(f"/api/programs/{program.slug}").status_code == 404
