import React, { useState, useEffect } from 'react'
import { Loader2 } from 'lucide-react'
import { APIService } from '@/lib/api'
import { MatchPerformanceCards } from '../charts/MatchPerformanceCards'
import { PlayerRadarChart } from '../charts/PlayerRadarChart'
import { PlayerBarChart } from '../charts/PlayerBarChart'
import { PlayerLineChart } from '../charts/PlayerLineChart'
import { PlayerStatTable } from '../charts/PlayerStatTable'

export function ChartPreview({ block, playerId, weekRange, previewData: externalData }) {
  const [data, setData] = useState(externalData || null)
  const [loading, setLoading] = useState(!externalData)
  const [error, setError] = useState(null)

  // Use player_id from props OR from block's chart_config (for intro/summary commentaries)
  const effectivePlayerId = playerId || block?.chart_config?.player_id

  useEffect(() => {
    // Use external data if provided
    if (externalData) {
      setData(externalData)
      setLoading(false)
      return
    }

    // Otherwise fetch data
    const fetchData = async () => {
      if (!effectivePlayerId || !block?.chart_type) {
        setData(null)
        setLoading(false)
        return
      }

      setLoading(true)
      setError(null)

      try {
        const params = {
          player_id: effectivePlayerId,
          chart_type: block.chart_type,
          stat_keys: block.chart_config?.stat_keys?.join(',') || 'goals,assists,rating',
          date_range: block.chart_config?.date_range || 'week',
        }

        if (params.date_range === 'week' && weekRange?.start && weekRange?.end) {
          params.week_start = weekRange.start
          params.week_end = weekRange.end
        }

        const result = await APIService.getChartData(params)
        setData(result)
      } catch (err) {
        console.error('Failed to fetch chart data:', err)
        setError('Failed to load chart data')
      } finally {
        setLoading(false)
      }
    }

    fetchData()
  }, [block, effectivePlayerId, weekRange, externalData])

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground/70" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="text-center text-red-500 py-4 text-sm">
        {error}
      </div>
    )
  }

  if (!data) {
    return (
      <div className="text-center text-muted-foreground py-4 text-sm">
        No data available for this player
      </div>
    )
  }

  const chartType = block?.chart_type || data?.chart_type

  switch (chartType) {
    case 'match_card':
      return <MatchPerformanceCards data={data} />

    case 'radar':
      return <PlayerRadarChart data={data} />

    case 'bar':
      return <PlayerBarChart data={data} />

    case 'line':
      return <PlayerLineChart data={data} />

    case 'stat_table':
      return <PlayerStatTable data={data} />

    default:
      return (
        <div className="text-center text-muted-foreground py-4 text-sm">
          Unknown chart type: {chartType}
        </div>
      )
  }
}

export default ChartPreview

