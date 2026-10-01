# Phase 2 C2 — two-key highlights

## Goal / constraints
- Club picks a server reel window; independent adult self-claimant approves; standalone private clip output; revoke on next request.
- Branch p2/c2-highlights from origin/p2/b3-admin; PR against main stacked on #1115, ready at end; no merge/deploy.
- HIGHLIGHTS_ENABLED default OFF; p2c2 -> real p2c1 ancestor copied verbatim; no placeholder.
- Reuse A1 adult/holds/outbox/audit, A2 capability+byte scope, B1 is_listed. No public minors, youth/mixed footage, raw match SAS or metadata.
- Own ports5151/5202 and scratch aw_p2_c2; foreground only; clean own resources.

## State
- In progress (fix round 1): RC2 F1–F16; foreground gates and scratch database configurable; preserve raw-independent takedown and verified-staff-only safe default.
- Complete: private tables, source fences, capability routes, independent consent, standalone worker+private bytes, outbox, erasure/export and dark web mounts.
- Complete: dependency cut B1811fabca/B216540e03/B3d49ec794/N3adea5177; main B1 squash e82bb4e3 refreshed with byte-identical application/test tree.
- Complete: recording-date DOB checks prevent childhood/unknown/future footage; independent clips survive raw expiry; UTC SQL/ORM guards fence source/date/identity changes and delayed cleanup.
- Complete: UUID leases, concurrent pick/decision/job fencing, late-upload cleanup; public reads recheck both keys/current canonical adult eligibility/holds/suppression/source.
- Gates: final full pytest4285 pass91skip0fail; focused46 + PG5 (combined51 pass1 optional C1-code skip); current C1 canonical overlay integration1 pass.
- Gates: current offline Playwright238 pass4skip incl13 C2 tests; Node219; Ruff check/format594 clean; lint0errors192warnings; Vite build pass; OSV547 clean, unchanged lockfiles.
- Gates: real chain p2c1/p2c2 upgraded; guarded upgrades/preapply twice, RLS4/source guards6, retained downgrade refused, empty rollback/upgraded; real ffmpeg1.001s/video-only/1280px.
- Evidence: 15 reviewed desktop/mobile synthetic-fixture PNGs in ~/codex-runs/aw-redesign/shots/C2; full logs and PR/hand-back in ~/codex-runs/aw-redesign/logs/C2.*.
- Limit: broad legacy browser suite still fails obsolete frozen routes and live email/admin fixtures; current offline suite is green. No provider sends or production data changes.
- Rollout: apply real C1 then C2 schema before deployment; build/schedule independent ffmpeg worker and existing outbox before enabling. Native views are I1, sharing these APIs.
- Delivery: implementation/checks complete; review URL, ready transition and resource cleanup recorded in external C2.final.md/BUS. No further repository changes required for PR publication.

## Acceptance / checks
- Both keys required; revoke removes lists+bytes immediately; minors/unknown ages/private matches blocked.
- Source/identity/window changes invalidate consent; concurrent job completion fenced.
- Candidate preview only standalone clip; public bytes proxy private blob, no SAS redirect.
- Every new table guarded DDL + RLS; export/erasure remains effective when flag OFF.
- Full Ruff/format/backend/Node/lint/build and current Playwright completed before push.
