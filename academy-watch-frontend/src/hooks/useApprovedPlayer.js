import { useCallback, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'
import { OpportunityStateContext } from '@/context/OpportunityStateContext'
import { APIService } from '@/lib/api'

// Private eligible adult self-claims only. Pending eligibility is distinct from no claims.
export function useApprovedPlayerRequest(flags) {
  const { token } = useAuth()
  const [state, setState] = useState({ token, claims: [], error: '', loaded: false, refreshing: false })
  const inflight = useRef(null)
  // A fresh lifetime for every auth/flag transition also rejects returning-account replies.
  const lifetime = useMemo(() => ({ token, applications: flags.applications }), [token, flags.applications])
  const currentLifetime = useRef(null)
  useLayoutEffect(() => {
    currentLifetime.current = lifetime
    return () => { currentLifetime.current = null }
  }, [lifetime])
  if (state.token !== token) setState({ token, claims: [], error: '', loaded: false, refreshing: false })
  const retry = useCallback((arrival = false) => {
    if (!token || !flags.applications) return
    if (inflight.current?.lifetime === lifetime) return inflight.current.promise
    setState(current => ({ ...current, refreshing: true, ...(arrival === true && current.error ? { error: '', loaded: false } : {}) }))
    const request = APIService.request('/me/application-claims').then(data => {
      if (currentLifetime.current === lifetime) setState({ token, claims: data.claims || [], error: '', loaded: true, refreshing: false })
    }).catch(() => {
      if (currentLifetime.current === lifetime) setState({ token, claims: [], error: 'Could not check your profiles. Please try again later.', loaded: true, refreshing: false })
    }).finally(() => { if (inflight.current?.promise === request) inflight.current = null })
    inflight.current = { lifetime, promise: request }
    return request
  }, [token, flags.applications, lifetime])
  useEffect(() => { retry() }, [retry])
  const loading = Boolean(token && (!flags.loaded || (flags.applications && (state.token !== token || !state.loaded))))
  return { claims: token && flags.applications && state.token === token ? state.claims : [], loading, refreshing: state.token === token && state.refreshing, error: token && flags.applications && state.token === token ? state.error : '', retry }
}

export function useApprovedPlayerState(flags, revalidate = false) {
  const { profiles, enable } = useContext(OpportunityStateContext)
  const { key, pathname } = useLocation()
  const arrival = `${key}:${pathname}`
  useEffect(() => { if (revalidate) enable(true, arrival) }, [revalidate, enable, arrival])
  return flags.applications ? profiles : { ...profiles, claims: [], error: '', loading: !flags.loaded }
}

export function useApprovedPlayer(flags) { return useApprovedPlayerState(flags).claims }
