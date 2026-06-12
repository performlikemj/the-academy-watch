import { useState, useEffect } from 'react'
import { APIService } from '@/lib/api'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { HeartPulse, CircleCheck } from 'lucide-react'

function formatDate(iso) {
  if (!iso) return null
  try {
    return new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
  } catch {
    return iso
  }
}

/**
 * Season availability — fixtures missed through injury/suspension, sourced
 * from API-Football's injuries feed. Renders nothing while loading or on
 * error so it never degrades the page.
 */
export function PlayerAvailability({ playerId }) {
  const [data, setData] = useState(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    if (!playerId) return
    let cancelled = false
    setData(null)
    setFailed(false)
    APIService.getPlayerAvailability(playerId)
      .then((res) => { if (!cancelled) setData(res) })
      .catch(() => { if (!cancelled) setFailed(true) })
    return () => { cancelled = true }
  }, [playerId])

  if (failed || !data) return null

  const absences = data.absences || []
  const total = data.summary?.total_absences || 0

  return (
    <Card className="overflow-hidden border-border/80">
      <div className="flex items-center justify-between gap-2 border-b border-border/60 bg-secondary/60 px-4 py-2.5">
        <span className="inline-flex items-center gap-2">
          <HeartPulse className="h-4 w-4 text-primary" />
          <h3 className="text-xs font-semibold uppercase tracking-wider text-foreground/70">
            Availability — {data.season}/{(data.season + 1) % 100}
          </h3>
        </span>
        {total > 0 && (
          <Badge className="bg-rose-50 text-rose-800 border-rose-200 whitespace-nowrap">
            {total} {total === 1 ? 'absence' : 'absences'}
          </Badge>
        )}
      </div>
      <CardContent className="p-0">
        {total === 0 ? (
          <p className="flex items-center gap-2 px-4 py-3.5 text-sm text-muted-foreground">
            <CircleCheck className="h-4 w-4 text-emerald-600" />
            No recorded injury or suspension absences this season.
          </p>
        ) : (
          <ul className="divide-y divide-border/50">
            {absences.slice(0, 6).map((absence, index) => (
              <li key={`${absence.fixture_id}-${index}`} className="flex items-center justify-between gap-3 px-4 py-2.5">
                <span className="min-w-0">
                  <span className="block truncate text-sm font-medium text-foreground">
                    {absence.reason || 'Unavailable'}
                  </span>
                  <span className="block truncate text-xs text-muted-foreground">
                    {[absence.type, absence.league_name].filter(Boolean).join(' · ')}
                  </span>
                </span>
                <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
                  {formatDate(absence.date)}
                </span>
              </li>
            ))}
            {absences.length > 6 && (
              <li className="px-4 py-2 text-xs text-muted-foreground">
                +{absences.length - 6} more missed fixtures
              </li>
            )}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}
