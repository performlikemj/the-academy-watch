"""Transfer-heal orphan self-heal scope.

Orphaned rows are requeued into the heal so a transfers-fed journey re-sync can
reactivate them via the journey upsert. The requeue is BOUNDED and TERMINAL:
only rows whose linked PlayerJourney still attributes the row's academy club
IN-WINDOW are requeued (those are the only rows the upsert can reactivate), so
graveyard rows are not force_full re-synced forever. Manual and pinned orphans
stay out of the queue. Reactivation needs a journey re-sync, so orphans are only
requeued when resync_journeys=True.
"""

import pytest
from flask import Flask
from src.models.journey import PlayerJourney
from src.models.league import League, Team, db
from src.models.tracked_player import TrackedPlayer


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("SKIP_API_HANDSHAKE", "1")
    monkeypatch.setenv("API_USE_STUB_DATA", "true")

    flask_app = Flask(__name__)
    flask_app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret-key",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(flask_app)
    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()


def _seed_team():
    league = League(league_id=39, name="Premier League", country="England", season=2025)
    db.session.add(league)
    db.session.flush()
    team = Team(team_id=100, name="Feyenoord", country="England", season=2025, league_id=league.id, is_active=True)
    db.session.add(team)
    db.session.flush()
    return team


def _journey(player_api_id, *, academy_club_ids=None, academy_last_seasons=None, birth_date=None):
    """A PlayerJourney carrying the academy attribution the requeue gate reads.

    The gate keys on the journey, not the tracked row's own fields, so a legacy
    owning-club orphan with NO row-local season is still requeued when its
    journey attributes the club in-window (the Gore case)."""
    j = PlayerJourney(
        player_api_id=player_api_id,
        player_name=f"Test Player {player_api_id}",
        academy_club_ids=academy_club_ids if academy_club_ids is not None else [],
        academy_last_seasons=academy_last_seasons if academy_last_seasons is not None else {},
        birth_date=birth_date,
    )
    db.session.add(j)
    db.session.flush()
    return j


def _tracked(
    player_api_id, team, *, active, data_source="journey-sync", last_season=None, status="on_loan", pinned=False
):
    tp = TrackedPlayer(
        player_api_id=player_api_id,
        player_name=f"Test Player {player_api_id}",
        team_id=team.id,
        status=status,
        data_source=data_source,
        last_academy_season=last_season,
        pinned_parent=pinned,
        is_active=active,
    )
    db.session.add(tp)
    db.session.flush()
    return tp


def _patch_api_and_journey(monkeypatch):
    """Stub every network call and record which players get a journey re-sync."""
    from src.api_football_client import APIFootballClient
    from src.services.journey_sync import JourneySyncService

    monkeypatch.setattr(APIFootballClient, "batch_get_player_transfers", lambda self, ids, **kw: {})
    monkeypatch.setattr(APIFootballClient, "get_team_players", lambda self, club_id, season=None: [])

    resynced: list[int] = []

    def _record_sync(self, player_api_id, force_full=False):
        resynced.append(player_api_id)
        return None  # no journey → the heal loop skips further processing

    monkeypatch.setattr(JourneySyncService, "sync_player", _record_sync)
    return resynced


class TestOrphanRequeueScope:
    def test_in_window_orphan_requeued_others_excluded(self, app, monkeypatch):
        from src.services.transfer_heal_service import refresh_and_heal
        from src.utils.academy_window import academy_window_start, current_academy_season

        recent = current_academy_season()
        old = academy_window_start() - 2
        team = _seed_team()

        active_row = _tracked(600, team, active=True, last_season=recent)
        # In-window orphan whose journey still attributes club 100 in-window.
        orphan_in_window = _tracked(601, team, active=False, last_season=recent)
        _journey(601, academy_club_ids=[100], academy_last_seasons={"100": recent})
        # Journey attributes 100 but OUT of window → not requeued.
        orphan_out_window = _tracked(602, team, active=False, last_season=old)
        _journey(602, academy_club_ids=[100], academy_last_seasons={"100": old})
        orphan_manual = _tracked(603, team, active=False, data_source="manual", last_season=recent)
        _journey(603, academy_club_ids=[100], academy_last_seasons={"100": recent})
        orphan_pinned = _tracked(604, team, active=False, last_season=recent, pinned=True)
        _journey(604, academy_club_ids=[100], academy_last_seasons={"100": recent})
        db.session.commit()
        ids = {
            "active": active_row.player_api_id,
            "in_window": orphan_in_window.player_api_id,
            "out_window": orphan_out_window.player_api_id,
            "manual": orphan_manual.player_api_id,
            "pinned": orphan_pinned.player_api_id,
        }

        resynced = _patch_api_and_journey(monkeypatch)
        result = refresh_and_heal(resync_journeys=True, dry_run=True, cascade_fixtures=False)

        # Only the active row + the in-window orphan are in the queue.
        assert result["total"] == 2
        assert ids["active"] in resynced
        assert ids["in_window"] in resynced
        assert ids["out_window"] not in resynced
        assert ids["manual"] not in resynced
        assert ids["pinned"] not in resynced

    def test_status_academy_orphan_requeued_without_season(self, app, monkeypatch):
        from src.services.transfer_heal_service import refresh_and_heal

        team = _seed_team()
        # No last_academy_season and the journey has no stored season either, but
        # the row says the player is in the academy right now — a current kid that
        # got orphaned must still self-heal (journey attributes the club).
        orphan = _tracked(605, team, active=False, last_season=None, status="academy")
        _journey(605, academy_club_ids=[100], academy_last_seasons={})
        db.session.commit()
        orphan_id = orphan.player_api_id

        resynced = _patch_api_and_journey(monkeypatch)
        result = refresh_and_heal(resync_journeys=True, dry_run=True, cascade_fixtures=False)

        assert result["total"] == 1
        assert orphan_id in resynced

    def test_owning_club_null_season_orphan_requeued(self, app, monkeypatch):
        # The canonical Gore row: data_source='owning-club', NO row-local season,
        # but the journey attributes the club in-window. The old row-local filter
        # missed it entirely; the journey-attribution gate must catch it.
        from src.services.transfer_heal_service import refresh_and_heal
        from src.utils.academy_window import current_academy_season

        recent = current_academy_season()
        team = _seed_team()
        orphan = _tracked(606, team, active=False, data_source="owning-club", last_season=None, status="first_team")
        _journey(606, academy_club_ids=[100], academy_last_seasons={"100": recent})
        db.session.commit()
        orphan_id = orphan.player_api_id

        resynced = _patch_api_and_journey(monkeypatch)
        result = refresh_and_heal(resync_journeys=True, dry_run=True, cascade_fixtures=False)

        assert result["total"] == 1
        assert orphan_id in resynced

    def test_journey_unattributed_orphan_not_requeued(self, app, monkeypatch):
        # Row passes the coarse row-local filter (in-window last_academy_season)
        # but its journey NO LONGER attributes the club — a genuinely-departed
        # row the upsert cannot reactivate. It must NOT be force_full re-synced
        # (terminal state; no fruitless nightly retries).
        from src.services.transfer_heal_service import refresh_and_heal
        from src.utils.academy_window import current_academy_season

        recent = current_academy_season()
        team = _seed_team()
        orphan = _tracked(607, team, active=False, last_season=recent)
        _journey(607, academy_club_ids=[999], academy_last_seasons={"999": recent})
        db.session.commit()
        orphan_id = orphan.player_api_id

        resynced = _patch_api_and_journey(monkeypatch)
        result = refresh_and_heal(resync_journeys=True, dry_run=True, cascade_fixtures=False)

        assert result["total"] == 0
        assert orphan_id not in resynced

    def test_orphan_without_journey_not_requeued(self, app, monkeypatch):
        # A row-local in-window orphan with NO journey at all cannot be
        # reactivated by the journey upsert, so it must stay out of the queue.
        from src.services.transfer_heal_service import refresh_and_heal
        from src.utils.academy_window import current_academy_season

        recent = current_academy_season()
        team = _seed_team()
        orphan = _tracked(608, team, active=False, last_season=recent)
        db.session.commit()
        orphan_id = orphan.player_api_id

        resynced = _patch_api_and_journey(monkeypatch)
        result = refresh_and_heal(resync_journeys=True, dry_run=True, cascade_fixtures=False)

        assert result["total"] == 0
        assert orphan_id not in resynced

    def test_orphans_not_requeued_without_resync(self, app, monkeypatch):
        # Without a journey re-sync there is nothing to reactivate the row, so
        # orphans must NOT be pulled in (they can't self-heal via cached data).
        from src.services.transfer_heal_service import refresh_and_heal
        from src.utils.academy_window import current_academy_season

        recent = current_academy_season()
        team = _seed_team()
        _tracked(600, team, active=True, last_season=recent)
        orphan = _tracked(601, team, active=False, last_season=recent)
        _journey(601, academy_club_ids=[100], academy_last_seasons={"100": recent})
        db.session.commit()

        _patch_api_and_journey(monkeypatch)
        result = refresh_and_heal(resync_journeys=False, dry_run=True, cascade_fixtures=False)

        # Only the active row is in the queue; the orphan is left alone.
        assert result["total"] == 1


class TestOrphanRequeueBudgetAndRotation:
    def test_orphan_budget_caps_requeue(self, app, monkeypatch):
        # A single call may requeue at most `orphan_budget` orphans, so the
        # per-team nightly job can keep the ceiling job-global.
        from src.services.transfer_heal_service import refresh_and_heal
        from src.utils.academy_window import current_academy_season

        recent = current_academy_season()
        team = _seed_team()
        for pid in (711, 712, 713):
            _tracked(pid, team, active=False, last_season=recent)
            _journey(pid, academy_club_ids=[100], academy_last_seasons={"100": recent})
        db.session.commit()

        resynced = _patch_api_and_journey(monkeypatch)
        result = refresh_and_heal(resync_journeys=True, dry_run=True, cascade_fixtures=False, orphan_budget=2)

        assert result["orphans_requeued"] == 2
        assert len([p for p in (711, 712, 713) if p in resynced]) == 2

    def test_zero_orphan_budget_requeues_nothing(self, app, monkeypatch):
        # A depleted job-global budget (0) must requeue no orphans, while active
        # rows still get processed normally.
        from src.services.transfer_heal_service import refresh_and_heal
        from src.utils.academy_window import current_academy_season

        recent = current_academy_season()
        team = _seed_team()
        _tracked(720, team, active=True, last_season=recent)
        orphan = _tracked(721, team, active=False, last_season=recent)
        _journey(721, academy_club_ids=[100], academy_last_seasons={"100": recent})
        db.session.commit()
        orphan_id = orphan.player_api_id

        resynced = _patch_api_and_journey(monkeypatch)
        result = refresh_and_heal(resync_journeys=True, dry_run=True, cascade_fixtures=False, orphan_budget=0)

        assert result["orphans_requeued"] == 0
        assert result["total"] == 1  # only the active row
        assert orphan_id not in resynced

    def test_stuck_orphan_rotates_to_back_of_queue(self, app, monkeypatch):
        # An orphan the re-sync cannot reactivate keeps churning force_full
        # re-syncs. Its updated_at must be bumped on the skipped requeue so the
        # oldest-touched ordering round-robins instead of re-selecting the same
        # stuck rows first every night (starving healable orphans behind them).
        from datetime import UTC, datetime, timedelta

        from src.services.transfer_heal_service import refresh_and_heal
        from src.utils.academy_window import current_academy_season

        recent = current_academy_season()
        team = _seed_team()
        older = _tracked(701, team, active=False, last_season=recent)
        newer = _tracked(702, team, active=False, last_season=recent)
        _journey(701, academy_club_ids=[100], academy_last_seasons={"100": recent})
        _journey(702, academy_club_ids=[100], academy_last_seasons={"100": recent})
        # Deterministic queue order: 701 is the oldest-touched candidate.
        t0 = datetime(2026, 6, 1, tzinfo=UTC)
        older.updated_at = t0
        newer.updated_at = t0 + timedelta(hours=1)
        db.session.commit()

        # sync_player returns None → the row stays inactive (never healable).
        resynced = _patch_api_and_journey(monkeypatch)

        # Budget 1 → run 1 requeues only the oldest (701).
        r1 = refresh_and_heal(resync_journeys=True, dry_run=False, cascade_fixtures=False, orphan_budget=1)
        assert r1["orphans_requeued"] == 1
        assert 701 in resynced
        assert 702 not in resynced

        # 701's updated_at was bumped past 702, so run 2 rotates to 702 —
        # the previously-starved row is now reached.
        db.session.expire_all()
        resynced.clear()
        r2 = refresh_and_heal(resync_journeys=True, dry_run=False, cascade_fixtures=False, orphan_budget=1)
        assert r2["orphans_requeued"] == 1
        assert 702 in resynced
        assert 701 not in resynced
