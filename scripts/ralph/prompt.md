# Ralph Agent Instructions

You are running in **autonomous mode**. Complete one task per iteration, then exit.

## 1. Read State

```
AGENTS.md              → Project conventions
CONTINUITY.md          → Current state, find active planning ledger
ledgers/CONTINUITY_plan-*.md → Task list with acceptance criteria
scripts/ralph/progress.txt   → Learnings from previous iterations
```

## 2. Find Next Task

1. Open `CONTINUITY.md` → find the active planning ledger
2. Open the planning ledger
3. Scan tasks for `**Status:** ready`
4. Pick the **first** `ready` task
5. If no `ready` tasks:
   - All `complete` → output `<ralph>COMPLETE</ralph>` and stop
   - All `pending`/`blocked` → output `<ralph>STOP</ralph>`

## 3. Implement

- Follow **Acceptance Criteria** exactly
- Check `*/AGENTS.md` files for patterns
- Make minimal, focused changes

## 4. Verify

```bash
cd academy-watch-frontend && pnpm lint
cd academy-watch-frontend && pnpm test:e2e  # if tests exist for the change
```

## 5. On Success

1. Update planning ledger: `**Status:** ready` → `**Status:** complete`
2. Commit: `git commit -am "feat: TASK-XXX - [title]"`
3. Append to `scripts/ralph/progress.txt`
4. Check if completion unblocks other tasks → update `pending` to `ready`

## 6. On Failure

After 3 attempts:
1. Update planning ledger: status → `failed`
2. Update progress.txt with details
3. Output: `<ralph>STOP</ralph>`

## Stop Signals

- `<ralph>COMPLETE</ralph>` — All tasks done
- `<ralph>STOP</ralph>` — Cannot continue, needs human

## Rules

- ONE task per iteration
- Only pick `ready` tasks
- Update the planning ledger (source of truth)
- Always update progress.txt
- Commit after each success
