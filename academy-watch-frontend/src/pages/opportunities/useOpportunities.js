import { useEffect, useState } from 'react'
import { APIService } from '@/lib/api'

export function useOpportunities() {
  const [flags, setFlags] = useState({ opportunities: false, applications: false, loaded: false })
  useEffect(() => {
    let active = true
    APIService.request('/opportunities/features').then(data => {
      if (active) setFlags({ ...data, loaded: true })
    }).catch(() => { if (active) setFlags({ opportunities: false, applications: false, loaded: true }) })
    return () => { active = false }
  }, [])
  return flags
}

export function when(value, timezone = 'UTC') {
  if (!value) return 'Date to be arranged'
  return new Intl.DateTimeFormat('en-GB', { dateStyle: 'medium', timeStyle: 'short', timeZone: timezone }).format(new Date(value))
}

export function errorMessage(error) {
  const code = error?.body?.error || error?.message || ''
  if (error?.status === 409) return 'This changed while you were working. Reload to see the latest state.'
  if (error?.status === 401) return 'Sign in to continue.'
  if (error?.status === 403) return 'An approved adult player claim and current access are required.'
  if (error?.status === 404) return 'This is no longer available.'
  return code.replaceAll('_', ' ') || 'Could not save. Please try again.'
}

export function write(path, data, method = 'POST') {
  return APIService.request(path, { method, body: JSON.stringify(data) })
}
