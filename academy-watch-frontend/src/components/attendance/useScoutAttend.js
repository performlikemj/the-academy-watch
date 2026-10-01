import { useEffect, useState } from 'react'
import { APIService } from '@/lib/api'

export function useScoutAttend() {
  const [enabled, setEnabled] = useState(false)
  useEffect(() => {
    let live = true
    APIService.request('/scout-attendance/features').then(data => { if (live) setEnabled(data.scout_attend === true) }).catch(() => {})
    return () => { live = false }
  }, [])
  return enabled
}

export function attendanceError(err) {
  const messages = {
    verified_scout_required: 'Your scout verification must be approved before you can ask to attend.',
    version_conflict: 'This request changed. Refresh to see the current decision.',
    request_exists: 'You have already asked to attend this session.',
    already_decided: 'This request already has a decision. Refresh to see it.',
    no_approach_confirmation_required: 'Confirm that any approach to a player goes through an introduction.',
    invalid_arrival_instructions: 'Add where the scout should stand and who to report to.',
  }
  if (err.status === 429) return 'Too many requests. Please try again later.'
  if (err.status === 404) return 'This session or request is no longer available.'
  if (err.status === 401) return 'Sign in again to continue.'
  if (err.status === 403) return messages[err.body?.error] || 'You do not have permission for this request.'
  return messages[err.body?.error] || 'Could not complete this request. Please try again.'
}

export function sendAttendance(path, body) {
  return APIService.request(path, { method: 'POST', body: JSON.stringify(body) })
}
