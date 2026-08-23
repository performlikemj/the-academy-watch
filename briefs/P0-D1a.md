# Task brief — P0-D1a: enforce the 90-day raw-footage promise (service)

**Pattern:** copy-adapt · **Thinking:** off · **Budget:** 60 min ·
**Files you will touch:** `academy-watch-backend/src/services/video_storage.py` (ONE new function),
`academy-watch-backend/src/services/video_retention.py` (NEW), and
`academy-watch-backend/tests/test_video_retention.py` (NEW). Nothing else.

**Shipped files:** this brief ships its NEW files under `briefs/assets/P0-D1a/`; each numbered section below gives the exact `cp` command. Never retype a shipped file — copy it. Your work is the edits inside existing files and the gate.

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

Shipped with this brief — COPY it, never retype (one command):

```bash
mkdir -p academy-watch-backend/src/services && cp briefs/assets/P0-D1a/video_retention.py academy-watch-backend/src/services/video_retention.py
```

### 3. Create `academy-watch-backend/tests/test_video_retention.py` (write it FIRST)

The fixture below is the proven recipe for video models in this repo (same imports/registrations as
`tests/test_club_console.py`; the JSONB→JSON shim in `tests/conftest.py` applies automatically).

Shipped with this brief — COPY it, never retype (one command):

```bash
mkdir -p academy-watch-backend/tests && cp briefs/assets/P0-D1a/test_video_retention.py academy-watch-backend/tests/test_video_retention.py
```

## How to start

1. `PLAN.md`, at most 10 lines. Then act.
2. Copy the test file (the `cp` command above). Run `make gate TASK=P0-D1a`. RED: `ImportError: cannot import name
   'video_retention'`. Correct.
3. Add `delete_blob`, copy `video_retention.py` (its `cp` command). Gate again. GREEN (the gate also runs
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
