import { useEffect, useState } from 'react'
import { APIService } from '@/lib/api'

export function usePublicationFlag() {
  const [enabled, setEnabled] = useState(null)
  useEffect(() => {
    let live = true
    APIService.getFeatures().then(flags => { if (live) setEnabled(flags?.club_player_publication === true) }).catch(() => { if (live) setEnabled(false) })
    return () => { live = false }
  }, [])
  return enabled
}
