# AGENTS.md

> This file defines how AI agents operate in this codebase.
> Read this first. Follow it always.

## Quick Start

1. Read `CONTINUITY.md` (or create it if missing)
2. Determine if this is trivial (<15 min, no dependencies) or needs a ledger
3. Do the work
4. Update ledgers before finishing

---

## Project Overview

**What:** The Academy Watch — Football academy tracking platform with AI newsletters
**Stack:** Flask 3.1 + SQLAlchemy (backend), React 19 + Vite 6 + Tailwind (frontend), PostgreSQL
**Test command:** `cd academy-watch-frontend && pnpm lint && pnpm test:e2e`
**Dev server:** Backend: `cd academy-watch-backend && python src/main.py` | Frontend: `cd academy-watch-frontend && pnpm dev`

---

## Operating Principles

1. **Ledger-first:** Read CONTINUITY.md before working. Update it when state changes.
2. **Single source of truth:** Ledgers and repo are authoritative; chat may be incomplete.
3. **Small updates:** Bullets over paragraphs. Facts only.
4. **No guessing:** Mark uncertainty as UNCONFIRMED. Ask 1-3 targeted questions.
5. **Right-size ceremony:** Trivial tasks get one-liners; complex work gets ledgers.

---

## File Locations

| File | Purpose |
|------|---------|
| `CONTINUITY.md` | Master ledger — current project state |
| `ledgers/` | Epic, planning, and task ledgers |
| `ledgers/archive/` | Completed ledgers |
| `scripts/ralph/` | Autonomous execution loop |
| `*/AGENTS.md` | Subdirectory-specific conventions |

---

## Bootstrap (First Run)

If `CONTINUITY.md` doesn't exist, create it with:
- Goal: inferred from user request or UNCONFIRMED
- State: Now = current task, Next = TBD

---

## Interactive → Ralph Handoff

Tasks flow from interactive sessions to autonomous execution:

**Planning ledger is the single source of truth** — both modes use it.

### Task Status Flow

| Status | Meaning | Ralph Action |
|--------|---------|--------------|
| `pending` | Has unmet dependencies | Skip |
| `ready` | Unblocked, can be worked | **Pick this** |
| `in-progress` | Currently being worked | Skip |
| `blocked` | Needs decision/input | Skip |
| `complete` | Done | Skip |

### To Hand Off to Ralph

1. Set any `in-progress` tasks to `ready` (if stopping mid-work)
2. Ensure acceptance criteria are explicit
3. Commit current state
4. Run: `./scripts/ralph/ralph.sh 25`

### After Ralph Completes

1. Review commits and `scripts/ralph/progress.txt`
2. Resolve any `blocked` or `failed` tasks
3. Continue interactively or run Ralph again

---

## Ledger Protocol

### Start of Turn
1. Read `CONTINUITY.md`
2. Attach to existing ledger OR create new one OR use trivial protocol
3. Update stale state before new work

### During Work
Update ledgers when:
- Goals/constraints change
- Decisions made
- Milestones reached (Done/Now/Next)
- Tests run (record result)
- Blockers identified

### Trivial Tasks
Skip ledger creation when ALL true:
- < 15 minutes
- Single file change
- No cross-task dependencies

Log one-liner in CONTINUITY.md's "Trivial Log" section.

---

## Codebase Patterns

> Agents: Add patterns here when you discover reusable conventions.

(none yet — agents will populate this)

---

## Quality Bar

Before marking work complete:
- [ ] Typecheck passes
- [ ] Tests pass
- [ ] Ledger state updated
- [ ] Patterns added to AGENTS.md if discovered
