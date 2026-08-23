# Task brief — P0-A6b: the `ContactThread` component (messages, send, outcome)

**Pattern:** copy-adapt · **Thinking:** off · **Budget:** 75 min ·
**Files you will touch:** `academy-watch-frontend/src/lib/contact-thread.js` (NEW),
`academy-watch-frontend/src/components/contact/ContactThread.jsx` (NEW), and
`academy-watch-frontend/tests/contact-thread.test.mjs` (NEW). Nothing else — no page wires it yet (next
tasks do).
**Depends on:** P0-A2 (`APIService.getContactMessages` / `sendContactMessage` / `reportContactOutcome`).

**Shipped files:** this brief ships its NEW files under `briefs/assets/P0-A6b/`; each numbered section below gives the exact `cp` command. Never retype a shipped file — copy it. Your work is the edits inside existing files and the gate.

## The situation

Once a scout's introduction is accepted (and, for contracted players, the club has granted consent), the
participants message each other in a thread, and either side records the outcome (contacted → trial →
signed / no fit). The API exists; the web has no thread UI. Build ONE component that every view reuses
(scout's sent list, player's inbox, club console). It takes the `contact_request` object the API returns.

API shapes you will consume (do not re-discover):

- `contact_request`: `{ id, player_api_id, message, status: "pending"|"accepted"|"declined"|"withdrawn"|
  "expired", routing_mode: "direct"|"club_included"|"club_notified", club_consent_status: null|"pending"|
  "granted"|"declined", messaging_open: boolean, created_at, responded_at, expires_at,
  participants: { scout: { display_name }, player: { display_name }, club: null|{ display_name } },
  latest_outcome: null|{ stage, notes, occurred_at, reported_by_user_id } }`
- `GET messages` → `{ messages: [{ id, sender_role: "scout"|"player"|"club", sender_display_name, body,
  created_at }], contact_request, total }`; 409 `{ code: "club_consent_required" }` or `{ error:
  "messages are available only for accepted requests" }` when closed.
- `POST message { body }` → 201 `{ message }` (body ≤ 2000 chars).
- `POST outcome { stage, notes, occurred_at }` → 201 `{ outcome, contact_request }`;
  stages: `contacted | trial_scheduled | trial_completed | signed | no_fit`; notes ≤ 2000.

## The job

### 1. Pure helper — create `academy-watch-frontend/src/lib/contact-thread.js`

Shipped with this brief — COPY it, never retype (one command):

```bash
mkdir -p academy-watch-frontend/src/lib && cp briefs/assets/P0-A6b/contact-thread.js academy-watch-frontend/src/lib/contact-thread.js
```

### 2. Component — create `academy-watch-frontend/src/components/contact/ContactThread.jsx`

Shipped with this brief — COPY it, never retype (one command):

```bash
mkdir -p academy-watch-frontend/src/components/contact && cp briefs/assets/P0-A6b/ContactThread.jsx academy-watch-frontend/src/components/contact/ContactThread.jsx
```

### 3. Test — create `academy-watch-frontend/tests/contact-thread.test.mjs` (write it FIRST)

Shipped with this brief — COPY it, never retype (one command):

```bash
mkdir -p academy-watch-frontend/tests && cp briefs/assets/P0-A6b/contact-thread.test.mjs academy-watch-frontend/tests/contact-thread.test.mjs
```

## How to start

1. `PLAN.md`, at most 10 lines. Then act.
2. Copy the test file (the `cp` command above). Run `make gate TASK=P0-A6b`. RED: `Cannot find module '../src/lib/contact-thread.js'`.
3. Copy the helper, then the component (their `cp` commands). Gate again. GREEN (~70 s with lint+build).

## When things go wrong

- `pnpm lint`: `react-hooks/exhaustive-deps` WARNINGS are fine (the repo pins them to warn); ERRORS are not.
- `pnpm build` fails on the `Select` import → the path is `@/components/ui/select` (lowercase), as shown.
- A state-note assertion fails → copy `describeThreadState` byte-for-byte; the order of the `if`s matters.
- Same error twice → STOP, BLOCKED, paste it.
- After ANY interruption: run the gate; whatever is red is your next step.

## Do not

- Do not wire the component into any page (next tasks). Do not add polling, websockets, or markdown.

## Done means

1. `make gate TASK=P0-A6b` green — you ran it, you saw it.
2. `academy-watch-frontend/src/components/contact/ContactThread.jsx` exists and exports `ContactThread`.
3. Handback file on disk + the `HANDBACK-FILED: .harness/handback/$HARNESS_SESSION.md` last line.
