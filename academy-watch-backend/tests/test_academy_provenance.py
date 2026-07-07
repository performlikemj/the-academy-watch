"""Tests for academy provenance: clubs may only track players formed in
their OWN academy.

Covers:
- _compute_academy_club_ids prior-senior-career behaviour (Malacia-shaped
  journeys yield no academy ids; genuine academy products keep theirs)
- _upsert_tracked_players never creates owning-club rows and deactivates
  journey-sync / owning-club / owning-parent rows (pinned rows survive)
- POST /api/admin/journeys/recompute-academy repair endpoint
"""

import pytest
from flask import Flask
from src.models.journey import PlayerJourney, PlayerJourneyEntry
from src.models.league import League, Team, db
from src.models.tracked_player import TrackedPlayer

ADMIN_KEY = "test-admin-key"


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("SKIP_API_HANDSHAKE", "1")
    monkeypatch.setenv("API_USE_STUB_DATA", "true")
    monkeypatch.setenv("ADMIN_API_KEY", ADMIN_KEY)
    monkeypatch.setenv("ADMIN_IP_WHITELIST", "")

    from src.routes.journey import journey_bp

    flask_app = Flask(__name__)
    flask_app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret-key",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )

    db.init_app(flask_app)
    flask_app.register_blueprint(journey_bp, url_prefix="/api")

    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def admin_headers(app):
    from src.auth import issue_user_token

    token = issue_user_token("admin@test.com", role="admin")["token"]
    return {"Authorization": f"Bearer {token}", "X-API-Key": ADMIN_KEY}


@pytest.fixture
def sync_service(app):
    from src.services.journey_sync import JourneySyncService

    return JourneySyncService()


def _seed_league():
    league = League(league_id=39, name="Premier League", country="England", season=2025)
    db.session.add(league)
    db.session.flush()
    return league


def _seed_team(league, api_id, name):
    team = Team(team_id=api_id, name=name, country="England", season=2025, league_id=league.id, is_active=True)
    db.session.add(team)
    db.session.flush()
    return team


def _entry(
    journey_id,
    season,
    club_api_id,
    club_name,
    *,
    level="First Team",
    entry_type="first_team",
    is_youth=False,
    appearances=10,
    league_api_id=1000,
):
    return PlayerJourneyEntry(
        journey_id=journey_id,
        season=season,
        club_api_id=club_api_id,
        club_name=club_name,
        league_api_id=league_api_id,
        league_name="Test League",
        league_country="England",
        level=level,
        entry_type=entry_type,
        is_youth=is_youth,
        is_international=False,
        appearances=appearances,
        goals=0,
        assists=0,
        minutes=appearances * 90,
    )


def _malacia_journey(player_api_id):
    """Feyenoord product bought by Man United, with a one-off U21 rehab entry.

    FT at club A (100) 2019-2021, transfer, FT at club B (200) 2022+, and ONE
    development entry at B's U21 side in 2024.
    """
    journey = PlayerJourney(
        player_api_id=player_api_id,
        player_name=f"Test Player {player_api_id}",
        academy_club_ids=[],
    )
    db.session.add(journey)
    db.session.flush()
    entries = [
        _entry(journey.id, 2019, 100, "Feyenoord", appearances=30),
        _entry(journey.id, 2020, 100, "Feyenoord", appearances=30),
        _entry(journey.id, 2021, 100, "Feyenoord", appearances=30),
        _entry(journey.id, 2022, 200, "Manchester United", appearances=20),
        _entry(journey.id, 2023, 200, "Manchester United", appearances=15),
        _entry(
            journey.id,
            2024,
            201,
            "Manchester United U21",
            level="U21",
            entry_type="development",
            is_youth=True,
            appearances=1,
        ),
    ]
    db.session.add_all(entries)
    db.session.flush()
    return journey


def _tracked(player_api_id, team, *, data_source="journey-sync", journey_id=None, pinned=False, active=True):
    tp = TrackedPlayer(
        player_api_id=player_api_id,
        player_name=f"Test Player {player_api_id}",
        team_id=team.id,
        status="first_team",
        data_source=data_source,
        journey_id=journey_id,
        pinned_parent=pinned,
        is_active=active,
    )
    db.session.add(tp)
    db.session.flush()
    return tp


class TestMalaciaShapedJourney:
    def test_compute_yields_no_academy_ids(self, app, sync_service):
        league = _seed_league()
        _seed_team(league, 100, "Feyenoord")
        _seed_team(league, 200, "Manchester United")
        journey = _malacia_journey(270)
        db.session.commit()

        sync_service._compute_academy_club_ids(journey)

        assert journey.academy_club_ids == []

    def test_journey_sync_row_at_owner_deactivated(self, app, sync_service):
        league = _seed_league()
        _seed_team(league, 100, "Feyenoord")
        team_b = _seed_team(league, 200, "Manchester United")
        journey = _malacia_journey(270)
        row = _tracked(270, team_b, data_source="journey-sync", journey_id=journey.id)
        db.session.commit()

        sync_service._compute_academy_club_ids(journey)

        assert row.is_active is False

    def test_owning_club_row_deactivated_by_upsert(self, app, sync_service):
        league = _seed_league()
        _seed_team(league, 100, "Feyenoord")
        team_b = _seed_team(league, 200, "Manchester United")
        journey = _malacia_journey(271)
        row = _tracked(271, team_b, data_source="owning-club", journey_id=journey.id)
        db.session.commit()

        sync_service._compute_academy_club_ids(journey)

        assert row.is_active is False

    def test_pinned_row_at_owner_survives(self, app, sync_service):
        league = _seed_league()
        _seed_team(league, 100, "Feyenoord")
        team_b = _seed_team(league, 200, "Manchester United")
        journey = _malacia_journey(272)
        row = _tracked(272, team_b, data_source="journey-sync", journey_id=journey.id, pinned=True)
        db.session.commit()

        sync_service._compute_academy_club_ids(journey)

        assert row.is_active is True


class TestGenuineAcademyProduct:
    def test_loan_does_not_disqualify_academy_origin(self, app, sync_service):
        # Seasons relative to today so the window gate never ages this out
        from src.utils.academy_window import current_academy_season

        cur = current_academy_season()
        league = _seed_league()
        team_c = _seed_team(league, 300, "Carlton Rovers")
        _seed_team(league, 400, "Faraway FC")
        journey = PlayerJourney(player_api_id=280, player_name="Test Player 280", academy_club_ids=[])
        db.session.add(journey)
        db.session.flush()
        db.session.add_all(
            [
                _entry(
                    journey.id,
                    cur - 2,
                    301,
                    "Carlton Rovers U21",
                    level="U21",
                    entry_type="development",
                    is_youth=True,
                    appearances=10,
                ),
                _entry(journey.id, cur - 1, 400, "Faraway FC", entry_type="loan", appearances=15),
                _entry(
                    journey.id,
                    cur,
                    301,
                    "Carlton Rovers U21",
                    level="U21",
                    entry_type="development",
                    is_youth=True,
                    appearances=8,
                ),
            ]
        )
        db.session.commit()

        sync_service._compute_academy_club_ids(journey)

        assert 300 in (journey.academy_club_ids or [])
        row = TrackedPlayer.query.filter_by(player_api_id=280, team_id=team_c.id).first()
        assert row is not None
        assert row.is_active is True
        assert row.data_source == "journey-sync"

    def test_same_club_first_team_debut_keeps_parent(self, app, sync_service):
        from src.utils.academy_window import current_academy_season

        cur = current_academy_season()
        league = _seed_league()
        team_c = _seed_team(league, 300, "Carlton Rovers")
        journey = PlayerJourney(player_api_id=281, player_name="Test Player 281", academy_club_ids=[])
        db.session.add(journey)
        db.session.flush()
        db.session.add_all(
            [
                _entry(journey.id, cur - 1, 300, "Carlton Rovers", entry_type="first_team", appearances=10),
                _entry(
                    journey.id,
                    cur,
                    301,
                    "Carlton Rovers U21",
                    level="U21",
                    entry_type="development",
                    is_youth=True,
                    appearances=5,
                ),
            ]
        )
        db.session.commit()

        sync_service._compute_academy_club_ids(journey)

        assert 300 in (journey.academy_club_ids or [])
        row = TrackedPlayer.query.filter_by(player_api_id=281, team_id=team_c.id).first()
        assert row is not None
        assert row.is_active is True


class TestUpsertNeverCreatesOwningClubRows:
    def test_no_row_created_at_owning_club(self, app, sync_service):
        league = _seed_league()
        _seed_team(league, 100, "Feyenoord")
        team_b = _seed_team(league, 200, "Manchester United")
        journey = _malacia_journey(273)
        db.session.commit()

        sync_service._compute_academy_club_ids(journey)

        rows_at_b = TrackedPlayer.query.filter_by(player_api_id=273, team_id=team_b.id).all()
        assert rows_at_b == []
        assert TrackedPlayer.query.filter_by(player_api_id=273).all() == []

    def test_existing_row_at_owning_club_deactivated_not_recreated(self, app, sync_service):
        league = _seed_league()
        _seed_team(league, 100, "Feyenoord")
        team_b = _seed_team(league, 200, "Manchester United")
        journey = _malacia_journey(274)
        row = _tracked(274, team_b, data_source="api-football", journey_id=journey.id)
        db.session.commit()

        sync_service._compute_academy_club_ids(journey)

        rows_at_b = TrackedPlayer.query.filter_by(player_api_id=274, team_id=team_b.id).all()
        assert len(rows_at_b) == 1
        assert rows_at_b[0].id == row.id
        assert rows_at_b[0].is_active is False
        assert not any(tp.data_source == "owning-club" for tp in rows_at_b)


class TestRecomputeAcademyEndpoint:
    def _seed_contradictions(self):
        league = _seed_league()
        team_a = _seed_team(league, 100, "Feyenoord")
        team_b = _seed_team(league, 200, "Manchester United")
        team_c = _seed_team(league, 300, "Carlton Rovers")

        journey = _malacia_journey(290)
        journey.academy_club_ids = [200]  # stale/wrong stored value

        # api-football row at the wrong parent (journey evidence) — caught
        # by the contradiction sweep (A is not the owning club).
        tp_wrong_parent = _tracked(290, team_a, data_source="api-football", journey_id=journey.id)
        # Row at the owning club — deactivated by the upsert itself.
        tp_owner = _tracked(290, team_b, data_source="api-football", journey_id=journey.id)
        # Cohort-discovered row WITHOUT a journey — must remain untouched.
        tp_no_journey = _tracked(291, team_c, data_source="api-football", journey_id=None)
        db.session.commit()
        return journey, tp_wrong_parent, tp_owner, tp_no_journey

    def test_dry_run_reports_but_mutates_nothing(self, app, client, admin_headers):
        journey, tp_wrong_parent, tp_owner, tp_no_journey = self._seed_contradictions()
        journey_id = journey.id
        ids = (tp_wrong_parent.id, tp_owner.id, tp_no_journey.id)

        resp = client.post(
            "/api/admin/journeys/recompute-academy",
            json={"dry_run": True},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["dry_run"] is True
        assert data["journeys_processed"] == 1
        assert data["journeys_changed"] == 1
        assert data["rows_deactivated"] == 2
        assert len(data["examples"]) == 2

        db.session.expire_all()
        assert db.session.get(TrackedPlayer, ids[0]).is_active is True
        assert db.session.get(TrackedPlayer, ids[1]).is_active is True
        assert db.session.get(TrackedPlayer, ids[2]).is_active is True
        assert sorted(db.session.get(PlayerJourney, journey_id).academy_club_ids or []) == [200]

    def test_real_run_deactivates_contradicting_rows(self, app, client, admin_headers):
        journey, tp_wrong_parent, tp_owner, tp_no_journey = self._seed_contradictions()
        journey_id = journey.id
        ids = (tp_wrong_parent.id, tp_owner.id, tp_no_journey.id)

        resp = client.post(
            "/api/admin/journeys/recompute-academy",
            json={"dry_run": False},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["dry_run"] is False
        assert data["rows_deactivated"] == 2
        reasons = {ex["reason"] for ex in data["examples"]}
        assert any("recomputed academy_club_ids" in r or "academy origin" in r for r in reasons)

        db.session.expire_all()
        # api-football row at wrong parent (journey evidence) deactivated
        assert db.session.get(TrackedPlayer, ids[0]).is_active is False
        # row at the owning club deactivated
        assert db.session.get(TrackedPlayer, ids[1]).is_active is False
        # cohort-discovered row without journey untouched
        assert db.session.get(TrackedPlayer, ids[2]).is_active is True
        assert sorted(db.session.get(PlayerJourney, journey_id).academy_club_ids or []) == []

    def test_real_run_deactivates_legacy_owning_club_rows(self, app, client, admin_headers):
        league = _seed_league()
        team_b = _seed_team(league, 200, "Manchester United")
        # Legacy owning-club row with no journey — sweep still removes it.
        tp = _tracked(295, team_b, data_source="owning-club", journey_id=None)
        db.session.commit()
        tp_id = tp.id

        resp = client.post(
            "/api/admin/journeys/recompute-academy",
            json={"dry_run": False},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.get_json()["rows_deactivated"] == 1

        db.session.expire_all()
        assert db.session.get(TrackedPlayer, tp_id).is_active is False

    def test_requires_admin_auth(self, app, client):
        resp = client.post("/api/admin/journeys/recompute-academy", json={"dry_run": True})
        assert resp.status_code == 401


class TestEntryTypingFinalForm:
    """The reordered/widened reclassifier passes (final-form provenance)."""

    def _entry(self, **kw):
        from src.models.journey import PlayerJourneyEntry

        defaults = dict(entry_type="academy", is_international=False, level="U21", appearances=1)
        defaults.update(kw)
        return PlayerJourneyEntry(**defaults)

    def _svc(self):
        from src.services.journey_sync import JourneySyncService

        return JourneySyncService.__new__(JourneySyncService)

    def test_signing_u21_rehab_becomes_integration_not_development(self):
        svc = self._svc()
        entries = [
            self._entry(
                club_api_id=209,
                club_name="Feyenoord",
                season=2019,
                entry_type="first_team",
                level="First Team",
                appearances=30,
            ),
            self._entry(
                club_api_id=33,
                club_name="Manchester United",
                season=2022,
                entry_type="first_team",
                level="First Team",
                appearances=30,
            ),
            self._entry(club_api_id=7198, club_name="Manchester United U21", season=2024),
        ]
        svc._apply_development_classification(entries, transfers=None, birth_date="1999-08-17")
        assert entries[2].entry_type == "integration"

    def test_homegrown_post_debut_youth_is_development(self):
        svc = self._svc()
        entries = [
            self._entry(club_api_id=7198, club_name="Manchester United U18", season=2020, level="U18"),
            self._entry(
                club_api_id=33,
                club_name="Manchester United",
                season=2021,
                entry_type="first_team",
                level="First Team",
                appearances=20,
            ),
            self._entry(club_api_id=7198, club_name="Manchester United U21", season=2022),
        ]
        svc._apply_development_classification(entries, transfers=None, birth_date="2004-07-01")
        assert entries[0].entry_type == "academy"
        assert entries[2].entry_type == "development"

    def test_buy_back_transfer_does_not_disqualify_formative_years(self):
        svc = self._svc()
        entries = [
            self._entry(club_api_id=496, club_name="Juventus U19", season=2009, level="U19"),
            self._entry(
                club_api_id=496,
                club_name="Juventus",
                season=2016,
                entry_type="first_team",
                level="First Team",
                appearances=30,
            ),
        ]
        transfers = [{"type": "€ 100M", "date": "2016-07-01", "teams": {"in": {"id": 496}, "out": {"id": 33}}}]
        svc._apply_development_classification(entries, transfers=transfers, birth_date="1993-03-15")
        assert entries[0].entry_type == "academy"

    def test_transfer_in_flags_later_development_entries(self):
        svc = self._svc()
        entries = [
            self._entry(
                club_api_id=33,
                club_name="Manchester United",
                season=2022,
                entry_type="first_team",
                level="First Team",
                appearances=30,
            ),
            self._entry(club_api_id=7198, club_name="Manchester United U21", season=2024),
        ]
        transfers = [{"type": "€ 15M", "date": "2022-07-05", "teams": {"in": {"id": 7198}, "out": {"id": 209}}}]
        svc._apply_development_classification(entries, transfers=transfers, birth_date="1999-08-17")
        assert entries[1].entry_type == "integration"

    def test_teenage_transfer_into_academy_stays_academy(self):
        svc = self._svc()
        entries = [self._entry(club_api_id=7198, club_name="Manchester United U18", season=2020, level="U18")]
        transfers = [{"type": "Free", "date": "2020-08-01", "teams": {"in": {"id": 7198}, "out": {"id": 9999}}}]
        svc._apply_development_classification(entries, transfers=transfers, birth_date="2004-07-01")
        assert entries[0].entry_type == "academy"


class TestRecomputeCursorPaging:
    """Batched/cursor behavior for production scale + concurrent writers."""

    def _seed_two_journeys(self):
        league = _seed_league()
        team_a = _seed_team(league, 100, "Feyenoord")
        team_b = _seed_team(league, 200, "Manchester United")
        j1 = _malacia_journey(290)
        j1.academy_club_ids = [200]
        j2 = _malacia_journey(291)
        j2.academy_club_ids = [200]
        _tracked(290, team_b, data_source="api-football", journey_id=j1.id)
        _tracked(291, team_b, data_source="api-football", journey_id=j2.id)
        db.session.commit()
        return j1, j2, team_a, team_b

    def test_cursor_pages_through_population(self, app, client, admin_headers):
        j1, j2, _, _ = self._seed_two_journeys()
        r1 = client.post(
            "/api/admin/journeys/recompute-academy",
            json={"dry_run": False, "limit": 1},
            headers=admin_headers,
        ).get_json()
        assert r1["journeys_processed"] == 1
        assert r1["next_cursor"] == j1.id
        r2 = client.post(
            "/api/admin/journeys/recompute-academy",
            json={"dry_run": False, "limit": 1, "cursor": r1["next_cursor"]},
            headers=admin_headers,
        ).get_json()
        assert r2["journeys_processed"] == 1
        r3 = client.post(
            "/api/admin/journeys/recompute-academy",
            json={"dry_run": False, "limit": 1, "cursor": r2["next_cursor"] or j2.id},
            headers=admin_headers,
        ).get_json()
        assert r3["journeys_processed"] == 0
        assert r3["next_cursor"] is None

    def test_per_journey_error_does_not_poison_the_run(self, app, client, admin_headers, monkeypatch):
        j1, j2, _, team_b = self._seed_two_journeys()
        from src.services.journey_sync import JourneySyncService

        original = JourneySyncService._compute_academy_club_ids

        def flaky(self, journey, entries=None, transfers=None):
            if journey.id == j1.id:
                raise RuntimeError("simulated concurrent-writer conflict")
            return original(self, journey, entries=entries, transfers=transfers)

        monkeypatch.setattr(JourneySyncService, "_compute_academy_club_ids", flaky)
        r = client.post(
            "/api/admin/journeys/recompute-academy",
            json={"dry_run": False, "limit": 10},
            headers=admin_headers,
        ).get_json()
        assert r["errors"] == 1
        assert r["journeys_processed"] == 1  # j2 still processed
        assert r["next_cursor"] is None

    def test_invalid_cursor_rejected(self, app, client, admin_headers):
        resp = client.post(
            "/api/admin/journeys/recompute-academy",
            json={"cursor": -3},
            headers=admin_headers,
        )
        assert resp.status_code == 400

    def test_dry_run_advances_cursor_without_mutation(self, app, client, admin_headers):
        j1, j2, _, team_b = self._seed_two_journeys()
        r = client.post(
            "/api/admin/journeys/recompute-academy",
            json={"dry_run": True, "limit": 1},
            headers=admin_headers,
        ).get_json()
        assert r["dry_run"] is True
        assert r["next_cursor"] == j1.id
        refreshed = db.session.get(PlayerJourney, j1.id)
        assert sorted(refreshed.academy_club_ids or []) == [200]  # unchanged


def _academy_alumnus_journey(player_api_id, youth_seasons, *, current_club_api_id=None, birth_date=None):
    """Genuine academy product of Feyenoord (100) with youth entries in the
    given seasons, optionally now at another club."""
    journey = PlayerJourney(
        player_api_id=player_api_id,
        player_name=f"Test Player {player_api_id}",
        academy_club_ids=[],
        birth_date=birth_date,
        current_club_api_id=current_club_api_id,
        current_level="First Team" if current_club_api_id else None,
    )
    db.session.add(journey)
    db.session.flush()
    entries = [
        _entry(
            journey.id,
            season,
            101,
            "Feyenoord U18",
            level="U18",
            entry_type="academy",
            is_youth=True,
            appearances=20,
            league_api_id=2000 + season,
        )
        for season in youth_seasons
    ]
    db.session.add_all(entries)
    db.session.flush()
    return journey


class TestAcademyTrackingWindow:
    """Clubs only track academy players current or within the past
    ACADEMY_WINDOW_YEARS seasons (src/utils/academy_window.py)."""

    def test_out_of_window_alumnus_row_deactivated(self, app, sync_service):
        from src.utils.academy_window import academy_window_start

        old = academy_window_start() - 2
        league = _seed_league()
        team = _seed_team(league, 100, "Feyenoord")
        journey = _academy_alumnus_journey(400, [old - 1, old])
        row = _tracked(400, team, data_source="journey-sync", journey_id=journey.id)
        db.session.commit()

        sync_service._compute_academy_club_ids(journey)

        # Provenance is permanent history; tracking liveness is not.
        assert journey.academy_club_ids == [100]
        assert journey.academy_last_seasons == {"100": old}
        assert row.is_active is False

    def test_out_of_window_alumnus_gets_no_new_row(self, app, sync_service):
        from src.utils.academy_window import academy_window_start

        old = academy_window_start() - 1
        league = _seed_league()
        team = _seed_team(league, 100, "Feyenoord")
        journey = _academy_alumnus_journey(401, [old])
        db.session.commit()

        sync_service._compute_academy_club_ids(journey)

        assert TrackedPlayer.query.filter_by(player_api_id=401, team_id=team.id).first() is None

    def test_in_window_product_kept_and_evidence_recorded(self, app, sync_service):
        from src.utils.academy_window import current_academy_season

        recent = current_academy_season() - 1
        league = _seed_league()
        team = _seed_team(league, 100, "Feyenoord")
        journey = _academy_alumnus_journey(402, [recent - 1, recent])
        row = _tracked(402, team, data_source="journey-sync", journey_id=journey.id)
        db.session.commit()

        sync_service._compute_academy_club_ids(journey)

        assert row.is_active is True
        assert row.last_academy_season == recent

    def test_in_window_product_row_created_with_evidence(self, app, sync_service):
        from src.utils.academy_window import current_academy_season

        recent = current_academy_season()
        league = _seed_league()
        team = _seed_team(league, 100, "Feyenoord")
        journey = _academy_alumnus_journey(403, [recent])
        db.session.commit()

        sync_service._compute_academy_club_ids(journey)

        created = TrackedPlayer.query.filter_by(player_api_id=403, team_id=team.id).first()
        assert created is not None
        assert created.is_active is True
        assert created.last_academy_season == recent

    def test_pinned_out_of_window_row_survives(self, app, sync_service):
        from src.utils.academy_window import academy_window_start

        old = academy_window_start() - 3
        league = _seed_league()
        team = _seed_team(league, 100, "Feyenoord")
        journey = _academy_alumnus_journey(404, [old])
        row = _tracked(404, team, data_source="journey-sync", journey_id=journey.id, pinned=True)
        db.session.commit()

        sync_service._compute_academy_club_ids(journey)

        assert row.is_active is True

    def test_recompute_endpoint_deactivates_out_of_window_with_reason(self, app, client, admin_headers):
        from src.utils.academy_window import academy_window_start, current_academy_season

        old = academy_window_start() - 2
        recent = current_academy_season() - 1
        league = _seed_league()
        team = _seed_team(league, 100, "Feyenoord")

        # api-football rows are untouched by the upsert's stale sweep, so
        # these exercise the endpoint's contradiction-sweep window branch.
        alumnus_journey = _academy_alumnus_journey(405, [old])
        alumnus_row = _tracked(405, team, data_source="api-football", journey_id=alumnus_journey.id)
        prospect_journey = _academy_alumnus_journey(406, [recent])
        prospect_row = _tracked(406, team, data_source="api-football", journey_id=prospect_journey.id)
        db.session.commit()
        alumnus_id, prospect_id = alumnus_row.id, prospect_row.id

        resp = client.post(
            "/api/admin/journeys/recompute-academy",
            json={"dry_run": False},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.get_json()
        reasons = {ex["reason"] for ex in data["examples"]}
        assert any("outside the academy tracking window" in r for r in reasons)

        db.session.expire_all()
        assert db.session.get(TrackedPlayer, alumnus_id).is_active is False
        survivor = db.session.get(TrackedPlayer, prospect_id)
        assert survivor.is_active is True
        assert survivor.last_academy_season == recent


class TestWindowProtectsCurrentAcademyKids:
    """Stale youth-league coverage must never age out a player who is in
    the academy right now (review finding: status escape hatch)."""

    def test_youth_level_journey_overrides_stale_seasons(self, app, sync_service):
        from src.utils.academy_window import academy_window_start

        old = academy_window_start() - 1
        league = _seed_league()
        team = _seed_team(league, 100, "Feyenoord")
        journey = _academy_alumnus_journey(430, [old])
        # API says the player is at youth level RIGHT NOW
        journey.current_level = "U21"
        journey.current_club_api_id = 100
        row = _tracked(430, team, data_source="journey-sync", journey_id=journey.id)
        row.status = "academy"
        db.session.commit()

        sync_service._compute_academy_club_ids(journey)

        assert row.is_active is True

    def test_row_status_academy_survives_window_deactivation(self, app, sync_service):
        from src.utils.academy_window import academy_window_start

        old = academy_window_start() - 1
        league = _seed_league()
        team = _seed_team(league, 100, "Feyenoord")
        # Journey says First Team elsewhere (no journey-level override) but
        # the stored row still says currently in this academy.
        journey = _academy_alumnus_journey(431, [old], current_club_api_id=999)
        row = _tracked(431, team, data_source="journey-sync", journey_id=journey.id)
        row.status = "academy"
        db.session.commit()

        sync_service._compute_academy_club_ids(journey)

        assert row.is_active is True


class TestUpsertReactivatesOrphanedAcademyRows:
    def test_inactive_row_revived_when_provenance_and_window_hold(self, app, sync_service):
        from src.utils.academy_window import current_academy_season

        recent = current_academy_season()
        league = _seed_league()
        team = _seed_team(league, 100, "Feyenoord")
        journey = _academy_alumnus_journey(432, [recent])
        row = _tracked(432, team, data_source="journey-sync", journey_id=journey.id, active=False)
        db.session.commit()

        sync_service._compute_academy_club_ids(journey)

        assert row.is_active is True
        assert row.last_academy_season == recent

    def test_inactive_manual_row_left_alone(self, app, sync_service):
        from src.utils.academy_window import current_academy_season

        recent = current_academy_season()
        league = _seed_league()
        team = _seed_team(league, 100, "Feyenoord")
        journey = _academy_alumnus_journey(433, [recent])
        row = _tracked(433, team, data_source="manual", journey_id=journey.id, active=False)
        db.session.commit()

        sync_service._compute_academy_club_ids(journey)

        assert row.is_active is False

    def test_reactivated_owning_club_row_becomes_visible_journey_sync(self, app, sync_service):
        # The Gore heal: an inactive 'owning-club' row whose club IS the academy
        # origin (in keep_ids). Reactivation must also flip data_source to
        # 'journey-sync' — otherwise the row comes back ACTIVE but still invisible
        # on Scout Desk / Teams (which exclude data_source='owning-club',
        # invariant #3), i.e. healed-but-hidden.
        from src.utils.academy_window import current_academy_season

        recent = current_academy_season()
        league = _seed_league()
        team = _seed_team(league, 100, "Feyenoord")
        journey = _academy_alumnus_journey(434, [recent])
        row = _tracked(434, team, data_source="owning-club", journey_id=journey.id, active=False)
        db.session.commit()

        sync_service._compute_academy_club_ids(journey)

        assert row.is_active is True
        assert row.data_source == "journey-sync"


class TestStoredAttributionFloor:
    """A transient sync that resolves NO academy evidence (API youth-coverage
    gap / tenure-gate flicker → empty academy_ids) must never orphan an
    established in-window academy row. Canonical case: Daniel Gore."""

    def _stored_journey(self, player_api_id, *, stored_last_seasons, senior_entry=None):
        """Journey with a PERSISTED academy attribution but NO youth entries
        this run — so _compute takes an empty-computation path and the floor
        must lean on the stored attribution to spare the row."""
        journey = PlayerJourney(
            player_api_id=player_api_id,
            player_name=f"Test Player {player_api_id}",
            academy_club_ids=sorted(int(k) for k in stored_last_seasons),
            academy_last_seasons={str(k): v for k, v in stored_last_seasons.items()},
        )
        db.session.add(journey)
        db.session.flush()
        if senior_entry is not None:
            season, club_api_id, club_name = senior_entry
            db.session.add(_entry(journey.id, season, club_api_id, club_name, entry_type="first_team", appearances=20))
            db.session.flush()
        return journey

    def test_empty_computation_spares_in_window_row(self, app, sync_service):
        from src.utils.academy_window import current_academy_season

        recent = current_academy_season()
        league = _seed_league()
        team = _seed_team(league, 100, "Feyenoord")
        journey = self._stored_journey(500, stored_last_seasons={100: recent})
        row = _tracked(500, team, data_source="journey-sync", journey_id=journey.id)
        db.session.commit()

        sync_service._compute_academy_club_ids(journey)

        assert row.is_active is True

    def test_homegrown_owned_row_spared_from_owning_block(self, app, sync_service):
        # Gore-shaped: the owning club IS the academy club (a homegrown player
        # still owned by his academy, e.g. on loan). A transient empty run would
        # otherwise nuke the row via BOTH the stale sweep and the owning-club
        # block; the floor must protect it in both.
        from src.utils.academy_window import current_academy_season

        recent = current_academy_season()
        league = _seed_league()
        team = _seed_team(league, 100, "Feyenoord")
        journey = self._stored_journey(501, stored_last_seasons={100: recent}, senior_entry=(recent, 100, "Feyenoord"))
        # owning-club data_source mirrors the real orphaned Gore row.
        row = _tracked(501, team, data_source="owning-club", journey_id=journey.id)
        db.session.commit()

        sync_service._compute_academy_club_ids(journey)

        assert row.is_active is True

    def test_floor_does_not_protect_out_of_window_stored_row(self, app, sync_service):
        # Stored attribution present but its last youth season is OUT of window
        # → a genuine aged-out alumnus; the floor must NOT keep it alive.
        from src.utils.academy_window import academy_window_start

        old = academy_window_start() - 2
        league = _seed_league()
        team = _seed_team(league, 100, "Feyenoord")
        journey = self._stored_journey(502, stored_last_seasons={100: old})
        row = _tracked(502, team, data_source="journey-sync", journey_id=journey.id)
        db.session.commit()

        sync_service._compute_academy_club_ids(journey)

        assert row.is_active is False

    def test_floor_ignores_stale_ids_without_season_evidence(self, app, sync_service):
        # academy_club_ids lists the club but there is NO season evidence
        # (academy_last_seasons empty) — a merely-stale stored value. This is the
        # recompute contradiction shape; the floor must NOT protect it.
        league = _seed_league()
        team = _seed_team(league, 100, "Feyenoord")
        journey = PlayerJourney(
            player_api_id=503,
            player_name="Test Player 503",
            academy_club_ids=[100],
            academy_last_seasons={},
        )
        db.session.add(journey)
        db.session.flush()
        row = _tracked(503, team, data_source="journey-sync", journey_id=journey.id)
        db.session.commit()

        sync_service._compute_academy_club_ids(journey)

        assert row.is_active is False

    def test_floor_ignores_season_less_stale_ids_even_for_u21(self, app, sync_service):
        # Same season-less stale shape, but now the player is a U21 WITH a birth
        # date. The floor must key on stored SEASON evidence only — the birth-date
        # development-age fallback in is_within_academy_window must NOT stand in
        # for it, or every young player's season-less stale attribution would be
        # spared (defeating the one-shot recompute repair).
        from datetime import date

        league = _seed_league()
        team = _seed_team(league, 100, "Feyenoord")
        nineteen = date.today().year - 19
        journey = PlayerJourney(
            player_api_id=504,
            player_name="Test Player 504",
            academy_club_ids=[100],
            academy_last_seasons={},
            birth_date=f"{nineteen}-01-15",
        )
        db.session.add(journey)
        db.session.flush()
        row = _tracked(504, team, data_source="journey-sync", journey_id=journey.id)
        db.session.commit()

        sync_service._compute_academy_club_ids(journey)

        assert row.is_active is False

    def test_floor_survives_two_consecutive_empty_runs(self, app, sync_service):
        # An API coverage gap that lasts two nightly syncs must not orphan the
        # row on run 2. Run 1 spares it AND retains the stored attribution the
        # floor depends on (instead of zeroing it), so run 2 still fires.
        from src.utils.academy_window import current_academy_season

        recent = current_academy_season()
        league = _seed_league()
        team = _seed_team(league, 100, "Feyenoord")
        journey = self._stored_journey(505, stored_last_seasons={100: recent})
        row = _tracked(505, team, data_source="journey-sync", journey_id=journey.id)
        db.session.commit()

        # Run 1: empty computation spares the row and keeps the attribution.
        sync_service._compute_academy_club_ids(journey)
        assert row.is_active is True
        assert (journey.academy_club_ids or []) == [100]
        assert (journey.academy_last_seasons or {}) == {"100": recent}
        db.session.commit()

        # Run 2: gap persists — the floor must still protect the row.
        sync_service._compute_academy_club_ids(journey)
        assert row.is_active is True

    def test_floor_honours_in_window_row_local_season(self, app, sync_service):
        # The journey's per-club season map is EMPTY (legacy pre-aw18 map, or
        # youth entries whose seasons are NULL) but the tracked ROW carries an
        # in-window last_academy_season. Keying the floor on the journey map
        # alone would orphan it on a single empty run (and, since retention
        # would zero academy_club_ids, put it beyond the transfer-heal requeue
        # gate too). Row-local season evidence must spare it AND be recovered
        # into the journey map so the floor survives a second empty run.
        from src.utils.academy_window import current_academy_season

        recent = current_academy_season()
        league = _seed_league()
        team = _seed_team(league, 100, "Feyenoord")
        journey = PlayerJourney(
            player_api_id=510,
            player_name="Test Player 510",
            academy_club_ids=[100],
            academy_last_seasons={},
        )
        db.session.add(journey)
        db.session.flush()
        row = _tracked(510, team, data_source="journey-sync", journey_id=journey.id)
        row.last_academy_season = recent
        db.session.commit()

        # Run 1: empty computation, but the row's own season spares it and the
        # attribution is recovered into the journey map.
        sync_service._compute_academy_club_ids(journey)
        assert row.is_active is True
        assert (journey.academy_club_ids or []) == [100]
        assert (journey.academy_last_seasons or {}) == {"100": recent}
        db.session.commit()

        # Run 2: gap persists — the recovered attribution keeps the floor firing.
        sync_service._compute_academy_club_ids(journey)
        assert row.is_active is True

    def test_floor_honours_row_status_academy_when_journey_level_lags(self, app, sync_service):
        # Row says status='academy' (a current academy kid) but the journey's
        # current_level lags (First Team / legacy) and the season map is empty.
        # The aged-out branch already spares status='academy' rows, but only on
        # runs with evidence; on a NO-evidence run academy_ids (and aged_out) are
        # empty, so the floor must itself honour the row's status.
        league = _seed_league()
        team = _seed_team(league, 100, "Feyenoord")
        journey = PlayerJourney(
            player_api_id=511,
            player_name="Test Player 511",
            academy_club_ids=[100],
            academy_last_seasons={},
            current_level="First Team",
        )
        db.session.add(journey)
        db.session.flush()
        row = _tracked(511, team, data_source="journey-sync", journey_id=journey.id)
        row.status = "academy"
        db.session.commit()

        sync_service._compute_academy_club_ids(journey)
        assert row.is_active is True
        # Retained via the row's status so the requeue gate could still see it.
        assert (journey.academy_club_ids or []) == [100]
        db.session.commit()

        sync_service._compute_academy_club_ids(journey)
        assert row.is_active is True
