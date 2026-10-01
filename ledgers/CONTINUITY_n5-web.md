# N5 — cleat loader and trial time-zone picker

- Goal: shared inline SVG club-colour cleat loader + accessible region-grouped searchable time-zone picker.
- Status: implementation complete; delivery follows on feat/cleat-loader-tz-picker against main784b1490.
- Constraints: frontend only; no new dependencies or lockfile changes; foreground commands; Academy Watch logo untouched. Renewal alone releases after review duel READY + green CI.
- Done: 2px side-profile boot with studs, smooth six-club 7.2s loop (1.2s per colour), still club green under reduced motion; request-free boot snapshot generated from shared primitives.
- Done: App/Suspense + full loading surfaces in PlayerPage, ProgramPage, MyClub, MyClubConsole and Scout comparison use CleatLoader. Current web had no wing/flap animation assets; logo assets preserved. Button spinners and content skeletons retain their distinct existing functions.
- Done: Radix/cmdk picker lives inside the native editor dialog; canonical regions, city/current UTC offset, direct city/IANA/legacy-alias search, keyboard/pointer selection, empty-search and Escape/focus restoration. Saved program.timezone wins for new posts when returned; otherwise browser zone; existing post zone wins on edit. Existing locking and zone-specific date conversion retained.
- Gates: OSV547 clean before frozen dependency restore; lint0errors186 inherited warnings; Vite build pass; Node225/225; Playwright64/64 (11 N5 + opportunities32 + club/player4 + club-review6 + navigation11). Logs in ~/codex-runs/aw-redesign/logs/N5.{lint,build,node,playwright}.log.
- Typecheck: no standalone typecheck configured (JavaScript project); Vite build validates compilation.
- Screenshots: all six full-page PNGs reviewed at1440×900/390×844 in ~/codex-runs/aw-redesign/shots/N5; no overflow; loading chalk/night + picker open.
- Test scope: browser API responses intercepted; no backend edits, migration, DB creation or backend tests required. Owned Vite5192 stopped by foreground test supervisor; no backend5133 started.
- Now: local implementation/gates complete. Delivery/review/CI status is recorded in ~/codex-runs/aw-redesign/logs/N5.final.md and BUS.md.
- Next: independent REVIEW-DUEL at delivered head; renewal releases only after both READY + green CI. No builder merge or deploy.

## N5 redraw round (renewal BUS ANSWER 2026-10-01 19:00)

- Done: right-facing low-cut football boot with open ankle dip/tapered toe, solid club-colour upper, contrasting collar/laces, defined soleplate and five blades. Gold heel accent in black/gold phase; ink laces for orange/sky, chalk laces for dark colours.
- Done: six1.2s phases =1s hold+200ms ease; reduced motion still green with all three animations disabled. Shared request-free inline snapshot regenerated (3180 bytes); component API/caption/accessibility/picker/routes/logo unchanged.
- Gates: lint0errors186 inherited warnings/build/Node225/Playwright64 pass; logs N5F1.{lint,build,node,playwright}.log. Browser verifies solid fill, hold/transition boundaries, every palette phase, gold heel/contrasting laces and reduced motion.
- Shots:30 full-page PNGs —4 chalk/night × desktop/phone defaults,24 phase frames,2 preserved picker shots. All24 phases reviewed in logs/N5F1.phase-review.png. Paths/CSS/palette/timing exported verbatim to logs/N5F1.loader.json for I1.
- Now: redraw round complete; push/delivery head and CI status in logs/N5F1.final.md and BUS.
- Next: REVIEW-DUEL on post-redraw head; renewal alone releases after both READY +green CI. No merge/deploy; own Vite5192 stopped.

## N5F2 review-duel fix round

- Status: implementation complete; final gate/push/cleanup receipts are maintained in `~/codex-runs/aw-redesign/logs/N5F2.final.md` (delivery ledger).
- Scope: O1 Medium + X1/O3/O4/O5/O6/O8 Small; all four RN5 reports read. O2 unrelated page/section spinners and O7 last-post default excluded by lead/reviewer evidence; accepted low-cut boot/palette unchanged.
- Done O1: total offset helper; unsupported zones skipped; missing shortOffset yields name-only labels; absent selected option retains canonical trigger string. Four browser create/edit/save compatibility regressions and unsupported saved-zone regression.
- Done X1/O3: generated inline body margin/background reset; blocked external stylesheet viewport regression; five contextual loader call sites hide the visual caption, retaining accessible Loading status.
- Done O4/O5/O6: current canonical row initialized/scrolled into view, immediate Enter retains it; exact UTC excludes universal offset labels while aliases/signed offsets remain searchable; ink active ring, bounded three-row minimum and short-viewport room above the field.
- Done O8: one bounded minute cache per browser session; repeat opens reuse313 offset formatters, next minute refresh tested. Resume6xCPU warm opens606/550/422ms (local instrumentation, no device guarantee).
- Reversed reviewed source: three new Node failures +12 browser failures reproduced before fixes. Before pause: focused compatibility/current-selection/loading9 pass, Node229 pass, OSV547 clean, lint0errors186 inherited warnings/build, Ruff/format579 and migrated opportunity PostgreSQL19 pass8.04s; scratch aw_p2_b2 dropped.
- Resume: MJ pause interrupted full pytest at71% and browser after17 checks; these are not claimed passed. Governed remaining targeted4 pass11.5s. Screenshot picker captures use viewport bounds so native-modal placement stays faithful.
- Integration: origin/main784b1490 already included after fetch/merge; no lower stacked lane, backend/schema/dependency change or migration CONTRACT.
- Final gates: backend-full/backend-lint/frontend-unit/frontend-build through governor cache on the final commit; relevant Playwright77 in a foreground owned-server supervisor. Exact results/cache keys/logs and reviewed screenshot index live in the delivery ledger.
- Next: pushed PR1125 independent review duel + exact-head CI; renewal/MJ alone releases. No builder merge/deploy. Owned5294 is stopped by supervisor; final cleanup receipt in delivery ledger.
