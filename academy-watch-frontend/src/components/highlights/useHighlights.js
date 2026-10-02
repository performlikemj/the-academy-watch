import { useEffect, useState } from 'react'
import { APIService } from '@/lib/api'

export function useHighlightsState() {
  const [state, setState] = useState({ enabled: false, loaded: false })
  useEffect(() => {
    let live = true
    APIService.getFeatures().catch(() => ({})).then(value => { if (live) setState({ enabled: value.highlights === true, loaded: true }) })
    return () => { live = false }
  }, [])
  return state
}

export function useHighlights() {
  return useHighlightsState().enabled
}

export function write(path, body, method = 'POST') {
  return APIService.request(path, { method, ...(body ? { body: JSON.stringify(body) } : {}) })
}

export function message(error) {
  if (error?.message === 'highlight_admin_taken_down') return 'This moment was taken down by The Academy Watch and cannot be picked.'
  if (error?.status === 409) return 'This moment changed. Refresh it before trying again.'
  if (error?.status === 401) return 'Sign in again to make your decision.'
  if (error?.status === 403) return 'Your club access changed. Refresh to check your access.'
  return 'We could not save that. Your decision was not changed. Try again.'
}
