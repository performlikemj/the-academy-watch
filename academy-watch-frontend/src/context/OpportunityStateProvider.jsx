import { useCallback, useLayoutEffect, useRef, useState } from 'react'
import { OpportunityStateContext } from '@/context/OpportunityStateContext'
import { useOpportunityFlags } from '@/pages/opportunities/useOpportunities'
import { useApprovedPlayerRequest } from '@/hooks/useApprovedPlayer'

// Navigation and pages recover together. Private results stay keyed to the auth token;
// public feature bootstrap remains lazy and shared with the other feature consumers.
export function OpportunityStateProvider({ children }) {
  const [requested, setRequested] = useState(false)
  const flags = useOpportunityFlags(requested)
  const profiles = useApprovedPlayerRequest(flags)
  const current = useRef({ flags, profiles })
  // Publish before consumer arrival effects, without making arrival callbacks depend
  // on request results (which would cause automatic retry loops after failures).
  useLayoutEffect(() => { current.current = { flags, profiles } })
  const arrivals = useRef({ features: null, profiles: null })
  const profilesArrival = useRef(null)
  const enable = useCallback((revalidateClaims = false, arrival) => {
    setRequested(true)
    const { flags: latestFlags, profiles: latestProfiles } = current.current
    const freshFeatures = arrivals.current.features !== arrival
    const freshProfiles = arrivals.current.profiles !== arrival
    arrivals.current = { features: arrival, profiles: arrival }
    if (latestFlags.error && freshFeatures) latestFlags.retry(true)
    // Back/forward navigation can reuse a history key on a later visit.
    if (freshProfiles) profilesArrival.current = null
    // A read already pending on arrival, or recovery started by navigation,
    // also satisfies a summary that mounts after its own profile data loads.
    if (latestProfiles.loading || latestProfiles.refreshing) profilesArrival.current = arrival
    const refreshProfiles = latestProfiles.error ? freshProfiles : revalidateClaims && profilesArrival.current !== arrival
    if (refreshProfiles && latestFlags.applications) {
      profilesArrival.current = arrival
      latestProfiles.retry(true)
    }
  }, [])
  return <OpportunityStateContext.Provider value={{ flags, profiles, enable }}>{children}</OpportunityStateContext.Provider>
}
