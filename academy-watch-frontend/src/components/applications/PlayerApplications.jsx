import { OpportunityBoundary } from '@/pages/opportunities/OpportunityBoundary'
import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ComingSoon } from '@/components/interest/ComingSoon'
import { useAuth } from '@/context/AuthContext'
import { APIService } from '@/lib/api'
import { errorMessage, useOpportunities, when, write } from '@/pages/opportunities/useOpportunities'
import '@/pages/opportunities/opportunities.css'

function PlayerApplicationsContent() {
  const flags = useOpportunities()
  const { token } = useAuth()
  const [rows, setRows] = useState([])
  const [error, setError] = useState('')
  const [page, setPage] = useState(1)
  const [more, setMore] = useState(false)
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState(null)
  const load = useCallback(async () => {
    if (!token) return
    setLoading(true)
    try { const data = await APIService.request(`/me/applications?page=${page}`); setRows(data.applications); setMore(data.has_more); setError('') }
    catch (err) { setError(errorMessage(err)) }
    finally { setLoading(false) }
  }, [page, token])
  useEffect(() => { if (token && flags.applications) load() }, [flags.applications, token, load])
  async function act(row, action, response) {
    setBusy(row.id); setError('')
    try { await write(`/me/applications/${row.id}/${action}`, { expected_version: row.version, ...(response ? { response } : {}) }); await load() }
    catch (err) { setError(errorMessage(err)); if (err.status === 409) await load() }
    finally { setBusy(null) }
  }
  if (flags.error) return <p role="alert" className="floodlight-container py-8">{flags.error}</p>
  if (!flags.loaded) return <p role="status" className="floodlight-container py-8">Loading applications…</p>
  if (!flags.applications) return <ComingSoon feature="player_applications" role="player" image="/media/player-sundown.webp" title="Your next chapter." lede="Applications will have a place here. Join the list to hear when you can take the next step towards a new club." bullets={['Discover a place to develop your game.', 'Keep your applications and replies together.', 'Choose the opportunity that fits your next step.']} />
  if (!token) return <section className="p2-opportunities floodlight-container pb-16"><h2 className="opp-section">My applications</h2><p className="mt-4 text-muted">Sign in to see your applications and next steps.</p></section>
  return <section className="p2-opportunities floodlight-container pb-16" aria-labelledby="my-applications">
    <div className="flex flex-wrap items-end justify-between gap-5 border-b border-hairline pb-5"><div><p className="opp-label">Your next chapter</p><h2 id="my-applications" className="opp-section mt-3">My applications</h2></div><Link className="opp-button" to="/opportunities">Find an opportunity →</Link></div>
    {error && <p role="alert" className="opp-error">{error}</p>}
    <div aria-live="polite" aria-busy={loading}>{loading ? <p className="py-8 text-muted">Loading applications…</p> : !rows.length ? <p className="py-8 text-muted">Your applications and next steps will appear here.</p> : rows.map(row => <article key={row.id} className="opp-row min-w-0 [overflow-wrap:anywhere]">
      <div className="flex flex-wrap items-start justify-between gap-4"><div><p className="opp-label">{row.club_name}</p><h3 className="opp-section mt-3 text-2xl">{row.opportunity_title}</h3><p className="mt-2 text-sm text-muted">Applied {when(row.submitted_at, row.timezone)}</p></div><span className="opp-label">{row.status_label}</span></div>
      {row.trial_at && <div className="mt-5 text-sm leading-relaxed"><p>Trial {when(row.trial_at, row.timezone)} · {row.trial_venue}</p><p className="mt-2 whitespace-pre-wrap text-muted">{row.trial_instructions}</p><p className="mt-2">{row.reservation_state === 'confirmed' ? 'Your place is confirmed.' : row.reservation_state === 'pending' ? 'Confirm below to keep your reserved place.' : 'This reservation is no longer active.'}</p></div>}
      <div className="mt-5 flex flex-wrap gap-3">{row.status === 'invited' && row.reservation_state === 'pending' && <><button className="opp-button primary" disabled={busy === row.id} onClick={() => act(row, 'trial-response', 'accept')}>Confirm trial</button><button className="opp-button" disabled={busy === row.id} onClick={() => act(row, 'trial-response', 'decline')}>Decline trial</button></>}
        {!['signed', 'rejected', 'withdrawn'].includes(row.status) && <button className="opp-button" disabled={busy === row.id} onClick={() => act(row, 'withdraw')}>Withdraw application</button>}
      </div><p className="mt-5 text-xs text-muted">Details retained until {when(row.retention_expires_at, row.timezone)}.</p>
    </article>)}</div>
    <div className="mt-5 flex gap-3">{page > 1 && <button className="opp-button" onClick={() => setPage(page - 1)}>Previous applications</button>}{more && <button className="opp-button" onClick={() => setPage(page + 1)}>Next applications</button>}</div>
  </section>
}

export function PlayerApplications(props) { const { token } = useAuth(); return <OpportunityBoundary><PlayerApplicationsContent key={token || 'signed-out'} {...props} /></OpportunityBoundary> }
