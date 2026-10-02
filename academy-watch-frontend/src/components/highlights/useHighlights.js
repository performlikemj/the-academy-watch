import { useEffect, useState } from 'react'
import { APIService } from '@/lib/api'

export function useHighlightsState() {
  const [state, setState] = useState({ enabled: null, status: 'loading' })
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    let live = true
    APIService.getFeaturesLive().then(value => {
      if (live) setState({ enabled: value.highlights === true, status: 'known' })
    }).catch(() => {
      // Failure is unknown on first load; a refresh retains the last known value.
      if (live) setState(current => ({ ...current, status: 'failed' }))
    })
    return () => { live = false }
  }, [attempt])
  return { ...state, retry: () => {
    setState(current => ({ ...current, status: 'loading' }))
    setAttempt(current => current + 1)
  } }
}

export function useHighlights() {
  return useHighlightsState()
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
