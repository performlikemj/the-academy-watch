# N3 — scout desk adults only

- Goal: enforce the strict shared public-adult rule across scout reads and additions; remove web/iOS U18 chips.
- Decision: MJ approved hiding under-18s on 2026-10-01; no feature flag.
- Branch: fix/scout-adults-only, from origin/main.
- Constraints: foreground commands only; own ports 5132/5193 and DB aw_n3; never modify shared/prod DB; iOS chip only.
- Impact gate: STOP and BUS ASK if unknown-age exceeds 15% of the existing desk.
- State: in-progress; implementation and all local gates complete; publication pending.
- Done: read CONTINUITY, CLAUDE, invariants, backend, DESIGN §§6–9 and BUS; confirmed tracked browse lacks unconditional adult rule.
- Impact (aw_n3 clone, 2026-10-01 UTC): desk828 distinct tracked players →744; remove84 = minors36 + unknown/unestablished48 (5.80%); below stop threshold.
- Done: canonical public-adult query/upstream adapters; scout browse/boards/compare/CSV/watchlist/lists/resolve/search; digests/snapshots; global search; GOL cached frames/lookup/suggestions/answers. GOL unverified web tool disabled; prior user questions retained, old assistant/tool data not replayed.
- Done: web/native U18 chip hidden; U21 max20/U23 max22; iOS change ships in next build. Verified self-claim creation/approval rejects unknown DOB and minors; contact requires approved self-claim.
- Validation: Ruff/format pass; OSV/setup pass; frontend lint0 errors/183 existing warnings, build, Node193 pass; Playwright17 pass; iOS232 unit tests pass incl. chip. Local HTTP18 checks pass; 744 exact IDs over8 pages, all5 board phases, CSV, minor/unknown compare and watchlist404; max browse page0.264s. Desktop/mobile screenshots reviewed.
- Validation: first full pytest20 failed/3254 pass/47 skip; adult-only fixtures lacked DOB and old saved-entry assertions changed. Fixed fixtures/policy assertions; focused221 pass + remaining273 pass/1 frozen-tool message assertion (guard ordering corrected). Final full run next.
- Validation: FINAL full pytest3278 passed/47 skipped/116 warnings in250.03s;37 new adults-only regression cases; focused GOL/replay206 pass. Native232, Node193, Playwright17 and Ruff/format533 all pass; lint/build rerun pass. Seven opt-in PostgreSQL tests skipped; separate real aw_n3 HTTP/GOL frame audits pass.
- Done: paid GOL replay fingerprints include current adult-policy revision; stale/pre-policy replay409, no additional debit. Real PostgreSQL verifies every returned player frame is strict-adult.
- Cleanup: owned servers5132/5193 stopped; aw_n3 dropped/absence verified; simulatorD1399891 already Shutdown; own node_modules/dist/test-results/derived data removed; no env copy or /tmp artifact. Tracked Xcode project restored unchanged after accidental artifact cleanup.
- Next: non-draft PR; BUS DONE/report; final ledger delivery commit.
