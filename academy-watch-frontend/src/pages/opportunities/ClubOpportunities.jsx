import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { APIService } from '@/lib/api'
import { SectionHeading, TeaserBlock } from '@/components/public/Floodlight'
import { useOpportunities, errorMessage } from './useOpportunities'
import { whenRange } from '@/lib/opportunity-time'

export function ClubOpportunities({ programId }) {
  const flags = useOpportunities()
  const [state, setState] = useState({ items: [], loading: true, error: '' })
  const [page, setPage] = useState(1)
  const [more, setMore] = useState(false)
  useEffect(() => { setPage(1) }, [programId])
  useEffect(() => {
    if (!flags.opportunities) return
    let active = true
    setState({ items: [], loading: true, error: '' })
    APIService.request(`/opportunities?program_id=${programId}&page=${page}`).then(data => {
      if (active) { setState({ items: data.opportunities, loading: false, error: '' }); setMore(data.has_more) }
    }).catch(err => { if (active) setState({ items: [], loading: false, error: errorMessage(err) }) })
    return () => { active = false }
  }, [flags.opportunities, programId, page])
  return <section aria-labelledby="club-opportunities">
    <SectionHeading id="club-opportunities" title="Opportunities" meta={flags.loaded && !flags.error ? (flags.opportunities ? 'Open now' : 'Coming soon') : undefined} />
    {flags.error ? <p role="alert" className="py-6 text-danger">{flags.error}</p> : !flags.loaded ? <p className="py-6 text-muted" role="status">Loading opportunities…</p> : !flags.opportunities ? <TeaserBlock className="mt-6" feature="opportunities" eyebrow="Trials · open sessions · places to fill" title="Straight from the club, soon." lede="Clubs will be able to post trials and open sessions here, and you’ll apply in about a minute. Leave your email and we’ll tell you when it opens." /> : <div aria-live="polite" aria-busy={state.loading}>
      {state.error ? <p role="alert" className="mt-6 text-danger">{state.error}</p> : state.loading ? <p className="py-6 text-muted">Loading opportunities…</p> : !state.items.length ? <p className="py-6 text-muted">No open opportunities at this club right now.</p> : state.items.map(item => <Link className="rule-row flex flex-wrap justify-between gap-4 py-6" key={item.id} to={`/opportunities/${item.id}`}><span className="min-w-0 max-w-full [overflow-wrap:anywhere]"><span className="block font-serif text-3xl">{item.title}</span><span className="mt-2 block text-sm text-muted">{whenRange(item.starts_at, item.ends_at, item.timezone)} · {item.venue}</span></span><span className="eyebrow self-center">View opportunity →</span></Link>)}
      <div className="mt-4 flex gap-4">{page > 1 && <button className="underline" onClick={() => setPage(page - 1)}>Previous opportunities</button>}{more && <button className="underline" onClick={() => setPage(page + 1)}>Next opportunities</button>}</div>
    </div>}
  </section>
}
