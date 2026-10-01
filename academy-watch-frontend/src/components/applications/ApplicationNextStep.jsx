import { Link } from 'react-router-dom'
import { when } from '@/lib/opportunity-time'

export function ApplicationNextStep({ application: row }) {
  return <div role="status" className="text-sm leading-relaxed">
    <h3 className="opp-section">You applied — {row.status_label}</h3>
    {row.trial_at && <div className="mt-5"><p>Trial {when(row.trial_at, row.timezone)} · {row.trial_venue}</p><p className="mt-2 whitespace-pre-wrap text-muted">{row.trial_instructions}</p></div>}
    <p className="mt-4">{row.reservation_state === 'pending' ? 'Confirm your trial on player home to keep your reserved place.' : row.reservation_state === 'confirmed' ? 'Your trial place is confirmed.' : ['signed', 'rejected', 'withdrawn'].includes(row.status) ? 'View the outcome on player home.' : 'The club will update your application on player home.'}</p>
    <Link className="opp-button mt-5" to="/onboarding/player#my-applications">View my applications →</Link>
  </div>
}
