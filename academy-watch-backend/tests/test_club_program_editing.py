"""S3-P2a club profile editing and moderated program-update coverage."""

from datetime import UTC, datetime, timedelta

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
ADMIN_EMAIL = "club-editing-admin@example.com"
MANAGER_EMAIL = "manager@club-editing.example"
PENDING_EMAIL = "pending@club-editing.example"
OUTSIDER_EMAIL = "outsider@club-editing.example"


@pytest.fixture
def editing_app(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", ADMIN_KEY)
    monkeypatch.setenv("ADMIN_IP_WHITELIST", "")
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
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(editing_app):
    return editing_app.test_client()


def _headers(email):
    return {"Authorization": f"Bearer {issue_user_token(email)['token']}"}


def _admin_headers():
    return {
        "Authorization": f"Bearer {issue_user_token(ADMIN_EMAIL, role='admin')['token']}",
        "X-API-Key": ADMIN_KEY,
    }


def _profile_payload(**overrides):
    payload = {
        "summary": "A player-first community academy.",
        "age_groups": ["U12", "U14"],
        "activities": ["Training", "League play"],
        "funding_purpose": "Travel and equipment.",
        "official_url": "https://club-editing.example",
        "safeguarding_url": "https://club-editing.example/safeguarding",
        "media_urls": ["https://club-editing.example/photo.jpg"],
        "external_support": None,
    }
    payload.update(overrides)
    return payload


def _seed_programs():
    league = FundingLeague(
        name="Club Editing League",
        country="Japan",
        region="Kanto",
        level="youth_regional",
        age_bands=["U12", "U14"],
        gender_program="both",
        season_calendar="calendar_year",
        data_tier="self_reported",
        registry_status="approved",
        admission_state="open",
    )
    manager = UserAccount(
        email=MANAGER_EMAIL,
        display_name="Club Manager",
        display_name_lower="club manager",
    )
    pending_user = UserAccount(
        email=PENDING_EMAIL,
        display_name="Pending Manager",
        display_name_lower="pending manager",
    )
    outsider = UserAccount(
        email=OUTSIDER_EMAIL,
        display_name="Outside User",
        display_name_lower="outside user",
    )
    db.session.add_all([league, manager, pending_user, outsider])
    db.session.flush()
    program = ClubProgram(
        funding_league_id=league.id,
        name="Club Editing Academy",
        legal_name="Club Editing Academy Association",
        slug="club-editing-academy",
        country="Japan",
        region="Kanto",
        platform_status="approved",
    )
    other_program = ClubProgram(
        funding_league_id=league.id,
        name="Other Editing Academy",
        legal_name="Other Editing Academy Association",
        slug="other-editing-academy",
        country="Japan",
        region="Kanto",
        platform_status="approved",
    )
    db.session.add_all([program, other_program])
    db.session.flush()
    approved_claim = ClubProgramClaim(
        program_id=program.id,
        user_account_id=manager.id,
        relationship_type="club_official",
        status="approved",
    )
    pending_claim = ClubProgramClaim(
        program_id=program.id,
        user_account_id=pending_user.id,
        relationship_type="club_official",
        status="pending",
    )
    db.session.add_all([approved_claim, pending_claim])
    db.session.flush()
    grant = ClubProgramManager(
        program_id=program.id,
        user_account_id=manager.id,
        source_claim_id=approved_claim.id,
        status="active",
        granted_by="fixture-admin@example.com",
    )
    approved_revision = ClubProgramProfileRevision(
        program_id=program.id,
        submitted_by_user_id=manager.id,
        status="approved",
        summary="The currently approved profile.",
        age_groups=["U12"],
        activities=["Training"],
        funding_purpose="Existing approved purpose.",
        official_url="https://club-editing.example",
        safeguarding_url="https://club-editing.example/safeguarding",
        media_urls=[],
        reviewed_by="fixture-admin@example.com",
        reviewed_at=datetime.now(UTC).replace(tzinfo=None),
    )
    db.session.add_all([grant, approved_revision])
    db.session.flush()
    program.approved_profile_revision_id = approved_revision.id
    db.session.commit()
    return program, other_program, manager, approved_revision


@pytest.mark.parametrize("email", [OUTSIDER_EMAIL, PENDING_EMAIL])
@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("get", "/profile", None),
        ("put", "/profile", _profile_payload()),
        ("get", "/updates", None),
        ("post", "/updates", {"title": "Fixture update", "body": "A sufficiently detailed update body."}),
        ("delete", "/updates/99999", None),
    ],
)
def test_every_manager_route_has_neutral_denial(client, email, method, path, body):
    program, _, _, _ = _seed_programs()
    response = getattr(client, method)(
        f"/api/club/{program.id}{path}",
        json=body,
        headers=_headers(email),
    )
    assert response.status_code == 403
    assert response.get_json() == {"error": "Club manager access denied"}


def test_profile_put_replaces_one_pending_revision_without_changing_public(client):
    program, _, manager, approved = _seed_programs()
    before = client.get(f"/api/programs/{program.slug}").get_json()["program"]
    assert before["program_provided"]["summary"] == approved.summary
    assert before["external_support"] is None
    assert before["is_fundable"] is False

    first = client.put(
        f"/api/club/{program.id}/profile",
        json=_profile_payload(
            summary="First pending profile.",
            age_groups=["U12", "U12", "U16"],
            external_support={"provider": "patreon", "url": "https://www.PATREON.com/creator/"},
        ),
        headers=_headers(manager.email),
    )
    assert first.status_code == 200, first.get_json()
    first_pending = first.get_json()["pending"]
    assert first_pending["age_groups"] == ["U12", "U16"]
    assert first_pending["external_support"] == {
        "provider": "patreon",
        "url": "https://www.patreon.com/creator",
    }

    second = client.put(
        f"/api/club/{program.id}/profile",
        json=_profile_payload(summary="Replacement pending profile."),
        headers=_headers(manager.email),
    )
    assert second.status_code == 200, second.get_json()
    assert second.get_json()["pending"]["id"] == first_pending["id"]
    assert second.get_json()["pending"]["summary"] == "Replacement pending profile."
    assert ClubProgramProfileRevision.query.filter_by(program_id=program.id, status="pending").count() == 1
    assert db.session.get(ClubProgram, program.id).approved_profile_revision_id == approved.id

    profile = client.get(f"/api/club/{program.id}/profile", headers=_headers(manager.email))
    assert profile.status_code == 200
    assert profile.get_json()["approved"]["id"] == approved.id
    assert profile.get_json()["pending"]["id"] == first_pending["id"]
    assert profile.get_json()["limits"]["updates_pending_max"] == 5

    after = client.get(f"/api/programs/{program.slug}").get_json()["program"]
    assert after["program_provided"]["summary"] == approved.summary
    assert after["external_support"] is None
    assert after["is_fundable"] is False


@pytest.mark.parametrize(
    "external_support",
    [
        {"provider": "patreon", "url": "http://patreon.com/creator"},
        {"provider": "patreon", "url": "https://user@patreon.com/creator"},
        {"provider": "patreon", "url": "https://patreon.com:443/creator"},
        {"provider": "patreon", "url": "https://patreon.com/creator?ref=test"},
        {"provider": "patreon", "url": "https://patreon.com/creator#about"},
        {"provider": "patreon", "url": "https://news.patreon.com/creator"},
        {"provider": "patreon", "url": "https://patreon.com.evil.example/creator"},
        {"provider": "patreon", "url": "https://notpatreon.com/creator"},
        {"provider": "patreon", "url": "https://patreon.com"},
        {"provider": "patreon", "url": "javascript:alert(1)"},
        {"provider": "unknown", "url": "https://patreon.com/creator"},
        {"provider": "patreon"},
        "https://patreon.com/creator",
    ],
)
def test_external_support_validation_rejects_unsafe_values(client, external_support):
    program, _, manager, _ = _seed_programs()
    response = client.put(
        f"/api/club/{program.id}/profile",
        json=_profile_payload(external_support=external_support),
        headers=_headers(manager.email),
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "validation_failed"
    assert "external_support" in response.get_json()["fields"]


@pytest.mark.parametrize(
    ("external_support", "expected"),
    [
        (
            {"provider": "patreon", "url": "https://www.Patreon.com/creator/"},
            {"provider": "patreon", "url": "https://www.patreon.com/creator"},
        ),
        (
            {"provider": "buy_me_a_coffee", "url": "https://BUYMEACOFFEE.com/creator/"},
            {"provider": "buy_me_a_coffee", "url": "https://buymeacoffee.com/creator"},
        ),
    ],
)
def test_external_support_accepts_and_normalizes_allowlisted_profiles(client, external_support, expected):
    program, _, manager, _ = _seed_programs()
    response = client.put(
        f"/api/club/{program.id}/profile",
        json=_profile_payload(external_support=external_support),
        headers=_headers(manager.email),
    )
    assert response.status_code == 200, response.get_json()
    assert response.get_json()["pending"]["external_support"] == expected


def test_profile_urls_with_query_strings_round_trip_byte_identically(client):
    program, _, manager, _ = _seed_programs()
    official_url = "https://club-editing.example/watch?v=x&t=10s"
    safeguarding_url = "https://club-editing.example/policy?lang=en&version=2"
    media_url = "https://club-editing.example/photo?id=7&size=large"
    response = client.put(
        f"/api/club/{program.id}/profile",
        json=_profile_payload(
            official_url=official_url,
            safeguarding_url=safeguarding_url,
            media_urls=[media_url],
        ),
        headers=_headers(manager.email),
    )
    assert response.status_code == 200, response.get_json()
    pending = response.get_json()["pending"]
    assert pending["official_url"] == official_url
    assert pending["safeguarding_url"] == safeguarding_url
    assert pending["media_urls"] == [media_url]


def test_profile_and_update_prose_round_trip_as_plain_text(client):
    program, _, manager, _ = _seed_programs()
    prose = "Boys & girls <3"
    profile = client.put(
        f"/api/club/{program.id}/profile",
        json=_profile_payload(summary=prose, funding_purpose=prose),
        headers=_headers(manager.email),
    )
    assert profile.status_code == 200, profile.get_json()
    stored_profile = db.session.get(ClubProgramProfileRevision, profile.get_json()["pending"]["id"])
    assert stored_profile.created_at.tzinfo is None
    fetched = client.get(f"/api/club/{program.id}/profile", headers=_headers(manager.email))
    assert fetched.get_json()["pending"]["summary"] == prose
    assert fetched.get_json()["pending"]["funding_purpose"] == prose

    title = "Boys & girls update"
    body = "Boys & girls train together every week."
    update = client.post(
        f"/api/club/{program.id}/updates",
        json={"title": title, "body": body, "impact": prose},
        headers=_headers(manager.email),
    )
    assert update.status_code == 201, update.get_json()
    update_id = update.get_json()["update"]["id"]
    assert db.session.get(ClubProgramUpdate, update_id).created_at.tzinfo is None
    approved = client.post(
        f"/api/admin/funding/programs/{program.id}/updates/{update_id}/review",
        json={"decision": "approve", "reason": "Plain-text round-trip fixture."},
        headers=_admin_headers(),
    )
    assert approved.status_code == 200, approved.get_json()
    public_update = client.get(f"/api/programs/{program.slug}").get_json()["program"]["updates"][0]
    assert public_update["title"] == title
    assert public_update["body"] == body
    assert public_update["impact"] == prose


@pytest.mark.parametrize(
    ("override", "field"),
    [
        ({"summary": "s" * 2001}, "summary"),
        ({"funding_purpose": "p" * 1001}, "funding_purpose"),
        ({"age_groups": [f"U{index}" for index in range(13)]}, "age_groups"),
        ({"activities": ["x" * 41]}, "activities"),
        ({"official_url": "http://club-editing.example"}, "official_url"),
        ({"safeguarding_url": "javascript:alert(1)"}, "safeguarding_url"),
        ({"media_urls": [f"https://club-editing.example/{index}" for index in range(7)]}, "media_urls"),
        ({"media_urls": ["http://club-editing.example/photo.jpg"]}, "media_urls"),
    ],
)
def test_profile_field_limits_and_https_urls_are_validated(client, override, field):
    program, _, manager, _ = _seed_programs()
    response = client.put(
        f"/api/club/{program.id}/profile",
        json=_profile_payload(**override),
        headers=_headers(manager.email),
    )
    assert response.status_code == 400
    assert field in response.get_json()["fields"]


def test_profile_admin_approval_and_rejection_are_audited_and_public(client):
    program, _, manager, approved = _seed_programs()
    created = client.put(
        f"/api/club/{program.id}/profile",
        json=_profile_payload(
            summary="A newly approved public summary.",
            external_support={"provider": "buy_me_a_coffee", "url": "https://buymeacoffee.com/creator"},
        ),
        headers=_headers(manager.email),
    ).get_json()["pending"]
    queue = client.get("/api/admin/funding/profile-revisions", headers=_admin_headers())
    assert queue.status_code == 200
    assert [item["id"] for item in queue.get_json()["revisions"]] == [created["id"]]
    assert queue.get_json()["revisions"][0]["program"]["slug"] == program.slug

    reviewed = client.post(
        f"/api/admin/funding/programs/{program.id}/profile-revisions/{created['id']}/review",
        json={"decision": "approve", "reason": "The profile meets the publishing standard."},
        headers=_admin_headers(),
    )
    assert reviewed.status_code == 200, reviewed.get_json()
    assert reviewed.get_json()["revision"]["status"] == "approved"
    approved_revision = db.session.get(ClubProgramProfileRevision, created["id"])
    assert approved_revision.reviewed_by == ADMIN_EMAIL
    assert approved_revision.reviewed_at.tzinfo is None
    public = client.get(f"/api/programs/{program.slug}").get_json()["program"]
    assert public["program_provided"]["summary"] == "A newly approved public summary."
    assert public["external_support"] == {
        "provider": "buy_me_a_coffee",
        "label": "Buy Me a Coffee",
        "url": "https://buymeacoffee.com/creator",
    }
    assert public["is_fundable"] is False
    assert (
        FundingAdminEvent.query.filter_by(
            action="profile_revision_approved",
            target_type="club_program_profile_revision",
            target_id=created["id"],
        ).count()
        == 1
    )

    rejected = client.put(
        f"/api/club/{program.id}/profile",
        json=_profile_payload(summary="A profile that will be rejected."),
        headers=_headers(manager.email),
    ).get_json()["pending"]
    rejection = client.post(
        f"/api/admin/funding/programs/{program.id}/profile-revisions/{rejected['id']}/review",
        json={"decision": "reject", "reason": "The evidence needs clarification."},
        headers=_admin_headers(),
    )
    assert rejection.status_code == 200
    assert rejection.get_json()["revision"]["status"] == "rejected"
    rejected_revision = db.session.get(ClubProgramProfileRevision, rejected["id"])
    assert rejected_revision.reviewed_by == ADMIN_EMAIL
    assert rejected_revision.reviewed_at.tzinfo is None
    assert (
        FundingAdminEvent.query.filter_by(
            action="profile_revision_rejected",
            target_type="club_program_profile_revision",
            target_id=rejected["id"],
        ).count()
        == 1
    )
    unchanged = client.get(f"/api/programs/{program.slug}").get_json()["program"]
    assert unchanged["program_provided"]["summary"] == "A newly approved public summary."
    assert db.session.get(ClubProgram, program.id).approved_profile_revision_id != approved.id

    rereview = client.post(
        f"/api/admin/funding/programs/{program.id}/profile-revisions/{rejected['id']}/review",
        json={"decision": "approve", "reason": "Attempted second decision."},
        headers=_admin_headers(),
    )
    assert rereview.status_code == 409
    assert rereview.get_json() == {"error": "revision not pending"}


def test_program_updates_moderate_publish_withdraw_and_enforce_pending_limit(client):
    program, other_program, manager, _ = _seed_programs()
    update_ids = []
    for index in range(5):
        response = client.post(
            f"/api/club/{program.id}/updates",
            json={
                "title": f"Program update {index}",
                "body": f"This is sufficiently detailed fixture update body number {index}.",
                "impact": "Players received direct support.",
            },
            headers=_headers(manager.email),
        )
        assert response.status_code == 201, response.get_json()
        update_ids.append(response.get_json()["update"]["id"])
    assert client.get(f"/api/programs/{program.slug}").get_json()["program"]["updates"] == []

    sixth = client.post(
        f"/api/club/{program.id}/updates",
        json={"title": "Sixth update", "body": "This sixth pending update must be rejected."},
        headers=_headers(manager.email),
    )
    assert sixth.status_code == 409
    assert sixth.get_json() == {"error": "pending_limit_reached"}

    queue = client.get("/api/admin/funding/program-updates", headers=_admin_headers())
    assert queue.status_code == 200
    assert {item["id"] for item in queue.get_json()["updates"]} == set(update_ids)
    approved = client.post(
        f"/api/admin/funding/programs/{program.id}/updates/{update_ids[0]}/review",
        json={"decision": "approve", "reason": "Useful, factual program update."},
        headers=_admin_headers(),
    )
    assert approved.status_code == 200, approved.get_json()
    assert approved.get_json()["update"]["published_at"] is not None
    approved_update = db.session.get(ClubProgramUpdate, update_ids[0])
    assert approved_update.reviewed_by == ADMIN_EMAIL
    assert approved_update.reviewed_at.tzinfo is None
    assert approved_update.published_at.tzinfo is None
    public_updates = client.get(f"/api/programs/{program.slug}").get_json()["program"]["updates"]
    assert [item["id"] for item in public_updates] == [update_ids[0]]
    assert set(public_updates[0]) == {"id", "title", "body", "impact", "published_at"}
    assert (
        FundingAdminEvent.query.filter_by(
            action="program_update_approved",
            target_type="club_program_update",
            target_id=update_ids[0],
        ).count()
        == 1
    )

    rejected = client.post(
        f"/api/admin/funding/programs/{program.id}/updates/{update_ids[1]}/review",
        json={"decision": "reject", "reason": "This update needs more evidence."},
        headers=_admin_headers(),
    )
    assert rejected.status_code == 200, rejected.get_json()
    rejected_update = db.session.get(ClubProgramUpdate, update_ids[1])
    assert rejected_update.reviewed_by == ADMIN_EMAIL
    assert rejected_update.reviewed_at.tzinfo is None

    withdrawn = client.delete(
        f"/api/club/{program.id}/updates/{update_ids[0]}",
        headers=_headers(manager.email),
    )
    assert withdrawn.status_code == 200
    assert withdrawn.get_json() == {"deleted": False, "status": "withdrawn"}
    assert client.get(f"/api/programs/{program.slug}").get_json()["program"]["updates"] == []
    withdrawn_again = client.delete(
        f"/api/club/{program.id}/updates/{update_ids[0]}",
        headers=_headers(manager.email),
    )
    assert withdrawn_again.status_code == 200
    assert withdrawn_again.get_json() == {"deleted": False, "status": "withdrawn"}
    assert db.session.get(ClubProgramUpdate, update_ids[0]).status == "withdrawn"

    rejected_delete = client.delete(
        f"/api/club/{program.id}/updates/{update_ids[1]}",
        headers=_headers(manager.email),
    )
    assert rejected_delete.get_json() == {"deleted": True, "status": None}
    assert db.session.get(ClubProgramUpdate, update_ids[1]) is None

    foreign_update = ClubProgramUpdate(
        program_id=other_program.id,
        author_user_id=manager.id,
        title="Another program update",
        body="This update belongs to a different club program.",
    )
    db.session.add(foreign_update)
    db.session.commit()
    foreign_delete = client.delete(
        f"/api/club/{program.id}/updates/{foreign_update.id}",
        headers=_headers(manager.email),
    )
    assert foreign_delete.status_code == 404
    assert foreign_delete.get_json() == {"error": "update not found"}


def test_public_updates_are_capped_at_ten_and_ordered_by_newest_publication(client):
    program, _, manager, _ = _seed_programs()
    first_published_at = datetime(2026, 1, 1, 12, 0)
    updates = []
    for index in range(11):
        update = ClubProgramUpdate(
            program_id=program.id,
            author_user_id=manager.id,
            title=f"Approved update {index}",
            body=f"This is approved public update body number {index}.",
            status="approved",
            published_at=first_published_at + timedelta(hours=index),
        )
        db.session.add(update)
        updates.append(update)
    db.session.commit()

    response = client.get(f"/api/programs/{program.slug}")
    assert response.status_code == 200
    public_updates = response.get_json()["program"]["updates"]
    expected = list(reversed(updates[1:]))
    assert len(public_updates) == 10
    assert [item["id"] for item in public_updates] == [update.id for update in expected]
    assert [item["published_at"] for item in public_updates] == [update.published_at.isoformat() for update in expected]


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"title": "No", "body": "This body is long enough for validation."}, "title"),
        ({"title": "Valid title", "body": "Too short"}, "body"),
        ({"title": "Valid title", "body": "This body is long enough for validation.", "impact": "x" * 501}, "impact"),
    ],
)
def test_program_update_field_limits(client, payload, field):
    program, _, manager, _ = _seed_programs()
    response = client.post(
        f"/api/club/{program.id}/updates",
        json=payload,
        headers=_headers(manager.email),
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "validation_failed"
    assert field in response.get_json()["fields"]
