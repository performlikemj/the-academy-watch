import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, Navigate } from 'react-router-dom'
import { APIService } from '@/lib/api'
import { useAuth, useAuthUI } from '@/context/AuthContext'
import { useNightSurface } from '@/hooks/useNightSurface'
import { useHighlights, useHighlightsState, write, message } from './useHighlights'
import './highlights.css'

function Preview({ row }) {
  const [url, setUrl] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const load = async () => {
    setBusy(true); setError('')
    try { setUrl(await APIService.highlightPreviewUrl(row.preview_url)) }
    catch { setError('This clip is unavailable. Refresh to check its current status.') }
    finally { setBusy(false) }
  }
  return <div className="my-4">
    {url ? <video src={url} controls preload="metadata" onError={() => { setUrl(null); setError('This preview link is unavailable. Preview the short clip again to get a fresh link.') }} aria-label={`Preview ${row.title}`} /> : <button className="hl-button" onClick={load} disabled={busy}>{busy ? 'Loading clip…' : 'Preview short clip'}</button>}
    {error && <p role="alert" className="hl-error mt-3">{error}</p>}
  </div>
}

function Inbox() {
  const { token } = useAuth()
  const { openLoginModal } = useAuthUI()
  const [rows, setRows] = useState([])
  const [page, setPage] = useState(1)
  const [more, setMore] = useState(false)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(null)
  const [error, setError] = useState('')
  const pollDelay = useRef(30000)
  const load = useCallback(async () => {
    if (!token) { setLoading(false); return }
    setLoading(true)
    try { const data = await APIService.request(`/me/highlight-requests?page=${page}`); setRows(data.highlights); setMore(data.has_more); setError('') }
    catch { pollDelay.current = Math.min(pollDelay.current * 2, 300000); setError('We could not load your requests. Please refresh to try again.') }
    finally { setLoading(false) }
  }, [token, page])
  useEffect(() => { load() }, [load])
  // Poll only while preparing; never manufacture a public state before the server says so.
  useEffect(() => {
    if (!rows.some(row => ['queued', 'running'].includes(row.render_status))) return
    let timer
    const cancel = () => clearTimeout(timer)
    const schedule = () => {
      cancel()
      if (!document.hidden) timer = setTimeout(() => { pollDelay.current = Math.min(pollDelay.current * 2, 300000); load() }, pollDelay.current)
    }
    const visibility = () => {
      cancel()
      if (!document.hidden) { pollDelay.current = 30000; load() }
    }
    document.addEventListener('visibilitychange', visibility)
    schedule()
    return () => { cancel(); document.removeEventListener('visibilitychange', visibility) }
  }, [rows, load])
  async function act(row, action, decision) {
    setBusy(row.id); setError('')
    try {
      const updated = await write(`/me/highlight-requests/${row.id}/${action}`, decision ? { decision, version: row.version } : {})
      setRows(current => current.map(item => item.id === row.id ? updated : item))
    } catch (err) { setError(message(err)) }
    finally { setBusy(null) }
  }
  const waiting = rows.filter(row => row.player_decision === 'pending' && !row.revoked).length
  return <section className="p2-highlights" aria-labelledby="highlight-approvals">
    <div className="flex flex-wrap items-center justify-between gap-4"><p className="hl-label">Highlight approvals · {waiting} waiting on this page</p><button className="hl-button" onClick={load} disabled={loading}>Refresh</button></div>
    <h1 id="highlight-approvals" className="mt-5">Your moments, <em className="text-gold">your call.</em></h1>
    <div className="grid gap-6 border-y border-hairline-dark py-6 my-8 sm:grid-cols-2">
      <div><p className="hl-label">Key 1 · the club</p><p className="mt-2">Your club picks a moment from a reviewed adult match.</p></div>
      <div><p className="hl-label">Key 2 · you</p><p className="mt-2">You decide whether the short clip can appear on your player and club pages.</p></div>
    </div>
    {!token && <button className="hl-button hl-primary" onClick={openLoginModal}>Sign in to review your highlights</button>}
    {error && <p role="alert" className="hl-error">{error}</p>}
    <div aria-live="polite" aria-busy={loading}>
      {token && loading && <p className="hl-muted">Loading your highlights…</p>}
      {token && !loading && !rows.length && <p className="hl-muted py-6">Nothing waiting for you. When your club picks a reviewed moment, it will appear here.</p>}
      {token && !loading && rows.map(row => <article key={row.id} className="hl-row">
        <p className="hl-label">{row.club_name} · {row.duration_s}s</p><h2 className="mt-3">{row.title}</h2>
        <p className="hl-label mt-4">{row.status_label}</p>
        {row.preview_url && <Preview key={`${row.id}:${row.version}`} row={row} />}
        {!row.revoked && <div className="flex flex-wrap gap-3 mt-5">
          {row.player_decision !== 'approve' && row.can_approve && <button className="hl-button hl-primary" disabled={busy === row.id} onClick={() => act(row, 'decision', 'approve')}>Make public</button>}
          {row.player_decision !== 'private' && <button className="hl-button" disabled={busy === row.id} onClick={() => act(row, 'decision', 'private')}>Keep private</button>}
          {row.player_decision === 'approve' && <button className="hl-button" disabled={busy === row.id} onClick={() => act(row, 'revoke')}>Take it back</button>}
          {row.can_retry && <button className="hl-button" disabled={busy === row.id} onClick={() => act(row, 'retry')}>Try again</button>}
        </div>}
      </article>)}
    </div>
    {token && <div className="flex gap-3 mt-6">{page > 1 && <button className="hl-button" onClick={() => setPage(page-1)}>Previous</button>}{more && <button className="hl-button" onClick={() => setPage(page+1)}>Next</button>}</div>}
    <p className="hl-muted mt-8">Only the short clip is shared. The full match stays private. You can take your approval back whenever you like; new grants stop immediately. An already issued clip link lasts at most 60 seconds; a download already underway may finish.</p>
  </section>
}

export function HighlightApprovals() {
  const { enabled, loaded } = useHighlightsState()
  useNightSurface()
  if (!loaded) return null
  if (!enabled) return <Navigate to="/" replace />
  return <div className="floodlight-container py-12 max-w-5xl">
    <meta name="referrer" content="no-referrer" />
    <Link to="/" className="inline-flex min-h-11 items-center text-chalk mb-6">← Home</Link>
    <Inbox />
  </div>
}

export function HighlightInboxLink() {
  const enabled = useHighlights()
  const { token } = useAuth()
  if (!enabled || !token) return null
  return <section className="p2-highlights mt-8"><p className="hl-label">Your player home</p><h2 className="mt-3">Highlight approvals</h2><p className="hl-muted my-4">Review moments your club picked, keep them private or take an approval back.</p><Link className="hl-button hl-primary" to="/highlight-approvals">Review highlights →</Link></section>
}
