import { useEffect, useState } from 'react'
import { APIService } from '@/lib/api'

export function usePublicationFlag() {
  const [enabled, setEnabled] = useState(null)
  useEffect(() => {
    let live = true
    const refresh = () => APIService.getFeatures().then(flags => { if (live) setEnabled(flags?.club_player_publication === true) }).catch(() => { if (live) setEnabled(false) })
    refresh()
    const timer = window.setInterval(refresh, 30000)
    window.addEventListener('focus', refresh)
    return () => { live = false; window.clearInterval(timer); window.removeEventListener('focus', refresh) }
  }, [])
  return enabled
}
