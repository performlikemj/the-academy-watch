"""Tests for the Follow Graph + Shadow Tracking feature.

Covers lists CRUD/caps/owner-gates, per-kind selector validation, the resolver
(each kind + union dedup + caps), shadow mint/cap/search stub-safety, the
watchlist->list dual-write mirror, the backfill admin endpoint
(dry-run/real/idempotent/cursor), digest generalization (per-list sections +
shadow "now tracking" card + FollowPlayerSnapshot persistence) with the
watchlist-only regression, and the profile/season-stats shadow fallbacks.
"""

import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from flask import Flask
from src.models.follow import Follow, FollowList, FollowPlayerSnapshot, PlayerShadow, PlayerShadowStats
from src.models.funding import ClubProgram, FundingLeague
from src.models.league import League, Team, db
from src.models.scout_watchlist import ScoutWatchlistEntry
from src.models.tracked_player import TrackedPlayer
from src.models.weekly import Fixture, FixturePlayerStats

ADMIN_KEY = "test-admin-key"


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("SKIP_API_HANDSHAKE", "1")
    monkeypatch.setenv("API_USE_STUB_DATA", "true")
    monkeypatch.setenv("ADMIN_API_KEY", ADMIN_KEY)
    monkeypatch.setenv("ADMIN_IP_WHITELIST", "")

    from src.routes.players import players_bp
    from src.routes.scout import scout_bp

    template_dir = Path(__file__).resolve().parent.parent / "src" / "templates"
    flask_app = Flask(__name__, template_folder=str(template_dir))
    flask_app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret-key",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        RATELIMIT_ENABLED=False,
    )
    db.init_app(flask_app)
    flask_app.register_blueprint(players_bp, url_prefix="/api")
    flask_app.register_blueprint(scout_bp, url_prefix="/api")

    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def seeded(app):
    """Parent academy + Brazilian loan club, two tracked players, one shadow."""
    league = League(league_id=39, name="Premier League", country="England", season=2025, is_european_top_league=True)
    db.session.add(league)
    db.session.flush()

    parent = Team(
        team_id=33, name="Manchester United", country="England", season=2025, league_id=league.id, is_active=True
    )
    loan_club = Team(team_id=901, name="Rio FC", country="Brazil", season=2025, league_id=league.id, is_active=True)
    db.session.add_all([parent, loan_club])
    db.session.flush()

    striker = TrackedPlayer(
        player_api_id=1001,
        player_name="Alfie Striker",
        position="Attacker",
        nationality="England",
        age=19,
        team_id=parent.id,
        status="on_loan",
        current_club_api_id=901,
        current_club_name="Rio FC",
        current_club_db_id=loan_club.id,
        data_depth="full_stats",
        is_active=True,
    )
    keeper = TrackedPlayer(
        player_api_id=1003,
        player_name="Charlie Gloves",
        position="Goalkeeper",
        nationality="Japan",
        age=18,
        team_id=parent.id,
        status="first_team",
        data_depth="full_stats",
        is_active=True,
    )
    ghost = TrackedPlayer(
        player_api_id=1005,
        player_name="Danny Ghost",
        position="Defender",
        age=20,
        team_id=parent.id,
        status="released",
        is_active=False,
    )
    db.session.add_all([striker, keeper, ghost])

    fixtures = [
        Fixture(
            fixture_id_api=5000 + i,
            season=2025,
            home_team_api_id=901,
            away_team_api_id=950 + i,
            date_utc=datetime(2025, 9, 1 + 7 * i),
        )
        for i in range(2)
    ]
    db.session.add_all(fixtures)
    db.session.flush()
    db.session.add_all(
        [
            FixturePlayerStats(
                fixture_id=fixtures[0].id,
                player_api_id=1001,
                team_api_id=901,
                minutes=90,
                goals=2,
                assists=1,
                rating=8.2,
            ),
            FixturePlayerStats(
                fixture_id=fixtures[1].id,
                player_api_id=1001,
                team_api_id=901,
                minutes=80,
                goals=1,
                assists=0,
                rating=7.0,
            ),
        ]
    )

    # A shadow player (worldwide) with current-season stats.
    shadow = PlayerShadow(
        player_api_id=2001,
        player_name="Shadow Prospect",
        position="Midfielder",
        nationality="Argentina",
        current_club_name="Boca",
        current_club_api_id=7001,
        is_active=True,
    )
    db.session.add(shadow)
    db.session.add(
        PlayerShadowStats(
            player_api_id=2001,
            team_api_id=7001,
            team_name="Boca",
            season=2025,
            appearances=6,
            goals=2,
            assists=3,
            minutes=520,
        )
    )
    db.session.commit()
    return {"parent": parent, "loan_club": loan_club}


def _make_user(email, **overrides):
    from src.auth import _ensure_user_account

    user = _ensure_user_account(email)
    for key, value in overrides.items():
        setattr(user, key, value)
    db.session.commit()
    return user


def _headers(email="scout@example.com"):
    from src.auth import issue_user_token

    _make_user(email)
    return {"Authorization": f"Bearer {issue_user_token(email)['token']}"}


def _admin_headers():
    from src.auth import issue_user_token

    token = issue_user_token("admin@example.com", role="admin")["token"]
    return {"Authorization": f"Bearer {token}", "X-API-Key": ADMIN_KEY}


class _FakeApiClient:
    """Profile + season-data source for mint/refresh; no injuries."""

    current_season_start_year = 2025

    def get_player_profile(self, player_id):
        return {
            "player": {
                "id": player_id,
                "name": "Minted Guy",
                "photo": "http://img/p.png",
                "position": "Attacker",
                "nationality": "Argentina",
                "birth": {"date": "2004-03-01"},
            }
        }

    def get_player_injuries(self, player_id, season=None):
        return []

    def _make_request(self, endpoint, params=None):
        if endpoint == "players":
            return {
                "response": [
                    {
                        "statistics": [
                            {
                                "team": {"id": 7001, "name": "Boca"},
                                "games": {"appearences": 5, "minutes": 400},
                                "goals": {"total": 3, "assists": 1},
                            },
                        ]
                    }
                ]
            }
        return {"response": []}


def _use_client(monkeypatch, client_obj):
    import src.routes.scout as scout_module

    monkeypatch.setattr(scout_module, "_get_api_client", lambda: client_obj)


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #


class TestAuth:
    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("get", "/api/scout/lists"),
            ("post", "/api/scout/lists"),
            ("patch", "/api/scout/lists/1"),
            ("delete", "/api/scout/lists/1"),
            ("post", "/api/scout/lists/1/follows"),
            ("get", "/api/scout/lists/1/resolve"),
            ("get", "/api/scout/player-search?q=abc"),
        ],
    )
    def test_user_endpoints_require_auth(self, client, method, path):
        assert getattr(client, method)(path).status_code == 401

    def test_admin_endpoints_require_admin(self, client):
        assert client.post("/api/admin/scout/shadow-refresh", json={}).status_code == 401
        assert client.post("/api/admin/scout/backfill-follow-lists", json={}, headers=_headers()).status_code == 401


# --------------------------------------------------------------------------- #
# Lists CRUD
# --------------------------------------------------------------------------- #


class TestListsCrud:
    def test_create_and_list(self, client, seeded):
        resp = client.post("/api/scout/lists", json={"name": "Wonderkids"}, headers=_headers())
        assert resp.status_code == 201
        created = resp.get_json()["list"]
        assert created["name"] == "Wonderkids"
        assert created["is_default"] is False
        assert created["follow_count"] == 0

        listing = client.get("/api/scout/lists", headers=_headers()).get_json()["lists"]
        assert [x["name"] for x in listing] == ["Wonderkids"]

    def test_duplicate_name_409(self, client, seeded):
        client.post("/api/scout/lists", json={"name": "Dupe"}, headers=_headers())
        resp = client.post("/api/scout/lists", json={"name": "Dupe"}, headers=_headers())
        assert resp.status_code == 409

    def test_blank_name_400(self, client, seeded):
        assert client.post("/api/scout/lists", json={"name": "   "}, headers=_headers()).status_code == 400
        assert client.post("/api/scout/lists", json={}, headers=_headers()).status_code == 400

    def test_list_cap_409(self, client, seeded, monkeypatch):
        import src.routes.scout as scout_module

        monkeypatch.setattr(scout_module, "MAX_FOLLOW_LISTS", 1)
        assert client.post("/api/scout/lists", json={"name": "One"}, headers=_headers()).status_code == 201
        resp = client.post("/api/scout/lists", json={"name": "Two"}, headers=_headers())
        assert resp.status_code == 409
        assert "list limit reached" in resp.get_json()["error"]

    def test_rename_and_toggle(self, client, seeded):
        lid = client.post("/api/scout/lists", json={"name": "Old"}, headers=_headers()).get_json()["list"]["id"]
        resp = client.patch(f"/api/scout/lists/{lid}", json={"name": "New", "is_active": False}, headers=_headers())
        assert resp.status_code == 200
        payload = resp.get_json()["list"]
        assert payload["name"] == "New"
        assert payload["is_active"] is False

    def test_owner_gate_on_other_users_list(self, client, seeded):
        lid = client.post("/api/scout/lists", json={"name": "Mine"}, headers=_headers("owner@example.com")).get_json()[
            "list"
        ]["id"]
        assert (
            client.patch(
                f"/api/scout/lists/{lid}", json={"name": "Hijack"}, headers=_headers("intruder@example.com")
            ).status_code
            == 404
        )
        assert client.delete(f"/api/scout/lists/{lid}", headers=_headers("intruder@example.com")).status_code == 404

    def test_default_list_not_deletable(self, client, seeded):
        # Adding a watchlist player mints the default list via the dual-write.
        client.post("/api/scout/watchlist", json={"player_api_id": 1001}, headers=_headers())
        default = FollowList.query.filter_by(is_default=True).one()
        resp = client.delete(f"/api/scout/lists/{default.id}", headers=_headers())
        assert resp.status_code == 400
        assert "default list" in resp.get_json()["error"]


# --------------------------------------------------------------------------- #
# Follows + selector validation
# --------------------------------------------------------------------------- #


class TestFollowValidation:
    def _list(self, client, email="scout@example.com"):
        return client.post("/api/scout/lists", json={"name": "L"}, headers=_headers(email)).get_json()["list"]["id"]

    def test_unknown_kind_400(self, client, seeded):
        lid = self._list(client)
        resp = client.post(
            f"/api/scout/lists/{lid}/follows", json={"kind": "wizard", "selector": {}}, headers=_headers()
        )
        assert resp.status_code == 400

    def test_player_unexpected_keys_400(self, client, seeded):
        lid = self._list(client)
        resp = client.post(
            f"/api/scout/lists/{lid}/follows",
            json={"kind": "player", "selector": {"player_api_id": 1001, "x": 1}},
            headers=_headers(),
        )
        assert resp.status_code == 400

    def test_program_follow_requires_public_approved_program(self, client, seeded):
        lid = self._list(client)
        league = FundingLeague(
            name="Follow Visibility League (Fixture)",
            country="Japan",
            region="Follow Visibility Region",
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
        program = ClubProgram(
            funding_league_id=league.id,
            name="Hidden Follow Program (Fixture)",
            legal_name="Hidden Follow Program Association (Fixture)",
            slug="hidden-follow-program-fixture",
            country="Japan",
            region="Follow Visibility Region",
            platform_status="pending",
        )
        db.session.add(program)
        db.session.commit()
        payload = {
            "kind": "academy_club",
            "selector": {"program_id": program.id},
            "notify_when_fundable": True,
        }
        assert client.post(f"/api/scout/lists/{lid}/follows", json=payload, headers=_headers()).status_code == 404

        program.platform_status = "approved"
        program.emergency_hidden = True
        db.session.commit()
        assert client.post(f"/api/scout/lists/{lid}/follows", json=payload, headers=_headers()).status_code == 404

        program.emergency_hidden = False
        db.session.commit()
        assert client.post(f"/api/scout/lists/{lid}/follows", json=payload, headers=_headers()).status_code == 201

    def test_geo_bad_match_and_too_many_countries_400(self, client, seeded):
        lid = self._list(client)
        assert (
            client.post(
                f"/api/scout/lists/{lid}/follows",
                json={"kind": "geo", "selector": {"countries": ["Brazil"], "match": "nope"}},
                headers=_headers(),
            ).status_code
            == 400
        )
        assert (
            client.post(
                f"/api/scout/lists/{lid}/follows",
                json={"kind": "geo", "selector": {"countries": [f"C{i}" for i in range(11)]}},
                headers=_headers(),
            ).status_code
            == 400
        )

    def test_query_unknown_scout_arg_400(self, client, seeded):
        lid = self._list(client)
        resp = client.post(
            f"/api/scout/lists/{lid}/follows",
            json={"kind": "query", "selector": {"scout_args": {"team": 1}}},
            headers=_headers(),
        )
        assert resp.status_code == 400

    def test_add_tracked_player_follow_and_dedup(self, client, seeded):
        lid = self._list(client)
        resp = client.post(
            f"/api/scout/lists/{lid}/follows",
            json={"kind": "player", "selector": {"player_api_id": 1001}},
            headers=_headers(),
        )
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["shadow_created"] is False
        assert body["follow"]["label"] == "Alfie Striker"
        # duplicate (kind, selector) rejected
        dup = client.post(
            f"/api/scout/lists/{lid}/follows",
            json={"kind": "player", "selector": {"player_api_id": 1001}},
            headers=_headers(),
        )
        assert dup.status_code == 409

    def test_follow_cap_409(self, client, seeded, monkeypatch):
        import src.routes.scout as scout_module

        monkeypatch.setattr(scout_module, "MAX_FOLLOWS_PER_LIST", 1)
        lid = self._list(client)
        assert (
            client.post(
                f"/api/scout/lists/{lid}/follows",
                json={"kind": "geo", "selector": {"countries": ["Brazil"]}},
                headers=_headers(),
            ).status_code
            == 201
        )
        resp = client.post(
            f"/api/scout/lists/{lid}/follows",
            json={"kind": "geo", "selector": {"countries": ["Spain"]}},
            headers=_headers(),
        )
        assert resp.status_code == 409

    def test_remove_follow(self, client, seeded):
        lid = self._list(client)
        fid = client.post(
            f"/api/scout/lists/{lid}/follows",
            json={"kind": "geo", "selector": {"countries": ["Brazil"]}},
            headers=_headers(),
        ).get_json()["follow"]["id"]
        assert client.delete(f"/api/scout/lists/{lid}/follows/{fid}", headers=_headers()).get_json() == {
            "removed": True
        }
        assert client.delete(f"/api/scout/lists/{lid}/follows/{fid}", headers=_headers()).get_json() == {
            "removed": False
        }


class TestEmbeddedFollows:
    """GET /scout/lists embeds each list's follows with read-time labels."""

    def test_get_lists_embeds_follows_with_labels(self, client, seeded):
        lid = client.post("/api/scout/lists", json={"name": "Board"}, headers=_headers()).get_json()["list"]["id"]
        for body in (
            {"kind": "player", "selector": {"player_api_id": 1001}},
            {"kind": "academy_club", "selector": {"team_id": seeded["parent"].id}},
            {"kind": "geo", "selector": {"countries": ["Brazil"], "match": "playing_in"}},
            {"kind": "geo", "selector": {"countries": ["Japan"], "match": "nationality"}},
            {"kind": "query", "selector": {"scout_args": {"position": "Attacker"}}},
        ):
            assert client.post(f"/api/scout/lists/{lid}/follows", json=body, headers=_headers()).status_code == 201

        lists = client.get("/api/scout/lists", headers=_headers()).get_json()["lists"]
        board = next(x for x in lists if x["id"] == lid)
        assert board["follow_count"] == 5
        follows = board["follows"]
        assert set(follows[0].keys()) == {
            "id",
            "kind",
            "selector",
            "label",
            "note",
            "notify_when_fundable",
            "created_at",
        }
        labels = {f["kind"]: f["label"] for f in follows if f["kind"] != "geo"}
        geo_labels = {f["label"] for f in follows if f["kind"] == "geo"}
        assert labels["player"] == "Alfie Striker"  # resolved player name
        assert labels["academy_club"] == "Club academy: Manchester United"
        assert labels["query"] == "Filter: Attacker"
        assert geo_labels == {"Playing in: Brazil", "Nationality: Japan"}

    def test_created_list_has_empty_follows(self, client, seeded):
        created = client.post("/api/scout/lists", json={"name": "Fresh"}, headers=_headers()).get_json()["list"]
        assert created["follows"] == []
        assert created["follow_count"] == 0

    def test_player_label_falls_back_to_shadow_name(self, client, seeded):
        lid = client.post("/api/scout/lists", json={"name": "WW"}, headers=_headers()).get_json()["list"]["id"]
        # 2001 is a shadow (no tracked row); its label resolves to the shadow name.
        client.post(
            f"/api/scout/lists/{lid}/follows",
            json={"kind": "player", "selector": {"player_api_id": 2001}},
            headers=_headers(),
        )
        lists = client.get("/api/scout/lists", headers=_headers()).get_json()["lists"]
        board = next(x for x in lists if x["id"] == lid)
        assert board["follows"][0]["label"] == "Shadow Prospect"


# --------------------------------------------------------------------------- #
# Shadow mint + search
# --------------------------------------------------------------------------- #


class TestShadow:
    def _list(self, client, email="scout@example.com"):
        return client.post("/api/scout/lists", json={"name": "L"}, headers=_headers(email)).get_json()["list"]["id"]

    def test_follow_untracked_mints_shadow(self, client, seeded, monkeypatch):
        _use_client(monkeypatch, _FakeApiClient())
        lid = self._list(client)
        resp = client.post(
            f"/api/scout/lists/{lid}/follows",
            json={"kind": "player", "selector": {"player_api_id": 4242}},
            headers=_headers(),
        )
        assert resp.status_code == 201
        assert resp.get_json()["shadow_created"] is True
        shadow = PlayerShadow.query.filter_by(player_api_id=4242).one()
        assert shadow.player_name == "Minted Guy"
        assert shadow.nationality == "Argentina"

    def test_shadow_follow_limit_403(self, client, seeded, monkeypatch):
        import src.routes.scout as scout_module

        _use_client(monkeypatch, _FakeApiClient())
        monkeypatch.setattr(scout_module, "SHADOW_FOLLOW_LIMIT", 1)
        lid = self._list(client)
        assert (
            client.post(
                f"/api/scout/lists/{lid}/follows",
                json={"kind": "player", "selector": {"player_api_id": 3001}},
                headers=_headers(),
            ).status_code
            == 201
        )
        resp = client.post(
            f"/api/scout/lists/{lid}/follows",
            json={"kind": "player", "selector": {"player_api_id": 3002}},
            headers=_headers(),
        )
        assert resp.status_code == 403
        assert "worldwide follow limit" in resp.get_json()["error"]

    def test_mint_offline_falls_back_to_seed(self, client, seeded, monkeypatch):
        class _Broken:
            def get_player_profile(self, pid):
                raise RuntimeError("no api")

        _use_client(monkeypatch, _Broken())
        lid = self._list(client)
        resp = client.post(
            f"/api/scout/lists/{lid}/follows",
            json={
                "kind": "player",
                "selector": {"player_api_id": 7777},
                "seed": {"name": "Seeded Name", "club_name": "Seed FC"},
            },
            headers=_headers(),
        )
        assert resp.status_code == 201
        shadow = PlayerShadow.query.filter_by(player_api_id=7777).one()
        assert shadow.player_name == "Seeded Name"
        assert shadow.current_club_name == "Seed FC"

    def test_player_search_found(self, client, seeded, monkeypatch):
        class _Found:
            def search_player_profiles_global(self, q):
                return [
                    {
                        "player": {"id": 2001, "name": "Shadow Prospect", "age": 20, "nationality": "Argentina"},
                        "statistics": [{"team": {"name": "Boca"}}],
                    },
                    {"player": {"id": 1001, "name": "Alfie Striker"}},
                ]

        _use_client(monkeypatch, _Found())
        resp = client.get("/api/scout/player-search?q=pro", headers=_headers())
        assert resp.status_code == 200
        results = {r["player_api_id"]: r for r in resp.get_json()["players"]}
        assert results[2001]["shadow"] is True and results[2001]["tracked"] is False
        assert results[1001]["tracked"] is True

    def test_player_search_stub_safe_on_error(self, client, seeded, monkeypatch):
        class _Raises:
            def search_player_profiles_global(self, q):
                raise RuntimeError("boom")

            def search_player_profiles(self, q, **kw):
                raise RuntimeError("boom")

        _use_client(monkeypatch, _Raises())
        resp = client.get("/api/scout/player-search?q=abc", headers=_headers())
        assert resp.status_code == 200
        assert resp.get_json()["players"] == []

    def test_shadow_refresh_endpoint(self, client, seeded, monkeypatch):
        _use_client(monkeypatch, _FakeApiClient())
        # Remove existing stats so we can observe the upsert repopulate them.
        PlayerShadowStats.query.delete()
        db.session.commit()
        resp = client.post("/api/admin/scout/shadow-refresh", json={"limit": 5}, headers=_admin_headers())
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["considered"] == 1
        assert data["stats_upserted"] == 1
        row = PlayerShadowStats.query.filter_by(player_api_id=2001, season=2025).one()
        assert row.appearances == 5 and row.goals == 3


# --------------------------------------------------------------------------- #
# Resolver
# --------------------------------------------------------------------------- #


class TestResolver:
    def _make_list(self, user):
        fl = FollowList(user_account_id=user.id, name="R")
        db.session.add(fl)
        db.session.flush()
        return fl

    def _add(self, fl, kind, selector):
        db.session.add(Follow(list_id=fl.id, kind=kind, selector=selector))
        db.session.commit()

    def test_player_tracked_and_shadow(self, app, seeded):
        from src.services.follow_resolver import resolve_list

        user = _make_user("r@example.com")
        fl = self._make_list(user)
        self._add(fl, "player", {"player_api_id": 1001})
        self._add(fl, "player", {"player_api_id": 2001})
        resolved = {r["player_api_id"]: r["source"] for r in resolve_list(fl)}
        assert resolved == {1001: "tracked", 2001: "shadow"}

    def test_academy_club(self, app, seeded):
        from src.services.follow_resolver import resolve_list

        user = _make_user("r@example.com")
        fl = self._make_list(user)
        self._add(fl, "academy_club", {"team_id": seeded["parent"].id})
        ids = {r["player_api_id"] for r in resolve_list(fl)}
        assert ids == {1001, 1003}  # both active academy players, ghost excluded

    def test_geo_playing_in_vs_nationality(self, app, seeded):
        from src.services.follow_resolver import resolve_list

        user = _make_user("r@example.com")
        # playing_in Brazil -> striker (current club Rio FC); keeper has no current club
        fl_playing = self._make_list(user)
        self._add(fl_playing, "geo", {"countries": ["Brazil"], "match": "playing_in"})
        assert {r["player_api_id"] for r in resolve_list(fl_playing)} == {1001}

        # nationality Japan -> keeper
        fl_nat = FollowList(user_account_id=user.id, name="Nat")
        db.session.add(fl_nat)
        db.session.flush()
        self._add(fl_nat, "geo", {"countries": ["Japan"], "match": "nationality"})
        assert {r["player_api_id"] for r in resolve_list(fl_nat)} == {1003}

    def test_query_kind(self, app, seeded):
        from src.services.follow_resolver import resolve_list

        user = _make_user("r@example.com")
        fl = self._make_list(user)
        self._add(fl, "query", {"scout_args": {"position": "Attacker"}})
        assert {r["player_api_id"] for r in resolve_list(fl)} == {1001}

    def test_union_dedup_and_cap(self, app, seeded):
        from src.services.follow_resolver import resolve_list

        user = _make_user("r@example.com")
        fl = self._make_list(user)
        # Two follows both resolving the striker -> deduped once.
        self._add(fl, "player", {"player_api_id": 1001})
        self._add(fl, "academy_club", {"team_id": seeded["parent"].id})
        full = resolve_list(fl)
        assert [r["player_api_id"] for r in full].count(1001) == 1
        assert len(resolve_list(fl, limit=1)) == 1


# --------------------------------------------------------------------------- #
# Dual-write mirror
# --------------------------------------------------------------------------- #


class TestDualWrite:
    def test_watchlist_add_mirrors_default_list(self, client, seeded):
        client.post("/api/scout/watchlist", json={"player_api_id": 1001}, headers=_headers())
        default = FollowList.query.filter_by(is_default=True).one()
        assert default.name == "My Watchlist"
        follow = default.follows.one()
        assert follow.kind == "player"
        assert follow.selector == {"player_api_id": 1001}

    def test_watchlist_remove_mirrors_default_list(self, client, seeded):
        client.post("/api/scout/watchlist", json={"player_api_id": 1001}, headers=_headers())
        client.delete("/api/scout/watchlist/1001", headers=_headers())
        default = FollowList.query.filter_by(is_default=True).one()
        assert default.follows.count() == 0


# --------------------------------------------------------------------------- #
# Backfill
# --------------------------------------------------------------------------- #


class TestBackfill:
    def _seed_watchlist_user(self, email, player_api_id=1001, note="keep", snapshot=None):
        user = _make_user(email)
        db.session.add(
            ScoutWatchlistEntry(user_account_id=user.id, player_api_id=player_api_id, note=note, last_snapshot=snapshot)
        )
        db.session.commit()
        return user

    def test_dry_run_creates_nothing(self, client, seeded):
        self._seed_watchlist_user("wl@example.com")
        resp = client.post("/api/admin/scout/backfill-follow-lists", json={"dry_run": True}, headers=_admin_headers())
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["users_processed"] == 1 and data["lists_created"] == 1 and data["follows_created"] == 1
        assert FollowList.query.count() == 0  # rolled back

    def test_real_run_and_idempotent(self, client, seeded):
        snap = json.dumps(
            {"appearances": 2, "goals": 1, "assists": 0, "minutes_played": 90, "status": "on_loan", "absences": 0}
        )
        self._seed_watchlist_user("wl@example.com", snapshot=snap)
        first = client.post("/api/admin/scout/backfill-follow-lists", json={"dry_run": False}, headers=_admin_headers())
        assert first.get_json()["lists_created"] == 1
        assert FollowList.query.filter_by(is_default=True).count() == 1
        assert Follow.query.count() == 1
        snapshot = FollowPlayerSnapshot.query.one()
        assert json.loads(snapshot.last_snapshot)["goals"] == 1
        assert snapshot.note == "keep"

        # Re-running skips users that already have a default list.
        second = client.post(
            "/api/admin/scout/backfill-follow-lists", json={"dry_run": False}, headers=_admin_headers()
        )
        assert second.get_json()["users_processed"] == 0
        assert FollowList.query.count() == 1

    def test_cursor_pages(self, client, seeded):
        self._seed_watchlist_user("a@example.com")
        self._seed_watchlist_user("b@example.com", player_api_id=1003)
        resp = client.post(
            "/api/admin/scout/backfill-follow-lists", json={"dry_run": False, "limit": 1}, headers=_admin_headers()
        )
        data = resp.get_json()
        assert data["users_processed"] == 1
        assert data["next_cursor"] is not None
        resp2 = client.post(
            "/api/admin/scout/backfill-follow-lists",
            json={"dry_run": False, "limit": 1, "cursor": data["next_cursor"]},
            headers=_admin_headers(),
        )
        assert resp2.get_json()["users_processed"] == 1


# --------------------------------------------------------------------------- #
# Digest generalization + regression
# --------------------------------------------------------------------------- #


class TestDigest:
    def _admin_send(self, client, body):
        return client.post("/api/scout/admin/send-digests", json=body, headers=_admin_headers())

    def test_watchlist_only_user_unchanged(self, client, seeded, monkeypatch):
        _use_client(monkeypatch, _FakeApiClient())
        user = _make_user("wl@example.com")
        # Seed the watchlist entry directly (no dual-write) so this user has NO list.
        db.session.add(ScoutWatchlistEntry(user_account_id=user.id, player_api_id=1001))
        db.session.commit()

        resp = self._admin_send(client, {"dry_run": True})
        preview = resp.get_json()["previews"][0]
        assert "group-label" not in preview["html"]  # legacy flat layout
        assert "Alfie Striker" in preview["html"]
        assert "Added to your watchlist" in preview["html"]

    def test_list_user_gets_sections_and_shadow_card(self, client, seeded, monkeypatch):
        _use_client(monkeypatch, _FakeApiClient())
        user = _make_user("list@example.com")
        fl = FollowList(user_account_id=user.id, name="Prospects", is_active=True)
        db.session.add(fl)
        db.session.flush()
        db.session.add_all(
            [
                Follow(list_id=fl.id, kind="player", selector={"player_api_id": 1001}),
                Follow(list_id=fl.id, kind="player", selector={"player_api_id": 2001}),
            ]
        )
        db.session.commit()

        resp = self._admin_send(client, {"dry_run": True})
        preview = resp.get_json()["previews"][0]
        assert preview["email"] == "list@example.com"
        assert "group-label" in preview["html"]
        assert "Prospects" in preview["html"]
        assert "Shadow Prospect" in preview["html"]
        assert "Now tracking worldwide" in preview["html"]  # shadow first-time card

    def test_real_send_persists_follow_snapshots(self, client, seeded, monkeypatch):
        _use_client(monkeypatch, _FakeApiClient())
        sends = []
        from src.services.email_service import email_service

        monkeypatch.setattr(
            email_service,
            "send_email",
            lambda **kwargs: (
                sends.append(kwargs)
                or SimpleNamespace(success=True, message_id="x", provider="f", http_status=200, error=None)
            ),
        )
        user = _make_user("list@example.com")
        fl = FollowList(user_account_id=user.id, name="Prospects", is_active=True)
        db.session.add(fl)
        db.session.flush()
        db.session.add(Follow(list_id=fl.id, kind="player", selector={"player_api_id": 2001}))
        db.session.commit()

        resp = self._admin_send(client, {"dry_run": False})
        assert resp.get_json()["sent"] == 1
        assert len(sends) == 1
        snap = FollowPlayerSnapshot.query.filter_by(user_account_id=user.id, player_api_id=2001).one()
        stored = json.loads(snap.last_snapshot)
        assert stored["goals"] == 2 and stored["appearances"] == 6  # from PlayerShadowStats
        assert snap.last_digest_at is not None

    def test_mirror_path_watchlist_is_byte_identical_to_legacy(self, client, seeded, monkeypatch):
        """The KEY regression: adding via POST /scout/watchlist mints a default
        list under the hood, but that default list must NOT flip the user onto
        the grouped/ASC/truncated list path. The email must be byte-identical to
        a user with the same watchlist and no lists at all."""
        _use_client(monkeypatch, _FakeApiClient())
        # User A: real mirror path (POST creates a default list twin).
        client.post("/api/scout/watchlist", json={"player_api_id": 1001}, headers=_headers("a@example.com"))
        client.post("/api/scout/watchlist", json={"player_api_id": 1003}, headers=_headers("a@example.com"))
        assert FollowList.query.filter_by(is_default=True).count() == 1  # mirror created it
        # User B: identical watchlist seeded directly — NO list.
        user_b = _make_user("b@example.com")
        db.session.add_all(
            [
                ScoutWatchlistEntry(user_account_id=user_b.id, player_api_id=1001),
                ScoutWatchlistEntry(user_account_id=user_b.id, player_api_id=1003),
            ]
        )
        db.session.commit()

        previews = {p["email"]: p for p in self._admin_send(client, {"dry_run": True}).get_json()["previews"]}
        a_html = previews["a@example.com"]["html"]
        b_html = previews["b@example.com"]["html"]
        assert "group-label" not in a_html  # flat layout, not grouped
        assert a_html == b_html  # default-list twin does not change the digest
        assert a_html.count('class="player-card"') == 2  # all watchlist players present
        assert a_html.index("Charlie Gloves") < a_html.index("Alfie Striker")  # DESC order preserved

    def test_watchlist_plus_custom_list_dedup(self, client, seeded, monkeypatch):
        """Flat watchlist section + grouped custom-list section, with the
        watchlist winning dedup (a watched player never repeats in a group)."""
        _use_client(monkeypatch, _FakeApiClient())
        hdr = _headers("mix@example.com")
        client.post("/api/scout/watchlist", json={"player_api_id": 1001}, headers=hdr)
        lid = client.post("/api/scout/lists", json={"name": "Extras"}, headers=hdr).get_json()["list"]["id"]
        client.post(
            f"/api/scout/lists/{lid}/follows", json={"kind": "player", "selector": {"player_api_id": 1003}}, headers=hdr
        )
        client.post(
            f"/api/scout/lists/{lid}/follows", json={"kind": "player", "selector": {"player_api_id": 1001}}, headers=hdr
        )

        html = self._admin_send(client, {"dry_run": True}).get_json()["previews"][0]["html"]
        assert "group-label" in html and "Extras" in html
        assert html.count("Alfie Striker") == 1  # watchlist wins — not duplicated in the group
        assert "Charlie Gloves" in html  # 1003 delivered via the custom list

    def test_default_list_only_fallback_when_watchlist_empty(self, client, seeded, monkeypatch):
        """Edge case: a user who cleared their watchlist but whose mirror follows
        remain still gets the default list's content (default routes as fallback)."""
        _use_client(monkeypatch, _FakeApiClient())
        hdr = _headers("cleared@example.com")
        client.post("/api/scout/watchlist", json={"player_api_id": 1001}, headers=hdr)
        # Simulate a desync: clear the watchlist entry directly (bypassing the
        # remove-mirror) so the default list follow survives.
        ScoutWatchlistEntry.query.delete()
        db.session.commit()
        default = FollowList.query.filter_by(is_default=True).one()
        assert default.follows.count() == 1  # mirror follow survived

        previews = self._admin_send(client, {"dry_run": True}).get_json()["previews"]
        assert len(previews) == 1
        html = previews[0]["html"]
        assert "Alfie Striker" in html  # default-list content still delivered
        assert "My Watchlist" in html  # rendered as a group section


# --------------------------------------------------------------------------- #
# Mint churn guard
# --------------------------------------------------------------------------- #


class _CountingProfileClient:
    def __init__(self, name="Refreshed"):
        self.calls = 0
        self._name = name

    def get_player_profile(self, player_id):
        self.calls += 1
        return {"player": {"id": player_id, "name": self._name}}


class TestMintChurnGuard:
    def test_existing_fresh_shadow_skips_profile_fetch(self, app, seeded):
        from datetime import UTC, datetime

        from src.services import player_shadow_service as svc

        shadow = PlayerShadow.query.filter_by(player_api_id=2001).one()
        shadow.last_profile_sync_at = datetime.now(UTC)
        db.session.commit()
        client = _CountingProfileClient()
        result = svc.mint_shadow(2001, api_client=client)
        assert client.calls == 0  # fresh -> zero upstream calls
        assert result.player_api_id == 2001

    def test_existing_stale_shadow_refetches_profile(self, app, seeded):
        from datetime import UTC, datetime, timedelta

        from src.services import player_shadow_service as svc

        shadow = PlayerShadow.query.filter_by(player_api_id=2001).one()
        shadow.last_profile_sync_at = datetime.now(UTC) - timedelta(days=30)
        db.session.commit()
        client = _CountingProfileClient(name="Refreshed")
        svc.mint_shadow(2001, api_client=client)
        assert client.calls == 1
        assert PlayerShadow.query.filter_by(player_api_id=2001).one().player_name == "Refreshed"


# --------------------------------------------------------------------------- #
# Profile / season-stats shadow fallbacks
# --------------------------------------------------------------------------- #


class TestProfileFallback:
    def test_profile_shadow_fill(self, client, seeded):
        resp = client.get("/api/players/2001/profile")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["shadow"] is True
        assert data["name"] == "Shadow Prospect"
        assert data["position"] == "Midfielder"
        assert data["loan_team_name"] == "Boca"

    def test_profile_unknown_player_unchanged(self, client, seeded):
        data = client.get("/api/players/999999/profile").get_json()
        assert "shadow" not in data
        assert data["name"] == "Player #999999"

    def test_season_stats_shadow_branch(self, client, seeded):
        resp = client.get("/api/players/2001/season-stats")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["source"] == "shadow"
        assert data["stats_coverage"] == "limited"
        assert data["appearances"] == 6 and data["goals"] == 2 and data["assists"] == 3
        assert data["clubs"][0]["team_name"] == "Boca"
        assert data["clubs"][0]["team_logo"] is None

    def test_season_stats_unknown_player_empty(self, client, seeded):
        data = client.get("/api/players/999999/season-stats").get_json()
        assert data["source"] == "none"
        assert data["clubs"] == []

    def test_season_stats_uses_latest_season(self, client, seeded):
        # Seed has 2001 @ season 2025 (apps=6); add a newer 2026 row and assert
        # the endpoint reports the LATEST season, immune to wall-clock drift.
        db.session.add(
            PlayerShadowStats(
                player_api_id=2001,
                team_api_id=7001,
                team_name="Boca",
                season=2026,
                appearances=9,
                goals=4,
                assists=2,
                minutes=700,
            )
        )
        db.session.commit()
        data = client.get("/api/players/2001/season-stats").get_json()
        assert data["appearances"] == 9 and data["goals"] == 4  # 2026, not 2025
