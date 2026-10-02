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
- Now: review union implementation complete; PR1135 awaiting independent verification/merge.
- Next: independent re-review; no PR merge or production actions by this lane.
