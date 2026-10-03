"""Clubs near you (p2b1): public directory, moderated location fields, flag-off parity."""

import json
import math
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qsl

import pytest
import test_club_console_bridge as console_bridge
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

# The real claim-bridge fixture (its own app, users and local club), for the onboarding test below.
bridge_app = console_bridge.bridge_app

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


SEARCH_URL = "/api/club-directory/search"


def _search(client, query="", **body):
    """A search with a position or search words: always the POST body, never the URL."""
    return client.post(SEARCH_URL, json={**dict(parse_qsl(query, keep_blank_values=True)), **body})


def _console_league_row():
    league = FundingLeague(
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
    db.session.add(league)
    db.session.flush()
    return league


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
        and _allow(first) == _allow(second)
    )


def _allow(response):
    return sorted(method.strip() for method in response.headers.get("Allow", "").split(",") if method.strip())


def test_flag_off_directory_answers_exactly_like_an_unrouted_path(app, client):
    """In the real app an unmatched GET falls to the SPA catch-all (src/main.py ``serve``); so must this."""
    served = []

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def serve(path):
        served.append(path)
        return "spa shell", 200

    _club(_league(), "Harbour City FC")
    for method in ("get", "head", "post", "put", "patch", "delete", "options"):
        assert _same_response(
            getattr(client, method)("/api/programs"), getattr(client, method)("/api/programs-that-never-existed")
        ), method
        assert _same_response(
            getattr(client, method)(SEARCH_URL), getattr(client, method)("/api/club-directory/never-existed")
        ), method
    assert client.get("/api/programs").data == b"spa shell"
    assert served[-1] == "api/programs"
    assert client.get("/api/programs?q=harbour&lat=1&lng=1").data == b"spa shell"
    refused = _search(client, "q=harbour&lat=1&lng=1")
    assert refused.status_code == 405
    assert _allow(refused) == ["GET", "HEAD", "OPTIONS"]
    assert "Harbour" not in refused.get_data(as_text=True)
    main_source = Path(__file__).resolve().parent.parent.joinpath("src", "main.py").read_text()
    assert '@app.route("/<path:path>")\ndef serve(path):' in main_source


def test_flag_off_directory_is_a_plain_404_without_a_catch_all(client):
    _club(_league(), "Harbour City FC")
    for method in ("get", "head"):
        assert _same_response(
            getattr(client, method)("/api/programs"), getattr(client, method)("/api/programs-that-never-existed")
        ), method
    for method in ("get", "head", "post", "put", "patch", "delete", "options"):
        assert _same_response(
            getattr(client, method)(SEARCH_URL), getattr(client, method)("/api/club-directory/never-existed")
        ), method
    assert client.get("/api/programs").status_code == 404
    assert client.get("/api/programs?q=harbour&lat=1&lng=1").status_code == 404
    assert _search(client, "q=harbour&lat=1&lng=1").status_code == 404


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
    _club(_league("Rejected League", registry_status="rejected"), "Rejected League Town")

    response = client.get("/api/programs")
    assert _names(response) == ["Harbour City FC"]
    assert response.get_json()["total"] == 1
    assert response.headers["Cache-Control"] == "no-store"


def test_console_local_club_is_listed_but_a_real_unapproved_league_is_not(client, on):
    """Console clubs are the ones being onboarded: the funding-league check only binds real leagues."""
    console = _console_league_row()
    listed = _club(console, "Console Local Town", directory={"venue_name": "Rec Ground", **_pin(50.8, -1.1)})
    _club(_league("Proposed League", registry_status="proposed"), "Proposed League Town", directory=_pin(50.8, -1.1))
    # A console club still needs everything else.
    _club(console, "Console Unmanaged Town", manager=None)
    _club(console, "Console Revoked Town", manager="revoked")
    _club(console, "Console Unverified Town", claim="pending")
    _club(console, "Console Hidden Town", hidden=True)
    _club(console, "Console Pending Town", status="pending")

    body = client.get("/api/programs").get_json()
    assert [club["name"] for club in body["clubs"]] == ["Console Local Town"]
    assert body["total"] == 1
    card = body["clubs"][0]
    assert set(card) == CARD_KEYS
    # The reserved league is plumbing, not a public league name.
    assert card["league"] is None
    assert CONSOLE_LEAGUE_NAME not in json.dumps(body)
    assert _names(_search(client, "lat=50.8&lng=-1.1&radius_km=5")) == ["Console Local Town"]

    # Every card opens: the listed console club has its page, with the same league rule.
    page = client.get(f"/api/programs/{listed.slug}")
    assert page.status_code == 200
    program = page.get_json()["program"]
    assert program["league"] is None
    assert program["directory"]["venue"]["name"] == "Rec Ground"
    assert CONSOLE_LEAGUE_NAME not in page.get_data(as_text=True)
    for slug in ("proposed-league-town", "console-unmanaged-town", "console-revoked-town", "console-hidden-town"):
        assert client.get(f"/api/programs/{slug}").status_code == 404, slug


def test_console_local_club_page_stays_private_while_the_flag_is_off(client):
    program = _club(_console_league_row(), "Console Local Town", directory=_pin(50.8, -1.1))
    assert client.get(f"/api/programs/{program.slug}").status_code == 404


@pytest.mark.parametrize("cause", ["manager", "claim"])
def test_losing_standing_removes_directory_data_from_the_club_page(client, on, cause):
    """RB1-3: the detail page uses the list's eligibility; a known slug is not a way around removal."""
    program = _club(
        _league(),
        "Harbour City FC",
        directory={"venue_name": "Private After Revocation", "club_level": "amateur", **_pin(51.5, -0.1)},
    )
    assert client.get(f"/api/programs/{program.slug}").get_json()["program"]["directory"]["venue"]["latitude"] == 51.5
    if cause == "manager":
        ClubProgramManager.query.filter_by(program_id=program.id).one().status = "revoked"
    else:
        ClubProgramClaim.query.filter_by(program_id=program.id).one().status = "rejected"
    db.session.commit()

    assert client.get("/api/programs").get_json()["total"] == 0
    detail = client.get(f"/api/programs/{program.slug}")
    # The legacy registry page of a club in an approved league is unchanged; its directory data is gone.
    assert detail.status_code == 200
    assert detail.get_json()["program"]["directory"] is None
    text = detail.get_data(as_text=True)
    assert "Private After Revocation" not in text and "51.5" not in text and "amateur" not in text


@pytest.mark.parametrize("cause", ["manager", "claim"])
def test_console_local_club_page_is_gone_once_standing_is_lost(client, on, cause):
    program = _club(_console_league_row(), "Console Local Town", directory=_pin(51.5, -0.1))
    assert client.get(f"/api/programs/{program.slug}").status_code == 200
    if cause == "manager":
        ClubProgramManager.query.filter_by(program_id=program.id).one().status = "revoked"
    else:
        ClubProgramClaim.query.filter_by(program_id=program.id).one().status = "revoked"
    db.session.commit()
    assert client.get("/api/programs").get_json()["total"] == 0
    assert client.get(f"/api/programs/{program.slug}").status_code == 404


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
    for query in ("", "q=harbour", "lat=50.8&lng=-1.1", "lat=50.8&lng=-1.1&radius_km=10", "city=Harbour City"):
        for response in (_search(client, query), client.get("/api/programs?city=Harbour%20City")):
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

    for response in (
        client.get("/api/programs"),
        _search(client, "lat=50.8&lng=-1.1&radius_km=25"),
        _search(client, "q=quayside"),
    ):
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
            assert private not in text, private

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
    assert _names(_search(client, "lat=51.5&lng=-0.14&radius_km=50")) == []
    assert _names(_search(client, "q=quayside")) == []
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

    (card,) = _search(client, "lat=51.5&lng=-0.14&radius_km=50").get_json()["clubs"]
    assert card["venue"] == {
        "name": "Quayside Park",
        "postcode": "SW1A 1AA",
        "latitude": 51.50101,
        "longitude": -0.14159,
    }
    assert card["club_level"] == "semi_pro"
    assert card["gender_programs"] == ["men", "women", "girls"]
    assert card["age_groups"] == ["U12", "U14"]
    assert _names(_search(client, "q=quayside")) == ["Harbour City FC"]


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
    assert _names(_search(client, "q=harbour")) == ["Harbour City FC"]
    assert _names(_search(client, "q=QUAYSIDE")) == ["Harbour City FC"]
    assert _names(_search(client, "q=hc1")) == ["Harbour City FC"]
    assert _names(_search(client, "q=north%20shore")) == ["Northgate Rovers"]
    # LIKE wildcards are literal text, not patterns.
    assert _names(_search(client, "q=%25%25")) == []
    assert _names(_search(client, "q=__")) == []
    assert _names(_search(client, "q=100%25_")) == ["100%_Real FC"]
    assert _names(_search(client, "q=%5C%5C")) == []
    assert _names(_search(client, "q=%27%20OR%201%3D1%20--")) == []


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
    body = _search(client, "lat=50.80&lng=-1.10").get_json()
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
    assert _names(_search(client, "lat=50.80&lng=-1.10&radius_km=5")) == ["Harbour City FC"]
    assert _names(_search(client, "lat=50.80&lng=-1.10&radius_km=20")) == [
        "Harbour City FC",
        "Millbrook Athletic",
    ]
    assert _names(_search(client, "lat=50.80&lng=-1.10&radius_km=100&programme=boys")) == ["Northgate Rovers"]
    assert _names(_search(client, "lat=-33.9&lng=151.2&radius_km=250")) == []


@pytest.mark.parametrize(
    ("origin", "target"),
    [
        ((50.80, -1.10), (51.40, -1.10)),
        ((50.80, -1.10), (50.80, 1.90)),
        ((60.0, 10.0), (61.5, 12.5)),
        ((-33.9, 151.2), (-35.2, 149.1)),
        ((35.0, 179.5), (35.5, -179.4)),
        ((1.0, 103.8), (-0.5, 102.9)),
        ((85.0, 0.0), (85.0, 25.0)),
        ((89.5, 10.0), (89.5, -170.0)),
        ((-89.0, 40.0), (-89.5, -100.0)),
    ],
)
def test_sql_radius_agrees_with_great_circle_distance(client, on, origin, target):
    """Radius membership is the great-circle distance itself: 10 m either side of it flips the answer."""
    _club(_league(), "Probe Town", directory=_pin(*target))
    true_km = club_directory.haversine_km(*origin, *target)
    assert true_km < club_directory.MAX_RADIUS_KM
    inside = _search(client, lat=origin[0], lng=origin[1], radius_km=round(true_km + 0.01, 3))
    outside = _search(client, lat=origin[0], lng=origin[1], radius_km=round(true_km - 0.01, 3))
    assert _names(inside) == ["Probe Town"]
    assert _names(outside) == []
    assert inside.get_json()["clubs"][0]["distance_km"] == pytest.approx(true_km, abs=0.06)


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
        "lat=91&lng=1",
        "lat=-90.5&lng=1",
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
    response = _search(client, query)
    assert response.status_code == 400, query
    assert set(response.get_json()) == {"error"}
    if not any(name in query for name in ("q=", "lat=", "lng=", "radius_km=")):
        assert client.get(f"/api/programs?{query}").status_code == 400, query


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


def test_directory_rate_limit_is_one_budget_across_both_routes(monkeypatch):
    monkeypatch.setenv(FLAG, "true")
    probe = Flask("club-directory-rate-limit")
    probe.config.update(TESTING=True, RATELIMIT_ENABLED=True, RATELIMIT_STORAGE_URI="memory://")
    was_enabled = limiter.enabled
    limiter.enabled = True
    try:
        limiter.init_app(probe)
        probe.register_blueprint(club_directory_bp, url_prefix="/api")
        monkeypatch.setattr(club_directory, "search", lambda params: {"clubs": []})
        with probe.app_context():
            limiter.reset()
        caller = {"REMOTE_ADDR": "192.0.2.42"}
        http = probe.test_client()
        codes = [
            (
                http.get("/api/programs", environ_base=caller)
                if index % 2
                else http.post(SEARCH_URL, json={"lat": 1, "lng": 1}, environ_base=caller)
            ).status_code
            for index in range(61)
        ]
        assert codes[:60] == [200] * 60
        assert codes[60] == 429
        assert http.get("/api/programs", environ_base={"REMOTE_ADDR": "192.0.2.43"}).status_code == 200
    finally:
        with probe.app_context():
            limiter.reset()
        limiter.enabled = was_enabled


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


# ---------------------------------------------------------------------------
# RB1 regressions (adversarial review of PR #1114) + fix round 1 decisions
# ---------------------------------------------------------------------------


def test_position_and_search_words_are_refused_in_a_url_and_taken_in_the_body(client, on):
    _seed_region()
    for query in ("q=harbour", "lat=50.8&lng=-1.1", "lat=50.8&lng=-1.1&radius_km=10", "radius_km=10", "lng=1"):
        refused = client.get(f"/api/programs?{query}")
        assert refused.status_code == 400, query
        assert "POST /api/club-directory/search" in refused.get_json()["error"]
        assert "Harbour" not in refused.get_data(as_text=True)

    # Native JSON numbers and lists, as the web app sends them.
    body = client.post(
        SEARCH_URL,
        json={"q": "oo", "lat": 50.8, "lng": -1.1, "radius_km": 20, "programme": ["women", "girls"], "per_page": 5},
    )
    assert body.status_code == 200
    assert body.headers["Cache-Control"] == "no-store"
    payload = body.get_json()
    assert [club["name"] for club in payload["clubs"]] == ["Millbrook Athletic"]
    # Nothing about the visitor is echoed back.
    assert set(payload) == {"clubs", "page", "per_page", "total", "has_more", "filters"}
    assert _names(client.post(SEARCH_URL, json={})) == _names(client.get("/api/programs"))


@pytest.mark.parametrize(
    "body",
    [
        ["lat", 1],
        "lat=1",
        {"lat": True, "lng": 1},
        {"lat": {"value": 1}, "lng": 1},
        {"lat": 10**400, "lng": 1},
        {"q": ["harbour"]},
        {"level": [1]},
        {"page": 10**12},
    ],
)
def test_malformed_search_bodies_are_a_400(client, on, body):
    response = client.post(SEARCH_URL, json=body)
    assert response.status_code == 400, body
    assert set(response.get_json()) == {"error"}


def test_search_body_is_bounded(client, on):
    assert client.post(SEARCH_URL, json={"q": "x" * 5000}).status_code == 413
    assert client.post(SEARCH_URL, data="{", content_type="application/json").status_code == 400
    refused = client.get(SEARCH_URL)
    assert refused.status_code == 405 and _allow(refused) == ["OPTIONS", "POST"]
    assert _allow(client.options(SEARCH_URL)) == ["OPTIONS", "POST"]


class _CountingInput:
    """Counts what the app actually pulls off the request stream."""

    def __init__(self, stream):
        self.stream = stream
        self.taken = 0

    def read(self, size=-1):
        data = self.stream.read(size) if size is not None and size >= 0 else self.stream.read()
        self.taken += len(data)
        return data

    def readline(self, size=-1):
        data = self.stream.readline(size) if size is not None and size >= 0 else self.stream.readline()
        self.taken += len(data)
        return data


def _over_the_wire(app, body=b"", *, chunks=None, length=True, path=SEARCH_URL, method="POST"):
    """RB1V-N1: raw HTTP bytes through gunicorn's own request parser into the WSGI app, as in production."""
    pytest.importorskip("gunicorn")
    from gunicorn.config import Config as GunicornConfig
    from gunicorn.http.message import Request
    from gunicorn.http.unreader import IterUnreader
    from gunicorn.http.wsgi import create

    head = f"{method} {path} HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\n".encode()
    if chunks is not None:
        framed = b"".join(format(len(chunk), "x").encode() + b"\r\n" + chunk + b"\r\n" for chunk in chunks)
        wire = head + b"Transfer-Encoding: chunked\r\n\r\n" + framed + b"0\r\n\r\n"
    elif length:
        wire = head + f"Content-Length: {len(body)}\r\n\r\n".encode() + body
    else:
        wire = head + b"\r\n" + body
    config = GunicornConfig()
    peer = ("127.0.0.1", 12345)
    _response, environ = create(
        Request(config, IterUnreader([wire]), peer), SimpleNamespace(), peer, ("127.0.0.1", 5001), config
    )
    counted = environ["wsgi.input"] = _CountingInput(environ["wsgi.input"])
    seen = {}

    def start_response(status, headers, exc_info=None):
        seen.update(status=int(status.split()[0]), headers=headers)

    payload = b"".join(app.wsgi_app(environ, start_response))
    return SimpleNamespace(
        status=seen["status"],
        # Allow is a set: its order is not part of the answer.
        headers=sorted(
            (name, ", ".join(sorted(part.strip() for part in value.split(","))) if name == "Allow" else value)
            for name, value in seen["headers"]
        ),
        data=payload,
        taken=counted.taken,
        environ=environ,
    )


def _search_bytes(size):
    """A valid search body of exactly ``size`` bytes (JSON allows trailing whitespace)."""
    return json.dumps({"q": "harbour"}).encode().ljust(size)


def test_search_body_limit_is_exact_for_an_ordinary_request(app, on):
    _seed_region()
    ordinary = _over_the_wire(app, json.dumps({"q": "harbour", "lat": 50.79, "lng": -1.06}).encode())
    assert ordinary.status == 200 and json.loads(ordinary.data)["total"] == 1
    at_limit = _over_the_wire(app, _search_bytes(2048))
    assert at_limit.status == 200 and json.loads(at_limit.data)["total"] == 1
    over = _over_the_wire(app, _search_bytes(2049))
    assert over.status == 413 and json.loads(over.data) == {"error": "the search is too large"}


def test_an_oversized_search_is_refused_without_being_read(app, on):
    """RB1V-N1: the reviewer's 1 MB body. It is a 413 and the worker never buffers it."""
    body = json.dumps({"q": "Ground", "padding": "x" * 1048576}).encode()
    declared = _over_the_wire(app, body)
    assert declared.status == 413 and declared.taken == 0
    chunked = _over_the_wire(app, chunks=[body])
    assert chunked.environ.get("CONTENT_LENGTH") is None and chunked.environ["wsgi.input_terminated"] is True
    assert chunked.status == 413 and json.loads(chunked.data) == {"error": "the search is too large"}
    assert chunked.taken <= 2049
    # Many small chunks add up just the same.
    dripped = _over_the_wire(app, chunks=[b" " * 512] * 8 + [b"{}"])
    assert dripped.status == 413 and dripped.taken <= 2049


def test_a_chunked_search_within_the_limit_still_works(app, on):
    _seed_region()
    found = _over_the_wire(app, chunks=[b'{"q": "har', b'bour", "lat": 50.79, "lng": -1.06}'])
    assert found.status == 200 and json.loads(found.data)["total"] == 1
    at_limit = _over_the_wire(app, chunks=[_search_bytes(2048)])
    assert at_limit.status == 200 and json.loads(at_limit.data)["total"] == 1
    assert _over_the_wire(app, chunks=[_search_bytes(2049)]).status == 413


def test_a_search_with_no_content_length_reads_no_body(app, on):
    """Neither a length nor chunked framing: the server hands over an empty body, so it is a plain 400."""
    body = json.dumps({"q": "Ground", "padding": "x" * 1048576}).encode()
    unframed = _over_the_wire(app, body, length=False)
    assert unframed.environ.get("CONTENT_LENGTH") is None
    assert unframed.status == 400 and unframed.taken == 0
    assert json.loads(unframed.data) == {"error": "the search must be a JSON object"}


def test_search_body_limit_holds_without_gunicorn(client, on):
    """The same limit through werkzeug alone: a terminated stream with no declared length."""
    import io

    def post(body):
        return client.post(
            SEARCH_URL,
            content_type="application/json",
            environ_overrides={
                "CONTENT_LENGTH": "",
                "wsgi.input": io.BytesIO(body),
                "wsgi.input_terminated": True,
                "HTTP_TRANSFER_ENCODING": "chunked",
            },
        )

    assert post(json.dumps({"q": "Ground", "padding": "x" * 1048576}).encode()).status_code == 413
    assert post(_search_bytes(2049)).status_code == 413
    assert post(_search_bytes(2048)).status_code == 200
    assert post(b"{").status_code == 400
    assert client.post(SEARCH_URL, data=b"\xff\xfe{", content_type="application/json").status_code == 400
    assert client.post(SEARCH_URL, data="[" * 2000, content_type="application/json").status_code == 400
    assert client.post(SEARCH_URL, data='{"q": "harbour"}', content_type="text/plain").status_code == 400


@pytest.mark.parametrize("with_catch_all", [False, True])
def test_flag_off_an_oversized_search_is_still_answered_as_an_unrouted_path(app, with_catch_all):
    """Flag off the body is never looked at: any size, any framing, same answer as a path with no route."""
    if with_catch_all:

        @app.route("/", defaults={"path": ""})
        @app.route("/<path:path>")
        def serve(path):
            return "spa shell", 200

    body = json.dumps({"q": "Ground", "padding": "x" * 1048576}).encode()
    for framing in ({"body": body}, {"chunks": [body]}, {"body": body, "length": False}):
        routed = _over_the_wire(app, **framing)
        unrouted = _over_the_wire(app, path="/api/club-directory/never-existed", **framing)
        assert (routed.status, routed.headers, routed.data) == (unrouted.status, unrouted.headers, unrouted.data)
        assert routed.status == (405 if with_catch_all else 404)
        assert routed.taken == 0


def test_a_visitor_search_never_reaches_the_access_log(app, client, on):
    """RB1-1: replay the real request through the deployed Gunicorn access-log format."""
    glogging = pytest.importorskip("gunicorn.glogging")
    from gunicorn.config import Config as GunicornConfig

    _seed_region()
    seen = []
    inner = app.wsgi_app

    def recording(environ, start_response):
        seen.append(environ)
        return inner(environ, start_response)

    app.wsgi_app = recording
    try:
        found = client.post(SEARCH_URL, json={"q": "HC1 2AB", "lat": 50.79, "lng": -1.06, "radius_km": 40})
    finally:
        app.wsgi_app = inner
    assert found.status_code == 200 and found.get_json()["total"] == 1

    environ = dict(seen[-1])
    # Replay original URI/body evidence against the deployed query-free access format.
    environ["RAW_URI"] = environ["PATH_INFO"] + (f"?{environ['QUERY_STRING']}" if environ["QUERY_STRING"] else "")
    config = GunicornConfig()
    config.set("accesslog", "-")
    dockerfile = Path(__file__).resolve().parent.parent.joinpath("Dockerfile").read_text()
    command = json.loads(next(line[4:] for line in dockerfile.splitlines() if line.startswith("CMD ")))
    assert command[command.index("--access-logfile") + 1] == "-"
    config.set("access_log_format", command[command.index("--access-logformat") + 1])
    atoms = glogging.Logger(config).atoms(
        SimpleNamespace(status="200 OK", sent=len(found.data), headers=list(found.headers)), [], environ, timedelta()
    )
    line = config.access_log_format % atoms
    assert f"POST {SEARCH_URL} HTTP/1.1 200" in line
    for private in ("50.79", "-1.06", "lat", "lng", "radius", "HC1", "2AB"):
        assert private not in line, line


def test_directory_search_terms_are_never_stored_in_product_analytics(app, client):
    """RB1-2: the server drops them even from a client that still sends them."""
    from src.models.product_event import ProductEvent
    from src.routes.events import events_bp

    app.register_blueprint(events_bp, url_prefix="/api")
    sent = client.post(
        "/api/events",
        json={
            "events": [
                {"name": "pageview", "path": "/clubs?q=AB12+3CD", "session_id": "synthetic-session"},
                {
                    "name": "pageview",
                    "path": "/clubs?for=youth&q=AB12%203CD&lat=50.79&lng=-1.06&radius_km=40&level=amateur&postcode=AB12",
                    "referrer": "https://app.example/clubs/?q=AB12+3CD&level=amateur#q=AB12",
                    "session_id": "synthetic-session",
                },
                {"name": "pageview", "path": "/search?q=midfielder", "referrer": "https://app.example/x?q=1"},
            ]
        },
    )
    assert sent.status_code == 202 and sent.get_json()["accepted"] == 3
    rows = ProductEvent.query.order_by(ProductEvent.id).all()
    assert [row.path for row in rows] == ["/clubs", "/clubs?for=youth&level=amateur", "/search?q=midfielder"]
    assert rows[1].referrer == "https://app.example/clubs/?level=amateur"
    assert rows[2].referrer == "https://app.example/x?q=1"
    stored = json.dumps([[row.path, row.referrer, row.props] for row in rows])
    for private in ("AB12", "3CD", "50.79", "1.06", "radius"):
        assert private not in stored


def test_an_approval_while_the_flag_is_off_never_publishes_unseen_location_edits(client, on, monkeypatch):
    """RB1-4: on -> club edits -> off -> admin approves what they can see -> on."""
    program = _club(_league(), "Harbour City FC", directory={"venue_name": "Old Approved Ground", **_pin(51.0, -1.0)})
    saved = client.put(
        f"/api/club/{program.id}/profile",
        json=_profile_body(
            summary="A new summary the reviewer can read.",
            directory={"venue_name": "Never Shown To Reviewer", "latitude": 52.5, "longitude": 1.25},
        ),
        headers=_headers(_manager_email(program)),
    )
    revision_id = saved.get_json()["pending"]["id"]

    monkeypatch.setenv(FLAG, "false")
    listed = client.get("/api/admin/funding/profile-revisions", headers=_admin_headers()).get_json()["revisions"]
    assert len(listed) == 1 and "directory" not in listed[0]
    approved = client.post(
        f"/api/admin/funding/programs/{program.id}/profile-revisions/{revision_id}/review",
        json={"decision": "approve", "reason": "Reviewed the displayed profile."},
        headers=_admin_headers(),
    )
    assert approved.status_code == 200 and "directory" not in approved.get_json()["revision"]

    monkeypatch.setenv(FLAG, "true")
    card = client.get("/api/programs").get_json()["clubs"][0]
    assert card["venue"] == {"name": "Old Approved Ground", "postcode": None, "latitude": 51.0, "longitude": -1.0}
    page = client.get(f"/api/programs/{program.slug}").get_json()["program"]
    assert page["directory"]["venue"]["name"] == "Old Approved Ground"
    # The visible part of the revision was approved as usual.
    assert page["program_provided"]["summary"] == "A new summary the reviewer can read."
    assert "Never Shown" not in json.dumps(
        client.get(f"/api/club/{program.id}/profile", headers=_headers(_manager_email(program))).get_json()
    )


def test_a_flag_off_approval_publishes_no_location_when_none_was_approved_before(client, on, monkeypatch):
    program = _club(_league(), "Harbour City FC")
    saved = client.put(
        f"/api/club/{program.id}/profile",
        json=_profile_body(directory={**DIRECTORY_INPUT, "venue_name": "Never Shown To Reviewer"}),
        headers=_headers(_manager_email(program)),
    )
    monkeypatch.setenv(FLAG, "false")
    review = client.post(
        f"/api/admin/funding/programs/{program.id}/profile-revisions/{saved.get_json()['pending']['id']}/review",
        json={"decision": "approve", "reason": "Reviewed the displayed profile."},
        headers=_admin_headers(),
    )
    assert review.status_code == 200
    monkeypatch.setenv(FLAG, "true")
    card = client.get("/api/programs").get_json()["clubs"][0]
    assert (card["venue"], card["club_level"], card["gender_programs"]) == (None, None, [])


def test_club_text_decoding_cost_is_bounded(client, on):
    """RB1-5: 400 kB of nested entities used to take 11 s and be accepted; now it is refused at once."""
    program = _club(_league(), "Harbour City FC")
    headers = _headers(_manager_email(program))

    def put(venue_name):
        return client.put(
            f"/api/club/{program.id}/profile", json=_profile_body(directory={"venue_name": venue_name}), headers=headers
        )

    started = time.perf_counter()
    oversized = put("&" + "amp;" * 100000 + "lt;")
    elapsed = time.perf_counter() - started
    assert oversized.status_code == 400 and "venue_name" in oversized.get_json()["fields"]
    assert elapsed < 1.0, elapsed

    # Short enough to pass the size bound, but nested deeper than is ever decoded.
    nested = put("&" + "amp;" * 40 + "lt;b")
    assert nested.status_code == 400 and "plain text" in nested.get_json()["fields"]["venue_name"]
    assert ClubProgramProfileRevision.query.filter_by(program_id=program.id, status="pending").count() == 0

    started = time.perf_counter()
    for _ in range(50):
        with pytest.raises(ValueError):
            club_directory._clean_text("&" + "amp;" * 119 + "lt;", "venue_name", club_directory.VENUE_NAME_MAX)
    assert time.perf_counter() - started < 1.0

    ordinary = put("Smith &amp; Sons Park")
    assert ordinary.status_code == 200
    assert ordinary.get_json()["pending"]["directory"]["venue_name"] == "Smith & Sons Park"


def test_radius_membership_is_great_circle_at_high_latitude(client, on):
    """RB1-6: visitor (85, 0), club (85, 25) is 240.4 km away; a 241 km radius used to return nothing."""
    _club(_league(), "Arctic Town", directory=_pin(85, 25))
    true_km = club_directory.haversine_km(85, 0, 85, 25)
    assert 240 < true_km < 241
    inside = _search(client, lat=85, lng=0, radius_km=241).get_json()
    assert (inside["total"], inside["clubs"][0]["distance_km"]) == (1, round(true_km, 1))
    assert _search(client, lat=85, lng=0, radius_km=240).get_json()["total"] == 0
    assert _search(client, lat=90, lng=0, radius_km=250).status_code == 200


def test_nearest_first_is_great_circle_over_any_distance(client, on):
    """RB1-6: over the pole (85, 180) is nearer than (74, 0); the flat projection listed it second."""
    league = _league()
    _club(league, "Across The Pole", directory=_pin(85, 180))
    _club(league, "Down The Meridian", directory=_pin(74, 0))
    _club(league, "Far Side", directory=_pin(-40, 175))
    _club(league, "No Pin Town")
    clubs = _search(client, lat=85, lng=0).get_json()["clubs"]
    assert [club["name"] for club in clubs] == ["Across The Pole", "Down The Meridian", "Far Side", "No Pin Town"]
    distances = [club["distance_km"] for club in clubs[:3]]
    assert distances == sorted(distances)
    assert distances[:2] == [1112.0, 1223.1]
    assert clubs[3]["distance_km"] is None


def test_nearest_first_pages_are_stable_and_complete(client, on):
    league = _league()
    pins = [(50.80, -1.10), (50.80, -1.10), (50.80, -1.10), (50.9, -1.0), (35.0, 179.9), (35.0, -179.9), (-60, 20)]
    for index, pin in enumerate(pins):
        _club(league, f"Pinned {index}", directory=_pin(*pin))
    _club(league, "Unpinned B")
    _club(league, "Unpinned A")
    origin = {"lat": 50.80, "lng": -1.10}
    everything = _search(client, per_page=50, **origin).get_json()
    assert everything["total"] == 9
    expected = [club["id"] for club in everything["clubs"]]
    measured = [club["distance_km"] for club in everything["clubs"][:7]]
    assert measured == sorted(measured)
    assert [club["name"] for club in everything["clubs"][:3]] == ["Pinned 0", "Pinned 1", "Pinned 2"]
    assert [club["name"] for club in everything["clubs"][7:]] == ["Unpinned A", "Unpinned B"]

    paged = []
    for page in range(1, 6):
        body = _search(client, per_page=2, page=page, **origin).get_json()
        assert body["total"] == 9 and body["has_more"] is (page < 5)
        paged.extend(club["id"] for club in body["clubs"])
    assert paged == expected
    assert len(set(paged)) == 9
    # The same request twice gives the same page.
    assert (
        _search(client, per_page=2, page=2, **origin).get_json()
        == _search(client, per_page=2, page=2, **origin).get_json()
    )


def test_the_sql_distance_term_is_the_haversine_term(client, on):
    """The value ordered and bounded in SQL equals hav(d/R) of the distance shown to people."""
    program = _club(_league(), "Probe Town", directory=_pin(-33.86, 151.21))
    revision = db.session.get(ClubProgramProfileRevision, program.approved_profile_revision_id)
    club_directory._sqlite_trig()
    for origin in ((51.5, -0.12), (-33.9, 151.2), (89.9, -30.0), (-89.9, 0.0), (0.0, -28.79)):
        term = db.session.query(club_directory._haversine_term(ClubProgramProfileRevision, *origin)).filter(
            ClubProgramProfileRevision.id == revision.id
        )
        shown = club_directory.haversine_km(*origin, -33.86, 151.21)
        assert term.scalar() == pytest.approx(math.sin(shown / (2 * club_directory.EARTH_RADIUS_KM)) ** 2, rel=1e-9)


@pytest.mark.parametrize("pin", [{"latitude": 85.0}, {"longitude": 25.0}])
def test_the_database_refuses_a_half_populated_pin(app, pin):
    """RB1-7: a CHECK accepts UNKNOWN, so the populated branch must say NOT NULL on both sides."""
    from sqlalchemy.exc import IntegrityError

    program = _club(_league(), "Harbour City FC", directory=_pin(50.8, -1.1))
    revision = db.session.get(ClubProgramProfileRevision, program.approved_profile_revision_id)
    revision.latitude = pin.get("latitude")
    revision.longitude = pin.get("longitude")
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()
    revision.latitude = revision.longitude = None
    db.session.commit()
    revision.latitude, revision.longitude = 91.0, 0.0
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_the_migration_and_model_agree_on_the_both_or_neither_pin_check():
    backend = Path(__file__).resolve().parent.parent
    migration = backend.joinpath("migrations", "versions", "p2b1_club_directory.py").read_text()
    model = backend.joinpath("src", "models", "funding.py").read_text()
    for source in (migration, model):
        assert "latitude IS NOT NULL AND longitude IS NOT NULL AND" in source
    # An earlier draft of the constraint is replaced, not left in place.
    assert "REPLACED_CHECKS" in migration and "drop_constraint" in migration


@pytest.mark.parametrize(
    ("directory", "field"),
    [
        ({"latitude": 10**400, "longitude": 1}, "latitude"),
        ({"latitude": 1, "longitude": -(10**400)}, "longitude"),
        ({"latitude": 10**20, "longitude": 10**20}, "latitude"),
    ],
)
def test_a_huge_json_integer_is_a_validation_error_not_a_500(client, on, directory, field):
    """RB1-8: it used to raise OverflowError out of the route."""
    program = _club(_league(), "Harbour City FC")
    response = client.put(
        f"/api/club/{program.id}/profile",
        json=_profile_body(directory=directory),
        headers=_headers(_manager_email(program)),
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "validation_failed"
    assert field in response.get_json()["fields"]


def test_exact_place_filters_match_non_ascii_names(client, on):
    """RB1-9: the stored and the requested name are folded by the same engine (Python folds İ differently)."""
    league = _league()
    _club(league, "Bosphorus FC", city="İstanbul", region="Marmara", country="Türkiye")
    _club(league, "Harbour City FC")
    assert _names(client.get("/api/programs", query_string={"city": "İstanbul"})) == ["Bosphorus FC"]
    assert _names(client.get("/api/programs", query_string={"country": "Türkiye"})) == ["Bosphorus FC"]
    assert _names(client.post(SEARCH_URL, json={"city": "İstanbul", "region": "MARMARA"})) == ["Bosphorus FC"]
    assert _names(client.get("/api/programs", query_string={"city": "Istanbul"})) == []


@pytest.mark.parametrize("role", ["coach", "analyst", "viewer"])
def test_all_squads_scoped_staff_cannot_read_or_edit_the_club_profile(client, on, monkeypatch, role):
    """A2 (RA2V5): "all squads" widens a scoped role's squad list, never its capabilities."""
    from src.models.club_access import ClubAccessGrant

    monkeypatch.setenv("CLUB_STAFF_ACCESS_ENABLED", "true")
    program = _club(_league(), "Harbour City FC", directory={"venue_name": "Quayside Park", **_pin(50.8, -1.1)})
    user = UserAccount(email=f"{role}@staff.example", display_name=role, display_name_lower=f"{role} staff")
    db.session.add(user)
    db.session.flush()
    db.session.add(
        ClubAccessGrant(program_id=program.id, user_account_id=user.id, role=role, all_squads=True, status="active")
    )
    db.session.commit()
    headers = _headers(user.email)
    edit = client.put(
        f"/api/club/{program.id}/profile",
        json=_profile_body(directory={"venue_name": "Injected Ground", "latitude": 1.5, "longitude": 1.5}),
        headers=headers,
    )
    assert edit.status_code == 403
    assert client.get(f"/api/club/{program.id}/profile", headers=headers).status_code == 403
    assert ClubProgramProfileRevision.query.filter_by(program_id=program.id, status="pending").count() == 0
    assert client.get("/api/programs").get_json()["clubs"][0]["venue"]["name"] == "Quayside Park"


def test_an_invited_manager_edits_the_location_but_only_into_review(client, on, monkeypatch):
    from src.models.club_access import ClubAccessGrant

    monkeypatch.setenv("CLUB_STAFF_ACCESS_ENABLED", "true")
    program = _club(_league(), "Harbour City FC", directory={"venue_name": "Quayside Park"})
    user = UserAccount(email="invited@staff.example", display_name="Invited", display_name_lower="invited staff")
    db.session.add(user)
    db.session.flush()
    db.session.add(
        ClubAccessGrant(
            program_id=program.id, user_account_id=user.id, role="manager", all_squads=True, status="active"
        )
    )
    db.session.commit()
    saved = client.put(
        f"/api/club/{program.id}/profile",
        json=_profile_body(directory={"venue_name": "New Ground"}),
        headers=_headers(user.email),
    )
    assert saved.status_code == 200
    assert saved.get_json()["pending"]["directory"]["venue_name"] == "New Ground"
    assert client.get("/api/programs").get_json()["clubs"][0]["venue"]["name"] == "Quayside Park"


def test_a_club_onboarded_through_the_real_claim_bridge_is_listed(bridge_app, monkeypatch):
    """The orchestrator's case end to end: official claim -> admin approves -> console club -> in the directory."""
    monkeypatch.setenv(FLAG, "true")
    bridge_app.register_blueprint(club_directory_bp, url_prefix="/api")
    http = bridge_app.test_client()
    official_claim = console_bridge._submit_claim(
        http, console_bridge.LOCAL_EMAIL, {"local_club_id": bridge_app.bridge["local_club_id"]}
    )
    assert http.get("/api/programs").get_json()["total"] == 0

    console_bridge._review(http, official_claim.id, "approve")
    program = ClubProgram.query.one()
    assert program.league.name == CONSOLE_LEAGUE_NAME and program.league.registry_status != "approved"
    listing = http.get("/api/programs").get_json()
    assert [(club["name"], club["league"], club["city"]) for club in listing["clubs"]] == [
        ("Harbour Juniors", None, "Kobe")
    ]
    page = http.get(f"/api/programs/{program.slug}")
    assert page.status_code == 200 and page.get_json()["program"]["league"] is None
    assert CONSOLE_LEAGUE_NAME not in page.get_data(as_text=True) + json.dumps(listing)

    console_bridge._review(http, official_claim.id, "revoke")
    assert http.get("/api/programs").get_json()["total"] == 0
    assert http.get(f"/api/programs/{program.slug}").status_code == 404
