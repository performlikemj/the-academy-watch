import { useEffect, useState } from 'react'
import { APIService } from '@/lib/api'

let flags
export function useHighlights() {
  const [enabled, setEnabled] = useState(false)
  useEffect(() => {
    let live = true
    flags ||= APIService.getFeatures().catch(() => ({}))
    flags.then(value => { if (live) setEnabled(value.highlights === true) })
    return () => { live = false }
  }, [])
  return enabled
}

export function write(path, body, method = 'POST') {
  return APIService.request(path, { method, ...(body ? { body: JSON.stringify(body) } : {}) })
}

export function message(error) {
  if (error?.status === 409) return 'This moment changed. Refresh it before trying again.'
  if (error?.status === 401) return 'Sign in again to make your decision.'
  if (error?.status === 403) return 'Your club access changed. Refresh to check your access.'
  return 'We could not save that. Your decision was not changed. Try again.'
}
