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
- Done: latest B3d49ec794 + B1811fabca merged; B2 5cd45b0b retained; worker/source/erasure cleanup fences late uploads; outbox delivery assertions added.
- Now: full gate in progress; schema preapply twice passed; waiting C1 canonical branch readiness contract while consuming helpers unchanged.
- Next: backend+worker; web surfaces; security/browser/PG/full gates; screenshots; PR ready+hand-back.

## Acceptance / checks
- Both keys required; revoke removes lists+bytes immediately; minors/unknown ages/private matches blocked.
- Source/identity/window changes invalidate consent; concurrent job completion fenced.
- Candidate preview only standalone clip; public bytes proxy private blob, no SAS redirect.
- Every new table guarded DDL + RLS; export/erasure remains effective when flag OFF.
- Full Ruff/format/backend/Node/lint/build and relevant Playwright before push.
