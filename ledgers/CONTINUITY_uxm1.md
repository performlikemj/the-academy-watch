# UXM1 — scout/player staging polish

- Status: complete; owner Codex; branch fix/staging-ux-scout-player; draft PR #1119 against main; no merge.
- Goal: P-08/P-09/P-10/P-11/P-12/P-27/P-28 plus small additive public-adult community search.
- Constraints: behavior preserved outside fixes; frozen unchanged; no dependencies/migrations; staging read-only; minors/club-private unfindable.
- Done: fixes implemented; read-only staging evidence captured; 16 fixed-view full-page PNGs + detail screenshots visually reviewed.
- Tests (merged main adea5177): full pytest 3645 pass/50 skip; Ruff check + format 553 files pass; Node 227 pass; lint 0 errors/181 existing warnings; build pass. Relevant Playwright 65 pass + final UXM1 22 pass (67 unique); current-season link 2 pass after lint cleanup. OSV scan passed before unchanged frozen-lockfile dependency restore.
- Decision: use /api/seasons directory explicitly for current desk/player reads; preserve existing backend resolver and frozen behavior.
- Decision: owner club display reuses accepted invitations; self-reported profile contract uses profile_contract_status instead of contact-routing status.
- Done: merged origin/main adea5177, preserving canonical N3 adult-only search/scout rules; explicit-current deep link survives stored historical season (desktop/mobile regression). Final evidence: 16 exact 1440×900/390×844 viewport PNGs + 16 full-page PNGs + 4 dialog details; no page errors/overflow; visually reviewed. External shots/UXM1/INDEX.md maps each view.
- Cleanup: own backend 5160/frontend 5210 stopped; aw_uxm1 dropped; runtime env/capture script/browser scratch output removed; staging untouched.
- Done: implementation b450b515 + season-link fix 19e038b0 pushed; draft PR https://github.com/performlikemj/the-academy-watch/pull/1119 open. Per-bug hand-back logs/UXM1.final.md marks all 8 assigned items FIXED, plus UXM2 P-21 CTA.
- Next: review draft PR; no outstanding implementation work/decisions.
- Acceptance: each bug evidenced and tested; full pytest, Ruff/format, Node/lint/build/relevant Playwright pass; screenshots reviewed; own servers/aw_uxm1/temp removed.
- Evidence/report: ~/codex-runs/aw-redesign/{shots/UXM1,logs/UXM1.final.md}.

## RUXM1 fix round 1
- Status: in-progress; five findings accepted; foreground gates and real backend/browser season + games evidence required.
- Now: implement server display-season directory contract; retain frozen resolver; correct community games, scout verification, positions and introductions.
- Next: merge moved main if needed, run all gates, push draft #1119, clean owned resources, hand back UXM1F1.final.md.
