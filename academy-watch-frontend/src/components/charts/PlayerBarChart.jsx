import React from 'react'
import {
  BarChart,
  Bar,
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

export function PlayerBarChart({ data }) {
  const chartData = data?.data || []
  const statKeys = data?.stat_keys || []
  
  if (!chartData.length) {
    return (
      <div className="text-center text-muted-foreground py-4 text-sm">
        No data available for bar chart
      </div>
    )
  }
  
  // Format match names for display
  const formattedData = chartData.map((item) => ({
    ...item,
    name: item.match?.length > 20 
      ? item.match.slice(0, 17) + '...'
      : item.match || new Date(item.date).toLocaleDateString(),
  }))
  
  return (
    <div className="space-y-2">
      {data?.player?.name && (
        <div className="text-sm font-medium text-foreground/80">
          {data.player.name} - Per Match Stats
        </div>
      )}
      
      <div className="h-[300px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={formattedData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID_COLOR} />
            <XAxis
              dataKey="name"
              tick={{ fontSize: 10, fill: CHART_AXIS_COLOR }}
              angle={-45}
              textAnchor="end"
              height={60}
            />
            <YAxis tick={{ fontSize: 10, fill: CHART_AXIS_COLOR }} />
            <Tooltip
              contentStyle={{
                backgroundColor: CHART_TOOLTIP_BG,
                border: `1px solid ${CHART_TOOLTIP_BORDER}`,
                borderRadius: '8px',
                boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)',
              }}
              labelStyle={{ fontWeight: 600, marginBottom: 4 }}
            />
            <Legend 
              wrapperStyle={{ fontSize: 11, paddingTop: 10 }}
              iconType="circle"
              iconSize={8}
            />
            {statKeys.map((key) => (
              <Bar
                key={key}
                dataKey={key}
                name={STAT_LABELS[key] || key.replace('_', ' ')}
                fill={CHART_STAT_COLORS[key] || CHART_AXIS_COLOR}
                radius={[4, 4, 0, 0]}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

export default PlayerBarChart

