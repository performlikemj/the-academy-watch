import { useEffect, useState } from 'react'
import { APIService } from '@/lib/api'
import { loadClubDirectoryFlag, peekClubDirectoryFlag } from '@/lib/club-directory'

// null = not known yet; true only when GET /api/features says club_directory is on.
export function useClubDirectory() {
  const [enabled, setEnabled] = useState(() => peekClubDirectoryFlag())
  useEffect(() => {
    let live = true
    loadClubDirectoryFlag(() => APIService.getFeatures()).then((value) => {
      if (live) setEnabled(value)
    })
    return () => { live = false }
  }, [])
  return enabled
}
