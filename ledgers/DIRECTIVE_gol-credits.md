# DIRECTIVE — GOL credits: 3 free questions, then a $20 starter pack and pay-as-you-go top-ups

Written 2026-09-04 by loanarmy-16 (S3 orchestrator) from owner decisions of 2026-09-04. Supersedes the Scout Pro *subscription* as the
way to pay for the GOL chatbot. Recon: codex read-only over loanarmy `3be03d0` and nbhd-united `c97dcdf` (`scratchpad/gol-credits-recon.json`).

## Owner decisions (binding)
1. The GOL chatbot is the paid feature (2026-09-03); chat and PDF export require login (live since #999).
2. Free allowance: **3 questions**, then prepaid credits. **$20 "starter"** pack; after that **pay as you go** — buy more credit. Not a subscription.
3. Mirror nbhd's credit model where it fits (nbhd-united: append-only `CreditLedger`, kinds grant/debit/reversal/adjustment, server-defined
   packs, Checkout `mode=payment` with `kind=credit_topup` metadata, `async_payment_succeeded`, `charge.refunded` incremental reversals).

## Orchestrator decisions (from the recon; reopen only with new evidence)
- **New table `gol_credit_ledger`**, user-scoped, append-only (the Film Room `VideoCreditLedger` is team-scoped, has no product
  discriminator, locks the wrong row and is not reused). Signed integer `delta`; `bucket ∈ {free_allowance, prepaid}`;
  `kind ∈ {grant, debit, reversal, adjustment}`; unique `idempotency_key`; nullable unique `stripe_session_id`; `stripe_event_id`,
  `stripe_payment_intent_id`, `pack_id`, `amount_paid_cents`, `client_msg_id`, `created_at`. Prepaid balance = Σ delta (prepaid);
  free remaining = max(0, FREE_ALLOWANCE + Σ delta (free_allowance)).
- **Free allowance is LIFETIME** (implicit opening balance of 3, debits appended). Retry-safe, auditable, no reset job, no timezone
  ambiguity. (A per-day window is a later product choice; keep `GOL_FREE_ALLOWANCE=3` in env so the number is not code.)
- **One POST `/api/gol/chat` = one question**, free first, then 1 prepaid credit. Follow-ups in the same conversation are questions.
  PDF export stays free (login only). Admins are exempt. **Billing dark (`BILLING_ENABLED` unset) = today's behaviour: unlimited, no debits.**
- **Debit before the first LLM call**, atomic: lock the user row, idempotency on a REQUIRED `client_msg_id` (`^[A-Za-z0-9_-]{8,64}$`,
  minted by the client per question and reused on retry), insert the debit, commit, then stream. Out of credit → **HTTP 402**
  `{"error":"credits_exhausted","feature":"gol_chat","free_questions_remaining":0,"credit_balance":0,"top_up_path":"/account/billing"}`
  BEFORE any SSE. A provider/tool failure that ends the stream with the service's terminal `error` event → one compensating
  `reversal` keyed `refund:<client_msg_id>`. A client abort is NOT refunded.
- **Packs are server-defined** in `PRODUCT_CATALOG` (`purchase_mode=payment`, integer `credits`): `gol_starter` = env
  `STRIPE_PRICE_GOL_STARTER` + `GOL_STARTER_CREDITS`; `gol_topup` = `STRIPE_PRICE_GOL_TOPUP` + `GOL_TOPUP_CREDITS` (the same $20 pack
  repeatable is fine at launch). The browser sends `pack_id` only. Checkout `mode=payment`, metadata `kind=credit_topup, product_code=gol,
  pack_id, user_id` on BOTH the Session and the PaymentIntent, idempotency per client_key as today.
- **Grants** on `checkout.session.completed` with `payment_status == "paid"` and on `checkout.session.async_payment_succeeded`;
  never on an unpaid completed. **Refunds:** `charge.refunded` → find the grant by PaymentIntent, convert Stripe's cumulative
  `amount_refunded` to an incremental reversal (integer credits, floor), negative balances are allowed and surfaced in the admin summary.
- The S3 subscription rail stays in code but **no subscription product is offered** (leave `STRIPE_PRICE_SCOUT_PRO_*` unset; prod has 0
  subscription rows). `gol_chat` entitlement is detached from subscriptions/grandfather: it means "has free questions or prepaid credit, or admin".
- Reuse unchanged: `BillingCustomer`/`ensure_customer`, webhook signature + event dedupe + failed-retry + watermark plumbing,
  `BillingCheckoutSession` idempotency, the dark gate, `/api/billing/config`, admin summary (extended additively).

## Packages (disjoint files; web builds against the contract)
- **GC-P0 backend** — catalog packs + payment-mode checkout, `gol_credit_ledger` (+ migration `s3d1` from `s3c1`, RLS), grants/refunds in the
  webhook, allowance/debit/reversal in `/api/gol/chat`, `usage` SSE event, entitlements + `/api/billing/me` fields, admin summary, tests.
- **GC-P1 web** — PricingPage ($20 starter + buy more), GOL panel (free-left / balance / 402 state), AccountBillingPage (balance, purchases),
  `client_msg_id` per question in `useGolChat`, `usage` event handling, spec.
Order: P0 → P1 (P1 may start against the contract). Merge one at a time; prod DDL pre-apply before merge, stamp after (S3 pattern).

## Acceptance (dark → lit)
Dark: nothing changes for anyone. Lit: a new signed-in user gets exactly 3 answered questions, the 4th is a 402 before any stream; buying
the starter (test key locally; MJ with a real card in prod, then refund) adds the pack's credits within one webhook; a refund reverses
proportionally; a retried question with the same `client_msg_id` debits once; a provider failure refunds once; admins never debit;
PDF export never debits; `/api/billing/me` and the panel show the same numbers.

## Owner inputs still open (build proceeds on the defaults, all env-configurable)
- Credits per $20 pack — default **100** (≈20¢/question; one question can cost up to six model calls). Top-up = the same $20/100 pack.
- Per-day vs lifetime free allowance — built as lifetime.
