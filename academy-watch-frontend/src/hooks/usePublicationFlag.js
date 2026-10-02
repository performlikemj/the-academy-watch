import { useEffect, useState } from 'react'
import { APIService } from '@/lib/api'

export function usePublicationFlag({ poll = false } = {}) {
  const [enabled, setEnabled] = useState(null)
  useEffect(() => {
    let live = true
    const refresh = () => APIService.getFeaturesLive().then(flags => { if (live) setEnabled(flags?.club_player_publication === true) }).catch(() => { if (live) setEnabled(previous => previous ?? false) })
    refresh()
    if (!poll) return () => { live = false }
    const timer = window.setInterval(refresh, 30000)
    window.addEventListener('focus', refresh)
    return () => { live = false; window.clearInterval(timer); window.removeEventListener('focus', refresh) }
  }, [poll])
  return enabled
}
