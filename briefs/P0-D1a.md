# Task brief — P0-D1a: enforce the 90-day raw-footage promise (service)

**Pattern:** copy-adapt · **Thinking:** off · **Budget:** 60 min ·
**Files you will touch:** `academy-watch-backend/src/services/video_storage.py` (ONE new function),
`academy-watch-backend/src/services/video_retention.py` (NEW), and
`academy-watch-backend/tests/test_video_retention.py` (NEW). Nothing else.

## The situation

The Terms promise that raw match footage is deleted 90 days after upload (derived numbers are kept).
`VideoMatch.expires_at` is stamped at upload-complete and the status list has an `expired` value — but
NO code deletes a blob or sets that status. This task builds the enforcement as a pure service; the next
task (P0-D1b) runs it from the scheduled maintenance job.

Rules for the sweeper: only footage a pipeline no longer needs may go (`uploaded`, `preflight`,
`needs_tagging`, `finalized`, `failed`); `queued`/`processing` rows wait for the next run; `created` rows
have no blob. Deleting the blob comes FIRST; the row flips to `expired` (and forgets `blob_path`/`blob_etag`)
only after the blob is confirmed gone. When blob storage is not configured (dev/tests) the row still flips.

## The job

### 1. `academy-watch-backend/src/services/video_storage.py` — add `delete_blob`

Append this function at the END of the file (after `verify_expected_blob`). It copies the shape of
`verify_uploaded_blob` (client → blob → call → broad except that logs and returns a value):

```python
def delete_blob(blob_path: str) -> bool:
    """Delete one raw-footage blob. True when it is gone afterwards (deleted now, or already absent)."""
    try:
        blob = _service_client().get_blob_client(_container(), blob_path)
        blob.delete_blob()
        return True
    except Exception as e:  # auth, network — all mean "not gone"; a 404 means it was already gone
        if getattr(e, "status_code", None) == 404:
            return True
        logger.warning("video blob delete failed for %s: %s", blob_path, e)
        return False
```

### 2. Create `academy-watch-backend/src/services/video_retention.py`

```python
"""Raw-footage retention (ToS: raw match video is deleted 90 days after upload; derived data is kept).

``VideoMatch.expires_at`` is stamped at upload-complete (routes/video.py, routes/club.py). This module
is the only thing that ENFORCES it: delete the blob, then flip the match to ``expired``. It never touches
tracklets, reports, or jobs.
"""

import logging
from datetime import UTC, datetime

from src.models.league import db
from src.models.video import VideoMatch
from src.services import video_storage

logger = logging.getLogger(__name__)

# Only footage no pipeline still needs may go: queued/processing rows wait for the next run, and
# created rows have no blob yet.
EXPIRABLE_STATUSES = ("uploaded", "preflight", "needs_tagging", "finalized", "failed")


def _utcnow_naive() -> datetime:
    # Columns are naive UTC (the routes store datetime.now(UTC) into a tz-less DateTime).
    return datetime.now(UTC).replace(tzinfo=None)


def due_matches(now: datetime | None = None) -> list[VideoMatch]:
    """Matches whose raw footage is past retention and still present, oldest deadline first."""
    now = now or _utcnow_naive()
    return (
        VideoMatch.query.filter(
            VideoMatch.expires_at.isnot(None),
            VideoMatch.expires_at <= now,
            VideoMatch.status.in_(EXPIRABLE_STATUSES),
            VideoMatch.blob_path.isnot(None),
        )
        .order_by(VideoMatch.expires_at.asc(), VideoMatch.id.asc())
        .all()
    )


def expire_raw_footage(now: datetime | None = None, *, dry_run: bool = False) -> dict:
    """Delete due raw footage and mark those matches expired. Returns counts; a failed delete is
    counted and skipped (the row stays untouched for the next run), never raised."""
    now = now or _utcnow_naive()
    due = due_matches(now)
    if dry_run:
        return {"due": len(due), "expired": 0, "failed": 0, "dry_run": True}
    expired = 0
    failed = 0
    for match in due:
        if video_storage.is_configured() and not video_storage.delete_blob(match.blob_path):
            failed += 1
            continue
        match.status = "expired"
        match.blob_path = None
        match.blob_etag = None
        db.session.commit()
        expired += 1
        logger.info("raw footage expired for video match %s", match.id)
    return {"due": len(due), "expired": expired, "failed": failed, "dry_run": False}
```

### 3. Create `academy-watch-backend/tests/test_video_retention.py` (write it FIRST)

The fixture below is the proven recipe for video models in this repo (same imports/registrations as
`tests/test_club_console.py`; the JSONB→JSON shim in `tests/conftest.py` applies automatically).

```python
"""Raw-footage retention: due rows lose their blob and flip to expired; nothing else is touched."""

from datetime import datetime

import pytest
from flask import Flask
from src.extensions import limiter
from src.models.follow import PlayerShadow  # noqa: F401
from src.models.funding import ClubProgram  # noqa: F401
from src.models.league import db
from src.models.player_suppression import PlayerSuppression  # noqa: F401
from src.models.showcase import LocalPlayer  # noqa: F401
from src.models.tracked_player import TrackedPlayer  # noqa: F401
from src.models.video import VideoMatch
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

    assert [m.id for m in video_retention.due_matches(NOW)] == [due_finalized.id, due_failed.id]


def test_expire_deletes_blob_then_flips_row(video_app, monkeypatch):
    row = _match(status="finalized", expires_at=PAST, blob_path="matches/7/raw.mp4")
    deleted = []
    monkeypatch.setattr(video_storage, "is_configured", lambda: True)
    monkeypatch.setattr(video_storage, "delete_blob", lambda path: deleted.append(path) or True)

    result = video_retention.expire_raw_footage(NOW)

    assert result == {"due": 1, "expired": 1, "failed": 0, "dry_run": False}
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

    assert result == {"due": 1, "expired": 0, "failed": 1, "dry_run": False}
    fresh = db.session.get(VideoMatch, row.id)
    assert fresh.status == "finalized"
    assert fresh.blob_path == "matches/x.mp4"


def test_dry_run_counts_and_changes_nothing(video_app, monkeypatch):
    row = _match(status="finalized", expires_at=PAST)
    monkeypatch.setattr(video_storage, "is_configured", lambda: True)

    def explode(path):
        raise AssertionError("dry run must not delete")

    monkeypatch.setattr(video_storage, "delete_blob", explode)
    assert video_retention.expire_raw_footage(NOW, dry_run=True) == {"due": 1, "expired": 0, "failed": 0, "dry_run": True}
    assert db.session.get(VideoMatch, row.id).status == "finalized"


def test_unconfigured_storage_still_flips_row(video_app, monkeypatch):
    row = _match(status="uploaded", expires_at=PAST)
    monkeypatch.setattr(video_storage, "is_configured", lambda: False)
    assert video_retention.expire_raw_footage(NOW)["expired"] == 1
    assert db.session.get(VideoMatch, row.id).status == "expired"


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
```

## How to start

1. `PLAN.md`, at most 10 lines. Then act.
2. Write the test file. Run `make gate TASK=P0-D1a`. RED: `ImportError: cannot import name
   'video_retention'`. Correct.
3. Add `delete_blob`, create `video_retention.py`. Gate again. GREEN (the gate also runs
   `tests/test_club_console.py`; ~20 seconds).

## When things go wrong

- `ruff` `I001` import order → in `video_retention.py` the order is `import logging` / `from datetime
  import UTC, datetime` / blank / `from src.models.league import db` / `from src.models.video import
  VideoMatch` / `from src.services import video_storage` — exactly as shown.
- `test_due_matches…` returns the `processing`/`queued` rows → `EXPIRABLE_STATUSES` must not include
  them; copy the tuple exactly.
- `test_expire_deletes_blob_then_flips_row` fails on `blob_etag` → set all three fields (`status`,
  `blob_path`, `blob_etag`) before `db.session.commit()`.
- `TypeError: can't compare offset-naive and offset-aware datetimes` → use `_utcnow_naive()` as shown;
  never `datetime.now(UTC)` directly in comparisons.
- Same error twice → STOP, BLOCKED, paste it.
- After ANY interruption: run the gate; whatever is red is your next step.

## Do not

- Do not touch routes, the maintenance job (next task), tracklets/reports/jobs, the model, or
  `verify_*` functions. Do not delete anything but the raw blob.

## Done means

1. `make gate TASK=P0-D1a` green — you ran it, you saw it.
2. `grep -n "def expire_raw_footage\|def due_matches" academy-watch-backend/src/services/video_retention.py`
   prints two lines; `grep -n "def delete_blob" academy-watch-backend/src/services/video_storage.py` prints one.
3. Handback file on disk + the `HANDBACK-FILED: .harness/handback/$HARNESS_SESSION.md` last line.
