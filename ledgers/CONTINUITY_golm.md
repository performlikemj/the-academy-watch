# Maintenance switch for the assistant

- Goal: request-time operational control with GOL_MAINTENANCE and unavailable-provider handling.
- Constraints: no production actions, iOS edits, dependency changes or migration; PR1135 targets main and stays unmerged.
- Base: origin/main58ccb8c6 incorporated; current main already included at start of fix round.
- Done: previously debited same-account questions retain reservation/replay/in-flight/refund behavior while fresh paused requests write nothing.
- Done: panel-open and explicit availability rechecks, Retry-After deadline, Clear reset, preserved retry identity and persistent polite maintenance announcement/input description.
- Done: browser spec included in existing CI config; temporary lane config removed; public documentation and PR wording updated.
- Tests: targeted backend76 PASS; hook/component54 PASS. Final-head gates/browser receipts recorded in the external GOLMF1 hand-back.
- Done: GOLMF1 validation/delivery complete at0570a961; PR1135 open awaiting review/merge, receipts in external logs/GOLMF1.final.md.
- Done (GOLMF2): active provider chunk/resume/EOF availability checks and stream closure; typed maintenance, failed execution, one refund and same-ID recovery. Only latest unreversed running/completed debits enter paused reservation; refunded/failed retries stay write-free, including exhausted balances.
- Done (GOLMF2): Retry remains visible for a non-maintenance failed question while paused, preserving ID/history/session and accepting refund usage; fresh input stays disabled.
- Tests (GOLMF2): backend96 PASS; hook/component57 PASS. Reversed probes failed14 backend cases + the paused recovery render before fixes. Final-head gate/browser/delivery receipts are authoritative in external logs/GOLMF2.final.md.
- Done (GOLMF3): paused route carries recover-only mode; reservation revalidates latest unreversed running/completed debit/execution after the account lock and before compensation/balance/new-attempt work. Lost eligibility rolls back to typed503; replay/live/stale behavior unchanged.
- Tests (GOLMF3): four deterministic interleavings failed before fix; maintenance/credits/history100 PASS after fix. Real PostgreSQL concurrent refunded/withheld-exhausted cases2 PASS, each proving account-lock blocking/rollback/zero retry writes/unchanged debit analytics; owned aw_golmf3 dropped. Final validation/delivery/CI receipts in external logs/GOLMF3.final.md.
- Now: implementation complete; PR1135 awaiting independent verification/merge.
- Next: independent re-review; no PR merge or production actions by this lane.
