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
from src.services.club_console_bridge import (
    CONSOLE_LEAGUE_COUNTRY,
    CONSOLE_LEAGUE_NAME,
    CONSOLE_LEAGUE_REGION,
    grant_console_for_official_claim,
)

ADMIN_KEY = "club-console-bridge-admin-key"
TEAM_API_ID = 88001
TEAM_EMAIL = "team-official@bridge.example"
LOCAL_EMAIL = "local-official@bridge.example"


@pytest.fixture
def bridge_app(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", ADMIN_KEY)
    monkeypatch.setenv("ADMIN_IP_WHITELIST", "")
    monkeypatch.setenv("SKIP_API_HANDSHAKE", "1")
    monkeypatch.setenv(
        "FUNDING_EVIDENCE_ENCRYPTION_KEY",
        "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=",
    )
    sent_emails = []

    def _capture_email(**kwargs):
        sent_emails.append(kwargs)
        return SimpleNamespace(success=True, provider="stub", message_id="bridge-test")

    monkeypatch.setattr("src.services.email_service.email_service.send_email", _capture_email)

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
        app.bridge = {"local_club_id": local_club.id, "sent_emails": sent_emails}
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


def _funding_claim_payload(league_id: int) -> dict:
    return {
        "funding_league_id": league_id,
        "team_api_id": TEAM_API_ID,
        "club_name": "Bridge Academy",
        "legal_name": "Bridge Academy Association",
        "country": "Japan",
        "region": "Kanto",
        "city": "Yokohama",
        "currency": "JPY",
        "applicant_message": "Funding registry adoption test.",
        "evidence": {
            "adult_authority_attested": True,
            "official_email": TEAM_EMAIL,
            "authorization_method": "official_domain_email",
            "organization_form": "association",
            "registration_reference": "BRIDGE-FUNDING-001",
            "official_contact_name": "Team Official",
            "official_contact_reference": "Club officer directory",
            "safeguarding_contact_email": "safeguarding@bridge.example",
            "safeguarding_policy_url": "https://bridge.example/safeguarding",
            "safeguarding_policy_attested": True,
            "eligible_organization_attested": True,
            "payout_control_attested": True,
        },
    }


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
    assert FundingAdminEvent.query.filter_by(action="program.console_bridge_created").count() == 1
    assert FundingAdminEvent.query.filter_by(action="claim.console_bridge_created").count() == 1
    assert FundingAdminEvent.query.filter_by(action="claim.console_bridge_granted").count() == 1

    roster = client.get(f"/api/club/{program.id}/roster", headers=_user_headers(TEAM_EMAIL))
    assert roster.status_code == 200, roster.get_json()
    assert roster.get_json() == {
        "members": [],
        "count": 0,
        "system_brief": {"body": None, "updated_at": None},
    }

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
    assert FundingAdminEvent.query.filter_by(action="program.console_bridge_created").count() == 1
    assert FundingAdminEvent.query.filter_by(action="claim.console_bridge_created").count() == 1
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


def test_console_league_cannot_be_opened_listed_or_renamed(client):
    official_claim = _submit_claim(client, TEAM_EMAIL, {"team_api_id": TEAM_API_ID})
    _review(client, official_claim.id, "approve")
    program, _, _ = _bridge_rows(official_claim)
    console_league = program.league
    audit_count = FundingAdminEvent.query.count()

    for payload in (
        {"registry_status": "approved", "reason": "Must remain private"},
        {"admission_state": "open", "reason": "Must remain closed"},
        {"name": "Public console league", "reason": "Must retain reserved identity"},
    ):
        response = client.patch(
            f"/api/admin/funding/leagues/{console_league.id}",
            json=payload,
            headers=_admin_headers(),
        )
        assert response.status_code == 409, response.get_json()
        assert response.get_json()["error"] == "console-only league must remain unlisted and closed"

    db.session.refresh(console_league)
    assert console_league.name == CONSOLE_LEAGUE_NAME
    assert console_league.registry_status == "proposed"
    assert console_league.admission_state == "closed"
    assert FundingAdminEvent.query.count() == audit_count
    assert client.get(f"/api/programs/{program.slug}").status_code == 404


def test_console_program_is_adopted_into_public_funding_flow(bridge_app, client):
    official_claim = _submit_claim(client, TEAM_EMAIL, {"team_api_id": TEAM_API_ID})
    _review(client, official_claim.id, "approve")
    program, bridge_program_claim, bridge_manager = _bridge_rows(official_claim)
    console_league_id = program.funding_league_id
    original_ids = (program.id, bridge_program_claim.id, bridge_manager.id)
    manager_before_adoption = (
        bridge_manager.source_claim_id,
        bridge_manager.status,
        bridge_manager.granted_by,
        bridge_manager.granted_at,
        bridge_manager.revoked_by,
        bridge_manager.revoked_reason,
        bridge_manager.revoked_at,
    )
    public_league = FundingLeague(
        name="Bridge Public Funding League",
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
    db.session.add(public_league)
    db.session.commit()
    emails_before = len(bridge_app.bridge["sent_emails"])

    response = client.post(
        "/api/funding/claims",
        json=_funding_claim_payload(public_league.id),
        headers=_user_headers(TEAM_EMAIL),
    )

    assert response.status_code == 201, response.get_json()
    assert response.get_json()["claim"]["id"] == bridge_program_claim.id
    db.session.expire_all()
    adopted_program = db.session.get(ClubProgram, program.id)
    funding_claim = db.session.get(ClubProgramClaim, bridge_program_claim.id)
    preserved_manager = db.session.get(ClubProgramManager, bridge_manager.id)
    assert (adopted_program.id, funding_claim.id, preserved_manager.id) == original_ids
    assert adopted_program.funding_league_id == public_league.id
    assert adopted_program.platform_status == "pending"
    assert adopted_program.donations_enabled is False
    assert adopted_program.reviewed_by is None
    assert adopted_program.review_reason is None
    assert adopted_program.reviewed_at is None
    assert adopted_program.verified_at is None
    assert adopted_program.next_review_at is None
    assert adopted_program.public_dict()["is_fundable"] is False
    assert funding_claim.status == "pending"
    assert funding_claim.applicant_message == "Funding registry adoption test."
    assert funding_claim.evidence is not None
    assert funding_claim.evidence.adult_authority_attested is True
    assert (
        preserved_manager.source_claim_id,
        preserved_manager.status,
        preserved_manager.granted_by,
        preserved_manager.granted_at,
        preserved_manager.revoked_by,
        preserved_manager.revoked_reason,
        preserved_manager.revoked_at,
    ) == manager_before_adoption
    adoption_event = FundingAdminEvent.query.filter_by(action="program.console_adopted").one()
    assert adoption_event.target_type == "program"
    assert adoption_event.target_id == adopted_program.id
    assert adoption_event.event_metadata == {
        "from_league_id": console_league_id,
        "to_league_id": public_league.id,
        "program_claim_id": funding_claim.id,
        "manager_grant_id": preserved_manager.id,
        "released_official_claim_ids": [official_claim.id],
    }
    assert FundingAdminEvent.query.filter_by(action="claim.resubmitted", target_id=funding_claim.id).count() == 1
    assert ClubProgram.query.count() == 1
    assert ClubProgramClaim.query.count() == 1
    assert ClubProgramManager.query.count() == 1
    assert client.get(f"/api/programs/{adopted_program.slug}").status_code == 404
    assert client.get(f"/api/club/{adopted_program.id}/roster", headers=_user_headers(TEAM_EMAIL)).status_code == 403
    assert len(bridge_app.bridge["sent_emails"]) == emails_before

    approval = client.post(
        f"/api/admin/funding/claims/{funding_claim.id}/approve",
        json={"reason": "Funding evidence verified"},
        headers=_admin_headers(),
    )
    assert approval.status_code == 200, approval.get_json()
    db.session.expire_all()
    funded_program = db.session.get(ClubProgram, program.id)
    approved_claim = db.session.get(ClubProgramClaim, bridge_program_claim.id)
    funded_manager = db.session.get(ClubProgramManager, bridge_manager.id)
    assert funded_program.platform_status == "approved"
    assert approved_claim.status == "approved"
    assert funded_manager.status == "active"
    assert funded_manager.source_claim_id == approved_claim.id
    assert client.get(f"/api/programs/{funded_program.slug}").status_code == 200
    assert client.get(f"/api/club/{funded_program.id}/roster", headers=_user_headers(TEAM_EMAIL)).status_code == 200

    funding_state = (
        funded_program.funding_league_id,
        funded_program.platform_status,
        funded_program.donations_enabled,
        approved_claim.status,
        approved_claim.applicant_message,
        funded_manager.status,
        funded_manager.source_claim_id,
        funded_manager.granted_by,
        funded_manager.granted_at,
    )
    _review(client, official_claim.id, "revoke")
    db.session.expire_all()
    assert db.session.get(ClubOfficialClaim, official_claim.id).status == "revoked"
    funded_program = db.session.get(ClubProgram, program.id)
    approved_claim = db.session.get(ClubProgramClaim, bridge_program_claim.id)
    funded_manager = db.session.get(ClubProgramManager, bridge_manager.id)
    assert (
        funded_program.funding_league_id,
        funded_program.platform_status,
        funded_program.donations_enabled,
        approved_claim.status,
        approved_claim.applicant_message,
        funded_manager.status,
        funded_manager.source_claim_id,
        funded_manager.granted_by,
        funded_manager.granted_at,
    ) == funding_state
    assert FundingAdminEvent.query.filter_by(action="claim.console_bridge_revoked").count() == 0


def test_other_user_cannot_adopt_a_bridge_console_program(bridge_app, client):
    official_claim = _submit_claim(client, TEAM_EMAIL, {"team_api_id": TEAM_API_ID})
    _review(client, official_claim.id, "approve")
    program, program_claim, manager = _bridge_rows(official_claim)
    console_league_id = program.funding_league_id
    public_league = FundingLeague(
        name="Unauthorized Adoption Target",
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
    db.session.add(public_league)
    db.session.commit()
    audit_count = FundingAdminEvent.query.count()
    emails_before = len(bridge_app.bridge["sent_emails"])

    response = client.post(
        "/api/funding/claims",
        json=_funding_claim_payload(public_league.id),
        headers=_user_headers(LOCAL_EMAIL),
    )

    assert response.status_code == 409, response.get_json()
    assert response.get_json()["error"] == (
        f"club program '{program.name}' ({program.slug}) is already registered in another league "
        "and is not eligible for console adoption"
    )
    db.session.expire_all()
    assert db.session.get(ClubProgram, program.id).funding_league_id == console_league_id
    assert db.session.get(ClubProgram, program.id).platform_status == "approved"
    assert db.session.get(ClubProgramClaim, program_claim.id).status == "approved"
    assert db.session.get(ClubProgramManager, manager.id).status == "active"
    assert ClubProgramClaim.query.count() == 1
    assert ClubProgramManager.query.count() == 1
    assert FundingAdminEvent.query.count() == audit_count
    assert len(bridge_app.bridge["sent_emails"]) == emails_before


def test_foreign_registry_program_still_cannot_be_adopted(client):
    original_league, program = _seed_team_program(
        slug="foreign-registry-program",
        platform_status="approved",
        donations_enabled=True,
    )
    requested_league = FundingLeague(
        name="Foreign Program Requested League",
        country="Japan",
        region="Kansai",
        level="youth_regional",
        age_bands=["U18"],
        gender_program="both",
        season_calendar="calendar_year",
        data_tier="self_reported",
        registry_status="approved",
        admission_state="open",
    )
    db.session.add(requested_league)
    db.session.commit()

    response = client.post(
        "/api/funding/claims",
        json=_funding_claim_payload(requested_league.id),
        headers=_user_headers(TEAM_EMAIL),
    )

    assert response.status_code == 409, response.get_json()
    assert response.get_json()["error"] == (
        "club program 'Bridge Academy' (foreign-registry-program) is already registered in another league "
        "and is not eligible for console adoption"
    )
    db.session.expire_all()
    unchanged_program = db.session.get(ClubProgram, program.id)
    assert unchanged_program.funding_league_id == original_league.id
    assert unchanged_program.platform_status == "approved"
    assert unchanged_program.donations_enabled is True
    assert ClubProgramClaim.query.count() == 0
    assert ClubProgramManager.query.count() == 0
    assert FundingAdminEvent.query.count() == 0


def test_pending_registry_program_conflicts_without_mutation_or_email(bridge_app, client):
    public_league, existing_program = _seed_team_program(
        slug="bridge-academy-pending",
        platform_status="pending",
        donations_enabled=True,
    )
    user = UserAccount.query.filter_by(email=TEAM_EMAIL).one()
    pending_claim = ClubProgramClaim(
        program_id=existing_program.id,
        user_account_id=user.id,
        relationship_type="finance_director",
        status="pending",
        applicant_message="Independent pending funding evidence",
    )
    db.session.add(pending_claim)
    db.session.commit()

    official_claim = _submit_claim(client, TEAM_EMAIL, {"team_api_id": TEAM_API_ID})
    response = client.post(
        f"/api/admin/club-claims/{official_claim.id}/review",
        json={"action": "approve"},
        headers=_admin_headers(),
    )

    assert response.status_code == 409, response.get_json()
    assert response.get_json()["error"] == (
        "club already has a registry program (bridge-academy-pending); approve it via the funding claim path"
    )
    db.session.expire_all()
    assert db.session.get(ClubOfficialClaim, official_claim.id).status == "pending"
    unchanged_program = db.session.get(ClubProgram, existing_program.id)
    assert unchanged_program.funding_league_id == public_league.id
    assert unchanged_program.platform_status == "pending"
    assert unchanged_program.donations_enabled is True
    unchanged_claim = db.session.get(ClubProgramClaim, pending_claim.id)
    assert unchanged_claim.status == "pending"
    assert unchanged_claim.relationship_type == "finance_director"
    assert unchanged_claim.applicant_message == "Independent pending funding evidence"
    assert ClubProgramManager.query.count() == 0
    assert FundingAdminEvent.query.count() == 0
    assert bridge_app.bridge["sent_emails"] == []


def test_public_program_with_another_manager_conflicts_without_any_mutation(bridge_app, client):
    public_league, program = _seed_team_program(
        slug="bridge-academy-independently-managed",
        platform_status="approved",
        donations_enabled=True,
    )
    user = UserAccount.query.filter_by(email=LOCAL_EMAIL).one()
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
    assert response.get_json()["error"] == (
        "club already has a registry program (bridge-academy-independently-managed); "
        "approve it via the funding claim path"
    )
    db.session.expire_all()
    assert db.session.get(ClubOfficialClaim, official_claim.id).status == "pending"
    unchanged_program = db.session.get(ClubProgram, program.id)
    assert unchanged_program.funding_league_id == public_league.id
    assert unchanged_program.platform_status == "approved"
    assert unchanged_program.donations_enabled is True
    assert unchanged_program.reviewed_by is None
    unchanged_claim = db.session.get(ClubProgramClaim, existing_claim.id)
    assert unchanged_claim.status == "approved"
    assert unchanged_claim.user_account_id == user.id
    assert unchanged_claim.applicant_message == "Independent funding evidence"
    unchanged_manager = db.session.get(ClubProgramManager, existing_manager.id)
    assert unchanged_manager.status == "active"
    assert unchanged_manager.user_account_id == user.id
    assert unchanged_manager.source_claim_id == existing_claim.id
    assert ClubProgramClaim.query.count() == 1
    assert ClubProgramManager.query.count() == 1
    assert FundingAdminEvent.query.count() == 0
    assert FundingLeague.query.filter_by(name=CONSOLE_LEAGUE_NAME).count() == 0
    assert client.get(f"/api/programs/{program.slug}").status_code == 200
    assert bridge_app.bridge["sent_emails"] == []


def test_bridge_created_program_moved_public_is_not_reclaimed(bridge_app, client):
    first_official = _submit_claim(client, TEAM_EMAIL, {"team_api_id": TEAM_API_ID})
    _review(client, first_official.id, "approve")
    program, first_program_claim, first_manager = _bridge_rows(first_official)
    public_league = FundingLeague(
        name="Adopted Bridge Program League",
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
    db.session.add(public_league)
    db.session.flush()
    program.league = public_league
    program.donations_enabled = True
    program.reviewed_by = "funding-admin@example.com"
    program.review_reason = "Adopted into the public funding registry"
    db.session.commit()
    audit_count = FundingAdminEvent.query.count()
    emails_before = len(bridge_app.bridge["sent_emails"])

    second_official = _submit_claim(client, LOCAL_EMAIL, {"team_api_id": TEAM_API_ID})
    response = client.post(
        f"/api/admin/club-claims/{second_official.id}/review",
        json={"action": "approve"},
        headers=_admin_headers(),
    )

    assert response.status_code == 409, response.get_json()
    assert response.get_json()["error"] == (
        f"club already has a registry program ({program.slug}); approve it via the funding claim path"
    )
    db.session.expire_all()
    assert db.session.get(ClubOfficialClaim, second_official.id).status == "pending"
    unchanged_program = db.session.get(ClubProgram, program.id)
    assert unchanged_program.funding_league_id == public_league.id
    assert unchanged_program.donations_enabled is True
    assert unchanged_program.reviewed_by == "funding-admin@example.com"
    assert unchanged_program.review_reason == "Adopted into the public funding registry"
    assert db.session.get(ClubProgramClaim, first_program_claim.id).status == "approved"
    assert db.session.get(ClubProgramManager, first_manager.id).status == "active"
    assert ClubProgramClaim.query.count() == 1
    assert ClubProgramManager.query.count() == 1
    assert FundingAdminEvent.query.count() == audit_count
    assert len(bridge_app.bridge["sent_emails"]) == emails_before


def test_bridge_owned_emergency_hidden_program_blocks_new_approval(bridge_app, client):
    existing_official = _submit_claim(client, TEAM_EMAIL, {"team_api_id": TEAM_API_ID})
    _review(client, existing_official.id, "approve")
    program, existing_program_claim, existing_manager = _bridge_rows(existing_official)
    program.emergency_hidden = True
    db.session.commit()
    emails_before = len(bridge_app.bridge["sent_emails"])

    official_claim = _submit_claim(client, LOCAL_EMAIL, {"team_api_id": TEAM_API_ID})

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
    assert db.session.get(ClubProgramClaim, existing_program_claim.id).status == "approved"
    assert db.session.get(ClubProgramManager, existing_manager.id).status == "active"
    assert ClubProgramClaim.query.count() == 1
    assert ClubProgramManager.query.count() == 1
    assert len(bridge_app.bridge["sent_emails"]) == emails_before


def test_matching_console_league_with_unowned_program_is_not_adopted(bridge_app, client):
    provider_league = League.query.filter_by(league_id=88000).one()
    console_named_league = FundingLeague(
        name=CONSOLE_LEAGUE_NAME,
        country=CONSOLE_LEAGUE_COUNTRY,
        region=CONSOLE_LEAGUE_REGION,
        level="youth_national",
        age_bands=["U18"],
        gender_program="boys",
        season_calendar="aug_may",
        data_tier="api_football",
        league_api_id=provider_league.league_id,
        existing_league_id=provider_league.id,
        registry_status="approved",
        admission_state="open",
    )
    db.session.add(console_named_league)
    db.session.flush()
    unowned_program = ClubProgram(
        funding_league_id=console_named_league.id,
        name="Unrelated Registry Club",
        legal_name="Unrelated Registry Club Association",
        slug="unrelated-preexisting-console-identity",
        country="Japan",
        region="Kanto",
        platform_status="approved",
        donations_enabled=True,
    )
    db.session.add(unowned_program)
    db.session.commit()

    official_claim = _submit_claim(client, TEAM_EMAIL, {"team_api_id": TEAM_API_ID})
    response = client.post(
        f"/api/admin/club-claims/{official_claim.id}/review",
        json={"action": "approve"},
        headers=_admin_headers(),
    )

    assert response.status_code == 409, response.get_json()
    assert response.get_json()["error"] == (
        "console league already contains a registry program (unrelated-preexisting-console-identity); "
        "it cannot be adopted"
    )
    db.session.expire_all()
    assert db.session.get(ClubOfficialClaim, official_claim.id).status == "pending"
    unchanged_league = db.session.get(FundingLeague, console_named_league.id)
    assert unchanged_league.level == "youth_national"
    assert unchanged_league.age_bands == ["U18"]
    assert unchanged_league.data_tier == "api_football"
    assert unchanged_league.league_api_id == provider_league.league_id
    assert unchanged_league.existing_league_id == provider_league.id
    assert unchanged_league.registry_status == "approved"
    assert unchanged_league.admission_state == "open"
    unchanged_program = db.session.get(ClubProgram, unowned_program.id)
    assert unchanged_program.donations_enabled is True
    assert ClubProgramClaim.query.count() == 0
    assert ClubProgramManager.query.count() == 0
    assert TeamProfile.query.count() == 0
    assert FundingAdminEvent.query.count() == 0
    assert bridge_app.bridge["sent_emails"] == []


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
    assert response.get_json()["error"] == (
        f"club already has a registry program ({poisoned_program.slug}); approve it via the funding claim path"
    )
    db.session.expire_all()
    assert db.session.get(ClubOfficialClaim, official_claim.id).status == "pending"
    assert db.session.get(ClubProgram, poisoned_program.id).platform_status == "pending"
    assert ClubProgramClaim.query.count() == 0
    assert ClubProgramManager.query.count() == 0
    assert FundingAdminEvent.query.count() == 0
    assert bridge_app.bridge["sent_emails"] == []


def test_existing_nonbridge_program_claim_is_never_rewritten(bridge_app, client):
    first_official = _submit_claim(client, TEAM_EMAIL, {"team_api_id": TEAM_API_ID})
    _review(client, first_official.id, "approve")
    program, _, _ = _bridge_rows(first_official)
    other_user = UserAccount.query.filter_by(email=LOCAL_EMAIL).one()
    independent_claim = ClubProgramClaim(
        program_id=program.id,
        user_account_id=other_user.id,
        relationship_type="finance_director",
        status="pending",
        applicant_message="Independent evidence must stay untouched",
    )
    db.session.add(independent_claim)
    db.session.commit()
    audit_count = FundingAdminEvent.query.count()
    emails_before = len(bridge_app.bridge["sent_emails"])

    second_official = _submit_claim(client, LOCAL_EMAIL, {"team_api_id": TEAM_API_ID})
    response = client.post(
        f"/api/admin/club-claims/{second_official.id}/review",
        json={"action": "approve"},
        headers=_admin_headers(),
    )

    assert response.status_code == 409, response.get_json()
    assert response.get_json()["error"] == "club already has a funding claim; approve it via the funding claim path"
    db.session.expire_all()
    assert db.session.get(ClubOfficialClaim, second_official.id).status == "pending"
    unchanged_claim = db.session.get(ClubProgramClaim, independent_claim.id)
    assert unchanged_claim.status == "pending"
    assert unchanged_claim.relationship_type == "finance_director"
    assert unchanged_claim.applicant_message == "Independent evidence must stay untouched"
    assert ClubProgramClaim.query.count() == 2
    assert ClubProgramManager.query.count() == 1
    assert FundingAdminEvent.query.count() == audit_count
    assert len(bridge_app.bridge["sent_emails"]) == emails_before


def test_revoked_historical_claim_cannot_replace_current_approved_claim(client):
    first_claim = _submit_claim(client, TEAM_EMAIL, {"team_api_id": TEAM_API_ID})
    _review(client, first_claim.id, "approve")
    first_program, first_program_claim, first_manager = _bridge_rows(first_claim)
    original_ids = (first_program.id, first_program_claim.id, first_manager.id)
    _review(client, first_claim.id, "revoke")

    current_claim = _submit_claim(client, TEAM_EMAIL, {"team_api_id": TEAM_API_ID})
    _review(client, current_claim.id, "approve")

    program, program_claim, manager = _bridge_rows(current_claim)
    assert (program.id, program_claim.id, manager.id) == original_ids
    assert f"ClubOfficialClaim #{current_claim.id}" in program_claim.applicant_message
    assert manager.status == "active"

    response = client.post(
        f"/api/admin/club-claims/{first_claim.id}/review",
        json={"action": "approve"},
        headers=_admin_headers(),
    )

    assert response.status_code == 409, response.get_json()
    assert response.get_json()["error"] == "cannot approve a revoked club-official claim"
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


def test_revoke_resolves_bridge_grant_from_audit_not_mutable_evidence(client):
    official_claim = _submit_claim(client, TEAM_EMAIL, {"team_api_id": TEAM_API_ID})
    _review(client, official_claim.id, "approve")
    program, program_claim, manager = _bridge_rows(official_claim)
    program_claim.applicant_message = "Display evidence changed outside the bridge"
    db.session.commit()

    _review(client, official_claim.id, "revoke")

    db.session.refresh(program_claim)
    db.session.refresh(manager)
    assert program_claim.status == "revoked"
    assert manager.status == "revoked"
    assert client.get(f"/api/club/{program.id}/roster", headers=_user_headers(TEAM_EMAIL)).status_code == 403


def test_revoke_fails_closed_when_creation_ownership_marker_is_missing(client):
    official_claim = _submit_claim(client, TEAM_EMAIL, {"team_api_id": TEAM_API_ID})
    _review(client, official_claim.id, "approve")
    program, program_claim, manager = _bridge_rows(official_claim)
    creation_event = FundingAdminEvent.query.filter_by(
        action="claim.console_bridge_created",
        target_type="claim",
        target_id=program_claim.id,
    ).one()
    db.session.delete(creation_event)
    db.session.commit()

    response = client.post(
        f"/api/admin/club-claims/{official_claim.id}/review",
        json={"action": "revoke"},
        headers=_admin_headers(),
    )

    assert response.status_code == 409, response.get_json()
    assert response.get_json()["error"] == "club console grant ownership could not be verified"
    db.session.expire_all()
    assert db.session.get(ClubOfficialClaim, official_claim.id).status == "approved"
    assert db.session.get(ClubProgramClaim, program_claim.id).status == "approved"
    assert db.session.get(ClubProgramManager, manager.id).status == "active"
    assert FundingAdminEvent.query.filter_by(action="claim.console_bridge_revoked").count() == 0
    assert client.get(f"/api/club/{program.id}/roster", headers=_user_headers(TEAM_EMAIL)).status_code == 200


def test_new_local_claim_after_revoke_reuses_rows_and_system_league(bridge_app, client):
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

    replacement_claim = _submit_claim(
        client,
        LOCAL_EMAIL,
        {"local_club_id": bridge_app.bridge["local_club_id"]},
    )
    _review(client, replacement_claim.id, "approve")
    restored_program, restored_claim, restored_manager = _bridge_rows(replacement_claim)
    assert (restored_program.id, restored_claim.id, restored_manager.id) == original_ids
    assert restored_claim.status == "approved"
    assert f"ClubOfficialClaim #{replacement_claim.id}" in restored_claim.applicant_message
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


def test_merged_away_local_claim_reuses_survivor_program(bridge_app, client):
    target_id = bridge_app.bridge["local_club_id"]
    team_user = UserAccount.query.filter_by(email=TEAM_EMAIL).one()
    source_club = LocalClub(
        name="Old Harbour Juniors",
        normalized_name="old harbour juniors",
        country="Japan",
        city="Kobe",
        level="youth",
        status="verified",
        provenance="user",
        created_by_user_id=team_user.id,
    )
    db.session.add(source_club)
    db.session.commit()

    source_claim = _submit_claim(client, TEAM_EMAIL, {"local_club_id": source_club.id})
    target_claim = _submit_claim(client, LOCAL_EMAIL, {"local_club_id": target_id})
    _review(client, target_claim.id, "approve")
    program, target_program_claim, target_manager = _bridge_rows(target_claim)
    assert program.slug == f"console-local-club-{target_id}"
    assert program.name == "Harbour Juniors"

    merge = client.post(
        f"/api/admin/local-clubs/{source_club.id}/merge",
        json={"into_local_club_id": target_id},
        headers=_admin_headers(),
    )
    assert merge.status_code == 200, merge.get_json()
    _review(client, source_claim.id, "approve")

    source_program, source_program_claim, source_manager = _bridge_rows(source_claim)
    assert source_program.id == program.id
    creation_event = FundingAdminEvent.query.filter_by(action="program.console_bridge_created").one()
    assert creation_event.event_metadata["local_club_id"] == target_id
    assert target_program_claim.id != source_program_claim.id
    assert target_manager.id != source_manager.id
    assert ClubProgram.query.count() == 1
    assert client.get(f"/api/club/{program.id}/roster", headers=_user_headers(TEAM_EMAIL)).status_code == 200
    assert client.get(f"/api/club/{program.id}/roster", headers=_user_headers(LOCAL_EMAIL)).status_code == 200

    _review(client, source_claim.id, "revoke")
    db.session.refresh(source_program_claim)
    db.session.refresh(source_manager)
    db.session.refresh(target_program_claim)
    db.session.refresh(target_manager)
    assert source_program_claim.status == "revoked"
    assert source_manager.status == "revoked"
    assert target_program_claim.status == "approved"
    assert target_manager.status == "active"
    assert client.get(f"/api/club/{program.id}/roster", headers=_user_headers(TEAM_EMAIL)).status_code == 403
    assert client.get(f"/api/club/{program.id}/roster", headers=_user_headers(LOCAL_EMAIL)).status_code == 200


def test_local_grant_revoke_survives_merge_and_reuses_canonical_rows(bridge_app, client):
    target_id = bridge_app.bridge["local_club_id"]
    team_user = UserAccount.query.filter_by(email=TEAM_EMAIL).one()
    source_club = LocalClub(
        name="Riverside Juniors",
        normalized_name="riverside juniors",
        country="South Korea",
        city="Busan",
        level="youth",
        status="verified",
        provenance="user",
        created_by_user_id=team_user.id,
    )
    db.session.add(source_club)
    db.session.commit()

    source_claim = _submit_claim(client, TEAM_EMAIL, {"local_club_id": source_club.id})
    _review(client, source_claim.id, "approve")
    program, program_claim, manager = _bridge_rows(source_claim)
    original_ids = (program.id, program_claim.id, manager.id)
    assert program.slug == f"console-local-club-{source_club.id}"
    assert program.name == "Riverside Juniors"
    assert program.legal_name == "Riverside Juniors"
    assert program.country == "South Korea"
    assert program.city == "Busan"
    program.region = "Source region sentinel"
    db.session.commit()

    merge = client.post(
        f"/api/admin/local-clubs/{source_club.id}/merge",
        json={"into_local_club_id": target_id},
        headers=_admin_headers(),
    )
    assert merge.status_code == 200, merge.get_json()
    _review(client, source_claim.id, "revoke")
    db.session.refresh(program_claim)
    db.session.refresh(manager)
    assert program_claim.status == "revoked"
    assert manager.status == "revoked"
    assert client.get(f"/api/club/{program.id}/roster", headers=_user_headers(TEAM_EMAIL)).status_code == 403

    replacement_claim = _submit_claim(client, TEAM_EMAIL, {"local_club_id": target_id})
    _review(client, replacement_claim.id, "approve")
    restored_program, restored_claim, restored_manager = _bridge_rows(replacement_claim)
    assert (restored_program.id, restored_claim.id, restored_manager.id) == original_ids
    assert restored_program.slug == f"console-local-club-{target_id}"
    assert restored_program.name == "Harbour Juniors"
    assert restored_program.legal_name == "Harbour Juniors"
    assert restored_program.country == "Japan"
    assert restored_program.city == "Kobe"
    assert restored_program.region == "Source region sentinel"
    assert restored_claim.status == "approved"
    assert restored_manager.status == "active"
    assert ClubProgram.query.count() == 1
    assert client.get(f"/api/club/{program.id}/roster", headers=_user_headers(TEAM_EMAIL)).status_code == 200
