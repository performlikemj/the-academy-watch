# Task brief — P0-D1b: the maintenance job runs the retention sweep

**Pattern:** copy-adapt · **Thinking:** off · **Budget:** 30 min ·
**Files you will touch:** `academy-watch-backend/src/jobs/run_video_maintenance.py` (edit `run`) and
`academy-watch-backend/tests/test_video_maintenance_job.py` (edit both tests). Nothing else.
**Depends on:** P0-C4 (the job module) and P0-D1a (`src/services/video_retention.py`) — both landed on
this branch.

**Shipped files:** this brief ships the replacement test under `briefs/assets/P0-D1b/`; the section below gives the exact `cp` command. Never retype a shipped file.

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

Replace the whole file with the shipped one — COPY it, never retype (one command):

```bash
cp briefs/assets/P0-D1b/test_video_maintenance_job.py academy-watch-backend/tests/test_video_maintenance_job.py
```

## How to start

1. `PLAN.md`, at most 5 lines. Then act.
2. Copy the replacement test file (the `cp` command above). Run `make gate TASK=P0-D1b`. RED: `AttributeError: module … has no attribute
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
