# Phase 2 C4 — scout attendance / Today / distance

- Owner: /root; branch p2/c4-scout-attend, stacked on #1115; no merge/deploy.
- State: in-progress — implementation, live local HTTP/browser and PostgreSQL race/migration checks passed; final broad gates and dependency refresh.
- Constraints: SCOUT_ATTEND_ENABLED default OFF; p2c3 -> p2c2; scratch-only missing ancestors; no applicants exposed to scouts; adult sessions only on scout tab; approved club pins; visitor coordinates in POST bodies only.
- Done: inspected PHASE2/DESIGN/BUS/P2R §2, repo agent docs and N04/N08/N15/N16 mockups.
- Done: isolated C4 backend/web flows, capability-scoped Today, POST distance, atomic outbox/audit, privacy/retention; real C1/C2 revisions copied; B3F3 integrated.
- Now: full CI-equivalent pytest + full Playwright; latest B1/B2 fixes; review screenshots and final code.
- Next: scoped negative/concurrency/outbox/privacy/migration checks; web flows; full local gates; reviewed desktop/mobile shots/C4; draft PR against main, then ready; C4.final.md and cleanup.
- Acceptance: verified scouts request one published event; club accepts/declines; rate limit/audit/transactional outbox; Today only permitted queues; distance from latest approved pin; flag-off parity.
- Tests: focused C4 SQLite/PG 30 pass; duplicate submission and competing decision locks pass; guarded C1/C2/C4 upgrades twice, C4 preapply twice + RLS/downgrade checks pass; Node 219 pass, lint 0 errors (195 warnings), Vite build pass; browser regression 44 pass + live local desktop/mobile 6 screenshots. Full gates running.
