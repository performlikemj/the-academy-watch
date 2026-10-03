import { useCallback, useEffect, useState } from 'react'
import { APIService, abandonMyClubFeatureRead } from '@/lib/api'
import { readWithDeadline } from '@/pages/club-console/entry-read'
import { loadStaffAccessFlag, peekStaffAccessFlag } from '@/lib/staff-access'
import { peekFeatures } from '@/lib/features'

// null = not known yet; true only when GET /api/features says club_staff_access is on.
export function useClubStaffAccess() {
  const [enabled, setEnabled] = useState(() => peekStaffAccessFlag())
  useEffect(() => {
    let live = true
    loadStaffAccessFlag(() => APIService.getFeatures()).then((value) => {
      if (live) setEnabled(value)
    })
    return () => { live = false }
  }, [])
  return enabled
}

// Club entry must distinguish an unavailable bootstrap from an explicit OFF.
// APIService shares the bootstrap with all other feature consumers.
export function useClubStaffAccessState() {
  const [state, setState] = useState(() => {
    const features = peekFeatures()
    return { enabled: features ? features.club_staff_access === true : null, pending: !features, error: false }
  })
  const [attempt, setAttempt] = useState(0)
  const retry = useCallback(() => {
    if (state.error === 'TimeoutError') abandonMyClubFeatureRead()
    setState({ enabled: null, pending: true, error: false })
    setAttempt(current => current + 1)
  }, [state.error])
  useEffect(() => {
    let live = true
    readWithDeadline(() => APIService.getFeatures()).then(features => {
      if (live) setState({ enabled: features?.club_staff_access === true, pending: false, error: false })
    }).catch(error => {
      if (live) setState({ enabled: null, pending: false, error: error.name || true })
    })
    return () => { live = false }
  }, [attempt])
  return { ...state, retry }
}
