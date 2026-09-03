# Adversarial check of S3 package __P__ (The Academy Watch / loanarmy)

You are the independent checker in a codex-builds / Fable-checks role split. Codex implemented package
__P__ in worktree `__W__` (branch `__BR__`, base `__BASE__`) and wrote a completion report.
Do NOT trust the report. Read the brief, read the diff, run the gates yourself, and attack the change.
READ-ONLY on the repo: never edit, commit, stash, or checkout. You may run ruff / pytest / pnpm lint /
pnpm build / a single Playwright spec inside the worktree (Playwright: start Vite on port 5185 from the
worktree, set E2E_BASE_URL=http://127.0.0.1:5185; NEVER touch ports 5001/5173 — another session's live
app; kill only the PID you started). Backend tests: `cd academy-watch-backend && PYTHONDONTWRITEBYTECODE=1
../.loan/bin/python -m pytest -p no:cacheprovider -q tests/<file>.py`. Four tests fail on main before S3
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
3. Safety (the S3 core — money): with `BILLING_ENABLED` unset, is EVERY billing route the exact neutral 404 of the contact
   rail, and does NOTHING that works today stop working (CSV export, lists, /auth/me, /programs/<slug>)? Can the browser choose a
   price, amount, currency, or URL? Is the webhook signature verified on the RAW body before any write? Does a replayed event
   write twice or email twice? Can an older event downgrade a newer state? Is entitlement derived from `billing_subscriptions`
   (never from a product event or a client field)? Are Stripe secrets or keys printed/logged/committed anywhere (grep for
   `sk_`, `whsec_`)? Does account deletion cancel at Stripe first and abort on failure? Clubs: can a non-manager read or write a
   profile/update? Can an approved revision change without the admin review route? Does the external-support validator accept
   any look-alike host, userinfo, port, query, http, or javascript:? Is `is_fundable` still false everywhere? Any donate CTA?
3b. Money-path lifecycle & concurrency (the GitHub Codex bot caught these on S3-P0 after a CLEAN verdict — attack them explicitly):
   two checkouts for one scope with DIFFERENT client_keys before any webhook lands (double charge?); account deletion with an OPEN
   Checkout Session or an active subscription and with the Stripe key MISSING (silent success?); two webhook events with EQUAL
   `created` seconds delivered stale-last; retrieve-based vs payload-based watermarks; multi-currency aggregation; a webhook for a
   purchaser that no longer exists; entitlement after `past_due` → `unpaid` → `canceled`; portal cancel + immediate re-checkout.
4. Correctness: trace inputs → DB → response. Idempotency under concurrency (savepoint + IntegrityError path
   actually reached? test it), transaction ordering (product event in the same transaction; watermark after send),
   dialect neutrality (no `ON CONFLICT`, no `@>`; JSON extraction works on SQLite AND Postgres), rate limits,
   caching (stale eligibility after suppression? TTL), HTML escaping, CSP (no inline script), deterministic PNG.
5. Tests: do they test the behaviour or the mock? (Migrations: the repo helpers query information_schema, so up/down verification runs on a THROWAWAY local Postgres, never SQLite.) Run them. Mutation check: flip the core rule (e.g. the age
   boundary, the neutral 404, the watermark order) — would a test fail? Name it.
6. User-facing symptom: does the actual job work? (P0: a signed test event creates a subscription row and flips scout_tier,
   replay is a duplicate, checkout is idempotent — from the test client; P1: a free account gets the 403 shape on CSV export and
   a pro/grandfathered one exports; P2a: manager PUT → pending, admin approve → public payload changes, link-out validated;
   P3: the spec drives pricing → checkout POST → navigation, account billing, program page, club editor.)
7. Gates you ran and their real output.

Final message = ONE JSON object, nothing else, ALSO written to __OUT__ (the message may be truncated — the file is authoritative):
{"package":"__P__","verdict":"CLEAN|FIX-FIRST|REJECT",
 "findings":[{"sev":"P1|P2|P3","where":"path:line","what":"...","fix":"smallest correct fix"}],
 "gates":{"ruff":"...","pytest":"...","lint":"...","build":"...","spec":"..."},
 "fences_ok":true,"unmet_requirements":["..."],"notes":"≤80 words"}
P1 = wrong/unsafe behaviour or a broken gate; P2 = real defect with a workaround; P3 = polish.
CLEAN means zero P1/P2.
