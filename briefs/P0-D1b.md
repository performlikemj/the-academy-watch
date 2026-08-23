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

## The job — `academy-watch-backend/src/jobs/run_video_maintenance.py` (three replacements by `sed`; no typing)

Do NOT use your edit tool on this file. Three commands, exactly, in this order:

Replace the services import line (adds `video_retention`):

```bash
SI=$(grep -n '^from src.services import video_queue$' academy-watch-backend/src/jobs/run_video_maintenance.py | cut -d: -f1); echo "SI=$SI"; sed -i '' "${SI}d" academy-watch-backend/src/jobs/run_video_maintenance.py && sed -i '' "$((SI-1))r briefs/assets/P0-D1b/services_import.py" academy-watch-backend/src/jobs/run_video_maintenance.py && echo IMPORT-REPLACED
```

Replace the whole `run` function (its `def` line through its `return {"stale_failed": stale, "dry_run": False}` line):

```bash
RS=$(grep -n '^def run(dry_run=False) -> dict:$' academy-watch-backend/src/jobs/run_video_maintenance.py | cut -d: -f1); RE=$(grep -n '^    return {"stale_failed": stale, "dry_run": False}$' academy-watch-backend/src/jobs/run_video_maintenance.py | cut -d: -f1); echo "RS=$RS RE=$RE"; sed -i '' "${RS},${RE}d" academy-watch-backend/src/jobs/run_video_maintenance.py && sed -i '' "$((RS-1))r briefs/assets/P0-D1b/run_function.py" academy-watch-backend/src/jobs/run_video_maintenance.py && echo RUN-REPLACED
```

Replace the docstring's last two lines about retention:

```bash
DL=$(grep -n 'Raw-footage retention expiry joins this job in a$' academy-watch-backend/src/jobs/run_video_maintenance.py | cut -d: -f1); echo "DL=$DL"; sed -i '' "${DL},$((DL+1))d" academy-watch-backend/src/jobs/run_video_maintenance.py && sed -i '' "$((DL-1))r briefs/assets/P0-D1b/docstring_lines.py" academy-watch-backend/src/jobs/run_video_maintenance.py && echo DOCSTRING-REPLACED
```

Confirm, read-only: `grep -c "expire_raw_footage" academy-watch-backend/src/jobs/run_video_maintenance.py` → `3`
(docstring + two calls). Anything else → STOP, BLOCKED.

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
