# CONTINUITY — Coach's brief (Track C) · positioning (Track P) · merge signals (Track M)

Directive: `ledgers/DIRECTIVE_coach-brief.md` (authored 2026-09-02; MJ chose "brief first").
Parent: `CONTINUITY.md` §Now 2026-09-02. Related: `DIRECTIVE_evidence-bench.md` (E2/E3), `CONTINUITY_video-analysis.md`.

## State
- 2026-09-02: directive authored from a codex read-only recon of main `bea9ec6`, then REVISED after a codex critique (21 findings, 11 blockers folded in: columns-on-owning-rows, hash+index persistence, evidence_found/no_evidence verdicts, fixture bridge for match 4, brief.json separate from the team pass, synthetic-only sims);
  decisions D1–D5 pending MJ. Nothing built yet.
- 2026-09-02: B1 dev-only fixture bridge implemented and verified on `feat/dev-club-fixture-bridge`: 53 requested backend tests pass; backend-wide Ruff check/format clean; PR #975 open and unmerged. Child ledger `CONTINUITY_dev-club-fixture-bridge.md`. No basecamp/prod execution.

## Next
- Review/merge B1 PR #975, then Fable runs it on basecamp after C1 merges.
- C1 migration `cb01` + club brief routes → C2 worker context + prompt/schema/gate → C3 MyClub editor + reel block
  (+ P1 camera-class fields) → match-4 regen with MJ's three briefs = acceptance.
- P2 calibration research + M1 merge scorer on basecamp in parallel (one codex brief each).

## Gotchas carried in
- Briefs are club-private: only `@require_club_manager()` routes; never in exports/manifests/sim reports.
- No negative verdicts (`seen | no_evidence` only); no names to the model.
- Deploys never migrate: pre-apply `cb01` on prod via the pooler and on basecamp's seeded DB before the regen.
