import { useCallback, useEffect, useState } from 'react'
import { APIService } from '@/lib/api'
import { useHighlights, write, message } from './useHighlights'
import './highlights.css'

function Picker({ programId, matchId }) {
  const base = `/club/${programId}/matches/${matchId}`
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [confirmed, setConfirmed] = useState(false)
  const [titles, setTitles] = useState({})
  const load = useCallback(async () => {
    try { setData(await APIService.request(`${base}/highlights`)); setError('') }
    catch { setError('Highlights could not be loaded. Your access or the recording may have changed.') }
  }, [base])
  useEffect(() => { load() }, [load])
  async function act(path, body, method) {
    setBusy(true); setError('')
    try { await write(path, body, method); await load(); setConfirmed(false) }
    catch (err) { setError(message(err)) }
    finally { setBusy(false) }
  }
  return <section className="p2-highlights mt-6" aria-labelledby={`highlight-picker-${matchId}`}>
    <p className="hl-label">Club key · reviewed adult footage</p><h2 id={`highlight-picker-${matchId}`} className="mt-3">Pick highlights</h2>
    <p className="hl-muted mt-4">Picking is the first key. The adult player holds the second. Only a separately cut clip can become public.</p>
    {error && <p role="alert" className="hl-error mt-4">{error}</p>}
    {data && !data.adult_recording && <div className="hl-row">
      <h3>Review the whole recording first</h3><p className="hl-muted mt-3">Youth, mixed-age and unknown-age footage stays private. Review every person visible, including the opposition and bystanders.</p>
      {data.can_review ? <><label className="flex gap-3 items-start py-5 min-h-11"><input type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)} /><span>I reviewed the whole recording and verified that every visible person is an adult. No minor or person of unknown age appears.</span></label><button className="hl-button" disabled={!confirmed || busy} onClick={() => act(`${base}/highlight-review`, { classification: 'adult_only', all_visible_people_adults: true })}>Confirm adult-only recording</button></> : <p className="hl-muted mt-3">A club owner or manager must complete this review.</p>}
    </div>}
    {data?.adult_recording && !data.candidates.length && <p className="hl-muted py-6">No eligible moments yet. Picks need a human-reviewed identity, a short reel window and the adult&apos;s own approved profile.</p>}
    {(data?.candidates || []).map(window => {
      const key = `${window.roster_entry_id}:${window.tracklet_id}:${window.start_s}`
      const picked = data.highlights.find(row => !row.revoked && row.roster_entry_id === window.roster_entry_id && row.tracklet_id === window.tracklet_id && row.start_s === window.start_s && row.end_s === window.end_s)
      return <article className="hl-row" key={key}>
        <p className="hl-label">{window.start_s}s–{window.end_s}s · {Math.round(window.end_s-window.start_s)}s clip</p><h3 className="mt-3">{window.player_name}</h3>
        {picked ? <div className="flex flex-wrap items-center gap-4 mt-4"><p className="hl-muted">{picked.status_label === 'Waiting for you' ? 'Waiting for player' : picked.status_label}</p><button className="hl-button" disabled={busy} onClick={() => act(`${base}/highlights/${picked.id}`, null, 'DELETE')}>Remove pick</button></div> : <><label className="block text-sm my-4">Clip title<input className="hl-input mt-2" maxLength={160} value={titles[key] || ''} placeholder="Match moment" onChange={event => setTitles(current => ({ ...current, [key]: event.target.value }))} /></label><button className="hl-button hl-primary" disabled={busy} onClick={() => act(`${base}/highlights`, { roster_entry_id: window.roster_entry_id, tracklet_id: window.tracklet_id, start_s: window.start_s, end_s: window.end_s, title: titles[key] || 'Match moment' })}>Pick moment</button></>}
      </article>
    })}
    <button className="hl-button mt-6" onClick={load} disabled={busy}>Refresh highlights</button>
  </section>
}

export function ClubHighlightPicker({ programId, matchId }) {
  const enabled = useHighlights()
  return enabled ? <Picker programId={programId} matchId={matchId} /> : null
}
