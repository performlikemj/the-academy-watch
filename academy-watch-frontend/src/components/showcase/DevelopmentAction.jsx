import { useEffect, useRef, useState } from 'react'
import { CheckCircle2, ClipboardCheck, Flag, Sparkles } from 'lucide-react'
import { APIService } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'

const statusLabels = { not_started: 'Your next step', working_on_it: 'Working on it', ready_for_review: 'Ready for coach review', reviewed: 'Reviewed by your coach' }

export function DevelopmentActionFields({ value, onChange, disabled }) {
  return <fieldset className="space-y-4 rounded-xl border border-primary/25 bg-background p-4" disabled={disabled}>
    <legend className="px-2 text-sm font-semibold">One clear development action</legend>
    <p className="text-sm text-muted-foreground">Give the player something specific to practise and a way to recognise progress.</p>
    <label className="block space-y-1 text-sm">What to work on<Input value={value.focus} maxLength={160} required onChange={(event) => onChange({ ...value, focus: event.target.value })} /></label>
    <label className="block space-y-1 text-sm">What to practise<Textarea value={value.practice} maxLength={1000} rows={3} required onChange={(event) => onChange({ ...value, practice: event.target.value })} placeholder="At the next session, try…" /></label>
    <label className="block space-y-1 text-sm">What progress looks like<Textarea value={value.success} maxLength={500} rows={2} required onChange={(event) => onChange({ ...value, success: event.target.value })} placeholder="We’ll look for…" /></label>
    <label className="block space-y-1 text-sm">Review date (optional)<Input type="date" value={value.review_on || ''} onChange={(event) => onChange({ ...value, review_on: event.target.value || null })} /></label>
  </fieldset>
}

export function DevelopmentActionSummary({ action }) {
  if (!action) return null
  return <section className="space-y-4 rounded-xl border border-primary/25 bg-primary/5 p-4" aria-label="Development action">
    <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-primary"><Flag className="h-4 w-4" /> Your next step</div>
    <h4 className="break-words text-lg font-semibold">{action.focus}</h4>
    <dl className="space-y-3 text-sm"><div><dt className="font-semibold">What to practise</dt><dd className="mt-1 whitespace-pre-wrap break-words leading-relaxed">{action.practice}</dd></div><div><dt className="font-semibold">What progress looks like</dt><dd className="mt-1 whitespace-pre-wrap break-words leading-relaxed">{action.success}</dd></div></dl>
    {action.review_on && <p className="text-xs font-medium text-muted-foreground">Review together: {action.review_on}</p>}
  </section>
}

export function FeedbackEvidencePicker({ programId, invitationId, disabled, onSelect, onFailure }) {
  const [rows, setRows] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const lifetime = useRef(null)
  useEffect(() => { const controller = new AbortController(); lifetime.current = controller; return () => controller.abort() }, [])
  async function load() {
    setBusy(true); setError(''); setRows(null)
    try {
      const result = await APIService.request(`/club/${programId}/player-feedback/suggestions?invitation_id=${invitationId}`, { signal: lifetime.current.signal })
      if (!lifetime.current.signal.aborted) setRows(result.suggestions || [])
    } catch (err) {
      if (lifetime.current.signal.aborted) return
      setError('Match observations could not be loaded. You can still write your own feedback.')
      if ([401, 403, 404, 409].includes(err.status)) onFailure(err)
    } finally { if (!lifetime.current.signal.aborted) setBusy(false) }
  }
  return <section className="space-y-3 rounded-xl border border-border bg-muted/25 p-4" aria-label="AI match observations">
    <div className="flex flex-wrap items-center justify-between gap-3"><div className="flex items-center gap-2 font-semibold"><Sparkles className="h-4 w-4 text-primary" /> Start from a match observation</div><Button type="button" variant="outline" size="sm" onClick={load} disabled={disabled || busy}>{busy ? 'Loading observations…' : 'Find AI observations'}</Button></div>
    <p className="text-xs leading-relaxed text-muted-foreground">Player-matched observations from finalized film. Check the interpretation and edit your advice before sharing anything.</p>
    {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
    {rows?.length === 0 && <p className="text-sm text-muted-foreground">No verified player observations are available from recent finalized matches. You can write a development action from your own coaching.</p>}
    {rows?.map((row) => <article key={row.id} className="space-y-2 rounded-lg border border-border bg-card p-3"><p className="text-xs font-medium text-muted-foreground">AI observation · Match {row.video_match_id} · {Math.floor(row.timestamp_s / 60)}:{String(Math.floor(row.timestamp_s % 60)).padStart(2, '0')}</p><p className="whitespace-pre-wrap break-words text-sm leading-relaxed">{row.text}</p><Button type="button" variant="outline" size="sm" disabled={disabled} onClick={() => onSelect(row)}>Use this observation</Button></article>)}
  </section>
}

export function DevelopmentProgress({ feedback, manager = false, programId, onUpdated, onAccessLost }) {
  if (!feedback.development_action) return null
  return <ProgressForm key={`${feedback.id}:${feedback.development_progress?.version || 0}`} feedback={feedback} manager={manager} programId={programId} onUpdated={onUpdated} onAccessLost={onAccessLost} />
}

function ProgressForm({ feedback, manager, programId, onUpdated, onAccessLost }) {
  const progress = feedback.development_progress
  const [note, setNote] = useState(manager ? '' : progress?.reflection || '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [conflict, setConflict] = useState(false)
  const lifetime = useRef(null)
  useEffect(() => { const controller = new AbortController(); lifetime.current = controller; return () => controller.abort() }, [])
  async function save(status) {
    if (busy) return
    setBusy(true); setError('')
    const path = manager ? `/club/${programId}/player-feedback/${feedback.thread_id}/progress-review` : `/me/player-feedback/${feedback.id}/progress`
    const body = { expected_version: progress?.version || 0, status, note: note.trim(), ...(manager ? { expected_revision: feedback.revision } : {}) }
    try {
      const data = await APIService.request(path, { method: 'POST', body: JSON.stringify(body), signal: lifetime.current.signal })
      if (!lifetime.current.signal.aborted) onUpdated(data.feedback)
    } catch (err) {
      if (lifetime.current.signal.aborted) return
      if ([401, 403, 404].includes(err.status) || err.body?.error === 'club_relationship_required') onAccessLost()
      else if (err.status === 409) { setConflict(true); setError('This action has changed. Refresh the feedback before updating it again. Your draft is still here.') }
      else setError('Could not save your update. Your draft is still here; please try again.')
    } finally { if (!lifetime.current.signal.aborted) setBusy(false) }
  }
  const canEdit = manager ? progress?.status === 'ready_for_review' : feedback.can_update_progress
  return <section className="space-y-4 rounded-xl border border-border p-4" aria-label={manager ? 'Review player progress' : 'My development progress'}>
    <div className="flex items-center gap-2 text-sm font-semibold"><ClipboardCheck className="h-4 w-4 text-primary" />{statusLabels[progress?.status || 'not_started']}</div>
    {manager && progress?.reflection && <div><p className="text-xs font-semibold text-muted-foreground">Player reflection</p><p className="mt-1 whitespace-pre-wrap break-words text-sm">{progress.reflection}</p></div>}
    {progress?.coach_note && <div className="rounded-lg bg-primary/5 p-3"><p className="text-xs font-semibold text-primary">Coach review</p><p className="mt-1 whitespace-pre-wrap break-words text-sm">{progress.coach_note}</p></div>}
    {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
    {canEdit ? <>
      <label className="block space-y-1 text-sm">{manager ? 'Your review for the player' : 'How did practice go?'}<Textarea value={note} onChange={(event) => setNote(event.target.value)} maxLength={1000} rows={3} disabled={busy} placeholder={manager ? 'Recognise progress and explain the next step…' : 'What did you try? What felt different? Where do you need help?'} /></label>
      <p className="text-xs leading-relaxed text-muted-foreground">{manager ? 'Your response is shared privately with this player.' : 'Only you and your club can see this reflection. A practice update is separate from reading the feedback.'}</p>
      <div className="flex flex-wrap gap-2"><Button type="button" variant="outline" onClick={() => save('working_on_it')} disabled={busy || conflict || (manager && !note.trim())}>{manager ? 'Keep practising' : 'Save practice update'}</Button><Button type="button" onClick={() => save(manager ? 'reviewed' : 'ready_for_review')} disabled={busy || conflict || !note.trim()}><CheckCircle2 className="mr-2 h-4 w-4" />{manager ? 'Mark reviewed' : 'Ready for coach review'}</Button></div>
    </> : !manager && !feedback.can_update_progress ? <p className="text-xs text-muted-foreground">Open the latest feedback revision to update your progress.</p> : manager && progress?.status !== 'reviewed' ? <p className="text-xs text-muted-foreground">The player can practise this action and send a reflection when they’re ready for your review.</p> : null}
    {progress?.history?.length > 0 && <details className="border-t border-border pt-3"><summary className="cursor-pointer text-sm font-medium">Development history</summary><ol className="mt-3 space-y-3">{progress.history.slice().reverse().map((event) => <li key={event.version} className="border-l-2 border-primary/25 pl-3 text-sm"><p className="font-medium">{event.actor === 'coach' ? 'Coach' : 'Player'} · {statusLabels[event.status]}</p><p className="text-xs text-muted-foreground">{event.at?.slice(0, 10)}</p>{event.note && <p className="mt-1 whitespace-pre-wrap break-words">{event.note}</p>}</li>)}</ol></details>}
  </section>
}
