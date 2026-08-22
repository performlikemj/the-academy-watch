# Task brief — P0-A6b: the `ContactThread` component (messages, send, outcome)

**Pattern:** copy-adapt · **Thinking:** off · **Budget:** 75 min ·
**Files you will touch:** `academy-watch-frontend/src/lib/contact-thread.js` (NEW),
`academy-watch-frontend/src/components/contact/ContactThread.jsx` (NEW), and
`academy-watch-frontend/tests/contact-thread.test.mjs` (NEW). Nothing else — no page wires it yet (next
tasks do).
**Depends on:** P0-A2 (`APIService.getContactMessages` / `sendContactMessage` / `reportContactOutcome`).

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

```js
// Thread state + copy, pure so it is unit-tested without React.

export const MESSAGE_MAX = 2000
export const OUTCOME_NOTES_MAX = 2000

export const OUTCOME_STAGES = [
  { value: 'contacted', label: 'Contacted' },
  { value: 'trial_scheduled', label: 'Trial scheduled' },
  { value: 'trial_completed', label: 'Trial completed' },
  { value: 'signed', label: 'Signed' },
  { value: 'no_fit', label: 'Not a fit' },
]

export function outcomeLabel(stage) {
  return OUTCOME_STAGES.find((s) => s.value === stage)?.label || stage || '—'
}

export function describeThreadState(request) {
  if (!request) return { open: false, note: 'No request selected.' }
  if (request.messaging_open) return { open: true, note: null }
  if (request.status === 'pending' && request.routing_mode === 'club_included' && request.club_consent_status === 'pending') {
    return { open: false, note: 'Waiting for the player to accept and the club to allow the introduction.' }
  }
  if (request.status === 'pending') return { open: false, note: 'Waiting for the player to accept.' }
  if (request.status === 'accepted' && request.club_consent_status === 'pending') {
    return { open: false, note: 'The player accepted. Messaging opens once the club allows the introduction.' }
  }
  if (request.club_consent_status === 'declined') return { open: false, note: 'The club declined this introduction.' }
  if (request.status === 'declined') return { open: false, note: 'The player declined this introduction.' }
  if (request.status === 'withdrawn') return { open: false, note: 'This introduction was withdrawn.' }
  if (request.status === 'expired') return { open: false, note: 'This introduction expired without a reply.' }
  return { open: false, note: 'Messaging is not available for this request.' }
}

export function participantName(request, role) {
  const name = request?.participants?.[role]?.display_name
  if (name) return name
  if (role === 'scout') return 'Scout'
  if (role === 'player') return 'Player'
  return 'Club'
}

export function canSendMessage(body) {
  const trimmed = String(body || '').trim()
  return trimmed.length > 0 && trimmed.length <= MESSAGE_MAX
}
```

### 2. Component — create `academy-watch-frontend/src/components/contact/ContactThread.jsx`

```jsx
import { useState, useEffect, useCallback } from 'react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Textarea } from '@/components/ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Loader2, Send } from 'lucide-react'
import { APIService } from '@/lib/api'
import { MESSAGE_MAX, OUTCOME_NOTES_MAX, OUTCOME_STAGES, outcomeLabel, describeThreadState, participantName, canSendMessage } from '@/lib/contact-thread'

function formatWhen(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString(undefined, { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' })
}

export function ContactThread({ request, onRequestChange }) {
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  const [stage, setStage] = useState('')
  const [notes, setNotes] = useState('')
  const [reporting, setReporting] = useState(false)
  const [outcomeError, setOutcomeError] = useState(null)

  const state = describeThreadState(request)
  const requestId = request?.id

  const load = useCallback(async () => {
    if (!requestId || !state.open) {
      setMessages([])
      return
    }
    setLoading(true)
    setError(null)
    try {
      const res = await APIService.getContactMessages(requestId)
      setMessages(Array.isArray(res?.messages) ? res.messages : [])
      if (res?.contact_request && onRequestChange) onRequestChange(res.contact_request)
    } catch (err) {
      setError(err?.body?.error || err?.message || 'Messages could not be loaded.')
    } finally {
      setLoading(false)
    }
  }, [requestId, state.open, onRequestChange])

  useEffect(() => {
    setDraft('')
    setStage('')
    setNotes('')
    setOutcomeError(null)
    load()
  }, [load])

  const send = async () => {
    if (!requestId || !canSendMessage(draft)) return
    setSending(true)
    setError(null)
    try {
      const res = await APIService.sendContactMessage(requestId, draft.trim())
      if (res?.message) setMessages((current) => [...current, res.message])
      setDraft('')
    } catch (err) {
      setError(err?.body?.error || err?.message || 'Message could not be sent.')
    } finally {
      setSending(false)
    }
  }

  const report = async () => {
    if (!requestId || !stage) return
    setReporting(true)
    setOutcomeError(null)
    try {
      const res = await APIService.reportContactOutcome(requestId, { stage, notes: notes.trim() || null })
      if (res?.contact_request && onRequestChange) onRequestChange(res.contact_request)
      setStage('')
      setNotes('')
    } catch (err) {
      setOutcomeError(err?.body?.error || err?.message || 'Outcome could not be saved.')
    } finally {
      setReporting(false)
    }
  }

  if (!request) {
    return <p className="text-sm text-muted-foreground">Select an introduction to read the thread.</p>
  }

  return (
    <div className="space-y-4" data-testid="contact-thread">
      <div className="space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-semibold text-foreground">{participantName(request, 'scout')} ↔ {participantName(request, 'player')}</span>
          {request.participants?.club ? <Badge variant="outline">via {participantName(request, 'club')}</Badge> : null}
          <Badge variant="secondary">{request.status}</Badge>
          {request.latest_outcome ? <Badge variant="outline">Outcome: {outcomeLabel(request.latest_outcome.stage)}</Badge> : null}
        </div>
        <p className="rounded-lg border border-border bg-secondary/30 p-3 text-sm text-foreground/90">{request.message}</p>
        {state.note ? <p className="text-xs text-muted-foreground">{state.note}</p> : null}
      </div>

      {state.open ? (
        <div className="space-y-3">
          {loading ? (
            <p className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> Loading messages…</p>
          ) : messages.length === 0 ? (
            <p className="text-sm text-muted-foreground">No messages yet — say hello.</p>
          ) : (
            <ul className="space-y-2">
              {messages.map((m) => (
                <li key={m.id} className="rounded-lg border border-border p-3">
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{m.sender_display_name || m.sender_role} · {formatWhen(m.created_at)}</p>
                  <p className="mt-1 whitespace-pre-wrap text-sm text-foreground">{m.body}</p>
                </li>
              ))}
            </ul>
          )}
          <div className="space-y-2">
            <Textarea value={draft} onChange={(e) => setDraft(e.target.value.slice(0, MESSAGE_MAX))} rows={3} maxLength={MESSAGE_MAX} placeholder="Write a message…" aria-label="Message" />
            <div className="flex items-center justify-between">
              <span className="text-[11px] text-muted-foreground tabular-nums">{draft.trim().length}/{MESSAGE_MAX}</span>
              <Button size="sm" onClick={send} disabled={sending || !canSendMessage(draft)}>
                {sending ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Send className="mr-1.5 h-4 w-4" />} Send
              </Button>
            </div>
          </div>
          {error ? <p className="text-sm text-rose-600">{error}</p> : null}

          <div className="space-y-2 rounded-lg border border-dashed border-border p-3">
            <p className="text-sm font-semibold text-foreground">Record the outcome</p>
            <div className="flex flex-wrap items-center gap-2">
              <Select value={stage} onValueChange={setStage}>
                <SelectTrigger className="w-48" aria-label="Outcome stage"><SelectValue placeholder="Choose a stage" /></SelectTrigger>
                <SelectContent>
                  {OUTCOME_STAGES.map((s) => <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>)}
                </SelectContent>
              </Select>
              <Button size="sm" variant="outline" onClick={report} disabled={reporting || !stage}>
                {reporting ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : null} Save outcome
              </Button>
            </div>
            <Textarea value={notes} onChange={(e) => setNotes(e.target.value.slice(0, OUTCOME_NOTES_MAX))} rows={2} maxLength={OUTCOME_NOTES_MAX} placeholder="Notes (optional)" aria-label="Outcome notes" />
            {outcomeError ? <p className="text-sm text-rose-600">{outcomeError}</p> : null}
          </div>
        </div>
      ) : null}
    </div>
  )
}

export default ContactThread
```

### 3. Test — create `academy-watch-frontend/tests/contact-thread.test.mjs` (write it FIRST)

```js
import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'

import { describeThreadState, participantName, canSendMessage, outcomeLabel, OUTCOME_STAGES, MESSAGE_MAX } from '../src/lib/contact-thread.js'

const componentFile = new URL('../src/components/contact/ContactThread.jsx', import.meta.url)

test('describeThreadState explains every closed state and opens only when the API says so', () => {
  assert.equal(describeThreadState(null).open, false)
  assert.deepEqual(describeThreadState({ messaging_open: true, status: 'accepted' }), { open: true, note: null })
  assert.match(describeThreadState({ messaging_open: false, status: 'pending', routing_mode: 'direct' }).note, /Waiting for the player to accept/)
  assert.match(describeThreadState({ messaging_open: false, status: 'pending', routing_mode: 'club_included', club_consent_status: 'pending' }).note, /club to allow/)
  assert.match(describeThreadState({ messaging_open: false, status: 'accepted', routing_mode: 'club_included', club_consent_status: 'pending' }).note, /Messaging opens once the club allows/)
  assert.match(describeThreadState({ messaging_open: false, status: 'declined', club_consent_status: 'declined' }).note, /club declined/)
  assert.match(describeThreadState({ messaging_open: false, status: 'declined' }).note, /player declined/)
  assert.match(describeThreadState({ messaging_open: false, status: 'withdrawn' }).note, /withdrawn/)
  assert.match(describeThreadState({ messaging_open: false, status: 'expired' }).note, /expired/)
})

test('participantName, canSendMessage and outcome labels', () => {
  const req = { participants: { scout: { display_name: 'Alex' }, player: { display_name: null }, club: { display_name: 'Club A' } } }
  assert.equal(participantName(req, 'scout'), 'Alex')
  assert.equal(participantName(req, 'player'), 'Player')
  assert.equal(participantName(req, 'club'), 'Club A')
  assert.equal(canSendMessage('  hi '), true)
  assert.equal(canSendMessage('   '), false)
  assert.equal(canSendMessage('x'.repeat(MESSAGE_MAX + 1)), false)
  assert.equal(outcomeLabel('trial_scheduled'), 'Trial scheduled')
  assert.deepEqual(OUTCOME_STAGES.map((s) => s.value), ['contacted', 'trial_scheduled', 'trial_completed', 'signed', 'no_fit'])
})

test('the component talks to the three thread endpoints through APIService', async () => {
  const src = await fs.readFile(componentFile, 'utf8')
  assert.ok(src.includes('APIService.getContactMessages(requestId)'))
  assert.ok(src.includes('APIService.sendContactMessage(requestId, draft.trim())'))
  assert.ok(src.includes('APIService.reportContactOutcome(requestId, { stage, notes: notes.trim() || null })'))
  assert.ok(src.includes('data-testid="contact-thread"'))
})
```

## How to start

1. `PLAN.md`, at most 10 lines. Then act.
2. Write the test file. Run `make gate TASK=P0-A6b`. RED: `Cannot find module '../src/lib/contact-thread.js'`.
3. Create the helper, then the component. Gate again. GREEN (~70 s with lint+build).

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
