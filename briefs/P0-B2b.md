# Task brief — P0-B2b: the roster editor only opens a match fetched in full (review follow-up)

**Pattern:** copy-adapt · **Thinking:** off · **Budget:** 30 min ·
**Files you will touch:** `academy-watch-frontend/src/pages/MyClubConsole.jsx` (two shipped placements, via step scripts)
and `academy-watch-frontend/tests/club-console-match-list.test.mjs` (replaced by the shipped file). Nothing else.

## Shipped step scripts

Commands that look like `bash briefs/assets/P0-B2b/step-N.sh` are the brief's own commands shipped as files.
Run them EXACTLY like that, from the worktree root. Never open, copy out, or retype their contents — they print the
markers the steps describe. If one prints `…-BLOCKED`, STOP and say BLOCKED with the line.

**Do NOT inspect the step scripts and do NOT re-check their anchors yourself.** No `cat`/`read`/`od`/python on
`step-N.sh`, no grep of your own for the lines they target: a retyped grep loses spaces and WILL disagree with the
script — the script is right, your retype is wrong, every time. If a script prints its marker (`X=<n>`, `…-INSERTED`,
`…-REPLACED`), the step is done; move to the next. Investigating anchors is the one thing that burns your whole budget.

## The situation

PR review (codex, P1) on P0-B2: the match LIST route returns summary rows without `roster`. The console stored those
rows as-is, so `MatchDetail` started with an empty roster ("0 selected"); if a manager then saved, the backend treated
that empty selection as authoritative and deleted the saved roster entries (and their player reports). Fix: the
selected match is fetched in full (`APIService.getClubMatch`) once, and the editor renders only after that; a
failure shows "Match details could not be loaded" with Retry. New matches created in this session already carry
`roster: []` and open immediately.

## Step 0 — replace the test (write it FIRST; one command)

```bash
cp briefs/assets/P0-B2b/club-console-match-list.test.mjs academy-watch-frontend/tests/club-console-match-list.test.mjs && echo TEST-REPLACED
```

Run `make gate TASK=P0-B2b` once now: RED on the new third test ("hydration is keyed on a roster array being present"). Correct.

## Step 1 — the hydrate block (one command)

```bash
bash briefs/assets/P0-B2b/step-1.sh
```

Prints `R=<n> C=<m>` then `HYDRATE-INSERTED`.

## Step 2 — the render guard (one command)

```bash
bash briefs/assets/P0-B2b/step-2.sh
```

Prints `G=<n>` then `GUARD-REPLACED`.

Confirm, read-only: `grep -c "const hydrated = Array.isArray(selectedMatch?.roster)\|{selectedMatch && !hydrated ? (" academy-watch-frontend/src/pages/MyClubConsole.jsx` → `2`.

## Step 3 — gate

```bash
make gate TASK=P0-B2b
```

GREEN (node --test 3 pass; then `pnpm lint` 0 errors + `pnpm build`; 1–4 minutes).

## When things go wrong

- `STEP1-BLOCKED` / `STEP2-BLOCKED` → STOP, say BLOCKED, paste the line. Do not hand-repair.
- `pnpm lint` error in MyClubConsole.jsx → STOP, BLOCKED, paste it (the snippets are shipped; if they lint dirty, the brief is wrong, not you).
- Same error twice → STOP, BLOCKED.

## Do not

- Do not edit MyClubConsole.jsx by hand, touch api.js, the backend, or anything else.

## Done means

1. `make gate TASK=P0-B2b` green — you ran it, you saw it.
2. The confirm grep prints `2`.
3. Handback on disk at `.harness/handback/$HARNESS_SESSION.md` + the last line `HANDBACK-FILED: .harness/handback/$HARNESS_SESSION.md`.
