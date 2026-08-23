# Task brief — P0-A6c: thread shows every message; clubs don't get an outcome form (review follow-ups)

**Pattern:** copy-adapt · **Thinking:** off · **Budget:** 30 min ·
**Files you will touch:** `academy-watch-frontend/src/components/contact/ContactThread.jsx`,
`academy-watch-frontend/src/components/contact/ClubIntroductionsPanel.jsx`, `academy-watch-frontend/tests/contact-thread.test.mjs`,
`academy-watch-frontend/tests/club-introductions-panel.test.mjs` — ALL FOUR are replaced by shipped files. Nothing else.

## The situation

PR review (codex, two P2s) on the contact UI: (1) the thread fetched only the first page of messages (oldest-first),
so a long conversation never showed its newest replies; (2) the shared thread showed "Record the outcome" to club
managers, but the API only lets the scout or the player report outcomes — every club attempt ended in an error.
The updated `ContactThread` pages through all messages and takes a `canReportOutcome` prop (default on);
`ClubIntroductionsPanel` passes `canReportOutcome={false}`. Tests updated to the new contract.

## Step 0 — replace the four files (four `cp` commands, nothing to type)

```bash
cp briefs/assets/P0-A6c/contact-thread.test.mjs academy-watch-frontend/tests/contact-thread.test.mjs && cp briefs/assets/P0-A6c/club-introductions-panel.test.mjs academy-watch-frontend/tests/club-introductions-panel.test.mjs && echo TESTS-REPLACED
```

```bash
cp briefs/assets/P0-A6c/ContactThread.jsx academy-watch-frontend/src/components/contact/ContactThread.jsx && cp briefs/assets/P0-A6c/ClubIntroductionsPanel.jsx academy-watch-frontend/src/components/contact/ClubIntroductionsPanel.jsx && echo COMPONENTS-REPLACED
```

Confirm, read-only: `grep -c "canReportOutcome" academy-watch-frontend/src/components/contact/ContactThread.jsx academy-watch-frontend/src/components/contact/ClubIntroductionsPanel.jsx` → `…ContactThread.jsx:2` and `…ClubIntroductionsPanel.jsx:1`.

## Step 1 — gate

```bash
make gate TASK=P0-A6c
```

GREEN (node --test, then `pnpm lint` 0 errors + `pnpm build`; 1–4 minutes).

## When things go wrong

- `pnpm lint` error in a replaced file → STOP, say BLOCKED, paste it (the files are shipped; if they lint dirty, the brief is wrong, not you).
- Same error twice → STOP, BLOCKED.

## Do not

- Do not edit any of the four files by hand, or touch anything else.

## Done means

1. `make gate TASK=P0-A6c` green — you ran it, you saw it.
2. The confirm grep prints `2` and `1`.
3. Handback on disk at `.harness/handback/$HARNESS_SESSION.md` + the last line `HANDBACK-FILED: .harness/handback/$HARNESS_SESSION.md`.
