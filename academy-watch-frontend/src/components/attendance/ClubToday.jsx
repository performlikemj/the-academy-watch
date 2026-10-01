import { useCallback, useEffect, useRef, useState } from 'react'
import { APIService } from '@/lib/api'
import { attendanceError, sendAttendance } from './useScoutAttend'
import './attendance.css'

function AttendanceDecision({ row, programId, refresh }) {
  const accepted = row.status === 'accepted'
  const [instructions, setInstructions] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function decide(decision) {
    setBusy(true); setError('')
    try { await sendAttendance(`/club/${programId}/attendance/${row.id}/decision`, { decision, expected_version: row.version, arrival_instructions: instructions }); await refresh() }
    catch (err) { setError(attendanceError(err)) }
    finally { setBusy(false) }
  }
  return <article className="c4-inbox-row"><p className="eyebrow">{accepted ? 'Accepted attendance · verified scout' : 'Attendance request · verified scout'}</p><h3>{row.title}</h3><p>{row.scout.name} · {row.scout.organization}</p>{!accepted && <p className="whitespace-pre-wrap">{row.note}</p>}
    {!accepted && <label className="c4-field">Where to stand and who to report to<textarea value={instructions} maxLength={500} rows={2} onChange={e => setInstructions(e.target.value)} /></label>}
    <div className="flex flex-wrap gap-3 mt-4">{!accepted && <button className="ch-btn dark" disabled={busy || !instructions.trim()} onClick={() => decide('accepted')}>Accept attendance</button>}<button className="ch-btn" disabled={busy} onClick={() => decide('declined')}>{accepted ? 'Rescind attendance' : 'Decline attendance'}</button></div>{error && <p role="alert" className="opp-error">{error}</p>}
  </article>
}

export function ClubToday({ programId, navigate }) {
  const generation = useRef(0)
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const refresh = useCallback(async () => {
    const run = ++generation.current
    setLoading(true); setError(''); setData(null)
    try { const response = await APIService.request(`/club/${programId}/today`); if (run === generation.current) setData(response) }
    catch (err) { if (run === generation.current) { setData(null); setError(attendanceError(err)) } }
    finally { if (run === generation.current) setLoading(false) }
  }, [programId])
  useEffect(() => { refresh(); return () => { generation.current++ } }, [refresh])
  async function moreAccepted() {
    setLoading(true); setError('')
    const run = generation.current
    try {
      const response = await APIService.request(`/club/${programId}/today?accepted_after=${data.accepted_next_cursor}`)
      if (run === generation.current) setData(old => ({ ...old, accepted_next_cursor: response.accepted_next_cursor, queues: { ...old.queues, accepted_attendance: [...old.queues.accepted_attendance, ...response.queues.accepted_attendance] } }))
    } catch (err) { if (run === generation.current) setError(attendanceError(err)) }
    finally { if (run === generation.current) setLoading(false) }
  }
  const queues = data?.queues || {}
  return <section className="c4-inbox" aria-label="Club inbox" aria-busy={loading}>
    <div className="ch-section-heading"><h2>Club inbox</h2><button className="ch-btn" onClick={refresh} disabled={loading}>Refresh</button></div>
    {error && <p role="alert" className="opp-error">{error}</p>}{loading && <p role="status">Checking your inbox…</p>}
    {data && <>
      {queues.applications && <section><h3 className="eyebrow">Applications per post</h3>{data.applications_partial && <p className="c4-meta">Counts cover the latest 100 retained applications. Open recruiting for the full list.</p>}{queues.applications.length ? queues.applications.map(post => <button className="ch-task rule-row" key={post.opportunity_id} onClick={() => navigate('recruiting')}><span className="ch-task-number">{post.new}</span><span><strong>{post.title}</strong><small>{post.total} applications · {post.new} new</small></span></button>) : <p className="c4-meta">No posts yet.</p>}</section>}
      {queues.introductions && <button className="ch-task rule-row" onClick={() => navigate('introductions')}><span className="ch-task-number">{queues.introductions.length}</span><span><strong>Introductions awaiting your consent</strong><small>You answer before the introduction proceeds.</small></span></button>}
      {queues.attendance && <section className="mt-8"><div className="ch-section-heading"><h2>Attendance requests</h2><small>{queues.attendance.length}</small></div>{queues.attendance.length ? queues.attendance.map(row => <AttendanceDecision key={row.id} row={row} programId={programId} refresh={refresh} />) : <p className="c4-meta py-6">No attendance requests waiting for your decision.</p>}{data.attendance_has_more && <p className="c4-meta">Showing the first 30 requests. Decide these to see the next requests.</p>}</section>}
      {queues.accepted_attendance && <section className="mt-8"><div className="ch-section-heading"><h2>Accepted scouts per session</h2></div>{queues.accepted_attendance.length ? queues.accepted_attendance.map(row => <AttendanceDecision key={row.id} row={row} programId={programId} refresh={refresh} />) : <p className="c4-meta py-6">No accepted scouts for upcoming sessions.</p>}{data.accepted_next_cursor && <button className="ch-btn" disabled={loading} onClick={moreAccepted}>Show more accepted scouts</button>}</section>}
      {queues.team_sheet && <section className="mt-8"><h3 className="eyebrow">Film Room · team sheet needed</h3>{queues.team_sheet.length ? queues.team_sheet.map(match => <button className="ch-task rule-row" key={match.id} onClick={() => navigate('matches')}><span><strong>{match.opponent_name || 'Club match'}</strong><small>Add who played to start the analysis.</small></span></button>) : <p className="c4-meta py-4">No matches waiting for a team sheet.</p>}</section>}
      {queues.analysing && <section className="mt-8"><h3 className="eyebrow">Film Room · analysing</h3>{queues.analysing.length ? queues.analysing.map(match => <button className="ch-task rule-row" key={match.id} onClick={() => navigate('matches')}><span><strong>{match.opponent_name || 'Club match'}</strong><small>{match.status} · Check Film Room for reports.</small></span></button>) : <p className="c4-meta py-4">No matches analysing at the moment.</p>}</section>}
    </>}
  </section>
}
