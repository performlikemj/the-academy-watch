# Maintenance switch for the assistant

- Goal: request-time operational control with GOL_MAINTENANCE and unavailable-provider handling.
- Constraints: no production actions, iOS edits, dependency changes or migration; PR1135 targets main and stays unmerged.
- Base: origin/main58ccb8c6 incorporated; current main already included at start of fix round.
- Done: previously debited same-account questions retain reservation/replay/in-flight/refund behavior while fresh paused requests write nothing.
- Done: panel-open and explicit availability rechecks, Retry-After deadline, Clear reset, preserved retry identity and persistent polite maintenance announcement/input description.
- Done: browser spec included in existing CI config; temporary lane config removed; public documentation and PR wording updated.
- Tests: targeted backend76 PASS; hook/component54 PASS. Final-head gates/browser receipts recorded in the external GOLMF1 hand-back.
- Now: regression coverage and implementation complete; final-head validation/delivery pending.
- Next: four cached gates, one browser spec run and refreshed evidence, push and cleanup; no PR merge.
