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
