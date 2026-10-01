# UXM1 — scout/player staging polish

- Status: in-progress; owner Codex; branch fix/staging-ux-scout-player.
- Goal: P-08/P-09/P-10/P-11/P-12/P-27/P-28 plus small additive public-adult community search.
- Constraints: behavior preserved outside fixes; frozen unchanged; no dependencies/migrations; staging read-only; minors/club-private unfindable.
- Done: fixes implemented; read-only staging evidence captured; 16 fixed-view full-page PNGs + detail screenshots visually reviewed.
- Tests: focused pytest 33 pass + search privacy 11 pass; Node 227 pass; lint 0 errors/181 existing warnings; build pass; relevant Playwright 61 pass. Initial full pytest 3566 pass/50 skip; final UXM1 Playwright 20 pass (63 unique relevant tests across runs).
- Decision: use /api/seasons directory explicitly for current desk/player reads; preserve existing backend resolver and frozen behavior.
- Decision: owner club display reuses accepted invitations; self-reported profile contract uses profile_contract_status instead of contact-routing status.
- Now: initial gates complete; integrate origin/main adea5177 (N3 adult-only scout policy) and re-gate final combined head.
- Next: scoped commit/push/draft PR; stop own servers/drop aw_uxm1/remove runtime env and screenshot scratch script.
- Acceptance: each bug evidenced and tested; full pytest, Ruff/format, Node/lint/build/relevant Playwright pass; screenshots reviewed; own servers/aw_uxm1/temp removed.
- Evidence/report: ~/codex-runs/aw-redesign/{shots/UXM1,logs/UXM1.final.md}.
