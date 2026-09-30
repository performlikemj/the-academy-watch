# Floodlight L2 — Club Home + player side

## Goal / constraints
- Behaviour-preserving Floodlight restyle; existing APIs, permissions, flags, routes, test IDs unchanged.
- Reuse L0 tokens, utilities, InterestSignup and ComingSoon. No shared shell/primitives or public/scout/admin edits.
- Worktree redesign/l2-club-player; local DB aw_rd_l2; backend 5112 / Vite 5182; draft PR to redesign/floodlight.

## State
- in-progress: Club Home and player restyle implemented and visually reviewed.
- Now: code/evidence verified and cleanup complete; commit/push/draft PR delivery.
- Next: commit/push/draft PR to redesign/floodlight; BUS DONE.
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
- Shared desktop header overlapping Logout with Get early access for long authenticated names reported to L0/orchestrator on BUS; outside lane ownership.

## Decisions
- Renewal assigns ShowcaseSection owner blocks to L2; L1 leaves them intact. Owner-only class changes; public rendering remains unchanged.
- No clip publication/selection flow exists in current console; private reels/reports preserved. No invented two-key publication controls/copy.
- Staff CRUD records club structure, explicitly does not grant login access; no invite-by-email functionality added.
