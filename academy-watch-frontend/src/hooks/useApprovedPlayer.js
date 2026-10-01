import { useCallback, useEffect, useState } from 'react'
import { useAuth } from '@/context/AuthContext'
import { APIService } from '@/lib/api'

// Private eligible adult self-claims only. Pending eligibility is distinct from no claims.
export function useApprovedPlayerState(flags) {
  const { token } = useAuth()
  const [attempt, setAttempt] = useState(0)
  const [state, setState] = useState({ token: null, attempt: 0, claims: [], error: '' })
  useEffect(() => {
    if (!token || !flags.applications) return
    let active = true
    APIService.request('/me/application-claims').then(data => {
      if (active) setState({ token, attempt, claims: data.claims || [], error: '' })
    }).catch(() => { if (active) setState({ token, attempt, claims: [], error: 'Could not check your profiles. Please try again later.' }) })
    return () => { active = false }
  }, [token, flags.applications, attempt])
  const loading = Boolean(token && (!flags.loaded || (flags.applications && (state.token !== token || state.attempt !== attempt))))
  const retry = useCallback(() => setAttempt(current => current + 1), [])
  return { claims: token && flags.applications && state.token === token ? state.claims : [], loading, error: token && flags.applications && state.token === token ? state.error : '', retry }
}

export function useApprovedPlayer(flags) { return useApprovedPlayerState(flags).claims }
