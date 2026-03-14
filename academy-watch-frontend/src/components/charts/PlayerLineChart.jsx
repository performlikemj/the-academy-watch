import React from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'
import { CHART_STAT_COLORS, CHART_AXIS_COLOR, CHART_GRID_COLOR, CHART_TOOLTIP_BG, CHART_TOOLTIP_BORDER } from '../../lib/theme-constants'

const STAT_LABELS = {
  goals: 'Goals',
  assists: 'Assists',
  rating: 'Rating',
  minutes: 'Minutes',
  shots_total: 'Shots',
  shots_on: 'On Target',
  passes_total: 'Passes',
  passes_key: 'Key Passes',
  tackles_total: 'Tackles',
  duels_won: 'Duels Won',
  saves: 'Saves',
}

export function PlayerLineChart({ data }) {
  const chartData = data?.data || []
  const statKeys = data?.stat_keys || []
  
  if (!chartData.length) {
    return (
      <div className="text-center text-muted-foreground py-4 text-sm">
        No data available for line chart
      </div>
    )
  }
  
  // Format dates for display
  const formattedData = chartData.map((item) => ({
    ...item,
    displayDate: item.date 
      ? new Date(item.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
      : 'N/A',
  }))
  
  return (
    <div className="space-y-2">
      {data?.player?.name && (
        <div className="text-sm font-medium text-foreground/80">
          {data.player.name} - Stats Over Time
        </div>
      )}
      
      <div className="h-[300px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={formattedData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID_COLOR} />
            <XAxis
              dataKey="displayDate"
              tick={{ fontSize: 10, fill: CHART_AXIS_COLOR }}
            />
            <YAxis tick={{ fontSize: 10, fill: CHART_AXIS_COLOR }} />
            <Tooltip
              contentStyle={{
                backgroundColor: CHART_TOOLTIP_BG,
                border: `1px solid ${CHART_TOOLTIP_BORDER}`,
                borderRadius: '8px',
                boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)',
              }}
              labelFormatter={(value, payload) => {
                if (payload?.[0]?.payload?.match) {
                  return payload[0].payload.match
                }
                return value
              }}
            />
            <Legend 
              wrapperStyle={{ fontSize: 11, paddingTop: 10 }}
              iconType="circle"
              iconSize={8}
            />
            {statKeys.map((key) => (
              <Line
                key={key}
                type="monotone"
                dataKey={key}
                name={STAT_LABELS[key] || key.replace('_', ' ')}
                stroke={CHART_STAT_COLORS[key] || CHART_AXIS_COLOR}
                strokeWidth={2}
                dot={{ r: 4, fill: CHART_STAT_COLORS[key] || CHART_AXIS_COLOR }}
                activeDot={{ r: 6 }}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

export default PlayerLineChart

