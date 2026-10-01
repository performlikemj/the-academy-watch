# N3 — scout desk adults only

- Goal: enforce the strict shared public-adult rule across scout reads and additions; remove web/iOS U18 chips.
- Decision: MJ approved hiding under-18s on 2026-10-01; no feature flag.
- Branch: fix/scout-adults-only, from origin/main.
- Constraints: foreground commands only; own ports 5132/5193 and DB aw_n3; never modify shared/prod DB; iOS chip only.
- Impact gate: STOP and BUS ASK if unknown-age exceeds 15% of the existing desk.
- State: complete; non-draft PR #1116 to main: https://github.com/performlikemj/the-academy-watch/pull/1116 . Implementation ab3adf9f.
- Done: read CONTINUITY, CLAUDE, invariants, backend, DESIGN §§6–9 and BUS; confirmed tracked browse lacks unconditional adult rule.
- Impact (aw_n3 clone, 2026-10-01 UTC): desk828 distinct tracked players →744; remove84 = minors36 + unknown/unestablished48 (5.80%); below stop threshold.
- Done: canonical public-adult query/upstream adapters; scout browse/boards/compare/CSV/watchlist/lists/resolve/search; digests/snapshots; global search; GOL cached frames/lookup/suggestions/answers. GOL unverified web tool disabled; prior user questions retained, old assistant/tool data not replayed.
- Done: web/native U18 chip hidden; U21 max20/U23 max22; iOS change ships in next build. Verified self-claim creation/approval rejects unknown DOB and minors; contact requires approved self-claim.
- Validation: Ruff/format pass; OSV/setup pass; frontend lint0 errors/183 existing warnings, build, Node193 pass; Playwright17 pass; iOS232 unit tests pass incl. chip. Local HTTP18 checks pass; 744 exact IDs over8 pages, all5 board phases, CSV, minor/unknown compare and watchlist404; max browse page0.264s. Desktop/mobile screenshots reviewed.
- Validation: first full pytest20 failed/3254 pass/47 skip; adult-only fixtures lacked DOB and old saved-entry assertions changed. Fixed fixtures/policy assertions; focused221 pass + remaining273 pass/1 frozen-tool message assertion (guard ordering corrected).
- Validation: FINAL full pytest3278 passed/47 skipped/116 warnings in250.03s;37 new adults-only regression cases; focused GOL/replay206 pass. Native232, Node193, Playwright17 and Ruff/format533 all pass; lint/build rerun pass. Seven opt-in PostgreSQL tests skipped; separate real aw_n3 HTTP/GOL frame audits pass.
- Done: paid GOL replay fingerprints include current adult-policy revision; stale/pre-policy replay409, no additional debit. Real PostgreSQL verifies every returned player frame is strict-adult.
- Cleanup: owned servers5132/5193 stopped; aw_n3 dropped/absence verified; simulatorD1399891 already Shutdown; own node_modules/dist/test-results/derived data removed; no env copy or /tmp artifact. Tracked Xcode project restored unchanged after accidental artifact cleanup.
- Delivery: report `~/codex-runs/aw-redesign/logs/N3.final.md`; screenshots `~/codex-runs/aw-redesign/shots/N3/`; BUS DONE and all CLAIMs released. PR MERGEABLE; initial CI OSV/backend lint green, remaining jobs running. No merge/deploy; lead reviews/merges.
- Next: lead PR review/merge; native chip in next iOS build.

## Fix round 1 — PR #1116

- State: implemented, validated and pushed; confirmed GitHub Codex P2 fixed and inline finding answered.
- Scope: memoise eligible/ineligible separately from state; audit follow resolver, watchlist/list, GOL and leaderboards for per-row eligibility.
- Gates: query-count regression + existing 37 adults-only cases, full pytest, Ruff/format; push, inline SHA reply and @codex review. No merge.
- Next: implement, validate and deliver `~/codex-runs/aw-redesign/logs/N3F1.final.md`.
- Done: shared namespaced `cached_public_adult_ids` stores positive/negative eligibility; digest state and batched player-follow resolution reuse run cache across lists/pages. Ordinary reads use fresh caches.
- Audit: watchlist and IDs reads batch; list collection/single-list payloads batch; GOL frames batch 500 unique IDs/read, lookup/suggestions batch; scout browse/compare/CSV and all leaderboard phases filter adult universe before pagination/ranking. Remaining scalar checks are single-player writes or one selected GOL lookup.
- Validation: focused adults-only/jobs/follow-graph/pulse digest suite 133 passed (15.19s), including all 37 original adult cases +5 new cases. SQL regression: eight watchers, two players, four pages; eligibility once per player on each of two runs (12 watchlist/mixed SQL queries, 6 list-only).
- Next: full pytest and Ruff/format gates, then commit/push/review delivery.
- Gates: Ruff check + format pass (533 files); diff whitespace clean. Initial full pytest stopped at collection without OPENAI_API_KEY; rerun uses CI-style dummy key with existing offline stubs.
- Validation: FINAL full pytest 3283 passed/47 skipped/116 warnings in 301.93s; all 37 original adults-only cases plus five new query-count/cache cases pass. No code failures. Ruff check/format533 clean.
- Delivery: implementation `0d5c879556b0fccec225498dd29aca2b257ab96a` pushed to fix/scout-adults-only; inline SHA reply https://github.com/performlikemj/the-academy-watch/pull/1116#discussion_r4151312336 . Final-head re-review command: `gh pr comment 1116 --body "@codex review"`.
- Hand-back: `~/codex-runs/aw-redesign/logs/N3F1.final.md`; full gate log `N3F1.pytest.log`. No frontend/iOS/dependency changes; no servers, local/shared/prod DB, temporary env or provider sends used. Foreground commands only.
- Next: Codex/lead PR review; no merge/deploy.

## Fix round 2 — PR #1116

- State: complete; implemented, validated and pushed; confirmed GitHub Codex P2 fixed and inline finding answered. Started from confirmed head a6a3efd5.
- Finding: hidden retained rows exhaust raw 50/list and 200/watchlist caps.
- Scope: count visible rows with batched eligibility; preserve payload fields and all retained/reappearing rows, even above caps; block further additions at/above visible caps.
- Gates: requested capacity/count/reactivation/query-bound regressions; Ruff/format and full pytest; push, inline SHA reply and @codex review; no merge.
- Next: implement and validate; hand-back ~/codex-runs/aw-redesign/logs/N3F2.final.md.
- Done: shared `_visible_follows` predicate for list payload/count and capacity; watchlist capacity batches saved IDs. Existing field names/retention preserved; duplicate checks reuse the loaded follows.
- Validation: focused adults-only/follow-graph/watchlist 143 passed in15.47s. Five new cases cover 50/200 hidden rows +201 additions, visible payloads, reactivation above cap, idempotent watchlist, mixed non-player cap; capacity eligibility exactly one batch/six SQL queries with1 or50/200 rows.
- Next: full pytest and Ruff/format gates, then push/review delivery.
- Gates: FINAL full pytest3288 passed/47 skipped/116 warnings in261.13s; Ruff check + format533 clean; diff whitespace clean. Full log ~/codex-runs/aw-redesign/logs/N3F2.pytest.log. No frontend/iOS/dependency changes.
- Next: commit/push, inline finding4151336631 SHA reply, final-head @codex review and hand-back; no merge.
- Delivery: implementation aa459860e79f60e4c6a83804dfd575e7bd1cf759 pushed to fix/scout-adults-only; inline SHA reply https://github.com/performlikemj/the-academy-watch/pull/1116#discussion_r4151453446 . Final-head re-review command: `gh pr comment 1116 --body "@codex review"`.
- Hand-back: ~/codex-runs/aw-redesign/logs/N3F2.final.md. Foreground commands only; no servers, persistent DB, provider sends or temporary env used. No frontend/native/dependency restore required.
- Next: Codex/lead PR review; no merge/deploy.
