import { useEffect, useRef, useState } from 'react'
import { Check, ChevronRight, LockKeyhole, RefreshCw } from 'lucide-react'
import { APIService } from '@/lib/api'
import { track } from '@/lib/track'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

const unavailable = 'This feedback is no longer available.'

export default function PlayerFeedbackInbox({ signedId, token }) {
  if (!token) return null
  return <Inbox key={`${signedId}:${token}`} signedId={Number(signedId)} token={token} />
}

function Inbox({ signedId, token }) {
  const [rows, setRows] = useState([])
  const [feedback, setFeedback] = useState(null)
  const [nextBefore, setNextBefore] = useState(null)
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [refresh, setRefresh] = useState(0)
  const lifetime = useRef(null)
  const sequence = useRef(0)

  useEffect(() => {
    const controller = new AbortController()
    lifetime.current = controller
    const current = ++sequence.current
    setLoading(true)
    setFeedback(null)
    setRows([])
    setError('')
    APIService.request(`/me/player-feedback?player_api_id=${signedId}`, { signal: controller.signal })
      .then((data) => {
        if (!controller.signal.aborted && sequence.current === current) {
          setRows(data.feedback || [])
          setNextBefore(data.next_before)
        }
      })
      .catch((err) => {
        if (!controller.signal.aborted && sequence.current === current) setError([401, 403, 404].includes(err.status) ? unavailable : 'Could not load feedback. Please try again.')
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => { controller.abort(); sequence.current += 1 }
  }, [signedId, token, refresh])

  useEffect(() => {
    function directDetail() {
      const match = window.location.hash.match(/^#player-feedback=([a-f0-9-]{36})$/i)
      if (match) openFeedback(match[1])
    }
    directDetail()
    window.addEventListener('hashchange', directDetail)
    return () => window.removeEventListener('hashchange', directDetail)
    // Scope changes remount this component; the effect owns this scope's handler.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function openFeedback(id) {
    const controller = lifetime.current
    if (!controller || controller.signal.aborted) return
    const current = ++sequence.current
    setBusy(true)
    setFeedback(null)
    setError('')
    try {
      const data = await APIService.request(`/me/player-feedback/${id}`, { signal: controller.signal })
      if (controller.signal.aborted || current !== sequence.current) return
      if (data.feedback?.player_api_id !== signedId) { setError(unavailable); return }
      setFeedback(data.feedback)
      track('pilot_ui', { package: 'P3', action: 'feedback_opened', outcome: 'success' })
    } catch (err) {
      if (controller.signal.aborted || current !== sequence.current) return
      setRows([])
      setNextBefore(null)
      setError([401, 403, 404].includes(err.status) ? unavailable : 'Could not open feedback. Please try again.')
    } finally {
      if (!controller.signal.aborted && current === sequence.current) setBusy(false)
    }
  }

  async function acknowledge() {
    if (busy || !feedback?.can_acknowledge) return
    const controller = lifetime.current
    const current = ++sequence.current
    setBusy(true)
    setError('')
    try {
      const data = await APIService.request(`/me/player-feedback/${feedback.id}/acknowledge`, { method: 'POST', body: '{}', signal: controller.signal })
      if (controller.signal.aborted || current !== sequence.current) return
      setFeedback(data.feedback)
      setRows((previous) => previous.map((row) => row.id === data.feedback.id ? { ...row, acknowledged_at: data.feedback.acknowledged_at } : row))
      track('pilot_ui', { package: 'P3', action: 'feedback_acknowledged', outcome: 'success' })
    } catch (err) {
      if (controller.signal.aborted || current !== sequence.current) return
      if ([401, 403, 404].includes(err.status)) { setFeedback(null); setRows([]); setNextBefore(null); setError(unavailable) }
      else if (err.body?.error === 'feedback_revision_conflict') { setFeedback(null); setError('Updated feedback — please read again'); setRefresh((value) => value + 1) }
      else setError('Could not acknowledge feedback. Please try again.')
    } finally { if (!controller.signal.aborted && current === sequence.current) setBusy(false) }
  }

  async function loadMore() {
    if (busy || !nextBefore) return
    const controller = lifetime.current
    setBusy(true)
    try {
      const data = await APIService.request(`/me/player-feedback?player_api_id=${signedId}&before=${nextBefore}`, { signal: controller.signal })
      if (controller.signal.aborted) return
      setRows((old) => [...old, ...data.feedback])
      setNextBefore(data.next_before)
    } catch (err) {
      if (controller.signal.aborted) return
      if ([401, 403, 404].includes(err.status)) { setRows([]); setFeedback(null); setNextBefore(null); setError(unavailable) }
      else setError('Could not load more feedback.')
    } finally { if (!controller.signal.aborted) setBusy(false) }
  }

  return <Card className="my-6 overflow-hidden border-primary/20" aria-label="Private player feedback">
    <CardHeader className="border-b border-border/60 bg-muted/30">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <CardTitle className="flex items-center gap-2 text-lg"><LockKeyhole className="h-4 w-4 shrink-0" /> Private feedback from your club</CardTitle>
          <CardDescription className="mt-2">Feedback shared directly with you. Each correction is a new revision.</CardDescription>
        </div>
        <Button aria-label="Refresh feedback" variant="ghost" size="icon" onClick={() => { setBusy(false); setRefresh((value) => value + 1) }}><RefreshCw className="h-4 w-4" /></Button>
      </div>
    </CardHeader>
    <CardContent className="space-y-5 p-5">
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      {loading ? <p role="status" className="text-sm text-muted-foreground">Loading feedback…</p> : !error && rows.length === 0 && !feedback ? <p className="py-4 text-sm text-muted-foreground">Your club has not published feedback yet.</p> : null}
      {rows.map((row) => <button key={row.id} className="flex w-full items-center justify-between gap-3 rounded-lg border border-border p-4 text-left hover:bg-muted/40" onClick={() => openFeedback(row.id)}>
        <span className="min-w-0 break-words"><span className="block text-xs text-muted-foreground">{row.program.name} · Revision {row.revision}</span><span className="mt-1 block font-medium">{row.title}</span>
          <span className="mt-2 block text-xs text-muted-foreground">{row.acknowledged_at ? 'Acknowledged' : row.revision > 1 ? 'Updated feedback — please read again' : 'Unread feedback'}</span></span>
        <ChevronRight className="h-4 w-4 shrink-0" />
      </button>)}
      {nextBefore && <Button variant="outline" onClick={loadMore} disabled={busy}>Load more feedback</Button>}
      {feedback && <article className="space-y-4 rounded-lg border-l-4 border-primary bg-muted/25 p-5" aria-label="Feedback detail">
        <p className="text-xs text-muted-foreground">{feedback.program.name} · {feedback.author.display_name} · Revision {feedback.revision}</p>
        <h3 className="break-words text-xl font-semibold">{feedback.title}</h3>
        <p className="whitespace-pre-wrap break-words text-sm leading-relaxed">{feedback.body}</p>
        {feedback.observation_refs?.length > 0 && <ul className="space-y-2 text-sm text-muted-foreground">{feedback.observation_refs.map((ref, index) => <li key={index} className="break-words">{ref.timestamp_s != null ? `${Math.floor(ref.timestamp_s / 60)}:${String(Math.floor(ref.timestamp_s % 60)).padStart(2, '0')} — ` : ''}{ref.label}</li>)}</ul>}
        {feedback.revision > 1 && !feedback.acknowledged_at && <p className="text-sm font-medium">Updated feedback — please read again</p>}
        <p className="text-xs leading-relaxed text-muted-foreground">Acknowledging confirms you read this revision; it does not mean you agree.</p>
        {feedback.acknowledged_at ? <p className="flex items-center gap-2 text-sm font-medium" role="status"><Check className="h-4 w-4" />Acknowledged</p> : feedback.can_acknowledge ? <Button onClick={acknowledge} disabled={busy} className="h-auto min-h-9 whitespace-normal">I’ve read this feedback</Button> : <p className="text-sm text-muted-foreground">Open the latest revision to acknowledge it.</p>}
      </article>}
    </CardContent>
  </Card>
}
