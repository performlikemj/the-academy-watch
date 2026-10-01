# Two-key highlights (C2)

- Rollout: `HIGHLIGHTS_ENABLED` defaults OFF. No new link, public clip or worker cut while dark. Export/erasure and delayed asset deletion still run.
- Club picking requires A2 `matches.view` + `matches.upload`, `match_bytes_in_scope`, and a verified immutable recording snapshot. A whole-club owner/manager must review the whole recording, including opposition and bystanders, as adult only. Youth squads, minors, unknown identities and unknown/future recording dates always fail closed. Stored DOB evidence must establish adulthood at the recording date as well as today; later birthdays cannot publish childhood footage. This is human review, not automatic age detection or redaction.
- Candidates come from the server's existing reviewed reel windows and a finalized human-confirmed identity/report. The client cannot invent times. A clip is <=60 seconds and strictly shorter than its recording.
- A listed club picks; an approved adult **self** claimant decides approve/private. Guardian claims cannot approve. C1 club-origin profiles become eligible only through canonical `public_adult`/`player_subject` publication helpers; never change provenance.
- Picked outputs remain private until both keys and current adult eligibility, account standing, suppression, subject/club holds, source generation and render generation pass on **every** list/byte request. Revoking either key immediately blocks subsequent reads. Already downloaded bytes cannot be recalled.
- Source edits atomically reset consent and fence jobs even while dark. SQL source guards cover bulk writes; the ORM listener covers SQLite and transactional application writes. A replacement source requires a fresh pick and decision. A repeat pick after removal is a fresh request and never inherits approval.
- Outbox intents contain only the opaque highlight ID/version; the registered template rechecks eligibility at delivery. No child identity, raw match URLs or storage credentials enter email intents.

## API

Club: `GET|POST /api/club/<program>/matches/<match>/highlights`, `POST .../highlight-review`, `DELETE .../highlights/<uuid>`. POST pick accepts only a server candidate's roster/tracklet/start/end plus a <=160 character title.

Player: `GET /api/me/highlight-requests?page=1`, `POST /api/me/highlight-requests/<uuid>/decision {decision:"approve"|"private",version}`, `/revoke`, `/retry`. Recipient-only standalone preview at `/me/highlight-requests/<uuid>/preview`; club preview remains A2 scoped. Inbox has bounded pages and optimistic decisions.

Public: `/api/players/<signed-id>/highlights`, `/api/programs/<slug>/highlights`, `/api/highlights/<uuid>/clip`. Clip bytes are proxied from the private cut blob with conditional ETag and bounded single-range support. No redirect, SAS, full-match capability or private source metadata. Responses use `private, no-store`.

Web: player home/owner showcase links to `/highlight-approvals`; match detail gets the club picker for upload-capable staff on finalized matches; player and club public pages mount only approved clips.

## Worker / deployment

1. Apply schema-only `p2c2_preapply.sql` before code deployment, after real p2c1 (down p2b3). Run it twice safely; the migration graph head is p2c2. Four private tables have RLS. Downgrade refuses retained rows, including cleanup jobs.
2. Build `Dockerfile.highlights` with `--build-arg BACKEND_IMAGE=<immutable backend image digest>`. Only this separate worker image installs ffmpeg; Flask never invokes it. Run a scheduled container job: `python -m src.workers.highlight_worker --limit 5` (1..20).
3. Give the worker existing private video-container credentials, DB connectivity and enough ephemeral disk for a <=12GB source. No public container/CDN/cache. Keep the main API image unchanged.
4. Worker uses its own `highlight_cut`/`highlight_delete` jobs, UUID attempt leases, `SKIP LOCKED` and 900-second fencing. Download is conditional on frozen snapshot/ETag, bounded to 300 seconds; ffmpeg is bounded to 300 seconds, 1 thread, 1280px H264, no audio/metadata, <=30MB output. No storage I/O under DB locks. Expired attempts use new private paths and cannot publish late.
5. Erasure/revocation/source changes queue cleanup after 20 minutes, beyond the render lease so late uploads cannot outrun deletion. Cleanup is active with flag OFF; transient delete failures retry at most three times. Monitor `highlight_render_jobs` failed deletions and retry operationally after resolving storage errors. Do not delete raw match recordings through this queue.
6. Enabling highlights also needs foundation outbox and real private storage plus the separate cut worker. The inbox exposes retry for failed cuts. No fabricated clips appear if storage/worker is unavailable.

## Validation

`pytest tests/test_highlights.py` checks both keys, age/mixed match scope, revocation, private bytes/ranges, immutable source reset, worker stale completion, cleanup, erasure and flag-off behavior.

Local opt-in PostgreSQL tests: create isolated `c2_checks` schema in `aw_p2_c2`, then `C2_POSTGRES_TESTS=1 pytest tests/test_highlights_postgres.py`; tests use that schema only and drop their tables. This is a local operator check, not a provider test.

`E2E_BASE_URL=... E2E_API_URL=... pnpm exec playwright test e2e/highlights.spec.mjs e2e/club-reels.spec.mjs` covers desktop/mobile dark UI and existing console integration. Synthetic fixtures are labelled and exist only in tests. Product uses server data only.
