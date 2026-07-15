"""Tests for showcase-local clubs and pre-moderated affiliations.

Local clubs are deliberately separate from API-Football ``Team`` rows.  The
tests seed both stores directly and exercise only the showcase blueprint so a
regression cannot accidentally rely on journey, sync, crawl, or scout code.
"""

import pytest
from flask import Flask
from src.auth import _ensure_user_account, issue_user_token
from src.models.league import League, Team, db
from src.models.showcase import LocalClub, PlayerClubAffiliation, PlayerProfileClaim

ADMIN_KEY = "test-admin-key"
PLAYER_ID = 5001


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("SKIP_API_HANDSHAKE", "1")
    monkeypatch.setenv("API_USE_STUB_DATA", "true")
    monkeypatch.setenv("ADMIN_API_KEY", ADMIN_KEY)
    monkeypatch.setenv("ADMIN_IP_WHITELIST", "")

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
    flask_app.register_blueprint(showcase_bp, url_prefix="/api")

    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _user_headers(email):
    token = issue_user_token(email)["token"]
    return {"Authorization": f"Bearer {token}"}


def _admin_headers():
    token = issue_user_token("admin@test.com", role="admin")["token"]
    return {"Authorization": f"Bearer {token}", "X-API-Key": ADMIN_KEY}


def _make_user(email):
    user = _ensure_user_account(email)
    db.session.commit()
    return user


def _approved_claim(player_api_id=PLAYER_ID, email="owner@example.com"):
    user = _make_user(email)
    claim = PlayerProfileClaim(
        player_api_id=player_api_id,
        user_account_id=user.id,
        relationship_type="player",
        status="approved",
    )
    db.session.add(claim)
    db.session.commit()
    return user, claim


def _seed_team(team_id=33, name="Manchester United", country="England", season=2025):
    league = League.query.filter_by(league_id=39).first()
    if league is None:
        league = League(league_id=39, name="Premier League", country="England", season=2025)
        db.session.add(league)
        db.session.flush()
    team = Team(
        team_id=team_id,
        name=name,
        country=country,
        season=season,
        league_id=league.id,
        is_active=True,
    )
    db.session.add(team)
    db.session.flush()
    return team


def _seed_local_club(
    name="Northside Juniors",
    *,
    country="England",
    city="Leeds",
    level="youth",
    status="pending",
    normalized_name=None,
    merged_into_local_club_id=None,
    created_by_user_id=None,
):
    club = LocalClub(
        name=name,
        normalized_name=normalized_name or " ".join(name.lower().split()),
        country=country,
        city=city,
        level=level,
        status=status,
        provenance="user",
        merged_into_local_club_id=merged_into_local_club_id,
        created_by_user_id=created_by_user_id,
    )
    db.session.add(club)
    db.session.flush()
    return club


def _seed_affiliation(
    *,
    player_api_id=PLAYER_ID,
    local_club_id=None,
    team_api_id=None,
    season="2025/26",
    status="pending",
    created_by_user_id=None,
    review_note=None,
):
    affiliation = PlayerClubAffiliation(
        player_api_id=player_api_id,
        local_club_id=local_club_id,
        team_api_id=team_api_id,
        season=season,
        status=status,
        created_by_user_id=created_by_user_id,
        review_note=review_note,
    )
    db.session.add(affiliation)
    db.session.flush()
    return affiliation


# --------------------------------------------------------------------------- #
# Local-club creation and search
# --------------------------------------------------------------------------- #


class TestLocalClubCreation:
    def test_requires_auth(self, client):
        response = client.post("/api/local-clubs", json={"name": "Northside Juniors"})

        assert response.status_code == 401

    def test_create_sanitizes_caps_and_normalizes(self, app, client):
        response = client.post(
            "/api/local-clubs",
            json={
                "name": " <b>North   Star FC</b> ",
                "country": f"<script>{'E' * 110}</script>",
                "city": f"<i>{'C' * 130}</i>",
                "level": "academy",
            },
            headers=_user_headers("creator@example.com"),
        )

        assert response.status_code == 201, response.get_json()
        club = response.get_json()["club"]
        assert club["name"] == "North   Star FC"
        assert club["country"] == "E" * 100
        assert club["city"] == "C" * 120
        assert club["level"] == "academy"
        assert club["status"] == "pending"
        with app.app_context():
            stored = db.session.get(LocalClub, club["id"])
            assert stored.normalized_name == "north star fc"
            assert stored.provenance == "user"
            assert stored.created_by_user_id == _make_user("creator@example.com").id
            stored.name = "  Renamed\n  North Star  "
            db.session.flush()
            assert stored.normalized_name == "renamed north star"

    def test_name_and_level_validation(self, app, client):
        headers = _user_headers("creator@example.com")
        invalid_payloads = [
            {},
            {"name": "x"},
            {"name": "x" * 201},
            {"name": "Valid Club", "level": "elite"},
        ]

        for payload in invalid_payloads:
            response = client.post("/api/local-clubs", json=payload, headers=headers)
            assert response.status_code == 400, (payload, response.get_json())

        with app.app_context():
            assert LocalClub.query.count() == 0

    @pytest.mark.parametrize("existing_status", ["pending", "merged"])
    def test_duplicate_other_users_nonpublic_club_is_generic(self, app, client, existing_status):
        with app.app_context():
            other_user = _make_user("other@example.com")
            existing = _seed_local_club(
                "North Star FC",
                country="England",
                status=existing_status,
                created_by_user_id=other_user.id,
            )
            db.session.commit()

        response = client.post(
            "/api/local-clubs",
            json={"name": " NORTH\n  star fc ", "country": "eNgLaNd"},
            headers=_user_headers("creator@example.com"),
        )

        assert response.status_code == 409, response.get_json()
        assert response.get_json() == {"error": "A local club with this name and country already exists"}
        with app.app_context():
            assert LocalClub.query.count() == 1

    @pytest.mark.parametrize(
        ("existing_status", "same_creator"),
        [("verified", False), ("pending", True), ("merged", True)],
    )
    def test_duplicate_public_or_caller_created_club_returns_minimal_existing(
        self,
        app,
        client,
        existing_status,
        same_creator,
    ):
        with app.app_context():
            caller = _make_user("creator@example.com")
            other_user = _make_user("other@example.com")
            existing = _seed_local_club(
                "North Star FC",
                country="England",
                city="Private City",
                level="academy",
                status=existing_status,
                created_by_user_id=caller.id if same_creator else other_user.id,
            )
            db.session.commit()
            expected = {
                "id": existing.id,
                "name": "North Star FC",
                "country": "England",
                "status": existing_status,
            }

        response = client.post(
            "/api/local-clubs",
            json={"name": " NORTH\n  star fc ", "country": "eNgLaNd"},
            headers=_user_headers("creator@example.com"),
        )

        assert response.status_code == 409, response.get_json()
        assert response.get_json() == {
            "error": "A local club with this name and country already exists",
            "existing": expected,
        }

    def test_rejected_duplicate_can_be_recreated(self, app, client):
        with app.app_context():
            rejected = _seed_local_club("North Star FC", country="England", status="rejected")
            db.session.commit()
            rejected_id = rejected.id

        response = client.post(
            "/api/local-clubs",
            json={"name": "north star fc", "country": "ENGLAND"},
            headers=_user_headers("creator@example.com"),
        )

        assert response.status_code == 201, response.get_json()
        assert response.get_json()["club"]["id"] != rejected_id


class TestClubSearch:
    def test_requires_auth_and_two_character_query(self, client):
        assert client.get("/api/clubs/search?q=north").status_code == 401
        response = client.get("/api/clubs/search?q=n", headers=_user_headers("searcher@example.com"))
        assert response.status_code == 400

    def test_returns_api_and_visible_local_groups(self, app, client):
        with app.app_context():
            other_user = _make_user("other@example.com")
            team = _seed_team(team_id=4401, name="Northbridge United")
            _seed_team(team_id=4401, name="Northbridge United", season=2024)
            other_pending = _seed_local_club(
                "Northbridge Secret Juniors",
                city="Private Town",
                status="pending",
                created_by_user_id=other_user.id,
            )
            verified = _seed_local_club("Northbridge Academy", status="verified")
            _seed_local_club("Northbridge Old Name", status="merged")
            _seed_local_club("Northbridge Rejected", status="rejected")
            db.session.commit()
            team_id = team.team_id
            visible_ids = {verified.id}
            hidden_id = other_pending.id

        response = client.get(
            "/api/clubs/search?q=NoRtHbRiDgE",
            headers=_user_headers("searcher@example.com"),
        )

        assert response.status_code == 200, response.get_json()
        body = response.get_json()
        assert body["api_teams"] == [{"team_api_id": team_id, "name": "Northbridge United", "country": "England"}]
        assert {club["id"] for club in body["local_clubs"]} == visible_ids
        assert hidden_id not in {club["id"] for club in body["local_clubs"]}
        assert "Northbridge Secret Juniors" not in response.get_data(as_text=True)
        assert "Private Town" not in response.get_data(as_text=True)
        assert all(set(club) == {"id", "name", "country", "city", "level", "status"} for club in body["local_clubs"])
        assert {club["status"] for club in body["local_clubs"]} == {"verified"}

    def test_returns_callers_own_pending_local_club(self, app, client):
        with app.app_context():
            searcher = _make_user("searcher@example.com")
            own_pending = _seed_local_club(
                "Northbridge Juniors",
                status="pending",
                created_by_user_id=searcher.id,
            )
            db.session.commit()
            own_pending_id = own_pending.id

        response = client.get(
            "/api/clubs/search?q=NoRtHbRiDgE",
            headers=_user_headers("searcher@example.com"),
        )

        assert response.status_code == 200, response.get_json()
        assert [club["id"] for club in response.get_json()["local_clubs"]] == [own_pending_id]
        assert response.get_json()["local_clubs"][0]["status"] == "pending"

    def test_treats_percent_and_underscore_as_literal_search_text(self, app, client):
        with app.app_context():
            literal_team = _seed_team(team_id=4401, name="Literal %_ United")
            _seed_team(team_id=4402, name="Ordinary United")
            literal_club = _seed_local_club("Literal %_ Juniors", status="verified")
            _seed_local_club("Ordinary Juniors", status="verified")
            db.session.commit()
            literal_team_id = literal_team.team_id
            literal_club_id = literal_club.id

        response = client.get(
            "/api/clubs/search",
            query_string={"q": "%_"},
            headers=_user_headers("searcher@example.com"),
        )

        assert response.status_code == 200, response.get_json()
        assert response.get_json()["api_teams"] == [
            {
                "team_api_id": literal_team_id,
                "name": "Literal %_ United",
                "country": "England",
            }
        ]
        assert [club["id"] for club in response.get_json()["local_clubs"]] == [literal_club_id]

    def test_caps_each_result_group_at_ten(self, app, client):
        with app.app_context():
            for index in range(12):
                _seed_team(team_id=7000 + index, name=f"Search Team {index}")
                _seed_local_club(f"Search Local {index}", status="verified")
            db.session.commit()

        response = client.get(
            "/api/clubs/search?q=search",
            headers=_user_headers("searcher@example.com"),
        )

        assert response.status_code == 200, response.get_json()
        assert len(response.get_json()["api_teams"]) == 10
        assert len(response.get_json()["local_clubs"]) == 10


# --------------------------------------------------------------------------- #
# Owner affiliation lifecycle
# --------------------------------------------------------------------------- #


class TestAffiliationCreation:
    def test_requires_exactly_one_club_reference(self, app, client):
        with app.app_context():
            _approved_claim()
            local = _seed_local_club(status="verified")
            db.session.commit()
            local_id = local.id
        headers = _user_headers("owner@example.com")

        for payload in ({}, {"local_club_id": local_id, "team_api_id": 33}):
            response = client.post(
                f"/api/players/{PLAYER_ID}/showcase/affiliations",
                json=payload,
                headers=headers,
            )
            assert response.status_code == 400, (payload, response.get_json())

    def test_non_owner_is_forbidden(self, app, client):
        with app.app_context():
            _approved_claim()

        response = client.post(
            f"/api/players/{PLAYER_ID}/showcase/affiliations",
            json={"team_api_id": 33},
            headers=_user_headers("stranger@example.com"),
        )

        assert response.status_code == 403

    def test_positive_team_id_and_sanitized_season(self, app, client):
        with app.app_context():
            owner, _ = _approved_claim()
            owner_id = owner.id

        response = client.post(
            f"/api/players/{PLAYER_ID}/showcase/affiliations",
            json={"team_api_id": 987654, "season": " <b>2025/26</b> "},
            headers=_user_headers("owner@example.com"),
        )

        assert response.status_code == 201, response.get_json()
        affiliation = response.get_json()["affiliation"]
        assert affiliation["player_api_id"] == PLAYER_ID
        assert affiliation["team_api_id"] == 987654
        assert affiliation["local_club_id"] is None
        assert affiliation["season"] == "2025/26"
        assert affiliation["status"] == "pending"
        with app.app_context():
            stored = db.session.get(PlayerClubAffiliation, affiliation["id"])
            assert stored.created_by_user_id == owner_id

    def test_team_id_and_season_validation(self, app, client):
        with app.app_context():
            _approved_claim()
        headers = _user_headers("owner@example.com")

        for team_api_id in (0, -1, "33", True):
            response = client.post(
                f"/api/players/{PLAYER_ID}/showcase/affiliations",
                json={"team_api_id": team_api_id},
                headers=headers,
            )
            assert response.status_code == 400, (team_api_id, response.get_json())

        response = client.post(
            f"/api/players/{PLAYER_ID}/showcase/affiliations",
            json={"team_api_id": 33, "season": "x" * 21},
            headers=headers,
        )
        assert response.status_code == 400, response.get_json()

    def test_local_reference_must_be_active(self, app, client):
        with app.app_context():
            _approved_claim()
            merged = _seed_local_club("Merged Club", status="merged")
            rejected = _seed_local_club("Rejected Club", status="rejected")
            db.session.commit()
            invalid_ids = [merged.id, rejected.id, 999999]
        headers = _user_headers("owner@example.com")

        for local_club_id in invalid_ids:
            response = client.post(
                f"/api/players/{PLAYER_ID}/showcase/affiliations",
                json={"local_club_id": local_club_id},
                headers=headers,
            )
            assert response.status_code == 400, (local_club_id, response.get_json())

    def test_five_non_rejected_cap_but_rejected_does_not_count(self, app, client):
        with app.app_context():
            owner, _ = _approved_claim()
            for index in range(4):
                _seed_affiliation(team_api_id=1000 + index, created_by_user_id=owner.id)
            _seed_affiliation(team_api_id=1999, status="rejected", created_by_user_id=owner.id)
            db.session.commit()
        headers = _user_headers("owner@example.com")

        fifth = client.post(
            f"/api/players/{PLAYER_ID}/showcase/affiliations",
            json={"team_api_id": 2000},
            headers=headers,
        )
        assert fifth.status_code == 201, fifth.get_json()

        sixth = client.post(
            f"/api/players/{PLAYER_ID}/showcase/affiliations",
            json={"team_api_id": 2001},
            headers=headers,
        )
        assert sixth.status_code == 409, sixth.get_json()

    def test_duplicate_local_and_team_references_are_409(self, app, client):
        with app.app_context():
            owner, _ = _approved_claim()
            local = _seed_local_club(status="verified")
            _seed_affiliation(local_club_id=local.id, created_by_user_id=owner.id)
            _seed_affiliation(team_api_id=33, status="self_reported", created_by_user_id=owner.id)
            db.session.commit()
            local_id = local.id
        headers = _user_headers("owner@example.com")

        for payload in ({"local_club_id": local_id}, {"team_api_id": 33}):
            response = client.post(
                f"/api/players/{PLAYER_ID}/showcase/affiliations",
                json=payload,
                headers=headers,
            )
            assert response.status_code == 409, (payload, response.get_json())

    def test_rejected_duplicate_can_be_resubmitted(self, app, client):
        with app.app_context():
            owner, _ = _approved_claim()
            _seed_affiliation(team_api_id=33, status="rejected", created_by_user_id=owner.id)
            db.session.commit()

        response = client.post(
            f"/api/players/{PLAYER_ID}/showcase/affiliations",
            json={"team_api_id": 33},
            headers=_user_headers("owner@example.com"),
        )

        assert response.status_code == 201, response.get_json()


class TestAffiliationDelete:
    def test_owner_deletes_player_row(self, app, client):
        with app.app_context():
            owner, _ = _approved_claim()
            affiliation = _seed_affiliation(team_api_id=33, created_by_user_id=owner.id)
            db.session.commit()
            affiliation_id = affiliation.id

        response = client.delete(
            f"/api/players/{PLAYER_ID}/showcase/affiliations/{affiliation_id}",
            headers=_user_headers("owner@example.com"),
        )

        assert response.status_code == 200, response.get_json()
        assert response.get_json() == {"deleted": True}
        with app.app_context():
            assert db.session.get(PlayerClubAffiliation, affiliation_id) is None

    def test_non_owner_cannot_delete_and_wrong_player_row_is_not_found(self, app, client):
        with app.app_context():
            owner, _ = _approved_claim()
            affiliation = _seed_affiliation(player_api_id=9999, team_api_id=33, created_by_user_id=owner.id)
            db.session.commit()
            affiliation_id = affiliation.id

        stranger = client.delete(
            f"/api/players/{PLAYER_ID}/showcase/affiliations/{affiliation_id}",
            headers=_user_headers("stranger@example.com"),
        )
        assert stranger.status_code == 403

        wrong_player = client.delete(
            f"/api/players/{PLAYER_ID}/showcase/affiliations/{affiliation_id}",
            headers=_user_headers("owner@example.com"),
        )
        assert wrong_player.status_code == 404
        with app.app_context():
            assert db.session.get(PlayerClubAffiliation, affiliation_id) is not None


# --------------------------------------------------------------------------- #
# Showcase visibility and club-name resolution
# --------------------------------------------------------------------------- #


class TestAffiliationVisibility:
    def test_public_sees_approved_states_owner_sees_all_with_notes(self, app, client):
        with app.app_context():
            owner, _ = _approved_claim()
            local = _seed_local_club("Northside Juniors", status="verified")
            _seed_team(team_id=33, name="Manchester United")
            _seed_affiliation(
                local_club_id=local.id,
                status="pending",
                created_by_user_id=owner.id,
                review_note="Awaiting review",
            )
            _seed_affiliation(
                team_api_id=33,
                status="rejected",
                created_by_user_id=owner.id,
                review_note="Wrong club",
            )
            _seed_affiliation(
                team_api_id=33,
                status="self_reported",
                created_by_user_id=owner.id,
                review_note="Approved by admin",
            )
            _seed_affiliation(
                local_club_id=local.id,
                status="club_confirmed",
                created_by_user_id=owner.id,
                review_note="Confirmed by official",
            )
            db.session.commit()

        public_response = client.get(f"/api/players/{PLAYER_ID}/showcase")
        assert public_response.status_code == 200, public_response.get_json()
        public = public_response.get_json()["affiliations"]
        assert {item["status"] for item in public} == {"self_reported", "club_confirmed"}
        assert {item["club_name"] for item in public} == {"Manchester United", "Northside Juniors"}
        assert all("review_note" not in item for item in public)
        assert all(
            set(item)
            == {
                "id",
                "player_api_id",
                "team_api_id",
                "local_club_id",
                "club_name",
                "season",
                "status",
                "created_at",
            }
            for item in public
        )

        stranger = client.get(
            f"/api/players/{PLAYER_ID}/showcase",
            headers=_user_headers("stranger@example.com"),
        ).get_json()["affiliations"]
        assert {item["status"] for item in stranger} == {"self_reported", "club_confirmed"}
        assert all("review_note" not in item for item in stranger)

        admin_bearer_only = client.get(
            f"/api/players/{PLAYER_ID}/showcase",
            headers={"Authorization": f"Bearer {issue_user_token('admin@test.com', role='admin')['token']}"},
        ).get_json()["affiliations"]
        assert {item["status"] for item in admin_bearer_only} == {"self_reported", "club_confirmed"}
        assert all("review_note" not in item for item in admin_bearer_only)

        owner_view = client.get(
            f"/api/players/{PLAYER_ID}/showcase",
            headers=_user_headers("owner@example.com"),
        ).get_json()["affiliations"]
        assert {item["status"] for item in owner_view} == {
            "pending",
            "rejected",
            "self_reported",
            "club_confirmed",
        }
        notes = {item["status"]: item["review_note"] for item in owner_view}
        assert notes == {
            "pending": "Awaiting review",
            "rejected": "Wrong club",
            "self_reported": "Approved by admin",
            "club_confirmed": "Confirmed by official",
        }
        assert all(item["created_at"] for item in owner_view)
        assert all("review_note" in item for item in owner_view)

    def test_public_hides_unverified_local_names_owner_and_admin_keep_them(self, app, client):
        with app.app_context():
            owner, _ = _approved_claim()
            pending = _seed_local_club("Pending Private Club", status="pending")
            rejected = _seed_local_club("Rejected Private Club", status="rejected")
            pending_merge_target = _seed_local_club("Pending Merge Target", status="pending")
            merged_source = _seed_local_club(
                "Old Merged Club",
                status="merged",
                merged_into_local_club_id=pending_merge_target.id,
            )
            affiliations = [
                _seed_affiliation(
                    local_club_id=pending.id,
                    status="self_reported",
                    created_by_user_id=owner.id,
                ),
                _seed_affiliation(
                    local_club_id=rejected.id,
                    status="self_reported",
                    created_by_user_id=owner.id,
                ),
                _seed_affiliation(
                    local_club_id=merged_source.id,
                    status="self_reported",
                    created_by_user_id=owner.id,
                ),
            ]
            db.session.commit()
            expected_private_names = {
                affiliations[0].id: "Pending Private Club",
                affiliations[1].id: "Rejected Private Club",
                affiliations[2].id: "Pending Merge Target",
            }

        public_response = client.get(f"/api/players/{PLAYER_ID}/showcase")

        assert public_response.status_code == 200, public_response.get_json()
        public_affiliations = public_response.get_json()["affiliations"]
        assert {item["id"] for item in public_affiliations} == set(expected_private_names)
        assert all(item["club_name"] is None for item in public_affiliations)
        assert all(name not in public_response.get_data(as_text=True) for name in expected_private_names.values())

        owner_response = client.get(
            f"/api/players/{PLAYER_ID}/showcase",
            headers=_user_headers("owner@example.com"),
        )
        assert owner_response.status_code == 200, owner_response.get_json()
        assert {
            item["id"]: item["club_name"] for item in owner_response.get_json()["affiliations"]
        } == expected_private_names

        admin_response = client.get(
            "/api/admin/showcase/affiliations?status=self_reported",
            headers=_admin_headers(),
        )
        assert admin_response.status_code == 200, admin_response.get_json()
        assert {
            item["id"]: item["club_name"] for item in admin_response.get_json()["affiliations"]
        } == expected_private_names

    def test_merged_local_club_name_follows_one_hop(self, app, client):
        with app.app_context():
            target = _seed_local_club("Current Club Name", status="verified")
            source = _seed_local_club(
                "Old Club Name",
                status="merged",
                merged_into_local_club_id=target.id,
            )
            affiliation = _seed_affiliation(local_club_id=source.id, status="self_reported")
            db.session.commit()
            affiliation_id = affiliation.id

        response = client.get(f"/api/players/{PLAYER_ID}/showcase")

        assert response.status_code == 200, response.get_json()
        affiliations = response.get_json()["affiliations"]
        assert [(item["id"], item["club_name"]) for item in affiliations] == [(affiliation_id, "Current Club Name")]


# --------------------------------------------------------------------------- #
# Admin local-club moderation, merge, and API bridge
# --------------------------------------------------------------------------- #


class TestAdminLocalClubs:
    def test_list_filters_by_status(self, app, client):
        with app.app_context():
            pending = _seed_local_club("Pending Club", status="pending")
            _seed_local_club("Verified Club", status="verified")
            db.session.commit()
            pending_id = pending.id

        response = client.get("/api/admin/local-clubs?status=pending", headers=_admin_headers())

        assert response.status_code == 200, response.get_json()
        assert [club["id"] for club in response.get_json()["clubs"]] == [pending_id]

    @pytest.mark.parametrize(
        ("action", "expected_status"),
        [("verify", "verified"), ("reject", "rejected")],
    )
    def test_review_pending_then_blocks_second_review(self, app, client, action, expected_status):
        with app.app_context():
            club = _seed_local_club(status="pending")
            db.session.commit()
            club_id = club.id

        response = client.post(
            f"/api/admin/local-clubs/{club_id}/review",
            json={"action": action, "note": "<b>Reviewed safely</b>"},
            headers=_admin_headers(),
        )

        assert response.status_code == 200, response.get_json()
        reviewed = response.get_json()["club"]
        assert reviewed["status"] == expected_status
        assert reviewed["review_note"] == "Reviewed safely"
        assert reviewed["reviewed_by"] == "admin@test.com"
        assert reviewed["reviewed_at"]

        second = client.post(
            f"/api/admin/local-clubs/{club_id}/review",
            json={"action": action},
            headers=_admin_headers(),
        )
        assert second.status_code == 409, second.get_json()

    def test_merge_repoints_all_affiliations(self, app, client):
        with app.app_context():
            source = _seed_local_club("Duplicate Juniors", status="pending")
            target = _seed_local_club("Canonical Juniors", status="verified")
            first = _seed_affiliation(local_club_id=source.id, status="pending")
            second = _seed_affiliation(player_api_id=5002, local_club_id=source.id, status="self_reported")
            db.session.commit()
            source_id = source.id
            target_id = target.id
            affiliation_ids = [first.id, second.id]

        response = client.post(
            f"/api/admin/local-clubs/{source_id}/merge",
            json={"into_local_club_id": target_id},
            headers=_admin_headers(),
        )

        assert response.status_code == 200, response.get_json()
        assert response.get_json()["moved_affiliations"] == 2
        merged = response.get_json()["club"]
        assert merged["status"] == "merged"
        assert merged["merged_into_local_club_id"] == target_id
        with app.app_context():
            source_row = db.session.get(LocalClub, source_id)
            assert source_row.status == "merged"
            assert source_row.merged_into_local_club_id == target_id
            moved = db.session.query(PlayerClubAffiliation).filter(PlayerClubAffiliation.id.in_(affiliation_ids)).all()
            assert {row.local_club_id for row in moved} == {target_id}

    def test_merge_blocks_self_missing_and_inactive_targets(self, app, client):
        with app.app_context():
            source = _seed_local_club("Source Club", status="pending")
            merged_target = _seed_local_club("Merged Target", status="merged")
            rejected_target = _seed_local_club("Rejected Target", status="rejected")
            db.session.commit()
            source_id = source.id
            invalid_target_ids = [source.id, merged_target.id, rejected_target.id, 999999]

        for target_id in invalid_target_ids:
            response = client.post(
                f"/api/admin/local-clubs/{source_id}/merge",
                json={"into_local_club_id": target_id},
                headers=_admin_headers(),
            )
            assert response.status_code == 400, (target_id, response.get_json())

        with app.app_context():
            source = db.session.get(LocalClub, source_id)
            assert source.status == "pending"
            assert source.merged_into_local_club_id is None

    def test_link_api_validates_positive_integer_and_never_writes_teams(self, app, client):
        with app.app_context():
            club = _seed_local_club(status="verified")
            db.session.commit()
            club_id = club.id
            assert Team.query.count() == 0

        for invalid in (0, -1, "33", True):
            response = client.post(
                f"/api/admin/local-clubs/{club_id}/link-api",
                json={"team_api_id": invalid},
                headers=_admin_headers(),
            )
            assert response.status_code == 400, (invalid, response.get_json())

        linked = client.post(
            f"/api/admin/local-clubs/{club_id}/link-api",
            json={"team_api_id": 987654},
            headers=_admin_headers(),
        )
        assert linked.status_code == 200, linked.get_json()
        assert linked.get_json()["club"]["api_team_id"] == 987654
        with app.app_context():
            assert db.session.get(LocalClub, club_id).api_team_id == 987654
            assert Team.query.count() == 0


# --------------------------------------------------------------------------- #
# Admin affiliation moderation
# --------------------------------------------------------------------------- #


class TestAdminAffiliations:
    def test_list_filters_and_resolves_both_club_kinds(self, app, client):
        with app.app_context():
            local = _seed_local_club("Northside Juniors", status="verified")
            _seed_team(team_id=33, name="Manchester United")
            local_affiliation = _seed_affiliation(
                local_club_id=local.id,
                status="pending",
                review_note="Local note",
            )
            team_affiliation = _seed_affiliation(
                player_api_id=5002,
                team_api_id=33,
                status="pending",
                review_note="Team note",
            )
            _seed_affiliation(player_api_id=5003, team_api_id=44, status="rejected")
            db.session.commit()
            expected = {
                local_affiliation.id: ("Northside Juniors", "Local note"),
                team_affiliation.id: ("Manchester United", "Team note"),
            }

        response = client.get(
            "/api/admin/showcase/affiliations?status=pending",
            headers=_admin_headers(),
        )

        assert response.status_code == 200, response.get_json()
        affiliations = response.get_json()["affiliations"]
        assert {item["id"] for item in affiliations} == set(expected)
        assert {item["id"]: (item["club_name"], item["review_note"]) for item in affiliations} == expected

    @pytest.mark.parametrize(
        ("action", "expected_status"),
        [("approve", "self_reported"), ("reject", "rejected")],
    )
    def test_review_pending_then_blocks_second_review(self, app, client, action, expected_status):
        with app.app_context():
            affiliation = _seed_affiliation(team_api_id=33, status="pending")
            db.session.commit()
            affiliation_id = affiliation.id

        response = client.post(
            f"/api/admin/showcase/affiliations/{affiliation_id}/review",
            json={"action": action, "note": "<i>Moderator note</i>"},
            headers=_admin_headers(),
        )

        assert response.status_code == 200, response.get_json()
        reviewed = response.get_json()["affiliation"]
        assert reviewed["status"] == expected_status
        assert reviewed["review_note"] == "Moderator note"
        with app.app_context():
            stored = db.session.get(PlayerClubAffiliation, affiliation_id)
            assert stored.status == expected_status
            assert stored.reviewed_by == "admin@test.com"
            assert stored.reviewed_at is not None

        second = client.post(
            f"/api/admin/showcase/affiliations/{affiliation_id}/review",
            json={"action": action},
            headers=_admin_headers(),
        )
        assert second.status_code == 409, second.get_json()
