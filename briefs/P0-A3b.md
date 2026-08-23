# Task brief — P0-A3b: consent page — transient errors are not "invalid link" (review follow-up)

**Pattern:** copy-adapt · **Thinking:** off · **Budget:** 30 min ·
**Files you will touch:** `academy-watch-frontend/src/pages/ClubConsentPage.jsx` (replaced by the shipped file). Nothing else.

**Shipped files:** the whole page is shipped at `briefs/assets/P0-A3/ClubConsentPage.jsx` (updated). You copy it
over the existing page with one `cp`. You never type code in this task.

## The situation

PR review (codex, P2) on the page P0-A3 added: when the first request fails for a TRANSIENT reason (network blip,
CORS, a 5xx) the page told the club manager the link was invalid and to ask the scout for a new one — even though
the link was still fine. The API's own "bad link" answer is a 404 (`invalid_consent_link`). The updated page keeps
`invalid` for 404 only, shows a "couldn't reach the server — try again" state with a Retry button for anything
else, and a failed confirm shows an inline error instead of invalidating the link.

## Step 0 — replace the page (one command)

```bash
cp briefs/assets/P0-A3/ClubConsentPage.jsx academy-watch-frontend/src/pages/ClubConsentPage.jsx && echo PAGE-REPLACED
```

Confirm, read-only: `grep -c "status === 'error'" academy-watch-frontend/src/pages/ClubConsentPage.jsx` → `1`.

## Step 1 — gate

```bash
make gate TASK=P0-A3b
```

GREEN (the P0-A3 test file still applies; then `pnpm lint` + `pnpm build`; 1–4 minutes).

## When things go wrong

- `pnpm lint` error in the page → STOP, say BLOCKED, paste it (the file is shipped; if it lints dirty, the brief is
  wrong, not you).
- Same error twice → STOP, BLOCKED.

## Do not

- Do not edit the page by hand, touch the helper, the test, App.jsx, or anything else.

## Done means

1. `make gate TASK=P0-A3b` green — you ran it, you saw it.
2. `grep -c "Try again" academy-watch-frontend/src/pages/ClubConsentPage.jsx` prints `1`.
3. Handback on disk at `.harness/handback/$HARNESS_SESSION.md` + the last line
   `HANDBACK-FILED: .harness/handback/$HARNESS_SESSION.md`.
