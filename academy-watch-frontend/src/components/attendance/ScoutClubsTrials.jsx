import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { APIService } from '@/lib/api'
import { useAuth, useAuthUI } from '@/context/AuthContext'
import { ScoutSurface, ScoutHeader, DeskSectionTitle } from '@/components/scout/ScoutDesk'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { when } from '@/lib/opportunity-time'
import { attendanceError, sendAttendance } from './useScoutAttend'
import { LocationControl } from './LocationControl'
import './attendance.css'

export function ScoutTabs({ clubs = false }) {
  return <nav className="c4-tabs" aria-label="Scout Desk views"><Link to="/scout" aria-current={!clubs ? 'page' : undefined}>Players</Link><Link to="/scout?desk=clubs" aria-current={clubs ? 'page' : undefined}>Clubs &amp; trials</Link></nav>
}

function AskToAttend({ item, onClose, onSent }) {
  const [note, setNote] = useState('')
  const [confirmed, setConfirmed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function submit(e) {
    e.preventDefault(); setBusy(true); setError('')
    try { const data = await sendAttendance(`/opportunities/${item.id}/attendance`, { note, no_approach_confirmed: confirmed }); onSent(data.attendance); onClose() }
    catch (err) { setError(attendanceError(err)) }
    finally { setBusy(false) }
  }
  return <Dialog open onOpenChange={value => { if (!value && !busy) onClose() }}><DialogContent className="dark c4-ask bg-night text-chalk max-h-[90dvh] overflow-y-auto">
    <DialogHeader><DialogTitle className="font-serif text-4xl font-normal">Ask to attend</DialogTitle><DialogDescription className="text-muted-dark">The club decides. Approval gives permission to observe this session.</DialogDescription></DialogHeader>
    <p className="c4-meta">{item.club_name} · {when(item.starts_at, item.timezone)} · {item.venue}</p><h2 className="font-serif text-3xl">{item.title}</h2>
    <form onSubmit={submit} className="grid gap-5"><label className="c4-field">A note to the club<textarea maxLength={500} rows={4} value={note} onChange={e => setNote(e.target.value)} /><span className="c4-meta">{note.length} / 500</span></label>
      <p className="text-sm text-muted-dark">You see the session, never who applied. Speaking to a player still goes through an introduction.</p>
      <label className="flex items-start gap-3 text-sm"><input type="checkbox" required checked={confirmed} onChange={e => setConfirmed(e.target.checked)} />I will use the introduction process for any approach to a player.</label>
      <p className="c4-meta">Requests are deleted within 180 days and normally 90 days after the session.</p>
      {error && <p role="alert" className="c4-error">{error}</p>}<button className="c4-button primary" disabled={!confirmed || busy}>{busy ? 'Sending…' : 'Send attendance request'}</button>
    </form>
  </DialogContent></Dialog>
}

export function ScoutClubsTrials() {
  const { token } = useAuth()
  const { openLoginModal } = useAuthUI()
  const [location, setLocation] = useState(null)
  const [radius, setRadius] = useState(50)
  const [query, setQuery] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [reload, setReload] = useState(0)
  const [clubs, setClubs] = useState([])
  const [trials, setTrials] = useState([])
  const [more, setMore] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const requestGeneration = useRef(0)
  const [requests, setRequests] = useState([])
  const [verified, setVerified] = useState(false)
  const [ask, setAsk] = useState(null)
  const [busy, setBusy] = useState(false)
  const refreshRequests = useCallback(async () => {
    const run = ++requestGeneration.current
    setVerified(false); setRequests([])
    if (!token) return
    try {
      const profile = await APIService.request('/auth/me')
      if (!profile.is_verified_scout) return
      let next = null; const rows = []
      do { const data = await APIService.request(`/me/scout-attendance${next ? `?after=${next}` : ''}`); rows.push(...data.attendance); next = data.next_cursor } while (next)
      if (run === requestGeneration.current) { setRequests(rows); setVerified(true) }
    } catch (err) { if (run === requestGeneration.current && err.status !== 403) setError(attendanceError(err)) }
  }, [token])
  useEffect(() => { refreshRequests(); return () => { requestGeneration.current++ } }, [refreshRequests])
  useEffect(() => {
    let active = true
    setLoading(true); setError('')
    const position = location ? { ...location, radius_km: radius } : {}
    Promise.all([sendAttendance('/opportunities/search', { ...position, adult_sessions: true, page }), sendAttendance('/club-directory/search', { ...position, ...(search ? { q: search } : {}), page })]).then(([posts, directory]) => {
      if (active) { setTrials(posts.opportunities); setClubs(directory.clubs); setMore(posts.has_more || directory.has_more) }
    }).catch(err => { if (active) { setTrials([]); setClubs([]); setError(attendanceError(err)) } }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [location, radius, search, page, reload])
  async function withdraw(row) {
    setBusy(true); setError('')
    try { await sendAttendance(`/me/scout-attendance/${row.id}/withdraw`, { expected_version: row.version }); await refreshRequests() }
    catch (err) { setError(attendanceError(err)) }
    finally { setBusy(false) }
  }
  const distance = item => item.distance_km == null ? 'Distance unavailable' : `${item.distance_km} km from you`
  return <ScoutSurface><div className="floodlight-container c4-night pb-28">
    <ScoutHeader eyebrow="Scout Desk · Clubs & trials" title="Where the football" accent="is." lede="Find adult trials and sessions. Ask the club before attending."><ScoutTabs clubs />
      <form className="c4-search" onSubmit={e => { e.preventDefault(); setSearch(query.trim()); setPage(1) }}><label className="c4-field">Find a club<input placeholder="Club, town or postcode" value={query} onChange={e => setQuery(e.target.value)} minLength={2} maxLength={80} /></label><button className="c4-button">Search clubs</button></form>
      <LocationControl dark location={location} setLocation={value => { setLocation(value); setPage(1) }} radius={radius} setRadius={value => { setRadius(value); setPage(1) }} />
    </ScoutHeader>
    {error && <p role="alert" className="c4-error">{error} <button className="c4-button" onClick={() => { setPage(1); refreshRequests(); setReload(value => value + 1) }}>Refresh</button></p>}
    {!token ? <p className="c4-notice"><button className="c4-button" onClick={() => openLoginModal()}>Sign in</button> to ask to attend a session.</p> : !verified && <p className="c4-notice">Attendance requests are for verified scouts. <Link to="/scout/verification">Get verified →</Link></p>}
    <section className="mb-14" aria-busy={loading}><DeskSectionTitle title="Trials & sessions" />
      {loading ? <p className="py-8 c4-meta">Finding sessions…</p> : !trials.length ? <p className="py-8 c4-meta">No adult sessions are open here yet. Try a wider area or browse without location.</p> : trials.map(item => {
        const row = requests.find(r => r.opportunity_id === item.id)
        return <article className="c4-row" key={item.id}><div><p className="eyebrow text-gold">{item.club_name} · {item.type.replaceAll('_', ' ')}</p><h2 className="font-serif text-3xl mt-3"><Link to={`/opportunities/${item.id}`}>{item.title}</Link></h2><p className="c4-meta mt-3">{when(item.starts_at, item.timezone)} · {item.venue}</p><p className="c4-meta mt-2">{distance(item)}</p>
          {row && <p role="status" className="mt-4 text-gold">{row.status === 'pending' ? 'Request sent · waiting on the club' : `Attendance ${row.status}`}</p>}{row?.status === 'accepted' && <p className="mt-3 whitespace-pre-wrap text-sm">{row.arrival_instructions}</p>}</div>
          {row && ['pending', 'accepted'].includes(row.status) ? <button className="c4-button" disabled={busy} onClick={() => withdraw(row)}>Withdraw request</button> : !row && <button className="c4-button" disabled={!verified} onClick={() => setAsk(item)}>Ask to attend</button>}</article>
      })}
    </section>
    {requests.some(row => !trials.some(item => item.id === row.opportunity_id)) && <section className="mb-14"><DeskSectionTitle title="Your attendance" />{requests.filter(row => !trials.some(item => item.id === row.opportunity_id)).map(row => <article className="c4-row" key={row.id}><div><p className="eyebrow text-gold">{row.club_name}</p><h2 className="font-serif text-3xl mt-3">{row.title}</h2><p role="status" className="mt-4 text-gold">{row.status === 'pending' ? 'Request sent · waiting on the club' : `Attendance ${row.status}`}</p>{row.status === 'accepted' && <p className="mt-3 whitespace-pre-wrap text-sm">{row.arrival_instructions}</p>}</div>{['pending', 'accepted'].includes(row.status) && <button className="c4-button" disabled={busy} onClick={() => withdraw(row)}>Withdraw request</button>}</article>)}</section>}
    <section><DeskSectionTitle title="Clubs" />{loading ? <p className="py-8 c4-meta">Finding clubs…</p> : !clubs.length ? <p className="py-8 c4-meta">No listed clubs match this search.</p> : clubs.map(club => <article className="c4-row" key={club.id}><div><p className="eyebrow text-gold">{[club.city, club.region, club.country].filter(Boolean).join(' · ')}</p><h2 className="font-serif text-3xl mt-3"><Link to={`/programs/${club.slug}`}>{club.name}</Link></h2><p className="c4-meta mt-3">{distance(club)}{club.open_opportunities != null ? ` · ${club.open_opportunities} open opportunities` : ''}</p></div><Link className="c4-button" to={`/programs/${club.slug}`}>View club →</Link></article>)}</section>
    <div className="flex gap-3 mt-8">{page > 1 && <button className="c4-button" onClick={() => setPage(page - 1)}>Previous</button>}{more && <button className="c4-button" onClick={() => setPage(page + 1)}>Next</button>}</div>
    <p className="c4-meta mt-10">Adult trials and sessions only. Applicant identities stay private with the club.</p>
    {ask && <AskToAttend item={ask} onClose={() => setAsk(null)} onSent={row => setRequests(old => [...old, row])} />}
  </div></ScoutSurface>
}
