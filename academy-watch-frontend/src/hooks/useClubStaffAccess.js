import { useEffect, useState } from 'react'
import { APIService } from '@/lib/api'
import { loadStaffAccessFlag, peekStaffAccessFlag } from '@/lib/staff-access'

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
