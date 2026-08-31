"""Raw-footage retention: due rows lose their blob and flip to expired; nothing else is touched."""

from datetime import datetime, timedelta

import pytest
from flask import Flask
from sqlalchemy import update
from src.extensions import limiter
from src.models.follow import PlayerShadow  # noqa: F401
from src.models.funding import ClubProgram  # noqa: F401
from src.models.league import db
from src.models.player_suppression import PlayerSuppression  # noqa: F401
from src.models.showcase import LocalPlayer  # noqa: F401
from src.models.tracked_player import TrackedPlayer  # noqa: F401
from src.models.video import VideoAnalysisJob, VideoMatch
from src.routes.club import club_bp
from src.routes.player_suppression import player_suppression_bp
from src.routes.showcase import showcase_bp
from src.routes.video import video_bp
from src.services import video_retention, video_storage

PAST = datetime(2026, 1, 1, 12, 0, 0)
FUTURE = datetime(2030, 1, 1, 12, 0, 0)
NOW = datetime(2026, 8, 23, 12, 0, 0)


@pytest.fixture
def video_app(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "retention-admin-key")
    monkeypatch.setenv("ADMIN_IP_WHITELIST", "")
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SECRET_KEY="retention-fixture-secret",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        RATELIMIT_ENABLED=False,
    )
    db.init_app(app)
    limiter.init_app(app)
    app.register_blueprint(showcase_bp, url_prefix="/api")
    app.register_blueprint(player_suppression_bp, url_prefix="/api")
    app.register_blueprint(club_bp, url_prefix="/api")
    app.register_blueprint(video_bp, url_prefix="/api")
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def _match(*, status, expires_at, blob_path="matches/x.mp4"):
    row = VideoMatch(status=status, expires_at=expires_at, blob_path=blob_path, blob_etag="etag")
    db.session.add(row)
    db.session.commit()
    return row


def test_due_matches_selects_only_past_expirable_rows_with_blobs(video_app):
    due_finalized = _match(status="finalized", expires_at=PAST)
    due_failed = _match(status="failed", expires_at=PAST)
    _match(status="processing", expires_at=PAST)
    _match(status="queued", expires_at=PAST)
    _match(status="finalized", expires_at=FUTURE)
    _match(status="finalized", expires_at=None)
    _match(status="finalized", expires_at=PAST, blob_path=None)
    _match(status="expired", expires_at=PAST, blob_path=None)

    assert [m.id for m in video_retention.due_matches(NOW)] == [
        due_finalized.id,
        due_failed.id,
    ]


@pytest.mark.parametrize("job_status", ["queued", "running"])
def test_due_matches_excludes_any_match_with_an_active_job(video_app, job_status):
    guarded = _match(status="needs_tagging", expires_at=PAST)
    due = _match(status="finalized", expires_at=PAST)
    db.session.add(
        VideoAnalysisJob(
            video_match_id=guarded.id,
            pipeline_kind="qwen_analysis",
            status=job_status,
        )
    )
    db.session.commit()

    assert [match.id for match in video_retention.due_matches(NOW)] == [due.id]


def test_expire_deletes_blob_then_flips_row(video_app, monkeypatch):
    row = _match(status="finalized", expires_at=PAST, blob_path="matches/7/raw.mp4")
    deleted = []
    monkeypatch.setattr(video_storage, "is_configured", lambda: True)
    monkeypatch.setattr(video_storage, "delete_blob", lambda path: deleted.append(path) or True)

    result = video_retention.expire_raw_footage(NOW)

    assert result == {"due": 1, "expired": 1, "failed": 0, "skipped": 0, "dry_run": False}
    assert deleted == ["matches/7/raw.mp4"]
    fresh = db.session.get(VideoMatch, row.id)
    assert fresh.status == "expired"
    assert fresh.blob_path is None
    assert fresh.blob_etag is None


def test_failed_delete_keeps_row_for_next_run(video_app, monkeypatch):
    row = _match(status="finalized", expires_at=PAST)
    monkeypatch.setattr(video_storage, "is_configured", lambda: True)
    monkeypatch.setattr(video_storage, "delete_blob", lambda path: False)

    result = video_retention.expire_raw_footage(NOW)

    assert result == {"due": 1, "expired": 0, "failed": 1, "skipped": 0, "dry_run": False}
    fresh = db.session.get(VideoMatch, row.id)
    assert fresh.status == "finalized"
    assert fresh.blob_path == "matches/x.mp4"


def test_dry_run_counts_and_changes_nothing(video_app, monkeypatch):
    row = _match(status="finalized", expires_at=PAST)
    monkeypatch.setattr(video_storage, "is_configured", lambda: True)

    def explode(path):
        raise AssertionError("dry run must not delete")

    monkeypatch.setattr(video_storage, "delete_blob", explode)
    assert video_retention.expire_raw_footage(NOW, dry_run=True) == {
        "due": 1,
        "expired": 0,
        "failed": 0,
        "skipped": 0,
        "dry_run": True,
    }
    assert db.session.get(VideoMatch, row.id).status == "finalized"


def test_unconfigured_storage_counts_as_failed_and_keeps_row(video_app, monkeypatch):
    row = _match(status="finalized", expires_at=PAST)
    monkeypatch.setattr(video_storage, "is_configured", lambda: False)
    monkeypatch.setattr(video_storage, "delete_blob", lambda path: pytest.fail("must not be called without storage"))

    result = video_retention.expire_raw_footage(NOW)

    assert result == {"due": 1, "expired": 0, "failed": 1, "skipped": 0, "dry_run": False}
    db.session.refresh(row)
    assert row.status == "finalized"
    assert row.blob_path == "matches/x.mp4"


def test_preflight_rows_are_never_due_even_past_deadline(video_app):
    _match(status="preflight", expires_at=PAST)
    _match(status="finalized", expires_at=PAST)

    due = video_retention.due_matches(NOW)

    assert [m.status for m in due] == ["finalized"]
    assert "preflight" not in video_retention.EXPIRABLE_STATUSES


def test_delete_blob_treats_404_as_gone(monkeypatch):
    class Gone(Exception):
        status_code = 404

    class FakeBlob:
        def delete_blob(self):
            raise Gone("already deleted")

    class FakeClient:
        def get_blob_client(self, container, path):
            return FakeBlob()

    monkeypatch.setattr(video_storage, "_service_client", lambda: FakeClient())
    assert video_storage.delete_blob("matches/gone.mp4") is True

    class Boom(Exception):
        status_code = 500

    class BoomBlob:
        def delete_blob(self):
            raise Boom("network")

    class BoomClient:
        def get_blob_client(self, container, path):
            return BoomBlob()

    monkeypatch.setattr(video_storage, "_service_client", lambda: BoomClient())
    assert video_storage.delete_blob("matches/stuck.mp4") is False


def test_row_claimed_by_process_after_the_snapshot_is_skipped_not_expired(video_app, monkeypatch):
    row = _match(status="uploaded", expires_at=PAST)
    snapshot = video_retention.due_matches(NOW)
    assert [m.id for m in snapshot] == [row.id]
    # The race: /process claims the match between the snapshot and the delete (another transaction, so go
    # through SQL and expire the in-memory copy — the sweeper must re-read, not trust its snapshot).
    db.session.execute(update(VideoMatch).where(VideoMatch.id == row.id).values(status="queued"))
    db.session.commit()
    db.session.expire_all()
    monkeypatch.setattr(video_retention, "due_matches", lambda now=None: snapshot)
    monkeypatch.setattr(video_storage, "is_configured", lambda: True)
    monkeypatch.setattr(
        video_storage, "delete_blob", lambda path: pytest.fail("must not delete a claimed match's footage")
    )

    result = video_retention.expire_raw_footage(NOW)

    assert result == {"due": 1, "expired": 0, "failed": 0, "skipped": 1, "dry_run": False}
    fresh = db.session.get(VideoMatch, row.id)
    assert fresh.status == "queued"
    assert fresh.blob_path == "matches/x.mp4"


def test_active_job_created_after_sweep_snapshot_is_skipped_under_match_lock(video_app, monkeypatch):
    row = _match(status="needs_tagging", expires_at=PAST)
    snapshot = video_retention.due_matches(NOW)
    assert [match.id for match in snapshot] == [row.id]
    db.session.add(
        VideoAnalysisJob(
            video_match_id=row.id,
            pipeline_kind="qwen_analysis",
            status="queued",
        )
    )
    db.session.commit()
    db.session.expire_all()
    monkeypatch.setattr(video_retention, "due_matches", lambda now=None: snapshot)
    monkeypatch.setattr(video_storage, "is_configured", lambda: True)
    monkeypatch.setattr(
        video_storage,
        "delete_blob",
        lambda path: pytest.fail("must not delete footage needed by an active analysis job"),
    )

    result = video_retention.expire_raw_footage(NOW)

    assert result == {"due": 1, "expired": 0, "failed": 0, "skipped": 1, "dry_run": False}
    fresh = db.session.get(VideoMatch, row.id)
    assert fresh.status == "needs_tagging"
    assert fresh.blob_path == "matches/x.mp4"


def test_abandoned_created_uploads_become_due_by_age(video_app, monkeypatch):
    old = VideoMatch(status="created", blob_path="matches/abandoned.mp4", created_at=NOW - timedelta(days=91))
    young = VideoMatch(status="created", blob_path="matches/young.mp4", created_at=NOW - timedelta(days=10))
    pathless = VideoMatch(status="created", blob_path=None, created_at=NOW - timedelta(days=400))
    db.session.add_all([old, young, pathless])
    db.session.commit()

    assert [m.id for m in video_retention.due_matches(NOW)] == [old.id]

    deleted = []
    monkeypatch.setattr(video_storage, "is_configured", lambda: True)
    monkeypatch.setattr(video_storage, "delete_blob", lambda path: deleted.append(path) or True)
    result = video_retention.expire_raw_footage(NOW)

    assert result == {"due": 1, "expired": 1, "failed": 0, "skipped": 0, "dry_run": False}
    assert deleted == ["matches/abandoned.mp4"]
    db.session.expire_all()
    assert db.session.get(VideoMatch, old.id).status == "expired"
    assert db.session.get(VideoMatch, old.id).blob_path is None
    assert db.session.get(VideoMatch, young.id).status == "created"


def test_sweep_waits_one_upload_grant_lifetime_past_the_deadline(video_app):
    just_past = _match(status="uploaded", expires_at=NOW - timedelta(minutes=30))
    long_past = _match(status="uploaded", expires_at=NOW - timedelta(minutes=90))

    assert [m.id for m in video_retention.due_matches(NOW)] == [long_past.id]
    assert timedelta(minutes=video_storage.UPLOAD_SAS_MINUTES) == video_retention.UPLOAD_GRANT_GRACE
    assert just_past.id not in [m.id for m in video_retention.due_matches(NOW)]


def test_can_issue_upload_grant_refuses_grants_that_would_outlive_the_deadline(video_app):
    fresh = _match(status="uploaded", expires_at=NOW + timedelta(days=10))
    closing = _match(status="uploaded", expires_at=NOW + timedelta(minutes=30))
    overdue = _match(status="uploaded", expires_at=NOW - timedelta(days=1))
    young_created = VideoMatch(status="created", blob_path="matches/y.mp4", created_at=NOW - timedelta(days=1))
    old_created = VideoMatch(status="created", blob_path="matches/o.mp4", created_at=NOW - timedelta(days=90))
    db.session.add_all([young_created, old_created])
    db.session.commit()

    assert video_retention.can_issue_upload_grant(fresh, NOW) is True
    assert video_retention.can_issue_upload_grant(closing, NOW) is False
    assert video_retention.can_issue_upload_grant(overdue, NOW) is False
    assert video_retention.can_issue_upload_grant(young_created, NOW) is True
    assert video_retention.can_issue_upload_grant(old_created, NOW) is False
    assert video_retention.retention_deadline(young_created) == young_created.created_at + timedelta(days=90)


def test_retention_window_closed_follows_the_deadline(video_app):
    open_row = _match(status="uploaded", expires_at=NOW + timedelta(days=1))
    closed_row = _match(status="uploaded", expires_at=NOW - timedelta(minutes=1))
    fresh_created = VideoMatch(status="created", blob_path="matches/f.mp4", created_at=NOW - timedelta(days=1))
    stale_created = VideoMatch(status="created", blob_path="matches/s.mp4", created_at=NOW - timedelta(days=91))
    db.session.add_all([fresh_created, stale_created])
    db.session.commit()

    assert video_retention.retention_window_closed(open_row, NOW) is False
    assert video_retention.retention_window_closed(closed_row, NOW) is True
    assert video_retention.retention_window_closed(fresh_created, NOW) is False
    assert video_retention.retention_window_closed(stale_created, NOW) is True
