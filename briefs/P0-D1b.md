# Task brief — P0-D1b: the maintenance job runs the retention sweep

**Pattern:** copy-adapt · **Thinking:** off · **Budget:** 30 min ·
**Files you will touch:** `academy-watch-backend/src/jobs/run_video_maintenance.py` (edit `run`) and
`academy-watch-backend/tests/test_video_maintenance_job.py` (edit both tests). Nothing else.
**Depends on:** P0-C4 (the job module) and P0-D1a (`src/services/video_retention.py`) — both landed on
this branch.

## The situation

`run_video_maintenance.run()` reaps stale analysis jobs. The retention service
(`video_retention.expire_raw_footage`) exists but nothing calls it. Make the job run both steps and
report both counts; dry-run must report what WOULD expire without changing anything.

## The job — `academy-watch-backend/src/jobs/run_video_maintenance.py`

The import line `from src.services import video_queue` becomes:

```python
from src.services import video_queue, video_retention
```

The whole `run` function is currently:

```python
def run(dry_run=False) -> dict:
    """Run every maintenance step once. Returns counts so a caller (or a test) can see what happened."""
    if dry_run:
        logger.info("video maintenance dry run: nothing changed")
        return {"stale_failed": 0, "dry_run": True}
    stale = video_queue.reap_stale_jobs()
    logger.info("video maintenance: stale-failed %d job(s)", stale)
    return {"stale_failed": stale, "dry_run": False}
```

Replace it with:

```python
def run(dry_run=False) -> dict:
    """Run every maintenance step once. Returns counts so a caller (or a test) can see what happened."""
    if dry_run:
        retention = video_retention.expire_raw_footage(dry_run=True)
        logger.info("video maintenance dry run: nothing changed (%d match(es) due for expiry)", retention["due"])
        return {"stale_failed": 0, "retention": retention, "dry_run": True}
    stale = video_queue.reap_stale_jobs()
    retention = video_retention.expire_raw_footage()
    logger.info(
        "video maintenance: stale-failed %d job(s); footage expired %d of %d due (%d failed)",
        stale,
        retention["expired"],
        retention["due"],
        retention["failed"],
    )
    return {"stale_failed": stale, "retention": retention, "dry_run": False}
```

Also update the module docstring's second paragraph: replace
`Raw-footage retention expiry joins this job in a later task.` with
`Then expires raw footage past its 90-day retention (``video_retention.expire_raw_footage``).`

## The tests — `academy-watch-backend/tests/test_video_maintenance_job.py` (edit FIRST)

Replace the whole file with:

```python
"""The video-maintenance job reaps stale analysis jobs and expires raw footage (honest dry-run)."""

from src.jobs import run_video_maintenance as job

SWEPT = {"due": 2, "expired": 2, "failed": 0, "dry_run": False}
DRY = {"due": 2, "expired": 0, "failed": 0, "dry_run": True}


def test_run_reaps_then_expires_and_reports_both(monkeypatch):
    calls = []

    def fake_reap():
        calls.append("reap")
        return 3

    def fake_expire(now=None, *, dry_run=False):
        calls.append("expire" if not dry_run else "expire-dry")
        return DRY if dry_run else SWEPT

    monkeypatch.setattr(job.video_queue, "reap_stale_jobs", fake_reap)
    monkeypatch.setattr(job.video_retention, "expire_raw_footage", fake_expire)
    assert job.run() == {"stale_failed": 3, "retention": SWEPT, "dry_run": False}
    assert calls == ["reap", "expire"]


def test_dry_run_changes_nothing_but_reports_due_count(monkeypatch):
    def explode():
        raise AssertionError("dry run must not reap")

    def fake_expire(now=None, *, dry_run=False):
        assert dry_run is True
        return DRY

    monkeypatch.setattr(job.video_queue, "reap_stale_jobs", explode)
    monkeypatch.setattr(job.video_retention, "expire_raw_footage", fake_expire)
    assert job.run(dry_run=True) == {"stale_failed": 0, "retention": DRY, "dry_run": True}
```

## How to start

1. `PLAN.md`, at most 5 lines. Then act.
2. Replace the test file. Run `make gate TASK=P0-D1b`. RED: `AttributeError: module … has no attribute
   'video_retention'`. Correct.
3. Edit the job (import + `run` + docstring line). Gate again. GREEN.

## When things go wrong

- `ruff` `F401`/`I001` → the import must read exactly `from src.services import video_queue, video_retention`.
- `assert calls == ["reap", "expire"]` fails with `["expire", "reap"]` → reap FIRST, then expire, as shown.
- Same error twice → STOP, BLOCKED, paste it.
- After ANY interruption: run the gate; whatever is red is your next step.

## Do not

- Do not touch `video_retention.py`, `video_queue.py`, routes, or other jobs.

## Done means

1. `make gate TASK=P0-D1b` green — you ran it, you saw it.
2. `grep -n "expire_raw_footage" academy-watch-backend/src/jobs/run_video_maintenance.py` prints two lines.
3. Handback file on disk + the `HANDBACK-FILED: .harness/handback/$HARNESS_SESSION.md` last line.
