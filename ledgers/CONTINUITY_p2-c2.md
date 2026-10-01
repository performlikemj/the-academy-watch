# Phase 2 C2 — two-key highlights

## Goal / constraints
- Club picks a server reel window; independent adult self-claimant approves; standalone private clip output; revoke on next request.
- Branch p2/c2-highlights from origin/p2/b3-admin; PR against main stacked on #1115, ready at end; no merge.
- HIGHLIGHTS_ENABLED default OFF; p2c2 -> real p2c1 ancestor copied verbatim; no placeholder.
- Reuse A1 adult/holds/outbox/audit, A2 capability+byte scope, B1 is_listed. No public minors, youth/mixed footage, raw match SAS or metadata.
- Own ports5151/5202 and scratch aw_p2_c2; foreground only; clean own resources.

## State
- Done: read Phase2/design/BUS/P2R5 and repo guidance; verified clean branch/base.
- Done: implemented private tables, source fences, capability routes, independent consent, standalone worker+private bytes, outbox, erasure/export, dark web mounts.
- Checks: focused PostgreSQL39 pass (35 behavior +4 concurrency), browser12 pass at1440/390 with reviewed screenshots; real ffmpeg cut1.001s/noaudio/1280px; Node219 pass; scratch real chain upgraded; guarded upgrade twice/RLS4/source guards6; OSV547 clean, lint0 errors/build pass.
- Done: final dependency cut B1811fabca/B216540e03/B3d49ec794/mainadea5177; independent clips survive raw expiry; UTC SQL/ORM guards fence source/date/identity changes + delayed cleanup.
- Done: recording-date DOB checks prevent childhood/unknown/future footage; request-local recording cache avoids repeated source reads, never cached by worker/writes.
- Checks: focused46 + PG5 (combined51 pass,1 C1 module pending skip); real C1 canonical overlay integration passed; schema/RLS/source guards/retained downgrade/empty rollback passed.
- Now: final full gate after B2 integration; current C1 code tested in temporary overlay without changing canonical modules. Browser broad runs expose existing frozen-route/legacy fixture failures (logs retained); supported current-route suite running.
- Next: backend+worker; web surfaces; security/browser/PG/full gates; screenshots; PR ready+hand-back.

## Acceptance / checks
- Both keys required; revoke removes lists+bytes immediately; minors/unknown ages/private matches blocked.
- Source/identity/window changes invalidate consent; concurrent job completion fenced.
- Candidate preview only standalone clip; public bytes proxy private blob, no SAS redirect.
- Every new table guarded DDL + RLS; export/erasure remains effective when flag OFF.
- Full Ruff/format/backend/Node/lint/build and relevant Playwright before push.
