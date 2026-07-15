"""F2 league registry, club admission, verification, and save-flow tests."""

from pathlib import Path
from unittest.mock import patch

import pytest
from flask import Flask
from sqlalchemy import text
from src.auth import issue_user_token
from src.extensions import limiter
from src.models.follow import Follow, FollowList
from src.models.funding import ClubConnectAccount, ClubProgramManager, FundingAdminEvent, FundingLeague
from src.models.league import League, UserAccount, db
from src.routes.funding import funding_bp
from src.services.account_roles import derive_account_role


@pytest.fixture
def funding_app(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "funding-admin-test-key")
    monkeypatch.setenv("STRIPE_CONNECT_TEST_MODE", "false")
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    monkeypatch.setenv(
        "FUNDING_EVIDENCE_ENCRYPTION_KEY",
        "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=",
    )
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SECRET_KEY="funding-fixture-secret",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        RATELIMIT_ENABLED=False,
    )
    db.init_app(app)
    limiter.init_app(app)
    app.register_blueprint(funding_bp, url_prefix="/api")
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def funding_client(funding_app):
    return funding_app.test_client()


@pytest.fixture
def admin_headers(funding_app):
    with funding_app.app_context():
        token = issue_user_token("mj-admin@example.com", role="admin")["token"]
    return {
        "Authorization": f"Bearer {token}",
        "X-API-Key": "funding-admin-test-key",
    }


def _user_headers(email="club-manager-fixture@example.com"):
    user = UserAccount(email=email, display_name=email.split("@", 1)[0], display_name_lower=email.split("@", 1)[0])
    db.session.add(user)
    db.session.commit()
    return user, {"Authorization": f"Bearer {issue_user_token(email)['token']}"}


def _league_payload(**overrides):
    payload = {
        "name": "Test League (Fixture)",
        "country": "Japan",
        "region": "Kanto Fixture Region",
        "level": "youth_regional",
        "age_bands": ["U12", "U14"],
        "gender_program": "both",
        "season_calendar": "calendar_year",
        "data_tier": "self_reported",
        "registry_status": "approved",
        "admission_state": "open",
        "reason": "Fixture registry setup",
    }
    payload.update(overrides)
    return payload


def _evidence():
    return {
        "adult_authority_attested": True,
        "official_email": "officer@test-club-fixture.example",
        "authorization_method": "official_domain_email",
        "organization_form": "association",
        "registration_reference": "TEST-REG-FIXTURE-001",
        "official_contact_name": "Test Officer (Fixture)",
        "official_contact_reference": "Fixture association directory entry",
        "safeguarding_contact_email": "safeguarding@test-club-fixture.example",
        "safeguarding_policy_url": "https://example.com/test-fixture-safeguarding",
        "safeguarding_policy_attested": True,
        "eligible_organization_attested": True,
        "payout_control_attested": True,
    }


def _claim_payload(league_id, *, country="Japan", club_name="Test Club Program (Fixture)"):
    return {
        "funding_league_id": league_id,
        "club_name": club_name,
        "legal_name": f"{club_name} Association",
        "country": country,
        "region": "Fixture Region",
        "city": "Fixture City",
        "currency": "JPY" if country == "Japan" else "USD",
        "evidence": _evidence(),
        "applicant_message": "Fixture claim for registry workflow testing.",
    }


def _create_open_league(client, headers, **overrides):
    response = client.post("/api/admin/funding/leagues", json=_league_payload(**overrides), headers=headers)
    assert response.status_code == 201, response.get_json()
    return response.get_json()["league"]


def _submit_claim(client, user_headers, league_id, **overrides):
    payload = _claim_payload(league_id, **overrides)
    response = client.post("/api/funding/claims", json=payload, headers=user_headers)
    assert response.status_code == 201, response.get_json()
    return response.get_json()["claim"]


class TestLeagueRegistry:
    def test_admin_crud_filters_and_admission_transitions(self, funding_app, funding_client, admin_headers):
        with funding_app.app_context():
            created = _create_open_league(funding_client, admin_headers)
            league_id = created["id"]

            filtered = funding_client.get(
                "/api/admin/funding/leagues?admission_state=open&level=youth_regional&q=Fixture",
                headers=admin_headers,
            )
            assert filtered.status_code == 200
            assert [row["id"] for row in filtered.get_json()["leagues"]] == [league_id]

            for state in ("waitlisted", "closed", "open"):
                changed = funding_client.patch(
                    f"/api/admin/funding/leagues/{league_id}",
                    json={"admission_state": state, "reason": f"Fixture transition to {state}"},
                    headers=admin_headers,
                )
                assert changed.status_code == 200, changed.get_json()
                assert changed.get_json()["league"]["admission_state"] == state

            public_rows = funding_client.get("/api/funding/leagues").get_json()["leagues"]
            assert [row["id"] for row in public_rows] == [league_id]

            deleted = funding_client.delete(
                f"/api/admin/funding/leagues/{league_id}",
                json={"reason": "Fixture cleanup"},
                headers=admin_headers,
            )
            assert deleted.status_code == 200
            assert deleted.get_json()["deleted"] is True
            assert db.session.get(FundingLeague, league_id) is None

    def test_api_football_registry_row_bridges_existing_league_read_only(
        self, funding_app, funding_client, admin_headers
    ):
        with funding_app.app_context():
            provider = League(
                league_id=99001,
                name="Test Provider League (Fixture)",
                country="United States",
                season=2026,
            )
            db.session.add(provider)
            db.session.commit()
            response = funding_client.post(
                "/api/admin/funding/leagues",
                json=_league_payload(
                    name="Ignored Fixture Name",
                    country="Ignored Fixture Country",
                    region="Test US Region (Fixture)",
                    data_tier="api_football:99001",
                ),
                headers=admin_headers,
            )
            assert response.status_code == 201, response.get_json()
            league = response.get_json()["league"]
            assert league["name"] == provider.name
            assert league["existing_league_id"] == provider.id
            assert league["is_provider_bridge"] is True
            assert League.query.filter_by(league_id=99001).count() == 1

            update = funding_client.patch(
                f"/api/admin/funding/leagues/{league['id']}",
                json={"name": "Mutated Fixture", "reason": "Should remain read-only"},
                headers=admin_headers,
            )
            assert update.status_code == 409
            delete = funding_client.delete(
                f"/api/admin/funding/leagues/{league['id']}",
                json={"reason": "Should remain bridged"},
                headers=admin_headers,
            )
            assert delete.status_code == 409

    def test_invalid_admission_transition_is_rejected(self, funding_app, funding_client, admin_headers):
        with funding_app.app_context():
            league = _create_open_league(funding_client, admin_headers)
            response = funding_client.patch(
                f"/api/admin/funding/leagues/{league['id']}",
                json={"admission_state": "fundraising", "reason": "Invalid fixture"},
                headers=admin_headers,
            )
            assert response.status_code == 400


class TestClubAdmission:
    def test_non_us_claim_approval_derives_manager_and_verified_without_connect(
        self, funding_app, funding_client, admin_headers
    ):
        with funding_app.app_context():
            league = _create_open_league(funding_client, admin_headers)
            user, headers = _user_headers()
            claim = _submit_claim(funding_client, headers, league["id"])
            assert claim["status"] == "pending"
            assert derive_account_role(user) == "scout"
            stored_email = db.session.execute(
                text("SELECT official_email FROM club_claim_evidence WHERE claim_id = :claim_id"),
                {"claim_id": claim["id"]},
            ).scalar_one()
            assert stored_email.startswith("fernet:v1:")
            assert "officer@test-club-fixture.example" not in stored_email

            approved = funding_client.post(
                f"/api/admin/funding/claims/{claim['id']}/approve",
                json={"reason": "Fixture evidence meets the approved bar"},
                headers=admin_headers,
            )
            assert approved.status_code == 200, approved.get_json()
            reviewed = approved.get_json()["claim"]
            assert reviewed["status"] == "approved"
            assert reviewed["program"]["is_verified_program"] is True
            assert reviewed["connect"] is None
            assert derive_account_role(user) == "club_manager"

            public = funding_client.get(f"/api/programs/{reviewed['program']['slug']}")
            assert public.status_code == 200
            program = public.get_json()["program"]
            assert program["is_verified_program"] is True
            assert program["provenance"]["label"] == "Self-reported"
            assert program["program_provided"] is None

    def test_rejection_requires_reason_and_records_audit(self, funding_app, funding_client, admin_headers):
        with funding_app.app_context():
            league = _create_open_league(funding_client, admin_headers)
            _, headers = _user_headers("rejected-manager-fixture@example.com")
            claim = _submit_claim(
                funding_client,
                headers,
                league["id"],
                club_name="Rejected Test Club (Fixture)",
            )
            missing_reason = funding_client.post(
                f"/api/admin/funding/claims/{claim['id']}/reject", json={}, headers=admin_headers
            )
            assert missing_reason.status_code == 400

            rejected = funding_client.post(
                f"/api/admin/funding/claims/{claim['id']}/reject",
                json={"reason": "Fixture registration evidence does not match"},
                headers=admin_headers,
            )
            assert rejected.status_code == 200
            assert rejected.get_json()["claim"]["status"] == "rejected"
            queue = funding_client.get("/api/admin/funding/claims?status=rejected", headers=admin_headers)
            assert queue.status_code == 200
            audit = queue.get_json()["claims"][0]["audit_trail"]
            assert audit[0]["action"] == "claim.submitted"
            assert audit[-1]["action"] == "claim.rejected"
            assert FundingAdminEvent.query.filter_by(target_type="claim", target_id=claim["id"]).count() == 2

    def test_rejecting_co_manager_claim_does_not_deverify_approved_program(
        self, funding_app, funding_client, admin_headers
    ):
        with funding_app.app_context():
            from src.models.funding import ClubProgram, ClubProgramClaim

            league = _create_open_league(funding_client, admin_headers)
            _, owner_headers = _user_headers("approved-owner-fixture@example.com")
            owner_claim = _submit_claim(funding_client, owner_headers, league["id"])
            approved = funding_client.post(
                f"/api/admin/funding/claims/{owner_claim['id']}/approve",
                json={"reason": "Fixture primary organization authority approved"},
                headers=admin_headers,
            ).get_json()["claim"]
            program = db.session.get(ClubProgram, approved["program"]["id"])
            co_manager, _ = _user_headers("rejected-co-manager-fixture@example.com")
            pending = ClubProgramClaim(
                program_id=program.id,
                user_account_id=co_manager.id,
                relationship_type="club_official",
                status="pending",
            )
            db.session.add(pending)
            db.session.commit()

            rejected = funding_client.post(
                f"/api/admin/funding/claims/{pending.id}/reject",
                json={"reason": "Fixture co-manager authority was not established"},
                headers=admin_headers,
            )
            assert rejected.status_code == 200, rejected.get_json()
            db.session.refresh(program)
            assert rejected.get_json()["claim"]["status"] == "rejected"
            assert program.platform_status == "approved"
            assert program.is_verified_program is True

    def test_proposed_league_waitlists_until_mj_opens_it(self, funding_app, funding_client, admin_headers):
        with funding_app.app_context():
            _, headers = _user_headers("proposal-manager-fixture@example.com")
            payload = _claim_payload(1, club_name="Proposed Test Club (Fixture)")
            payload.pop("funding_league_id")
            payload["proposed_league"] = _league_payload(
                name="Proposed Test League (Fixture)",
                region="Proposed Fixture Region",
            )
            response = funding_client.post("/api/funding/claims", json=payload, headers=headers)
            assert response.status_code == 201, response.get_json()
            body = response.get_json()
            assert body["league_waitlisted"] is True
            claim = body["claim"]
            proposed_id = claim["program"]["league"]["id"]
            proposed = db.session.get(FundingLeague, proposed_id)
            assert proposed.registry_status == "proposed"
            assert proposed.admission_state == "waitlisted"

            blocked = funding_client.post(
                f"/api/admin/funding/claims/{claim['id']}/approve",
                json={"reason": "Fixture approval attempted early"},
                headers=admin_headers,
            )
            assert blocked.status_code == 409

            opened = funding_client.patch(
                f"/api/admin/funding/leagues/{proposed_id}",
                json={
                    "registry_status": "approved",
                    "admission_state": "open",
                    "reason": "MJ fixture registry review completed",
                },
                headers=admin_headers,
            )
            assert opened.status_code == 200
            approved = funding_client.post(
                f"/api/admin/funding/claims/{claim['id']}/approve",
                json={"reason": "Fixture club evidence approved after league opening"},
                headers=admin_headers,
            )
            assert approved.status_code == 200

    def test_us_claim_uses_only_mocked_test_connect_readiness(self, funding_app, funding_client, admin_headers):
        with funding_app.app_context():
            league = _create_open_league(
                funding_client,
                admin_headers,
                name="US Test League (Fixture)",
                country="United States",
                region="US Fixture Region",
            )
            _, headers = _user_headers("us-manager-fixture@example.com")
            claim = _submit_claim(
                funding_client,
                headers,
                league["id"],
                country="United States",
                club_name="US Test Club (Fixture)",
            )
            connect_result = {
                "stripe_account_id": "acct_test_fixture_001",
                "livemode": False,
                "account_type": "express",
                "business_type": "company",
                "details_submitted": True,
                "charges_enabled": False,
                "payouts_enabled": True,
                "transfers_active": True,
                "requirements_due": [],
                "disabled_reason": None,
                "onboarding_url": "https://connect.stripe.com/test-fixture",
                "onboarding_expires_at": None,
            }
            with (
                patch("src.routes.funding.test_connect_configured", return_value=True),
                patch(
                    "src.routes.funding.create_express_organization_onboarding",
                    return_value=connect_result,
                ) as create_connect,
            ):
                approved = funding_client.post(
                    f"/api/admin/funding/claims/{claim['id']}/approve",
                    json={"reason": "Fixture US organization and Connect readiness approved"},
                    headers=admin_headers,
                )
            assert approved.status_code == 200, approved.get_json()
            create_connect.assert_called_once()
            result = approved.get_json()["claim"]
            assert result["program"]["is_verified_program"] is True
            assert result["connect"]["livemode"] is False
            assert result["connect"]["is_ready"] is True

    def test_us_approval_without_test_keys_never_calls_stripe_or_verifies(
        self, funding_app, funding_client, admin_headers
    ):
        with funding_app.app_context():
            league = _create_open_league(
                funding_client,
                admin_headers,
                name="Second US Test League (Fixture)",
                country="United States",
                region="Second US Fixture Region",
            )
            _, headers = _user_headers("us-no-connect-fixture@example.com")
            claim = _submit_claim(
                funding_client,
                headers,
                league["id"],
                country="United States",
                club_name="US Pending Connect Club (Fixture)",
            )
            with patch("src.routes.funding.create_express_organization_onboarding") as create_connect:
                approved = funding_client.post(
                    f"/api/admin/funding/claims/{claim['id']}/approve",
                    json={"reason": "Fixture platform approval; Connect remains pending"},
                    headers=admin_headers,
                )
            assert approved.status_code == 200
            create_connect.assert_not_called()
            result = approved.get_json()["claim"]
            assert result["program"]["is_verified_program"] is False
            assert result["connect"]["stripe_account_id"] is None
            assert ClubConnectAccount.query.count() == 1

    def test_us_connect_sync_recomputes_verification_after_hosted_onboarding(
        self, funding_app, funding_client, admin_headers
    ):
        with funding_app.app_context():
            league = _create_open_league(
                funding_client,
                admin_headers,
                name="Connect Sync US Test League (Fixture)",
                country="United States",
                region="Connect Sync Fixture Region",
            )
            _, headers = _user_headers("connect-sync-manager-fixture@example.com")
            claim = _submit_claim(
                funding_client,
                headers,
                league["id"],
                country="United States",
                club_name="Connect Sync US Test Club (Fixture)",
            )
            approved = funding_client.post(
                f"/api/admin/funding/claims/{claim['id']}/approve",
                json={"reason": "Fixture platform approval before test onboarding"},
                headers=admin_headers,
            ).get_json()["claim"]
            account = ClubConnectAccount.query.one()
            account.stripe_account_id = "acct_test_sync_fixture_001"
            db.session.commit()
            assert approved["program"]["is_verified_program"] is False

            refreshed = {
                "stripe_account_id": account.stripe_account_id,
                "livemode": False,
                "account_type": "express",
                "country": "US",
                "business_type": "company",
                "details_submitted": True,
                "charges_enabled": False,
                "payouts_enabled": True,
                "transfers_active": True,
                "requirements_due": [],
                "disabled_reason": None,
            }
            with patch("src.routes.funding.retrieve_test_express_account", return_value=refreshed) as retrieve:
                synced = funding_client.post(
                    f"/api/admin/funding/programs/{approved['program']['id']}/connect/sync",
                    json={"reason": "Fixture hosted onboarding completed"},
                    headers=admin_headers,
                )
            assert synced.status_code == 200, synced.get_json()
            retrieve.assert_called_once_with("acct_test_sync_fixture_001")
            assert synced.get_json()["program"]["is_verified_program"] is True
            assert synced.get_json()["connect"]["is_ready"] is True
            assert FundingAdminEvent.query.filter_by(action="connect.synced").count() == 1


class TestSaveProgram:
    def test_save_reuses_academy_follow_and_drives_admin_demand(self, funding_app, funding_client, admin_headers):
        with funding_app.app_context():
            league = _create_open_league(funding_client, admin_headers)
            _, manager_headers = _user_headers("save-program-manager-fixture@example.com")
            claim = _submit_claim(funding_client, manager_headers, league["id"])
            approved = funding_client.post(
                f"/api/admin/funding/claims/{claim['id']}/approve",
                json={"reason": "Fixture program approved for save-flow test"},
                headers=admin_headers,
            ).get_json()["claim"]
            slug = approved["program"]["slug"]

            _, saver_headers = _user_headers("program-saver-fixture@example.com")
            first = funding_client.post(
                f"/api/programs/{slug}/save",
                json={"notify_when_fundable": True},
                headers=saver_headers,
            )
            second = funding_client.post(
                f"/api/programs/{slug}/save",
                json={"notify_when_fundable": True},
                headers=saver_headers,
            )
            assert first.status_code == 201
            assert second.status_code == 200
            assert Follow.query.count() == 1
            follow = Follow.query.one()
            assert follow.kind == "academy_club"
            assert follow.selector == {"program_id": approved["program"]["id"]}
            assert follow.notify_when_fundable is True

            duplicate_list = FollowList(
                user_account_id=follow.follow_list.user_account_id,
                name="Duplicate Fixture Signal",
                is_default=False,
            )
            db.session.add(duplicate_list)
            db.session.flush()
            db.session.add(
                Follow(
                    list_id=duplicate_list.id,
                    kind="academy_club",
                    selector={"program_id": approved["program"]["id"]},
                    label=follow.label,
                    notify_when_fundable=True,
                )
            )
            db.session.commit()

            demand = funding_client.get("/api/admin/funding/demand", headers=admin_headers)
            assert demand.status_code == 200, demand.get_json()
            assert demand.get_json()["programs"][0]["saved_count"] == 1
            assert demand.get_json()["by_league"][0] == {
                "league": "Test League (Fixture)",
                "saved_count": 1,
            }


def test_revoke_api_removes_manager_role_and_records_deverification(funding_app, funding_client, admin_headers):
    with funding_app.app_context():
        user = UserAccount(
            email="revoked-manager-fixture@example.com",
            display_name="RevokedManagerFixture",
            display_name_lower="revokedmanagerfixture",
        )
        db.session.add(user)
        league = FundingLeague(
            name="Role Test League (Fixture)",
            country="Japan",
            region="Role Fixture Region",
            level="recreational",
            age_bands=["U12"],
            gender_program="both",
            season_calendar="calendar_year",
            data_tier="self_reported",
            registry_status="approved",
            admission_state="open",
        )
        db.session.add(league)
        db.session.flush()
        from src.models.funding import ClubProgram, ClubProgramClaim

        program = ClubProgram(
            funding_league_id=league.id,
            name="Role Test Club (Fixture)",
            legal_name="Role Test Club Association (Fixture)",
            slug="role-test-club-fixture",
            country="Japan",
            region="Role Fixture Region",
            platform_status="approved",
        )
        db.session.add(program)
        db.session.flush()
        claim = ClubProgramClaim(
            program_id=program.id,
            user_account_id=user.id,
            relationship_type="club_official",
            status="approved",
        )
        db.session.add(claim)
        db.session.flush()
        manager = ClubProgramManager(
            program_id=program.id,
            user_account_id=user.id,
            source_claim_id=claim.id,
            status="active",
            granted_by="mj-admin@example.com",
        )
        db.session.add(manager)
        db.session.commit()
        assert derive_account_role(user) == "club_manager"
        response = funding_client.post(
            f"/api/admin/funding/claims/{claim.id}/revoke",
            json={"reason": "Fixture authority grant withdrawn"},
            headers=admin_headers,
        )
        assert response.status_code == 200, response.get_json()
        assert response.get_json()["claim"]["status"] == "revoked"
        assert response.get_json()["claim"]["program"]["platform_status"] == "suspended"
        assert response.get_json()["claim"]["program"]["is_verified_program"] is False
        assert derive_account_role(user) == "scout"
        assert FundingAdminEvent.query.filter_by(action="claim.revoked", target_id=claim.id).count() == 1


def test_gf01_is_single_head_guarded_and_enables_rls():
    migration = Path(__file__).resolve().parents[1] / "migrations" / "versions" / "gf01_grassroots_identity.py"
    source = migration.read_text()
    assert 'down_revision = "sea01"' in source
    assert source.count("ENABLE ROW LEVEL SECURITY") >= 1
    assert "for table_name in NEW_TABLES" in source
    assert "if not table_exists" in source
    assert "add_column_safe" in source
