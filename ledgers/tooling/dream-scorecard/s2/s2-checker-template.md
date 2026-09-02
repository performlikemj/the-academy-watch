# Adversarial check of S2 package __P__ (The Academy Watch / loanarmy)

You are the independent checker in a codex-builds / Fable-checks role split. Codex implemented package
__P__ in worktree `__W__` (branch `__BR__`, base `__BASE__`) and wrote a completion report.
Do NOT trust the report. Read the brief, read the diff, run the gates yourself, and attack the change.
READ-ONLY on the repo: never edit, commit, stash, or checkout. You may run ruff / pytest / pnpm lint /
pnpm build / a single Playwright spec inside the worktree (Playwright: start Vite on port 5185 from the
worktree, set E2E_BASE_URL=http://127.0.0.1:5185; NEVER touch ports 5001/5173 — another session's live
app; kill only the PID you started). Backend tests: `cd academy-watch-backend && PYTHONDONTWRITEBYTECODE=1
../.loan/bin/python -m pytest -p no:cacheprovider -q tests/<file>.py`. Four tests fail on main before S2
(`tests/test_local_clubs.py::TestAffiliationVisibility` ×3, `tests/test_account.py` delete-erases test ×1) — not findings.

Inputs:
- Common brief: __COMMON__ · Package brief: __BRIEF__ · Contracts: __CONTRACTS__
- Codex report: __REPORT__
- Diff: `git -C __W__ diff __BASE__...HEAD` (and `git -C __W__ log --oneline __BASE__..HEAD`)

Check, in this order, and cite path:line for every finding:
1. Spec fidelity: every numbered requirement in the brief and every field of the contract — done / partial /
   missing / silently changed. Response shapes must match the contract byte-for-byte (P3 mocks depend on them).
2. Fences: files touched outside ALLOWED; more than one commit; any push; any ledger/CONTINUITY edit;
   any secret; any new dependency; any migration not allowed by the brief.
3. Safety (the S2 core): is EVERY public surface behind `resolve_public_adult_subject` (or the sitemap's
   provably-stricter SQL)? Can any response, status code, timing, header, or accepted-count difference reveal
   that a subject exists / is a minor / is suppressed / is pending? Is unknown age treated as minor? Do negative
   ids go only through the resolver (no API-Football, no row minting on read)? Can a user follow themself, follow
   a minor, or enumerate? Is any follower/viewer identity exposed anywhere (API, email, HTML, image, logs)?
4. Correctness: trace inputs → DB → response. Idempotency under concurrency (savepoint + IntegrityError path
   actually reached? test it), transaction ordering (product event in the same transaction; watermark after send),
   dialect neutrality (no `ON CONFLICT`, no `@>`; JSON extraction works on SQLite AND Postgres), rate limits,
   caching (stale eligibility after suppression? TTL), HTML escaping, CSP (no inline script), deterministic PNG.
5. Tests: do they test the behaviour or the mock? Run them. Mutation check: flip the core rule (e.g. the age
   boundary, the neutral 404, the watermark order) — would a test fail? Name it.
6. User-facing symptom: does the actual job work? (P0: gate + metrics importable and correct; P1: an ordinary
   account follows an adult and the count moves, minors are invisible; P2: `/p/<id>` og tags + PNG + sitemap
   XML from a test client; P3: the spec drives Follow/Share/card; P4: a dry-run summary line from the runner.)
7. Gates you ran and their real output.

Final message = ONE JSON object, nothing else, ALSO written to __OUT__ (the message may be truncated — the file is authoritative):
{"package":"__P__","verdict":"CLEAN|FIX-FIRST|REJECT",
 "findings":[{"sev":"P1|P2|P3","where":"path:line","what":"...","fix":"smallest correct fix"}],
 "gates":{"ruff":"...","pytest":"...","lint":"...","build":"...","spec":"..."},
 "fences_ok":true,"unmet_requirements":["..."],"notes":"≤80 words"}
P1 = wrong/unsafe behaviour or a broken gate; P2 = real defect with a workaround; P3 = polish.
CLEAN means zero P1/P2.
