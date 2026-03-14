import { useState, useEffect, useRef } from 'react'
import { X } from 'lucide-react'
import { APIService } from '@/lib/api'

const DISMISS_KEY = 'sync_banner_dismissed'
const POLL_INTERVAL = 10_000
const LOGO_CYCLE_INTERVAL = 2_000

export default function SyncBanner() {
  const [syncing, setSyncing] = useState(false)
  const [message, setMessage] = useState('')
  const [progress, setProgress] = useState(null)
  const [teams, setTeams] = useState([])
  const [activeIndex, setActiveIndex] = useState(0)
  const [dismissed, setDismissed] = useState(
    () => sessionStorage.getItem(DISMISS_KEY) === '1',
  )
  const timerRef = useRef(null)
  const cycleRef = useRef(null)

  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const data = await APIService.request('/sync-status')
        setSyncing(data.syncing)
        setMessage(data.message || '')
        setProgress(
          data.syncing
            ? { stage: data.stage, current: data.progress, total: data.total }
            : null,
        )
        if (data.teams) setTeams(data.teams)
        if (!data.syncing) {
          sessionStorage.removeItem(DISMISS_KEY)
          setDismissed(false)
        }
      } catch {
        // Silently ignore — banner just won't show
      }
    }

    fetchStatus()
    timerRef.current = setInterval(fetchStatus, POLL_INTERVAL)
    return () => clearInterval(timerRef.current)
  }, [])

  // Cycle through team logos
  useEffect(() => {
    if (teams.length <= 1) return
    cycleRef.current = setInterval(() => {
      setActiveIndex(i => (i + 1) % teams.length)
    }, LOGO_CYCLE_INTERVAL)
    return () => clearInterval(cycleRef.current)
  }, [teams.length])

  if (!syncing || dismissed) return null

  return (
    <div className="bg-gradient-to-r from-primary/5 to-primary/10 border-b border-primary/20 px-4 py-3">
      <div className="max-w-6xl mx-auto flex items-center justify-between gap-4 text-sm">
        <div className="flex items-center gap-3 min-w-0">
          {teams.length > 0 ? (
            <div className="relative h-8 w-8 shrink-0">
              {teams.map((team, i) => (
                <img
                  key={team.team_id}
                  src={team.logo}
                  alt={team.name}
                  className="absolute inset-0 h-8 w-8 object-contain transition-opacity duration-500"
                  style={{ opacity: i === activeIndex ? 1 : 0 }}
                />
              ))}
            </div>
          ) : (
            <div className="h-8 w-8 shrink-0 rounded-full bg-primary/10 animate-pulse" />
          )}
          <div className="min-w-0">
            <p className="font-medium text-foreground">
              We're building the academy database — this may take a few minutes
            </p>
            <p className="text-xs text-primary truncate">
              {progress?.stage || 'Starting...'}
              {progress?.total > 0 && (
                <span className="ml-1 text-primary/80">
                  ({progress.current}/{progress.total})
                </span>
              )}
            </p>
          </div>
        </div>
        <button
          onClick={() => {
            sessionStorage.setItem(DISMISS_KEY, '1')
            setDismissed(true)
          }}
          className="shrink-0 p-1 rounded hover:bg-primary/10 transition-colors"
          aria-label="Dismiss banner"
        >
          <X className="h-4 w-4 text-muted-foreground/70" />
        </button>
      </div>
    </div>
  )
}
