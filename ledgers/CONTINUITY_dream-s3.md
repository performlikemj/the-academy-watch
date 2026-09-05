# CONTINUITY — Dream roadmap S3: "money rails"

Parent: `CONTINUITY.md` · Source: `ledgers/GRADING_dream-scorecard-2026-09-02.md` (after S2: 61.0%) · Handoff: `ledgers/DIRECTIVE_dream-s3-handoff.md`
Owner: MJ · Orchestrator: Fable · Executors: codex CLI plus GLM 5.3 for IOS-1 · Shipped dark 2026-09-04

## Decisions (owner, 2026-09-03 — do not reopen)
- Charge only for data The Academy Watch generates: API-Football grants no commercial rights and forbids reselling its data.
- CSV export and custom lists remain free. The paid Scout Pro feature is the GOL chatbot.
- GOL chat and PDF access require login; the prior anonymous path could make up to six billed LLM calls per message.
- Admins are exempt. The grandfather window is moot under the re-scope.
- Donations remain gated on counsel; supporter import and the club bundle are deferred.

## Target rows (scorecard) → 3
3.6 Pay for Scout Pro · 5.5 Revenue rails · 4.1 Club funding registry / programs · 4.4 External platform connection · 4.6 Supporter/fan-facing club page.

Computed result: **61.0% → 65.6% (+4.6 points)**. Pillars: P1 75.0%, P2 63.9%, P3 75.0%, P4 46.4%, P5 59.4%.

## Status
- **S3 shipped and deployed dark.** `BILLING_ENABLED` is unset; no live purchase has run and revenue remains $0.
- The five target rows are re-scored to 3 from the orchestrator's integrated-review verdicts.
- Next: the owner completes the go-live checklist below; roadmap work continues with S4 and S6.

## What shipped
| PR | Package | Result |
|---|---|---|
| #993 | P0 billing (`8f6a445`) | Checkout, signed webhook, billing lifecycle, portal, account integration, admin summary, and `s3b1`. |
| #992 | P2a clubs (`60ebd09`) | Moderated program revisions, external support link-outs, program updates, admin review, and `s3c1`. |
| #994 | P3 web (`43cd967`) | Pricing/account billing surfaces, club program editor/updates, public link-outs, and admin revenue UI. |
| #996 | P1 Scout Pro (`74ddd2f`) | Scout entitlements, Checkout entry point, `/auth/me` projection, and paid-feature gating. |
| #999 | Re-scope backend (`5c5fff8`) | Kept CSV/custom lists free and moved the paid entitlement to authenticated GOL chat/PDF. |
| #1002 | Integration fixes (`cf263ad`) | Closed integrated-review findings, including the late-webhook-after-account-deletion defect. |
| #1003 | Test polish | Tightened the S3 regression suite after integration. |
| #1000 | Re-scope web | Aligned web pricing and feature messaging with the owner-approved GOL-only paid scope. |
| #1001 | iOS IOS-1 | GLM 5.3 build, merged after one codex round; 171/171 tests. |

## How it shipped
- Flow: briefs → codex critique → codex builds → per-package Fable checkers → GitHub Codex bot → fix rounds → integrated Fable review.
- GLM orchestrator run `20260903-141247-cc-loanarmy` drove the P0/P2a fix loops while the owner was out of credits.
- GLM shadow grading: P2a was CLEAN first try; P1 shadow remains unmerged and grading-only; IOS-1 merged after one codex round.
- The integrated review exercised the money path end to end. Its one real defect—late webhook delivery after account deletion—was fixed in #1002.
- The GitHub Codex bot and the package checkers were both used on each PR; shifted-line repeats were triaged against the fixed code.

## Production state (verified 2026-09-04)
- Alembic head: `s3d1`; chain tail `… → s2f1 → cb01 → s3b1 → s3c1 → s3d1`.
- Five billing tables plus `club_program_updates` exist, have RLS enabled, and contain 0 rows.
- `BILLING_ENABLED` is unset. Every billing and entitlement route returns neutral 404, including `OPTIONS`.
- Anonymous GOL chat returns 401; suggestions remain public at 200.

## Acceptance / review evidence
- Dark-mode route gate verified across billing and entitlement endpoints, including preflight.
- Signed webhook handling covers replay, out-of-order and equal-created events, failed retries, and late delivery after account deletion.
- Entitlement is derived from `billing_subscriptions`; `scout_tier` is a projection, not the source of truth.
- Club revisions publish only after review; approved external links are normalized and program updates remain moderated.
- No production charge was attempted; the real-card purchase/refund is deliberately the final owner acceptance step.

## Gotchas
1. A deploy failed on an Azure-login flake and passed on rerun.
2. A transient `OPTIONS 200` was rollout timing, not a dark-gate leak.
3. The old `basecamp_sim.sh` migrated the shared DB; use the throwaway-DB script shipped in #995.
4. Codex and GLM sandboxes cannot commit from linked worktrees; commit by explicit path.
5. The GitHub Codex bot can re-list fixed findings at shifted line numbers; verify the current code before reopening one.
6. Migration helpers require a throwaway PostgreSQL database for validation, not SQLite.

## Debts / queue (S3)
- Harness telemetry launcher branch `feat/telemetry-run-build` is unreviewed.
- GLM shadow P1 branch `glm/20260903-114137` is grading-only and must not merge as product work.
- Remove dead `identityKey` segments.
- `MAX_FOLLOW_LISTS` counts the default row.
- Film Room credit checkout and its CTA were not part of S3.
- Supporter import, club bundle billing, and donations are deferred; donations still require counsel.
- iOS scope stops at IOS-1; nothing beyond IOS-1 shipped in S3.

## GO-LIVE checklist (owner)
1. Create the Stripe webhook endpoint for `/api/billing/stripe/webhook`.
2. Rotate `STRIPE_WEBHOOK_SECRET` using the established rotate-keys pattern.
3. Create the one-time starter price and set `STRIPE_PRICE_GOL_STARTER` plus `GOL_STARTER_CREDITS` (default 100 pending owner confirmation).
4. Set `STRIPE_PRICE_GOL_TOPUP` plus `GOL_TOPUP_CREDITS` for pay-as-you-go top-ups.
5. Leave `STRIPE_PRICE_SCOUT_PRO_MONTHLY` and `STRIPE_PRICE_SCOUT_PRO_YEARLY` unset; no subscription price env should be configured.
6. Approve the Terms copy, then set repository variable `VITE_BILLING_TERMS=1`.
7. Set `BILLING_ENABLED=1` only after steps 1–6 are complete.
8. Buy the GOL starter pack once with a real card, verify the credit grant, then refund the purchase and verify the reversal.

## GOL credits (2026-09-04)

### Decisions
- Three free GOL questions per signed-in user, lifetime; each later question consumes one prepaid credit. Admins remain exempt.
- The first purchase is a $20 starter pack, followed by pay-as-you-go top-ups; there is no GOL subscription.
- The user-scoped, append-only ledger mirrors nbhd's grant/debit/reversal/adjustment model where it fits.
- Credits per $20 pack remain env-configured through `GOL_STARTER_CREDITS` / `GOL_TOPUP_CREDITS`; the default is 100 pending owner confirmation.

### What shipped
- #1006 GOL credits backend (squash `61853b7`): migration `s3d1` from `s3c1`; user-scoped `gol_credit_ledger`; payment-mode Checkout; 402 before SSE; usage SSE frames; question-bound `client_msg_id`; cumulative refund math.
- #1007 GOL credits web (`84e259f`): allowance/balance UI, 402 exhausted state, retry-safe question IDs, and starter/top-up purchase surfaces.
- #1005 Film Room credit race fix (`f6b882c`): lock the team row first; refund only when a prior debit exists.

### How it shipped
- Codex brief critique produced 33 fixes before the builds.
- Codex built the packages; Fable checkers ran P0 FIX-FIRST → two fix rounds → CLEAN and P1 CLEAN → one fix round → CLEAN.
- The GitHub bot was silent. Merge proceeded on checker, CI, and simulation evidence; each simulation was 11/11.

### Production state
- Deployed dark with `BILLING_ENABLED` unset; billing routes return 404 and anonymous chat returns 401.
- `s3d1` was pre-applied, then stamped. `gol_credit_ledger` has RLS enabled and 0 rows.
- No live credit purchase has run. Credits per pack remain at the env default of 100 pending owner confirmation.

### Gotchas
- A reviewer found that reusing one `client_msg_id` with different question text could bypass the paywall. The fix binds the ID to the normalized question hash and rejects different-text reuse.
- Promotion codes are disabled for fixed-price credit packs.
- Packs are USD-only: non-USD prices are not offered and are rejected at checkout; webhook records preserve the currency Stripe reports.
- SQLite cannot prove the `SELECT FOR UPDATE` row lock; the PostgreSQL concurrency probe did.

### Debts / follow-ups
- Decide whether the free allowance should gain a per-day option; the shipped policy is lifetime.
- Revisit remaining nbhd alignment follow-ups as the credit rail matures.
- iOS has no credits UI.
- The 402 exhausted-state experience is web-only.

## Log
- 2026-09-03/04 — S3 packages merged and deployed behind the default-off billing gate; migrations pre-applied/stamped through `s3c1`.
- 2026-09-04 — Integrated Fable review complete; late webhook after account deletion fixed in #1002; dark production checks pass.
- 2026-09-04 — Scorecard regenerated from `scorecard.json` fallback plus the five owner-supplied overrides; overall 65.6%.


## Go-live addendum (2026-09-05)
Money-safety stage done (`ledgers/DIRECTIVE_money-safety.md`). Confirm `BILLING_TERMS_EFFECTIVE_DATE` (2026-09-15 placeholder) before `VITE_BILLING_TERMS=1`; decide credits per $20 pack (rec 100); after go-live watch `product_events` for `gol_orphaned_purchase` / `gol_unfulfillable_legacy_purchase`.


## GO-LIVE EXECUTED 2026-09-06
Steps 1–7 of the checklist done by the orchestrator on the owner's instruction ("enable billing"). Live Stripe ids (not secrets): product=prod_VCkofRnGBgwkjR; starter=price_1UCLIzEHpp7b1sGxWAYImdhv; topup=price_1UCLIzEHpp7b1sGxPv7F4b2C; webhook=we_1UCLJ0EHpp7b1sGxDoH8JwZ0. Old lemonmoss webhook endpoint disabled. Step 8 (real-card purchase + refund) is the owner's.
