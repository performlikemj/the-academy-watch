# Adversarial check of S1 package __P__ (The Academy Watch / loanarmy)

You are the independent checker in a codex-builds / Fable-checks role split. Codex implemented package
__P__ in worktree `__W__` (branch `__BR__`, base origin/main c764f10) and wrote a completion report.
Do NOT trust the report. Read the brief, read the diff, run the gates yourself, and attack the change.
READ-ONLY on the repo: never edit, commit, stash, or checkout. You may run ruff / pytest / pnpm lint /
pnpm build / a single Playwright spec inside the worktree (Playwright: start Vite on port 5185 from the
worktree, set E2E_BASE_URL=http://127.0.0.1:5185; NEVER touch ports 5001/5173 — another session's live
app; kill only the PID you started).

Inputs:
- Brief: __BRIEF__
- Codex report: __REPORT__
- Diff: `git -C __W__ diff origin/main...HEAD` (and `git -C __W__ log --oneline origin/main..HEAD`)

Check, in this order, and cite path:line for every finding:
1. Spec fidelity: every numbered requirement in the brief — done / partial / missing / silently changed.
2. Fences: files touched outside ALLOWED; more than one commit; any push; any ledger/CONTINUITY edit;
   any secret; any new dependency; any migration.
3. Correctness: read the new code paths end-to-end. Trace inputs → DB → response. Look for: fail-open
   age math (timezones, leap days, birth_year edge), idempotency holes, transaction ordering (commit before
   side effects?), auth gaps (which decorator guards the route), data leaks in public lists, N+1 or
   unbounded loops, error handling that hides failures.
4. Tests: do they test the behaviour or the mock? Run them. Mutation check: mentally flip the core rule
   (e.g. `>= 18` → `>= 17`) — would a test fail? Name the test that would.
5. User-facing symptom: does the actual user job now work? (A: web self-claim submits; B: approved club
   reaches a `require_club_manager` route; C: job runs `--dry-run` end-to-end; D: delete/export/report
   controls call the real routes.)
6. Gates you ran and their real output.

Final message = ONE JSON object, nothing else, also written to __OUT__:
{"package":"__P__","verdict":"CLEAN|FIX-FIRST|REJECT",
 "findings":[{"sev":"P1|P2|P3","where":"path:line","what":"...","fix":"smallest correct fix"}],
 "gates":{"ruff":"...","pytest":"...","lint":"...","build":"...","spec":"..."},
 "fences_ok":true,"unmet_requirements":["..."],"notes":"≤80 words"}
P1 = wrong/unsafe behaviour or a broken gate; P2 = real defect with a workaround; P3 = polish.
CLEAN means zero P1/P2.
