import { useCallback, useState } from 'react'
import { OpportunityStateContext } from '@/context/OpportunityStateContext'
import { useOpportunityFlags } from '@/pages/opportunities/useOpportunities'
import { useApprovedPlayerRequest } from '@/hooks/useApprovedPlayer'

// Navigation and pages recover together. Private results stay keyed to the auth token;
// public feature bootstrap remains lazy and shared with the other feature consumers.
export function OpportunityStateProvider({ children }) {
  const [requested, setRequested] = useState(false)
  const enable = useCallback(() => setRequested(true), [])
  const flags = useOpportunityFlags(requested)
  const profiles = useApprovedPlayerRequest(flags)
  return <OpportunityStateContext.Provider value={{ flags, profiles, enable }}>{children}</OpportunityStateContext.Provider>
}
