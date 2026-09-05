# Money-safety stage (MS) — common brief header

Context: The Academy Watch (loanarmy monorepo). An independent review (`ledgers/research/astra-review-2026-09-05.md`, read it — Part 2 "Defects" and the
Appendix) found three P1 defects and three launch blockers that must be fixed BEFORE billing (`BILLING_ENABLED`) is switched on in prod. This stage fixes them.
Read first: `CLAUDE.md`, `docs/agents/backend.md`, `docs/agents/invariants.md` (migrations guard every DDL; RLS on every new public table; naive-UTC timestamps;
dialect-neutral SQLAlchemy; SQLite in-memory tests where `with_for_update` is a no-op), and for web `docs/agents/frontend.md`.
Python: `/Users/michaeljones/Projects/loanarmy/.loan/bin/python` (3.11). Gates (CI): `ruff check academy-watch-backend && ruff format --check academy-watch-backend`;
web: `cd academy-watch-frontend && pnpm lint && pnpm build` and `pnpm test`. Backend pytest is NOT a CI gate — run it yourself and report real counts.

Standing rules: you work alone in the worktree named in your package; stage files by path (never `git add -A`/`.`), never `--no-verify`, never merge, never push to
main, ONE commit unless told otherwise, no ledger/CONTINUITY/docs edits, no secrets printed, no changes outside your package's file list. Do not weaken tests.
Prod: Stripe LIVE keys — never call Stripe for real; tests use fakes/mocks only. Migrations: new revision id given in the package; `down_revision` = current head
(`flask db heads` → expect `s3d1`); guard DDL with existence checks; `ALTER TABLE ... ENABLE ROW LEVEL SECURITY` on every new table (no policies).
Final report contract: diff stat; what you changed and why per item; the exact test/gate output lines; anything odd or unfinished; commit sha; PR URL.
Money-path lifecycle attacks the checker WILL run (design for them): duplicate/out-of-order/concurrent webhook events, partial refunds, config changes between
checkout and fulfilment, payment completing after account deletion, client replay of the same request, process death mid-stream.
