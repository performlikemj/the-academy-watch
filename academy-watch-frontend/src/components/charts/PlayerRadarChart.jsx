import React from 'react'
import {
  Radar,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  ResponsiveContainer,
  Tooltip,
} from 'recharts'
import { CHART_POSITION_COLORS, CHART_AXIS_COLOR } from '../../lib/theme-constants'

export function PlayerRadarChart({ data }) {
  const radarData = data?.data || []
  const matchesCount = data?.matches_count || 0
  const position = data?.position || 'Unknown'
  const positionCategory = data?.position_category || 'Midfielder'
  
  if (!radarData.length) {
    return (
      <div className="text-center text-muted-foreground py-4 text-sm">
        No data available for radar chart
      </div>
    )
  }
  
  // Transform data for recharts - use pre-normalized values from backend
  const chartData = radarData.map((item) => ({
    stat: item.label,
    value: item.normalized || 0,  // Pre-normalized 0-100 from backend
    avgPerGame: item.value,       // Average per game
    total: item.total,            // Total across matches
    maxValue: item.max_value,     // Position-adjusted max per game
  }))
  
  const chartColor = CHART_POSITION_COLORS[positionCategory] || CHART_AXIS_COLOR
  
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        {data?.player?.name && (
          <div className="text-sm font-medium text-foreground/80">
            {data.player.name} - {matchesCount} match{matchesCount !== 1 ? 'es' : ''}
          </div>
        )}
        {position !== 'Unknown' && (
          <div 
            className="text-xs px-2 py-0.5 rounded-full font-medium"
            style={{ 
              backgroundColor: `${chartColor}20`, 
              color: chartColor 
            }}
          >
            {position} ({positionCategory})
          </div>
        )}
      </div>
      
      <div className="h-[300px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <RadarChart data={chartData} cx="50%" cy="50%" outerRadius="80%">
            <PolarGrid gridType="polygon" />
            <PolarAngleAxis 
              dataKey="stat" 
              tick={{ fontSize: 11, fill: CHART_AXIS_COLOR }}
            />
            <PolarRadiusAxis 
              angle={30} 
              domain={[0, 100]} 
              tick={{ fontSize: 10 }}
              tickCount={5}
            />
            <Radar
              name="Stats"
              dataKey="value"
              stroke={chartColor}
              fill={chartColor}
              fillOpacity={0.4}
              strokeWidth={2}
            />
            <Tooltip
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null
                const item = payload[0].payload
                return (
                  <div className="bg-card border shadow-lg rounded-lg px-3 py-2 min-w-[160px]">
                    <div className="font-semibold text-sm text-foreground mb-1">{item.stat}</div>
                    <div className="space-y-0.5 text-xs">
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Per game:</span>
                        <span className="font-medium">{item.avgPerGame}</span>
                      </div>
                      {matchesCount > 1 && (
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">Total:</span>
                          <span className="font-medium">{item.total}</span>
                        </div>
                      )}
                      <div className="flex justify-between text-muted-foreground/70 pt-1 border-t mt-1">
                        <span>vs {positionCategory} avg:</span>
                        <span className="font-medium" style={{ color: chartColor }}>{item.value}%</span>
                      </div>
                      <div className="flex justify-between text-muted-foreground/70">
                        <span>Expected max:</span>
                        <span>{item.maxValue}/game</span>
                      </div>
                    </div>
                  </div>
                )
              }}
            />
          </RadarChart>
        </ResponsiveContainer>
      </div>
      
      {/* Legend explanation */}
      <div className="text-xs text-muted-foreground text-center">
        Values normalized to % of expected {positionCategory.toLowerCase()} performance per game
      </div>
    </div>
  )
}

export default PlayerRadarChart

