"""S3-P2a manager-editable program profiles, moderated updates, and link-out."""

from __future__ import annotations

import pytest
from flask import Flask
from src.auth import issue_user_token
from src.extensions import limiter
from src.models.funding import (
    ClubProgram,
    ClubProgramClaim,
    ClubProgramManager,
    ClubProgramProfileRevision,
    ClubProgramUpdate,
    FundingAdminEvent,
    FundingLeague,
)
from src.models.league import UserAccount, db
from src.routes.club import club_bp
from src.routes.funding import funding_bp

ADMIN_KEY = "club-editing-admin-key"
ADMIN_EMAIL = "editing-admin@example.com"
MANAGER_EMAIL = "editing-manager@example.com"
OUTSIDER_EMAIL = "editing-outsider@example.com"
PENDING_EMAIL = "editing-pending@example.com"

PROFILE_LIMITS = {
    "summary_max": 2000,
    "funding_purpose_max": 1000,
    "list_items_max": 12,
    "list_item_max": 40,
    "media_urls_max": 6,
    "updates_pending_max": 5,
}


def _seed_league_and_program(slug: str, name: str = "Editing Academy") -> ClubProgram:
    league = FundingLeague(
        name=f"Editing League ({slug})",
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
    db.session.add(league)
    db.session.flush()
    program = ClubProgram(
        funding_league_id=league.id,
        name=name,
        legal_name=name,
        slug=slug,
        country="Japan",
        region="Kanto",
        platform_status="approved",
    )
    db.session.add(program)
    db.session.flush()
    return program


def _seed_actor(program: ClubProgram, email: str, *, claim_status: str) -> UserAccount:
    user = UserAccount(
        email=email,
        display_name=email.split("@", 1)[0],
        display_name_lower=email.split("@", 1)[0],
    )
    db.session.add(user)
    db.session.flush()
    claim = ClubProgramClaim(
        program_id=program.id,
        user_account_id=user.id,
        relationship_type="club_official",
        status=claim_status,
    )
    db.session.add(claim)
    db.session.flush()
    if claim_status == "approved":
        db.session.add(
            ClubProgramManager(
                program_id=program.id,
                user_account_id=user.id,
                source_claim_id=claim.id,
                status="active",
                granted_by="fixture",
            )
        )
    db.session.flush()
    return user


def _profile_body(**overrides) -> dict:
    payload = {
        "summary": "A community academy in Kanto.",
        "age_groups": ["U12", "U14"],
        "activities": ["Training", "Matches"],
        "funding_purpose": "New training equipment.",
        "official_url": "https://editing-academy.example",
        "safeguarding_url": "https://editing-academy.example/safeguarding",
        "media_urls": ["https://cdn.example/photo.jpg"],
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def editing_app(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", ADMIN_KEY)
    monkeypatch.setenv("STRIPE_CONNECT_TEST_MODE", "false")
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    monkeypatch.setenv(
        "FUNDING_EVIDENCE_ENCRYPTION_KEY",
        "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=",
    )
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SECRET_KEY="club-editing-fixture-secret",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        RATELIMIT_ENABLED=False,
    )
    db.init_app(app)
    limiter.init_app(app)
    app.register_blueprint(funding_bp, url_prefix="/api")
    app.register_blueprint(club_bp, url_prefix="/api")
    with app.app_context():
        db.create_all()
        program = _seed_league_and_program("editing-academy")
        _seed_actor(program, MANAGER_EMAIL, claim_status="approved")
        _seed_actor(program, PENDING_EMAIL, claim_status="pending")
        outsider = UserAccount(
            email=OUTSIDER_EMAIL,
            display_name="editing-outsider",
            display_name_lower="editing-outsider",
        )
        db.session.add(outsider)
        other_program = _seed_league_and_program("other-academy", name="Other Academy")
        db.session.commit()
        app.editing = {
            "program_id": program.id,
            "program_slug": program.slug,
            "other_program_id": other_program.id,
            "manager_token": issue_user_token(MANAGER_EMAIL)["token"],
            "outsider_token": issue_user_token(OUTSIDER_EMAIL)["token"],
            "pending_token": issue_user_token(PENDING_EMAIL)["token"],
            "admin_token": issue_user_token(ADMIN_EMAIL, role="admin")["token"],
        }
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(editing_app):
    return editing_app.test_client()


def _manager_headers(editing_app) -> dict:
    return {"Authorization": f"Bearer {editing_app.editing['manager_token']}"}


def _admin_headers(editing_app) -> dict:
    return {
        "Authorization": f"Bearer {editing_app.editing['admin_token']}",
        "X-API-Key": ADMIN_KEY,
    }


def _unauthorized_headers(editing_app, which: str) -> dict:
    return {"Authorization": f"Bearer {editing_app.editing[f'{which}_token']}"}


def _public_program(client, editing_app) -> dict:
    response = client.get(f"/api/programs/{editing_app.editing['program_slug']}")
    assert response.status_code == 200, response.get_json()
    return response.get_json()["program"]


def _put_profile(client, editing_app, body: dict):
    return client.put(
        f"/api/club/{editing_app.editing['program_id']}/profile",
        json=body,
        headers=_manager_headers(editing_app),
    )


def _review_revision(client, editing_app, program_id: int, revision_id: int, decision: str):
    return client.post(
        f"/api/admin/funding/programs/{program_id}/profile-revisions/{revision_id}/review",
        json={"decision": decision, "reason": f"Editing test: {decision}"},
        headers=_admin_headers(editing_app),
    )


def _create_update(client, editing_app, title: str = "Weekly round-up"):
    return client.post(
        f"/api/club/{editing_app.editing['program_id']}/updates",
        json={"title": title, "body": "The U14s won their fixture this weekend.", "impact": "Three wins in a row."},
        headers=_manager_headers(editing_app),
    )


class TestManagerAccessControl:
    def test_non_manager_and_pending_claim_user_get_neutral_403_everywhere(self, editing_app, client):
        program_id = editing_app.editing["program_id"]
        probes = (
            ("get", f"/api/club/{program_id}/profile", None),
            ("put", f"/api/club/{program_id}/profile", _profile_body()),
            ("get", f"/api/club/{program_id}/updates", None),
            ("post", f"/api/club/{program_id}/updates", {"title": "Hi", "body": "x" * 30}),
            ("delete", f"/api/club/{program_id}/updates/999", None),
        )
        for which in ("outsider", "pending"):
            headers = _unauthorized_headers(editing_app, which)
            for method, path, body in probes:
                response = getattr(client, method)(path, json=body, headers=headers)
                assert response.status_code == 403, (which, method, path, response.status_code)
                assert response.get_json() == {"error": "Club manager access denied"}


class TestProfileEditing:
    def test_put_creates_then_replaces_pending_revision_in_place(self, editing_app, client):
        first = _put_profile(client, editing_app, _profile_body(summary="First draft summary."))
        assert first.status_code == 200, first.get_json()
        pending = first.get_json()["pending"]
        assert pending["status"] == "pending"
        assert pending["summary"] == "First draft summary."
        assert (
            ClubProgramProfileRevision.query.filter_by(
                program_id=editing_app.editing["program_id"], status="pending"
            ).count()
            == 1
        )

        second = _put_profile(client, editing_app, _profile_body(summary="Second draft summary."))
        assert second.status_code == 200, second.get_json()
        replaced = second.get_json()["pending"]
        assert replaced["id"] == pending["id"], "a second PUT must replace the pending row in place"
        assert replaced["summary"] == "Second draft summary."
        assert (
            ClubProgramProfileRevision.query.filter_by(
                program_id=editing_app.editing["program_id"], status="pending"
            ).count()
            == 1
        )

    def test_get_profile_returns_approved_pending_and_limits(self, editing_app, client):
        response = client.get(
            f"/api/club/{editing_app.editing['program_id']}/profile",
            headers=_manager_headers(editing_app),
        )
        assert response.status_code == 200, response.get_json()
        payload = response.get_json()
        assert payload["program"] == {
            "id": editing_app.editing["program_id"],
            "slug": editing_app.editing["program_slug"],
            "name": "Editing Academy",
        }
        assert payload["approved"] is None
        assert payload["pending"] is None
        assert payload["limits"] == PROFILE_LIMITS

        _put_profile(client, editing_app, _profile_body())
        approved_row = ClubProgramProfileRevision.query.filter_by(status="pending").one()
        _review_revision(client, editing_app, editing_app.editing["program_id"], approved_row.id, "approve")
        _put_profile(client, editing_app, _profile_body(summary="Fresh pending draft."))
        response = client.get(
            f"/api/club/{editing_app.editing['program_id']}/profile",
            headers=_manager_headers(editing_app),
        )
        payload = response.get_json()
        assert payload["approved"]["id"] == approved_row.id
        assert payload["approved"]["status"] == "approved"
        assert payload["pending"]["summary"] == "Fresh pending draft."
        assert payload["pending"]["status"] == "pending"

    def test_pending_revision_never_reaches_public_page(self, editing_app, client):
        program = _public_program(client, editing_app)
        assert program["program_provided"] is None
        _put_profile(client, editing_app, _profile_body(summary="Unapproved summary."))
        program = _public_program(client, editing_app)
        assert program["program_provided"] is None
        assert program["external_support"] is None
        assert program["updates"] == []


class TestExternalSupportValidation:
    def test_rejects_every_unsafe_external_support_url(self, editing_app, client):
        rejects = [
            {"provider": "patreon", "url": "http://patreon.com/creator"},
            {"provider": "patreon", "url": "https://user@patreon.com/creator"},
            {"provider": "patreon", "url": "https://user:pass@patreon.com/creator"},
            {"provider": "patreon", "url": "https://patreon.com:8443/creator"},
            {"provider": "patreon", "url": "https://patreon.com:99999/creator"},
            {"provider": "patreon", "url": "https://patreon.com/creator?ref=attacker"},
            {"provider": "patreon", "url": "https://patreon.com/creator#top"},
            {"provider": "patreon", "url": "https://shop.patreon.com/creator"},
            {"provider": "patreon", "url": "https://patreon.com.evil.tld/creator"},
            {"provider": "patreon", "url": "https://notpatreon.com/creator"},
            {"provider": "patreon", "url": "https://patreon.com"},
            {"provider": "patreon", "url": "https://patreon.com/"},
            {"provider": "patreon", "url": "javascript:alert(1)"},
            {"provider": "patreon"},
            {"provider": "ko-fi", "url": "https://ko-fi.com/creator"},
            {"provider": "patreon", "url": "https://www.patreon.com/creator" + "/x" * 90},
        ]
        for value in rejects:
            response = _put_profile(client, editing_app, _profile_body(external_support=value))
            assert response.status_code == 400, value
            body = response.get_json()
            assert body["error"] == "validation_failed", value
            assert "external_support" in body["fields"], value
            assert ClubProgramProfileRevision.query.count() == 0

    def test_accepts_and_normalises_allowlisted_providers(self, editing_app, client):
        cases = [
            (
                {"provider": "patreon", "url": "https://www.patreon.com/creator"},
                {"provider": "patreon", "url": "https://www.patreon.com/creator"},
            ),
            (
                {"provider": "buy_me_a_coffee", "url": "https://buymeacoffee.com/creator"},
                {"provider": "buy_me_a_coffee", "url": "https://buymeacoffee.com/creator"},
            ),
            (
                {"provider": "patreon", "url": "https://WWW.Patreon.Com/creator/"},
                {"provider": "patreon", "url": "https://www.patreon.com/creator"},
            ),
        ]
        for submitted, expected in cases:
            response = _put_profile(client, editing_app, _profile_body(external_support=submitted))
            assert response.status_code == 200, (submitted, response.get_json())
            pending = response.get_json()["pending"]
            assert pending["external_support"] == expected
            db.session.rollback()
        response = _put_profile(client, editing_app, _profile_body(external_support=None))
        assert response.status_code == 200
        assert response.get_json()["pending"]["external_support"] is None


class TestProfileValidation:
    def test_length_and_list_limits(self, editing_app, client):
        cases = [
            (_profile_body(summary="s" * 2001), "summary"),
            (_profile_body(funding_purpose="f" * 1001), "funding_purpose"),
            (_profile_body(age_groups=[f"U{n}" for n in range(13)]), "age_groups"),
            (_profile_body(age_groups=["x" * 41]), "age_groups"),
            (_profile_body(activities=["y" * 41]), "activities"),
            (_profile_body(media_urls=[f"https://cdn.example/{n}.jpg" for n in range(7)]), "media_urls"),
            (_profile_body(media_urls=["https://cdn.example/" + "x" * 497 + ".jpg"]), "media_urls"),
        ]
        for body, field in cases:
            response = _put_profile(client, editing_app, body)
            assert response.status_code == 400, field
            assert response.get_json()["error"] == "validation_failed"
            assert field in response.get_json()["fields"], field

    def test_https_only_urls(self, editing_app, client):
        cases = [
            (_profile_body(official_url="http://editing-academy.example"), "official_url"),
            (_profile_body(official_url="javascript:alert(1)"), "official_url"),
            (_profile_body(safeguarding_url="ftp://editing-academy.example/policy"), "safeguarding_url"),
            (_profile_body(media_urls=["http://cdn.example/photo.jpg"]), "media_urls"),
        ]
        for body, field in cases:
            response = _put_profile(client, editing_app, body)
            assert response.status_code == 400, field
            assert field in response.get_json()["fields"], field

    def test_multiple_field_errors_are_collected(self, editing_app, client):
        response = _put_profile(
            client,
            editing_app,
            _profile_body(summary="s" * 2001, official_url="http://editing-academy.example"),
        )
        assert response.status_code == 400
        fields = response.get_json()["fields"]
        assert set(fields) == {"summary", "official_url"}

    def test_lists_are_deduped_and_trimmed(self, editing_app, client):
        response = _put_profile(
            client,
            editing_app,
            _profile_body(age_groups=[" U12 ", "U12", "U14"], activities=[" Training "]),
        )
        assert response.status_code == 200, response.get_json()
        pending = response.get_json()["pending"]
        assert pending["age_groups"] == ["U12", "U14"]
        assert pending["activities"] == ["Training"]


class TestAdminProfileReview:
    def test_approve_publishes_summary_and_external_support_with_label(self, editing_app, client):
        program_id = editing_app.editing["program_id"]
        _put_profile(
            client,
            editing_app,
            _profile_body(
                summary="Approved summary.",
                external_support={"provider": "patreon", "url": "https://www.patreon.com/creator"},
            ),
        )
        revision = ClubProgramProfileRevision.query.filter_by(program_id=program_id).one()
        response = _review_revision(client, editing_app, program_id, revision.id, "approve")
        assert response.status_code == 200, response.get_json()
        assert response.get_json()["revision"]["status"] == "approved"

        program = _public_program(client, editing_app)
        assert program["program_provided"]["summary"] == "Approved summary."
        assert program["external_support"] == {
            "provider": "patreon",
            "label": "Patreon",
            "url": "https://www.patreon.com/creator",
        }
        event = FundingAdminEvent.query.filter_by(
            action="profile_revision_approved",
            target_type="club_program_profile_revision",
            target_id=revision.id,
        ).one()
        assert event.reason == "Editing test: approve"

    def test_reapprove_points_public_at_the_newest_approved_revision(self, editing_app, client):
        program_id = editing_app.editing["program_id"]
        _put_profile(
            client,
            editing_app,
            _profile_body(
                summary="First approved.",
                external_support={"provider": "patreon", "url": "https://www.patreon.com/creator"},
            ),
        )
        first = ClubProgramProfileRevision.query.filter_by(program_id=program_id).one()
        _review_revision(client, editing_app, program_id, first.id, "approve")
        _put_profile(
            client,
            editing_app,
            _profile_body(
                summary="Second approved.",
                external_support={"provider": "buy_me_a_coffee", "url": "https://buymeacoffee.com/creator"},
            ),
        )
        second = ClubProgramProfileRevision.query.filter_by(program_id=program_id, status="pending").one()
        _review_revision(client, editing_app, program_id, second.id, "approve")

        program = _public_program(client, editing_app)
        assert program["program_provided"]["summary"] == "Second approved."
        assert program["external_support"]["label"] == "Buy Me a Coffee"
        assert db.session.get(ClubProgram, program_id).approved_profile_revision_id == second.id

    def test_reject_keeps_public_page_unchanged_and_audits(self, editing_app, client):
        program_id = editing_app.editing["program_id"]
        _put_profile(client, editing_app, _profile_body(summary="Approved summary."))
        approved = ClubProgramProfileRevision.query.filter_by(program_id=program_id).one()
        _review_revision(client, editing_app, program_id, approved.id, "approve")
        _put_profile(client, editing_app, _profile_body(summary="Should never publish."))
        rejected = ClubProgramProfileRevision.query.filter_by(program_id=program_id, status="pending").one()
        response = _review_revision(client, editing_app, program_id, rejected.id, "reject")
        assert response.status_code == 200, response.get_json()
        assert response.get_json()["revision"]["status"] == "rejected"

        program = _public_program(client, editing_app)
        assert program["program_provided"]["summary"] == "Approved summary."
        assert db.session.get(ClubProgram, program_id).approved_profile_revision_id == approved.id
        FundingAdminEvent.query.filter_by(
            action="profile_revision_rejected",
            target_type="club_program_profile_revision",
            target_id=rejected.id,
        ).one()

    def test_re_review_conflicts_and_unknown_or_mismatched_ids_return_404(self, editing_app, client):
        program_id = editing_app.editing["program_id"]
        _put_profile(client, editing_app, _profile_body())
        revision = ClubProgramProfileRevision.query.filter_by(program_id=program_id).one()
        _review_revision(client, editing_app, program_id, revision.id, "approve")
        again = _review_revision(client, editing_app, program_id, revision.id, "approve")
        assert again.status_code == 409
        assert again.get_json() == {"error": "revision not pending"}

        unknown = _review_revision(client, editing_app, program_id, 424242, "approve")
        assert unknown.status_code == 404
        mismatch = _review_revision(
            client, editing_app, editing_app.editing["other_program_id"], revision.id, "approve"
        )
        assert mismatch.status_code == 404

    def test_review_requires_decision_and_reason(self, editing_app, client):
        program_id = editing_app.editing["program_id"]
        _put_profile(client, editing_app, _profile_body())
        revision = ClubProgramProfileRevision.query.filter_by(program_id=program_id).one()
        bad_decision = client.post(
            f"/api/admin/funding/programs/{program_id}/profile-revisions/{revision.id}/review",
            json={"decision": "maybe", "reason": "Nope"},
            headers=_admin_headers(editing_app),
        )
        assert bad_decision.status_code == 400
        missing_reason = client.post(
            f"/api/admin/funding/programs/{program_id}/profile-revisions/{revision.id}/review",
            json={"decision": "approve", "reason": "   "},
            headers=_admin_headers(editing_app),
        )
        assert missing_reason.status_code == 400

    def test_admin_queue_lists_pending_revisions_with_program_context(self, editing_app, client):
        program_id = editing_app.editing["program_id"]
        _put_profile(client, editing_app, _profile_body(summary="Queued summary."))
        revision = ClubProgramProfileRevision.query.filter_by(program_id=program_id).one()
        response = client.get("/api/admin/funding/profile-revisions", headers=_admin_headers(editing_app))
        assert response.status_code == 200, response.get_json()
        revisions = response.get_json()["revisions"]
        assert len(revisions) == 1
        assert revisions[0]["id"] == revision.id
        assert revisions[0]["submitted_by_user_id"] is not None
        assert revisions[0]["program"] == {
            "id": program_id,
            "slug": editing_app.editing["program_slug"],
            "name": "Editing Academy",
        }
        assert revisions[0]["summary"] == "Queued summary."

        _review_revision(client, editing_app, program_id, revision.id, "approve")
        response = client.get("/api/admin/funding/profile-revisions", headers=_admin_headers(editing_app))
        assert response.get_json()["revisions"] == []
        response = client.get("/api/admin/funding/profile-revisions?status=all", headers=_admin_headers(editing_app))
        assert [row["status"] for row in response.get_json()["revisions"]] == ["approved"]
        response = client.get("/api/admin/funding/profile-revisions?status=bogus", headers=_admin_headers(editing_app))
        assert response.status_code == 400


class TestProgramUpdates:
    def test_create_is_pending_and_invisible_until_approved(self, editing_app, client):
        response = _create_update(client, editing_app)
        assert response.status_code == 201, response.get_json()
        update = response.get_json()["update"]
        assert update["status"] == "pending"
        assert update["published_at"] is None
        program = _public_program(client, editing_app)
        assert program["updates"] == []

    def test_sixth_pending_update_returns_409(self, editing_app, client):
        for index in range(PROFILE_LIMITS["updates_pending_max"]):
            response = _create_update(client, editing_app, title=f"Round-up {index + 1}")
            assert response.status_code == 201, index
        overflow = _create_update(client, editing_app, title="One too many")
        assert overflow.status_code == 409
        assert overflow.get_json() == {"error": "pending_limit_reached"}

    def test_admin_approve_publishes_update_with_published_at(self, editing_app, client):
        program_id = editing_app.editing["program_id"]
        created = _create_update(client, editing_app).get_json()["update"]
        response = client.post(
            f"/api/admin/funding/programs/{program_id}/updates/{created['id']}/review",
            json={"decision": "approve", "reason": "Publishing round-up"},
            headers=_admin_headers(editing_app),
        )
        assert response.status_code == 200, response.get_json()
        approved = response.get_json()["update"]
        assert approved["status"] == "approved"
        assert approved["published_at"] is not None

        program = _public_program(client, editing_app)
        assert len(program["updates"]) == 1
        published = program["updates"][0]
        assert set(published) == {"id", "title", "body", "impact", "published_at"}
        assert published["id"] == created["id"]
        assert published["published_at"] is not None
        FundingAdminEvent.query.filter_by(
            action="program_update_approved",
            target_type="club_program_update",
            target_id=created["id"],
        ).one()

    def test_admin_reject_never_publishes(self, editing_app, client):
        program_id = editing_app.editing["program_id"]
        created = _create_update(client, editing_app).get_json()["update"]
        response = client.post(
            f"/api/admin/funding/programs/{program_id}/updates/{created['id']}/review",
            json={"decision": "reject", "reason": "Not suitable"},
            headers=_admin_headers(editing_app),
        )
        assert response.status_code == 200
        assert response.get_json()["update"]["status"] == "rejected"
        program = _public_program(client, editing_app)
        assert program["updates"] == []
        FundingAdminEvent.query.filter_by(
            action="program_update_rejected",
            target_type="club_program_update",
            target_id=created["id"],
        ).one()

    def test_update_re_review_and_unknown_ids(self, editing_app, client):
        program_id = editing_app.editing["program_id"]
        created = _create_update(client, editing_app).get_json()["update"]
        review_url = f"/api/admin/funding/programs/{program_id}/updates/{created['id']}/review"
        assert (
            client.post(
                review_url, json={"decision": "approve", "reason": "ok"}, headers=_admin_headers(editing_app)
            ).status_code
            == 200
        )
        again = client.post(
            review_url, json={"decision": "approve", "reason": "ok"}, headers=_admin_headers(editing_app)
        )
        assert again.status_code == 409
        assert again.get_json() == {"error": "update not pending"}
        unknown = client.post(
            f"/api/admin/funding/programs/{program_id}/updates/987654/review",
            json={"decision": "approve", "reason": "ok"},
            headers=_admin_headers(editing_app),
        )
        assert unknown.status_code == 404

    def test_manager_delete_of_approved_update_withdraws_it(self, editing_app, client):
        program_id = editing_app.editing["program_id"]
        created = _create_update(client, editing_app).get_json()["update"]
        client.post(
            f"/api/admin/funding/programs/{program_id}/updates/{created['id']}/review",
            json={"decision": "approve", "reason": "ok"},
            headers=_admin_headers(editing_app),
        )
        assert len(_public_program(client, editing_app)["updates"]) == 1

        response = client.delete(
            f"/api/club/{program_id}/updates/{created['id']}",
            headers=_manager_headers(editing_app),
        )
        assert response.status_code == 200, response.get_json()
        assert response.get_json() == {"deleted": False, "status": "withdrawn"}
        assert _public_program(client, editing_app)["updates"] == []
        row = db.session.get(ClubProgramUpdate, created["id"])
        assert row.status == "withdrawn"
        assert row.published_at is not None

    def test_manager_delete_of_pending_update_removes_the_row(self, editing_app, client):
        program_id = editing_app.editing["program_id"]
        created = _create_update(client, editing_app).get_json()["update"]
        response = client.delete(
            f"/api/club/{program_id}/updates/{created['id']}",
            headers=_manager_headers(editing_app),
        )
        assert response.status_code == 200, response.get_json()
        assert response.get_json() == {"deleted": True, "status": None}
        assert db.session.get(ClubProgramUpdate, created["id"]) is None

    def test_manager_delete_of_another_program_update_returns_404(self, editing_app, client):
        other_id = editing_app.editing["other_program_id"]
        foreign = ClubProgramUpdate(
            program_id=other_id,
            title="Other program update",
            body="Belongs to another program entirely.",
            status="pending",
        )
        db.session.add(foreign)
        db.session.commit()
        response = client.delete(
            f"/api/club/{editing_app.editing['program_id']}/updates/{foreign.id}",
            headers=_manager_headers(editing_app),
        )
        assert response.status_code == 404
        assert response.get_json() == {"error": "update not found"}

    def test_update_validation_shape(self, editing_app, client):
        cases = [
            ({"title": "ab", "body": "b" * 30}, "title"),
            ({"title": "t" * 141, "body": "b" * 30}, "title"),
            ({"title": "Valid title", "body": "too short"}, "body"),
            ({"title": "Valid title", "body": "b" * 4001}, "body"),
            ({"title": "Valid title", "body": "b" * 30, "impact": "i" * 501}, "impact"),
            ({"body": "b" * 30}, "title"),
        ]
        for body, field in cases:
            response = client.post(
                f"/api/club/{editing_app.editing['program_id']}/updates",
                json=body,
                headers=_manager_headers(editing_app),
            )
            assert response.status_code == 400, field
            assert response.get_json()["error"] == "validation_failed"
            assert field in response.get_json()["fields"], field

    def test_manager_update_list_is_newest_first_with_all_statuses(self, editing_app, client):
        program_id = editing_app.editing["program_id"]
        first = _create_update(client, editing_app, title="First update").get_json()["update"]
        second = _create_update(client, editing_app, title="Second update").get_json()["update"]
        client.post(
            f"/api/admin/funding/programs/{program_id}/updates/{first['id']}/review",
            json={"decision": "approve", "reason": "ok"},
            headers=_admin_headers(editing_app),
        )
        response = client.get(f"/api/club/{program_id}/updates", headers=_manager_headers(editing_app))
        assert response.status_code == 200, response.get_json()
        updates = response.get_json()["updates"]
        assert [row["id"] for row in updates] == [second["id"], first["id"]]
        assert updates[0]["status"] == "pending"
        assert updates[1]["status"] == "approved"
        assert set(updates[0]) == {
            "id",
            "title",
            "body",
            "impact",
            "status",
            "review_reason",
            "created_at",
            "published_at",
        }

    def test_admin_update_queue_lists_pending_with_program_context(self, editing_app, client):
        created = _create_update(client, editing_app).get_json()["update"]
        response = client.get("/api/admin/funding/program-updates", headers=_admin_headers(editing_app))
        assert response.status_code == 200, response.get_json()
        updates = response.get_json()["updates"]
        assert [row["id"] for row in updates] == [created["id"]]
        assert updates[0]["program"] == {
            "id": editing_app.editing["program_id"],
            "slug": editing_app.editing["program_slug"],
            "name": "Editing Academy",
        }
        response = client.get("/api/admin/funding/program-updates?status=bogus", headers=_admin_headers(editing_app))
        assert response.status_code == 400


class TestPublicFundableStaysFalse:
    def test_is_fundable_is_false_before_and_after_approval(self, editing_app, client):
        program_id = editing_app.editing["program_id"]
        assert _public_program(client, editing_app)["is_fundable"] is False

        _put_profile(
            client,
            editing_app,
            _profile_body(
                summary="Final summary.",
                external_support={"provider": "patreon", "url": "https://www.patreon.com/creator"},
            ),
        )
        revision = ClubProgramProfileRevision.query.filter_by(program_id=program_id).one()
        _review_revision(client, editing_app, program_id, revision.id, "approve")
        _create_update(client, editing_app)
        update = ClubProgramUpdate.query.filter_by(program_id=program_id).one()
        client.post(
            f"/api/admin/funding/programs/{program_id}/updates/{update.id}/review",
            json={"decision": "approve", "reason": "ok"},
            headers=_admin_headers(editing_app),
        )

        program = _public_program(client, editing_app)
        assert program["is_fundable"] is False
        assert program["external_support"] == {
            "provider": "patreon",
            "label": "Patreon",
            "url": "https://www.patreon.com/creator",
        }
        assert len(program["updates"]) == 1
