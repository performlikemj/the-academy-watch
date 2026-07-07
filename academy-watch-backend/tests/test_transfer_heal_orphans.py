"""Transfer-heal orphan self-heal scope.

Orphaned in-window academy rows (is_active=false, journey-attributed,
non-manual, non-pinned) must be requeued into the heal so a transfers-fed
journey re-sync can reactivate them via the journey upsert. Out-of-window,
manual, and pinned orphans must stay out of the queue. Reactivation needs a
journey re-sync, so orphans are only requeued when resync_journeys=True.
"""

import pytest
from flask import Flask
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
        orphan_in_window = _tracked(601, team, active=False, last_season=recent)
        orphan_out_window = _tracked(602, team, active=False, last_season=old)
        orphan_manual = _tracked(603, team, active=False, data_source="manual", last_season=recent)
        orphan_pinned = _tracked(604, team, active=False, last_season=recent, pinned=True)
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
        # No last_academy_season, but the row says the player is in the academy
        # right now — a current kid that got orphaned must still self-heal.
        orphan = _tracked(605, team, active=False, last_season=None, status="academy")
        db.session.commit()
        orphan_id = orphan.player_api_id

        resynced = _patch_api_and_journey(monkeypatch)
        result = refresh_and_heal(resync_journeys=True, dry_run=True, cascade_fixtures=False)

        assert result["total"] == 1
        assert orphan_id in resynced

    def test_orphans_not_requeued_without_resync(self, app, monkeypatch):
        # Without a journey re-sync there is nothing to reactivate the row, so
        # orphans must NOT be pulled in (they can't self-heal via cached data).
        from src.services.transfer_heal_service import refresh_and_heal
        from src.utils.academy_window import current_academy_season

        recent = current_academy_season()
        team = _seed_team()
        _tracked(600, team, active=True, last_season=recent)
        _tracked(601, team, active=False, last_season=recent)
        db.session.commit()

        _patch_api_and_journey(monkeypatch)
        result = refresh_and_heal(resync_journeys=False, dry_run=True, cascade_fixtures=False)

        # Only the active row is in the queue; the orphan is left alone.
        assert result["total"] == 1
