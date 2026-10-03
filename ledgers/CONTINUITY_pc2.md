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
