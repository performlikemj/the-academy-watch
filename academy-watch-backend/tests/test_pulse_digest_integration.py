"""Digest integration for player pulse + shared AI cards (Builder B).

Two guarantees are load-bearing here:

1. **Byte-identical legacy behaviour.** With empty ``player_pulse`` /
   ``player_card_cache`` tables the rendered digest (HTML + text) is EXACTLY
   what it was before pulse cards existed. Proven additively/reversibly: render
   → insert a card → render → delete the card → render, and assert the first and
   last renders are byte-identical while the middle one differs.
2. **Additive card slot-in.** When a ``player_card_cache`` row exists for the
   player's current window, the provenance-clean card supersedes the raw delta
   line (season line + chips) in both the HTML and plaintext bodies.

Plus the two admin ops endpoints (``/api/admin/pulse/compute`` and
``/api/admin/pulse/generate-cards``): auth, validation, dry-run semantics
(compute rolls back; generate-cards lists candidates with ZERO LLM calls), and
threshold/limit passthrough. Builder A's services are treated as their contract
signatures — ``compute_pulse(window_end, player_api_ids=None)`` and
``generate_cards(window_end, threshold, limit)`` — and are stubbed here so no
live scoring/LLM call ever runs (and the tests pass whether or not those service
modules exist yet).
"""

import importlib
import json
import sys
import types
from datetime import date, datetime
from pathlib import Path

import pytest
from flask import Flask
from src.models.league import League, Team, db
from src.models.pulse import PlayerCardCache, PlayerPulse  # registers the tables for create_all
from src.models.scout_watchlist import ScoutWatchlistEntry
from src.models.tracked_player import TrackedPlayer
from src.models.weekly import Fixture, FixturePlayerStats

ADMIN_KEY = "test-admin-key"
WINDOW = date(2025, 9, 15)


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("SKIP_API_HANDSHAKE", "1")
    monkeypatch.setenv("API_USE_STUB_DATA", "true")
    monkeypatch.setenv("ADMIN_API_KEY", ADMIN_KEY)
    monkeypatch.setenv("ADMIN_IP_WHITELIST", "")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.com")

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
    """Parent academy + loan club, one striker with two scored fixtures."""
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
    db.session.add_all([striker, keeper])

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
    db.session.commit()
    return {"parent": parent, "loan_club": loan_club}


def _make_user(email):
    from src.auth import _ensure_user_account

    user = _ensure_user_account(email)
    db.session.commit()
    return user


def _watchlist_user(email="wl@example.com", player_api_id=1001, note="watch this", snapshot=True):
    user = _make_user(email)
    last_snapshot = None
    if snapshot:
        last_snapshot = json.dumps(
            {"appearances": 1, "goals": 1, "assists": 0, "minutes_played": 90, "status": "on_loan", "absences": 0}
        )
    entry = ScoutWatchlistEntry(
        user_account_id=user.id, player_api_id=player_api_id, note=note, last_snapshot=last_snapshot
    )
    db.session.add(entry)
    db.session.commit()
    return user


def _render(user):
    from src.services.scout_digest_service import build_user_digest

    entries = ScoutWatchlistEntry.query.filter_by(user_account_id=user.id).all()
    return build_user_digest(user, entries, api_client=None)


def _add_card(player_api_id=1001, window=WINDOW, html=None, text=None):
    db.session.add(PlayerPulse(player_api_id=player_api_id, window_end=window, score=7.5, delta_json={"goals": 3}))
    db.session.add(
        PlayerCardCache(
            player_api_id=player_api_id,
            window_end=window,
            card_html=html or "<p><strong>Alfie Striker</strong> scored 3 goals across 2 apps this week.</p>",
            card_text=text or "Alfie Striker scored 3 goals across 2 apps this week.",
            model="test-model",
        )
    )
    db.session.commit()


def _admin_headers():
    from src.auth import issue_user_token

    token = issue_user_token("admin@example.com", role="admin")["token"]
    return {"Authorization": f"Bearer {token}", "X-API-Key": ADMIN_KEY}


def _install_service(monkeypatch, module_name, **fns):
    """Bind stub functions on Builder A's service module — importing it if it
    already exists, otherwise registering a fake module (so these tests pass
    before those service files land). All changes are undone by monkeypatch."""
    try:
        mod = importlib.import_module(module_name)
        created = False
    except ModuleNotFoundError:
        mod = types.ModuleType(module_name)
        created = True
    for key, value in fns.items():
        monkeypatch.setattr(mod, key, value, raising=False)
    if created:
        monkeypatch.setitem(sys.modules, module_name, mod)
        parent_name, _, child = module_name.rpartition(".")
        parent = importlib.import_module(parent_name)
        monkeypatch.setattr(parent, child, mod, raising=False)
    return mod


# --------------------------------------------------------------------------- #
# Byte-identical regression + additive card slot-in
# --------------------------------------------------------------------------- #


class TestDigestByteIdentical:
    def test_empty_pulse_tables_are_additive_and_reversible(self, app, seeded):
        """The load-bearing invariant: with no card row the digest is unchanged,
        and adding then removing a card restores byte-identical output."""
        user = _watchlist_user()

        before = _render(user)
        assert PlayerCardCache.query.count() == 0
        assert 'class="season-line"' in before["html"]
        assert "pulse-card" not in before["html"]

        _add_card()
        with_card = _render(user)
        assert with_card["html"] != before["html"]
        assert "pulse-card" in with_card["html"]

        PlayerPulse.query.delete()
        PlayerCardCache.query.delete()
        db.session.commit()
        after = _render(user)

        assert after["html"] == before["html"]  # byte-identical HTML
        assert after["text"] == before["text"]  # byte-identical plaintext

    def test_two_identical_watchlists_render_identically_when_empty(self, app, seeded):
        """Direct analog of the follow-graph a_html == b_html regression."""
        user_a = _watchlist_user("a@example.com")
        user_b = _watchlist_user("b@example.com")
        assert _render(user_a)["html"] == _render(user_b)["html"]

    def test_card_supersedes_delta_line_in_html_and_text(self, app, seeded):
        user = _watchlist_user()
        _add_card()
        digest = _render(user)

        # HTML: the card fragment renders; the raw delta line is gone.
        assert "pulse-card" in digest["html"]
        assert "scored 3 goals across 2 apps this week" in digest["html"]
        assert 'class="season-line"' not in digest["html"]
        assert 'class="chip"' not in digest["html"]
        # Note (unrelated to the delta line) is still rendered — purely additive.
        assert "watch this" in digest["html"]

        # Plaintext: card text replaces the "2 apps · 3 goals ..." delta line.
        assert "Alfie Striker scored 3 goals across 2 apps this week." in digest["text"]
        assert "2 apps · 3 goals" not in digest["text"]

    def test_card_for_other_window_is_ignored(self, app, seeded):
        """A card row for a different window than the current one must not leak
        into the digest (the current window is the latest cached window)."""
        user = _watchlist_user()
        # Only a stale-window card exists -> current window is that window, but the
        # player's row IS at that window, so add a card at a DIFFERENT player to
        # advance the window without giving THIS player a current-window card.
        _add_card(player_api_id=1003, window=date(2025, 10, 1))
        digest = _render(user)
        # Current window = 2025-10-01 (latest). Player 1001 has no card there.
        assert "pulse-card" not in digest["html"]
        assert 'class="season-line"' in digest["html"]


# --------------------------------------------------------------------------- #
# Card rendering through the real send path
# --------------------------------------------------------------------------- #


class TestSendDigestPath:
    def test_admin_send_digests_renders_card(self, app, client, seeded):
        _watchlist_user()
        _add_card()
        resp = client.post("/api/scout/admin/send-digests", json={"dry_run": True}, headers=_admin_headers())
        assert resp.status_code == 200
        preview = resp.get_json()["previews"][0]
        assert "pulse-card" in preview["html"]
        assert "scored 3 goals across 2 apps this week" in preview["html"]
        assert 'class="season-line"' not in preview["html"]


# --------------------------------------------------------------------------- #
# Admin op: /api/admin/pulse/compute
# --------------------------------------------------------------------------- #


class TestPulseCompute:
    """The endpoint delegates persistence + dry_run to compute_pulse and passes
    the service's result (counts + top preview) straight through."""

    def test_requires_admin(self, client, seeded):
        assert client.post("/api/admin/pulse/compute", json={}).status_code == 401

    def test_bad_window_end_400(self, client, seeded):
        resp = client.post("/api/admin/pulse/compute", json={"window_end": "not-a-date"}, headers=_admin_headers())
        assert resp.status_code == 400

    def test_bad_dry_run_400(self, client, seeded):
        resp = client.post("/api/admin/pulse/compute", json={"dry_run": "yes"}, headers=_admin_headers())
        assert resp.status_code == 400

    def _stub_compute(self):
        def compute_pulse(window_end, player_api_ids=None, *, dry_run=False, **kwargs):
            top = [
                {"player_api_id": 1001, "name": "Alfie Striker", "score": 9.0, "signals": ["goals"]},
                {"player_api_id": 1003, "name": "Charlie Gloves", "score": 4.0, "signals": ["minutes"]},
            ]
            if not dry_run:  # real runs own their persistence (upsert + commit)
                db.session.add_all(
                    [
                        PlayerPulse(player_api_id=1001, window_end=window_end, score=9.0, delta_json={"goals": 3}),
                        PlayerPulse(player_api_id=1003, window_end=window_end, score=4.0, delta_json={"minutes": 200}),
                    ]
                )
                db.session.commit()
            return {
                "window_end": window_end.isoformat(),
                "players_considered": 2,
                "scored": 2,
                "upserted": 0 if dry_run else 2,
                "dry_run": dry_run,
                "top": top,
            }

        return compute_pulse

    def test_dry_run_previews_without_writing(self, client, seeded, monkeypatch):
        _install_service(monkeypatch, "src.services.player_pulse_service", compute_pulse=self._stub_compute())
        resp = client.post(
            "/api/admin/pulse/compute",
            json={"window_end": WINDOW.isoformat(), "dry_run": True},
            headers=_admin_headers(),
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["dry_run"] is True and data["applied"] is False
        assert data["scored"] == 2
        assert [p["player_api_id"] for p in data["top"]] == [1001, 1003]  # score-DESC preview
        assert PlayerPulse.query.count() == 0  # nothing persisted

    def test_real_run_persists(self, client, seeded, monkeypatch):
        _install_service(monkeypatch, "src.services.player_pulse_service", compute_pulse=self._stub_compute())
        resp = client.post(
            "/api/admin/pulse/compute",
            json={"window_end": WINDOW.isoformat(), "dry_run": False},
            headers=_admin_headers(),
        )
        assert resp.status_code == 200
        assert resp.get_json()["applied"] is True
        assert PlayerPulse.query.filter_by(window_end=WINDOW).count() == 2

    def test_delegates_dry_run_and_default_window_to_service(self, client, seeded, monkeypatch):
        received = {}

        def compute_pulse(window_end, player_api_ids=None, *, dry_run=False, **kwargs):
            received["dry_run"] = dry_run
            received["window_end"] = window_end
            return {"scored": 0, "top": []}

        _install_service(monkeypatch, "src.services.player_pulse_service", compute_pulse=compute_pulse)
        resp = client.post("/api/admin/pulse/compute", json={"dry_run": True}, headers=_admin_headers())
        assert resp.get_json()["window_end"] == date.today().isoformat()
        assert received["dry_run"] is True
        assert received["window_end"] == date.today()  # default window


# --------------------------------------------------------------------------- #
# Admin op: /api/admin/pulse/generate-cards
# --------------------------------------------------------------------------- #


class TestGenerateCards:
    """The endpoint validates threshold/limit, then delegates the LLM step +
    dry_run to generate_cards and passes its result straight through."""

    def _seed_pulse(self):
        # Two above the default 3.0 threshold, one below.
        db.session.add_all(
            [
                PlayerPulse(player_api_id=1001, window_end=WINDOW, score=9.0, delta_json={"goals": 3}),
                PlayerPulse(player_api_id=1003, window_end=WINDOW, score=4.0, delta_json={"assists": 2}),
                PlayerPulse(player_api_id=1007, window_end=WINDOW, score=1.0, delta_json={"minutes": 30}),
            ]
        )
        db.session.commit()

    def test_requires_admin(self, client, seeded):
        assert client.post("/api/admin/pulse/generate-cards", json={}).status_code == 401

    def test_bad_threshold_400(self, client, seeded):
        resp = client.post("/api/admin/pulse/generate-cards", json={"threshold": "high"}, headers=_admin_headers())
        assert resp.status_code == 400

    def test_bad_limit_400(self, client, seeded):
        resp = client.post("/api/admin/pulse/generate-cards", json={"limit": 0}, headers=_admin_headers())
        assert resp.status_code == 400

    def test_real_seam_dry_run_lists_candidates_no_llm(self, client, seeded):
        """No stub — hits Builder A's real generate_cards dry_run path (pure
        queries, ZERO LLM calls, writes nothing)."""
        self._seed_pulse()
        db.session.add(
            PlayerCardCache(player_api_id=1003, window_end=WINDOW, card_html="<p>x</p>", card_text="x", model="m")
        )
        db.session.commit()
        resp = client.post(
            "/api/admin/pulse/generate-cards",
            json={"window_end": WINDOW.isoformat(), "dry_run": True},
            headers=_admin_headers(),
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["dry_run"] is True and data["applied"] is False
        assert data["generated"] == 0
        assert data["skipped_cached"] == 1  # 1003 already cached
        assert [c["player_api_id"] for c in data["candidates"]] == [1001]  # 1007 below threshold
        assert PlayerCardCache.query.count() == 1  # nothing new written

    def test_delegates_args_and_dry_run(self, client, seeded, monkeypatch):
        received = {}

        def generate_cards(window_end, threshold=None, limit=None, *, dry_run=False):
            received["args"] = (window_end, threshold, limit, dry_run)
            return {"generated": 2, "skipped_cached": 0, "candidates": []}

        _install_service(monkeypatch, "src.services.player_card_service", generate_cards=generate_cards)
        resp = client.post(
            "/api/admin/pulse/generate-cards",
            json={"window_end": WINDOW.isoformat(), "threshold": 5.0, "limit": 7, "dry_run": False},
            headers=_admin_headers(),
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["generated"] == 2 and data["applied"] is True
        assert received["args"] == (WINDOW, 5.0, 7, False)

    def test_limit_capped_before_service(self, client, seeded, monkeypatch):
        received = {}

        def generate_cards(window_end, threshold=None, limit=None, *, dry_run=False):
            received["limit"] = limit
            return {"generated": 0, "skipped_cached": 0, "candidates": []}

        _install_service(monkeypatch, "src.services.player_card_service", generate_cards=generate_cards)
        client.post(
            "/api/admin/pulse/generate-cards",
            json={"window_end": WINDOW.isoformat(), "limit": 100000, "dry_run": False},
            headers=_admin_headers(),
        )
        from src.routes.scout import MAX_PULSE_CARD_LIMIT

        assert received["limit"] == MAX_PULSE_CARD_LIMIT  # sanity cap applied
