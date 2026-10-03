import { useCallback, useEffect, useState } from 'react'
import { APIService } from '@/lib/api'
import { peekFeatures } from '@/lib/features'
import { watchEntryRead } from './entry-read'

export function useClubEntryFeatures() {
  const [state, setState] = useState(() => {
    const features = peekFeatures()
    return { enabled: features ? features.club_staff_access === true : null, pending: !features, error: false }
  })
  const [attempt, setAttempt] = useState(0)
  const retry = useCallback(() => {
    setState({ enabled: null, pending: true, error: false })
    setAttempt(current => current + 1)
  }, [])
  useEffect(() => {
    let live = true
    const unavailable = () => { if (live) setState({ enabled: null, pending: false, error: true }) }
    // Initial consumers share main's bootstrap. Retry is local, so a dead or
    // superseded shared read cannot determine this new attempt's result.
    watchEntryRead(() => attempt === 0 ? APIService.getFeatures() : APIService.request('/features'), unavailable)
      .then(features => {
        if (live) setState({ enabled: features?.club_staff_access === true, pending: false, error: false })
      }).catch(unavailable)
    return () => { live = false }
  }, [attempt])
  return { ...state, retry }
}
