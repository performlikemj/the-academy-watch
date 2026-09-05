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
# MS-M1 — backend money safety (GOL replay, refund-before-grant, purchase snapshot, late payment after deletion)

Worktree: `/Users/michaeljones/Projects/loanarmy/.worktrees/ms-m1` (branch `fix/ms-m1-money-safety`, from origin/main).
Files you may touch: `academy-watch-backend/src/services/gol_credits.py`, `src/routes/gol.py`, `src/services/stripe_billing.py`, `src/models/gol_credits.py`,
`src/models/billing.py`, `src/routes/billing.py` (only if checkout creation lives there), `src/services/account.py` (deletion path only), ONE new migration
`migrations/versions/s3e1_money_safety.py` (down_revision `s3d1`), tests `tests/test_gol_credits.py`, `tests/test_billing.py`, and new test files. Nothing else.

## Item 1 — GOL question replay must not re-run the model (P1)
Today (`gol_credits.py:83` `reserve_question`, `gol.py:~75-135`): a repeated `client_msg_id` whose debit is unreversed returns `debited=False` and the route
STILL runs `service.chat(...)` again. Also `question_hash` covers only the normalised message, so history/session can change under the same id, and
`refund_question(g.user, client_msg_id)` compensates "the latest" debit rather than the exact attempt.
Build (smallest correct mechanism):
- New table `gol_chat_executions` (id, user_account_id FK, client_msg_id (64), attempt int, debit_id FK→gol_credit_ledger nullable, status in
  ('running','completed','failed'), input_hash (64), response_text TEXT nullable, response_meta JSON/Text nullable (the terminal non-token events, e.g. cards),
  created_at, completed_at; UNIQUE(user_account_id, client_msg_id, attempt); RLS enabled). Naive-UTC timestamps.
- `input_hash` = sha256 over a canonical JSON of {normalised message, normalised history (role+content), session_id}. `reserve_question` receives it as
  `question_hash` (rename param or keep name; store it in `debit.note` as today AND in the execution row).
- Route flow when billing is enabled and the caller is not admin:
  a. reservation with `debited=True` → create execution row `running` in the same transaction as the debit (or immediately after, before streaming).
  b. reservation replay (`debited=False`, existing unreversed debit): look up the execution for (user, client_msg_id, attempt):
     - `completed` → stream `usage` then a single `replace` (or the existing terminal event type the web hook understands — read `useGolChat.js` events:
       token/replace/usage/error/... and use what renders a full answer) with the stored `response_text`, then whatever `done` event exists. Do NOT call the model.
     - `running` and started < 5 min ago → HTTP 409 `{"error":"in_flight"}` before any SSE.
     - `running` older than 5 min, `failed`, or missing → allow ONE re-run without a new debit (mark the old row failed, create attempt-scoped execution again).
  c. On stream completion: persist `response_text` (accumulated token content, with `replace` events replacing it) + meta, `completed_at`, status completed.
     On error/exception: status failed, and compensation refunds the EXACT debit id (`refund_question(user, client_msg_id, attempt=...)` — add the attempt/debit id
     parameter; keep old signature working for callers that pass none by resolving to the reservation's attempt).
  d. Different `input_hash` for a known `client_msg_id` → 409 `client_msg_id_reused` (as today).
- Admin (`exempt`) and billing-disabled paths: unchanged (no execution rows).
Tests (SQLite, mock `GolService.chat` with a call counter): replay after exhaustion returns the stored answer and the counter does not increase; in-flight → 409;
history change under the same id → 409; error mid-stream refunds the exact attempt and a retry with the same id creates attempt 2; process-death simulation
(running row older than 5 min) allows one re-run without a new debit.

## Item 2 — refund arriving before the grant must not be lost (P1)
Today (`stripe_billing.py:~789-800`): `charge.refunded` with no grant row returns False → webhook stored as terminal `ignored`; a later grant is never reversed.
Build: new table `gol_refund_holds` (id, stripe_payment_intent_id UNIQUE, amount_refunded_cents int, stripe_event_id, created_at, applied_at nullable,
applied_grant_id FK nullable; RLS enabled). On `charge.refunded` with no grant: upsert the hold with the CUMULATIVE `amount_refunded` from the charge object and
return True (processed). In `_apply_gol_checkout` after `grant_purchase(...)` (same user lock): if a hold exists for the payment intent, call `apply_refund`
with the cumulative amount, mark the hold applied. Keep today's path when the grant already exists. Tests: refund→grant order ends with the same balance as
grant→refund; duplicate refund events are no-ops; partial then full refund; concurrent-looking sequences (grant and refund events processed back-to-back).

## Item 3 — snapshot the purchased pack at checkout (launch blocker)
Today `_apply_gol_checkout` grants `offered_packs()[row.price_code]["credits"]` at fulfilment time. Add to `billing_checkout_sessions`: `snapshot_credits` int,
`snapshot_unit_amount_cents` int, `snapshot_currency` (3), `snapshot_stripe_price_id` (255) — all nullable (legacy rows). Fill them where the GOL checkout row is
created (find it: grep `product_code="gol"` / `create_checkout` in `stripe_billing.py`/`routes/billing.py`). Fulfil from the snapshot when present; if
`amount_total` ≠ snapshot amount, still grant the snapshot credits but log a warning with session id (never abort a paid purchase); legacy rows without a
snapshot fall back to the current pack (today's behaviour). Tests: pack credits changed between checkout and webhook → customer gets the snapshot; pack removed
from config → still fulfilled from the snapshot.

## Item 4 — GOL payment completing after account deletion must not 500 forever (P2)
Today `_apply_gol_checkout` raises `unresolvable_credit_purchase` (500) when the checkout row/user is gone (account deletion cascades `billing_checkout_sessions`,
`account.py:~866`). Policy (owner-approved): acknowledge and record for manual refund — do not recreate the account. Build: when the row or user is missing for a
payment-mode session, write a `ProductEvent(event_name="gol_orphaned_purchase", props={session_id, payment_intent, amount_total, currency})` and return False
(webhook → `ignored`, HTTP 200) with a `logger.warning`. Test: delete the account (use the real deletion service), then deliver `checkout.session.completed` → 200,
event ignored, product event written, no exception.

## Migration `s3e1_money_safety.py`
Guarded creation of the two tables (+ indexes) and the four columns; RLS on both tables; downgrade drops what it created. Also write
`ledgers/tooling/dream-scorecard/s3/s3e1_preapply.sql`? NO — ledgers are out of your fence; instead put the exact DDL your migration emits (from a throwaway
Postgres via `alembic upgrade --sql s3d1:s3e1` if available, else hand-derived) in the PR body under "DDL for prod pre-apply" so the orchestrator can pre-apply it.

Commit: `fix(billing): GOL replay returns the stored answer, refund holds survive event ordering, purchase snapshots, orphaned late payments (s3e1)`.
Push `fix/ms-m1-money-safety`; open the PR (base main), body = per-item summary + tests + the DDL block. Do NOT merge.

## CRITIQUE FOLD-IN (overrides anything above that conflicts) — the reviewer rated the first draft RETHINK; this is the design you build
Transactional design, in one sentence: every money decision is made while holding a durable row lock on the thing the decision is about (the user for questions,
the payment intent for settlement, the purchase for fulfilment), and every asynchronous completion carries the exact identity it is completing.

### Item 1 (GOL executions)
- `reserve_question` creates or claims the execution row INSIDE the existing user lock and commits debit + execution together (never a later transaction).
- Table `gol_chat_executions`: one row per debit attempt (UNIQUE user, client_msg_id, attempt) with `debit_id` FK, `status` (running|completed|failed),
  `input_hash`, `lease_generation` int default 1, `lease_started_at`, `response_text`, `response_events` (JSON text: ordered list of the terminal non-token events
  exactly as emitted: `replace`, `data_card`, `history_entries`, …), `recover_count` int default 0, `created_at`, `completed_at`. RLS on.
- Reservation return value adds `debit_id`, `execution_id`, `lease_generation`. Every compensation call passes `debit_id` (new kw-arg on `refund_question`; legacy
  callers without it keep latest-debit behaviour). Completion and failure updates are `UPDATE ... WHERE id=:id AND lease_generation=:gen` — a stale worker whose lease
  was taken over must not write anything (and must not refund).
- Recovery: a `running` execution with `lease_started_at` older than 5 min may be reclaimed atomically (single UPDATE ... WHERE status='running' AND
  lease_started_at < cutoff → lease_generation+1, recover_count+1, lease_started_at=now; check rowcount==1). Max `recover_count` = 2; beyond that mark failed and
  refund the exact debit. Two simultaneous reclaimers: exactly one wins (rowcount test with two sessions where possible; on SQLite prove the predicate logic).
- Hash: sha256 over canonical JSON of {message normalised, history = the exact list produced by `_sanitize_history_entry` (includes assistant `tool_calls` and
  tool `tool_call_id`), session_id}. Validate/reject malformed input BEFORE reserving. Tests: tool-field-only change and session-only change → 409.
- Completion semantics: persist `response_text` + `response_events`, `status=completed`, `completed_at` BEFORE forwarding the terminal `done` event. An `error` event,
  an exception, a generator that returns without `done` (token-only EOF), or a client disconnect (`GeneratorExit`) → `status=failed` and refund the exact debit.
  Tests: error-then-normal-return, token-only EOF, failure between persistence and delivery (persist succeeded → replay serves it, no refund).
- Replay: resolve the execution BEFORE constructing `GolService`. Completed → emit `usage`, then `replace` {content: response_text}, then the stored
  `response_events` in order (cards, history_entries), then `done`. Running & fresh → 409 `in_flight`. Test replay while `GolService` construction raises.

### Item 2 (settlement) — replaces "gol_refund_holds"
- Table `gol_payment_settlements`: `stripe_payment_intent_id` UNIQUE, `grant_ledger_id` FK nullable, `refund_target_cents` int default 0 (MONOTONIC max of
  cumulative `amount_refunded`), `refund_applied_cents` int default 0, `last_refund_event_id`, `created_at`, `updated_at`. RLS on.
- BOTH handlers (`_apply_gol_checkout` grant path and `charge.refunded`) first ensure the settlement row exists (insert in `begin_nested`, swallow IntegrityError —
  the existing pattern) and then `SELECT ... FOR UPDATE` it, THEN lock the user row (consistent order: settlement → user), THEN decide. Grant path: after
  `grant_purchase`, set `grant_ledger_id`, and if `refund_target_cents > refund_applied_cents` apply the difference via `apply_refund` (cumulative). Refund path:
  raise `refund_target_cents` to max(existing, event amount_refunded); if a grant exists apply the increase now; else return True (processed, held). Emit
  `gol_credits_refunded` analytics only for newly reversed credits. Tests: refund→grant, grant→refund, full→partial→grant (target stays full), repeated amounts with
  different event ids, a larger refund after application, and the exact interleaving "refund sees no grant / grant sees no hold" reproduced with two sessions where
  the test DB allows; on SQLite document that the lock order is the guarantee.

### Item 3 (purchase terms) — replaces the four columns
- Table `gol_checkout_terms`: `purchase_key` (36, UNIQUE, uuid4), `checkout_row_id` FK, `stripe_session_id` (255, UNIQUE, nullable until attached), `price_code`,
  `credits`, `unit_amount_cents`, `currency`, `stripe_price_id`, `created_at`, `attached_at`. RLS on.
- Persist the terms row (committed) BEFORE calling Stripe; pass `purchase_key` in the Session `metadata` (keep the existing `kind=credit_topup` metadata) and as
  `client_reference_id` if unused; after creation attach `stripe_session_id` idempotently. Fulfilment resolves terms by `stripe_session_id`, else by
  `metadata.purchase_key`; NEVER fall back to a different session's terms via the reused checkout row; legacy sessions with no terms → current pack + warning.
  A checkout row reused for a new session must not overwrite the previous session's terms (they live in their own rows).
- Tests: config change between checkout and webhook; pack removed; expiration → recreation → delayed completion of the ORIGINAL session fulfils the original terms;
  crash after remote creation (terms row exists, session not attached) then webhook with the purchase_key → fulfilled once.

### Item 4 (orphaned late payment)
- Classify as `gol_orphaned_purchase` ONLY when: a terms row identifies it as an Academy Watch GOL purchase AND the event proves payment (`payment_status` paid for
  `checkout.session.completed`, or `async_payment_succeeded`). Deduplicate the manual-refund record by `purchase_key` (one ProductEvent per purchase, both event
  types). Unpaid completion → ignored silently; sessions with no terms and no row → ignored + warning. Tests: unpaid completion, async success, unrelated payment
  session, deletion-then-webhook and webhook-then-deletion orders.

### Deletion/export (fence widened)
- `src/services/account.py`: add `gol_chat_executions` and `gol_checkout_terms` to the explicit deletion order (before ledger forfeiture); settlements: SET NULL the
  `grant_ledger_id` when the ledger rows are deleted (or delete settlements for that user's intents — choose and test). Add owned executions to the account EXPORT
  (question fingerprint, answer, timestamps). Test real deletion with completed + running executions and an applied settlement.

### Migration s3e1
- Three tables + indexes, guarded, RLS on. Do NOT try `alembic --sql` (the helpers run catalog queries). Provide hand-derived DDL in the PR body clearly marked
  UNVERIFIED — the orchestrator validates on disposable Postgres. Update the existing assertions superseded by the new policies (`tests/test_billing.py` ~:544 "missing
  purchase fails", ~:676 "unknown refund ignored") intentionally, stating why in the test names.
