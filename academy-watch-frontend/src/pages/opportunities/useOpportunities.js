import { useCallback, useContext, useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { APIService } from '@/lib/api'
import { OpportunityStateContext } from '@/context/OpportunityStateContext'
import { peekFeatures } from '@/lib/features'

const unavailable = { opportunities: false, applications: false, loaded: true }
function effectiveFlags(data) {
  return { opportunities: data.opportunities === true, applications: data.opportunities === true && data.applications === true, loaded: true }
}

export function useOpportunityFlags(enabled) {
  const inflight = useRef(null)
  const mounted = useRef(true)
  const [flags, setFlags] = useState(() => {
    const data = peekFeatures()
    return data ? effectiveFlags(data) : { opportunities: false, applications: false, loaded: false }
  })
  const retry = useCallback((arrival = false) => {
    if (inflight.current) return inflight.current
    setFlags(current => arrival === true ? { ...current, error: '', loaded: false, retrying: true } : { ...current, retrying: true })
    const request = APIService.getFeatures().then(data => {
      if (mounted.current) setFlags(effectiveFlags(data))
    }).catch(() => {
      if (mounted.current) setFlags({ loaded: true, error: 'Could not load opportunities. Please try again later.' })
    }).finally(() => { if (inflight.current === request) inflight.current = null })
    inflight.current = request
    return request
  }, [])
  useEffect(() => {
    mounted.current = true
    if (enabled) retry()
    return () => { mounted.current = false }
  }, [enabled, retry])
  return { ...flags, retry }
}

export function useOpportunities(enabled = true) {
  const { flags, enable } = useContext(OpportunityStateContext)
  const { key, pathname } = useLocation()
  const arrival = `${key}:${pathname}`
  useEffect(() => { if (enabled) enable(false, arrival) }, [enabled, enable, arrival])
  return enabled ? flags : unavailable
}

export { when } from '@/lib/opportunity-time'

export function errorMessage(error) {
  const code = error?.body?.error || error?.message || ''
  if (code === 'temporarily_unavailable') return 'Temporarily unavailable. Please try again later.'
  if (code === 'already_applied') return 'You already applied. View your applications and next steps on player home.'
  if (error?.status === 409) return 'This changed while you were working. Reload to see the latest state.'
  if (error?.status === 401) return 'Sign in to continue.'
  if (error?.status === 403) return 'An approved adult player claim and current access are required.'
  if (error?.status === 404) return 'This is no longer available.'
  return code.replaceAll('_', ' ') || 'Could not save. Please try again.'
}

export function write(path, data, method = 'POST') {
  return APIService.request(path, { method, body: JSON.stringify(data) })
}
