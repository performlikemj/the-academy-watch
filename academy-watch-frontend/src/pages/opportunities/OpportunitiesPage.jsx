import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { APIService } from '@/lib/api'
import { InterestSignup } from '@/components/interest/InterestSignup'
import { OpportunitiesTeaser } from '@/pages/teasers/OpportunitiesTeaser'
import { errorMessage, useOpportunities, when, write } from './useOpportunities'
import './opportunities.css'

export function OpportunitiesPage() {
  const flags = useOpportunities()
  const [items, setItems] = useState([])
  const [kind, setKind] = useState('')
  const [page, setPage] = useState(1)
  const [more, setMore] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    if (!flags.opportunities) return
    let active = true
    setLoading(true)
    setError('')
    APIService.request(`/opportunities?page=${page}${kind ? `&type=${kind}` : ''}`).then(data => {
      if (active) { setItems(data.opportunities); setMore(data.has_more) }
    }).catch(err => { if (active) setError(errorMessage(err)) }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [flags.opportunities, kind, page])
  if (!flags.loaded || !flags.opportunities) return <OpportunitiesTeaser />
  return <div className="p2-opportunities">
    <header className="bg-night text-chalk"><div className="floodlight-container py-16 sm:py-24">
      <p className="eyebrow text-gold">Trials · open sessions · places to fill</p>
      <h1 className="opp-heading mt-5 max-w-4xl">Room for your <em className="text-gold">next</em> step.</h1>
      <p className="mt-6 max-w-xl text-base text-chalk/85">Opportunities, straight from the clubs that run them.</p>
    </div></header>
    <main className="floodlight-container py-12 sm:py-16">
      <div className="flex flex-wrap items-end justify-between gap-6 border-b border-hairline pb-6">
        <h2 className="opp-section">Open opportunities</h2>
        <label className="opp-field">Type<select aria-label="Type" value={kind} onChange={event => { setKind(event.target.value); setPage(1) }}><option value="">All opportunities</option><option value="trial">Trials</option><option value="open_session">Open sessions</option><option value="position">Positions</option></select></label>
      </div>
      {error && <p role="alert" className="opp-error">{error}</p>}
      <div aria-live="polite" aria-busy={loading}>{loading ? <p className="py-12 text-muted">Loading opportunities…</p> : !items.length ? <p className="py-12 text-muted">No open opportunities at the moment. Check back for your next step.</p> : items.map(item => <Link key={item.id} to={`/opportunities/${item.id}`} className="opp-row flex flex-wrap items-center justify-between gap-5 no-underline">
        <div className="min-w-0"><p className="opp-label">{item.club_name} · {item.type.replaceAll('_', ' ')}</p><h3 className="opp-section mt-3">{item.title}</h3><p className="mt-3 text-sm text-muted">{when(item.starts_at, item.timezone)} · {item.venue}</p></div><span className="opp-label">View opportunity →</span>
      </Link>)}</div>
      <div className="mt-8 flex gap-3">{page > 1 && <button className="opp-button" onClick={() => setPage(page - 1)}>Previous</button>}{more && <button className="opp-button" onClick={() => setPage(page + 1)}>Next</button>}</div>
    </main>
  </div>
}

function AdultApplication({ opportunity }) {
  const [claims, setClaims] = useState(null)
  const [claimId, setClaimId] = useState('')
  const [position, setPosition] = useState('')
  const [currentClub, setCurrentClub] = useState('')
  const [consent, setConsent] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [done, setDone] = useState(false)
  const [requestKey] = useState(() => crypto.randomUUID())
  useEffect(() => {
    let active = true
    APIService.request('/me/application-claims').then(data => {
      if (active) { setClaims(data.claims); setClaimId(String(data.claims[0]?.claim_id || '')) }
    }).catch(err => { if (active) { setClaims([]); setError(errorMessage(err)) } })
    return () => { active = false }
  }, [])
  async function apply(event) {
    event.preventDefault()
    setBusy(true); setError('')
    try { await write(`/opportunities/${opportunity.id}/applications`, { claim_id: Number(claimId), position, current_club: currentClub, contact_consent: consent, client_request_id: requestKey }); setDone(true) }
    catch (err) { setError(errorMessage(err)) }
    finally { setBusy(false) }
  }
  return <section className="rounded-[10px] border border-hairline p-6 sm:p-8">
    <p className="opp-label">Adult players · 18 and over</p><h2 className="opp-section mt-4">Take the next step.</h2>
    <p className="my-5 text-sm leading-relaxed text-muted">Apply with your approved adult player profile. Your application stays private with this club.</p>
    {done ? <div role="status"><p>Application sent.</p><Link className="opp-button mt-4" to="/onboarding/player">View my applications</Link></div> : claims === null ? <p>Checking your profiles…</p> : claims.length === 0 ? <><p className="text-sm">Sign in and claim your adult player profile to apply.</p><Link className="opp-button mt-4" to="/onboarding/player">Find my profile</Link></> : <form onSubmit={apply} className="grid gap-5">
      <label className="opp-field">Your player profile<select aria-label="Your player profile" value={claimId} onChange={event => setClaimId(event.target.value)}>{claims.map(claim => <option key={claim.claim_id} value={claim.claim_id}>{claim.name}</option>)}</select></label>
      <label className="opp-field">Position<input required maxLength={80} value={position} onChange={event => setPosition(event.target.value)} /></label>
      <label className="opp-field">Current club (optional)<input maxLength={180} value={currentClub} onChange={event => setCurrentClub(event.target.value)} /></label>
      <label className="flex items-start gap-3 text-sm leading-relaxed"><input type="checkbox" required checked={consent} onChange={event => setConsent(event.target.checked)} className="mt-1" />I agree that this club may contact me about my application.</label>
      <p className="text-xs leading-relaxed text-muted">Application details are deleted within 180 days, or 90 days after the trial or closure if sooner. You can withdraw on player home.</p>
      <button disabled={busy} className="opp-button primary">{busy ? 'Sending…' : 'Send application'}</button>
    </form>}
    {error && <p role="alert" className="opp-error">{error}</p>}
  </section>
}

export function OpportunityDetail() {
  const flags = useOpportunities()
  const { opportunityId } = useParams()
  const [item, setItem] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => {
    if (!flags.opportunities) return
    let active = true
    setItem(null); setError('')
    APIService.request(`/opportunities/${opportunityId}`).then(data => { if (active) setItem(data.opportunity) }).catch(err => { if (active) setError(errorMessage(err)) })
    return () => { active = false }
  }, [flags.opportunities, opportunityId])
  if (!flags.loaded || !flags.opportunities) return <OpportunitiesTeaser />
  return <main className="p2-opportunities floodlight-container py-12 sm:py-16">
    <Link to="/opportunities" className="opp-label">← All opportunities</Link>
    {error ? <p role="alert" className="opp-error mt-8">{error}</p> : !item ? <p className="py-12">Loading opportunity…</p> : <div className="mt-10 grid items-start gap-12 lg:grid-cols-[minmax(0,1fr)_440px] lg:gap-16">
      <article className="min-w-0">
        <Link to={`/programs/${item.club_slug}`} className="text-lg">{item.club_name}</Link><p className="mt-3 text-sm text-muted">{item.gender_program === 'all' ? 'All programmes' : item.gender_program}</p><p className="opp-label mt-8">{item.type.replaceAll('_', ' ')}{item.squad_name ? ` · ${item.squad_name}` : ''}</p>
        <h1 className="opp-heading mt-4">{item.title}</h1>
        <dl className="my-10 grid border-y border-hairline sm:grid-cols-3">{[['When', `${when(item.starts_at, item.timezone)}${item.ends_at ? ` – ${when(item.ends_at, item.timezone)}` : ''}`], ['Where', [item.venue, item.address].filter(Boolean).join(' · ')], ['Who', item.birth_year_min || item.birth_year_max ? `Born ${item.birth_year_min || '…'}–${item.birth_year_max || '…'} · ${item.position_requirements}` : item.position_requirements]].map(([label, value]) => <div key={label} className="min-w-0 border-b border-hairline py-6 sm:border-b-0 sm:pr-5"><dt className="opp-label">{label}</dt><dd className="mt-3 font-serif text-2xl leading-tight">{value}</dd></div>)}</dl>
        <p className="whitespace-pre-wrap font-serif text-3xl leading-snug">{item.description}</p><p className="mt-6 whitespace-pre-wrap text-base leading-relaxed text-muted">{item.instructions}</p>
        <div className="opp-row text-sm text-muted"><p>{item.coach}</p><p className="mt-2">Applications close {when(item.closes_at, item.timezone)} ({item.timezone})</p>{item.places_left !== undefined && <p className="mt-2">{item.places_left} places available</p>}</div>
      </article>
      <aside className="grid gap-8">
        {flags.applications ? <AdultApplication key={item.id} opportunity={item} /> : <section className="rounded-[10px] border border-hairline p-6"><h2 className="opp-section">Applications are coming.</h2><InterestSignup feature="player_applications" role="player" className="mt-5" /></section>}
        <section className="border-t border-hairline pt-6"><p className="opp-label">Parents &amp; guardians</p><h2 className="opp-section mt-3">A path for younger players.</h2><p className="my-5 text-sm text-muted">Under-18 applications are coming soon. Leave your own email to hear when they open.</p><InterestSignup feature="player_applications" role="parent" /></section>
      </aside>
    </div>}
  </main>
}
