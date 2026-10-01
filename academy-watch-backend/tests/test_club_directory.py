"""Clubs near you (p2b1): public directory, moderated location fields, flag-off parity."""

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from flask import Flask
from src.auth import issue_user_token
from src.extensions import limiter
from src.models.funding import (
    ClubProgram,
    ClubProgramClaim,
    ClubProgramManager,
    ClubProgramProfileRevision,
    ClubRosterMember,
    ClubSquad,
    ClubStaff,
    FundingLeague,
)
from src.models.league import UserAccount, db
from src.models.showcase import LocalPlayer
from src.routes.club import club_bp
from src.routes.club_directory import club_directory_bp
from src.routes.funding import funding_bp
from src.services import club_directory
from src.services.club_console_bridge import (
    CONSOLE_LEAGUE_COUNTRY,
    CONSOLE_LEAGUE_NAME,
    CONSOLE_LEAGUE_REGION,
)

ADMIN_KEY = "club-directory-admin-key"
ADMIN_EMAIL = "club-directory-admin@example.com"
FLAG = "CLUB_DIRECTORY_ENABLED"

CARD_KEYS = {
    "id",
    "slug",
    "name",
    "crest_url",
    "brand",
    "country",
    "region",
    "city",
    "league",
    "verified",
    "verified_at",
    "venue",
    "club_level",
    "gender_programs",
    "age_groups",
    "activities",
    "squad_count",
    "distance_km",
}
DIRECTORY_INPUT = {
    "venue_name": "Quayside Park",
    "postcode": "sw1a 1aa",
    "latitude": 51.501009,
    "longitude": -0.141588,
    "club_level": "semi_pro",
    "gender_programs": ["girls", "men", "women"],
}


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", ADMIN_KEY)
    monkeypatch.setenv("ADMIN_IP_WHITELIST", "")
    monkeypatch.delenv(FLAG, raising=False)
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SECRET_KEY="club-directory-fixture-secret",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        RATELIMIT_ENABLED=False,
    )
    db.init_app(app)
    limiter.init_app(app)
    app.register_blueprint(funding_bp, url_prefix="/api")
    app.register_blueprint(club_bp, url_prefix="/api")
    app.register_blueprint(club_directory_bp, url_prefix="/api")
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setenv(FLAG, "true")


def _headers(email):
    return {"Authorization": f"Bearer {issue_user_token(email)['token']}"}


def _admin_headers():
    return {
        "Authorization": f"Bearer {issue_user_token(ADMIN_EMAIL, role='admin')['token']}",
        "X-API-Key": ADMIN_KEY,
    }


def _league(name="Harbour County League", registry_status="approved", **overrides):
    league = FundingLeague(
        name=name,
        country=overrides.pop("country", "England"),
        region=overrides.pop("region", "South Coast"),
        level="recreational",
        age_bands=[],
        gender_program="both",
        season_calendar="aug_may",
        data_tier="self_reported",
        registry_status=registry_status,
        admission_state="open" if registry_status == "approved" else "closed",
    )
    db.session.add(league)
    db.session.flush()
    return league


def _club(
    league,
    name,
    *,
    city="Harbour City",
    region="South Coast",
    country="England",
    status="approved",
    manager="active",
    claim="approved",
    hidden=False,
    directory=None,
    revision_status="approved",
    age_groups=None,
):
    """One program with (optionally) a manager grant and one profile revision."""
    slug = name.lower().replace(" ", "-")
    program = ClubProgram(
        funding_league_id=league.id,
        name=name,
        legal_name=f"{name} Association",
        slug=slug,
        country=country,
        region=region,
        city=city,
        platform_status=status,
        emergency_hidden=hidden,
    )
    user = UserAccount(email=f"{slug}@clubs.example", display_name=f"{name} manager", display_name_lower=slug)
    db.session.add_all([program, user])
    db.session.flush()
    if manager:
        program_claim = ClubProgramClaim(
            program_id=program.id, user_account_id=user.id, relationship_type="club_official", status=claim
        )
        db.session.add(program_claim)
        db.session.flush()
        db.session.add(
            ClubProgramManager(
                program_id=program.id,
                user_account_id=user.id,
                source_claim_id=program_claim.id,
                status=manager,
                granted_by="fixture-admin@example.com",
            )
        )
    if directory is not None or age_groups is not None:
        revision = ClubProgramProfileRevision(
            program_id=program.id,
            submitted_by_user_id=user.id,
            status=revision_status,
            summary=f"{name} profile.",
            age_groups=age_groups or [],
            activities=["Training"],
            media_urls=[],
            **(directory or {}),
        )
        db.session.add(revision)
        db.session.flush()
        if revision_status == "approved":
            program.approved_profile_revision_id = revision.id
    db.session.commit()
    return program


def _pin(lat, lng, **extra):
    return {"latitude": lat, "longitude": lng, "geocode_source": "club_entered", **extra}


def _names(response):
    assert response.status_code == 200, response.get_json()
    return [club["name"] for club in response.get_json()["clubs"]]


def _manager_email(program):
    return f"{program.slug}@clubs.example"


def _profile_body(**overrides):
    body = {
        "summary": "A community club by the harbour.",
        "age_groups": ["U12", "U14"],
        "activities": ["Training"],
        "funding_purpose": None,
        "official_url": None,
        "safeguarding_url": None,
        "media_urls": [],
        "external_support": None,
    }
    body.update(overrides)
    return body


# ---------------------------------------------------------------------------
# Flag off = today
# ---------------------------------------------------------------------------


def _same_response(first, second):
    return (
        first.status_code == second.status_code
        and first.data == second.data
        and first.content_type == second.content_type
        and first.headers.get("Allow") == second.headers.get("Allow")
    )


def test_flag_off_directory_answers_exactly_like_an_unrouted_path(app, client):
    """In the real app an unmatched GET falls to the SPA catch-all (src/main.py ``serve``); so must this."""
    served = []

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def serve(path):
        served.append(path)
        return "spa shell", 200

    _club(_league(), "Harbour City FC")
    for method in ("get", "head", "post", "options"):
        assert _same_response(
            getattr(client, method)("/api/programs"), getattr(client, method)("/api/programs-that-never-existed")
        ), method
    assert client.get("/api/programs").data == b"spa shell"
    assert served[-1] == "api/programs"
    assert "Harbour" not in client.get("/api/programs?q=harbour&lat=1&lng=1").get_data(as_text=True)
    main_source = Path(__file__).resolve().parent.parent.joinpath("src", "main.py").read_text()
    assert '@app.route("/<path:path>")\ndef serve(path):' in main_source


def test_flag_off_directory_is_a_plain_404_without_a_catch_all(client):
    _club(_league(), "Harbour City FC")
    for method in ("get", "head"):
        assert _same_response(
            getattr(client, method)("/api/programs"), getattr(client, method)("/api/programs-that-never-existed")
        ), method
    assert client.get("/api/programs").status_code == 404
    assert client.get("/api/programs?q=harbour&lat=1&lng=1").status_code == 404


def test_flag_off_payloads_carry_no_directory_keys(client):
    program = _club(_league(), "Harbour City FC", directory={"venue_name": "Quayside Park", **_pin(50.8, -1.1)})
    headers = _headers(_manager_email(program))

    profile = client.get(f"/api/club/{program.id}/profile", headers=headers).get_json()
    assert set(profile["approved"]) == EXPECTED_REVISION_KEYS
    assert "directory" not in json.dumps(profile)

    public = client.get(f"/api/programs/{program.slug}").get_json()["program"]
    assert "directory" not in public
    assert "Quayside" not in json.dumps(public)

    saved = client.put(
        f"/api/club/{program.id}/profile",
        json=_profile_body(directory={**DIRECTORY_INPUT, "venue_name": "Sneaky Lane"}),
        headers=headers,
    )
    assert saved.status_code == 200
    assert set(saved.get_json()["pending"]) == EXPECTED_REVISION_KEYS
    pending = ClubProgramProfileRevision.query.filter_by(program_id=program.id, status="pending").one()
    # The submitted object is ignored while off; the draft simply keeps the approved location.
    assert pending.venue_name == "Quayside Park"
    assert (pending.latitude, pending.longitude) == (50.8, -1.1)

    admin = client.get("/api/admin/funding/profile-revisions?status=all", headers=_admin_headers()).get_json()
    assert all("directory" not in revision for revision in admin["revisions"])


EXPECTED_REVISION_KEYS = {
    "id",
    "status",
    "summary",
    "age_groups",
    "activities",
    "funding_purpose",
    "official_url",
    "safeguarding_url",
    "media_urls",
    "external_support",
    "review_reason",
    "reviewed_at",
    "created_at",
}


def test_flag_off_invalid_directory_input_cannot_fail_a_save(client):
    program = _club(_league(), "Harbour City FC")
    saved = client.put(
        f"/api/club/{program.id}/profile",
        json=_profile_body(directory={"latitude": "not-a-number", "club_level": "galactic"}),
        headers=_headers(_manager_email(program)),
    )
    assert saved.status_code == 200


def test_features_key_only_when_on(monkeypatch):
    from src.routes.api import features

    probe = Flask(__name__)
    monkeypatch.delenv(FLAG, raising=False)
    with probe.test_request_context():
        assert "club_directory" not in features().get_json()
    monkeypatch.setenv(FLAG, "true")
    with probe.test_request_context():
        assert features().get_json()["club_directory"] is True


# ---------------------------------------------------------------------------
# Eligibility
# ---------------------------------------------------------------------------


def test_only_eligible_clubs_are_listed(client, on):
    league = _league()
    _club(league, "Harbour City FC")
    _club(league, "Pending Town", status="pending")
    _club(league, "Rejected Town", status="rejected")
    _club(league, "Suspended Town", status="suspended")
    _club(league, "Hidden Town", hidden=True)
    _club(league, "Unmanaged Town", manager=None)
    _club(league, "Revoked Town", manager="revoked")
    _club(league, "Unverified Claim Town", claim="pending")
    _club(league, "Revoked Claim Town", claim="revoked")
    _club(_league("Proposed League", registry_status="proposed"), "Proposed League Town")
    console = FundingLeague(
        name=CONSOLE_LEAGUE_NAME,
        country=CONSOLE_LEAGUE_COUNTRY,
        region=CONSOLE_LEAGUE_REGION,
        level="recreational",
        age_bands=[],
        gender_program="both",
        season_calendar="calendar_year",
        data_tier="self_reported",
        registry_status="proposed",
        admission_state="closed",
    )
    db.session.add(console)
    db.session.flush()
    _club(console, "Console Only Town")

    response = client.get("/api/programs")
    assert _names(response) == ["Harbour City FC"]
    assert response.get_json()["total"] == 1
    assert response.headers["Cache-Control"] == "no-store"


def test_us_club_without_payments_setup_is_still_listed(client, on):
    """Directory standing is not the US-payments meaning of is_verified_program."""
    program = _club(_league("Bay League", country="US", region="California"), "Bay United", country="US")
    assert program.is_verified_program is False
    assert _names(client.get("/api/programs")) == ["Bay United"]


def test_hidden_club_disappears_and_returns_on_lift(client, on):
    league = _league()
    program = _club(league, "Harbour City FC", directory=_pin(50.8, -1.1))
    _club(league, "Millbrook Athletic")
    assert _names(client.get("/api/programs")) == ["Harbour City FC", "Millbrook Athletic"]

    program.emergency_hidden = True
    db.session.commit()
    for query in ("", "?q=harbour", "?lat=50.8&lng=-1.1", "?lat=50.8&lng=-1.1&radius_km=10", "?city=Harbour%20City"):
        response = client.get(f"/api/programs{query}")
        assert "Harbour City FC" not in _names(response), query
        assert "harbour-city-fc" not in response.get_data(as_text=True), query
    assert client.get("/api/programs").get_json()["total"] == 1
    assert client.get(f"/api/programs/{program.slug}").status_code == 404

    program.emergency_hidden = False
    db.session.commit()
    assert _names(client.get("/api/programs")) == ["Harbour City FC", "Millbrook Athletic"]


def test_losing_the_last_manager_removes_the_club(client, on):
    program = _club(_league(), "Harbour City FC")
    assert _names(client.get("/api/programs")) == ["Harbour City FC"]
    ClubProgramManager.query.filter_by(program_id=program.id).one().status = "revoked"
    db.session.commit()
    assert _names(client.get("/api/programs")) == []


# ---------------------------------------------------------------------------
# Payload: clubs, never people
# ---------------------------------------------------------------------------


def test_card_is_an_exact_allowlist_and_never_carries_people(client, on):
    program = _club(
        _league(),
        "Harbour City FC",
        directory={"venue_name": "Quayside Park", "postcode": "HC1 2AB", "club_level": "semi_pro", **_pin(50.8, -1.1)},
        age_groups=["U14", "U16"],
    )
    program.banner_url = "showcase/banners/secret-banner.jpg"
    program.system_brief_body = "Private coaching brief"
    manager = UserAccount.query.filter_by(email=_manager_email(program)).one()
    squad = ClubSquad(program_id=program.id, name="Zzyzx Under-14 Tigers", kind="age_group", age_limit=14)
    seniors = ClubSquad(program_id=program.id, name="Qwerty First Team", kind="first_team")
    db.session.add_all([squad, seniors])
    db.session.flush()
    minor = LocalPlayer(
        display_name="Minorchild Privatename",
        normalized_name="minorchild privatename",
        birth_date=date(datetime.now(UTC).year - 13, 1, 1),
        birth_year=datetime.now(UTC).year - 13,
        status="approved",
        provenance="club",
        origin_program_id=program.id,
    )
    adult = LocalPlayer(
        display_name="Adultplayer Privatename",
        normalized_name="adultplayer privatename",
        birth_date=date(1995, 1, 1),
        birth_year=1995,
        status="approved",
        provenance="club",
        origin_program_id=program.id,
    )
    db.session.add_all([minor, adult])
    db.session.flush()
    db.session.add_all(
        [
            ClubRosterMember(
                program_id=program.id, local_player_id=minor.id, added_by_user_id=manager.id, squad_id=squad.id
            ),
            ClubRosterMember(
                program_id=program.id, local_player_id=adult.id, added_by_user_id=manager.id, squad_id=seniors.id
            ),
            ClubRosterMember(program_id=program.id, player_api_id=987654, added_by_user_id=manager.id),
            ClubStaff(program_id=program.id, display_name="Coachperson Hiddenname", title="Head coach"),
        ]
    )
    db.session.commit()

    for path in ("/api/programs", "/api/programs?lat=50.8&lng=-1.1&radius_km=25", "/api/programs?q=quayside"):
        response = client.get(path)
        body = response.get_json()
        assert set(body) == {"clubs", "page", "per_page", "total", "has_more", "filters"}
        (card,) = body["clubs"]
        assert set(card) == CARD_KEYS
        assert set(card["brand"]) == {"primary_color", "accent_color"}
        assert set(card["venue"]) == {"name", "postcode", "latitude", "longitude"}
        assert card["league"] == {"name": "Harbour County League"}
        assert card["squad_count"] == 2
        assert card["verified"] is True
        text = response.get_data(as_text=True)
        for private in (
            "Minorchild",
            "Adultplayer",
            "Privatename",
            "Coachperson",
            "Zzyzx",
            "Qwerty",
            "987654",
            "secret-banner",
            "coaching brief",
            "clubs.example",
            "birth",
            "roster",
            "is_verified_program",
            "legal_name",
            "Association",
        ):
            assert private not in text, (path, private)

    public = client.get(f"/api/programs/{program.slug}").get_json()["program"]
    assert public["directory"] == {
        "venue": {"name": "Quayside Park", "postcode": "HC1 2AB", "latitude": 50.8, "longitude": -1.1},
        "club_level": "semi_pro",
        "gender_programs": [],
        "squad_count": 2,
    }
    assert "Minorchild" not in json.dumps(public) and "Zzyzx" not in json.dumps(public)


def test_club_without_an_approved_profile_lists_with_empty_offering(client, on):
    _club(_league(), "Harbour City FC")
    (card,) = client.get("/api/programs").get_json()["clubs"]
    assert card["venue"] is None
    assert card["club_level"] is None
    assert card["gender_programs"] == card["age_groups"] == card["activities"] == []
    assert card["squad_count"] == 0
    assert card["distance_km"] is None


def test_open_opportunity_count_is_only_present_when_the_other_lane_provides_it(client, on, monkeypatch):
    program = _club(_league(), "Harbour City FC")
    monkeypatch.setattr(club_directory, "open_opportunity_counts", lambda ids: None)
    assert "open_opportunities" not in client.get("/api/programs").get_json()["clubs"][0]
    monkeypatch.setattr(club_directory, "open_opportunity_counts", lambda ids: {program.id: 2})
    assert client.get("/api/programs").get_json()["clubs"][0]["open_opportunities"] == 2


# ---------------------------------------------------------------------------
# Moderation: only approved values are public
# ---------------------------------------------------------------------------


def test_location_is_promoted_only_by_admin_approval(client, on):
    program = _club(_league(), "Harbour City FC", age_groups=["U12"])
    headers = _headers(_manager_email(program))

    saved = client.put(
        f"/api/club/{program.id}/profile", json=_profile_body(directory=DIRECTORY_INPUT), headers=headers
    )
    assert saved.status_code == 200, saved.get_json()
    pending = saved.get_json()["pending"]
    assert pending["directory"] == {
        "venue_name": "Quayside Park",
        "postcode": "SW1A 1AA",
        "latitude": 51.50101,
        "longitude": -0.14159,
        "club_level": "semi_pro",
        "gender_programs": ["men", "women", "girls"],
    }
    assert db.session.get(ClubProgramProfileRevision, pending["id"]).geocode_source == "club_entered"

    # Still pending: nothing public moved.
    (card,) = client.get("/api/programs").get_json()["clubs"]
    assert card["venue"] is None and card["club_level"] is None and card["gender_programs"] == []
    assert card["age_groups"] == ["U12"]
    assert _names(client.get("/api/programs?lat=51.5&lng=-0.14&radius_km=50")) == []
    assert _names(client.get("/api/programs?q=quayside")) == []
    assert _names(client.get("/api/programs?level=semi_pro")) == []
    assert client.get(f"/api/programs/{program.slug}").get_json()["program"]["directory"]["venue"] is None

    queue = client.get("/api/admin/funding/profile-revisions", headers=_admin_headers()).get_json()["revisions"]
    assert queue[0]["directory"]["venue_name"] == "Quayside Park"

    review = client.post(
        f"/api/admin/funding/programs/{program.id}/profile-revisions/{pending['id']}/review",
        json={"decision": "approve", "reason": "Ground confirmed against the club website."},
        headers=_admin_headers(),
    )
    assert review.status_code == 200
    assert review.get_json()["revision"]["directory"]["postcode"] == "SW1A 1AA"

    (card,) = client.get("/api/programs?lat=51.5&lng=-0.14&radius_km=50").get_json()["clubs"]
    assert card["venue"] == {
        "name": "Quayside Park",
        "postcode": "SW1A 1AA",
        "latitude": 51.50101,
        "longitude": -0.14159,
    }
    assert card["club_level"] == "semi_pro"
    assert card["gender_programs"] == ["men", "women", "girls"]
    assert card["age_groups"] == ["U12", "U14"]
    assert _names(client.get("/api/programs?q=quayside")) == ["Harbour City FC"]


def test_rejected_location_is_never_public(client, on):
    program = _club(_league(), "Harbour City FC", directory={"venue_name": "Old Ground", **_pin(50.0, -1.0)})
    headers = _headers(_manager_email(program))
    pending = client.put(
        f"/api/club/{program.id}/profile",
        json=_profile_body(directory={**DIRECTORY_INPUT, "venue_name": "Wrong Ground"}),
        headers=headers,
    ).get_json()["pending"]
    client.post(
        f"/api/admin/funding/programs/{program.id}/profile-revisions/{pending['id']}/review",
        json={"decision": "reject", "reason": "That is not the club's ground."},
        headers=_admin_headers(),
    )
    (card,) = client.get("/api/programs").get_json()["clubs"]
    assert card["venue"]["name"] == "Old Ground"
    assert "Wrong Ground" not in client.get("/api/programs").get_data(as_text=True)


def test_a_save_without_the_directory_object_keeps_the_approved_location(client, on):
    program = _club(
        _league(),
        "Harbour City FC",
        directory={
            "venue_name": "Quayside Park",
            "club_level": "amateur",
            "gender_programs": ["women"],
            **_pin(50.8, -1.1),
        },
    )
    headers = _headers(_manager_email(program))
    saved = client.put(f"/api/club/{program.id}/profile", json=_profile_body(), headers=headers).get_json()
    assert saved["pending"]["directory"] == {
        "venue_name": "Quayside Park",
        "postcode": None,
        "latitude": 50.8,
        "longitude": -1.1,
        "club_level": "amateur",
        "gender_programs": ["women"],
    }
    # A later explicit null clears the draft's location (still subject to review).
    cleared = client.put(
        f"/api/club/{program.id}/profile", json=_profile_body(directory=None), headers=headers
    ).get_json()
    assert cleared["pending"]["directory"] == {
        "venue_name": None,
        "postcode": None,
        "latitude": None,
        "longitude": None,
        "club_level": None,
        "gender_programs": [],
    }
    assert db.session.get(ClubProgramProfileRevision, cleared["pending"]["id"]).geocode_source is None


@pytest.mark.parametrize(
    ("directory", "field"),
    [
        ({"latitude": 51.5}, "latitude"),
        ({"longitude": -0.1}, "latitude"),
        ({"latitude": 0, "longitude": 0}, "latitude"),
        ({"latitude": 91, "longitude": 0}, "latitude"),
        ({"latitude": 10, "longitude": 181}, "longitude"),
        ({"latitude": "51.5", "longitude": -0.1}, "latitude"),
        ({"latitude": True, "longitude": 1}, "latitude"),
        ({"club_level": "galactic"}, "club_level"),
        ({"gender_programs": ["men", "robots"]}, "gender_programs"),
        ({"gender_programs": "men"}, "gender_programs"),
        ({"postcode": "!!"}, "postcode"),
        ({"postcode": "ABCDEFGHIJKLMNOP"}, "postcode"),
        ({"venue_name": "x" * 121}, "venue_name"),
        ({"venue_name": 12}, "venue_name"),
        ("not-an-object", "directory"),
    ],
)
def test_directory_input_validation(client, on, directory, field):
    program = _club(_league(), "Harbour City FC")
    response = client.put(
        f"/api/club/{program.id}/profile",
        json=_profile_body(directory=directory),
        headers=_headers(_manager_email(program)),
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "validation_failed"
    assert field in response.get_json()["fields"]
    assert ClubProgramProfileRevision.query.filter_by(program_id=program.id, status="pending").count() == 0


def test_venue_name_is_stored_as_plain_text(client, on):
    program = _club(_league(), "Harbour City FC")
    saved = client.put(
        f"/api/club/{program.id}/profile",
        json=_profile_body(directory={"venue_name": "  <b>Quayside</b>   <script>alert(1)</script>Park "}),
        headers=_headers(_manager_email(program)),
    ).get_json()
    assert "<" not in saved["pending"]["directory"]["venue_name"]
    assert saved["pending"]["directory"]["venue_name"].startswith("Quayside")


def test_profile_edit_still_needs_club_permission(client, on):
    league = _league()
    program = _club(league, "Harbour City FC")
    other = _club(league, "Millbrook Athletic")
    response = client.put(
        f"/api/club/{program.id}/profile",
        json=_profile_body(directory=DIRECTORY_INPUT),
        headers=_headers(_manager_email(other)),
    )
    assert response.status_code == 403
    assert client.put(f"/api/club/{program.id}/profile", json=_profile_body()).status_code == 401


# ---------------------------------------------------------------------------
# Search, filters, distance, pagination
# ---------------------------------------------------------------------------


def _seed_region():
    league = _league()
    _club(
        league,
        "Harbour City FC",
        directory={
            "venue_name": "Quayside Park",
            "postcode": "HC1 2AB",
            "club_level": "semi_pro",
            "gender_programs": ["men", "women"],
            **_pin(50.80, -1.10),
        },
    )
    _club(
        league,
        "Millbrook Athletic",
        city="Millbrook",
        directory={"club_level": "grassroots", "gender_programs": ["women", "girls"], **_pin(50.86, -1.02)},
    )
    _club(
        league,
        "Northgate Rovers",
        city="Northgate",
        region="North Shore",
        directory={"club_level": "grassroots", "gender_programs": ["men", "boys"], **_pin(51.40, -1.10)},
    )
    _club(league, "Saltdean Town", city="Saltdean", directory={"venue_name": "Cliff Road", "club_level": "amateur"})
    _club(league, "100%_Real FC", city="Percent Town", country="Wales", region="Gwent")


def test_text_search_is_escaped_and_covers_place_fields(client, on):
    _seed_region()
    assert _names(client.get("/api/programs?q=harbour")) == ["Harbour City FC"]
    assert _names(client.get("/api/programs?q=QUAYSIDE")) == ["Harbour City FC"]
    assert _names(client.get("/api/programs?q=hc1")) == ["Harbour City FC"]
    assert _names(client.get("/api/programs?q=north%20shore")) == ["Northgate Rovers"]
    # LIKE wildcards are literal text, not patterns.
    assert _names(client.get("/api/programs?q=%25%25")) == []
    assert _names(client.get("/api/programs?q=__")) == []
    assert _names(client.get("/api/programs?q=100%25_")) == ["100%_Real FC"]
    assert _names(client.get("/api/programs?q=%5C%5C")) == []
    assert _names(client.get("/api/programs?q=%27%20OR%201%3D1%20--")) == []


def test_place_filters_are_exact_and_case_insensitive(client, on):
    _seed_region()
    assert _names(client.get("/api/programs?country=wales")) == ["100%_Real FC"]
    assert _names(client.get("/api/programs?region=NORTH%20SHORE")) == ["Northgate Rovers"]
    assert _names(client.get("/api/programs?city=harbour%20city")) == ["Harbour City FC"]
    assert _names(client.get("/api/programs?city=harbour")) == []
    assert _names(client.get("/api/programs?city=%25")) == []


def test_offering_filters(client, on):
    _seed_region()
    assert _names(client.get("/api/programs?level=grassroots")) == ["Millbrook Athletic", "Northgate Rovers"]
    assert _names(client.get("/api/programs?level=grassroots,amateur")) == [
        "Millbrook Athletic",
        "Northgate Rovers",
        "Saltdean Town",
    ]
    assert _names(client.get("/api/programs?programme=girls")) == ["Millbrook Athletic"]
    assert _names(client.get("/api/programs?programme=women,girls")) == ["Harbour City FC", "Millbrook Athletic"]
    # "men" must not match inside "women".
    assert _names(client.get("/api/programs?programme=men")) == ["Harbour City FC", "Northgate Rovers"]
    assert _names(client.get("/api/programs?programme=boys&level=semi_pro")) == []
    filters = client.get("/api/programs").get_json()["filters"]
    assert filters == {
        "levels": ["grassroots", "amateur", "semi_pro", "professional"],
        "programmes": ["men", "women", "boys", "girls"],
    }


def test_distance_sort_and_distance_unavailable(client, on):
    _seed_region()
    body = client.get("/api/programs?lat=50.80&lng=-1.10").get_json()
    names = [club["name"] for club in body["clubs"]]
    assert names[:3] == ["Harbour City FC", "Millbrook Athletic", "Northgate Rovers"]
    # Clubs with no approved coordinates come last, by name, with no distance.
    assert names[3:] == ["100%_Real FC", "Saltdean Town"]
    distances = [club["distance_km"] for club in body["clubs"]]
    assert distances[0] == 0.0
    assert distances[1] == pytest.approx(club_directory.haversine_km(50.80, -1.10, 50.86, -1.02), abs=0.06)
    assert distances[2] == pytest.approx(66.7, abs=0.2)
    assert distances[3:] == [None, None]
    assert all(club["distance_km"] is None for club in client.get("/api/programs").get_json()["clubs"])


def test_radius_keeps_only_pinned_clubs_in_range(client, on):
    _seed_region()
    assert _names(client.get("/api/programs?lat=50.80&lng=-1.10&radius_km=5")) == ["Harbour City FC"]
    assert _names(client.get("/api/programs?lat=50.80&lng=-1.10&radius_km=20")) == [
        "Harbour City FC",
        "Millbrook Athletic",
    ]
    assert _names(client.get("/api/programs?lat=50.80&lng=-1.10&radius_km=100&programme=boys")) == ["Northgate Rovers"]
    assert _names(client.get("/api/programs?lat=-33.9&lng=151.2&radius_km=250")) == []


@pytest.mark.parametrize(
    ("origin", "target"),
    [
        ((50.80, -1.10), (51.40, -1.10)),
        ((50.80, -1.10), (50.80, 1.90)),
        ((60.0, 10.0), (61.5, 12.5)),
        ((-33.9, 151.2), (-35.2, 149.1)),
        ((35.0, 179.5), (35.5, -179.4)),
        ((1.0, 103.8), (-0.5, 102.9)),
    ],
)
def test_sql_radius_agrees_with_great_circle_distance(client, on, origin, target):
    """The trig-free SQL distance tracks haversine to well under 1% inside the allowed radius."""
    _club(_league(), "Probe Town", directory=_pin(*target))
    true_km = club_directory.haversine_km(*origin, *target)
    assert true_km < club_directory.MAX_RADIUS_KM
    inside = f"/api/programs?lat={origin[0]}&lng={origin[1]}&radius_km={true_km * 1.005:.3f}"
    outside = f"/api/programs?lat={origin[0]}&lng={origin[1]}&radius_km={true_km * 0.995:.3f}"
    assert _names(client.get(inside)) == ["Probe Town"]
    assert _names(client.get(outside)) == []
    assert client.get(inside).get_json()["clubs"][0]["distance_km"] == pytest.approx(true_km, abs=0.06)


def test_pagination_is_bounded(client, on):
    league = _league()
    for index in range(7):
        _club(league, f"Club {index:02d}")
    first = client.get("/api/programs?per_page=3").get_json()
    assert [club["name"] for club in first["clubs"]] == ["Club 00", "Club 01", "Club 02"]
    assert (first["page"], first["per_page"], first["total"], first["has_more"]) == (1, 3, 7, True)
    last = client.get("/api/programs?per_page=3&page=3").get_json()
    assert [club["name"] for club in last["clubs"]] == ["Club 06"]
    assert last["has_more"] is False
    assert client.get("/api/programs?per_page=3&page=4").get_json()["clubs"] == []
    assert client.get("/api/programs").get_json()["per_page"] == club_directory.DEFAULT_PER_PAGE


@pytest.mark.parametrize(
    "query",
    [
        "per_page=51",
        "per_page=0",
        "per_page=-1",
        "per_page=abc",
        "page=0",
        "page=101",
        "page=1e3",
        "q=a",
        f"q={'x' * 81}",
        f"city={'x' * 121}",
        "lat=50",
        "lng=1",
        "lat=abc&lng=1",
        "lat=86&lng=1",
        "lat=50&lng=181",
        "lat=nan&lng=1",
        "lat=inf&lng=1",
        "radius_km=10",
        "lat=50&lng=1&radius_km=0",
        "lat=50&lng=1&radius_km=251",
        "lat=50&lng=1&radius_km=abc",
        "level=galactic",
        "programme=robots",
        "programme=men,robots",
    ],
)
def test_bad_queries_are_rejected(client, on, query):
    response = client.get(f"/api/programs?{query}")
    assert response.status_code == 400, query
    assert set(response.get_json()) == {"error"}


def test_approved_revision_resolution_matches_the_detail_page(client, on):
    """Stale pointer -> the latest approved revision, exactly like approved_revision_for."""
    program = _club(_league(), "Harbour City FC", directory={"venue_name": "Old Ground"})
    older = db.session.get(ClubProgramProfileRevision, program.approved_profile_revision_id)
    manager = UserAccount.query.filter_by(email=_manager_email(program)).one()
    newer = ClubProgramProfileRevision(
        program_id=program.id,
        submitted_by_user_id=manager.id,
        status="approved",
        age_groups=[],
        activities=[],
        media_urls=[],
        venue_name="New Ground",
        created_at=datetime(2030, 1, 1),
    )
    db.session.add(newer)
    db.session.commit()
    assert client.get("/api/programs").get_json()["clubs"][0]["venue"]["name"] == "Old Ground"
    older.status = "withdrawn"
    db.session.commit()
    assert client.get("/api/programs").get_json()["clubs"][0]["venue"]["name"] == "New Ground"
    assert len(client.get("/api/programs").get_json()["clubs"]) == 1


def test_directory_rate_limit_is_declared():
    source = Path(club_directory.__file__).parent.parent.joinpath("routes", "club_directory.py").read_text()
    assert '@limiter.limit("60 per minute"' in source


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------


def test_p2b1_chains_from_p2a2_and_guards_its_ddl():
    repo_root = Path(__file__).resolve().parent.parent
    config = Config(str(repo_root / "alembic.ini"))
    config.set_main_option("script_location", str(repo_root / "migrations"))
    script = ScriptDirectory.from_config(config)
    assert script.get_revision("p2b1").down_revision == "p2a2"
    source = (repo_root / "migrations" / "versions" / "p2b1_club_directory.py").read_text()
    assert "add_column_safe" in source and "_check_exists" in source
    assert "create_table" not in source
    for column in club_directory.DIRECTORY_FIELDS:
        assert f'"{column}"' in source
        assert hasattr(ClubProgramProfileRevision, column)
