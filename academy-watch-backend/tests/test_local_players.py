"""Tests for moderated local players and their unified signed identities.

Approved adults gain a DB-only negative player id while remaining isolated
from API-Football. These tests cover claimant visibility, owner curation,
moderation, signed showcase reads, local merges, and graduation to a real API
identity without weakening moderation or losing linked records.
"""

import re
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from flask import Flask
from PIL import Image
from src.auth import _ensure_user_account, issue_user_token
from src.extensions import limiter
from src.models.contact import ContactRequest
from src.models.follow import Follow, FollowList, FollowPlayerSnapshot, PlayerShadow, PlayerShadowStats
from src.models.funding import ClubRosterMember
from src.models.league import (
    CommunityTake,
    NewsletterCommentary,
    NewsletterPlayerYoutubeLink,
    Player,
    PlayerComment,
    PlayerFlag,
    PlayerLink,
    QuickTakeSubmission,
    Team,
    db,
)
from src.models.player_suppression import PlayerSuppression
from src.models.pulse import PlayerCardCache, PlayerPulse
from src.models.scout_watchlist import ScoutWatchlistEntry
from src.models.season_rollup import PlayerSeasonCell, PlayerSeasonTotal
from src.models.showcase import (
    LocalClub,
    LocalPlayer,
    PlayerClubAffiliation,
    PlayerProfileClaim,
    PlayerShowcaseMedia,
    PlayerShowcaseProfile,
    without_minor_local_bridge,
)
from src.models.tracked_player import TrackedPlayer
from src.models.video import VideoPlayerReport, VideoRosterEntry
from src.services import social_proof

ADMIN_KEY = "test-admin-key"
CODE_PATTERN = re.compile(r"^AW-[ABCDEFGHJKLMNPQRSTUVWXYZ23456789]{8}$")
DEFAULT_ADULT_BIRTH_YEAR = datetime.now(UTC).year - 19
LP01_MIGRATION = Path(__file__).resolve().parents[1] / "migrations/versions/lp01_local_player_birth_date.py"


def _birth_date_years_ago(years):
    today = datetime.now(UTC).date()
    try:
        return today.replace(year=today.year - years)
    except ValueError:
        return today.replace(year=today.year - years, day=28)


@pytest.fixture
def app(monkeypatch, tmp_path):
    monkeypatch.setenv("SKIP_API_HANDSHAKE", "1")
    monkeypatch.setenv("API_USE_STUB_DATA", "true")
    monkeypatch.setenv("ADMIN_API_KEY", ADMIN_KEY)
    monkeypatch.setenv("ADMIN_IP_WHITELIST", "")
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("FLASK_ENV", "development")
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("SHOWCASE_MEDIA_LOCAL_DIR", str(tmp_path / "showcase-media"))
    monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)

    from src.routes.showcase import showcase_bp

    flask_app = Flask(__name__)
    flask_app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret-key",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        RATELIMIT_ENABLED=False,
    )

    db.init_app(flask_app)
    limiter.init_app(flask_app)
    flask_app.register_blueprint(showcase_bp, url_prefix="/api")

    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


class FakeResponse:
    """Small streaming response used at the social-proof HTTP boundary."""

    def __init__(self, body=b"", *, status_code=200, headers=None, encoding="utf-8"):
        self._body = body
        self.status_code = status_code
        self.headers = headers or {}
        self.encoding = encoding
        self.raw = BytesIO(body)
        self.closed = False

    @property
    def content(self):
        return self._body

    @property
    def text(self):
        return self._body.decode(self.encoding or "utf-8", errors="replace")

    def iter_content(self, chunk_size=1, decode_unicode=False):
        del decode_unicode
        for start in range(0, len(self._body), chunk_size):
            yield self._body[start : start + chunk_size]

    def close(self):
        self.closed = True


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _user_headers(email):
    _ensure_user_account(email)
    db.session.commit()
    token = issue_user_token(email)["token"]
    return {"Authorization": f"Bearer {token}"}


def _admin_headers():
    token = issue_user_token("admin@test.com", role="admin")["token"]
    return {"Authorization": f"Bearer {token}", "X-API-Key": ADMIN_KEY}


def _make_user(email):
    user = _ensure_user_account(email)
    db.session.commit()
    return user


def _seed_local_player(
    display_name="Northside Prospect",
    *,
    birth_date=None,
    birth_year=DEFAULT_ADULT_BIRTH_YEAR,
    position="Midfielder",
    country="England",
    city="Leeds",
    club_name="Northside Juniors",
    status="pending",
    api_player_id=None,
    merged_into_local_player_id=None,
    created_by_user_id=None,
):
    player = LocalPlayer(
        display_name=display_name,
        normalized_name=LocalPlayer.normalize_name(display_name),
        birth_date=birth_date,
        birth_year=birth_year,
        position=position,
        country=country,
        city=city,
        club_name=club_name,
        status=status,
        api_player_id=api_player_id,
        merged_into_local_player_id=merged_into_local_player_id,
        provenance="user",
        created_by_user_id=created_by_user_id,
    )
    db.session.add(player)
    db.session.flush()
    return player


def _seed_claim(
    email="owner@example.com",
    *,
    player_api_id=None,
    local_player_id=None,
    status="approved",
    relationship_type="player",
    code="AW-ABCDEFGH",
):
    user = _make_user(email)
    claim = PlayerProfileClaim(
        player_api_id=player_api_id,
        local_player_id=local_player_id,
        user_account_id=user.id,
        relationship_type=relationship_type,
        status=status,
        verification_code=code,
        verification_status="unverified",
    )
    db.session.add(claim)
    db.session.commit()
    return user, claim


def _seed_local_club(name="Northside Juniors", *, status="verified"):
    club = LocalClub(
        name=name,
        normalized_name=LocalClub.normalize_name(name),
        country="England",
        city="Leeds",
        level="youth",
        status=status,
        provenance="user",
    )
    db.session.add(club)
    db.session.flush()
    return club


def _seed_media(
    *,
    player_api_id=None,
    local_player_id=None,
    user_id=None,
    status="approved",
    sort_order=0,
    suffix="photo",
):
    subject_path = f"local-players/{local_player_id}" if local_player_id is not None else f"players/{player_api_id}"
    media = PlayerShowcaseMedia(
        player_api_id=player_api_id,
        local_player_id=local_player_id,
        kind="photo",
        blob_path=f"{subject_path}/{suffix}.jpg",
        public_url=f"/api/dev/showcase-media/published/{subject_path}/{suffix}.jpg",
        content_type="image/jpeg",
        size_bytes=1024,
        status=status,
        sort_order=sort_order,
        uploaded_by_user_id=user_id,
    )
    db.session.add(media)
    db.session.flush()
    return media


def _create_local_player(client, email="creator@example.com", **overrides):
    payload = {
        "display_name": "Northside Prospect",
        "birth_year": DEFAULT_ADULT_BIRTH_YEAR,
        "position": "Midfielder",
        "country": "England",
        "city": "Leeds",
        "club_name": "Northside Juniors",
    }
    payload.update(overrides)
    response = client.post("/api/local-players", json=payload, headers=_user_headers(email))
    assert response.status_code == 201, response.get_json()
    return response.get_json()


def _jpeg_bytes() -> bytes:
    image = Image.new("RGB", (48, 32), "#4f7d63")
    output = BytesIO()
    image.save(output, "JPEG", quality=90)
    return output.getvalue()


def _url_path(url):
    parsed = urlsplit(url)
    return parsed.path or url


def _create_complete_local_photo(client, lp_id, headers, raw):
    created = client.post(
        f"/api/local-players/{lp_id}/showcase/photos",
        json={"content_type": "image/jpeg", "size_bytes": len(raw)},
        headers=headers,
    )
    assert created.status_code == 201, created.get_json()
    body = created.get_json()
    upload = body["upload"]
    uploaded = client.put(_url_path(upload["url"]), data=raw, headers=upload["headers"])
    assert uploaded.status_code in (200, 201, 204), uploaded.get_json(silent=True)
    media_id = body["media"]["id"]
    completed = client.post(
        f"/api/local-players/{lp_id}/showcase/photos/{media_id}/complete",
        headers=headers,
    )
    assert completed.status_code == 200, completed.get_json()
    assert completed.get_json()["media"]["status"] == "pending"
    return body, completed.get_json()["media"]


def _fake_get(monkeypatch, responses):
    queued = list(responses)

    class FakeCookies:
        def clear(self):
            return None

    class FakeSession:
        def __init__(self):
            self.trust_env = True
            self.cookies = FakeCookies()
            self.headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.close()

        def get(self, _url, **_kwargs):
            if not queued:
                raise AssertionError("unexpected network fetch")
            response = queued.pop(0)
            if isinstance(response, Exception):
                raise response
            return response

        def close(self):
            return None

    monkeypatch.setattr(social_proof.requests, "Session", FakeSession)


def test_lp01_migration_chains_from_bx01_and_guards_birth_date_ddl():
    source = LP01_MIGRATION.read_text()

    assert 'revision = "lp01"' in source
    assert 'down_revision = "bx01"' in source
    assert "if table_exists(TABLE) and not column_exists(TABLE, COLUMN):" in source
    assert "op.add_column(TABLE, sa.Column(COLUMN, sa.Date(), nullable=True))" in source
    assert "if table_exists(TABLE) and column_exists(TABLE, COLUMN):" in source
    assert "op.drop_column(TABLE, COLUMN)" in source


# --------------------------------------------------------------------------- #
# Creation, validation, and duplicates
# --------------------------------------------------------------------------- #


class TestLocalPlayerCreation:
    def test_requires_auth(self, client):
        response = client.post("/api/local-players", json={"display_name": "Northside Prospect"})

        assert response.status_code == 401

    def test_create_sanitizes_normalizes_and_auto_claims(self, app, client):
        response = client.post(
            "/api/local-players",
            json={
                "display_name": " <b>North   Star Prospect</b> ",
                "birth_year": 2005,
                "position": f"<i>{'M' * 60}</i>",
                "country": f"<script>{'E' * 110}</script>",
                "city": f"<b>{'C' * 130}</b>",
                "club_name": f" <em>Northside {'F' * 210}</em> ",
            },
            headers=_user_headers("creator@example.com"),
        )

        assert response.status_code == 201, response.get_json()
        body = response.get_json()
        player = body["player"]
        assert set(player) == {
            "id",
            "display_name",
            "birth_year",
            "position",
            "country",
            "city",
            "club_name",
            "status",
            "api_player_id",
        }
        assert player == {
            "id": player["id"],
            "display_name": "North   Star Prospect",
            "birth_year": 2005,
            "position": "M" * 50,
            "country": "E" * 100,
            "city": "C" * 120,
            "club_name": f"Northside {'F' * 190}",
            "status": "pending",
            "api_player_id": None,
        }
        assert "birth_date" not in player

        claim = body["claim"]
        assert claim["player_api_id"] is None
        assert claim["local_player_id"] == player["id"]
        assert claim["relationship_type"] == "player"
        assert claim["status"] == "pending"
        assert CODE_PATTERN.fullmatch(claim["verification_code"])
        assert claim["verification_status"] == "unverified"

        with app.app_context():
            stored = db.session.get(LocalPlayer, player["id"])
            creator = _make_user("creator@example.com")
            assert stored.normalized_name == "north star prospect"
            assert stored.created_by_user_id == creator.id
            assert stored.provenance == "user"
            assert stored.club_name == f"Northside {'F' * 190}"
            assert stored.birth_date is None
            stored.display_name = "  Renamed\n  Prospect  "
            db.session.flush()
            assert stored.normalized_name == "renamed prospect"

    @pytest.mark.parametrize(
        ("years_ago", "expected_status"),
        [(18, 400), (19, 201)],
        ids=["current-year-minus-18", "current-year-minus-19"],
    )
    def test_self_claim_birth_year_fails_closed_until_age_is_certain(self, app, client, years_ago, expected_status):
        birth_year = datetime.now(UTC).year - years_ago
        response = client.post(
            "/api/local-players",
            json={"display_name": f"Year Evidence Prospect {years_ago}", "birth_year": birth_year},
            headers=_user_headers("creator@example.com"),
        )

        assert response.status_code == expected_status, response.get_json()
        if expected_status == 400:
            assert response.get_json()["error"] == "The platform is 18+ for self-managed profiles"
            with app.app_context():
                assert LocalPlayer.query.count() == 0
                assert PlayerProfileClaim.query.count() == 0
        else:
            assert response.get_json()["player"]["birth_year"] == birth_year

    @pytest.mark.parametrize("years_ago", [18, 19], ids=["exactly-18", "nineteen-years-ago"])
    def test_adult_self_claim_birth_date_is_stored_and_public_after_approval(self, app, client, years_ago):
        birth_date = _birth_date_years_ago(years_ago)
        owner_email = f"adult-{years_ago}@example.com"

        response = client.post(
            "/api/local-players",
            json={"display_name": f"Adult Prospect {years_ago}", "birth_date": birth_date.isoformat()},
            headers=_user_headers(owner_email),
        )

        assert response.status_code == 201, response.get_json()
        player = response.get_json()["player"]
        player_id = player["id"]
        assert player["birth_year"] == birth_date.year
        assert "birth_date" not in player
        with app.app_context():
            assert db.session.get(LocalPlayer, player_id).birth_date == birth_date

        approved = client.post(
            f"/api/admin/local-players/{player_id}/review",
            json={"action": "approve", "note": "Adult identity verified"},
            headers=_admin_headers(),
        )
        assert approved.status_code == 200, approved.get_json()
        assert "birth_date" not in approved.get_json()["player"]

        public = client.get(f"/api/local-players/{player_id}")
        assert public.status_code == 200, public.get_json()
        assert public.get_json()["player"]["birth_year"] == birth_date.year
        assert "birth_date" not in public.get_json()["player"]

        other_user = client.get(
            f"/api/local-players/{player_id}",
            headers=_user_headers("other-user@example.com"),
        )
        assert other_user.status_code == 200, other_user.get_json()
        assert "birth_date" not in other_user.get_json()["player"]

        owner = client.get(f"/api/local-players/{player_id}", headers=_user_headers(owner_email))
        assert owner.status_code == 200, owner.get_json()
        assert "birth_date" not in owner.get_json()["player"]

    def test_valid_birth_date_overrides_malformed_birth_year(self, app, client):
        birth_date = _birth_date_years_ago(19)
        response = client.post(
            "/api/local-players",
            json={
                "display_name": "Authoritative Date Prospect",
                "birth_date": birth_date.isoformat(),
                "birth_year": "not-a-year",
            },
            headers=_user_headers("authoritative-date@example.com"),
        )

        assert response.status_code == 201, response.get_json()
        player = response.get_json()["player"]
        assert player["birth_year"] == birth_date.year
        with app.app_context():
            stored = db.session.get(LocalPlayer, player["id"])
            assert stored.birth_date == birth_date
            assert stored.birth_year == birth_date.year

    def test_self_claim_birth_date_one_day_short_of_18_is_rejected(self, app, client):
        birth_date = _birth_date_years_ago(18) + timedelta(days=1)

        response = client.post(
            "/api/local-players",
            json={"display_name": "Minor Prospect", "birth_date": birth_date.isoformat()},
            headers=_user_headers("creator@example.com"),
        )

        assert response.status_code == 400, response.get_json()
        assert response.get_json()["error"] == "The platform is 18+ for self-managed profiles"
        with app.app_context():
            assert LocalPlayer.query.count() == 0
            assert PlayerProfileClaim.query.count() == 0

    def test_self_claim_without_birth_evidence_is_rejected(self, app, client):
        response = client.post(
            "/api/local-players",
            json={"display_name": "Unknown Age Prospect"},
            headers=_user_headers("creator@example.com"),
        )

        assert response.status_code == 400, response.get_json()
        assert response.get_json()["error"] == "The platform is 18+ for self-managed profiles"
        with app.app_context():
            assert LocalPlayer.query.count() == 0
            assert PlayerProfileClaim.query.count() == 0

    def test_guardian_claim_with_2009_birth_year_remains_claimant_only(self, client):
        response = client.post(
            "/api/local-players",
            json={
                "display_name": "Guardian Managed Prospect",
                "birth_year": 2009,
                "relationship_type": "guardian",
            },
            headers=_user_headers("guardian@example.com"),
        )

        assert response.status_code == 201, response.get_json()
        body = response.get_json()
        assert body["player"]["birth_year"] == 2009
        assert body["claim"]["relationship_type"] == "guardian"
        player_id = body["player"]["id"]

        approved = client.post(
            f"/api/admin/local-players/{player_id}/review",
            json={"action": "approve", "note": "Guardian identity verified"},
            headers=_admin_headers(),
        )
        assert approved.status_code == 200, approved.get_json()
        assert client.get(f"/api/local-players/{player_id}").status_code == 404
        assert (
            client.get(
                f"/api/local-players/{player_id}",
                headers=_user_headers("other-user@example.com"),
            ).status_code
            == 404
        )
        owner = client.get(
            f"/api/local-players/{player_id}",
            headers=_user_headers("guardian@example.com"),
        )
        assert owner.status_code == 200, owner.get_json()

    @pytest.mark.parametrize("relationship_type", ["agent", "guardian"])
    @pytest.mark.parametrize(
        ("days_after_eighteenth_birthday", "retains_birth_date"),
        [(1, False), (0, True)],
        ids=["one-day-short-of-18", "exactly-18"],
    )
    def test_non_player_claim_birth_date_is_minimized_unless_it_proves_adulthood(
        self,
        app,
        client,
        relationship_type,
        days_after_eighteenth_birthday,
        retains_birth_date,
    ):
        birth_date = _birth_date_years_ago(18) + timedelta(days=days_after_eighteenth_birthday)
        response = client.post(
            "/api/local-players",
            json={
                "display_name": f"{relationship_type.title()} Date Prospect {days_after_eighteenth_birthday}",
                "birth_date": birth_date.isoformat(),
                "relationship_type": relationship_type,
            },
            headers=_user_headers(f"{relationship_type}-{days_after_eighteenth_birthday}@example.com"),
        )

        assert response.status_code == 201, response.get_json()
        player = response.get_json()["player"]
        assert player["birth_year"] == birth_date.year
        assert "birth_date" not in player
        with app.app_context():
            expected_birth_date = birth_date if retains_birth_date else None
            assert db.session.get(LocalPlayer, player["id"]).birth_date == expected_birth_date

    @pytest.mark.parametrize("relationship_type", ["agent", "guardian"])
    def test_supported_relationship_types_round_trip(self, client, relationship_type):
        body = _create_local_player(
            client,
            display_name=f"{relationship_type.title()} Prospect",
            relationship_type=relationship_type,
        )

        assert body["claim"]["relationship_type"] == relationship_type

    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {"display_name": "x"},
            {"display_name": "x" * 201},
            {"display_name": 123},
            {"display_name": "Valid Prospect", "relationship_type": "club_official"},
            {"display_name": "Valid Prospect", "relationship_type": 1},
        ],
    )
    def test_name_and_relationship_validation(self, app, client, payload):
        response = client.post("/api/local-players", json=payload, headers=_user_headers("creator@example.com"))

        assert response.status_code == 400, (payload, response.get_json())
        with app.app_context():
            assert LocalPlayer.query.count() == 0
            assert PlayerProfileClaim.query.count() == 0

    @pytest.mark.parametrize("birth_year", [1949, 2021, "2008", 2008.0, True, False])
    def test_birth_year_validation(self, app, client, birth_year):
        response = client.post(
            "/api/local-players",
            json={"display_name": "Valid Prospect", "birth_year": birth_year},
            headers=_user_headers("creator@example.com"),
        )

        assert response.status_code == 400, (birth_year, response.get_json())
        with app.app_context():
            assert LocalPlayer.query.count() == 0

    @pytest.mark.parametrize("birth_year", [None, 1950, 2020])
    def test_birth_year_boundaries(self, client, birth_year):
        response = client.post(
            "/api/local-players",
            json={
                "display_name": f"Boundary Prospect {birth_year}",
                "birth_year": birth_year,
                "relationship_type": "guardian",
            },
            headers=_user_headers("creator@example.com"),
        )

        assert response.status_code == 201, response.get_json()
        assert response.get_json()["player"]["birth_year"] == birth_year

    @pytest.mark.parametrize("existing_status", ["pending", "approved"])
    def test_active_duplicate_echoes_existing(self, app, client, existing_status):
        with app.app_context():
            existing = _seed_local_player(
                "North Star Prospect",
                birth_year=DEFAULT_ADULT_BIRTH_YEAR,
                status=existing_status,
            )
            db.session.commit()
            existing_id = existing.id

        response = client.post(
            "/api/local-players",
            json={"display_name": " NORTH\n star prospect ", "birth_year": DEFAULT_ADULT_BIRTH_YEAR},
            headers=_user_headers("creator@example.com"),
        )

        assert response.status_code == 409, response.get_json()
        body = response.get_json()
        assert body["error"]
        if existing_status == "approved":
            assert body["existing"] == {
                "id": existing_id,
                "display_name": "North Star Prospect",
                "club_name": "Northside Juniors",
                "status": "approved",
            }
            assert not {"city", "birth_year", "position", "country"} & body["existing"].keys()
        else:
            assert "existing" not in body
        with app.app_context():
            assert LocalPlayer.query.count() == 1

    def test_caller_owned_pending_duplicate_echoes_limited_existing(self, app, client):
        with app.app_context():
            creator = _make_user("creator@example.com")
            existing = _seed_local_player(
                "North Star Prospect",
                birth_year=DEFAULT_ADULT_BIRTH_YEAR,
                status="pending",
                created_by_user_id=creator.id,
            )
            db.session.commit()
            existing_id = existing.id

        response = client.post(
            "/api/local-players",
            json={"display_name": " NORTH\n star prospect ", "birth_year": DEFAULT_ADULT_BIRTH_YEAR},
            headers=_user_headers("creator@example.com"),
        )

        assert response.status_code == 409, response.get_json()
        body = response.get_json()
        assert body["error"]
        assert body["existing"] == {
            "id": existing_id,
            "display_name": "North Star Prospect",
            "club_name": "Northside Juniors",
            "status": "pending",
        }
        assert not {"city", "birth_year", "position", "country"} & body["existing"].keys()
        with app.app_context():
            assert LocalPlayer.query.count() == 1

    def test_duplicate_without_birth_year_uses_null_safe_match(self, app, client):
        with app.app_context():
            _seed_local_player("No Birth Year Prospect", birth_year=None, status="pending")
            db.session.commit()

        response = client.post(
            "/api/local-players",
            json={"display_name": " no  birth year prospect ", "relationship_type": "guardian"},
            headers=_user_headers("creator@example.com"),
        )

        assert response.status_code == 409, response.get_json()

    @pytest.mark.parametrize("existing_status", ["rejected", "merged"])
    def test_inactive_duplicate_can_be_recreated(self, app, client, existing_status):
        with app.app_context():
            existing = _seed_local_player("Recreated Prospect", status=existing_status)
            db.session.commit()
            existing_id = existing.id

        body = _create_local_player(client, display_name=" recreated prospect ")

        assert body["player"]["id"] != existing_id


# --------------------------------------------------------------------------- #
# Identity visibility and public showcase
# --------------------------------------------------------------------------- #


class TestLocalPlayerVisibility:
    def test_sql_minor_bridge_keeps_exact_date_adult_and_hides_conservative_minors(self, app):
        exact_adult_api_id = 81_001
        year_only_minor_api_id = 81_002
        unknown_age_api_id = 81_003
        with app.app_context():
            team = Team(
                team_id=81_000,
                name="Bridge Test Academy",
                country="England",
                season=datetime.now(UTC).year,
            )
            db.session.add(team)
            db.session.flush()
            db.session.add_all(
                [
                    TrackedPlayer(
                        player_api_id=player_api_id,
                        player_name=f"Bridge Player {player_api_id}",
                        team_id=team.id,
                        status="academy",
                        is_active=True,
                    )
                    for player_api_id in (exact_adult_api_id, year_only_minor_api_id, unknown_age_api_id)
                ]
            )
            exact_adult_birth_date = _birth_date_years_ago(18)
            _seed_local_player(
                "Exact Adult Bridge",
                birth_date=exact_adult_birth_date,
                birth_year=exact_adult_birth_date.year,
                status="approved",
                api_player_id=exact_adult_api_id,
            )
            _seed_local_player(
                "Year Only Minor Bridge",
                birth_year=2009,
                status="approved",
                api_player_id=year_only_minor_api_id,
            )
            _seed_local_player(
                "Unknown Age Bridge",
                birth_year=None,
                status="approved",
                api_player_id=unknown_age_api_id,
            )
            db.session.commit()

            visible_ids = {
                player_api_id
                for (player_api_id,) in db.session.query(TrackedPlayer.player_api_id)
                .filter(without_minor_local_bridge(TrackedPlayer.player_api_id))
                .all()
            }

        assert exact_adult_api_id in visible_ids
        assert year_only_minor_api_id not in visible_ids
        assert unknown_age_api_id not in visible_ids

    def test_pending_is_claimant_only_until_admin_approval(self, app, client):
        with app.app_context():
            player = _seed_local_player(status="pending")
            db.session.commit()
            player_id = player.id
            _, claim = _seed_claim(local_player_id=player_id, status="pending")
            claim_id = claim.id

        assert client.get(f"/api/local-players/{player_id}").status_code == 404
        assert (
            client.get(
                f"/api/local-players/{player_id}",
                headers=_user_headers("stranger@example.com"),
            ).status_code
            == 404
        )
        assert (
            client.get(
                f"/api/local-players/{player_id}",
                headers={"Authorization": "Bearer not.a.real.token"},
            ).status_code
            == 404
        )

        owner = client.get(
            f"/api/local-players/{player_id}",
            headers=_user_headers("owner@example.com"),
        )
        assert owner.status_code == 200, owner.get_json()
        assert owner.get_json()["player"]["status"] == "pending"
        assert owner.get_json()["player"]["club_name"] == "Northside Juniors"

        approved = client.post(
            f"/api/admin/local-players/{player_id}/review",
            json={"action": "approve", "note": "Identity checked"},
            headers=_admin_headers(),
        )
        assert approved.status_code == 200, approved.get_json()
        assert approved.get_json()["player"]["status"] == "approved"
        public = client.get(f"/api/local-players/{player_id}")
        assert public.status_code == 200, public.get_json()
        assert public.get_json()["player"]["id"] == player_id
        assert public.get_json()["player"]["club_name"] == "Northside Juniors"

        with app.app_context():
            # Identity approval does not silently approve the ownership claim.
            assert db.session.get(PlayerProfileClaim, claim_id).status == "pending"

    def test_rejected_player_remains_visible_to_its_claimant_only(self, app, client):
        with app.app_context():
            player = _seed_local_player(status="pending")
            db.session.commit()
            player_id = player.id
            _seed_claim(local_player_id=player_id, status="pending")

        rejected = client.post(
            f"/api/admin/local-players/{player_id}/review",
            json={"action": "reject"},
            headers=_admin_headers(),
        )
        assert rejected.status_code == 200, rejected.get_json()
        assert client.get(f"/api/local-players/{player_id}").status_code == 404
        owner = client.get(
            f"/api/local-players/{player_id}",
            headers=_user_headers("owner@example.com"),
        )
        assert owner.status_code == 200
        assert owner.get_json()["player"]["status"] == "rejected"

    def test_merged_player_follows_exactly_one_hop(self, app, client):
        with app.app_context():
            target = _seed_local_player("Canonical Prospect", status="approved")
            source = _seed_local_player(
                "Duplicate Prospect",
                status="merged",
                merged_into_local_player_id=target.id,
            )
            db.session.commit()
            source_id = source.id
            target_id = target.id

        response = client.get(f"/api/local-players/{source_id}")

        assert response.status_code == 200, response.get_json()
        assert set(response.get_json()) == {"player", "merged_into"}
        assert response.get_json()["merged_into"] == target_id
        assert response.get_json()["player"]["id"] == target_id
        assert response.get_json()["player"]["display_name"] == "Canonical Prospect"

    def test_showcase_shape_and_film_room_are_local_only(self, app, client, monkeypatch):
        with app.app_context():
            player = _seed_local_player(status="approved", api_player_id=987654)
            db.session.commit()
            player_id = player.id
            _seed_claim(local_player_id=player_id, status="pending")

        from src.routes import showcase as showcase_routes

        def _film_room_must_not_run(_player_api_id):
            raise AssertionError("local showcase attempted to load Film Room")

        monkeypatch.setattr(showcase_routes, "_verified_footage", _film_room_must_not_run)
        response = client.get(f"/api/local-players/{player_id}/showcase")

        assert response.status_code == 200, response.get_json()
        body = response.get_json()
        assert set(body) == {
            "local_player_id",
            "profile",
            "photos",
            "reel",
            "affiliations",
            "verified_footage",
            "claim_status",
        }
        assert body == {
            "local_player_id": player_id,
            "profile": None,
            "photos": [],
            "reel": [],
            "affiliations": [],
            "verified_footage": [],
            "claim_status": "unclaimed",
        }


# --------------------------------------------------------------------------- #
# Owner curation
# --------------------------------------------------------------------------- #


class TestLocalOwnerGate:
    def test_pending_claim_can_view_but_cannot_curate(self, app, client):
        with app.app_context():
            player = _seed_local_player(status="pending")
            db.session.commit()
            player_id = player.id
            _seed_claim(local_player_id=player_id, status="pending")
        headers = _user_headers("owner@example.com")

        assert client.get(f"/api/local-players/{player_id}/showcase", headers=headers).status_code == 200
        response = client.put(
            f"/api/local-players/{player_id}/showcase/profile",
            json={"bio": "Draft"},
            headers=headers,
        )
        assert response.status_code == 403

    @pytest.mark.parametrize(
        ("method", "suffix", "payload"),
        [
            ("PUT", "profile", {"bio": "No"}),
            ("POST", "reel", {"url": "https://youtu.be/nope123"}),
            ("POST", "photos", {"content_type": "image/jpeg", "size_bytes": 100}),
            ("POST", "affiliations", {"team_api_id": 33}),
        ],
    )
    def test_non_owner_cannot_curate_any_local_content(self, app, client, method, suffix, payload):
        with app.app_context():
            player = _seed_local_player(status="approved")
            db.session.commit()
            player_id = player.id
            _seed_claim(local_player_id=player_id, status="approved")

        response = client.open(
            f"/api/local-players/{player_id}/showcase/{suffix}",
            method=method,
            json=payload,
            headers=_user_headers("stranger@example.com"),
        )

        assert response.status_code == 403, response.get_json()

    def test_api_claim_with_same_integer_does_not_grant_local_ownership(self, app, client):
        with app.app_context():
            player = _seed_local_player(status="approved")
            db.session.commit()
            player_id = player.id
            _seed_claim(email="api-owner@example.com", player_api_id=player_id, status="approved")

        denied = client.put(
            f"/api/local-players/{player_id}/showcase/profile",
            json={"bio": "Crossed subject"},
            headers=_user_headers("api-owner@example.com"),
        )

        assert denied.status_code == 403, denied.get_json()


class TestLocalProfileCuration:
    def test_profile_owner_draft_and_local_admin_moderation(self, app, client):
        with app.app_context():
            player = _seed_local_player(status="approved")
            db.session.commit()
            player_id = player.id
            _seed_claim(local_player_id=player_id, status="approved")
        headers = _user_headers("owner@example.com")

        saved = client.put(
            f"/api/local-players/{player_id}/showcase/profile",
            json={
                "bio": "Community academy prospect",
                "positions": "CM",
                "preferred_foot": "right",
                "height_cm": 174,
            },
            headers=headers,
        )
        assert saved.status_code == 200, saved.get_json()
        profile = saved.get_json()["profile"]
        assert profile["player_api_id"] is None
        assert profile["local_player_id"] == player_id
        assert profile["status"] == "pending"

        assert client.get(f"/api/local-players/{player_id}/showcase").get_json()["profile"] is None
        owner = client.get(f"/api/local-players/{player_id}/showcase", headers=headers).get_json()["profile"]
        assert owner["bio"] == "Community academy prospect"
        assert owner["status"] == "pending"
        assert owner["local_player_id"] == player_id

        approved = client.post(
            f"/api/admin/showcase/local-profiles/{player_id}/review",
            json={"action": "approve"},
            headers=_admin_headers(),
        )
        assert approved.status_code == 200, approved.get_json()
        assert approved.get_json()["profile"]["status"] == "approved"
        public = client.get(f"/api/local-players/{player_id}/showcase").get_json()["profile"]
        assert public["bio"] == "Community academy prospect"
        assert public["local_player_id"] == player_id
        assert public["self_reported"] is True


class TestLocalReelCuration:
    def test_add_reorder_and_delete_local_reel_without_api_collision(self, app, client):
        with app.app_context():
            player = _seed_local_player(status="approved")
            db.session.commit()
            player_id = player.id
            _seed_claim(local_player_id=player_id, status="approved")
        headers = _user_headers("owner@example.com")

        first = client.post(
            f"/api/local-players/{player_id}/showcase/reel",
            json={"url": "https://youtu.be/local-a", "title": "First"},
            headers=headers,
        )
        second = client.post(
            f"/api/local-players/{player_id}/showcase/reel",
            json={"url": "https://youtu.be/local-b", "title": "Second"},
            headers=headers,
        )
        assert first.status_code == 201, first.get_json()
        assert second.status_code == 201, second.get_json()
        for response in (first, second):
            link = response.get_json()["link"]
            assert link["player_id"] is None
            assert link["local_player_id"] == player_id
            assert link["status"] == "pending"
        first_id = first.get_json()["link"]["id"]
        second_id = second.get_json()["link"]["id"]

        with app.app_context():
            db.session.get(PlayerLink, first_id).status = "approved"
            db.session.get(PlayerLink, second_id).status = "approved"
            foreign = PlayerLink(
                player_id=player_id,
                local_player_id=None,
                url="https://youtu.be/api-foreign",
                link_type="highlight",
                status="approved",
                sort_order=77,
            )
            db.session.add(foreign)
            db.session.commit()
            foreign_id = foreign.id

        reordered = client.patch(
            f"/api/local-players/{player_id}/showcase/reel/order",
            json={"ordered_ids": [second_id, foreign_id, "yt-1", first_id]},
            headers=headers,
        )
        assert reordered.status_code == 200, reordered.get_json()
        with app.app_context():
            assert db.session.get(PlayerLink, second_id).sort_order == 0
            assert db.session.get(PlayerLink, first_id).sort_order == 1
            assert db.session.get(PlayerLink, foreign_id).sort_order == 77

        public = client.get(f"/api/local-players/{player_id}/showcase").get_json()["reel"]
        assert [item["url"] for item in public] == ["https://youtu.be/local-b", "https://youtu.be/local-a"]
        assert all(item["local_player_id"] == player_id for item in public)

        deleted = client.delete(
            f"/api/local-players/{player_id}/showcase/reel/{first_id}",
            headers=headers,
        )
        assert deleted.status_code == 200, deleted.get_json()
        with app.app_context():
            assert db.session.get(PlayerLink, first_id) is None
            assert db.session.get(PlayerLink, foreign_id) is not None


class TestLocalPhotoCuration:
    def test_local_photo_full_owner_lifecycle_and_namespace(self, app, client):
        raw = _jpeg_bytes()
        with app.app_context():
            player = _seed_local_player(status="approved")
            db.session.commit()
            player_id = player.id
            _seed_claim(local_player_id=player_id, status="approved")
        headers = _user_headers("owner@example.com")

        first_created, first_pending = _create_complete_local_photo(client, player_id, headers, raw)
        second_created, second_pending = _create_complete_local_photo(client, player_id, headers, raw)
        assert f"/local-players/{player_id}/" in _url_path(first_created["upload"]["url"])
        assert f"/local-players/{player_id}/" in _url_path(second_created["upload"]["url"])
        assert first_pending["player_api_id"] is None
        assert first_pending["local_player_id"] == player_id

        owner_pending = client.get(
            f"/api/local-players/{player_id}/showcase",
            headers=headers,
        ).get_json()["photos"]
        assert {item["id"] for item in owner_pending} == {first_pending["id"], second_pending["id"]}
        assert client.get(f"/api/local-players/{player_id}/showcase").get_json()["photos"] == []

        for media_id in (first_pending["id"], second_pending["id"]):
            reviewed = client.post(
                f"/api/admin/showcase/media/{media_id}/review",
                json={"action": "approve"},
                headers=_admin_headers(),
            )
            assert reviewed.status_code == 200, reviewed.get_json()
            assert reviewed.get_json()["media"]["local_player_id"] == player_id

        reordered = client.patch(
            f"/api/local-players/{player_id}/showcase/photos/order",
            json={"ordered_ids": [second_pending["id"], first_pending["id"]]},
            headers=headers,
        )
        assert reordered.status_code == 200, reordered.get_json()
        assert [item["id"] for item in reordered.get_json()["photos"]] == [
            second_pending["id"],
            first_pending["id"],
        ]

        primary = client.patch(
            f"/api/local-players/{player_id}/showcase/photos/{first_pending['id']}",
            json={"is_primary": True},
            headers=headers,
        )
        assert primary.status_code == 200, primary.get_json()
        assert primary.get_json()["media"]["is_primary"] is True
        assert primary.get_json()["media"]["local_player_id"] == player_id

        deleted = client.delete(
            f"/api/local-players/{player_id}/showcase/photos/{second_pending['id']}",
            headers=headers,
        )
        assert deleted.status_code == 200, deleted.get_json()
        public = client.get(f"/api/local-players/{player_id}/showcase").get_json()["photos"]
        assert [item["id"] for item in public] == [first_pending["id"]]


class TestLocalAffiliationCuration:
    def test_create_moderate_publish_and_delete_local_affiliation(self, app, client):
        with app.app_context():
            player = _seed_local_player(status="approved")
            club = _seed_local_club()
            db.session.commit()
            player_id = player.id
            club_id = club.id
            _seed_claim(local_player_id=player_id, status="approved")
        headers = _user_headers("owner@example.com")

        created = client.post(
            f"/api/local-players/{player_id}/showcase/affiliations",
            json={"local_club_id": club_id, "season": " <b>2025/26</b> "},
            headers=headers,
        )
        assert created.status_code == 201, created.get_json()
        affiliation = created.get_json()["affiliation"]
        assert affiliation["player_api_id"] is None
        assert affiliation["local_player_id"] == player_id
        assert affiliation["local_club_id"] == club_id
        assert affiliation["season"] == "2025/26"
        assert affiliation["status"] == "pending"
        assert client.get(f"/api/local-players/{player_id}/showcase").get_json()["affiliations"] == []

        reviewed = client.post(
            f"/api/admin/showcase/affiliations/{affiliation['id']}/review",
            json={"action": "approve"},
            headers=_admin_headers(),
        )
        assert reviewed.status_code == 200, reviewed.get_json()
        public = client.get(f"/api/local-players/{player_id}/showcase").get_json()["affiliations"]
        assert len(public) == 1
        assert public[0]["local_player_id"] == player_id
        assert public[0]["club_name"] == "Northside Juniors"
        assert public[0]["status"] == "self_reported"

        deleted = client.delete(
            f"/api/local-players/{player_id}/showcase/affiliations/{affiliation['id']}",
            headers=headers,
        )
        assert deleted.status_code == 200, deleted.get_json()
        with app.app_context():
            assert db.session.get(PlayerClubAffiliation, affiliation["id"]) is None


def test_api_rows_with_same_numeric_id_do_not_consume_local_caps(app, client):
    with app.app_context():
        player = _seed_local_player(status="approved")
        db.session.commit()
        player_id = player.id
        owner, _ = _seed_claim(local_player_id=player_id, status="approved")
        for index in range(20):
            db.session.add(
                PlayerLink(
                    player_id=player_id,
                    local_player_id=None,
                    url=f"https://youtu.be/api-{index}",
                    link_type="highlight",
                    status="approved",
                )
            )
        for index in range(8):
            _seed_media(player_api_id=player_id, user_id=owner.id, status="pending", suffix=f"api-{index}")
        for index in range(5):
            db.session.add(
                PlayerClubAffiliation(
                    player_api_id=player_id,
                    local_player_id=None,
                    team_api_id=1000 + index,
                    status="pending",
                )
            )
        db.session.commit()
    headers = _user_headers("owner@example.com")

    reel = client.post(
        f"/api/local-players/{player_id}/showcase/reel",
        json={"url": "https://youtu.be/local-cap"},
        headers=headers,
    )
    photo = client.post(
        f"/api/local-players/{player_id}/showcase/photos",
        json={"content_type": "image/jpeg", "size_bytes": 100},
        headers=headers,
    )
    affiliation = client.post(
        f"/api/local-players/{player_id}/showcase/affiliations",
        json={"team_api_id": 999999},
        headers=headers,
    )

    assert reel.status_code == 201, reel.get_json()
    assert photo.status_code == 201, photo.get_json()
    assert affiliation.status_code == 201, affiliation.get_json()


# --------------------------------------------------------------------------- #
# Subject collision and claim verification
# --------------------------------------------------------------------------- #


class TestSubjectIsolation:
    def test_signed_showcase_resolves_only_approved_adult_local_subjects(self, app, client, monkeypatch):
        from src.routes import showcase as showcase_routes
        from src.services import player_shadow_service

        monkeypatch.setattr(
            player_shadow_service,
            "_resolve_client",
            lambda _client: (_ for _ in ()).throw(AssertionError("negative mint reached API client resolution")),
        )
        monkeypatch.setattr(
            showcase_routes,
            "_verified_footage",
            lambda _player_api_id: (_ for _ in ()).throw(AssertionError("local showcase loaded Film Room")),
        )

        adult = _create_local_player(client, display_name="Signed Adult")
        adult_id = adult["player"]["id"]
        approved = client.post(
            f"/api/admin/local-players/{adult_id}/review",
            json={"action": "approve"},
            headers=_admin_headers(),
        )
        assert approved.status_code == 200, approved.get_json()

        minor = _create_local_player(
            client,
            email="minor-creator@example.com",
            display_name="Private Minor",
            birth_year=datetime.now(UTC).year - 12,
            relationship_type="guardian",
        )
        minor_id = minor["player"]["id"]
        assert (
            client.post(
                f"/api/admin/local-players/{minor_id}/review",
                json={"action": "approve"},
                headers=_admin_headers(),
            ).status_code
            == 200
        )

        with app.app_context():
            db.session.add(
                PlayerShowcaseProfile(
                    local_player_id=adult_id,
                    bio="Local profile through the signed universe",
                    status="approved",
                )
            )
            db.session.commit()

        response = client.get(f"/api/players/{-adult_id}/showcase")
        assert response.status_code == 200, response.get_json()
        assert response.get_json()["local_player_id"] == adult_id
        assert response.get_json()["profile"]["bio"] == "Local profile through the signed universe"
        assert response.get_json()["verified_footage"] == []
        assert client.get(f"/api/players/{-minor_id}/showcase").status_code == 404
        assert client.get("/api/players/-999999/showcase").status_code == 404

    def test_local_and_api_payloads_do_not_cross_on_equal_ids(self, app, client):
        with app.app_context():
            player = _seed_local_player(status="approved")
            db.session.commit()
            player_id = player.id

            db.session.add(PlayerShadow(player_api_id=player_id, player_name="API identity"))

            db.session.add_all(
                [
                    PlayerShowcaseProfile(
                        player_api_id=None,
                        local_player_id=player_id,
                        bio="Local profile",
                        status="approved",
                    ),
                    PlayerShowcaseProfile(
                        player_api_id=player_id,
                        local_player_id=None,
                        bio="API profile",
                        status="approved",
                    ),
                    PlayerLink(
                        player_id=None,
                        local_player_id=player_id,
                        url="https://youtu.be/local-only",
                        link_type="highlight",
                        status="approved",
                    ),
                    PlayerLink(
                        player_id=player_id,
                        local_player_id=None,
                        url="https://youtu.be/api-only",
                        link_type="highlight",
                        status="approved",
                    ),
                    PlayerClubAffiliation(
                        player_api_id=None,
                        local_player_id=player_id,
                        team_api_id=101,
                        season="local-season",
                        status="self_reported",
                    ),
                    PlayerClubAffiliation(
                        player_api_id=player_id,
                        local_player_id=None,
                        team_api_id=202,
                        season="api-season",
                        status="self_reported",
                    ),
                ]
            )
            local_media = _seed_media(local_player_id=player_id, suffix="local-only")
            api_media = _seed_media(player_api_id=player_id, suffix="api-only")
            db.session.commit()
            local_media_id = local_media.id
            api_media_id = api_media.id

        local = client.get(f"/api/local-players/{player_id}/showcase")
        api = client.get(f"/api/players/{player_id}/showcase")

        assert local.status_code == 200, local.get_json()
        assert api.status_code == 200, api.get_json()
        local_body = local.get_json()
        api_body = api.get_json()
        assert local_body["profile"]["bio"] == "Local profile"
        assert local_body["profile"]["local_player_id"] == player_id
        assert [item["url"] for item in local_body["reel"]] == ["https://youtu.be/local-only"]
        assert [item["id"] for item in local_body["photos"]] == [local_media_id]
        assert [item["season"] for item in local_body["affiliations"]] == ["local-season"]

        assert api_body["profile"]["bio"] == "API profile"
        assert "local_player_id" not in api_body["profile"]
        assert [item["url"] for item in api_body["reel"]] == ["https://youtu.be/api-only"]
        assert [item["id"] for item in api_body["photos"]] == [api_media_id]
        assert [item["season"] for item in api_body["affiliations"]] == ["api-season"]
        assert all("local_player_id" not in item for item in api_body["reel"])
        assert all("local_player_id" not in item for item in api_body["photos"])
        assert all("local_player_id" not in item for item in api_body["affiliations"])

    def test_local_player_is_absent_from_club_and_admin_player_search(self, app, client):
        with app.app_context():
            _seed_local_player("Unique Northbridge Prospect", status="approved")
            db.session.commit()

        clubs = client.get(
            "/api/clubs/search?q=northbridge",
            headers=_user_headers("searcher@example.com"),
        )
        players = client.get(
            "/api/admin/showcase/player-search?q=northbridge",
            headers=_admin_headers(),
        )

        assert clubs.status_code == 200, clubs.get_json()
        assert clubs.get_json() == {"api_teams": [], "local_clubs": []}
        assert players.status_code == 200, players.get_json()
        assert players.get_json() == {"players": []}


class TestLocalClaims:
    def test_claim_model_enforces_exactly_one_subject(self, app):
        with app.app_context():
            user = _make_user("owner@example.com")
            both = PlayerProfileClaim(
                player_api_id=5001,
                local_player_id=1,
                user_account_id=user.id,
                relationship_type="player",
                status="pending",
            )
            db.session.add(both)
            with pytest.raises(ValueError, match="exactly one"):
                db.session.flush()
            db.session.rollback()

            neither = PlayerProfileClaim(
                player_api_id=None,
                local_player_id=None,
                user_account_id=user.id,
                relationship_type="player",
                status="pending",
            )
            db.session.add(neither)
            with pytest.raises(ValueError, match="exactly one"):
                db.session.flush()
            db.session.rollback()

    def test_me_claims_includes_local_mini_dict_and_null_local_id_for_api_claim(self, app, client):
        with app.app_context():
            player = _seed_local_player("Academy Prospect", status="pending")
            db.session.commit()
            player_id = player.id
            user = _make_user("owner@example.com")
            local_claim = PlayerProfileClaim(
                player_api_id=None,
                local_player_id=player_id,
                user_account_id=user.id,
                relationship_type="player",
                status="pending",
                verification_code=None,
                verification_status="unverified",
            )
            api_claim = PlayerProfileClaim(
                player_api_id=5001,
                local_player_id=None,
                user_account_id=user.id,
                relationship_type="agent",
                status="pending",
                verification_code=None,
                verification_status="unverified",
            )
            db.session.add_all([local_claim, api_claim])
            db.session.commit()
            local_claim_id = local_claim.id
            api_claim_id = api_claim.id

        response = client.get("/api/me/claims", headers=_user_headers("owner@example.com"))

        assert response.status_code == 200, response.get_json()
        by_id = {claim["id"]: claim for claim in response.get_json()["claims"]}
        local = by_id[local_claim_id]
        api = by_id[api_claim_id]
        assert local["player_api_id"] is None
        assert local["local_player_id"] == player_id
        assert local["local_player"] == {
            "id": player_id,
            "display_name": "Academy Prospect",
            "club_name": "Northside Juniors",
            "status": "pending",
        }
        assert local["player_name"] == "Academy Prospect"
        assert CODE_PATTERN.fullmatch(local["verification_code"])

        assert api["player_api_id"] == 5001
        assert api["local_player_id"] is None
        assert "local_player" not in api
        assert CODE_PATTERN.fullmatch(api["verification_code"])

    def test_existing_verify_endpoint_updates_local_claim(self, app, client, monkeypatch):
        code = "AW-ABCDEFGH"
        with app.app_context():
            player = _seed_local_player(status="pending")
            db.session.commit()
            player_id = player.id
            _, claim = _seed_claim(
                local_player_id=player_id,
                status="pending",
                code=code,
            )
            claim_id = claim.id
        _fake_get(monkeypatch, [FakeResponse(f"Player bio {code.lower()}".encode())])

        response = client.post(
            f"/api/me/claims/{claim_id}/verify",
            json={"proof_url": "https://instagram.com/academy-prospect"},
            headers=_user_headers("owner@example.com"),
        )

        assert response.status_code == 200, response.get_json()
        verified = response.get_json()["claim"]
        assert verified["player_api_id"] is None
        assert verified["local_player_id"] == player_id
        assert verified["status"] == "pending"
        assert verified["verification_status"] == "code_found"
        assert verified["verification_checked_at"]
        with app.app_context():
            stored = db.session.get(PlayerProfileClaim, claim_id)
            assert stored.player_api_id is None
            assert stored.local_player_id == player_id
            assert stored.verification_status == "code_found"


# --------------------------------------------------------------------------- #
# Admin moderation, merge, and API bridge
# --------------------------------------------------------------------------- #


class TestAdminLocalPlayers:
    @pytest.mark.parametrize(
        ("action", "expected_status"),
        [("approve", "approved"), ("reject", "rejected")],
    )
    def test_list_creator_email_and_pending_only_review(self, app, client, action, expected_status):
        created = _create_local_player(
            client,
            email="creator@example.com",
            display_name=f"{action.title()} Prospect",
        )
        player_id = created["player"]["id"]

        listing = client.get("/api/admin/local-players?status=pending", headers=_admin_headers())
        assert listing.status_code == 200, listing.get_json()
        assert [player["id"] for player in listing.get_json()["players"]] == [player_id]
        listed = listing.get_json()["players"][0]
        assert listed["created_by_email"] == "creator@example.com"
        assert listed["normalized_name"] == f"{action} prospect"
        assert listed["provenance"] == "user"
        assert listed["club_name"] == "Northside Juniors"

        reviewed = client.post(
            f"/api/admin/local-players/{player_id}/review",
            json={"action": action, "note": " <b>Reviewed safely</b> "},
            headers=_admin_headers(),
        )
        assert reviewed.status_code == 200, reviewed.get_json()
        player = reviewed.get_json()["player"]
        assert player["status"] == expected_status
        assert player["club_name"] == "Northside Juniors"
        assert player["review_note"] == "Reviewed safely"
        assert player["reviewed_by"] == "admin@test.com"
        assert player["reviewed_at"]

        second = client.post(
            f"/api/admin/local-players/{player_id}/review",
            json={"action": action},
            headers=_admin_headers(),
        )
        assert second.status_code == (200 if action == "approve" else 409), second.get_json()

        with app.app_context():
            stored = db.session.get(LocalPlayer, player_id)
            shadows = PlayerShadow.query.all()
            if action == "approve":
                assert stored.api_player_id == -player_id
                assert len(shadows) == 1
                assert shadows[0].player_api_id == -player_id
                assert shadows[0].player_name == f"{action.title()} Prospect"
                assert shadows[0].position == "Midfielder"
                assert shadows[0].nationality == "England"
                assert shadows[0].birth_date is None
                assert shadows[0].photo_url is None
                assert shadows[0].requested_by_user_id == stored.created_by_user_id
            else:
                assert stored.api_player_id is None
                assert shadows == []

    def test_orphan_legacy_player_row_does_not_block_mint_or_scout_union(self, app, client, caplog):
        from src.routes import showcase as showcase_routes

        with app.app_context():
            player = _seed_local_player("Orphan Namespace Prospect", status="pending")
            signed_id = -player.id
            db.session.add(Player(player_id=signed_id, name="Retired orphan row"))
            db.session.commit()
            player_id = player.id
            showcase_routes._logged_orphan_legacy_player_ids.discard(signed_id)
            assert showcase_routes._legacy_negative_identity_conflict(signed_id) is None
            assert showcase_routes._legacy_negative_identity_conflict(signed_id) is None

        reviewed = client.post(
            f"/api/admin/local-players/{player_id}/review",
            json={"action": "approve"},
            headers=_admin_headers(),
        )
        assert reviewed.status_code == 200, reviewed.get_json()
        assert reviewed.get_json()["player"]["api_player_id"] == signed_id

        repeated = client.post(
            f"/api/admin/local-players/{player_id}/review",
            json={"action": "approve"},
            headers=_admin_headers(),
        )
        assert repeated.status_code == 200, repeated.get_json()
        warnings = [record for record in caplog.records if "Ignoring orphan legacy players row" in record.message]
        assert len(warnings) == 1

        with app.app_context():
            from src.routes.scout import _scout_identity_subquery

            identity = _scout_identity_subquery(include_local=True)
            visible_ids = {row.player_api_id for row in db.session.query(identity.c.player_api_id).all()}
            assert signed_id in visible_ids

    @pytest.mark.parametrize(
        "reference_kind",
        ["tracked", "shadow", "claim", "watchlist", "follow", "follow_snapshot"],
    )
    def test_referenced_legacy_negative_id_blocks_approval(self, app, client, reference_kind):
        with app.app_context():
            player = _seed_local_player(f"Referenced {reference_kind} Prospect", status="pending")
            signed_id = -player.id
            if reference_kind == "tracked":
                team = Team(team_id=90_001, name="Legacy Academy", country="England", season=2025)
                db.session.add(team)
                db.session.flush()
                reference = TrackedPlayer(
                    player_api_id=signed_id,
                    player_name="Legacy tracked player",
                    team_id=team.id,
                )
            elif reference_kind == "shadow":
                reference = PlayerShadow(player_api_id=signed_id, player_name="Legacy shadow")
            elif reference_kind == "claim":
                _owner, reference = _seed_claim(player_api_id=signed_id, status="pending")
            elif reference_kind == "watchlist":
                watcher = _make_user("legacy-watchlist@example.com")
                reference = ScoutWatchlistEntry(user_account_id=watcher.id, player_api_id=signed_id)
            elif reference_kind == "follow":
                follower = _make_user("legacy-follow@example.com")
                follow_list = FollowList(user_account_id=follower.id, name="Legacy list")
                db.session.add(follow_list)
                db.session.flush()
                reference = Follow(
                    list_id=follow_list.id,
                    kind="player",
                    selector={"player_api_id": signed_id},
                )
            else:
                follower = _make_user("legacy-follow-snapshot@example.com")
                reference = FollowPlayerSnapshot(
                    user_account_id=follower.id,
                    player_api_id=signed_id,
                )
            db.session.add(reference)
            db.session.commit()
            player_id = player.id

        reviewed = client.post(
            f"/api/admin/local-players/{player_id}/review",
            json={"action": "approve"},
            headers=_admin_headers(),
        )
        assert reviewed.status_code == 409, reviewed.get_json()
        assert reviewed.get_json()["error"] == "synthetic player id conflicts with a legacy manual player"
        with app.app_context():
            stored = db.session.get(LocalPlayer, player_id)
            assert stored.status == "pending"
            assert stored.api_player_id is None

    def test_merge_repoints_every_local_subject_with_exact_counts(self, app, client):
        with app.app_context():
            source = _seed_local_player("Duplicate Prospect", status="pending")
            target = _seed_local_player("Canonical Prospect", status="approved")
            db.session.commit()
            source_id = source.id
            target_id = target.id

            first_user = _make_user("first@example.com")
            second_user = _make_user("second@example.com")
            api_user = _make_user("api@example.com")
            local_claims = [
                PlayerProfileClaim(
                    player_api_id=None,
                    local_player_id=source_id,
                    user_account_id=user.id,
                    relationship_type="player",
                    status="pending",
                )
                for user in (first_user, second_user)
            ]
            api_claim = PlayerProfileClaim(
                player_api_id=source_id,
                local_player_id=None,
                user_account_id=api_user.id,
                relationship_type="player",
                status="pending",
            )
            local_profile = PlayerShowcaseProfile(
                player_api_id=None,
                local_player_id=source_id,
                bio="Move me",
                status="pending",
            )
            api_profile = PlayerShowcaseProfile(
                player_api_id=source_id,
                local_player_id=None,
                bio="Leave API row",
                status="pending",
            )
            local_media = [_seed_media(local_player_id=source_id, suffix=f"local-{index}") for index in range(2)]
            api_media = _seed_media(player_api_id=source_id, suffix="api")
            local_affiliations = [
                PlayerClubAffiliation(
                    player_api_id=None,
                    local_player_id=source_id,
                    team_api_id=100 + index,
                    status="pending",
                )
                for index in range(2)
            ]
            api_affiliation = PlayerClubAffiliation(
                player_api_id=source_id,
                local_player_id=None,
                team_api_id=999,
                status="pending",
            )
            local_links = [
                PlayerLink(
                    player_id=None,
                    local_player_id=source_id,
                    url=f"https://youtu.be/local-{index}",
                    link_type="highlight",
                    status="pending",
                )
                for index in range(2)
            ]
            api_link = PlayerLink(
                player_id=source_id,
                local_player_id=None,
                url="https://youtu.be/api-row",
                link_type="highlight",
                status="pending",
            )
            db.session.add_all(
                [
                    *local_claims,
                    api_claim,
                    local_profile,
                    api_profile,
                    *local_affiliations,
                    api_affiliation,
                    *local_links,
                    api_link,
                ]
            )
            db.session.commit()
            local_claim_ids = [row.id for row in local_claims]
            local_profile_id = local_profile.id
            local_media_ids = [row.id for row in local_media]
            local_affiliation_ids = [row.id for row in local_affiliations]
            local_link_ids = [row.id for row in local_links]
            api_ids = {
                "claim": api_claim.id,
                "profile": api_profile.id,
                "media": api_media.id,
                "affiliation": api_affiliation.id,
                "link": api_link.id,
            }

        response = client.post(
            f"/api/admin/local-players/{source_id}/merge",
            json={"into_local_player_id": target_id},
            headers=_admin_headers(),
        )

        assert response.status_code == 200, response.get_json()
        assert response.get_json()["moved"] == {
            "claims": 2,
            "profiles": 1,
            "media": 2,
            "affiliations": 2,
            "links": 2,
        }
        assert response.get_json()["player"]["status"] == "merged"
        assert response.get_json()["player"]["merged_into_local_player_id"] == target_id

        with app.app_context():
            db.session.expire_all()
            source = db.session.get(LocalPlayer, source_id)
            assert source.status == "merged"
            assert source.merged_into_local_player_id == target_id
            assert {db.session.get(PlayerProfileClaim, row_id).local_player_id for row_id in local_claim_ids} == {
                target_id
            }
            assert db.session.get(PlayerShowcaseProfile, local_profile_id).local_player_id == target_id
            assert {db.session.get(PlayerShowcaseMedia, row_id).local_player_id for row_id in local_media_ids} == {
                target_id
            }
            assert {
                db.session.get(PlayerClubAffiliation, row_id).local_player_id for row_id in local_affiliation_ids
            } == {target_id}
            assert {db.session.get(PlayerLink, row_id).local_player_id for row_id in local_link_ids} == {target_id}

            assert db.session.get(PlayerProfileClaim, api_ids["claim"]).player_api_id == source_id
            assert db.session.get(PlayerProfileClaim, api_ids["claim"]).local_player_id is None
            assert db.session.get(PlayerShowcaseProfile, api_ids["profile"]).player_api_id == source_id
            assert db.session.get(PlayerShowcaseMedia, api_ids["media"]).player_api_id == source_id
            assert db.session.get(PlayerClubAffiliation, api_ids["affiliation"]).player_api_id == source_id
            assert db.session.get(PlayerLink, api_ids["link"]).player_id == source_id
            assert db.session.get(PlayerLink, api_ids["link"]).local_player_id is None

    def test_merge_consolidates_profile_collision_and_returns_card_to_moderation(self, app, client):
        with app.app_context():
            source = _seed_local_player("Duplicate Profile", status="approved")
            target = _seed_local_player("Canonical Profile", status="approved")
            db.session.commit()
            source_id = source.id
            target_id = target.id
            source_profile = PlayerShowcaseProfile(
                player_api_id=None,
                local_player_id=source_id,
                bio="Source biography",
                positions="CM",
                status="approved",
            )
            target_profile = PlayerShowcaseProfile(
                player_api_id=None,
                local_player_id=target_id,
                bio="Canonical biography",
                status="approved",
                reviewed_by="original-reviewer@example.com",
                reviewed_at=datetime.now(UTC),
            )
            db.session.add_all([source_profile, target_profile])
            db.session.commit()
            source_profile_id = source_profile.id
            target_profile_id = target_profile.id

        response = client.post(
            f"/api/admin/local-players/{source_id}/merge",
            json={"into_local_player_id": target_id},
            headers=_admin_headers(),
        )

        assert response.status_code == 200, response.get_json()
        assert response.get_json()["moved"]["profiles"] == 1
        with app.app_context():
            profiles = PlayerShowcaseProfile.query.filter_by(local_player_id=target_id).all()
            assert [profile.id for profile in profiles] == [target_profile_id]
            assert profiles[0].bio == "Canonical biography"
            assert profiles[0].positions == "CM"
            assert profiles[0].status == "pending"
            assert profiles[0].reviewed_by is None
            assert profiles[0].reviewed_at is None
            assert db.session.get(PlayerShowcaseProfile, source_profile_id) is None

    def test_merge_consolidates_same_users_claim_and_preserves_approval(self, app, client):
        with app.app_context():
            source = _seed_local_player("Duplicate Claim", status="approved")
            target = _seed_local_player("Canonical Claim", status="approved")
            db.session.commit()
            source_id = source.id
            target_id = target.id
            user = _make_user("same-owner@example.com")
            source_claim = PlayerProfileClaim(
                player_api_id=None,
                local_player_id=source_id,
                user_account_id=user.id,
                relationship_type="player",
                status="approved",
                verification_code="AW-ABCDEFGH",
                verification_status="code_found",
            )
            target_claim = PlayerProfileClaim(
                player_api_id=None,
                local_player_id=target_id,
                user_account_id=user.id,
                relationship_type="guardian",
                status="pending",
                verification_code="AW-HGFEDCBA",
                verification_status="unverified",
            )
            db.session.add_all([source_claim, target_claim])
            db.session.commit()
            source_claim_id = source_claim.id
            target_claim_id = target_claim.id
            user_id = user.id

        response = client.post(
            f"/api/admin/local-players/{source_id}/merge",
            json={"into_local_player_id": target_id},
            headers=_admin_headers(),
        )

        assert response.status_code == 200, response.get_json()
        assert response.get_json()["moved"]["claims"] == 1
        with app.app_context():
            claims = PlayerProfileClaim.query.filter_by(
                local_player_id=target_id,
                user_account_id=user_id,
            ).all()
            assert [claim.id for claim in claims] == [target_claim_id]
            assert claims[0].status == "approved"
            assert claims[0].relationship_type == "player"
            assert claims[0].verification_code == "AW-ABCDEFGH"
            assert claims[0].verification_status == "code_found"
            assert db.session.get(PlayerProfileClaim, source_claim_id) is None

    def test_merge_claim_collision_is_denial_safe_and_preserves_independent_evidence(self, app, client):
        with app.app_context():
            source = _seed_local_player("Approved Duplicate", status="approved")
            target = _seed_local_player("Revoked Canonical", status="approved")
            db.session.commit()
            source_id = source.id
            target_id = target.id
            user = _make_user("reviewed-owner@example.com")
            source_claim = PlayerProfileClaim(
                player_api_id=None,
                local_player_id=source_id,
                user_account_id=user.id,
                relationship_type="player",
                status="approved",
                verification_code="AW-ABCDEFGH",
                verification_proof_url="https://instagram.com/reviewed-owner",
                verification_status="code_found",
                verification_note="social code found",
                reviewed_by="source-reviewer@example.com",
                reviewed_at=datetime.now(UTC),
            )
            target_claim = PlayerProfileClaim(
                player_api_id=None,
                local_player_id=target_id,
                user_account_id=user.id,
                relationship_type="guardian",
                status="revoked",
                verification_code="AW-HGFEDCBA",
                verification_status="unverified",
                verification_note="official vouched previously",
                verification_method="vouch",
                reviewed_by="revoking-admin@example.com",
                reviewed_at=datetime.now(UTC),
            )
            db.session.add_all([source_claim, target_claim])
            db.session.commit()
            target_claim_id = target_claim.id

        response = client.post(
            f"/api/admin/local-players/{source_id}/merge",
            json={"into_local_player_id": target_id},
            headers=_admin_headers(),
        )

        assert response.status_code == 200, response.get_json()
        with app.app_context():
            claim = db.session.get(PlayerProfileClaim, target_claim_id)
            assert claim.status == "revoked"
            assert claim.relationship_type == "guardian"
            assert claim.reviewed_by == "revoking-admin@example.com"
            assert claim.verification_status == "code_found"
            assert claim.verification_proof_url == "https://instagram.com/reviewed-owner"
            assert claim.verification_method == "vouch"
            assert "social code found" in claim.verification_note
            assert "official vouched previously" in claim.verification_note

    def test_merge_rejects_self_missing_and_inactive_targets(self, app, client):
        with app.app_context():
            source = _seed_local_player("Source Prospect", status="pending")
            merged = _seed_local_player("Merged Target", status="merged")
            rejected = _seed_local_player("Rejected Target", status="rejected")
            db.session.commit()
            source_id = source.id
            invalid_targets = [source.id, merged.id, rejected.id, 999999]

        for target_id in invalid_targets:
            response = client.post(
                f"/api/admin/local-players/{source_id}/merge",
                json={"into_local_player_id": target_id},
                headers=_admin_headers(),
            )
            assert response.status_code == 400, (target_id, response.get_json())

        with app.app_context():
            source = db.session.get(LocalPlayer, source_id)
            assert source.status == "pending"
            assert source.merged_into_local_player_id is None

    @pytest.mark.parametrize("source_status", ["merged", "rejected"])
    def test_merge_rejects_inactive_source(self, app, client, source_status):
        with app.app_context():
            source = _seed_local_player("Inactive Source", status=source_status)
            target = _seed_local_player("Active Target", status="approved")
            db.session.commit()
            source_id = source.id
            target_id = target.id

        response = client.post(
            f"/api/admin/local-players/{source_id}/merge",
            json={"into_local_player_id": target_id},
            headers=_admin_headers(),
        )

        assert response.status_code == 409, response.get_json()

    def test_link_api_graduates_every_subject_store_and_is_idempotent(self, app, client):
        with app.app_context():
            creator = _make_user("bridge-creator@example.com")
            owner = _make_user("bridge-owner@example.com")
            scout = _make_user("bridge-scout@example.com")
            player = _seed_local_player(
                "Bridge Prospect",
                status="approved",
                created_by_user_id=creator.id,
            )
            db.session.flush()
            player_id = player.id
            old_player_api_id = -player_id
            player.api_player_id = old_player_api_id
            target_player_api_id = 5001

            source_claim = PlayerProfileClaim(
                local_player_id=player_id,
                user_account_id=owner.id,
                relationship_type="player",
                status="approved",
                verification_status="code_found",
            )
            target_claim = PlayerProfileClaim(
                player_api_id=target_player_api_id,
                user_account_id=owner.id,
                relationship_type="guardian",
                status="pending",
                verification_status="unverified",
            )
            source_profile = PlayerShowcaseProfile(
                local_player_id=player_id,
                bio="Local biography",
                positions="CM",
                status="approved",
            )
            target_profile = PlayerShowcaseProfile(
                player_api_id=target_player_api_id,
                bio="API biography",
                status="approved",
            )
            local_link = PlayerLink(
                player_id=None,
                local_player_id=player_id,
                url="https://youtu.be/graduates",
                link_type="highlight",
                status="approved",
            )
            local_media = _seed_media(local_player_id=player_id, suffix="graduates")
            affiliation = PlayerClubAffiliation(
                local_player_id=player_id,
                team_api_id=77,
                status="self_reported",
            )
            source_shadow = PlayerShadow(
                player_api_id=old_player_api_id,
                player_name="Bridge Prospect",
                position="Midfielder",
                requested_by_user_id=creator.id,
            )
            target_shadow = PlayerShadow(
                player_api_id=target_player_api_id,
                player_name="API Bridge Prospect",
                nationality="England",
            )
            shadow_stats = PlayerShadowStats(
                player_api_id=old_player_api_id,
                team_api_id=77,
                team_name="Bridge FC",
                season=2025,
                appearances=4,
                goals=2,
                assists=1,
                minutes=300,
            )
            source_watchlist = ScoutWatchlistEntry(
                user_account_id=scout.id,
                player_api_id=old_player_api_id,
                note="local note",
                last_snapshot='{"goals": 2}',
                last_digest_at=datetime.now(UTC),
            )
            target_watchlist = ScoutWatchlistEntry(
                user_account_id=scout.id,
                player_api_id=target_player_api_id,
            )
            follow_list = FollowList(user_account_id=scout.id, name="Graduation list")
            db.session.add(follow_list)
            db.session.flush()
            source_follow = Follow(
                list_id=follow_list.id,
                kind="player",
                selector={"player_api_id": old_player_api_id},
                note="follow note",
            )
            target_follow = Follow(
                list_id=follow_list.id,
                kind="player",
                selector={"player_api_id": target_player_api_id},
            )
            source_snapshot = FollowPlayerSnapshot(
                user_account_id=scout.id,
                player_api_id=old_player_api_id,
                last_snapshot='{"goals": 2}',
                last_digest_at=datetime.now(UTC),
            )
            target_snapshot = FollowPlayerSnapshot(
                user_account_id=scout.id,
                player_api_id=target_player_api_id,
            )
            source_roster = ClubRosterMember(
                program_id=1,
                local_player_id=player_id,
                added_by_user_id=scout.id,
                role="Captain",
            )
            target_roster = ClubRosterMember(
                program_id=1,
                player_api_id=target_player_api_id,
                added_by_user_id=scout.id,
            )
            now = datetime.now(UTC)
            old_cell = PlayerSeasonCell(
                player_api_id=old_player_api_id,
                season=2025,
                source="shadow",
                club_api_id=77,
                club_name="Bridge FC",
                competition_tier="league",
                level_group="senior",
                appearances=4,
                goals=2,
                assists=1,
                minutes=300,
                synced_at=now,
            )
            old_total = PlayerSeasonTotal(
                player_api_id=old_player_api_id,
                season=2025,
                level_group="senior",
                appearances=4,
                goals=2,
                assists=1,
                minutes=300,
                primary_source="shadow",
                computed_at=now,
            )
            suppression = PlayerSuppression(
                local_player_id=player_id,
                reason_code="player_request",
                requester_role="player",
                requester_contact="owner@example.com",
                request_statement="Historical lifted request",
                status="lifted",
            )
            target_suppression = PlayerSuppression(
                player_api_id=target_player_api_id,
                reason_code="legal",
                requester_role="other",
                requester_contact="legal@example.com",
                request_statement="Keep the graduated identity hidden",
                status="active",
            )
            pulse = PlayerPulse(
                player_api_id=old_player_api_id,
                window_end=now.date(),
                score=4.0,
                delta_json={"player": {"name": "Bridge Prospect"}},
                created_at=now,
            )
            card = PlayerCardCache(
                player_api_id=old_player_api_id,
                window_end=now.date(),
                card_html="<p>Bridge prospect</p>",
                card_text="Bridge prospect",
                model="test-model",
                created_at=now,
            )
            newsletter_link = NewsletterPlayerYoutubeLink(
                newsletter_id=999,
                player_id=old_player_api_id,
                player_name="Bridge Prospect",
                youtube_link="https://youtu.be/newsletter-bridge",
            )
            player_flag = PlayerFlag(
                player_api_id=old_player_api_id,
                reason="Bridge this identity",
                status="pending",
            )
            quick_take = QuickTakeSubmission(
                player_id=old_player_api_id,
                player_name="Bridge Prospect",
                content="A pending local observation",
                status="pending",
            )
            community_take = CommunityTake(
                source_type="submission",
                source_author="Local observer",
                content="An approved local observation",
                player_id=old_player_api_id,
                player_name="Bridge Prospect",
                status="approved",
            )
            commentary = NewsletterCommentary(
                player_id=old_player_api_id,
                commentary_type="player",
                content="Local player commentary",
                author_id=owner.id,
                author_name="Bridge Owner",
            )
            player_comment = PlayerComment(
                player_id=old_player_api_id,
                user_id=owner.id,
                author_email="bridge-owner@example.com",
                author_name="Bridge Owner",
                body="Local player page comment",
            )
            db.session.add_all(
                [
                    source_claim,
                    target_claim,
                    source_profile,
                    target_profile,
                    local_link,
                    affiliation,
                    source_shadow,
                    target_shadow,
                    shadow_stats,
                    source_watchlist,
                    target_watchlist,
                    source_follow,
                    target_follow,
                    source_snapshot,
                    target_snapshot,
                    source_roster,
                    target_roster,
                    old_cell,
                    old_total,
                    suppression,
                    target_suppression,
                    pulse,
                    card,
                    newsletter_link,
                    player_flag,
                    quick_take,
                    community_take,
                    commentary,
                    player_comment,
                ]
            )
            db.session.flush()
            contact = ContactRequest(
                scout_user_id=scout.id,
                player_api_id=old_player_api_id,
                claim_id=source_claim.id,
                message="Introduction",
                status="pending",
                routing_mode="direct",
                expires_at=(datetime.now(UTC) + timedelta(days=7)).replace(tzinfo=None),
            )
            video_roster = VideoRosterEntry(
                video_match_id=1,
                player_name="Bridge Prospect",
                jersey_number=8,
                club_roster_member_id=source_roster.id,
            )
            db.session.add_all([contact, video_roster])
            db.session.flush()
            video_report = VideoPlayerReport(
                video_match_id=1,
                roster_entry_id=video_roster.id,
                club_program_id_at_finalize=1,
                club_roster_member_id_at_finalize=source_roster.id,
                club_local_player_id_at_finalize=player_id,
                minutes_visible=45.0,
                model_version="test-model",
            )
            db.session.add(video_report)
            db.session.commit()
            local_link_id = local_link.id
            local_media_id = local_media.id
            target_claim_id = target_claim.id
            target_profile_id = target_profile.id
            source_roster_id = source_roster.id
            target_roster_id = target_roster.id
            contact_id = contact.id
            video_roster_id = video_roster.id
            video_report_id = video_report.id
            newsletter_link_id = newsletter_link.id
            player_flag_id = player_flag.id
            quick_take_id = quick_take.id
            community_take_id = community_take.id
            commentary_id = commentary.id
            player_comment_id = player_comment.id

        for invalid in (0, -1, "5001", True):
            response = client.post(
                f"/api/admin/local-players/{player_id}/link-api",
                json={"player_api_id": invalid},
                headers=_admin_headers(),
            )
            assert response.status_code == 400, (invalid, response.get_json())

        linked = client.post(
            f"/api/admin/local-players/{player_id}/link-api",
            json={"player_api_id": target_player_api_id},
            headers=_admin_headers(),
        )
        assert linked.status_code == 200, linked.get_json()
        body = linked.get_json()
        assert set(body) == {"player", "graduation"}
        assert body["player"]["api_player_id"] == target_player_api_id
        assert body["graduation"]["from_player_api_id"] == old_player_api_id
        assert body["graduation"]["to_player_api_id"] == target_player_api_id
        assert body["graduation"]["shadow_merged"] is True
        assert body["graduation"]["rollup"] == {"cells": 1, "totals": 1}
        assert body["graduation"]["rekeyed"] == {
            "claims": 1,
            "profiles": 1,
            "media": 1,
            "affiliations": 1,
            "links": 1,
            "player_shadows": 1,
            "shadow_stats": 1,
            "watchlist_entries": 1,
            "follow_selectors": 1,
            "follow_snapshots": 1,
            "roster_members": 1,
            "video_roster_entries": 1,
            "video_player_reports": 1,
            "contact_requests": 1,
            "suppressions": 1,
            "player_pulses": 1,
            "player_card_cache": 1,
            "newsletter_youtube_links": 1,
            "player_flags": 1,
            "quick_take_submissions": 1,
            "community_takes": 1,
            "newsletter_commentary": 1,
            "player_comments": 1,
            "season_cells": 1,
            "season_totals": 1,
        }

        with app.app_context():
            assert db.session.get(LocalPlayer, player_id).api_player_id == target_player_api_id
            assert db.session.get(PlayerLink, local_link_id).local_player_id is None
            assert db.session.get(PlayerLink, local_link_id).player_id == target_player_api_id
            assert db.session.get(PlayerShowcaseMedia, local_media_id).local_player_id is None
            assert db.session.get(PlayerShowcaseMedia, local_media_id).player_api_id == target_player_api_id
            claim = db.session.get(PlayerProfileClaim, target_claim_id)
            assert claim.status == "approved"
            assert claim.relationship_type == "player"
            assert claim.verification_status == "code_found"
            profile = db.session.get(PlayerShowcaseProfile, target_profile_id)
            assert profile.bio == "API biography"
            assert profile.positions == "CM"
            assert profile.status == "pending"
            assert PlayerShadow.query.filter_by(player_api_id=old_player_api_id).first() is None
            assert PlayerShadow.query.filter_by(player_api_id=target_player_api_id).count() == 1
            assert PlayerShadowStats.query.filter_by(player_api_id=target_player_api_id).count() == 1
            assert ScoutWatchlistEntry.query.filter_by(player_api_id=target_player_api_id).count() == 1
            assert ScoutWatchlistEntry.query.one().note == "local note"
            assert Follow.query.count() == 1
            assert Follow.query.one().selector == {"player_api_id": target_player_api_id}
            assert Follow.query.one().note == "follow note"
            assert FollowPlayerSnapshot.query.filter_by(player_api_id=target_player_api_id).count() == 1
            assert ClubRosterMember.query.count() == 1
            assert db.session.get(ClubRosterMember, target_roster_id).role == "Captain"
            assert db.session.get(VideoRosterEntry, video_roster_id).club_roster_member_id == target_roster_id
            report = db.session.get(VideoPlayerReport, video_report_id)
            assert report.club_roster_member_id_at_finalize == source_roster_id
            assert report.club_player_api_id_at_finalize == target_player_api_id
            assert report.club_local_player_id_at_finalize is None
            assert db.session.get(ContactRequest, contact_id).player_api_id == target_player_api_id
            assert db.session.get(ContactRequest, contact_id).claim_id == target_claim_id
            suppression_rows = PlayerSuppression.query.all()
            assert len(suppression_rows) == 2
            assert all(row.player_api_id == target_player_api_id for row in suppression_rows)
            assert all(row.local_player_id is None for row in suppression_rows)
            assert any(row.status == "active" for row in suppression_rows)
            assert PlayerPulse.query.filter_by(player_api_id=target_player_api_id).count() == 1
            assert PlayerCardCache.query.filter_by(player_api_id=target_player_api_id).count() == 1
            assert db.session.get(NewsletterPlayerYoutubeLink, newsletter_link_id).player_id == target_player_api_id
            assert db.session.get(PlayerFlag, player_flag_id).player_api_id == target_player_api_id
            assert db.session.get(QuickTakeSubmission, quick_take_id).player_id == target_player_api_id
            assert db.session.get(CommunityTake, community_take_id).player_id == target_player_api_id
            assert db.session.get(NewsletterCommentary, commentary_id).player_id == target_player_api_id
            assert db.session.get(PlayerComment, player_comment_id).player_id == target_player_api_id
            assert PlayerSeasonCell.query.filter_by(player_api_id=old_player_api_id).count() == 0
            assert PlayerSeasonTotal.query.filter_by(player_api_id=old_player_api_id).count() == 0
            assert PlayerSeasonCell.query.filter_by(player_api_id=target_player_api_id).count() == 1
            assert PlayerSeasonTotal.query.filter_by(player_api_id=target_player_api_id).count() == 1

        stale_negative = client.get(f"/api/players/{old_player_api_id}/showcase")
        assert stale_negative.status_code == 404

        repeated = client.post(
            f"/api/admin/local-players/{player_id}/link-api",
            json={"player_api_id": target_player_api_id},
            headers=_admin_headers(),
        )
        assert repeated.status_code == 200, repeated.get_json()
        assert all(value == 0 for value in repeated.get_json()["graduation"]["rekeyed"].values())
        assert repeated.get_json()["graduation"]["rollup"] == {"cells": 1, "totals": 1}

    def test_link_api_rejects_another_local_player_and_rolls_back_refresh_failure(self, app, client, monkeypatch):
        with app.app_context():
            first = _seed_local_player("First", status="approved")
            second = _seed_local_player("Second", status="approved", api_player_id=6001)
            db.session.flush()
            first.api_player_id = -first.id
            db.session.add(PlayerShadow(player_api_id=-first.id, player_name="First"))
            db.session.commit()
            first_id = first.id
            second_id = second.id
            old_player_api_id = -first_id

        conflict = client.post(
            f"/api/admin/local-players/{first_id}/link-api",
            json={"player_api_id": 6001},
            headers=_admin_headers(),
        )
        assert conflict.status_code == 409, conflict.get_json()

        from src.routes import showcase as showcase_routes

        monkeypatch.setattr(
            showcase_routes.season_rollup_service,
            "refresh_player",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("refresh failed")),
        )
        failed = client.post(
            f"/api/admin/local-players/{first_id}/link-api",
            json={"player_api_id": 6002},
            headers=_admin_headers(),
        )
        assert failed.status_code == 500, failed.get_json()
        with app.app_context():
            assert db.session.get(LocalPlayer, first_id).api_player_id == old_player_api_id
            assert db.session.get(LocalPlayer, second_id).api_player_id == 6001
            assert PlayerShadow.query.filter_by(player_api_id=old_player_api_id).count() == 1
            assert PlayerShadow.query.filter_by(player_api_id=6002).count() == 0

    def test_link_api_does_not_resurrect_rejected_showcase_duplicates(self, app, client):
        with app.app_context():
            player = _seed_local_player("Denied Duplicate", status="approved")
            db.session.flush()
            player_id = player.id
            old_player_api_id = -player_id
            target_player_api_id = 7001
            player.api_player_id = old_player_api_id
            db.session.add(PlayerShadow(player_api_id=old_player_api_id, player_name=player.display_name))

            source_media = _seed_media(local_player_id=player_id, suffix="same-photo", status="approved")
            target_media = _seed_media(
                player_api_id=target_player_api_id,
                suffix="target-photo",
                status="rejected",
            )
            target_media.blob_path = source_media.blob_path
            source_affiliation = PlayerClubAffiliation(
                local_player_id=player_id,
                team_api_id=77,
                status="club_confirmed",
            )
            target_affiliation = PlayerClubAffiliation(
                player_api_id=target_player_api_id,
                team_api_id=77,
                status="rejected",
            )
            source_link = PlayerLink(
                local_player_id=player_id,
                url="https://youtu.be/denied-duplicate",
                link_type="highlight",
                status="approved",
            )
            target_link = PlayerLink(
                player_id=target_player_api_id,
                url="https://youtube.com/watch?v=denied-duplicate",
                link_type="highlight",
                status="rejected",
            )
            db.session.add_all([source_affiliation, target_affiliation, source_link, target_link])
            db.session.commit()
            source_ids = (source_media.id, source_affiliation.id, source_link.id)
            target_ids = (target_media.id, target_affiliation.id, target_link.id)

        response = client.post(
            f"/api/admin/local-players/{player_id}/link-api",
            json={"player_api_id": target_player_api_id},
            headers=_admin_headers(),
        )

        assert response.status_code == 200, response.get_json()
        with app.app_context():
            assert [
                db.session.get(model, row_id)
                for model, row_id in zip(
                    (PlayerShowcaseMedia, PlayerClubAffiliation, PlayerLink), source_ids, strict=True
                )
            ] == [None, None, None]
            target_rows = [
                db.session.get(model, row_id)
                for model, row_id in zip(
                    (PlayerShowcaseMedia, PlayerClubAffiliation, PlayerLink), target_ids, strict=True
                )
            ]
            assert [row.status for row in target_rows] == ["rejected", "rejected", "rejected"]
