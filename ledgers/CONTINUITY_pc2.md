# PC2 — one set of scout numbers
- Owner: /root; branch feat/pc2-one-set-of-numbers; base 3d4cf2b1 (PR1131).
- Binding brief: ~/codex-runs/aw-redesign/briefs/PC2.directive.md.
- State: in-progress; recon/CONTRACT posted to BUS before build.
- Constraints: no schema change, production operations, provider calls or merge; foreground governed checks.
- Decision: shared merge_match_lines + season_totals; preserve provider totals; correct old reported cells before rank/page via batched projection.
- Acceptance: all-surface mixed fixture equality; approved-only card enrichment; 50-row query counts; off-container resumable/throttled rebuild proof on aw_pc2; staging persona table; four final-head cached gates; lane/browser; ready PR to main after1131; bounded CI.
- Now: implement canonical reported totals/read projection.
- Next: rebuild and fixture proofs, validation, push/PR and hand-back.

- Milestone: canonical reported totals/write path + pre-rank old-cell projection + approved card fields + counters implemented.
- Milestone: cross-surface fixture (Kofi/Reuben/Emeka/keeper/empty/mismatch-double-header/provider) compares all listed endpoints before/after rebuild, across 4 flag/freeze combinations.
- Verification: original Scout64 + match-line20 PASS; new equality/rebuild6 PASS before widening to all8 stats. Query budget: baseline50=11; corrected1=16; corrected50=16 (constant).
- Verification: targeted rollup/freeze164 passed with6 expected/compatibility failures; provider adapter preserved and deliberate whole-source assertions revised; next run169passed/1 stale baseline fixture failure (fixed).
- Verification: OSV PASS; frozen-lock frontend restore complete; no lockfile change.
- Now: PostgreSQL nullable VALUES typing fixed; all8 stats checks + rebuild CLI proof + final-head validation pending (governor queue).

- Milestone: provider missing-rollup compatibility now reuses four batch feeders; all8-stat PostgreSQL matrix10 PASS. 50-row queries11->17, 1/50 both17.
- Verification: targeted rollup/data172 PASS (2 new missing-provider compare failures fixed then PG10 PASS); Scout/privacy/match250 PASS with one stale query cap, updated cap focused2 PASS.
- Verification: touched PC browser spec run ONCE:81 PASS/2 optional captured-staging SKIP; auto Vite stopped.
- Rebuild proof: aw_pc2 full model schema,54 entries/6 identities/11 cells/6 totals. Dry6/5/5 in0.487s; batch2/resume4; repeat6/0/0; rollback5/restored6/5/5. No production.
- Before/after proof: real base3d4cf2b1 route code vs current code on identical fictional PostgreSQL fixture; external PC2-before.json / PC2-after.json / PC2-surfaces.json.
- Decision: colour fallback examined: no page passes club palette; provider Team has no palette. Report to SD/ORCH; no extra payload/design scope.
- Now: final lint/commit and four cached gates, push ready PR, bounded CI; exact delivery authoritative in external logs/PC2.final.md.

- Cleanup: aw_pc2 dropped; port5247 has no listener; no simulator owned.
- Delivery: PC1131 released on mainf18abf6b; refresh onto that main before final-head gates.

- Main refresh: merged origin/mainf18abf6b; conflicting PC files are byte-identical to base3d4cf2b1 on main, kept tested PC2 versions; both ledger histories/GOL pattern retained. Browser product/spec blobs unchanged from the single81-PASS run.

- Final-gate audit on013fc52a: frontend390/lint-build + backend-lint641 PASS; backend5132 PASS/1716 SKIP/3 FAIL (two stale C1 SQL counts and provider-only historical guard).
- Fixes: C1 alias before/after policy parity preserved with updated bounded PC2 query baseline25; restored provider-only historical validation.
- Additional audit: reproduced cache4/360 being replaced by own1/120/20 goals; fixed batched provider-cache fallback/write retention, also after removing last report. Orphan reported cells no longer headline; worldwide saved shadow seasons/unknown metrics align. matches classified as reported by player UI, browser mocks updated to current contract.
- Verification current fixes: targeted224 PASS + node player-card33 PASS; PG23/latest CLI/browser/four new-head cached gates next.

- Verification final code: targeted224 PASS; real PostgreSQL23 PASS (16 equality combinations + budget/rebuild/orphan/shadow/cache-retention controls).
- Final CLI rehearsal:6/5/5 dry0.499s; first2/2/2 0.285s; resume4/3/3 0.415s; repeat6/0/0 0.497s; undo5; restored6/5/5 0.487s. Scratch dropped again.
- State: implementation/targeted proof complete; commit final fixes, then four cached gates and the touched browser spec once on this final head (fixture now models matches source). Push/ready PR/CI/duel delivery recorded externally.

- Final40317628 full audit:5142 PASS/1716 SKIP/6 FAIL, all two legacy scout fixtures with orphan reported totals. Added raw match rows; source-filter control now explicitly proves provider wins before testing club-only category. Product code unchanged. Touched browser40317628:81 PASS/2 optional SKIP (1.8m); retained for this fixture-only successor.
- Now: focused scout fixture validation, final fixture-only commit/push; four cached gates once at successor head; bounded CI and exact receipts in external hand-back.
- Focused fixture verification: scout blueprint/watchlist102 PASS; ruff format/check PASS. No browser/product changes since81-PASS run.
- Runbook audit: corrected stale missing-provider query bound4->5 (four existing feeders plus cache fallback); matches implementation and external hand-back. Documentation-only successor; current90df2ed0 full run finishes normally before successor gates. Browser/product/test blobs unchanged.
