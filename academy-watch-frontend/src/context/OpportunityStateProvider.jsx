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
  const enable = useCallback((revalidateClaims = false, arrival) => {
    setRequested(true)
    const { flags: latestFlags, profiles: latestProfiles } = current.current
    const freshFeatures = arrivals.current.features !== arrival
    const freshProfiles = arrivals.current.profiles !== arrival
    arrivals.current = { features: arrival, profiles: arrival }
    if (latestFlags.error && freshFeatures) latestFlags.retry(true)
    if (latestProfiles.error ? freshProfiles : revalidateClaims) latestProfiles.retry(true)
  }, [])
  return <OpportunityStateContext.Provider value={{ flags, profiles, enable }}>{children}</OpportunityStateContext.Provider>
}
