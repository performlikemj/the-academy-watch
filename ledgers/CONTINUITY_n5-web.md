# N5 — cleat loader and trial time-zone picker

- Goal: shared inline SVG club-colour cleat loader + accessible region-grouped searchable time-zone picker.
- Status: implementation complete; delivery follows on feat/cleat-loader-tz-picker against main784b1490.
- Constraints: frontend only; no new dependencies or lockfile changes; foreground commands; Academy Watch logo untouched. Renewal alone releases after review duel READY + green CI.
- Done: 2px side-profile boot with studs, smooth six-club 7.2s loop (1.2s per colour), still club green under reduced motion; request-free 2,035-byte boot snapshot generated from shared primitives.
- Done: App/Suspense + full loading surfaces in PlayerPage, ProgramPage, MyClub, MyClubConsole and Scout comparison use CleatLoader. Current web had no wing/flap animation assets; logo assets preserved. Button spinners and content skeletons retain their distinct existing functions.
- Done: Radix/cmdk picker lives inside the native editor dialog; canonical regions, city/current UTC offset, direct city/IANA/legacy-alias search, keyboard/pointer selection, empty-search and Escape/focus restoration. Saved program.timezone wins for new posts when returned; otherwise browser zone; existing post zone wins on edit. Existing locking and zone-specific date conversion retained.
- Gates: OSV547 clean before frozen dependency restore; lint0errors186 inherited warnings; Vite build pass; Node225/225; Playwright64/64 (11 N5 + opportunities32 + club/player4 + club-review6 + navigation11). Logs in ~/codex-runs/aw-redesign/logs/N5.{lint,build,node,playwright}.log.
- Typecheck: no standalone typecheck configured (JavaScript project); Vite build validates compilation.
- Screenshots: all six full-page PNGs reviewed at1440×900/390×844 in ~/codex-runs/aw-redesign/shots/N5; no overflow; loading chalk/night + picker open.
- Test scope: browser API responses intercepted; no backend edits, migration, DB creation or backend tests required. Owned Vite5192 stopped by foreground test supervisor; no backend5133 started.
- Now: local implementation/gates complete. Delivery/review/CI status is recorded in ~/codex-runs/aw-redesign/logs/N5.final.md and BUS.md.
- Next: independent REVIEW-DUEL at delivered head; renewal releases only after both READY + green CI. No builder merge or deploy.
