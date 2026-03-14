import React, { useRef, useEffect, useState, useCallback } from 'react'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

const STAT_LABELS = {
  minutes: 'Min',
  rating: 'Rating',
  goals: 'G',
  assists: 'A',
  shots_total: 'Shots',
  shots_on: 'On T',
  passes_total: 'Pass',
  passes_key: 'Key',
  tackles_total: 'Tck',
  tackles_blocks: 'Blk',
  tackles_interceptions: 'Int',
  duels_total: 'Duel',
  duels_won: 'Won',
  yellows: 'Y',
  reds: 'R',
  saves: 'Sav',
  goals_conceded: 'GC',
}

export function PlayerStatTable({ data }) {
  const tableData = data?.data || []
  const statKeys = data?.stat_keys || []
  const totals = data?.totals || {}
  const scrollRef = useRef(null)
  const [canScrollLeft, setCanScrollLeft] = useState(false)
  const [canScrollRight, setCanScrollRight] = useState(false)

  const updateScrollIndicators = useCallback(() => {
    const el = scrollRef.current
    if (!el) return
    setCanScrollLeft(el.scrollLeft > 4)
    setCanScrollRight(el.scrollLeft < el.scrollWidth - el.clientWidth - 4)
  }, [])

  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    updateScrollIndicators()
    el.addEventListener('scroll', updateScrollIndicators, { passive: true })
    const ro = new ResizeObserver(updateScrollIndicators)
    ro.observe(el)
    return () => {
      el.removeEventListener('scroll', updateScrollIndicators)
      ro.disconnect()
    }
  }, [tableData.length, updateScrollIndicators])

  if (!tableData.length) {
    return (
      <div className="text-center text-muted-foreground py-4 text-sm">
        No data available for stats table
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {data?.player?.name && (
        <div className="text-sm font-medium text-foreground/80">
          {data.player.name} - {data.matches_count || tableData.length} match{(data.matches_count || tableData.length) !== 1 ? 'es' : ''}
        </div>
      )}

      <div className="relative rounded-lg border">
        {canScrollLeft && (
          <div className="absolute left-0 top-0 bottom-0 w-6 bg-gradient-to-r from-card to-transparent z-10 pointer-events-none rounded-l-lg" />
        )}
        {canScrollRight && (
          <div className="absolute right-0 top-0 bottom-0 w-6 bg-gradient-to-l from-card to-transparent z-10 pointer-events-none rounded-r-lg" />
        )}
        <div ref={scrollRef} className="overflow-x-auto scrollbar-hide">
          <Table>
            <TableHeader>
              <TableRow className="bg-secondary">
                <TableHead className="text-xs font-semibold">Date</TableHead>
                <TableHead className="text-xs font-semibold">Opponent</TableHead>
                <TableHead className="text-xs font-semibold text-center">Result</TableHead>
                {statKeys.map((key) => (
                  <TableHead key={key} className="text-xs font-semibold text-center">
                    {STAT_LABELS[key] || key}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {tableData.map((row, idx) => {
                const resultParts = row.result?.split('-') || []
                const homeScore = parseInt(resultParts[0]) || 0
                const awayScore = parseInt(resultParts[1]) || 0
                const isWin = row.is_home ? homeScore > awayScore : awayScore > homeScore
                const isDraw = homeScore === awayScore

                return (
                  <TableRow key={idx} className="hover:bg-secondary">
                    <TableCell className="text-xs">
                      {row.date ? new Date(row.date).toLocaleDateString('en-US', {
                        month: 'short',
                        day: 'numeric'
                      }) : 'N/A'}
                    </TableCell>
                    <TableCell className="text-xs">
                      <div className="flex items-center gap-1">
                        <span className={cn(
                          'inline-block w-1.5 h-1.5 rounded-full',
                          row.is_home ? 'bg-emerald-500' : 'bg-muted-foreground/70'
                        )} />
                        {row.opponent}
                      </div>
                    </TableCell>
                    <TableCell className="text-center">
                      <Badge
                        variant="outline"
                        className={cn(
                          'text-xs font-mono tabular-nums',
                          isWin && 'bg-emerald-50 text-emerald-700 border-emerald-200',
                          isDraw && 'bg-secondary text-foreground/80 border-border',
                          !isWin && !isDraw && 'bg-rose-50 text-rose-700 border-rose-200'
                        )}
                      >
                        {row.result}
                      </Badge>
                    </TableCell>
                    {statKeys.map((key) => {
                      const value = row[key]
                      const isHighlight =
                        (key === 'goals' || key === 'assists') && value > 0 ||
                        key === 'rating' && value >= 7

                      return (
                        <TableCell
                          key={key}
                          className={cn(
                            'text-xs text-center tabular-nums',
                            isHighlight && 'font-bold text-emerald-700'
                          )}
                        >
                          {key === 'rating' && value ? value.toFixed(1) : (value ?? '-')}
                        </TableCell>
                      )
                    })}
                  </TableRow>
                )
              })}

              {/* Totals row */}
              {Object.keys(totals).length > 0 && (
                <TableRow className="bg-secondary font-semibold">
                  <TableCell className="text-xs" colSpan={3}>
                    Totals / Averages
                  </TableCell>
                  {statKeys.map((key) => (
                    <TableCell key={key} className="text-xs text-center tabular-nums">
                      {key === 'rating' && totals[key]
                        ? totals[key].toFixed(1)
                        : (totals[key] ?? '-')}
                    </TableCell>
                  ))}
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </div>
    </div>
  )
}

export default PlayerStatTable
