# N1 — simplify header navigation

- Goal: exact primary/account/mobile navigation requested by MJ; preserve routes, auth and admin key controls.
- Status: complete; non-draft PR #1111 against main: https://github.com/performlikemj/the-academy-watch/pull/1111.
- Constraints: frontend only; no new dependencies; disposable aw_n1 and ports 5130/5195; non-draft PR to main explicitly authorized.
- Done: More removed; Clubs/Players/Scouts/Opportunities primary; Search icon opens existing search; Radix account menu with ordered/gated account and role links, logout and 180px name truncation. Mobile drawer shares account items; admin key badge/popover/dialog preserved; Pricing added to footer; routes untouched.
- Validation: OSV zero findings; lint zero errors (183 pre-existing warnings); build passes; Node 193/193; relevant Playwright 52 pass/1 expected build-flag skip (navigation, foundation, club review, billing); final screenshot run 8/8, changed screenshot test lint clean. JavaScript frontend has no configured typecheck command.
- Screenshots: eight full-page PNGs visually reviewed at 1440×900 and 390×844 in ~/codex-runs/aw-redesign/shots/N1/. Home route, synthetic mocked visitor/scout/manager/admin accounts; desktop account menus and mobile drawers open. Capture animations disabled so all controls are visible.
- Test edits: mobile foundation asserts four primary links; long-name/logout and billing identity-switch journeys use account menu; auth helper opens account dropdown; Node contact-gate assertions reflect new account list.
- Cleanup: own servers stopped; aw_n1 dropped/absence verified; copied .env, temporary review sheets and Playwright artifacts removed. Worktree retained; no production access/provider sends.
- Notes: initial Node source assertions updated; concurrent Playwright artifact collisions resolved by one combined run. No unresolved failures.
- Delivery: code commit 17cd3743 pushed to feat/nav-simplify; requested PR title applied; no remaining implementation work.
