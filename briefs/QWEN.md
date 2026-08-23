# QWEN.md — your rulebook for this repo. Read it first, every time.

You are a coding agent working in **The Academy Watch** monorepo. Two parts matter to you:

| Path | What it is | How it is tested |
|---|---|---|
| `academy-watch-backend/` | Flask 3.1 + SQLAlchemy 2.0, Python 3.11. Code in `src/`, tests in `tests/`. | `pytest`, in-memory SQLite, no network. |
| `academy-watch-frontend/` | React 19 + Vite, pnpm. Pages in `src/pages/`, API client `src/lib/api.js`. | Unit tests: plain `node --test tests/*.test.mjs` (no jsdom). `pnpm lint` + `pnpm build` are the CI gates. |

Everything else in this repo is OFF LIMITS unless your brief names it.

## What to do first

1. Read this whole file.
2. If `PROGRESS.md` exists in the repo root, read it — it is your memory from a restart.
3. Your prompt names ONE task, like `P0-A1`. Read `briefs/P0-A1.md`. Do only that task. Nothing else.
4. Write `PLAN.md` (at most 10 lines). Then act. Do not plan in your head past that.
5. Work test-first, exactly as the brief says.
6. When the task is done, write your handback file and stop. Do not start another task.

## The gate — one command decides if your work is good

```bash
make gate TASK=<your task id>        # e.g.  make gate TASK=P0-A1
```

It runs, in order: `ruff check` + `ruff format --check` on the backend, then ONLY the test files your
brief names (listed in `briefs/<TASK>.gate`), then — only if your brief is a frontend task —
`pnpm lint` and `pnpm build` (about 70 seconds; wait for them).

You are NOT done until it prints `GATE GREEN` and exits 0. Run it yourself. Do not guess. Never say
it passed if you did not run it. If it is RED, read the FIRST error, fix it, run the gate again.
If the SAME error happens twice, stop guessing — the problem may be the setup, not your code. Say so.

Facts about this repo's tests, so you do not rediscover them:
- **Never run the full suites** (`pytest` with no file, or `pnpm test`). They have old failures that
  are not yours and not your job. The gate runs exactly the right files.
- `tests/test_contact.py` cannot run alone (a model it imports needs a table another test module
  registers). The gate always runs it together with `tests/test_club_console.py`. Do the same.
- To run ONE test while iterating (faster than the gate), from `academy-watch-backend/`:
  `/Users/michaeljones/Projects/loanarmy/.loan/bin/python -m pytest -q -p no:cacheprovider tests/<file>.py -k <test name>`
  (that python is the repo's venv; `python3` on PATH is NOT it). Then run the real gate.
- Frontend unit tests are plain node: from `academy-watch-frontend/`, `node --test tests/<file>.test.mjs`.
  Components have no render tests; `pnpm lint` + `pnpm build` are the contract for JSX.
- `ruff format --check` is a separate gate from `ruff check`. If it says "would reformat", run
  `ruff format <that file>` on a file YOU edited, then gate again. Line length is 120.

## Reading files — the rule that saves your budget

- **Never print a whole file.** The big ones (`App.jsx` 4,300 lines, `api.js` 3,000 lines) are
  truncated and you lose your place; you will re-read them for half an hour and write nothing.
- Use line ranges: `sed -n '1640,1650p' <file>`, or `grep -n "<exact text>" <file>`. Your brief
  tells you the lines and the exact text — read ONLY those.
- Act early. A brief that says "write the test FIRST" means your FIRST tool call creates that file.
  Thinking longer does not make the file appear. Write, run the gate, read the error, fix.
- Keep each tool call small: one file write or one edit per call. Big pastes are split in the brief —
  follow the split.
- **You do not type code into existing files.** Briefs ship every snippet under `briefs/assets/<TASK>/`
  and give you the exact shell to place it: find the anchor line with `grep -n "<unique text>"`, then
  `sed -i '' "${N}r briefs/assets/<TASK>/<snippet>"` to insert after line N (or `sed -i '' "A,Bd"` to
  delete lines A–B first). Copy those commands exactly. Reason: measured on this lane, your `edit`
  tool calls reproduced closing-brace lines with one extra space every time (`\n     }`), so the anchor
  never matched; `sed` and `cp` do not have that problem.
- If a brief ever does ask for your `edit` tool: it refuses a file you have not read in this session —
  `read` ONLY the anchor lines with `offset`/`limit` first (never the whole file). If it says
  "old_string was not found" ONCE, stop and say BLOCKED — do not spend time on whitespace forensics.
- After a successful edit, move to the NEXT step immediately (the next edit or the gate). Do not re-read
  the file to admire the change; the gate is your proof.
- When a brief ships a file under `briefs/assets/<TASK>/`, you COPY it with the exact `cp` command the
  brief gives. Never retype a shipped file — retyping changes whitespace inside strings and silently
  breaks tests. Your skill is the EDITS inside existing files; shipped files are not a test of typing.

## How to write code here

1. Write or extend the test the brief names. Run the gate. See it RED. Good — the test works.
2. Write the smallest code that makes it GREEN. Run the gate again.
3. Small steps. One change at a time. Gate often.
4. Copy the shapes the brief shows you. Do not invent new patterns, helpers, or abstractions.

## Hard rules

- Never `git add`, `git commit`, `git push`, `git stash`, or `git checkout` anything. The orchestrator
  commits. (The sandbox cannot write the git index anyway — do not fight it.)
- Never install anything (`pip`, `pnpm add`, `npm`). If a package is missing, ASK (below).
- Never touch the network, Azure, production, `.env`, secrets, or start a dev server.
- Never edit a file your brief does not name. Never "improve" unrelated code. Never reformat whole files.
- Never edit `briefs/`, `Makefile`, `lane-gate.sh`, `run-qwen.sh`, or `.harness/` — one exception:
  your own help file and your own handback file under `.harness/`.

## When you are stuck — two ways to stop

**Someone can answer you** (a fact you lack, a decision only a person can make, a missing package):
write a help file, then stop.

```bash
mkdir -p .harness/help
cat > ".harness/help/$HARNESS_SESSION.json" <<'EOF'
{"kind":"missing_info","what":"what you need","why_needed":"why the task stops without it","tried":"what you tried","task":"P0-A1"}
EOF
```

`kind` is one of `missing_package`, `missing_info`, `design_decision`, `env_broken`. Someone answers
and your run continues where it stopped; waiting costs you no time. Asking is a good answer.
Guessing is not.

**Dead end, nothing to ask:** say `BLOCKED` and exactly what stopped you. Paste the error.

A bad answer is saying you finished when the gate is red.

## Done means (every brief)

1. `make gate TASK=<id>` is GREEN — you ran it, you saw it.
2. The brief's observable is real (each brief says what a person can point at).
3. Your report is ON DISK at `.harness/handback/$HARNESS_SESSION.md` (`mkdir -p .harness/handback`
   first). Say what you changed, what the gate printed, and anything you could NOT verify. Then the
   LAST line of your final message is exactly:

   ```
   HANDBACK-FILED: .harness/handback/$HARNESS_SESSION.md
   ```

   The file is the deliverable; the sentinel is only the receipt.

## Shipped step scripts (`bash briefs/assets/<TASK>/step-N.sh`)

Many briefs ship their placement commands as script files. When a brief says `bash briefs/assets/<TASK>/step-N.sh`,
run exactly that line from the worktree root. Never open the script, never copy its contents out, never retype or
"fix" it — retyped commands lose spaces and then cannot find their lines (this is exactly what blocked P0-B2). The
script prints the markers the brief describes (`X=<n>`, `…-INSERTED`, `…-REPLACED`); an empty `X=` or a `BLOCKED`
line means STOP and say BLOCKED with that line pasted.

**Do NOT inspect the step scripts and do NOT re-check their anchors yourself.** No `cat`/`read`/`od`/python on
`step-N.sh`, no grep of your own for the lines they target: a retyped grep loses spaces and WILL disagree with the
script — the script is right, your retype is wrong, every time. If a script prints its marker (`X=<n>`, `…-INSERTED`,
`…-REPLACED`), the step is done; move to the next. Investigating anchors is the one thing that burns your whole budget.
