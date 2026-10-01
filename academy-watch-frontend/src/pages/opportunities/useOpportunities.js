import { useCallback, useEffect, useState } from 'react'
import { APIService } from '@/lib/api'
import { peekFeatures } from '@/lib/features'

const unavailable = { opportunities: false, applications: false, loaded: true }
function effectiveFlags(data) {
  return { opportunities: data.opportunities === true, applications: data.opportunities === true && data.applications === true, loaded: true }
}

export function useOpportunities(enabled = true) {
  const [attempt, setAttempt] = useState(0)
  const [flags, setFlags] = useState(() => {
    const data = peekFeatures()
    return data ? effectiveFlags(data) : { opportunities: false, applications: false, loaded: false }
  })
  useEffect(() => {
    if (!enabled) return
    let active = true
    APIService.getFeatures().then(data => {
      if (active) setFlags(effectiveFlags(data))
    }).catch(() => { if (active) setFlags({ loaded: true, error: 'Could not load opportunities. Please try again later.' }) })
    return () => { active = false }
  }, [enabled, attempt])
  const retry = useCallback(() => {
    setFlags(current => ({ ...current, retrying: true }))
    setAttempt(current => current + 1)
  }, [])
  return enabled ? { ...flags, retry } : unavailable
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
