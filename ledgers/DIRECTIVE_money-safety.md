# DIRECTIVE — Money-safety stage (MS), 2026-09-05

Owner decision (MJ, 2026-09-05, "go fixes"): fix the three P1 defects and three launch blockers from the independent gpt-6-astra review
(`ledgers/research/astra-review-2026-09-05.md`) BEFORE `BILLING_ENABLED` is switched on. Then go live with prepaid GOL credits (B2 in the review's plan).

## Packages (parallel worktrees, disjoint files)
| Pkg | Scope | Brief | Migration |
|---|---|---|---|
| MS-M1 | GOL replay = stored answer (executions + lease), refund settlements that survive event ordering, purchase terms bound to the Stripe session, orphaned late payments | `ledgers/tooling/dream-scorecard/s3/money-safety/ms-m1-backend-money.md` | `s3e1` (3 tables, RLS on) — pre-apply DDL to prod BEFORE merge, stamp AFTER deploy (S3 pattern) |
| MS-M2 | Club-confirmed results require the club's authority over the player (current club at entry, academy parent, or accepted `PlayerClubAffiliation`) | `…/ms-m2-club-attribution.md` | none |
| MS-M3 | SSE parser with frame state across chunks; prepaid-credit billing terms + privacy fixes (dark behind `VITE_BILLING_TERMS`) | `…/ms-m3-web.md` | none |

Brief critique (gpt-6-astra, 28 gaps, M1 RETHINK → redesigned): `…/ms-critique-gpt-6-astra.md`. Fold-ins are appended to each brief.

## Decisions recorded here
- Client disconnect mid-answer = failed execution + automatic refund of that exact debit (terms copy says so).
- Rollup does NOT re-evaluate club authority on rebuild (would erase legitimate old-club results after transfers); the write-side gate is the fix; prod has zero
  club claims so there are no legacy rows (verify with the audit SQL in the M2 PR).
- Orphaned late payments (account deleted before the webhook) are acknowledged, recorded as `gol_orphaned_purchase`, and refunded manually by the owner.
- Billing terms effective date placeholder `2026-09-15` — owner confirms at go-live.

## Method
codex builds (M1 on gpt-6-astra, M2/M3 on gpt-5.6-sol) → Fable checker per PR (money-path attacks from `s3-checker-template.md` §3b) → fix rounds →
merge → prod pre-apply/stamp for s3e1 → then the go-live checklist in `ledgers/CONTINUITY_dream-s3.md` (Stripe endpoint + prices + credits envs + terms flag +
BILLING_ENABLED + one real-card purchase/refund by the owner).
