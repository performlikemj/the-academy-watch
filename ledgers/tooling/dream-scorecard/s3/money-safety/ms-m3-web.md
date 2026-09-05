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
# MS-M3 — web: SSE frame parsing across chunk boundaries + prepaid-credit billing terms (launch blockers)

Worktree: `/Users/michaeljones/Projects/loanarmy/.worktrees/ms-m3` (branch `fix/ms-m3-web-launch-blockers`, from origin/main).
Files you may touch: `academy-watch-frontend/src/hooks/useGolChat.js`, a new `academy-watch-frontend/src/lib/sse.js` (+ its test), `src/pages/LegalPages.jsx`,
`e2e/billing.spec.mjs` only if a scenario must change, and the frontend test runner config if a unit test needs registering (`scripts/run-tests.mjs`). Nothing else.

## Item 1 — SSE parser (`useGolChat.js:~171-200`)
Today `let eventType = 'token'` is declared INSIDE the read loop, so a chunk that ends right after `event: usage\n` and a next chunk that starts with `data: ...`
misclassifies the frame as `token` (stale balances, lost 402/error/retry behaviour). Build: extract a tiny stateful parser into `src/lib/sse.js`
(`createSseParser(onEvent)` with `.push(chunkText)` and `.flush()`), keeping `eventType`, the pending `data` lines and partial-line buffer OUTSIDE the loop, dispatching
on the blank-line frame boundary per the SSE spec (multiple `data:` lines join with `\n`; `event:` optional → default `message`/`token` as the hook expects; ignore
comments `:`; CRLF tolerant). Use it in the hook. Unit tests (the repo's node test runner: `pnpm test`; look at `scripts/run-tests.mjs` for how tests are discovered):
every split position of a 3-frame sample (usage/token/error), multiple frames in one chunk, a frame split inside a UTF-8 multibyte char (feed bytes through a
TextDecoder with stream:true like the hook does), CRLF, terminal buffered data flushed on `done`. Then the existing e2e billing spec must still pass.

## Item 2 — billing legal copy (`LegalPages.jsx:~99-105` and the Privacy processors/retention sections)
Today section "13. Paid subscriptions" describes auto-renewing subscriptions; the launched paid product is PREPAID GOL CHAT CREDITS (3 free questions, then $20
starter pack + top-ups, no renewal). Replace the `BILLING_TERMS_ENABLED` copy with this owner-drafted text (keep the flag; do not change other sections):
Terms §13 "Prepaid chat credits":
  "Some features — currently the Academy Watch chat assistant — use prepaid credits. New accounts receive a small free allowance. Credit packs are one-time
  purchases processed by Stripe; they do not renew and you will not be charged again unless you buy another pack. One credit is used per question; if a question
  fails before an answer is produced, the credit is returned automatically. Credits have no cash value and cannot be transferred. Unused packs can be refunded
  within 14 days of purchase by emailing mj@bywayofmj.com; refunded credits are removed from your balance. Deleting your account forfeits any remaining credits.
  Pack prices are shown before you buy; later price changes do not affect credits you already hold."
Privacy — processors list: keep the Stripe line; ADD under "What we collect": "Chat assistant usage: when you ask the assistant a question, the question and the
conversation context are sent to our model provider (OpenAI, OpenRouter or Groq) to generate the answer. We keep the question fingerprint, the answer and your
credit ledger (purchases, uses, refunds) with your account." Retention: ADD "Purchase records (pack, amount, Stripe identifiers) are kept for accounting for up to
seven years, in a form no longer linked to a deleted account." Mark nothing else. The web shows this copy only when `VITE_BILLING_TERMS=1`, so it ships dark.
Gates: `pnpm lint && pnpm build`, `pnpm test`, and `pnpm exec playwright test e2e/billing.spec.mjs` if it runs locally without prod (read `playwright.config.js`;
if it needs a backend, run the backend dev server on a FREE port — ports 5001/5173 belong to another session — or skip and say so).
Commit: `fix(web): SSE parser keeps frame state across chunks; billing terms describe prepaid chat credits`.
Push `fix/ms-m3-web-launch-blockers`; open the PR (base main). Do NOT merge.

## CRITIQUE FOLD-IN (overrides anything above that conflicts)
- Parser contract: `.flush()` at EOF DISCARDS an unterminated frame (strict SSE); EOF without a `done` event is NOT success — the hook must mark the assistant
  message incomplete (error state, retry with the same client_msg_id allowed) and must flush the `TextDecoder` (`decoder.decode()` with no args) before
  finalising. Tests: event-only frame followed by a default event, `data:` without a space, multi-line data, comments, CR / LF / CRLF splits including a split
  between CR and LF, every split position of a sample containing usage/token/replace/data_card/history_entries/error/done.
- Hook-level test with a mocked `ReadableStream` that splits real byte chunks and verifies: replacement text, cards, hidden history entries, usage updates,
  same-id retry state on 402/error, incomplete stream ≠ success, and that callbacks from a reset chat cannot update usage/retry state.
- Copy: DROP the seven-year retention sentence (no retention mechanism exists; purchase ledger rows are deleted with the account today). Replace with: "When you
  delete your account, your credit ledger and purchase records are deleted from our systems; Stripe retains its own payment records under its policy."
  ALSO fix the two contradictory lines: the model-provider bullet (~:143) must say chat questions and conversation context are sent to the provider when you use
  the assistant (newsletter generation sends sports data only), and the Stripe paragraph (~:145) must describe what is stored for prepaid credits (Stripe customer
  id, purchase identifiers, amounts, refunds; no card details) instead of "subscription status".
- Refund wording must match the backend policy: "If the assistant fails to complete an answer — an error, or the connection drops before the answer finishes — the
  credit is returned automatically."
- Effective date: add `BILLING_TERMS_EFFECTIVE_DATE` next to `EFFECTIVE_DATE` (~:5) set to "2026-09-15" and render it in the billing section ("Prepaid credit terms
  effective …"); the go-live checklist owner (not you) confirms the date. Do not change the global EFFECTIVE_DATE.
- E2E: `e2e/billing.spec.mjs` mocks every API call (no backend needed). Run it with this worktree's frontend on a FREE port: `pnpm exec vite --port 5199 --strictPort`
  (or the repo's dev command with `--port`), `E2E_BASE_URL=http://127.0.0.1:5199`. Update the dark-copy assertion (~:116) to the new heading and add a lit-copy
  scenario (build/serve with `VITE_BILLING_TERMS=1` on another free port) asserting the prepaid heading is present and "Paid subscriptions"/"renew automatically" are
  absent. State which chat disclosures remain visible when billing is off (they are not flag-gated: the model-provider bullet stays; the credit ledger sentence is
  inside the flag).
