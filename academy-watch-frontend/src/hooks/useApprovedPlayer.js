import { useEffect, useState } from 'react'
import { useAuth } from '@/context/AuthContext'
import { APIService } from '@/lib/api'

// Private self-claims only, and only while the applications feature is available.
export function useApprovedPlayer(flags) {
  const { token } = useAuth()
  const [state, setState] = useState({ token: null, claims: [] })
  useEffect(() => {
    if (!token || !flags.applications) return
    let active = true
    APIService.request('/me/application-claims').then(data => {
      if (active) setState({ token, claims: data.claims || [] })
    }).catch(() => { if (active) setState({ token, claims: [] }) })
    return () => { active = false }
  }, [token, flags.applications])
  return token && flags.applications && state.token === token ? state.claims : []
}
