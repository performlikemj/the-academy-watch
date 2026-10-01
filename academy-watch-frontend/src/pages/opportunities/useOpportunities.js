import { useEffect, useState } from 'react'
import { APIService } from '@/lib/api'

export function useOpportunities(enabled = true) {
  const [flags, setFlags] = useState({ opportunities: false, applications: false, loaded: false })
  useEffect(() => {
    if (!enabled) return
    let active = true
    APIService.request('/opportunities/features', {}, { nullOn404: true }).then(data => {
      if (active) setFlags({ opportunities: false, applications: false, ...data, loaded: true })
    }).catch(() => { if (active) setFlags({ opportunities: false, applications: false, loaded: true }) })
    return () => { active = false }
  }, [enabled])
  return enabled ? flags : { opportunities: false, applications: false, loaded: true }
}

export { when } from '@/lib/opportunity-time'

export function errorMessage(error) {
  const code = error?.body?.error || error?.message || ''
  if (code === 'temporarily_unavailable') return 'Temporarily unavailable. Please try again later.'
  if (error?.status === 409) return 'This changed while you were working. Reload to see the latest state.'
  if (error?.status === 401) return 'Sign in to continue.'
  if (error?.status === 403) return 'An approved adult player claim and current access are required.'
  if (error?.status === 404) return 'This is no longer available.'
  return code.replaceAll('_', ' ') || 'Could not save. Please try again.'
}

export function write(path, data, method = 'POST') {
  return APIService.request(path, { method, body: JSON.stringify(data) })
}
