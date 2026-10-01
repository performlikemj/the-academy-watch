import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { APIService } from '@/lib/api'
import { useAuth } from '@/context/AuthContext'
import { useOpportunities, errorMessage } from '@/pages/opportunities/useOpportunities'
import { ComingSoon } from '@/components/interest/ComingSoon'
import '@/styles/floodlight-player.css'

function PlayerApplicationsSummary() {
  const flags = useOpportunities()
  const { token } = useAuth()
  const [rows, setRows] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => {
    if (!token || !flags.applications) return
    let active = true
    APIService.request('/me/applications').then(data => { if (active) setRows(data.applications) }).catch(err => { if (active) setError(errorMessage(err)) })
    return () => { active = false }
  }, [token, flags.applications])
  if (flags.applications && token) return <section className="fl-applications border-t border-hairline py-8" aria-label="Your applications">
    <h2 className="font-serif text-4xl">Your applications</h2>
    {error ? <p role="alert" className="mt-4 text-danger">{error}</p> : rows === null ? <p className="mt-4 text-muted">Loading applications…</p> : rows.length ? <ul className="mt-5">{rows.slice(0, 3).map(row => <li key={row.id} className="rule-row flex flex-wrap justify-between gap-2 py-4"><span>{row.opportunity_title}</span><span className="eyebrow">{row.status_label}</span></li>)}</ul> : <p className="mt-4 text-muted">Your applications and next steps will appear here.</p>}
    <Link className="mt-5 inline-flex rounded-full border border-ink px-5 py-3 text-sm" to="/onboarding/player#my-applications">View my applications →</Link>
  </section>
  return <section className="fl-applications" aria-label="Player applications coming soon">
    <ComingSoon feature="player_applications" role="player" title="Your next chapter."
      lede="Applications will have a place here. Join the list to hear when you can take the next step towards a new club."
      image="/media/player-sundown.webp"
      bullets={['Find an opportunity that fits your game.', 'Keep your applications and replies together.']} />
  </section>
}

export function PlayerApplicationsTeaser() { const { token } = useAuth(); return <PlayerApplicationsSummary key={token || 'signed-out'} /> }
