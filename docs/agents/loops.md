# Running loops safely here

A **loop** is an agent repeating cycles of work until a stop condition is met.
This repo runs them today: Ralph (`./scripts/ralph/ralph.sh`) executes ledger
tasks autonomously, and five Azure Container App jobs run scheduled syncs
(see `OPERATIONS.md`). `docs/agents/invariants.md` is the list of hard stops
every loop must honor.

## Ralph protocol

- Ralph picks ONLY `ready` tasks from the active planning ledger (statuses:
  pending / ready / in-progress / blocked / complete — see `AGENTS.md`).
- One task per iteration; update the ledger and commit after each.
- Sentinels: `<ralph>COMPLETE</ralph>` when all tasks done, `<ralph>STOP</ralph>`
  when blocked. Review `scripts/ralph/progress.txt` and the commits afterwards.
- Handing off: set `in-progress` → `ready`, make acceptance criteria explicit,
  commit, then `./scripts/ralph/ralph.sh 25`.

## 1. Stop conditions are safety gates, not just quality gates

In an autonomous loop a wrong action *executes*. Hard-halt (raise to a human)
before: prod schema migrations, bulk journey re-syncs against prod (they starve
the health probe and have caused outages — invariants.md §7), sending email via
Mailgun, Stripe changes, deleting Azure resources, anything touching prod secrets.

## 2. Key "done" off the real end-state, not a proxy

A MERGED badge ≠ `main` advanced (stacked PRs produce phantom merges — verify
`git log origin/main`). CI green ≠ the page renders. "Job triggered" ≠ data
landed — query the row or endpoint afterwards.

## 3. Verify by DRIVING the change

- Web UI: Playwright — load the page, interact, screenshot, zero new console errors.
- API: curl the endpoint (prod or local) and read the payload; time it and check
  its size — oversized responses break rendering with "correct" data (debugging.md).
- Data jobs: SQL count/aggregate before vs after.

## 4. Make the loop observe itself

Sub-agents report through the ledgers (`CONTINUITY.md`, planning-ledger status
flips) — a structured channel. The orchestrator verifies each agent's *actual
output* (commit exists, row written, screenshot taken), not that it "finished".

## 5. Pilot the unit before you fan out

Prove one instance end-to-end before scaling: one player before a full journey
re-sync, one team before a full rebuild. Full rebuilds run for hours and burn
API-Football quota (invariants.md §11) — a flaw amplifies N times.

## 6. When a result misses the bar, fix the SYSTEM

Encode the miss as a new invariant, hook, or verify step so the next iteration
can't repeat it. That flywheel is the point of the harness.

## Token spend

Mechanical work → cheap model; judgment → capable model. Prefer a deterministic
script over re-reasoning. The scheduled ACA jobs + pg_cron already cover daily
syncs and cache purges — don't build agent loops for what they already do.
