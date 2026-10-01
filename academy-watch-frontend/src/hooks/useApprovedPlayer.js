import { useCallback, useContext, useEffect, useState } from 'react'
import { useAuth } from '@/context/AuthContext'
import { OpportunityStateContext } from '@/context/OpportunityStateContext'
import { APIService } from '@/lib/api'

// Private eligible adult self-claims only. Pending eligibility is distinct from no claims.
export function useApprovedPlayerRequest(flags) {
  const { token } = useAuth()
  const [attempt, setAttempt] = useState(0)
  const [state, setState] = useState({ token, attempt: 0, claims: [], error: '', loaded: false })
  // Clear during the auth transition, including returning to a previous token.
  if (state.token !== token) setState({ token, attempt, claims: [], error: '', loaded: false })
  useEffect(() => {
    if (!token || !flags.applications) return
    let active = true
    APIService.request('/me/application-claims').then(data => {
      if (active) setState({ token, attempt, claims: data.claims || [], error: '', loaded: true })
    }).catch(() => { if (active) setState({ token, attempt, claims: [], error: 'Could not check your profiles. Please try again later.', loaded: true }) })
    return () => { active = false }
  }, [token, flags.applications, attempt])
  const loading = Boolean(token && (!flags.loaded || (flags.applications && (state.token !== token || state.attempt !== attempt || !state.loaded))))
  const retry = useCallback(() => setAttempt(current => current + 1), [])
  return { claims: token && flags.applications && state.token === token ? state.claims : [], loading, error: token && flags.applications && state.token === token ? state.error : '', retry }
}

export function useApprovedPlayerState(flags) {
  const { profiles } = useContext(OpportunityStateContext)
  return flags.applications ? profiles : { ...profiles, claims: [], error: '', loading: !flags.loaded }
}

export function useApprovedPlayer(flags) { return useApprovedPlayerState(flags).claims }
