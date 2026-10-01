# Phase 2 C2 — two-key highlights

## Goal / constraints
- Club picks a server reel window; independent adult self-claimant approves; standalone private clip output; revoke on next request.
- Branch p2/c2-highlights from origin/p2/b3-admin; PR against main stacked on #1115, ready at end; no merge.
- HIGHLIGHTS_ENABLED default OFF; p2c2 -> p2c1 (scratch placeholder never committed).
- Reuse A1 adult/holds/outbox/audit, A2 capability+byte scope, B1 is_listed. No public minors, youth/mixed footage, raw match SAS or metadata.
- Own ports5151/5202 and scratch aw_p2_c2; foreground only; clean own resources.

## State
- Done: read Phase2/design/BUS/P2R5 and repo guidance; verified clean branch/base.
- Now: trace reviewed reel windows, snapshot worker and privacy lifecycle; define C2 contract.
- Next: backend+worker; web surfaces; security/browser/PG/full gates; screenshots; PR ready+hand-back.

## Acceptance / checks
- Both keys required; revoke removes lists+bytes immediately; minors/unknown ages/private matches blocked.
- Source/identity/window changes invalidate consent; concurrent job completion fenced.
- Candidate preview only standalone clip; public bytes proxy private blob, no SAS redirect.
- Every new table guarded DDL + RLS; export/erasure remains effective when flag OFF.
- Full Ruff/format/backend/Node/lint/build and relevant Playwright before push.
