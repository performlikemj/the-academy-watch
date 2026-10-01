# UXM1 — scout/player staging polish

- Status: complete including RUXM1 fix round 1; owner Codex; branch fix/staging-ux-scout-player; draft PR #1119 against main; no merge.
- Goal: P-08/P-09/P-10/P-11/P-12/P-27/P-28 plus small additive public-adult community search.
- Constraints: behavior preserved outside fixes; frozen unchanged; no dependencies/migrations; staging read-only; minors/club-private unfindable.
- Done: fixes implemented; read-only staging evidence captured; 16 fixed-view full-page PNGs + detail screenshots visually reviewed.
- Tests (merged main adea5177): full pytest 3645 pass/50 skip; Ruff check + format 553 files pass; Node 227 pass; lint 0 errors/181 existing warnings; build pass. Relevant Playwright 65 pass + final UXM1 22 pass (67 unique); current-season link 2 pass after lint cleanup. OSV scan passed before unchanged frozen-lockfile dependency restore.
- Decision (updated RUXM1F2): /api/seasons display_season labels default desk/player views; unpicked reads omit season to retain server latest-data fallbacks. Every explicit URL/store pick scopes reads and survives links. Backend resolver/frozen behavior unchanged.
- Decision: owner club display reuses accepted invitations; self-reported profile contract uses profile_contract_status instead of contact-routing status.
- Done: merged origin/main adea5177, preserving canonical N3 adult-only search/scout rules; explicit-current deep link survives stored historical season (desktop/mobile regression). Final evidence: 16 exact 1440×900/390×844 viewport PNGs + 16 full-page PNGs + 4 dialog details; no page errors/overflow; visually reviewed. External shots/UXM1/INDEX.md maps each view.
- Cleanup: own backend 5160/frontend 5210 stopped; aw_uxm1 dropped; runtime env/capture script/browser scratch output removed; staging untouched.
- Done: implementation b450b515 + season-link fix 19e038b0 pushed; draft PR https://github.com/performlikemj/the-academy-watch/pull/1119 open. Per-bug hand-back logs/UXM1.final.md marks all 8 assigned items FIXED, plus UXM2 P-21 CTA.
- Next: review draft PR; no outstanding implementation work/decisions.
- Acceptance: each bug evidenced and tested; full pytest, Ruff/format, Node/lint/build/relevant Playwright pass; screenshots reviewed; own servers/aw_uxm1/temp removed.
- Evidence/report: ~/codex-runs/aw-redesign/{shots/UXM1,logs/UXM1.final.md}.

## RUXM1 fix round 1
- Status: complete; all five findings fixed; foreground gates and real backend/browser season + games evidence required.
- Done: server display-season directory contract and all five fixes implemented; frozen resolver unchanged.
- Next: review updated draft #1119; no merge.

- Milestone: all five fixes implemented; directory adds display_season from unchanged stats_season_with_data and includes it in picker rows. Explicit calendar/history requests preserved; community page ignores seasonStore and sends no games season. Unknown/failed scout lookup permits server-authorized composition; header neutral. Map positions + common aliases + short stated fallback. Introductions dedupe both initial selection and Strict Mode replay; Retry available after errors.
- Validation underway: OSV547 clean, Ruff/format558 clean, Node257 pass, lint0errors/180warnings, build pass. New browser regressions pass after Strict Mode dedupe; real Flask+SQLite community multi-season list verified without API mocks; tracked check adjusted to actual array payload. Full pytest + full modern Playwright foreground in progress.
- Main refresh: origin/main e82bb4e3 (#1114) merged642a50d8; only CONTINUITY conflict, both entries retained.
- Real fixture uses disposable SQLite directory aw_uxm1f1_* with production blueprints/SQL; no PostgreSQL database created, no production/staging access.
- Initial full backend:3765pass/50skip plus one old seasons-directory expected-list assertion; the API now correctly includes fixture-backed display season2025. Assertion corrected, focused all5 pass; full final gate restarted. No product-code failure.
- Milestone: implementation627520a0 committed (not pushed pending full pytest); full modern browser215pass/4existing skips, final affected39pass after adding mutation regression. Community game writes now reload displayed totals instead of adopting old-game season. Final Node257/lint0errors180warnings/build green; real frozen Flask/SQLite tracked season+games checks both passed; repeat freezeOFF in progress.
- Real API freezeOFF repeat:2passed; same tracked fixture minutes90 and both community game seasons displayed. All owned backend5160/frontend5210 sessions stopped; disposable SQLite directories removed automatically. Generated dist/browser test-results/reports cleaned; existing dependencies retained.
- Final gates: full pytest3766passed/50skipped (602.56s); Ruff+format558 clean; Node257pass; lint0errors180warnings; build pass. Full modern Playwright215pass/4existing skips plus final affected39pass including one new mutation test (216 unique passes); real freezeOFF2pass, freezeON2pass. No TS/typecheck configuration in JavaScript frontend.
- Cleanup complete: owned servers/SQLite/temp/build/browser output removed; tracked baseline browser report retained; no PostgreSQL DB created. Implementation627520a0; origin/main e82bb4e3 remains ancestor. Delivery: implementation627520a0 pushed with validation ledger d3f8baa7 to draft #1119; remote verified OPEN/DRAFT, PR body updated, no merge. Hand-back logs/UXM1F1.final.md.

## RUXM1V fix round 2
- Status: in-progress; N2 signed-out checking state, N1 implicit-season request defaults, N3 explicit pick survives player link.
- Now: inspect request/label separation and extend mocked/real Flask browser regressions.
- Next: main refresh, foreground full gates, push draft #1119 without merge, hand-back logs/UXM1F2.final.md.
- Milestone: signed-out pill Get verified + login row CTA; request/default label separated; explicit selections preserved. Mocked desktop/mobile and real Flask older shadow15/limited30 regressions added. Main still e82bb4e3; no merge needed.
- Gates underway: Ruff/format558 clean (incl Python fixture); Node257 pass; lint0errors180existing warnings; build pass. Foreground full pytest + lane browser40 running. players.py/tracked_player.py/follow.py byte-identical to origin/main: real no-param baseline retains unchanged main semantics. No dependency/lockfile changes or restores; JS frontend has no typecheck target.
- Initial browser37pass/3 test-assertion failures: modal hides header after delayed lookup; frozen source uses public_match_data wrapper. Corrected assertions; direct real HTTP already confirms shadow15/1200 and limited30/2500 with no param, both0 with explicit display. Full lane rerun40 in progress. Baseline evidence logs/UXM1F2.real-baselines.json.
- Browser final: all40 lane checks pass (36 mocked desktop/mobile +4 real Flask/SQLite, freezeON); real freezeOFF repeat4pass. No API interception in real spec. Implicit shadow15/1200 and limited30/2500 match main; explicit display returns0 and calendar picks persist in links. Full pytest remains in progress with no failures.
