import { useState, useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import {
  Drawer,
  DrawerContent,
  DrawerHeader,
  DrawerTitle,
  DrawerFooter,
} from '@/components/ui/drawer'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Loader2, ChevronRight } from 'lucide-react'
import { APIService } from '@/lib/api'
import { cn } from '@/lib/utils'

/* ── Skeleton loader matching final layout ─────────────────────── */

function Skeleton({ className }) {
  return <div className={cn('animate-pulse rounded bg-muted', className)} />
}

function PreviewSkeleton() {
  return (
    <div className="space-y-5 px-1">
      {/* Header */}
      <div className="space-y-2">
        <Skeleton className="h-5 w-40" />
        <Skeleton className="h-3 w-56" />
        <Skeleton className="h-3 w-32" />
      </div>
      {/* Stat cards */}
      <div className="grid grid-cols-4 gap-2">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="rounded-lg border p-3 space-y-2">
            <Skeleton className="h-6 w-10 mx-auto" />
            <Skeleton className="h-3 w-12 mx-auto" />
          </div>
        ))}
      </div>
      {/* Form rows */}
      <div className="space-y-1.5">
        <Skeleton className="h-4 w-24 mb-2" />
        {[...Array(5)].map((_, i) => (
          <Skeleton key={i} className="h-8 w-full" />
        ))}
      </div>
    </div>
  )
}

/* ── Stat card ─────────────────────────────────────────────────── */

function StatCard({ value, label, accent }) {
  const colorClass =
    accent === 'emerald' ? 'text-emerald-600 dark:text-emerald-400' :
    accent === 'amber' ? 'text-amber-600 dark:text-amber-400' :
    'text-foreground'

  return (
    <div className="rounded-lg border bg-card p-3 text-center">
      <div className={cn('text-xl font-bold tabular-nums', colorClass)}>
        {value ?? '\u2013'}
      </div>
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground mt-0.5">
        {label}
      </div>
    </div>
  )
}

/* ── Rating badge with color coding ────────────────────────────── */

function RatingBadge({ rating }) {
  if (rating == null) return <span className="text-muted-foreground">\u2013</span>
  const r = Number(rating)
  const color =
    r >= 7.5 ? 'text-emerald-600 dark:text-emerald-400 font-bold' :
    r >= 7.0 ? 'text-emerald-600/80 dark:text-emerald-400/80' :
    r >= 6.5 ? 'text-foreground' :
    r >= 6.0 ? 'text-muted-foreground' :
    'text-red-500 dark:text-red-400'
  return <span className={cn('tabular-nums text-xs', color)}>{r.toFixed(1)}</span>
}

/* ── Main drawer ───────────────────────────────────────────────── */

export function PlayerPreviewDrawer({ playerId, open, onOpenChange }) {
  const [profile, setProfile] = useState(null)
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const abortRef = useRef(null)
  const loadedIdRef = useRef(null)

  useEffect(() => {
    if (!open || !playerId || loadedIdRef.current === playerId) return

    // Abort previous fetch if still in flight
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    setLoading(true)
    setError(null)
    setProfile(null)
    setStats(null)

    Promise.all([
      APIService.getPublicPlayerProfile(playerId),
      APIService.getPublicPlayerStats(playerId),
    ])
      .then(([profileData, statsData]) => {
        if (controller.signal.aborted) return
        setProfile(profileData)
        setStats(statsData)
        loadedIdRef.current = playerId
      })
      .catch((err) => {
        if (controller.signal.aborted) return
        setError(err.message || 'Failed to load player data')
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })

    return () => controller.abort()
  }, [playerId, open])

  // Reset when drawer fully closes
  useEffect(() => {
    if (!open) {
      loadedIdRef.current = null
    }
  }, [open])

  // Derive display data
  const name = profile?.player_name || profile?.name || 'Player'
  const position = profile?.position || stats?.position || '\u2013'
  const age = profile?.age ?? stats?.age
  const nationality = profile?.nationality || stats?.nationality
  const parentClub = profile?.parent_club || profile?.team_name
  const currentClub = profile?.current_club_name || profile?.loan_club

  // Season totals from stats
  const matches = stats?.matches || stats?.recent_matches || []
  const seasonGoals = stats?.goals ?? matches.reduce((s, m) => s + (m.goals || 0), 0)
  const seasonAssists = stats?.assists ?? matches.reduce((s, m) => s + (m.assists || 0), 0)
  const seasonApps = stats?.appearances ?? matches.length
  const avgRating = stats?.avg_rating ?? (
    matches.length > 0
      ? (matches.reduce((s, m) => s + (m.rating || 0), 0) / matches.length).toFixed(1)
      : null
  )

  const recentMatches = matches.slice(0, 5)

  return (
    <Drawer open={open} onOpenChange={onOpenChange}>
      <DrawerContent className="max-h-[85vh]">
        <DrawerHeader className="pb-2">
          <DrawerTitle className="sr-only">{name}</DrawerTitle>
        </DrawerHeader>

        <ScrollArea className="flex-1 overflow-y-auto px-4 pb-2">
          {loading ? (
            <PreviewSkeleton />
          ) : error ? (
            <div className="text-center py-8 space-y-2">
              <p className="text-sm text-muted-foreground">{error}</p>
              <Button variant="outline" size="sm" asChild>
                <Link to={`/players/${playerId}`}>View full profile</Link>
              </Button>
            </div>
          ) : profile ? (
            <div className="space-y-4">
              {/* ── Player header ── */}
              <div>
                <div className="flex items-start justify-between gap-2">
                  <h2 className="text-lg font-bold leading-tight">{name}</h2>
                  <Badge
                    variant="outline"
                    className="shrink-0 text-[10px] uppercase tracking-wider border-emerald-600/30 text-emerald-700 dark:text-emerald-400"
                  >
                    {position}
                  </Badge>
                </div>
                <div className="text-sm text-muted-foreground mt-1 space-y-0.5">
                  {parentClub && currentClub && parentClub !== currentClub ? (
                    <p>{parentClub} <span className="text-muted-foreground/50">\u2192</span> {currentClub}</p>
                  ) : (
                    <p>{parentClub || currentClub || '\u2013'}</p>
                  )}
                  <p className="text-xs">
                    {[age && `${age} yrs`, nationality].filter(Boolean).join(' \u00b7 ')}
                  </p>
                </div>
              </div>

              {/* ── Season stats grid ── */}
              <div className="grid grid-cols-4 gap-2">
                <StatCard value={seasonGoals} label="Goals" accent="emerald" />
                <StatCard value={seasonAssists} label="Assists" accent="amber" />
                <StatCard value={seasonApps} label="Apps" />
                <StatCard value={avgRating} label="Rating" />
              </div>

              {/* ── Recent form ── */}
              {recentMatches.length > 0 && (
                <div>
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">
                    Recent Form
                  </h3>
                  <div className="rounded-lg border divide-y">
                    {recentMatches.map((m, i) => (
                      <div
                        key={i}
                        className="flex items-center gap-2 px-3 py-2 text-xs"
                        style={{ animationDelay: `${i * 50}ms` }}
                      >
                        <span className="flex-1 min-w-0 truncate font-medium">
                          {m.opponent || m.team_name || '\u2013'}
                        </span>
                        <Badge variant="secondary" className="text-[10px] tabular-nums shrink-0">
                          {m.minutes || 0}\u2032
                        </Badge>
                        <div className="flex gap-1 w-10 justify-end shrink-0">
                          {(m.goals || 0) > 0 && (
                            <span className="text-emerald-600 dark:text-emerald-400 font-bold">
                              {m.goals}G
                            </span>
                          )}
                          {(m.assists || 0) > 0 && (
                            <span className="text-amber-600 dark:text-amber-400 font-bold">
                              {m.assists}A
                            </span>
                          )}
                        </div>
                        <div className="w-8 text-right shrink-0">
                          <RatingBadge rating={m.rating} />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* ── Empty state ── */}
              {!loading && recentMatches.length === 0 && (
                <p className="text-sm text-muted-foreground text-center py-3">
                  No recent match data available
                </p>
              )}
            </div>
          ) : null}
        </ScrollArea>

        <DrawerFooter className="pt-2">
          <Button variant="outline" size="sm" asChild className="w-full">
            <Link to={`/players/${playerId}`}>
              View full profile
              <ChevronRight className="h-3.5 w-3.5 ml-1" />
            </Link>
          </Button>
        </DrawerFooter>
      </DrawerContent>
    </Drawer>
  )
}
