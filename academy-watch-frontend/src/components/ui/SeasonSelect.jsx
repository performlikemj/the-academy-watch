import { useEffect, useState } from 'react'
import { APIService } from '@/lib/api'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { formatSeasonLabel } from '@/lib/seasons'
import { cn } from '@/lib/utils'

let seasonDirectoryPromise

function getSeasonDirectory() {
  if (!seasonDirectoryPromise) {
    seasonDirectoryPromise = APIService.getSeasons().catch((error) => {
      seasonDirectoryPromise = undefined
      throw error
    })
  }
  return seasonDirectoryPromise
}

export function SeasonSelect({
  value,
  onValueChange,
  onCurrentSeasonChange,
  className,
  ariaLabel = 'Select season',
}) {
  const [directory, setDirectory] = useState(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    let cancelled = false
    getSeasonDirectory()
      .then((data) => {
        if (!cancelled) {
          setDirectory(data)
          const currentSeason = Number(data?.current_season)
          if (Number.isInteger(currentSeason)) onCurrentSeasonChange?.(currentSeason)
        }
      })
      .catch(() => {
        if (!cancelled) setError(true)
      })
    return () => { cancelled = true }
  }, [onCurrentSeasonChange])

  const resolvedValue = value ?? directory?.current_season
  const selectedItem = directory?.seasons?.find((item) => Number(item.season) === Number(resolvedValue))

  return (
    <Select
      value={resolvedValue == null ? '' : String(resolvedValue)}
      onValueChange={(next) => {
        const season = Number(next)
        onValueChange?.(season, season === Number(directory?.current_season))
      }}
      disabled={!directory || error}
    >
      <SelectTrigger className={cn('w-full min-w-28 sm:w-auto', className)} aria-label={ariaLabel}>
        <SelectValue placeholder={error ? 'Unavailable' : 'Season'}>
          {resolvedValue == null ? null : (selectedItem?.label || formatSeasonLabel(resolvedValue))}
        </SelectValue>
      </SelectTrigger>
      <SelectContent>
        {(directory?.seasons || []).map((item) => (
          <SelectItem
            key={item.season}
            value={String(item.season)}
            className={cn(!item.has_rollup && 'text-muted-foreground/60')}
            title={item.has_rollup ? undefined : 'Season rollup not available'}
          >
            <span>{item.label}</span>
            {item.is_current ? (
              <span className="text-[10px] font-semibold uppercase tracking-wide text-primary">Current</span>
            ) : null}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

export default SeasonSelect
