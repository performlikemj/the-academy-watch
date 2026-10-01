# UXM2 — club console / billing staging polish

- Goal: P-13 club, P-17, P-18, P-19, P-20, P-21, P-22, P-25 from SUX staging review.
- Branch: fix/staging-ux-club-misc; worktree uxm2; ports 5161/5211; scratch DB aw_uxm2.
- Constraints: staging read-only; foreground commands; no dependencies/migrations; preserve A2 scope/viewer redaction/minor privacy; no UXM1-owned edits without BUS agreement; draft PR, no merge.
- Sources: DESIGN §§3/6–9; BUS tail; SUX.product-bugs.md; CLAUDE.md; docs/agents/{frontend,backend,invariants,club-staff-access}.md; PHASE2 decision 2.
- Done: instructions/evidence read; START/CLAIM posted; live read-only staging reproduction recorded in external logs/uxm2/staging-readonly.json; OSV clean + frozen dependency restore; first scoped fixes implemented.
- Status: complete.
- Now: draft PR #1123 open; hand-back and cleanup complete.
- Next: review draft PR #1123; no merge authorized.
- Decision: orchestrator BUS 14:29 explicitly authorizes in-scope Coach’s brief writes via players.manage OR feedback; implemented with member scope/redacted response; viewers and analysts denied.
- Gates: Ruff check/format pass (553 files); Node 210 pass; lint 0 errors/181 inherited warnings; build pass. Relevant Playwright 93 pass/1 expected skip + trust desk 1 pass. Final UXM2 20 pass; correction suite 4 pass on isolated rerun after one fixed-delay harness startup flake. Full offline pytest 3645 pass/50 skip/146 warnings (675.74s). No standalone typecheck script/config in this JavaScript frontend; build passes.

- Decision: UXM1 owns P-21 ScoutPage CTA (BUS 05:27 ANSWER); no ScoutPage edits in UXM2.
- DB: read-only pg_dump of sanitized staging into own aw_uxm2; production/provider integrations disabled for local run.

- Milestone: new Playwright 20/20 passed; Node 210/210, lint 0 errors/181 inherited warnings, build, Ruff/format pass.
- Main refresh: origin/main adea5177 (N3 adults-only) fast-forwarded per BUS; interrupted old-base pytest after 991 pass/17 skip to re-run final combined tree.

- Live scratch PostgreSQL/HTTP: relationship names, expired status, current squad without invented dates, coach in-scope 200/out-of-scope 404/viewer+analyst 403, redacted write, plain-text results, descending dates, loan destinations 200/78 all passed. Original brief restored after local authorization check.
- Live-DB full pytest variant: 3647 pass/45 skip/3 inherited radar-contract failures (`peers_count`, `player_percentile`, removed `compute_position_percentiles`); untouched radar tests/service; retained log. Offline CI mode uses existing natural no-DB skips, not custom exclusions.
- Evidence: 40 full-page views + 10 details at 1440×900/390×844; zero 5xx/overflow after matches grid constrained to viewport. 40 exact viewport captures also complete; all 90 PNGs reviewed via contact sheets/details. Screenshot INDEX.md records view/persona/routes. External shots/UXM2 and logs/uxm2.
- P-21 CTA delivered by UXM1 in draft PR #1119 (`logs/UXM1.final.md`); UXM2 product/date changes stay separate.

- Cleanup complete: own 5161/5211 foreground servers stopped; aw_uxm2 dropped (database count 0); own runtime env/token/dump/media and browser scratch outputs removed. Evidence/logs retained.

- Pre-push main moved to e82bb4e3 (B1 directory); merged in 6d8b1957. Sole import-block conflict keeps B1 imports and UXM2 shared date formatter. All UXM2 added/removed lines byte-identical to implementation8667a8bf (external b1-refresh-proof.json); no migration authored/run. Final combined full gates pass, screenshot behavior unchanged with directory flag off.

- B1 refreshed gates: Ruff/format 557 files, Node218, lint0errors/181 inherited warnings/build pass; relevant Playwright94pass/1expected skip in one clean final combined run (4.2m). Full pytest3764pass/50skip/146warnings in798.82s (13m18s). Gate-only Vite5211 stopped; browser outputs and external capture scratch script removed.

- Final B1-refreshed combined gates all pass at code head6d8b1957: pytest3764/50skip; Node218; Playwright94/1expected skip; Ruff-format557; lint0errors/181 inherited warnings/build; no code changes after gates.

- Delivery: [draft PR #1123](https://github.com/performlikemj/the-academy-watch/pull/1123) against main, implementation8667a8bf + main/B1 merge6d8b1957. External logs/UXM2.final.md and shots/UXM2/INDEX.md record per-bug status/evidence. Documentation closure does not alter tested code.
