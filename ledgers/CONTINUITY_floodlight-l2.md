# Floodlight L2 — Club Home + player side

## Goal / constraints
- Behaviour-preserving Floodlight restyle; existing APIs, permissions, flags, routes, test IDs unchanged.
- Reuse L0 tokens, utilities, InterestSignup and ComingSoon. No shared primitives or public/scout/admin edits; fix round 1 explicitly assigns App.jsx header to L2.
- Worktree redesign/l2-club-player; local DB aw_rd_l2; backend 5112 / Vite 5182; draft PR to redesign/floodlight.

## State
- complete: Club Home and player restyle implemented, verified and delivered in draft PR #1107.
- Now: draft https://github.com/performlikemj/the-academy-watch/pull/1107 against redesign/floodlight, awaiting integration review.
- Next: orchestrator integration review; no merge or production action. BUS DONE, claims released.
- Cleanup: own 5112/5182 servers stopped; aw_rd_l2 dropped; copied .env, local tokens, seed/capture scripts and temporary media removed. No simulator or manually-created /tmp files; worktree retained.

## Acceptance
- Club Today tasks use existing returned counts only; restyle map/squads/player/match/brand/settings/staff.
- Recruiting and player applications use ComingSoon; staff CRUD exists and stays functional.
- Player onboarding/create, approvals, development remain functional.
- Visually reviewed authenticated screenshots on every touched route at 1440×900 and 390×844.
- Relevant existing tests, lint/build pass; BUS DONE; own servers stopped and DB/env/temp files removed.

## Verification
- OSV clean; frozen dependency restore complete.
- Lint passes (existing 182 warnings), build passes, 193 Node tests pass.
- Relevant Playwright final: 45 passed (1.2m), zero skips/failures. Four old failures fixed in test harnesses only: URL view navigation, roster router context, persisted result wrappers and idempotency IDs.
- Live local flow passes: banner upload/replacement; player photo pending → approved via existing moderator endpoint → published proxy bytes; anonymous minor 404; player reflection → coach review.
- aw_rd_l2 copied and engine host/database asserted before upgrade ch02 → fl01. Synthetic manager/player fixture uses existing guarded sim seed and local token issuer; SMTP/Mailgun disabled.
- Authenticated screenshot walk: 20 routes × desktop/mobile, plus 2 live-action states (42 PNGs); no overflow or page errors. Visually inspected all images.
- Evidence: ~/codex-runs/aw-redesign/shots/L2 and logs/L2-*.
- Initial shared header overlap reported on BUS; resolved under explicit L2 ownership in fix round 1.

## Decisions
- Renewal assigns ShowcaseSection owner blocks to L2; L1 leaves them intact. Owner-only class changes; public rendering remains unchanged.
- No clip publication/selection flow exists in current console; private reels/reports preserved. No invented two-key publication controls/copy.
- Staff CRUD records club structure, explicitly does not grant login access; no invite-by-email functionality added.

## Fix round 1
- complete: origin/redesign/floodlight 8ebc1283 merged cleanly (a3e13a22); retained admin-only chrome.
- All six review items fixed: measured chalk/white text and focus on accepted club colours; darkened active/hover rows; unbroken heading wraps at 390px; singular/plural count helper; connected tree lines without the stray pitch arc; assigned shared signed-in header and phone drawer footer.
- Branding/API/upload/approval/invite/role contracts unchanged. Player hero uses solid primary so decorative stripes cannot reduce contrast.
- Header names truncate at 180px; visitor-only CTA hidden while signed in; local long-name manager/scout/admin checked at 1440/1024/390px. Admin keeps its own chrome.
- Validation: OSV 547 dependencies clean; lint 0 errors / 183 warnings; build; 193 Node; 86 relevant Playwright passes / one existing billing-enabled-build skip; final six review checks rerun after the selected-filter focus rule, all pass. Ruff check/format clean on merged backend (520 files). No separate typecheck script in this JS/JSX project; build compiles it.
- Browser checks independently measure computed text/active/hover/focus contrast; boundary #767676 white text = 4.542:1. 1,476 accepted RGB-grid samples: minimum text 4.5003:1, focus 3.001:1 (logs/L2-r1-colour-audit.json).
- Three inherited billing club-profile fixtures now mock /map and open the existing ?view=profile URL; mutation/fallback/retry assertions preserved and passing.
- Screenshots: 60 fresh PNGs, real lane backend and synthetic manager/adult player/scout/admin; all visually reviewed, no overflow or page errors. 40 route pairs + nine role/header views + eleven edge/focus states; INDEX.md/results-r1-final.json in shots/L2. Prior live-state evidence archived in round0-live.
- Cleanup complete: own servers 5112/5182 stopped; aw_rd_l2 dropped and absence verified; copied env, local auth, seed/capture scripts and temporary media removed. No simulator or manually-created /tmp files; worktree retained.
- Handback: existing draft PR #1107; no merge/deploy. BUS DONE and claims released on delivery.
