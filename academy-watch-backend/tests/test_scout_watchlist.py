"""Tests for scout watchlist, CSV export, and digest endpoints in src/routes/scout.py."""

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from flask import Flask
from src.models.league import League, PlayerStatsCache, Team, UserAccount, db
from src.models.scout_watchlist import ScoutWatchlistEntry
from src.models.tracked_player import TrackedPlayer
from src.models.weekly import Fixture, FixturePlayerStats

CSV_HEADER_LINE = (
    "player_id,name,age,position,nationality,status,parent_club,current_club,"
    "appearances,goals,assists,minutes,avg_rating,goal_contributions,contributions_per90"
)


@pytest.fixture
def watchlist_app():
    """Minimal Flask app with scout blueprint + templates for digest rendering."""
    os.environ.setdefault("SKIP_API_HANDSHAKE", "1")
    os.environ.setdefault("API_USE_STUB_DATA", "true")

    from src.routes.scout import scout_bp

    template_dir = Path(__file__).resolve().parent.parent / "src" / "templates"
    app = Flask(__name__, template_folder=str(template_dir))
    app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret-key",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        RATELIMIT_ENABLED=False,
    )

    db.init_app(app)
    app.register_blueprint(scout_bp, url_prefix="/api")

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(watchlist_app):
    return watchlist_app.test_client()


@pytest.fixture
def seeded(watchlist_app):
    """Seed teams, tracked players (full + cache coverage + inactive), and stats."""
    league = League(league_id=39, name="Premier League", country="England", season=2025, is_european_top_league=True)
    db.session.add(league)
    db.session.flush()

    parent = Team(
        team_id=33, name="Manchester United", country="England", season=2025, league_id=league.id, is_active=True
    )
    loan_club = Team(team_id=901, name="Loan FC", country="Brazil", season=2025, league_id=league.id, is_active=True)
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
        current_club_name="Loan FC",
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
        status="on_loan",
        current_club_api_id=902,
        current_club_name="Far FC",
        data_depth="events_only",
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
            PlayerStatsCache(
                player_api_id=1003,
                team_api_id=902,
                season=2025,
                appearances=12,
                goals=0,
                assists=1,
                minutes_played=1080,
                saves=41,
            ),
        ]
    )
    db.session.commit()


def _make_user(email, **overrides):
    from src.auth import _ensure_user_account

    user = _ensure_user_account(email)
    for key, value in overrides.items():
        setattr(user, key, value)
    db.session.commit()
    return user


def _headers(email="scout@example.com"):
    from src.auth import issue_user_token

    token = issue_user_token(email)["token"]
    return {"Authorization": f"Bearer {token}"}


def _admin_headers():
    from src.auth import issue_user_token

    token = issue_user_token("admin@example.com", role="admin")["token"]
    return {"Authorization": f"Bearer {token}", "X-API-Key": "test-admin-key"}


class _FakeApiClient:
    """Two season absences for player 1001, none for anyone else."""

    def get_player_injuries(self, player_api_id, season=None):
        if player_api_id != 1001:
            return []
        return [{"player": {"id": 1001, "reason": "Knee Injury"}}, {"player": {"id": 1001, "reason": "Knock"}}]


class TestAuthRequired:
    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("get", "/api/scout/watchlist"),
            ("post", "/api/scout/watchlist"),
            ("delete", "/api/scout/watchlist/1001"),
            ("patch", "/api/scout/watchlist/1001"),
            ("get", "/api/scout/watchlist/ids"),
            ("patch", "/api/scout/watchlist/settings"),
            ("get", "/api/scout/export.csv"),
        ],
    )
    def test_user_endpoints_require_auth(self, client, method, path):
        resp = getattr(client, method)(path)
        assert resp.status_code == 401

    def test_admin_digest_endpoint_requires_admin_auth(self, client):
        with patch.dict(os.environ, {"ADMIN_API_KEY": "test-admin-key"}):
            assert client.post("/api/scout/admin/send-digests", json={}).status_code == 401
            # A plain user token must not pass the admin gate
            resp = client.post("/api/scout/admin/send-digests", json={}, headers=_headers())
            assert resp.status_code == 401


class TestAddAndRemove:
    def test_add_returns_201_with_enriched_player(self, client, seeded):
        resp = client.post("/api/scout/watchlist", json={"player_api_id": 1001}, headers=_headers())
        assert resp.status_code == 201
        entry = resp.get_json()["entry"]
        assert entry["player_api_id"] == 1001
        assert entry["note"] is None
        assert entry["created_at"]
        assert entry["player"]["goals"] == 3
        assert entry["player"]["appearances"] == 2
        assert len(entry["player"]["recent_form"]) == 2

    def test_re_add_is_idempotent_200(self, client, seeded):
        headers = _headers()
        assert client.post("/api/scout/watchlist", json={"player_api_id": 1001}, headers=headers).status_code == 201
        resp = client.post("/api/scout/watchlist", json={"player_api_id": 1001}, headers=headers)
        assert resp.status_code == 200
        assert resp.get_json()["entry"]["player_api_id"] == 1001
        assert ScoutWatchlistEntry.query.count() == 1

    def test_add_unknown_or_inactive_player_404(self, client, seeded):
        assert client.post("/api/scout/watchlist", json={"player_api_id": 99999}, headers=_headers()).status_code == 404
        assert client.post("/api/scout/watchlist", json={"player_api_id": 1005}, headers=_headers()).status_code == 404

    def test_add_missing_or_invalid_id_400(self, client, seeded):
        headers = _headers()
        assert client.post("/api/scout/watchlist", json={}, headers=headers).status_code == 400
        assert client.post("/api/scout/watchlist", json={"player_api_id": "abc"}, headers=headers).status_code == 400
        assert client.post("/api/scout/watchlist", json={"player_api_id": -3}, headers=headers).status_code == 400

    def test_watchlist_limit_409(self, client, seeded, monkeypatch):
        import src.routes.scout as scout_module

        monkeypatch.setattr(scout_module, "WATCHLIST_LIMIT", 1)
        headers = _headers()
        assert client.post("/api/scout/watchlist", json={"player_api_id": 1001}, headers=headers).status_code == 201
        resp = client.post("/api/scout/watchlist", json={"player_api_id": 1003}, headers=headers)
        assert resp.status_code == 409
        assert "watchlist limit reached" in resp.get_json()["error"]

    def test_delete_is_idempotent(self, client, seeded):
        headers = _headers()
        client.post("/api/scout/watchlist", json={"player_api_id": 1001}, headers=headers)
        resp = client.delete("/api/scout/watchlist/1001", headers=headers)
        assert resp.status_code == 200
        assert resp.get_json() == {"removed": True}
        resp = client.delete("/api/scout/watchlist/1001", headers=headers)
        assert resp.status_code == 200
        assert resp.get_json() == {"removed": False}


class TestNote:
    def test_set_note_runs_through_bleach(self, client, seeded, monkeypatch):
        import src.routes.scout as scout_module

        calls = {}

        def fake_clean(value, *args, **kwargs):
            calls["value"] = value
            calls["strip"] = kwargs.get("strip")
            return value.replace("<b>", "").replace("</b>", "")

        monkeypatch.setattr(scout_module.bleach, "clean", fake_clean)
        headers = _headers()
        client.post("/api/scout/watchlist", json={"player_api_id": 1001}, headers=headers)
        resp = client.patch("/api/scout/watchlist/1001", json={"note": "<b>One to watch</b>"}, headers=headers)
        assert resp.status_code == 200
        assert resp.get_json()["entry"]["note"] == "One to watch"
        assert calls["strip"] is True

    def test_note_too_long_after_cleaning_400(self, client, seeded):
        headers = _headers()
        client.post("/api/scout/watchlist", json={"player_api_id": 1001}, headers=headers)
        resp = client.patch("/api/scout/watchlist/1001", json={"note": "x" * 2001}, headers=headers)
        assert resp.status_code == 400

    def test_whitespace_note_clears_to_null(self, client, seeded):
        headers = _headers()
        client.post("/api/scout/watchlist", json={"player_api_id": 1001}, headers=headers)
        client.patch("/api/scout/watchlist/1001", json={"note": "keep an eye"}, headers=headers)
        resp = client.patch("/api/scout/watchlist/1001", json={"note": "   "}, headers=headers)
        assert resp.status_code == 200
        assert resp.get_json()["entry"]["note"] is None
        assert ScoutWatchlistEntry.query.one().note is None

    def test_note_for_player_not_on_list_404(self, client, seeded):
        resp = client.patch("/api/scout/watchlist/1001", json={"note": "hi"}, headers=_headers())
        assert resp.status_code == 404


class TestIdsAndSettings:
    def test_ids_endpoint_returns_watched_ids(self, client, seeded):
        headers = _headers()
        client.post("/api/scout/watchlist", json={"player_api_id": 1001}, headers=headers)
        client.post("/api/scout/watchlist", json={"player_api_id": 1003}, headers=headers)
        resp = client.get("/api/scout/watchlist/ids", headers=headers)
        assert resp.status_code == 200
        assert sorted(resp.get_json()["player_ids"]) == [1001, 1003]

    def test_settings_toggle_persists(self, client, seeded):
        _make_user("scout@example.com")
        headers = _headers()
        resp = client.patch("/api/scout/watchlist/settings", json={"digest_opt_in": False}, headers=headers)
        assert resp.status_code == 200
        assert resp.get_json() == {"digest_opt_in": False}
        user = UserAccount.query.filter_by(email="scout@example.com").one()
        assert user.scout_digest_opt_in is False
        assert client.get("/api/scout/watchlist", headers=headers).get_json()["digest_opt_in"] is False

    def test_settings_rejects_non_boolean(self, client, seeded):
        headers = _headers()
        assert (
            client.patch("/api/scout/watchlist/settings", json={"digest_opt_in": "yes"}, headers=headers).status_code
            == 400
        )
        assert client.patch("/api/scout/watchlist/settings", json={}, headers=headers).status_code == 400


class TestGetWatchlist:
    def test_entries_enriched_ordered_with_null_for_inactive(self, client, seeded):
        user = _make_user("scout@example.com")
        db.session.add_all(
            [
                ScoutWatchlistEntry(
                    user_account_id=user.id, player_api_id=1001, created_at=datetime(2026, 1, 1, tzinfo=UTC)
                ),
                ScoutWatchlistEntry(
                    user_account_id=user.id, player_api_id=1005, created_at=datetime(2026, 2, 1, tzinfo=UTC)
                ),
                ScoutWatchlistEntry(
                    user_account_id=user.id, player_api_id=1003, created_at=datetime(2026, 3, 1, tzinfo=UTC)
                ),
            ]
        )
        db.session.commit()

        resp = client.get("/api/scout/watchlist", headers=_headers())
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["digest_opt_in"] is True
        assert data["scout_tier"] == "free"
        assert [e["player_api_id"] for e in data["entries"]] == [1003, 1005, 1001]

        keeper, ghost, striker = data["entries"]
        assert keeper["player"]["appearances"] == 12
        assert ghost["player"] is None  # TrackedPlayer deactivated
        assert striker["player"]["goals"] == 3
        assert striker["player"]["minutes_played"] == 170
        assert striker["player"]["avg_rating"] == pytest.approx(7.6)
        assert len(striker["player"]["recent_form"]) == 2

    def test_other_users_entries_are_not_visible(self, client, seeded):
        other = _make_user("other@example.com")
        db.session.add(ScoutWatchlistEntry(user_account_id=other.id, player_api_id=1001))
        db.session.commit()
        resp = client.get("/api/scout/watchlist", headers=_headers("scout@example.com"))
        assert resp.get_json()["entries"] == []


class TestCsvExport:
    def test_export_header_and_data_row(self, client, seeded):
        resp = client.get("/api/scout/export.csv?sort=goals", headers=_headers())
        assert resp.status_code == 200
        assert resp.mimetype == "text/csv"
        assert 'filename="academy-watch-scout-export.csv"' in resp.headers["Content-Disposition"]

        lines = resp.data.decode().splitlines()
        assert lines[0] == CSV_HEADER_LINE
        assert lines[1] == (
            "1001,Alfie Striker,19,Attacker,England,on_loan,Manchester United,Loan FC,2,3,1,170,7.6,4,2.12"
        )
        assert len(lines) == 3  # header + striker + keeper

    def test_export_ids_subset_ignores_filters(self, client, seeded):
        resp = client.get("/api/scout/export.csv?ids=1003&position=Attacker", headers=_headers())
        lines = resp.data.decode().splitlines()
        assert len(lines) == 2
        assert lines[1].startswith("1003,Charlie Gloves,")

    def test_export_invalid_ids_400(self, client, seeded):
        assert client.get("/api/scout/export.csv?ids=a,b", headers=_headers()).status_code == 400


@pytest.fixture
def digest_seed(watchlist_app, seeded):
    """Two watchlist users: one with snapshots that force deltas, one opted out."""
    keeper = TrackedPlayer.query.filter_by(player_api_id=1003).one()
    keeper.status = "first_team"  # snapshot below says on_loan -> promotion headline

    user = _make_user("scout@example.com")
    opted_out = _make_user("optout@example.com", scout_digest_opt_in=False)

    striker_snapshot = json.dumps(
        {
            "appearances": 1,
            "goals": 1,
            "assists": 1,
            "minutes_played": 90,
            "status": "on_loan",
            "absences": 0,
            "taken_at": "2026-05-01T00:00:00+00:00",
        }
    )
    keeper_snapshot = json.dumps(
        {
            "appearances": 12,
            "goals": 0,
            "assists": 1,
            "minutes_played": 1080,
            "status": "on_loan",
            "absences": 0,
            "taken_at": "2026-05-01T00:00:00+00:00",
        }
    )
    db.session.add_all(
        [
            ScoutWatchlistEntry(user_account_id=user.id, player_api_id=1001, last_snapshot=striker_snapshot),
            ScoutWatchlistEntry(user_account_id=user.id, player_api_id=1003, last_snapshot=keeper_snapshot),
            ScoutWatchlistEntry(user_account_id=opted_out.id, player_api_id=1001),
        ]
    )
    db.session.commit()
    return {"user": user, "opted_out": opted_out}


class TestDigests:
    def _post(self, client, body):
        with patch.dict(os.environ, {"ADMIN_API_KEY": "test-admin-key"}):
            return client.post("/api/scout/admin/send-digests", json=body, headers=_admin_headers())

    def test_dry_run_renders_deltas_without_mutating(self, client, digest_seed, monkeypatch):
        import src.routes.scout as scout_module

        monkeypatch.setattr(scout_module, "_get_api_client", lambda: _FakeApiClient())

        sends = []
        from src.services.email_service import email_service

        monkeypatch.setattr(email_service, "send_email", lambda **kwargs: sends.append(kwargs))

        resp = self._post(client, {"dry_run": True})
        assert resp.status_code == 200
        data = resp.get_json()
        # Opted-out users are excluded by the SQL eligibility filter, so they
        # never consume a slot and aren't counted as skipped.
        assert data["users_considered"] == 1
        assert data["sent"] == 0
        assert data["skipped"] == 0
        assert data["next_cursor"] is None
        assert sends == []

        assert len(data["previews"]) == 1
        preview = data["previews"][0]
        assert preview["email"] == "scout@example.com"
        assert preview["players"] == 2
        assert "Scout Digest" in preview["subject"]
        assert "+2 goals" in preview["html"]
        assert "Promoted to first team" in preview["html"]
        assert "2 new absences" in preview["html"]

        # Snapshots untouched in dry runs
        for entry in ScoutWatchlistEntry.query.all():
            assert entry.last_digest_at is None
        striker_entry = ScoutWatchlistEntry.query.filter_by(
            user_account_id=digest_seed["user"].id, player_api_id=1001
        ).one()
        assert json.loads(striker_entry.last_snapshot)["goals"] == 1

    def test_real_send_updates_snapshots_and_skips_opted_out(self, client, digest_seed, monkeypatch):
        import src.routes.scout as scout_module

        monkeypatch.setattr(scout_module, "_get_api_client", lambda: _FakeApiClient())

        sends = []

        def fake_send_email(**kwargs):
            sends.append(kwargs)
            return SimpleNamespace(success=True, message_id="fake-id", provider="fake", http_status=200, error=None)

        from src.services.email_service import email_service

        monkeypatch.setattr(email_service, "send_email", fake_send_email)

        resp = self._post(client, {"dry_run": False})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["sent"] == 1
        assert data["skipped"] == 0
        assert data["users_considered"] == 1  # opted-out user filtered in SQL
        assert data["next_cursor"] is None
        assert "html" not in data["previews"][0]

        assert len(sends) == 1
        assert sends[0]["to"] == "scout@example.com"
        assert "Scout Digest" in sends[0]["subject"]
        assert "+2 goals" in sends[0]["html"]

        striker_entry = ScoutWatchlistEntry.query.filter_by(
            user_account_id=digest_seed["user"].id, player_api_id=1001
        ).one()
        snapshot = json.loads(striker_entry.last_snapshot)
        assert snapshot["goals"] == 3
        assert snapshot["minutes_played"] == 170
        assert snapshot["absences"] == 2
        assert striker_entry.last_digest_at is not None

        opted_out_entry = ScoutWatchlistEntry.query.filter_by(user_account_id=digest_seed["opted_out"].id).one()
        assert opted_out_entry.last_snapshot is None
        assert opted_out_entry.last_digest_at is None

    def test_digest_cursor_pages_through_all_eligible_users(self, client, digest_seed, monkeypatch):
        """The cursor must walk the full population — the original selection
        re-picked the same first `limit` users on every run."""
        import src.routes.scout as scout_module

        monkeypatch.setattr(scout_module, "_get_api_client", lambda: _FakeApiClient())
        second = _make_user("scout2@example.com")
        db.session.add(ScoutWatchlistEntry(user_account_id=second.id, player_api_id=1003))
        db.session.commit()

        resp = self._post(client, {"dry_run": True, "limit": 1})
        data = resp.get_json()
        assert data["users_considered"] == 1
        emails = [p["email"] for p in data["previews"]]
        assert emails == ["scout@example.com"]
        assert data["next_cursor"] == digest_seed["user"].id

        resp = self._post(client, {"dry_run": True, "limit": 1, "cursor": data["next_cursor"]})
        data2 = resp.get_json()
        assert [p["email"] for p in data2["previews"]] == ["scout2@example.com"]

        resp = self._post(client, {"dry_run": True, "limit": 50, "cursor": second.id})
        assert resp.get_json()["users_considered"] == 0

    def test_digest_rejects_invalid_cursor(self, client, digest_seed):
        assert self._post(client, {"cursor": -1}).status_code == 400
        assert self._post(client, {"cursor": "abc"}).status_code == 400


class TestCsvInjectionEscaping:
    def test_formula_prefixed_names_are_neutralised(self, client, seeded, watchlist_app):
        from src.models.league import Team

        team = Team.query.first()
        db.session.add(
            TrackedPlayer(
                player_api_id=4242,
                player_name="=2+5",
                position="Attacker",
                nationality="+SUM(A1:A9)",
                age=19,
                team_id=team.id,
                status="academy",
                is_active=True,
            )
        )
        db.session.commit()

        _make_user("scout@example.com")
        resp = client.get("/api/scout/export.csv?ids=4242", headers=_headers())
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        data_row = body.splitlines()[1]
        assert "'=2+5" in data_row
        assert "'+SUM(A1:A9)" in data_row
        assert ",=2+5" not in data_row
